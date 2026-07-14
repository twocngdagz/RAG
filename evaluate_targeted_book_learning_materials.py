import argparse
import hashlib
import json
import multiprocessing
import os
import re
import shutil
import sys
import time
import traceback
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv


load_dotenv()

EVALUATION_SCHEMA_VERSION = "targeted_v2_learning_materials_evaluation.v1"
CHECKPOINT_SCHEMA_VERSION = "targeted_v2_evaluation_checkpoint.v1"
TARGETED_SOURCE_CONCEPT_PROMPT_VERSION = "targeted_source_concepts.v1"
TARGETED_V2_COMPARISON_PROMPT_VERSION = "targeted_v2_comparison.v1"

V1_AUDIT_SCHEMA_VERSION = "book_claim_support_audit.v1"
V2_BOOK_SCHEMA_VERSION = "book_learning_materials.v2"
V2_CONTRACT_AUDIT_SCHEMA_VERSION = "book_learning_materials_contract_audit.v1"

DEFAULT_MODEL = "mistralai/mistral-medium-3.5-128b"
DEFAULT_NVIDIA_BASE_URL = os.getenv(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

SELECTED_CHAPTER_NUMBERS = [2, 11, 15, 16]
EXPECTED_LIVE_V1_RESULT_COUNT = 777

SUPPORT_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "SOURCE_DAMAGED",
    "NOT_A_FACTUAL_CLAIM",
}
SOURCE_GROUNDED_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "SOURCE_DAMAGED",
}
UNSAFE_SOURCE_STATUSES = {
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "SOURCE_DAMAGED",
}
PEDAGOGICAL_STATUSES = {"USABLE", "NEEDS_REVISION", "MISLEADING"}
ABSTENTION_STATUSES = {"JUSTIFIED", "OVERCAUTIOUS", "MISALIGNED"}
CONCEPT_IMPORTANCES = {"HIGH", "MEDIUM", "LOW"}
CONCEPT_TYPES = {
    "official_rule",
    "task_format",
    "definition",
    "strategy",
    "language_rule",
    "practice_skill",
    "source_topic",
    "other",
}
SOURCE_CONDITIONS = {"CLEAR", "AMBIGUOUS", "DAMAGED"}
SEVERITIES = {"HIGH", "MEDIUM", "LOW"}
CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}
V1_COVERAGE_STATUSES = {
    "COVERED_SAFELY",
    "PARTIALLY_COVERED",
    "COVERED_UNSAFELY",
    "OMITTED",
}
V2_COVERAGE_STATUSES = {
    "COVERED_SAFELY",
    "PARTIALLY_COVERED",
    "SAFELY_WITHHELD",
    "SILENTLY_OMITTED",
    "COVERED_UNSAFELY",
}
ORIGINS = {
    "source_grounded",
    "pedagogical_generation",
    "insufficient_source_evidence",
}

KNOWN_PATTERN_PROBES = [
    {
        "probe_id": "wanted_pronunciation",
        "chapter_number": 2,
        "v1_claim_id": "chapter_02.worked_examples.2.explanation",
        "label": "Wanted pronunciation",
    },
    {
        "probe_id": "spelling_zero_score",
        "chapter_number": 11,
        "v1_claim_id": "chapter_11.common_misconceptions.2.correction",
        "label": "Spelling/zero-score",
    },
    {
        "probe_id": "highlight_correct_summary",
        "chapter_number": 15,
        "v1_claim_id": "chapter_15.key_terms.1.meaning",
        "label": "Highlight Correct Summary",
    },
    {
        "probe_id": "essay_timing",
        "chapter_number": 16,
        "v1_claim_id": "chapter_16.core_lessons.4.explanation",
        "label": "Essay timing",
    },
]


class TargetedEvaluationError(Exception):
    pass


class ModelCallError(TargetedEvaluationError):
    pass


class ModelCallTimeoutError(ModelCallError):
    pass


class ModelJSONError(TargetedEvaluationError):
    pass


@dataclass
class RuntimeStats:
    model_call_count: int = 0
    repair_call_count: int = 0


@dataclass(frozen=True)
class InputBundle:
    selected_chapter_numbers: list[int]
    v1_book: dict[str, Any]
    v1_audit: dict[str, Any]
    v2_book: dict[str, Any]
    v2_contract_audit: dict[str, Any]
    clean_chunks: list[dict[str, Any]]
    clean_chunks_by_id: dict[str, dict[str, Any]]
    input_hashes: dict[str, str]
    v1_results: list[dict[str, Any]]
    v1_results_by_id: dict[str, dict[str, Any]]
    v1_results_by_chapter: dict[int, list[dict[str, Any]]]
    v2_chapters: list[dict[str, Any]]
    v2_records: list[dict[str, Any]]
    v2_records_by_chapter: dict[int, list[dict[str, Any]]]
    chunks_by_chapter: dict[int, list[dict[str, Any]]]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate targeted book_learning_materials.v2 chapters for semantic "
            "safety and source-concept retention."
        )
    )
    parser.add_argument("--v1-book-file", required=True)
    parser.add_argument("--v1-audit-file", required=True)
    parser.add_argument("--v2-book-file", required=True)
    parser.add_argument("--v2-contract-audit-file", required=True)
    parser.add_argument("--clean-chunks-file", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--checkpoint")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-timeout-seconds", type=int, default=180)
    parser.add_argument("--model-max-retries", type=int, default=2)
    parser.add_argument("--model-retry-backoff-seconds", type=float, default=5)
    parser.add_argument("--max-new-evaluation-chapters", type=positive_int)
    parser.add_argument("--evaluation-chapter-number", type=positive_int)
    parser.add_argument("--reevaluate-selected-chapter", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def text_preview(value: str, max_chars: int = 220) -> str:
    normalized = normalize_text(value)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise TargetedEvaluationError(f"{label} does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise TargetedEvaluationError(f"{label} is not valid JSON: {path}: {error}") from error


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def default_checkpoint_path(output_path: Path) -> Path:
    if output_path.name.endswith(".json"):
        return output_path.with_name(output_path.name[: -len(".json")] + ".checkpoint.json")
    return output_path.with_name(output_path.name + ".checkpoint.json")


def raw_dir_for_output(output_path: Path) -> Path:
    if output_path.name.endswith(".json"):
        return output_path.with_name(output_path.name[: -len(".json")] + ".raw")
    return output_path.with_name(output_path.name + ".raw")


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargetedEvaluationError(f"{label} must be a JSON object.")
    return value


def require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TargetedEvaluationError(f"{label} must be a JSON array.")
    return value


def clean_chunk_id(chunk: dict[str, Any]) -> str | None:
    for key in ("id", "node_id", "chunk_id"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def validate_v1_book(
    data: Any,
    *,
    selected_chapter_numbers: list[int],
) -> dict[str, Any]:
    book = require_object(data, "V1 book")
    materials = require_object(book.get("learning_materials"), "V1 book learning_materials")
    chapters = require_list(materials.get("chapters"), "V1 book chapters")
    by_number: dict[int, str] = {}
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            raise TargetedEvaluationError(f"V1 chapter at index {index} must be an object.")
        number = chapter.get("chapter_number")
        title = chapter.get("chapter_title")
        if not isinstance(number, int) or number <= 0:
            raise TargetedEvaluationError(f"V1 chapter {index} has invalid chapter_number.")
        if number in by_number:
            raise TargetedEvaluationError(f"Duplicate V1 chapter_number: {number}")
        if not isinstance(title, str) or not title.strip():
            raise TargetedEvaluationError(f"V1 chapter {number} has empty chapter_title.")
        by_number[number] = title.strip()
    missing = [number for number in selected_chapter_numbers if number not in by_number]
    if missing:
        raise TargetedEvaluationError(f"V1 book is missing selected chapters: {missing}")
    return book


def validate_v1_audit(
    data: Any,
    *,
    expected_result_count: int | None = EXPECTED_LIVE_V1_RESULT_COUNT,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    audit = require_object(data, "V1 audit")
    if audit.get("schema_version") != V1_AUDIT_SCHEMA_VERSION:
        raise TargetedEvaluationError(
            f"V1 audit schema_version must be {V1_AUDIT_SCHEMA_VERSION}."
        )
    if audit.get("run_status") != "COMPLETE":
        raise TargetedEvaluationError("V1 audit run_status must be COMPLETE.")
    results = require_list(audit.get("results"), "V1 audit results")
    if expected_result_count is not None and len(results) != expected_result_count:
        raise TargetedEvaluationError(
            f"V1 audit must contain {expected_result_count} results, got {len(results)}."
        )
    by_id: dict[str, dict[str, Any]] = {}
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise TargetedEvaluationError(f"V1 audit result {index} must be an object.")
        claim_id = result.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise TargetedEvaluationError(f"V1 audit result {index} has empty claim_id.")
        if claim_id in by_id:
            raise TargetedEvaluationError(f"Duplicate V1 audit claim_id: {claim_id}")
        status = result.get("support_status")
        if status not in SUPPORT_STATUSES:
            raise TargetedEvaluationError(f"{claim_id} has invalid support_status: {status}")
        for field in ("claim_text", "claim_type", "rationale", "severity"):
            if field not in result:
                raise TargetedEvaluationError(f"{claim_id} is missing {field}.")
        if result.get("severity") not in SEVERITIES:
            raise TargetedEvaluationError(f"{claim_id} has invalid severity.")
        by_id[claim_id] = result
    return audit, results, by_id


def validate_v2_book(
    data: Any,
    *,
    selected_chapter_numbers: list[int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    book = require_object(data, "V2 book")
    if book.get("schema_version") != V2_BOOK_SCHEMA_VERSION:
        raise TargetedEvaluationError(
            f"V2 book schema_version must be {V2_BOOK_SCHEMA_VERSION}."
        )
    generation = require_object(book.get("generation"), "V2 generation")
    if generation.get("pipeline_version") != V2_BOOK_SCHEMA_VERSION:
        raise TargetedEvaluationError("V2 generation pipeline_version mismatch.")
    if generation.get("selection_mode") != "chapters":
        raise TargetedEvaluationError("V2 generation selection_mode must be chapters.")
    available_selected = generation.get("selected_chapter_numbers")
    if not isinstance(available_selected, list):
        raise TargetedEvaluationError(
            "V2 selected_chapter_numbers must be an array."
        )
    missing_selected = [
        number for number in selected_chapter_numbers if number not in available_selected
    ]
    if missing_selected:
        raise TargetedEvaluationError(
            "V2 selected_chapter_numbers is missing requested chapters: "
            f"{missing_selected}."
        )
    if generation.get("book_synthesis_performed") is not False:
        raise TargetedEvaluationError("V2 book_synthesis_performed must be false.")
    materials = require_object(book.get("learning_materials"), "V2 learning_materials")
    chapters = require_list(materials.get("chapters"), "V2 chapters")
    ordered_numbers = [
        chapter.get("chapter_number")
        for chapter in chapters
        if isinstance(chapter, dict)
        and chapter.get("chapter_number") in set(selected_chapter_numbers)
    ]
    if ordered_numbers != selected_chapter_numbers:
        raise TargetedEvaluationError(
            f"V2 chapters must contain requested chapters in order {selected_chapter_numbers}, got {ordered_numbers}."
        )
    chapters_by_number = {
        chapter.get("chapter_number"): chapter
        for chapter in chapters
        if isinstance(chapter, dict)
    }
    missing_chapters = [
        number for number in selected_chapter_numbers if number not in chapters_by_number
    ]
    if missing_chapters:
        raise TargetedEvaluationError(
            f"V2 chapters are missing requested chapters: {missing_chapters}."
        )
    selected_chapters = [chapters_by_number[number] for number in selected_chapter_numbers]
    for chapter in selected_chapters:
        if not isinstance(chapter.get("chapter_title"), str) or not chapter["chapter_title"].strip():
            raise TargetedEvaluationError(
                f"V2 chapter {chapter.get('chapter_number')} has empty chapter_title."
            )
    return book, selected_chapters


def validate_v2_contract_audit(data: Any) -> dict[str, Any]:
    audit = require_object(data, "V2 contract audit")
    if audit.get("schema_version") != V2_CONTRACT_AUDIT_SCHEMA_VERSION:
        raise TargetedEvaluationError(
            f"V2 contract audit schema_version must be {V2_CONTRACT_AUDIT_SCHEMA_VERSION}."
        )
    if audit.get("status") != "PASS":
        raise TargetedEvaluationError("V2 contract audit status must be PASS.")
    summary = require_object(audit.get("summary"), "V2 contract audit summary")
    if summary.get("invalid_claim_count") != 0:
        raise TargetedEvaluationError("V2 contract audit invalid_claim_count must be 0.")
    if audit.get("errors") != []:
        raise TargetedEvaluationError("V2 contract audit errors must be empty.")
    return audit


def validate_clean_chunks(
    data: Any,
    *,
    selected_chapter_numbers: list[int],
    expected_source_pdf: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    if isinstance(data, dict):
        chunks = data.get("chunks") or data.get("nodes") or data.get("items")
    else:
        chunks = data
    chunks = require_list(chunks, "Clean chunks")
    lookup: dict[str, dict[str, Any]] = {}
    by_chapter: dict[int, list[dict[str, Any]]] = defaultdict(list)
    source_pdfs: set[str] = set()
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            raise TargetedEvaluationError(f"Clean chunk {index} must be an object.")
        node_id = clean_chunk_id(chunk)
        if not node_id:
            raise TargetedEvaluationError(f"Clean chunk {index} is missing a non-empty ID.")
        if node_id in lookup:
            raise TargetedEvaluationError(f"Duplicate clean chunk ID: {node_id}")
        if "text_preview" in chunk:
            # The field may be present in some artifacts, but this evaluator never uses it.
            pass
        source_pdf = chunk.get("source_pdf")
        if isinstance(source_pdf, str) and source_pdf.strip():
            source_pdfs.add(source_pdf.strip())
        chapter_number = chunk.get("chapter_number")
        if isinstance(chapter_number, int):
            by_chapter[chapter_number].append(chunk)
        text = chunk.get("text")
        if (
            chapter_number in set(selected_chapter_numbers)
            and (not isinstance(text, str) or not text.strip())
        ):
            raise TargetedEvaluationError(f"Selected clean chunk {node_id} has empty full text.")
        lookup[node_id] = chunk
    if expected_source_pdf:
        inconsistent = sorted(source for source in source_pdfs if source != expected_source_pdf)
        if inconsistent:
            raise TargetedEvaluationError(
                "Clean chunks contain source_pdf values inconsistent with the V2 book: "
                + ", ".join(inconsistent)
            )
    missing = [number for number in selected_chapter_numbers if not by_chapter.get(number)]
    if missing:
        raise TargetedEvaluationError(f"Clean chunks are missing selected chapters: {missing}")
    return list(chunks), lookup, dict(by_chapter)


def record_text_derivation(record: dict[str, Any], clean_chunks_by_id: dict[str, dict[str, Any]]) -> str:
    origin = record["origin"]
    if origin == "pedagogical_generation":
        return "pedagogical_generation"
    if origin == "insufficient_source_evidence":
        return "insufficient_source_evidence"
    learner_text = record.get("text")
    if not isinstance(learner_text, str) or not learner_text.strip():
        return "source_paraphrase"
    normalized_text = normalize_text(learner_text)
    for node_id in record.get("source_chunk_ids") or []:
        chunk = clean_chunks_by_id.get(node_id)
        if chunk and normalized_text in normalize_text(str(chunk.get("text") or "")):
            return "exact_source_text"
    return "source_paraphrase"


def grounded_field(
    chapter: dict[str, Any],
    chapter_index: int,
    chapter_number: int,
    chapter_title: str,
    relative_id: str,
    relative_path: str,
    value: Any,
    field_role: str,
    clean_chunks_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TargetedEvaluationError(
            f"V2 grounded content at chapter {chapter_number}.{relative_id} must be an object."
        )
    record = {
        "record_id": f"chapter_{chapter_number:02d}.{relative_id}",
        "json_path": f"$.learning_materials.chapters[{chapter_index}].{relative_path}",
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "field_role": field_role,
        "claim_kind": value.get("claim_kind"),
        "origin": value.get("origin"),
        "text": value.get("text"),
        "source_chunk_ids": list(value.get("source_chunk_ids") or []),
        "grounded_in_source_chunk_ids": list(value.get("grounded_in_source_chunk_ids") or []),
        "evidence_spans": list(value.get("evidence_spans") or []),
        "reason": value.get("reason"),
    }
    if record["origin"] not in ORIGINS:
        raise TargetedEvaluationError(f"{record['record_id']} has invalid origin.")
    record["text_derivation"] = record_text_derivation(record, clean_chunks_by_id)
    return record


def extract_v2_grounded_records(
    v2_chapters: list[dict[str, Any]],
    clean_chunks_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(v2_chapters):
        chapter_number = int(chapter["chapter_number"])
        chapter_title = str(chapter["chapter_title"])

        def add(relative_id: str, relative_path: str, value: Any, field_role: str) -> None:
            records.append(
                grounded_field(
                    chapter,
                    chapter_index,
                    chapter_number,
                    chapter_title,
                    relative_id,
                    relative_path,
                    value,
                    field_role,
                    clean_chunks_by_id,
                )
            )

        add("estimated_study_time", "estimated_study_time", chapter.get("estimated_study_time"), "estimated_study_time")
        add("chapter_summary", "chapter_summary", chapter.get("chapter_summary"), "chapter_summary")

        for index, item in enumerate(require_list(chapter.get("learning_objectives"), "learning_objectives")):
            add(f"learning_objectives.{index}", f"learning_objectives[{index}]", item, "learning_objective")

        for index, item in enumerate(require_list(chapter.get("key_terms"), "key_terms")):
            add(
                f"key_terms.{index}.meaning",
                f"key_terms[{index}].meaning",
                require_object(item, "key term").get("meaning"),
                "key_term_meaning",
            )

        for index, item in enumerate(require_list(chapter.get("core_lessons"), "core_lessons")):
            add(
                f"core_lessons.{index}.explanation",
                f"core_lessons[{index}].explanation",
                require_object(item, "core lesson").get("explanation"),
                "core_lesson_explanation",
            )

        for index, item in enumerate(require_list(chapter.get("worked_examples"), "worked_examples")):
            item = require_object(item, "worked example")
            add(
                f"worked_examples.{index}.example",
                f"worked_examples[{index}].example",
                item.get("example"),
                "worked_example_example",
            )
            add(
                f"worked_examples.{index}.explanation",
                f"worked_examples[{index}].explanation",
                item.get("explanation"),
                "worked_example_explanation",
            )

        for index, item in enumerate(require_list(chapter.get("common_misconceptions"), "common_misconceptions")):
            item = require_object(item, "common misconception")
            add(
                f"common_misconceptions.{index}.misconception",
                f"common_misconceptions[{index}].misconception",
                item.get("misconception"),
                "common_misconception_statement",
            )
            add(
                f"common_misconceptions.{index}.correction",
                f"common_misconceptions[{index}].correction",
                item.get("correction"),
                "common_misconception_correction",
            )

        for index, item in enumerate(require_list(chapter.get("practice_questions"), "practice_questions")):
            item = require_object(item, "practice question")
            add(
                f"practice_questions.{index}.question",
                f"practice_questions[{index}].question",
                item.get("question"),
                "practice_question",
            )
            add(
                f"practice_questions.{index}.answer",
                f"practice_questions[{index}].answer",
                item.get("answer"),
                "practice_answer",
            )

        for index, item in enumerate(require_list(chapter.get("review_checklist"), "review_checklist")):
            add(f"review_checklist.{index}", f"review_checklist[{index}]", item, "review_checklist_item")
    return records


def filter_v1_results_by_chapter(
    results: list[dict[str, Any]],
    *,
    selected_chapter_numbers: list[int],
) -> dict[int, list[dict[str, Any]]]:
    by_chapter: dict[int, list[dict[str, Any]]] = {number: [] for number in selected_chapter_numbers}
    selected = set(selected_chapter_numbers)
    for result in results:
        chapter_number = result.get("chapter_number")
        if chapter_number in selected:
            by_chapter[int(chapter_number)].append(result)
    return by_chapter


def load_and_validate_inputs(
    *,
    v1_book_file: Path,
    v1_audit_file: Path,
    v2_book_file: Path,
    v2_contract_audit_file: Path,
    clean_chunks_file: Path,
    selected_chapter_numbers: list[int] | None = None,
    expected_v1_result_count: int | None = EXPECTED_LIVE_V1_RESULT_COUNT,
) -> InputBundle:
    selected_chapter_numbers = selected_chapter_numbers or SELECTED_CHAPTER_NUMBERS[:]
    hashes = {
        "v1_book": sha256_file(v1_book_file),
        "v1_audit": sha256_file(v1_audit_file),
        "v2_book": sha256_file(v2_book_file),
        "v2_contract_audit": sha256_file(v2_contract_audit_file),
        "clean_chunks": sha256_file(clean_chunks_file),
    }
    v1_book = validate_v1_book(
        load_json(v1_book_file, "V1 book file"),
        selected_chapter_numbers=selected_chapter_numbers,
    )
    v1_audit, v1_results, v1_results_by_id = validate_v1_audit(
        load_json(v1_audit_file, "V1 audit file"),
        expected_result_count=expected_v1_result_count,
    )
    v2_book, v2_chapters = validate_v2_book(
        load_json(v2_book_file, "V2 book file"),
        selected_chapter_numbers=selected_chapter_numbers,
    )
    v2_contract_audit = validate_v2_contract_audit(
        load_json(v2_contract_audit_file, "V2 contract audit file")
    )
    source_pdf = None
    if isinstance(v2_book.get("book"), dict):
        value = v2_book["book"].get("source_pdf")
        if isinstance(value, str) and value.strip():
            source_pdf = value.strip()
    clean_chunks, clean_chunks_by_id, chunks_by_chapter = validate_clean_chunks(
        load_json(clean_chunks_file, "Clean chunks file"),
        selected_chapter_numbers=selected_chapter_numbers,
        expected_source_pdf=source_pdf,
    )
    v2_records = extract_v2_grounded_records(v2_chapters, clean_chunks_by_id)
    by_chapter: dict[int, list[dict[str, Any]]] = {number: [] for number in selected_chapter_numbers}
    for record in v2_records:
        by_chapter[int(record["chapter_number"])].append(record)
    v1_results_by_chapter = filter_v1_results_by_chapter(
        v1_results,
        selected_chapter_numbers=selected_chapter_numbers,
    )
    selected_v1_results = [
        result
        for number in selected_chapter_numbers
        for result in v1_results_by_chapter[number]
    ]
    selected_v1_results_by_id = {
        result["claim_id"]: result for result in selected_v1_results
    }

    return InputBundle(
        selected_chapter_numbers=selected_chapter_numbers,
        v1_book=v1_book,
        v1_audit=v1_audit,
        v2_book=v2_book,
        v2_contract_audit=v2_contract_audit,
        clean_chunks=clean_chunks,
        clean_chunks_by_id=clean_chunks_by_id,
        input_hashes=hashes,
        v1_results=selected_v1_results,
        v1_results_by_id=selected_v1_results_by_id,
        v1_results_by_chapter=v1_results_by_chapter,
        v2_chapters=v2_chapters,
        v2_records=v2_records,
        v2_records_by_chapter=by_chapter,
        chunks_by_chapter=chunks_by_chapter,
    )


def compact_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": clean_chunk_id(chunk),
        "chapter_number": chunk.get("chapter_number"),
        "section": chunk.get("section"),
        "topic": chunk.get("topic"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "text": chunk.get("text"),
    }


def quote_candidates_from_text(text: str, *, max_candidates: int = 12) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?])\s+|\s+•\s+|\s+\u2022\s+", normalized)
    candidates: list[str] = []
    seen: set[str] = set()
    for part in parts:
        candidate = part.strip()
        words = candidate.split()
        if 4 <= len(words) <= 80 and candidate not in seen:
            candidates.append(candidate)
            seen.add(candidate)
        if len(candidates) >= max_candidates:
            break
    return candidates


def concept_source_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    item = compact_chunk(chunk)
    item["quote_candidates"] = quote_candidates_from_text(str(chunk.get("text") or ""))
    return item


def allowed_quote_bank(chapter_chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    bank: list[dict[str, str]] = []
    for chunk in chapter_chunks:
        node_id = clean_chunk_id(chunk)
        if not node_id:
            continue
        for index, quote in enumerate(quote_candidates_from_text(str(chunk.get("text") or "")), start=1):
            bank.append(
                {
                    "node_id": node_id,
                    "quote_id": f"{node_id}.quote_{index:02d}",
                    "quote": quote,
                }
            )
    return bank


def chapter_title_from_v2(bundle: InputBundle, chapter_number: int) -> str:
    for chapter in bundle.v2_chapters:
        if chapter.get("chapter_number") == chapter_number:
            return str(chapter.get("chapter_title") or f"Chapter {chapter_number}")
    return f"Chapter {chapter_number}"


def build_source_concept_prompt(
    *,
    chapter_number: int,
    chapter_title: str,
    chapter_chunks: list[dict[str, Any]],
) -> str:
    source_chunks = [concept_source_chunk(chunk) for chunk in chapter_chunks]
    quote_bank = allowed_quote_bank(chapter_chunks)
    return f"""You are evaluating source text for a learning-materials grounding audit.

Return valid JSON only. Do not use Markdown or code fences.
Use only the supplied clean source chunks for this one chapter.
Do not use v1 generated material, v2 generated material, audit judgments, outside PTE knowledge, web content, or other chapters.
If OCR/layout damage prevents reliable extraction, mark the concept source_condition as DAMAGED instead of filling gaps.

Prompt version: {TARGETED_SOURCE_CONCEPT_PROMPT_VERSION}
Chapter number: {chapter_number}
Chapter title: {chapter_title}

Return this schema exactly:
{{
  "chapter_number": {chapter_number},
  "concepts": [
    {{
      "concept_id": "chapter_{chapter_number:02d}.concept_01",
      "title": "short concept title",
      "importance": "HIGH | MEDIUM | LOW",
      "concept_type": "official_rule | task_format | definition | strategy | language_rule | practice_skill | source_topic | other",
      "source_condition": "CLEAR | AMBIGUOUS | DAMAGED",
      "description": "one concise sentence grounded in source text",
      "source_chunk_ids": ["one or more supplied node IDs"],
      "evidence_spans": [
        {{
          "node_id": "one supplied node ID",
          "quote": "Exact source quote, 4 to 80 words"
        }}
      ]
    }}
  ]
}}

Rules:
- Extract between 4 and 15 important learner-relevant concepts.
- concept_id values must be sequential for this chapter: chapter_{chapter_number:02d}.concept_01, chapter_{chapter_number:02d}.concept_02, etc.
- Every evidence quote must appear exactly in the supplied clean text after whitespace normalization.
- evidence_spans.quote must be copied exactly from the allowed evidence quote bank for that same node_id.
- Do not manually quote from the text field; use the allowed evidence quote bank only for evidence_spans.quote.
- Do not paraphrase, correct punctuation, change case, merge non-contiguous text, or add ellipses inside evidence quotes.
- If no quote_candidate supports a concept, omit that concept.
- Do not reuse the same node_id plus quote pair for more than one concept.
- Do not add placeholder concepts.
- Do not include concepts unsupported by these chunks.

Allowed evidence quote bank:
{json.dumps(quote_bank, ensure_ascii=False, indent=2)}

Clean source chunks:
{json.dumps(source_chunks, ensure_ascii=False, indent=2)}
"""


def slim_v1_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": result.get("claim_id"),
        "claim_text": result.get("claim_text"),
        "claim_type": result.get("claim_type"),
        "support_status": result.get("support_status"),
        "severity": result.get("severity"),
        "rationale": result.get("rationale"),
    }


def slim_v2_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": record["record_id"],
        "field_role": record["field_role"],
        "claim_kind": record["claim_kind"],
        "origin": record["origin"],
        "text": record["text"],
        "reason": record["reason"],
        "source_chunk_ids": record["source_chunk_ids"],
        "grounded_in_source_chunk_ids": record["grounded_in_source_chunk_ids"],
        "evidence_spans": record["evidence_spans"],
        "text_derivation": record["text_derivation"],
    }


def probes_for_chapter(chapter_number: int) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in probe.items() if key != "label"}
        for probe in KNOWN_PATTERN_PROBES
        if probe["chapter_number"] == chapter_number
    ]


PROBE_ALIAS_RULES = {
    "wanted_pronunciation": {
        "any": [
            "wanted",
            "-ed ending",
            "ed ending",
            "past-tense ending",
            "past tense ending",
            "regular past tense",
        ]
    },
    "spelling_zero_score": {
        "any": [
            "spelling",
            "misspelled",
            "zero score",
            "write from dictation",
            "fill in the blanks",
            "partial credit",
        ]
    },
    "highlight_correct_summary": {
        "any": [
            "highlight correct summary",
            "correct summary",
            "summary task",
        ]
    },
    "essay_timing": {
        "all": ["essay"],
        "any": ["time", "timing", "minute", "minutes", "time limit"],
    },
}

PRONUNCIATION_RELATED_TERMS = [
    "pronunciation",
    "phonetic notation",
    "ipa",
    "word ending",
    "word endings",
    "-ed ending",
    "ed ending",
    "past-tense ending",
    "past tense ending",
]

DAMAGED_PRONUNCIATION_RE = re.compile(r"(�|//|/(?:\s*)/)")


def concept_search_text(concept: dict[str, Any]) -> str:
    parts = [
        str(concept.get("title") or ""),
        str(concept.get("description") or ""),
    ]
    for span in concept.get("evidence_spans") or []:
        if isinstance(span, dict):
            parts.append(str(span.get("quote") or ""))
    return normalize_text(" ".join(parts)).lower()


def concept_is_pronunciation_related(concept: dict[str, Any]) -> bool:
    search_text = concept_search_text(concept)
    return any(term in search_text for term in PRONUNCIATION_RELATED_TERMS)


def has_damaged_pronunciation_notation(concept: dict[str, Any]) -> bool:
    if not concept_is_pronunciation_related(concept):
        return False
    for span in concept.get("evidence_spans") or []:
        if isinstance(span, dict) and DAMAGED_PRONUNCIATION_RE.search(str(span.get("quote") or "")):
            return True
    return False


def concept_matches_probe_alias(concept: dict[str, Any], probe_id: str) -> bool:
    rules = PROBE_ALIAS_RULES.get(probe_id)
    if not rules:
        return True
    search_text = concept_search_text(concept)
    required = rules.get("all") or []
    alternatives = rules.get("any") or []
    if any(term not in search_text for term in required):
        return False
    return any(term in search_text for term in alternatives)


def deterministic_v1_coverage_status(
    *,
    concept: dict[str, Any],
    v1_claim_ids: list[str],
    v1_by_id: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, str]]:
    statuses = {
        claim_id: v1_by_id[claim_id]["support_status"]
        for claim_id in v1_claim_ids
    }
    if not statuses:
        return "OMITTED", statuses
    factual_statuses = {
        claim_id: status
        for claim_id, status in statuses.items()
        if status != "NOT_A_FACTUAL_CLAIM"
    }
    if not factual_statuses:
        raise ModelJSONError(
            f"{concept['concept_id']} maps only to NOT_A_FACTUAL_CLAIM v1 claims."
        )
    if any(
        status in {"UNSUPPORTED", "CONTRADICTED", "SOURCE_DAMAGED"}
        for status in factual_statuses.values()
    ):
        return "COVERED_UNSAFELY", statuses
    if any(status == "PARTIALLY_SUPPORTED" for status in factual_statuses.values()):
        return "PARTIALLY_COVERED", statuses
    if all(status == "SUPPORTED" for status in factual_statuses.values()):
        return "COVERED_SAFELY", statuses
    raise ModelJSONError(
        f"{concept['concept_id']} has unsupported v1 claim status combination: {statuses}"
    )


def build_chapter_evaluation_prompt(
    *,
    chapter_number: int,
    chapter_title: str,
    chapter_chunks: list[dict[str, Any]],
    concepts: dict[str, Any],
    v1_results: list[dict[str, Any]],
    v2_records: list[dict[str, Any]],
) -> str:
    return f"""You are evaluating a targeted book_learning_materials.v2 chapter against source evidence.

Return valid JSON only. Do not use Markdown or code fences.
Use only the supplied same-chapter source chunks, source concepts, v1 audit records, and v2 records.
Do not use other chapters, web content, or outside PTE knowledge.
Do not rejudge v1 claims. The supplied v1 support_status values are authoritative baseline data.

Prompt version: {TARGETED_V2_COMPARISON_PROMPT_VERSION}
Chapter number: {chapter_number}
Chapter title: {chapter_title}

Origin-specific rules:
- For source_grounded v2 records, set semantic_support_status to SUPPORTED, PARTIALLY_SUPPORTED, UNSUPPORTED, CONTRADICTED, or SOURCE_DAMAGED. Set the other two status fields to NOT_APPLICABLE.
- For pedagogical_generation v2 records, set pedagogical_quality_status to USABLE, NEEDS_REVISION, or MISLEADING. Set the other two status fields to NOT_APPLICABLE.
- For insufficient_source_evidence v2 records, set abstention_status to JUSTIFIED, OVERCAUTIOUS, or MISALIGNED. Set the other two status fields to NOT_APPLICABLE.
- For concept coverage, distinguish SAFELY_WITHHELD from SILENTLY_OMITTED. A safe withholding must cite a relevant insufficient_source_evidence record.

Return this schema exactly:
{{
  "chapter_number": {chapter_number},
  "v2_record_evaluations": [
    {{
      "record_id": "one supplied v2 record_id",
      "semantic_support_status": "SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED | SOURCE_DAMAGED | NOT_APPLICABLE",
      "pedagogical_quality_status": "USABLE | NEEDS_REVISION | MISLEADING | NOT_APPLICABLE",
      "abstention_status": "JUSTIFIED | OVERCAUTIOUS | MISALIGNED | NOT_APPLICABLE",
      "severity": "HIGH | MEDIUM | LOW",
      "confidence": "HIGH | MEDIUM | LOW",
      "rationale": "concise rationale",
      "supported_elements": [],
      "unsupported_elements": [],
      "contradicted_elements": [],
      "evidence_chunk_ids_used": [],
      "concept_ids": []
    }}
  ],
  "concept_coverage": [
    {{
      "concept_id": "one supplied concept_id",
      "importance": "HIGH | MEDIUM | LOW",
      "source_condition": "CLEAR | AMBIGUOUS | DAMAGED",
      "v1_coverage_status": "COVERED_SAFELY | PARTIALLY_COVERED | COVERED_UNSAFELY | OMITTED",
      "v1_claim_ids": [],
      "v2_coverage_status": "COVERED_SAFELY | PARTIALLY_COVERED | SAFELY_WITHHELD | SILENTLY_OMITTED | COVERED_UNSAFELY",
      "v2_record_ids": [],
      "rationale": "concise rationale"
    }}
  ],
  "known_pattern_traces": [
    {{
      "probe_id": "probe id supplied for this chapter",
      "chapter_number": {chapter_number},
      "source_condition": "CLEAR | AMBIGUOUS | DAMAGED",
      "matching_concept_ids": [],
      "v1_claim_id": "known v1 claim id",
      "v1_support_status": "SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED | SOURCE_DAMAGED | NOT_A_FACTUAL_CLAIM",
      "v2_status": "COVERED_SAFELY | PARTIALLY_COVERED | SAFELY_WITHHELD | SILENTLY_OMITTED | COVERED_UNSAFELY",
      "v2_record_ids": [],
      "conclusion": "concise conclusion"
    }}
  ]
}}

Complete same-chapter clean source chunks:
{json.dumps([compact_chunk(chunk) for chunk in chapter_chunks], ensure_ascii=False, indent=2)}

Validated source concepts:
{json.dumps(concepts, ensure_ascii=False, indent=2)}

V1 Step 34B baseline records for this chapter only:
{json.dumps([slim_v1_result(item) for item in v1_results], ensure_ascii=False, indent=2)}

V2 grounded-content records for this chapter:
{json.dumps([slim_v2_record(item) for item in v2_records], ensure_ascii=False, indent=2)}

Known-pattern probes for this chapter:
{json.dumps(probes_for_chapter(chapter_number), ensure_ascii=False, indent=2)}
"""


def parse_model_json(raw_response: str) -> Any:
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError:
        start = raw_response.find("{")
        end = raw_response.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw_response[start : end + 1])
            except json.JSONDecodeError as error:
                raise ModelJSONError(f"Model response is not valid JSON: {error}") from error
        raise ModelJSONError("Model response is not valid JSON.")


def validate_string_list(value: Any, *, label: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list):
        raise ModelJSONError(f"{label} must be an array.")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ModelJSONError(f"{label} must contain non-empty strings.")
        output.append(item.strip())
    duplicates = [item for item, count in Counter(output).items() if count > 1]
    if duplicates:
        raise ModelJSONError(f"{label} contains duplicates: {', '.join(duplicates)}")
    if not allow_empty and not output:
        raise ModelJSONError(f"{label} must not be empty.")
    return output


def validate_evidence_quote(
    *,
    quote: str,
    node_id: str,
    clean_chunks_by_id: dict[str, dict[str, Any]],
    label: str,
) -> str:
    normalized_quote = normalize_text(quote)
    words = normalized_quote.split()
    if len(words) < 4:
        raise ModelJSONError(f"{label} quote must contain at least 4 words.")
    if len(words) > 80:
        raise ModelJSONError(f"{label} quote must contain at most 80 words.")
    chunk = clean_chunks_by_id.get(node_id)
    if chunk is None:
        raise ModelJSONError(f"{label} references unknown source chunk ID: {node_id}")
    if normalized_quote not in normalize_text(str(chunk.get("text") or "")):
        raise ModelJSONError(f"{label} quote was not found in clean source text.")
    return quote


def validate_source_concept_inventory(
    parsed: Any,
    *,
    chapter_number: int,
    chapter_chunks: list[dict[str, Any]],
    clean_chunks_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    data = require_model_object(parsed, "Source concept response")
    if data.get("chapter_number") != chapter_number:
        raise ModelJSONError(f"Source concept response must be for chapter {chapter_number}.")
    concepts = require_model_list(data.get("concepts"), "concepts")
    if not 4 <= len(concepts) <= 15:
        raise ModelJSONError("Source concept response must contain between 4 and 15 concepts.")
    chapter_source_ids = {clean_chunk_id(chunk) for chunk in chapter_chunks}
    chapter_source_ids.discard(None)
    seen_concepts: set[str] = set()
    normalized_concepts: list[dict[str, Any]] = []
    for index, item in enumerate(concepts, start=1):
        concept = require_model_object(item, f"concepts[{index - 1}]")
        expected_id = f"chapter_{chapter_number:02d}.concept_{index:02d}"
        concept_id = concept.get("concept_id")
        if concept_id != expected_id:
            raise ModelJSONError(f"Expected concept_id {expected_id}, got {concept_id!r}.")
        if concept_id in seen_concepts:
            raise ModelJSONError(f"Duplicate concept_id: {concept_id}")
        seen_concepts.add(concept_id)
        if concept.get("importance") not in CONCEPT_IMPORTANCES:
            raise ModelJSONError(f"{concept_id} has invalid importance.")
        if concept.get("concept_type") not in CONCEPT_TYPES:
            raise ModelJSONError(f"{concept_id} has invalid concept_type.")
        if concept.get("source_condition") not in SOURCE_CONDITIONS:
            raise ModelJSONError(f"{concept_id} has invalid source_condition.")
        for field in ("title", "description"):
            if not isinstance(concept.get(field), str) or not concept[field].strip():
                raise ModelJSONError(f"{concept_id} has empty {field}.")
        source_ids = validate_string_list(
            concept.get("source_chunk_ids"), label=f"{concept_id}.source_chunk_ids", allow_empty=False
        )
        unknown = [node_id for node_id in source_ids if node_id not in chapter_source_ids]
        if unknown:
            raise ModelJSONError(f"{concept_id} references source IDs outside the chapter: {unknown}")
        spans = require_model_list(concept.get("evidence_spans"), f"{concept_id}.evidence_spans")
        if not spans:
            raise ModelJSONError(f"{concept_id} must include at least one evidence span.")
        normalized_spans: list[dict[str, str]] = []
        seen_spans: set[tuple[str, str]] = set()
        for span_index, span in enumerate(spans):
            span_obj = require_model_object(span, f"{concept_id}.evidence_spans[{span_index}]")
            node_id = span_obj.get("node_id")
            quote = span_obj.get("quote")
            if not isinstance(node_id, str) or not node_id.strip():
                raise ModelJSONError(f"{concept_id} evidence span has empty node_id.")
            node_id = node_id.strip()
            if node_id not in source_ids:
                raise ModelJSONError(f"{concept_id} evidence span node_id is not in source_chunk_ids.")
            if not isinstance(quote, str) or not quote.strip():
                raise ModelJSONError(f"{concept_id} evidence span has empty quote.")
            normalized_quote = normalize_text(quote)
            key = (node_id, normalized_quote)
            if key in seen_spans:
                raise ModelJSONError(f"Duplicate evidence span in source concepts: {node_id}")
            seen_spans.add(key)
            validate_evidence_quote(
                quote=quote,
                node_id=node_id,
                clean_chunks_by_id=clean_chunks_by_id,
                label=f"{concept_id}.evidence_spans[{span_index}]",
            )
            normalized_spans.append({"node_id": node_id, "quote": quote})
        source_condition = concept["source_condition"]
        source_condition_warnings: list[dict[str, Any]] = []
        normalized_candidate = {
            "concept_id": concept_id,
            "title": concept["title"].strip(),
            "description": concept["description"].strip(),
            "evidence_spans": normalized_spans,
        }
        if source_condition != "DAMAGED" and has_damaged_pronunciation_notation(normalized_candidate):
            source_condition_warnings.append(
                {
                    "code": "PRONUNCIATION_SOURCE_DAMAGED",
                    "concept_id": concept_id,
                    "previous_source_condition": source_condition,
                }
            )
            source_condition = "DAMAGED"
        normalized_concepts.append(
            {
                "concept_id": concept_id,
                "title": concept["title"].strip(),
                "importance": concept["importance"],
                "concept_type": concept["concept_type"],
                "source_condition": source_condition,
                "description": concept["description"].strip(),
                "source_chunk_ids": source_ids,
                "evidence_spans": normalized_spans,
                "warnings": source_condition_warnings,
            }
        )
    return {"chapter_number": chapter_number, "concepts": normalized_concepts}


def require_model_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelJSONError(f"{label} must be a JSON object.")
    return value


def require_model_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelJSONError(f"{label} must be a JSON array.")
    return value


def validate_chapter_evaluation(
    parsed: Any,
    *,
    chapter_number: int,
    concepts: dict[str, Any],
    v1_results: list[dict[str, Any]],
    v2_records: list[dict[str, Any]],
    chapter_chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    data = require_model_object(parsed, "Chapter evaluation response")
    if data.get("chapter_number") != chapter_number:
        raise ModelJSONError(f"Chapter evaluation response must be for chapter {chapter_number}.")
    concept_items = concepts["concepts"]
    concept_ids = [item["concept_id"] for item in concept_items]
    concept_lookup = {item["concept_id"]: item for item in concept_items}
    v1_ids = {item["claim_id"] for item in v1_results}
    v1_by_id = {item["claim_id"]: item for item in v1_results}
    record_ids = [item["record_id"] for item in v2_records]
    record_lookup = {item["record_id"]: item for item in v2_records}
    chapter_source_ids = {clean_chunk_id(chunk) for chunk in chapter_chunks}
    chapter_source_ids.discard(None)

    raw_evaluations = require_model_list(data.get("v2_record_evaluations"), "v2_record_evaluations")
    seen_records: set[str] = set()
    normalized_evaluations_by_id: dict[str, dict[str, Any]] = {}
    for item in raw_evaluations:
        result = require_model_object(item, "v2 record evaluation")
        record_id = result.get("record_id")
        if record_id not in record_lookup:
            raise ModelJSONError(f"Evaluation returned unknown v2 record_id: {record_id}")
        if record_id in seen_records:
            raise ModelJSONError(f"Duplicate v2 record evaluation: {record_id}")
        seen_records.add(record_id)
        record = record_lookup[record_id]
        semantic = result.get("semantic_support_status")
        pedagogical = result.get("pedagogical_quality_status")
        abstention = result.get("abstention_status")
        if semantic not in SOURCE_GROUNDED_STATUSES | {"NOT_APPLICABLE"}:
            raise ModelJSONError(f"{record_id} has invalid semantic_support_status.")
        if pedagogical not in PEDAGOGICAL_STATUSES | {"NOT_APPLICABLE"}:
            raise ModelJSONError(f"{record_id} has invalid pedagogical_quality_status.")
        if abstention not in ABSTENTION_STATUSES | {"NOT_APPLICABLE"}:
            raise ModelJSONError(f"{record_id} has invalid abstention_status.")
        origin = record["origin"]
        if origin == "source_grounded":
            if semantic == "NOT_APPLICABLE" or pedagogical != "NOT_APPLICABLE" or abstention != "NOT_APPLICABLE":
                raise ModelJSONError(f"{record_id} has invalid source_grounded status combination.")
        elif origin == "pedagogical_generation":
            if semantic != "NOT_APPLICABLE" or pedagogical == "NOT_APPLICABLE" or abstention != "NOT_APPLICABLE":
                raise ModelJSONError(f"{record_id} has invalid pedagogical status combination.")
        elif origin == "insufficient_source_evidence":
            if semantic != "NOT_APPLICABLE" or pedagogical != "NOT_APPLICABLE" or abstention == "NOT_APPLICABLE":
                raise ModelJSONError(f"{record_id} has invalid insufficient-evidence status combination.")
        if result.get("severity") not in SEVERITIES:
            raise ModelJSONError(f"{record_id} has invalid severity.")
        if result.get("confidence") not in CONFIDENCES:
            raise ModelJSONError(f"{record_id} has invalid confidence.")
        if not isinstance(result.get("rationale"), str) or not result["rationale"].strip():
            raise ModelJSONError(f"{record_id} rationale must be non-empty.")
        supported_elements = validate_string_list(result.get("supported_elements"), label=f"{record_id}.supported_elements")
        unsupported_elements = validate_string_list(result.get("unsupported_elements"), label=f"{record_id}.unsupported_elements")
        contradicted_elements = validate_string_list(result.get("contradicted_elements"), label=f"{record_id}.contradicted_elements")
        evidence_ids = validate_string_list(result.get("evidence_chunk_ids_used"), label=f"{record_id}.evidence_chunk_ids_used")
        concept_refs = validate_string_list(result.get("concept_ids"), label=f"{record_id}.concept_ids")
        unknown_concepts = [concept_id for concept_id in concept_refs if concept_id not in concept_lookup]
        if unknown_concepts:
            raise ModelJSONError(f"{record_id} references unknown concept IDs: {unknown_concepts}")
        allowed_evidence = set(record.get("source_chunk_ids") or []) | set(record.get("grounded_in_source_chunk_ids") or [])
        if origin == "insufficient_source_evidence":
            allowed_evidence = allowed_evidence | set(chapter_source_ids)
        invalid_evidence = [node_id for node_id in evidence_ids if node_id not in allowed_evidence]
        if invalid_evidence:
            raise ModelJSONError(f"{record_id} uses invented or disallowed evidence IDs: {invalid_evidence}")
        normalized_evaluations_by_id[record_id] = {
            "record_id": record_id,
            "semantic_support_status": semantic,
            "pedagogical_quality_status": pedagogical,
            "abstention_status": abstention,
            "severity": result["severity"],
            "confidence": result["confidence"],
            "rationale": result["rationale"].strip(),
            "supported_elements": supported_elements,
            "unsupported_elements": unsupported_elements,
            "contradicted_elements": contradicted_elements,
            "evidence_chunk_ids_used": evidence_ids,
            "concept_ids": concept_refs,
        }
    missing = [record_id for record_id in record_ids if record_id not in seen_records]
    extra = [record_id for record_id in seen_records if record_id not in record_lookup]
    if missing or extra:
        raise ModelJSONError(f"V2 evaluation IDs mismatch. Missing={missing}; extra={extra}")

    raw_coverage = require_model_list(data.get("concept_coverage"), "concept_coverage")
    seen_concepts: set[str] = set()
    normalized_coverage_by_id: dict[str, dict[str, Any]] = {}
    for item in raw_coverage:
        coverage = require_model_object(item, "concept coverage")
        concept_id = coverage.get("concept_id")
        if concept_id not in concept_lookup:
            raise ModelJSONError(f"Coverage returned unknown concept_id: {concept_id}")
        if concept_id in seen_concepts:
            raise ModelJSONError(f"Duplicate concept coverage: {concept_id}")
        seen_concepts.add(concept_id)
        concept = concept_lookup[concept_id]
        if coverage.get("importance") != concept["importance"]:
            raise ModelJSONError(f"{concept_id} coverage importance does not match inventory.")
        if coverage.get("source_condition") != concept["source_condition"]:
            raise ModelJSONError(f"{concept_id} coverage source_condition does not match inventory.")
        if coverage.get("v1_coverage_status") not in V1_COVERAGE_STATUSES:
            raise ModelJSONError(f"{concept_id} has invalid v1_coverage_status.")
        if coverage.get("v2_coverage_status") not in V2_COVERAGE_STATUSES:
            raise ModelJSONError(f"{concept_id} has invalid v2_coverage_status.")
        v1_claim_ids = validate_string_list(coverage.get("v1_claim_ids"), label=f"{concept_id}.v1_claim_ids")
        unknown_v1 = [claim_id for claim_id in v1_claim_ids if claim_id not in v1_ids]
        if unknown_v1:
            raise ModelJSONError(f"{concept_id} references unknown v1 claim IDs: {unknown_v1}")
        v1_coverage_status, v1_claim_statuses = deterministic_v1_coverage_status(
            concept=concept,
            v1_claim_ids=v1_claim_ids,
            v1_by_id=v1_by_id,
        )
        v2_record_ids = validate_string_list(coverage.get("v2_record_ids"), label=f"{concept_id}.v2_record_ids")
        unknown_v2 = [record_id for record_id in v2_record_ids if record_id not in record_lookup]
        if unknown_v2:
            raise ModelJSONError(f"{concept_id} references unknown v2 record IDs: {unknown_v2}")
        if not isinstance(coverage.get("rationale"), str) or not coverage["rationale"].strip():
            raise ModelJSONError(f"{concept_id} coverage rationale must be non-empty.")
        normalized_coverage_by_id[concept_id] = {
            "concept_id": concept_id,
            "importance": concept["importance"],
            "source_condition": concept["source_condition"],
            "v1_coverage_status": v1_coverage_status,
            "v1_claim_ids": v1_claim_ids,
            "v1_claim_statuses": v1_claim_statuses,
            "v2_coverage_status": coverage["v2_coverage_status"],
            "v2_record_ids": v2_record_ids,
            "rationale": coverage["rationale"].strip(),
        }
    missing_concepts = [concept_id for concept_id in concept_ids if concept_id not in seen_concepts]
    if missing_concepts:
        raise ModelJSONError(f"Missing concept coverage results: {missing_concepts}")

    expected_probes = probes_for_chapter(chapter_number)
    raw_traces = require_model_list(data.get("known_pattern_traces"), "known_pattern_traces")
    seen_probes: set[str] = set()
    normalized_traces_by_id: dict[str, dict[str, Any]] = {}
    expected_probe_by_id = {probe["probe_id"]: probe for probe in expected_probes}
    for item in raw_traces:
        trace = require_model_object(item, "known pattern trace")
        probe_id = trace.get("probe_id")
        if probe_id not in expected_probe_by_id:
            raise ModelJSONError(f"Unknown known-pattern probe_id for chapter {chapter_number}: {probe_id}")
        if probe_id in seen_probes:
            raise ModelJSONError(f"Duplicate known-pattern probe: {probe_id}")
        seen_probes.add(probe_id)
        probe = expected_probe_by_id[probe_id]
        if trace.get("chapter_number") != chapter_number:
            raise ModelJSONError(f"{probe_id} has wrong chapter_number.")
        if trace.get("source_condition") not in SOURCE_CONDITIONS:
            raise ModelJSONError(f"{probe_id} has invalid source_condition.")
        concept_refs = validate_string_list(trace.get("matching_concept_ids"), label=f"{probe_id}.matching_concept_ids")
        unknown_concepts = [concept_id for concept_id in concept_refs if concept_id not in concept_lookup]
        if unknown_concepts:
            raise ModelJSONError(f"{probe_id} references unknown concepts: {unknown_concepts}")
        trace_warnings: list[dict[str, Any]] = []
        valid_concept_refs: list[str] = []
        for concept_id in concept_refs:
            concept = concept_lookup[concept_id]
            if concept_matches_probe_alias(concept, probe_id):
                valid_concept_refs.append(concept_id)
            else:
                trace_warnings.append(
                    {
                        "code": "KNOWN_PATTERN_CONCEPT_MISMATCH",
                        "probe_id": probe_id,
                        "concept_id": concept_id,
                    }
                )
        if trace.get("v1_claim_id") != probe["v1_claim_id"]:
            raise ModelJSONError(f"{probe_id} has wrong v1_claim_id.")
        expected_v1 = v1_by_id.get(probe["v1_claim_id"])
        if expected_v1 and trace.get("v1_support_status") != expected_v1["support_status"]:
            raise ModelJSONError(f"{probe_id} v1_support_status does not match Step 34B.")
        if trace.get("v1_support_status") not in SUPPORT_STATUSES:
            raise ModelJSONError(f"{probe_id} has invalid v1_support_status.")
        if trace.get("v2_status") not in V2_COVERAGE_STATUSES:
            raise ModelJSONError(f"{probe_id} has invalid v2_status.")
        v2_record_ids = validate_string_list(trace.get("v2_record_ids"), label=f"{probe_id}.v2_record_ids")
        unknown_v2 = [record_id for record_id in v2_record_ids if record_id not in record_lookup]
        if unknown_v2:
            raise ModelJSONError(f"{probe_id} references unknown v2 record IDs: {unknown_v2}")
        if not isinstance(trace.get("conclusion"), str) or not trace["conclusion"].strip():
            raise ModelJSONError(f"{probe_id} conclusion must be non-empty.")
        trace_source_condition = trace["source_condition"]
        if any(
            has_damaged_pronunciation_notation(concept_lookup[concept_id])
            for concept_id in valid_concept_refs
        ):
            if trace_source_condition != "DAMAGED":
                trace_warnings.append(
                    {
                        "code": "PRONUNCIATION_SOURCE_DAMAGED",
                        "probe_id": probe_id,
                        "previous_source_condition": trace_source_condition,
                    }
                )
            trace_source_condition = "DAMAGED"
        normalized_traces_by_id[probe_id] = {
            "probe_id": probe_id,
            "chapter_number": chapter_number,
            "source_condition": trace_source_condition,
            "matching_concept_ids": valid_concept_refs,
            "v1_claim_id": probe["v1_claim_id"],
            "v1_support_status": trace["v1_support_status"],
            "v2_status": trace["v2_status"],
            "v2_record_ids": v2_record_ids,
            "conclusion": trace["conclusion"].strip(),
            "warnings": trace_warnings,
        }
    missing_probes = [probe["probe_id"] for probe in expected_probes if probe["probe_id"] not in seen_probes]
    if missing_probes:
        raise ModelJSONError(f"Missing known-pattern traces: {missing_probes}")

    return {
        "chapter_number": chapter_number,
        "v2_record_evaluations": [
            normalized_evaluations_by_id[record_id] for record_id in record_ids
        ],
        "concept_coverage": [
            normalized_coverage_by_id[concept_id] for concept_id in concept_ids
        ],
        "known_pattern_traces": [
            normalized_traces_by_id[probe["probe_id"]] for probe in expected_probes
        ],
    }


def default_complete(prompt: str, *, model: str, timeout_seconds: int) -> str:
    if not NVIDIA_API_KEY:
        raise ModelCallError("Missing NVIDIA_API_KEY. Create a real .env file from .env.example.")
    from openai import OpenAI

    client = OpenAI(
        api_key=NVIDIA_API_KEY,
        base_url=DEFAULT_NVIDIA_BASE_URL,
        timeout=timeout_seconds,
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    return response.choices[0].message.content or ""


def multiprocessing_context() -> multiprocessing.context.BaseContext:
    if "fork" in multiprocessing.get_all_start_methods():
        return multiprocessing.get_context("fork")
    return multiprocessing.get_context()


def model_call_worker(
    connection: Any,
    prompt: str,
    model: str,
    timeout_seconds: int,
    complete_fn: Callable[[str], str] | None,
) -> None:
    try:
        completer = complete_fn or (
            lambda value: default_complete(
                value,
                model=model,
                timeout_seconds=timeout_seconds,
            )
        )
        connection.send(
            {
                "status": "ok",
                "response": completer(prompt),
            }
        )
    except BaseException as error:  # pragma: no cover - defensive child-process path
        connection.send(
            {
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        connection.close()


def complete_in_child_process(
    prompt: str,
    *,
    model: str,
    timeout_seconds: int,
    complete_fn: Callable[[str], str] | None,
    stage_label: str,
    chapter_number: int,
    call_kind: str,
) -> str:
    context = multiprocessing_context()
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=model_call_worker,
        args=(child_connection, prompt, model, timeout_seconds, complete_fn),
    )
    process.start()
    child_connection.close()
    process.join(timeout_seconds)
    if process.is_alive():
        process.terminate()
        process.join(2)
        if process.is_alive():
            process.kill()
            process.join(2)
        parent_connection.close()
        raise ModelCallTimeoutError(
            f"{stage_label} chapter {chapter_number} {call_kind} model call "
            f"exceeded configured timeout of {timeout_seconds} second(s)."
        )

    try:
        if parent_connection.poll():
            payload = parent_connection.recv()
        else:
            payload = {
                "status": "error",
                "error_type": "ChildProcessError",
                "message": f"model worker exited with code {process.exitcode}",
                "traceback": "",
            }
    finally:
        parent_connection.close()
        process.join()

    if payload.get("status") == "ok":
        return str(payload.get("response") or "")
    raise ModelCallError(
        f"{stage_label} chapter {chapter_number} {call_kind} model call failed in "
        f"child process: {payload.get('error_type')}: {payload.get('message')}"
    )


def complete_with_retries(
    prompt: str,
    *,
    model: str,
    timeout_seconds: int,
    max_retries: int,
    retry_backoff_seconds: float,
    complete_fn: Callable[[str], str] | None,
    stage_label: str,
    chapter_number: int,
    call_kind: str,
) -> str:
    last_error: Exception | None = None
    attempts = max_retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return complete_in_child_process(
                prompt,
                model=model,
                timeout_seconds=timeout_seconds,
                complete_fn=complete_fn,
                stage_label=stage_label,
                chapter_number=chapter_number,
                call_kind=call_kind,
            )
        except ModelCallTimeoutError:
            raise
        except Exception as error:  # pragma: no cover - live model behavior
            last_error = error
            if attempt >= attempts:
                break
            print(
                f"Model call failed; retry {attempt}/{max_retries}: {error}",
                file=sys.stderr,
            )
            if retry_backoff_seconds > 0:
                time.sleep(retry_backoff_seconds)
    raise ModelCallError(f"Model call failed after {attempts} attempt(s): {last_error}") from last_error


def save_raw_response(raw_dir: Path, stage_id: str, kind: str, raw_response: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{stage_id}.{kind}.raw_response.txt"
    atomic_write_text(path, raw_response)
    return path


def build_repair_prompt(
    *,
    stage: str,
    chapter_number: int,
    expected_ids: list[str],
    invalid_response: str,
    validation_error: str,
    extra_context: dict[str, Any] | None = None,
) -> str:
    extra = ""
    if extra_context:
        extra = (
            "\nAdditional context from the original request, for schema repair only:\n"
            + json.dumps(extra_context, indent=2, ensure_ascii=False)
            + "\n"
        )
    return f"""Repair this malformed JSON response for the targeted evaluation pipeline.

Return JSON only. Do not reconsider judgments. Preserve the intended judgments from the invalid response.
Do not add new source evidence. Use only the expected IDs listed here.
The expected IDs list is an allow-list, not a request to add missing placeholder objects.
Do not add placeholder concepts, placeholder records, unknown enum values, or empty evidence just to fill the list.
For source concept repairs, preserve the original concept count and IDs when possible, and fix only JSON/schema issues that can be fixed from the invalid response.

Stage: {stage}
Chapter number: {chapter_number}
Expected IDs:
{json.dumps(expected_ids, indent=2, ensure_ascii=False)}

Validation error:
{validation_error}
{extra}

Invalid response:
{invalid_response}
"""


def call_json_stage_with_repair(
    *,
    stage_id: str,
    stage_label: str,
    chapter_number: int,
    prompt: str,
    expected_ids: list[str],
    validate_fn: Callable[[Any], dict[str, Any]],
    args: argparse.Namespace,
    raw_dir: Path,
    stats: RuntimeStats,
    complete_fn: Callable[[str], str] | None,
    repair_extra_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = complete_with_retries(
        prompt,
        model=args.model,
        timeout_seconds=args.model_timeout_seconds,
        max_retries=args.model_max_retries,
        retry_backoff_seconds=args.model_retry_backoff_seconds,
        complete_fn=complete_fn,
        stage_label=stage_label,
        chapter_number=chapter_number,
        call_kind="initial",
    )
    stats.model_call_count += 1
    try:
        return validate_fn(parse_model_json(raw))
    except (ModelJSONError, TargetedEvaluationError) as error:
        save_raw_response(raw_dir, stage_id, "invalid", raw)
        repair_prompt = build_repair_prompt(
            stage=stage_label,
            chapter_number=chapter_number,
            expected_ids=expected_ids,
            invalid_response=raw,
            validation_error=str(error),
            extra_context=repair_extra_context,
        )
        repaired_raw = complete_with_retries(
            repair_prompt,
            model=args.model,
            timeout_seconds=args.model_timeout_seconds,
            max_retries=args.model_max_retries,
            retry_backoff_seconds=args.model_retry_backoff_seconds,
            complete_fn=complete_fn,
            stage_label=stage_label,
            chapter_number=chapter_number,
            call_kind="repair",
        )
        stats.model_call_count += 1
        stats.repair_call_count += 1
        try:
            return validate_fn(parse_model_json(repaired_raw))
        except (ModelJSONError, TargetedEvaluationError) as repair_error:
            save_raw_response(raw_dir, stage_id, "repair_invalid", repaired_raw)
            raise ModelJSONError(
                f"{stage_label} chapter {chapter_number} failed validation after repair: {repair_error}"
            ) from repair_error


def initial_checkpoint(
    *,
    bundle: InputBundle,
    model: str,
) -> dict[str, Any]:
    planned_calls = len(bundle.selected_chapter_numbers)
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "status": "IN_PROGRESS",
        "input_hashes": bundle.input_hashes,
        "model": model,
        "source_concept_prompt_version": TARGETED_SOURCE_CONCEPT_PROMPT_VERSION,
        "comparison_prompt_version": TARGETED_V2_COMPARISON_PROMPT_VERSION,
        "selected_chapter_numbers": bundle.selected_chapter_numbers[:],
        "planned_source_concept_calls": planned_calls,
        "planned_chapter_evaluation_calls": planned_calls,
        "completed_source_concept_chapters": [],
        "completed_evaluation_chapters": [],
        "source_concepts_by_chapter": {},
        "evaluations_by_chapter": {},
        "model_call_count": 0,
        "repair_call_count": 0,
        "errors": [],
    }


def validate_resume_checkpoint(
    checkpoint: dict[str, Any],
    *,
    bundle: InputBundle,
    model: str,
) -> None:
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise TargetedEvaluationError("Incompatible checkpoint schema_version.")
    if checkpoint.get("input_hashes") != bundle.input_hashes:
        raise TargetedEvaluationError("Incompatible checkpoint: input hashes changed.")
    if checkpoint.get("model") != model:
        raise TargetedEvaluationError("Incompatible checkpoint: model changed.")
    if checkpoint.get("source_concept_prompt_version") != TARGETED_SOURCE_CONCEPT_PROMPT_VERSION:
        raise TargetedEvaluationError("Incompatible checkpoint: source prompt version changed.")
    if checkpoint.get("comparison_prompt_version") != TARGETED_V2_COMPARISON_PROMPT_VERSION:
        raise TargetedEvaluationError("Incompatible checkpoint: comparison prompt version changed.")
    selected_chapter_numbers = bundle.selected_chapter_numbers
    if checkpoint.get("selected_chapter_numbers") != selected_chapter_numbers:
        raise TargetedEvaluationError("Incompatible checkpoint: selected chapter order changed.")
    for key in ("completed_source_concept_chapters", "completed_evaluation_chapters"):
        completed = checkpoint.get(key)
        if not isinstance(completed, list):
            raise TargetedEvaluationError(f"Incompatible checkpoint: {key} must be an array.")
        selected_set = set(selected_chapter_numbers)
        if any(number not in selected_set for number in completed):
            raise TargetedEvaluationError(f"Incompatible checkpoint: {key} contains unknown chapters.")
        positions = {number: index for index, number in enumerate(selected_chapter_numbers)}
        if completed != sorted(completed, key=lambda number: positions[number]):
            raise TargetedEvaluationError(f"Incompatible checkpoint: {key} order changed.")


def write_checkpoint(path: Path, checkpoint: dict[str, Any], stats: RuntimeStats) -> None:
    checkpoint["model_call_count"] = stats.model_call_count
    checkpoint["repair_call_count"] = stats.repair_call_count
    atomic_write_json(path, checkpoint)


def append_checkpoint_error(
    *,
    checkpoint: dict[str, Any],
    checkpoint_path: Path,
    stats: RuntimeStats,
    stage_label: str,
    chapter_number: int,
    error: Exception,
) -> None:
    errors = list(checkpoint.get("errors") or [])
    errors.append(
        {
            "stage": stage_label,
            "chapter_number": chapter_number,
            "error_type": type(error).__name__,
            "message": str(error),
        }
    )
    checkpoint["errors"] = errors
    checkpoint["status"] = "IN_PROGRESS"
    write_checkpoint(checkpoint_path, checkpoint, stats)


def resume_command(args: argparse.Namespace, *, force_resume: bool = True) -> str:
    parts = [
        "python evaluate_targeted_book_learning_materials.py",
        f"--v1-book-file {args.v1_book_file!r}",
        f"--v1-audit-file {args.v1_audit_file!r}",
        f"--v2-book-file {args.v2_book_file!r}",
        f"--v2-contract-audit-file {args.v2_contract_audit_file!r}",
        f"--clean-chunks-file {args.clean_chunks_file!r}",
        f"--output {args.output!r}",
    ]
    if args.report:
        parts.append(f"--report {args.report!r}")
    checkpoint = args.checkpoint or str(default_checkpoint_path(Path(args.output)))
    parts.extend(
        [
            f"--checkpoint {checkpoint!r}",
            f"--model {args.model!r}",
            f"--model-timeout-seconds {args.model_timeout_seconds}",
            f"--model-max-retries {args.model_max_retries}",
            f"--model-retry-backoff-seconds {args.model_retry_backoff_seconds}",
        ]
    )
    max_new_evaluation_chapters = getattr(args, "max_new_evaluation_chapters", None)
    if max_new_evaluation_chapters is not None:
        parts.append(f"--max-new-evaluation-chapters {max_new_evaluation_chapters}")
    evaluation_chapter_number = getattr(args, "evaluation_chapter_number", None)
    if evaluation_chapter_number is not None:
        parts.append(f"--evaluation-chapter-number {evaluation_chapter_number}")
    if getattr(args, "reevaluate_selected_chapter", False):
        parts.append("--reevaluate-selected-chapter")
    if force_resume:
        parts.append("--resume")
    return " ".join(parts)


def format_chapter_list(chapters: list[int]) -> str:
    return ", ".join(str(number) for number in chapters) if chapters else "none"


def print_limited_run_stop(
    *,
    args: argparse.Namespace,
    checkpoint: dict[str, Any],
    newly_completed_evaluation_chapters: list[int],
) -> None:
    completed_evaluations = list(checkpoint.get("completed_evaluation_chapters") or [])
    selected_chapter_numbers = list(checkpoint.get("selected_chapter_numbers") or [])
    remaining = [
        number
        for number in selected_chapter_numbers
        if number not in completed_evaluations
    ]
    print(
        "Completed source-concept chapters reused: "
        + format_chapter_list(list(checkpoint.get("completed_source_concept_chapters") or []))
    )
    print(f"New chapter-evaluation limit: {getattr(args, 'max_new_evaluation_chapters', None)}")
    print(
        "Chapter evaluated this run: "
        + format_chapter_list(newly_completed_evaluation_chapters)
    )
    print("Completed evaluation chapters: " + format_chapter_list(completed_evaluations))
    print("Remaining evaluation chapters: " + format_chapter_list(remaining))
    print(f"Checkpoint status: {checkpoint.get('status')}")
    print("Execution stopped after configured chapter limit.")
    print("Final evaluation not written.")
    print("Resume command:")
    print(resume_command(args))


def print_exact_chapter_stop(
    *,
    args: argparse.Namespace,
    checkpoint: dict[str, Any],
    chapter_number: int,
    newly_completed_evaluation_chapters: list[int],
    already_complete: bool = False,
) -> None:
    completed_evaluations = list(checkpoint.get("completed_evaluation_chapters") or [])
    selected_chapter_numbers = list(checkpoint.get("selected_chapter_numbers") or [])
    remaining = [
        number
        for number in selected_chapter_numbers
        if number not in completed_evaluations
    ]
    print(f"Requested evaluation chapter: {chapter_number}")
    if already_complete:
        print(f"Chapter {chapter_number} is already complete.")
    print(
        "Chapter evaluated this run: "
        + format_chapter_list(newly_completed_evaluation_chapters)
    )
    print("Completed evaluation chapters: " + format_chapter_list(completed_evaluations))
    print("Remaining evaluation chapters: " + format_chapter_list(remaining))
    print(f"Checkpoint status: {checkpoint.get('status')}")
    print("Execution stopped after exact chapter selection.")
    print("Final evaluation not written.")
    print("Resume command:")
    print(resume_command(args))


def output_paths(args: argparse.Namespace) -> tuple[Path, Path | None, Path]:
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else None
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else default_checkpoint_path(output_path)
    return output_path, report_path, checkpoint_path


def selected_chapter_numbers_for_run(
    *,
    args: argparse.Namespace,
    checkpoint_path: Path,
) -> list[int]:
    evaluation_chapter_number = getattr(args, "evaluation_chapter_number", None)
    if (
        evaluation_chapter_number is not None
        and evaluation_chapter_number not in SELECTED_CHAPTER_NUMBERS
    ):
        raise TargetedEvaluationError(
            f"--evaluation-chapter-number must be one of: {SELECTED_CHAPTER_NUMBERS}."
        )
    if args.resume and checkpoint_path.exists():
        checkpoint = require_object(load_json(checkpoint_path, "Checkpoint"), "Checkpoint")
        selected = checkpoint.get("selected_chapter_numbers")
        if not isinstance(selected, list) or not all(isinstance(number, int) for number in selected):
            raise TargetedEvaluationError(
                "Incompatible checkpoint: selected_chapter_numbers must be an integer array."
            )
        if evaluation_chapter_number is not None and evaluation_chapter_number not in selected:
            raise TargetedEvaluationError(
                f"--evaluation-chapter-number {evaluation_chapter_number} is not in checkpoint selected_chapter_numbers."
            )
        return selected[:]
    if evaluation_chapter_number is not None:
        return [evaluation_chapter_number]
    return SELECTED_CHAPTER_NUMBERS[:]


def enforce_overwrite_rules(
    *,
    output_path: Path,
    report_path: Path | None,
    checkpoint_path: Path,
    raw_dir: Path,
    overwrite: bool,
    resume: bool,
) -> None:
    if resume:
        return
    existing = [path for path in [output_path, report_path, checkpoint_path] if path and path.exists()]
    if raw_dir.exists():
        existing.append(raw_dir)
    if existing and not overwrite:
        raise TargetedEvaluationError(
            "Step 34C.3 output already exists. Use --overwrite or --resume. Existing: "
            + ", ".join(str(path) for path in existing)
        )
    if overwrite:
        for path in [output_path, report_path, checkpoint_path]:
            if path and path.exists():
                path.unlink()
        if raw_dir.exists():
            shutil.rmtree(raw_dir)


def chapter_v1_baseline(v1_results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["support_status"] for item in v1_results)
    high_unsafe = sum(
        1
        for item in v1_results
        if item["support_status"] in UNSAFE_SOURCE_STATUSES and item.get("severity") == "HIGH"
    )
    return {
        "claim_count": len(v1_results),
        "supported_count": counts["SUPPORTED"],
        "partially_supported_count": counts["PARTIALLY_SUPPORTED"],
        "unsupported_count": counts["UNSUPPORTED"],
        "contradicted_count": counts["CONTRADICTED"],
        "source_damaged_count": counts["SOURCE_DAMAGED"],
        "not_factual_count": counts["NOT_A_FACTUAL_CLAIM"],
        "high_severity_unsafe_count": high_unsafe,
        "results_by_status": dict(sorted(counts.items())),
    }


def summarize_v2_for_chapter(
    records: list[dict[str, Any]],
    evaluations: list[dict[str, Any]],
) -> dict[str, Any]:
    by_record = {item["record_id"]: item for item in records}
    semantic = Counter()
    pedagogical = Counter()
    abstention = Counter()
    high_unsafe = 0
    for result in evaluations:
        record = by_record[result["record_id"]]
        if record["origin"] == "source_grounded":
            semantic[result["semantic_support_status"]] += 1
            if (
                result["semantic_support_status"] in UNSAFE_SOURCE_STATUSES
                and result["severity"] == "HIGH"
            ):
                high_unsafe += 1
        elif record["origin"] == "pedagogical_generation":
            pedagogical[result["pedagogical_quality_status"]] += 1
        elif record["origin"] == "insufficient_source_evidence":
            abstention[result["abstention_status"]] += 1
    return {
        "record_count": len(records),
        "source_grounded_results": dict(sorted(semantic.items())),
        "pedagogical_quality_results": dict(sorted(pedagogical.items())),
        "abstention_results": dict(sorted(abstention.items())),
        "high_severity_unsafe_count": high_unsafe,
    }


def summarize_coverage(coverage: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(item["v2_coverage_status"] for item in coverage)
    by_importance = Counter(item["importance"] for item in coverage)
    return {
        "concept_count": len(coverage),
        "concepts_by_importance": dict(sorted(by_importance.items())),
        "coverage_results": dict(sorted(counts.items())),
        "high_importance_silently_omitted_count": sum(
            1
            for item in coverage
            if item["importance"] == "HIGH" and item["v2_coverage_status"] == "SILENTLY_OMITTED"
        ),
        "high_importance_covered_unsafely_count": sum(
            1
            for item in coverage
            if item["importance"] == "HIGH" and item["v2_coverage_status"] == "COVERED_UNSAFELY"
        ),
        "medium_importance_silently_omitted_count": sum(
            1
            for item in coverage
            if item["importance"] == "MEDIUM" and item["v2_coverage_status"] == "SILENTLY_OMITTED"
        ),
    }


def count_or_zero(counter: Counter[str], key: str) -> int:
    return int(counter.get(key, 0))


def build_summary(
    *,
    bundle: InputBundle,
    source_concepts_by_chapter: dict[int, dict[str, Any]],
    evaluations_by_chapter: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    selected_chapter_numbers = bundle.selected_chapter_numbers
    selected_v1_results = [
        result
        for number in selected_chapter_numbers
        for result in bundle.v1_results_by_chapter[number]
    ]
    v1_status = Counter(item["support_status"] for item in selected_v1_results)
    v1_high_unsafe = sum(
        1
        for item in selected_v1_results
        if item["support_status"] in UNSAFE_SOURCE_STATUSES and item.get("severity") == "HIGH"
    )
    records_by_origin = Counter(record["origin"] for record in bundle.v2_records)
    records_by_kind = Counter(record["claim_kind"] for record in bundle.v2_records)
    records_by_derivation = Counter(record["text_derivation"] for record in bundle.v2_records)
    record_lookup = {record["record_id"]: record for record in bundle.v2_records}

    source_grounded_status = Counter()
    pedagogical_status = Counter()
    abstention_status = Counter()
    v2_high_unsafe = 0
    concepts_by_importance = Counter()
    coverage_status = Counter()
    concept_count = 0
    high_silent = 0
    high_unsafe_concept = 0
    medium_silent = 0
    for number in selected_chapter_numbers:
        evaluation = evaluations_by_chapter[number]
        for result in evaluation["v2_record_evaluations"]:
            record = record_lookup[result["record_id"]]
            if record["origin"] == "source_grounded":
                source_grounded_status[result["semantic_support_status"]] += 1
                if (
                    result["semantic_support_status"] in UNSAFE_SOURCE_STATUSES
                    and result["severity"] == "HIGH"
                ):
                    v2_high_unsafe += 1
            elif record["origin"] == "pedagogical_generation":
                pedagogical_status[result["pedagogical_quality_status"]] += 1
            else:
                abstention_status[result["abstention_status"]] += 1
        for coverage in evaluation["concept_coverage"]:
            concept_count += 1
            concepts_by_importance[coverage["importance"]] += 1
            coverage_status[coverage["v2_coverage_status"]] += 1
            if coverage["importance"] == "HIGH" and coverage["v2_coverage_status"] == "SILENTLY_OMITTED":
                high_silent += 1
            if coverage["importance"] == "HIGH" and coverage["v2_coverage_status"] == "COVERED_UNSAFELY":
                high_unsafe_concept += 1
            if coverage["importance"] == "MEDIUM" and coverage["v2_coverage_status"] == "SILENTLY_OMITTED":
                medium_silent += 1

    return {
        "v1_claim_count": len(selected_v1_results),
        "v1_supported_count": count_or_zero(v1_status, "SUPPORTED"),
        "v1_partially_supported_count": count_or_zero(v1_status, "PARTIALLY_SUPPORTED"),
        "v1_unsupported_count": count_or_zero(v1_status, "UNSUPPORTED"),
        "v1_contradicted_count": count_or_zero(v1_status, "CONTRADICTED"),
        "v1_source_damaged_count": count_or_zero(v1_status, "SOURCE_DAMAGED"),
        "v1_not_factual_count": count_or_zero(v1_status, "NOT_A_FACTUAL_CLAIM"),
        "v1_results_by_status": dict(sorted(v1_status.items())),
        "v1_high_severity_unsafe_count": v1_high_unsafe,
        "v2_record_count": len(bundle.v2_records),
        "v2_source_grounded_count": records_by_origin["source_grounded"],
        "v2_pedagogical_generation_count": records_by_origin["pedagogical_generation"],
        "v2_insufficient_source_evidence_count": records_by_origin["insufficient_source_evidence"],
        "v2_records_by_claim_kind": dict(sorted(records_by_kind.items())),
        "v2_records_by_origin": dict(sorted(records_by_origin.items())),
        "v2_records_by_text_derivation": dict(sorted(records_by_derivation.items())),
        "v2_source_grounded_results": dict(sorted(source_grounded_status.items())),
        "v2_source_grounded_supported_count": source_grounded_status["SUPPORTED"],
        "v2_source_grounded_partially_supported_count": source_grounded_status["PARTIALLY_SUPPORTED"],
        "v2_source_grounded_unsupported_count": source_grounded_status["UNSUPPORTED"],
        "v2_source_grounded_contradicted_count": source_grounded_status["CONTRADICTED"],
        "v2_source_grounded_source_damaged_count": source_grounded_status["SOURCE_DAMAGED"],
        "v2_high_severity_unsafe_count": v2_high_unsafe,
        "pedagogical_quality_results": dict(sorted(pedagogical_status.items())),
        "pedagogical_usable_count": pedagogical_status["USABLE"],
        "pedagogical_needs_revision_count": pedagogical_status["NEEDS_REVISION"],
        "pedagogical_misleading_count": pedagogical_status["MISLEADING"],
        "abstention_results": dict(sorted(abstention_status.items())),
        "abstention_justified_count": abstention_status["JUSTIFIED"],
        "abstention_overcautious_count": abstention_status["OVERCAUTIOUS"],
        "abstention_misaligned_count": abstention_status["MISALIGNED"],
        "concept_count": concept_count,
        "high_importance_concept_count": concepts_by_importance["HIGH"],
        "medium_importance_concept_count": concepts_by_importance["MEDIUM"],
        "low_importance_concept_count": concepts_by_importance["LOW"],
        "concepts_by_importance": dict(sorted(concepts_by_importance.items())),
        "v2_concept_coverage_results": dict(sorted(coverage_status.items())),
        "v2_covered_safely_count": coverage_status["COVERED_SAFELY"],
        "v2_partially_covered_count": coverage_status["PARTIALLY_COVERED"],
        "v2_safely_withheld_count": coverage_status["SAFELY_WITHHELD"],
        "v2_silently_omitted_count": coverage_status["SILENTLY_OMITTED"],
        "v2_covered_unsafely_count": coverage_status["COVERED_UNSAFELY"],
        "high_importance_silently_omitted_count": high_silent,
        "high_importance_covered_unsafely_count": high_unsafe_concept,
        "medium_importance_silently_omitted_count": medium_silent,
    }


def safety_verdict(summary: dict[str, Any], evaluations_by_chapter: dict[int, dict[str, Any]]) -> str:
    if summary["v2_high_severity_unsafe_count"] > 0:
        return "FAIL"
    if summary["pedagogical_misleading_count"] > 0:
        return "FAIL"
    if summary["high_importance_covered_unsafely_count"] > 0:
        return "FAIL"
    has_medium_low_unsafe = False
    for evaluation in evaluations_by_chapter.values():
        for result in evaluation["v2_record_evaluations"]:
            if (
                result["semantic_support_status"] in UNSAFE_SOURCE_STATUSES
                and result["severity"] in {"MEDIUM", "LOW"}
            ):
                has_medium_low_unsafe = True
    if (
        has_medium_low_unsafe
        or summary["pedagogical_needs_revision_count"] > 0
        or summary["abstention_overcautious_count"] > 0
        or summary["abstention_misaligned_count"] > 0
    ):
        return "PASS_WITH_WARNINGS"
    return "PASS"


def coverage_verdict(summary: dict[str, Any]) -> str:
    if (
        summary["high_importance_silently_omitted_count"] > 0
        or summary["high_importance_covered_unsafely_count"] > 0
    ):
        return "FAIL"
    if (
        summary["v2_partially_covered_count"] > 0
        or summary["medium_importance_silently_omitted_count"] > 0
        or summary["v2_safely_withheld_count"] > 0
    ):
        return "PASS_WITH_WARNINGS"
    return "PASS"


def comparison_verdict(summary: dict[str, Any], safety: str, coverage: str) -> str:
    improved_high_risk = (
        summary["v2_high_severity_unsafe_count"]
        < summary["v1_high_severity_unsafe_count"]
    )
    if safety == "PASS" and coverage == "PASS" and improved_high_risk:
        return "IMPROVED"
    if safety in {"PASS", "PASS_WITH_WARNINGS"} and coverage == "PASS_WITH_WARNINGS" and improved_high_risk:
        return "IMPROVED_WITH_COVERAGE_WARNINGS"
    return "NOT_IMPROVED"


def build_known_pattern_traces(evaluations_by_chapter: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    selected = set(evaluations_by_chapter)
    traces_by_id = {
        trace["probe_id"]: trace
        for number in selected
        for trace in evaluations_by_chapter[number]["known_pattern_traces"]
    }
    return [
        traces_by_id[probe["probe_id"]]
        for probe in KNOWN_PATTERN_PROBES
        if probe["chapter_number"] in selected
    ]


def build_priority_findings(
    *,
    evaluations_by_chapter: dict[int, dict[str, Any]],
    v2_records_by_chapter: dict[int, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for number in sorted(evaluations_by_chapter):
        record_lookup = {record["record_id"]: record for record in v2_records_by_chapter[number]}
        record_order = {record["record_id"]: index for index, record in enumerate(v2_records_by_chapter[number])}
        evaluation = evaluations_by_chapter[number]
        for result in evaluation["v2_record_evaluations"]:
            record = record_lookup[result["record_id"]]
            if (
                record["origin"] == "source_grounded"
                and result["severity"] == "HIGH"
                and result["semantic_support_status"] in UNSAFE_SOURCE_STATUSES
            ):
                findings.append(
                    {
                        "chapter_number": number,
                        "category": "HIGH_SEVERITY_UNSAFE_SOURCE_GROUNDED",
                        "record_id": result["record_id"],
                        "status": result["semantic_support_status"],
                        "rationale": result["rationale"],
                        "sort_index": record_order[result["record_id"]],
                    }
                )
            if record["origin"] == "pedagogical_generation" and result["pedagogical_quality_status"] == "MISLEADING":
                findings.append(
                    {
                        "chapter_number": number,
                        "category": "MISLEADING_PEDAGOGICAL_RECORD",
                        "record_id": result["record_id"],
                        "status": "MISLEADING",
                        "rationale": result["rationale"],
                        "sort_index": record_order[result["record_id"]],
                    }
                )
        for index, coverage in enumerate(evaluation["concept_coverage"]):
            if coverage["importance"] == "HIGH" and coverage["v2_coverage_status"] in {
                "SILENTLY_OMITTED",
                "COVERED_UNSAFELY",
            }:
                findings.append(
                    {
                        "chapter_number": number,
                        "category": f"HIGH_IMPORTANCE_{coverage['v2_coverage_status']}",
                        "concept_id": coverage["concept_id"],
                        "status": coverage["v2_coverage_status"],
                        "rationale": coverage["rationale"],
                        "sort_index": index,
                    }
                )
        for trace in evaluation["known_pattern_traces"]:
            if trace["v2_status"] in {"SILENTLY_OMITTED", "COVERED_UNSAFELY"}:
                findings.append(
                    {
                        "chapter_number": number,
                        "category": "KNOWN_PATTERN_TRACE_REMAINS_UNSAFE_OR_OMITTED",
                        "probe_id": trace["probe_id"],
                        "status": trace["v2_status"],
                        "rationale": trace["conclusion"],
                        "sort_index": 1000,
                    }
                )
    return sorted(
        findings,
        key=lambda item: (
            item["chapter_number"],
            item["category"],
            item.get("sort_index", 0),
            item.get("record_id") or item.get("concept_id") or item.get("probe_id") or "",
        ),
    )


def build_final_output(
    *,
    args: argparse.Namespace,
    bundle: InputBundle,
    checkpoint: dict[str, Any],
    output_path: Path,
    report_path: Path | None,
) -> dict[str, Any]:
    source_concepts_by_chapter = {
        int(number): value
        for number, value in checkpoint["source_concepts_by_chapter"].items()
    }
    evaluations_by_chapter = {
        int(number): value
        for number, value in checkpoint["evaluations_by_chapter"].items()
    }
    summary = build_summary(
        bundle=bundle,
        source_concepts_by_chapter=source_concepts_by_chapter,
        evaluations_by_chapter=evaluations_by_chapter,
    )
    safety = safety_verdict(summary, evaluations_by_chapter)
    coverage = coverage_verdict(summary)
    comparison = comparison_verdict(summary, safety, coverage)
    chapters: list[dict[str, Any]] = []
    for number in bundle.selected_chapter_numbers:
        chapter_records = bundle.v2_records_by_chapter[number]
        evaluation = evaluations_by_chapter[number]
        chapter = {
            "chapter_number": number,
            "chapter_title": chapter_title_from_v2(bundle, number),
            "source_concepts": source_concepts_by_chapter[number]["concepts"],
            "v1_baseline": chapter_v1_baseline(bundle.v1_results_by_chapter[number]),
            "v2_records": [
                {
                    "record_id": record["record_id"],
                    "json_path": record["json_path"],
                    "field_role": record["field_role"],
                    "claim_kind": record["claim_kind"],
                    "origin": record["origin"],
                    "text_derivation": record["text_derivation"],
                    "source_chunk_ids": record["source_chunk_ids"],
                    "grounded_in_source_chunk_ids": record["grounded_in_source_chunk_ids"],
                    "reason": record["reason"],
                    "text_preview": text_preview(record["text"] or record["reason"] or ""),
                }
                for record in chapter_records
            ],
            "v2_record_evaluations": evaluation["v2_record_evaluations"],
            "concept_coverage": evaluation["concept_coverage"],
            "known_pattern_traces": evaluation["known_pattern_traces"],
            "v2_summary": summarize_v2_for_chapter(
                chapter_records,
                evaluation["v2_record_evaluations"],
            ),
            "coverage_summary": summarize_coverage(evaluation["concept_coverage"]),
        }
        chapter["chapter_safety_summary"] = {
            "high_severity_unsafe_count": chapter["v2_summary"]["high_severity_unsafe_count"],
            "misleading_pedagogical_count": chapter["v2_summary"]["pedagogical_quality_results"].get("MISLEADING", 0),
        }
        chapters.append(chapter)
    known_pattern_traces = build_known_pattern_traces(evaluations_by_chapter)
    priority_findings = build_priority_findings(
        evaluations_by_chapter=evaluations_by_chapter,
        v2_records_by_chapter=bundle.v2_records_by_chapter,
    )
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "run_status": "COMPLETE",
        "safety_verdict": safety,
        "coverage_verdict": coverage,
        "comparison_verdict": comparison,
        "input": {
            "v1_book_file": str(args.v1_book_file),
            "v1_audit_file": str(args.v1_audit_file),
            "v2_book_file": str(args.v2_book_file),
            "v2_contract_audit_file": str(args.v2_contract_audit_file),
            "clean_chunks_file": str(args.clean_chunks_file),
            "input_hashes": bundle.input_hashes,
            "selected_chapter_numbers": bundle.selected_chapter_numbers,
        },
        "generation": {
            "model": args.model,
            "source_concept_prompt_version": TARGETED_SOURCE_CONCEPT_PROMPT_VERSION,
            "comparison_prompt_version": TARGETED_V2_COMPARISON_PROMPT_VERSION,
            "planned_source_concept_calls": len(bundle.selected_chapter_numbers),
            "completed_source_concept_calls": len(checkpoint["completed_source_concept_chapters"]),
            "planned_chapter_evaluation_calls": len(bundle.selected_chapter_numbers),
            "completed_chapter_evaluation_calls": len(checkpoint["completed_evaluation_chapters"]),
            "model_call_count": checkpoint["model_call_count"],
            "repair_call_count": checkpoint["repair_call_count"],
        },
        "summary": summary,
        "chapters": chapters,
        "known_pattern_traces": known_pattern_traces,
        "priority_findings": priority_findings,
        "warnings": [],
        "errors": [],
    }


def format_text_report(result: dict[str, Any], *, output_path: Path, checkpoint_path: Path) -> str:
    summary = result["summary"]
    generation = result["generation"]
    input_info = result["input"]
    lines = [
        "TARGETED V2 LEARNING-MATERIALS EVALUATION",
        "",
        "INPUT",
        f"V1 book: {input_info['v1_book_file']}",
        f"V1 audit: {input_info['v1_audit_file']}",
        f"V2 book: {input_info['v2_book_file']}",
        f"V2 contract audit: {input_info['v2_contract_audit_file']}",
        f"Clean chunks: {input_info['clean_chunks_file']}",
        f"Model: {generation['model']}",
        f"Selected chapters: {', '.join(map(str, input_info['selected_chapter_numbers']))}",
        "",
        "EXECUTION",
        f"Run status: {result['run_status']}",
        f"Source-concept calls: {generation['completed_source_concept_calls']}/{generation['planned_source_concept_calls']}",
        f"Chapter-evaluation calls: {generation['completed_chapter_evaluation_calls']}/{generation['planned_chapter_evaluation_calls']}",
        f"Model calls: {generation['model_call_count']}",
        f"Repair calls: {generation['repair_call_count']}",
        f"Checkpoint: {checkpoint_path}",
        "",
        "VERDICTS",
        f"Safety: {result['safety_verdict']}",
        f"Coverage: {result['coverage_verdict']}",
        f"Comparison: {result['comparison_verdict']}",
        "",
        "V1 BASELINE",
        f"Claims: {summary['v1_claim_count']}",
        f"Supported: {summary['v1_supported_count']}",
        f"Partially supported: {summary['v1_partially_supported_count']}",
        f"Unsupported: {summary['v1_unsupported_count']}",
        f"Contradicted: {summary['v1_contradicted_count']}",
        f"Source damaged: {summary['v1_source_damaged_count']}",
        f"Not factual: {summary['v1_not_factual_count']}",
        f"High-severity unsafe: {summary['v1_high_severity_unsafe_count']}",
        "",
        "V2 SEMANTIC SAFETY",
        f"Records: {summary['v2_record_count']}",
        f"Source grounded: {summary['v2_source_grounded_count']}",
        f"Supported: {summary['v2_source_grounded_supported_count']}",
        f"Partially supported: {summary['v2_source_grounded_partially_supported_count']}",
        f"Unsupported: {summary['v2_source_grounded_unsupported_count']}",
        f"Contradicted: {summary['v2_source_grounded_contradicted_count']}",
        f"Source damaged: {summary['v2_source_grounded_source_damaged_count']}",
        f"High-severity unsafe: {summary['v2_high_severity_unsafe_count']}",
        "",
        "V2 PEDAGOGICAL QUALITY",
        f"Usable: {summary['pedagogical_usable_count']}",
        f"Needs revision: {summary['pedagogical_needs_revision_count']}",
        f"Misleading: {summary['pedagogical_misleading_count']}",
        "",
        "V2 ABSTENTIONS",
        f"Justified: {summary['abstention_justified_count']}",
        f"Overcautious: {summary['abstention_overcautious_count']}",
        f"Misaligned: {summary['abstention_misaligned_count']}",
        "",
        "CONTENT RETENTION",
        f"Source concepts: {summary['concept_count']}",
        f"High: {summary['high_importance_concept_count']}",
        f"Medium: {summary['medium_importance_concept_count']}",
        f"Low: {summary['low_importance_concept_count']}",
        f"Covered safely: {summary['v2_covered_safely_count']}",
        f"Partially covered: {summary['v2_partially_covered_count']}",
        f"Safely withheld: {summary['v2_safely_withheld_count']}",
        f"Silently omitted: {summary['v2_silently_omitted_count']}",
        f"Covered unsafely: {summary['v2_covered_unsafely_count']}",
        "",
        "KNOWN PATTERN TRACES",
    ]
    trace_labels = {probe["probe_id"]: probe["label"] for probe in KNOWN_PATTERN_PROBES}
    for trace in result["known_pattern_traces"]:
        lines.append(
            f"{trace_labels.get(trace['probe_id'], trace['probe_id'])}: "
            f"{trace['v2_status']} | {trace['source_condition']} | {trace['conclusion']}"
        )
    lines.extend(["", "CHAPTER RESULTS"])
    for chapter in result["chapters"]:
        lines.extend(
            [
                "",
                f"Chapter {chapter['chapter_number']}: {chapter['chapter_title']}",
                f"Source concepts: {len(chapter['source_concepts'])}",
                f"V1 baseline: {chapter['v1_baseline']}",
                f"V2 summary: {chapter['v2_summary']}",
                f"Coverage summary: {chapter['coverage_summary']}",
            ]
        )
    lines.extend(["", "PRIORITY FINDINGS"])
    if result["priority_findings"]:
        for finding in result["priority_findings"]:
            label = finding.get("record_id") or finding.get("concept_id") or finding.get("probe_id")
            lines.append(
                f"Chapter {finding['chapter_number']} | {finding['category']} | "
                f"{label} | {finding['status']} | {finding['rationale']}"
            )
    else:
        lines.append("None")
    lines.extend(["", "WARNINGS"])
    lines.extend(result["warnings"] or ["None"])
    lines.extend(["", "ERRORS"])
    lines.extend(result["errors"] or ["None"])
    lines.extend(["", "OUTPUT", f"JSON: {output_path}", f"Checkpoint: {checkpoint_path}"])
    return "\n".join(lines) + "\n"


def print_dry_run(
    *,
    output_path: Path,
    report_path: Path | None,
    checkpoint_path: Path,
    bundle: InputBundle,
) -> None:
    planned_source_calls = len(bundle.selected_chapter_numbers)
    planned_evaluation_calls = len(bundle.selected_chapter_numbers)
    print("Targeted v2 evaluation dry run.")
    print(f"Selected chapters: {', '.join(map(str, bundle.selected_chapter_numbers))}")
    print(f"V1 filtered claims: {sum(len(bundle.v1_results_by_chapter[number]) for number in bundle.selected_chapter_numbers)}")
    print(f"V2 grounded-content records: {len(bundle.v2_records)}")
    print(f"Planned source-concept calls: {planned_source_calls}")
    print(f"Planned chapter-evaluation calls: {planned_evaluation_calls}")
    print(f"Planned normal model calls: {planned_source_calls + planned_evaluation_calls}")
    print("Model calls made: 0")
    print(f"Output path: {output_path}")
    if report_path:
        print(f"Report path: {report_path}")
    print(f"Checkpoint path: {checkpoint_path}")
    print("Dry run complete: no files written")


def evaluate_targeted_book_learning_materials(
    args: argparse.Namespace,
    *,
    complete_fn: Callable[[str], str] | None = None,
    expected_v1_result_count: int | None = EXPECTED_LIVE_V1_RESULT_COUNT,
) -> dict[str, Any] | None:
    if args.model_timeout_seconds < 1:
        raise TargetedEvaluationError("--model-timeout-seconds must be at least 1.")
    if args.model_max_retries < 0:
        raise TargetedEvaluationError("--model-max-retries must be 0 or greater.")
    if args.model_retry_backoff_seconds < 0:
        raise TargetedEvaluationError("--model-retry-backoff-seconds must be 0 or greater.")
    max_new_evaluation_chapters = getattr(args, "max_new_evaluation_chapters", None)
    if max_new_evaluation_chapters is not None and max_new_evaluation_chapters <= 0:
        raise TargetedEvaluationError("--max-new-evaluation-chapters must be a positive integer.")
    evaluation_chapter_number = getattr(args, "evaluation_chapter_number", None)
    reevaluate_selected_chapter = bool(getattr(args, "reevaluate_selected_chapter", False))
    if reevaluate_selected_chapter and not args.resume:
        raise TargetedEvaluationError("--reevaluate-selected-chapter requires --resume.")
    if reevaluate_selected_chapter and evaluation_chapter_number is None:
        raise TargetedEvaluationError(
            "--reevaluate-selected-chapter requires --evaluation-chapter-number."
        )

    output_path, report_path, checkpoint_path = output_paths(args)
    raw_dir = raw_dir_for_output(output_path)
    selected_chapter_numbers = selected_chapter_numbers_for_run(
        args=args,
        checkpoint_path=checkpoint_path,
    )
    bundle = load_and_validate_inputs(
        v1_book_file=Path(args.v1_book_file),
        v1_audit_file=Path(args.v1_audit_file),
        v2_book_file=Path(args.v2_book_file),
        v2_contract_audit_file=Path(args.v2_contract_audit_file),
        clean_chunks_file=Path(args.clean_chunks_file),
        selected_chapter_numbers=selected_chapter_numbers,
        expected_v1_result_count=expected_v1_result_count,
    )
    if args.dry_run:
        print_dry_run(
            output_path=output_path,
            report_path=report_path,
            checkpoint_path=checkpoint_path,
            bundle=bundle,
        )
        return None

    enforce_overwrite_rules(
        output_path=output_path,
        report_path=report_path,
        checkpoint_path=checkpoint_path,
        raw_dir=raw_dir,
        overwrite=args.overwrite,
        resume=args.resume,
    )

    if args.resume:
        if not checkpoint_path.exists():
            raise TargetedEvaluationError(f"Cannot resume; checkpoint does not exist: {checkpoint_path}")
        checkpoint = require_object(load_json(checkpoint_path, "Checkpoint"), "Checkpoint")
        validate_resume_checkpoint(checkpoint, bundle=bundle, model=args.model)
    else:
        checkpoint = initial_checkpoint(bundle=bundle, model=args.model)

    stats = RuntimeStats(
        model_call_count=int(checkpoint.get("model_call_count") or 0),
        repair_call_count=int(checkpoint.get("repair_call_count") or 0),
    )
    completed_concepts = list(checkpoint.get("completed_source_concept_chapters") or [])
    completed_evaluations = list(checkpoint.get("completed_evaluation_chapters") or [])
    source_concepts_by_chapter = dict(checkpoint.get("source_concepts_by_chapter") or {})
    evaluations_by_chapter = dict(checkpoint.get("evaluations_by_chapter") or {})
    if (
        reevaluate_selected_chapter
        and evaluation_chapter_number not in completed_evaluations
    ):
        raise TargetedEvaluationError(
            f"Cannot reevaluate chapter {evaluation_chapter_number}; it is not complete in the checkpoint."
        )

    for chapter_number in bundle.selected_chapter_numbers:
        if chapter_number in completed_concepts:
            print(f"Skipping source concepts for chapter {chapter_number}; already complete.")
            continue
        chapter_chunks = bundle.chunks_by_chapter[chapter_number]
        prompt = build_source_concept_prompt(
            chapter_number=chapter_number,
            chapter_title=chapter_title_from_v2(bundle, chapter_number),
            chapter_chunks=chapter_chunks,
        )
        try:
            result = call_json_stage_with_repair(
                stage_id=f"chapter_{chapter_number:02d}.source_concepts",
                stage_label="source_concepts",
                chapter_number=chapter_number,
                prompt=prompt,
                expected_ids=[
                    f"chapter_{chapter_number:02d}.concept_{index:02d}"
                    for index in range(1, 16)
                ],
                validate_fn=lambda parsed, chapter_number=chapter_number, chapter_chunks=chapter_chunks: validate_source_concept_inventory(
                    parsed,
                    chapter_number=chapter_number,
                    chapter_chunks=chapter_chunks,
                    clean_chunks_by_id=bundle.clean_chunks_by_id,
                ),
                args=args,
                raw_dir=raw_dir,
                stats=stats,
                complete_fn=complete_fn,
                repair_extra_context={
                    "allowed_evidence_quote_bank": allowed_quote_bank(chapter_chunks),
                    "repair_instruction": (
                        "For each evidence span, choose an exact quote from this bank "
                        "for the same node_id or remove the concept if no quote supports it. "
                        "Do not reuse the same node_id plus quote pair in more than one concept."
                    ),
                },
            )
        except ModelCallTimeoutError as error:
            append_checkpoint_error(
                checkpoint=checkpoint,
                checkpoint_path=checkpoint_path,
                stats=stats,
                stage_label="source_concepts",
                chapter_number=chapter_number,
                error=error,
            )
            raise
        source_concepts_by_chapter[str(chapter_number)] = result
        completed_concepts.append(chapter_number)
        checkpoint["source_concepts_by_chapter"] = source_concepts_by_chapter
        checkpoint["completed_source_concept_chapters"] = completed_concepts
        write_checkpoint(checkpoint_path, checkpoint, stats)
        print(
            f"Completed source concepts for chapter {chapter_number}: "
            f"{len(result['concepts'])} concept(s)."
        )

    newly_completed_evaluation_chapters: list[int] = []
    stopped_due_to_limit = False
    evaluation_chapter_numbers = (
        [evaluation_chapter_number]
        if evaluation_chapter_number is not None
        else bundle.selected_chapter_numbers
    )
    if (
        evaluation_chapter_number is not None
        and evaluation_chapter_number in completed_evaluations
        and not reevaluate_selected_chapter
    ):
        print_exact_chapter_stop(
            args=args,
            checkpoint=checkpoint,
            chapter_number=evaluation_chapter_number,
            newly_completed_evaluation_chapters=[],
            already_complete=True,
        )
        return None
    for chapter_number in evaluation_chapter_numbers:
        if chapter_number in completed_evaluations and not reevaluate_selected_chapter:
            print(f"Skipping chapter evaluation for chapter {chapter_number}; already complete.")
            continue
        if (
            max_new_evaluation_chapters is not None
            and len(newly_completed_evaluation_chapters) >= max_new_evaluation_chapters
        ):
            stopped_due_to_limit = True
            break
        concepts = source_concepts_by_chapter.get(str(chapter_number))
        if not concepts:
            raise TargetedEvaluationError(
                f"Cannot evaluate chapter {chapter_number}; source concept inventory is missing."
            )
        chapter_chunks = bundle.chunks_by_chapter[chapter_number]
        chapter_records = bundle.v2_records_by_chapter[chapter_number]
        prompt = build_chapter_evaluation_prompt(
            chapter_number=chapter_number,
            chapter_title=chapter_title_from_v2(bundle, chapter_number),
            chapter_chunks=chapter_chunks,
            concepts=concepts,
            v1_results=bundle.v1_results_by_chapter[chapter_number],
            v2_records=chapter_records,
        )
        try:
            result = call_json_stage_with_repair(
                stage_id=f"chapter_{chapter_number:02d}.evaluation",
                stage_label="chapter_evaluation",
                chapter_number=chapter_number,
                prompt=prompt,
                expected_ids=[record["record_id"] for record in chapter_records]
                + [concept["concept_id"] for concept in concepts["concepts"]],
                validate_fn=lambda parsed, chapter_number=chapter_number, concepts=concepts, chapter_chunks=chapter_chunks, chapter_records=chapter_records: validate_chapter_evaluation(
                    parsed,
                    chapter_number=chapter_number,
                    concepts=concepts,
                    v1_results=bundle.v1_results_by_chapter[chapter_number],
                    v2_records=chapter_records,
                    chapter_chunks=chapter_chunks,
                ),
                args=args,
                raw_dir=raw_dir,
                stats=stats,
                complete_fn=complete_fn,
            )
        except TargetedEvaluationError as error:
            if isinstance(error, ModelCallTimeoutError) or reevaluate_selected_chapter:
                append_checkpoint_error(
                    checkpoint=checkpoint,
                    checkpoint_path=checkpoint_path,
                    stats=stats,
                    stage_label="chapter_evaluation",
                    chapter_number=chapter_number,
                    error=error,
                )
            raise
        evaluations_by_chapter[str(chapter_number)] = result
        if chapter_number not in completed_evaluations:
            completed_evaluations.append(chapter_number)
            positions = {number: index for index, number in enumerate(bundle.selected_chapter_numbers)}
            completed_evaluations = sorted(
                completed_evaluations, key=lambda number: positions[number]
            )
        newly_completed_evaluation_chapters.append(chapter_number)
        checkpoint["evaluations_by_chapter"] = evaluations_by_chapter
        checkpoint["completed_evaluation_chapters"] = completed_evaluations
        write_checkpoint(checkpoint_path, checkpoint, stats)
        print(
            f"Completed targeted evaluation for chapter {chapter_number}: "
            f"{len(result['v2_record_evaluations'])} record(s)."
        )

    remaining_evaluations = [
        number for number in bundle.selected_chapter_numbers if number not in completed_evaluations
    ]
    if evaluation_chapter_number is not None and remaining_evaluations:
        checkpoint["status"] = "IN_PROGRESS"
        checkpoint["last_run"] = {
            "evaluation_chapter_number": evaluation_chapter_number,
            "reevaluate_selected_chapter": reevaluate_selected_chapter,
            "newly_completed_evaluation_chapters": newly_completed_evaluation_chapters,
            "stopped_after_exact_chapter": True,
        }
        write_checkpoint(checkpoint_path, checkpoint, stats)
        print_exact_chapter_stop(
            args=args,
            checkpoint=checkpoint,
            chapter_number=evaluation_chapter_number,
            newly_completed_evaluation_chapters=newly_completed_evaluation_chapters,
        )
        return None
    if remaining_evaluations and (
        stopped_due_to_limit
        or (
            max_new_evaluation_chapters is not None
            and len(newly_completed_evaluation_chapters) >= max_new_evaluation_chapters
        )
    ):
        checkpoint["status"] = "IN_PROGRESS"
        checkpoint["last_run"] = {
            "max_new_evaluation_chapters": max_new_evaluation_chapters,
            "newly_completed_evaluation_chapters": newly_completed_evaluation_chapters,
            "stopped_due_to_limit": True,
        }
        write_checkpoint(checkpoint_path, checkpoint, stats)
        print_limited_run_stop(
            args=args,
            checkpoint=checkpoint,
            newly_completed_evaluation_chapters=newly_completed_evaluation_chapters,
        )
        return None

    checkpoint["status"] = "COMPLETE"
    checkpoint["completed_source_concept_chapters"] = bundle.selected_chapter_numbers[:]
    checkpoint["completed_evaluation_chapters"] = bundle.selected_chapter_numbers[:]
    write_checkpoint(checkpoint_path, checkpoint, stats)

    result = build_final_output(
        args=args,
        bundle=bundle,
        checkpoint=checkpoint,
        output_path=output_path,
        report_path=report_path,
    )
    atomic_write_json(output_path, result)
    if report_path:
        atomic_write_text(
            report_path,
            format_text_report(result, output_path=output_path, checkpoint_path=checkpoint_path),
        )
    print("Targeted v2 learning-materials evaluation completed.")
    print(f"Run status: {result['run_status']}")
    print(f"Safety verdict: {result['safety_verdict']}")
    print(f"Coverage verdict: {result['coverage_verdict']}")
    print(f"Comparison verdict: {result['comparison_verdict']}")
    print(f"Output path: {output_path}")
    if report_path:
        print(f"Report path: {report_path}")
    print(f"Checkpoint path: {checkpoint_path}")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        evaluate_targeted_book_learning_materials(args)
    except TargetedEvaluationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        if not args.dry_run:
            print(f"Resume with: {resume_command(args)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
