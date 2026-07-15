import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


BOOK_LEARNING_MATERIALS_SCHEMA_VERSION = "book_learning_materials.v2"
BOOK_LEARNING_MATERIALS_CONTRACT_AUDIT_VERSION = (
    "book_learning_materials_contract_audit.v1"
)

ORIGINS = {
    "source_grounded",
    "pedagogical_generation",
    "insufficient_source_evidence",
}
CLAIM_KINDS = {
    "source_summary",
    "learning_objective",
    "definition",
    "official_rule",
    "task_format",
    "strategy",
    "factual_explanation",
    "pronunciation_rule",
    "grammar_rule",
    "pedagogical_example",
    "misconception_statement",
    "misconception_correction",
    "practice_question",
    "practice_answer",
    "learner_instruction",
    "self_assessment",
    "study_plan",
    "other",
}
HIGH_RISK_CLAIM_KINDS = {
    "official_rule",
    "task_format",
    "pronunciation_rule",
    "grammar_rule",
}
PEDAGOGICAL_GENERATION_ALLOWED_KINDS = {
    "pedagogical_example",
    "practice_question",
    "practice_answer",
    "learner_instruction",
    "self_assessment",
    "study_plan",
    # A misconception names a false belief, so it is generated, not grounded: the
    # source states the truth and never the error. Kept in sync with the
    # generator, which coerces every misconception_statement to this origin.
    "misconception_statement",
}

GROUNDED_CONTENT_FIELDS = {
    "text",
    "claim_kind",
    "origin",
    "source_chunk_ids",
    "grounded_in_source_chunk_ids",
    "evidence_spans",
    "reason",
}


class BookLearningMaterialsContractError(Exception):
    pass


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value or "")).strip()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def load_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise BookLearningMaterialsContractError(f"{label} does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BookLearningMaterialsContractError(
            f"{label} is not valid JSON: {path}\nError: {error}"
        ) from error


def chunk_node_id(chunk: dict[str, Any]) -> str | None:
    for key in ("node_id", "id", "chunk_id"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def load_clean_chunks(path: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    data = load_json(path, "Clean chunks file")
    if isinstance(data, dict):
        chunks = data.get("chunks") or data.get("nodes") or data.get("items")
    else:
        chunks = data

    errors: list[dict[str, str]] = []
    lookup: dict[str, dict[str, Any]] = {}

    if not isinstance(chunks, list):
        errors.append(
            {
                "code": "INVALID_TOP_LEVEL_SHAPE",
                "json_path": "$",
                "message": "Clean chunks JSON must be an array or supported wrapper.",
            }
        )
        return lookup, errors

    for index, chunk in enumerate(chunks):
        path_text = f"$[{index}]"
        if not isinstance(chunk, dict):
            errors.append(
                {
                    "code": "INVALID_TOP_LEVEL_SHAPE",
                    "json_path": path_text,
                    "message": "Clean chunk must be an object.",
                }
            )
            continue
        node_id = chunk_node_id(chunk)
        if not node_id:
            errors.append(
                {
                    "code": "SOURCE_CHUNK_ID_NOT_FOUND",
                    "json_path": path_text,
                    "message": "Clean chunk is missing a non-empty node ID.",
                }
            )
            continue
        if node_id in lookup:
            errors.append(
                {
                    "code": "DUPLICATE_CLEAN_CHUNK_ID",
                    "json_path": path_text,
                    "message": f"Duplicate clean chunk ID: {node_id}",
                }
            )
            continue
        text = chunk.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(
                {
                    "code": "EMPTY_CLEAN_CHUNK_TEXT",
                    "json_path": path_text,
                    "message": f"Clean chunk has empty text: {node_id}",
                }
            )
        lookup[node_id] = chunk

    return lookup, errors


class ContractValidator:
    def __init__(
        self,
        *,
        book: dict[str, Any],
        clean_chunks: dict[str, dict[str, Any]],
        book_file: Path,
        clean_chunks_file: Path,
        initial_errors: list[dict[str, str]] | None = None,
    ) -> None:
        self.book = book
        self.clean_chunks = clean_chunks
        self.book_file = book_file
        self.clean_chunks_file = clean_chunks_file
        self.errors: list[dict[str, str]] = list(initial_errors or [])
        self.warnings: list[str] = []
        self.grounded_content_count = 0
        self.claims_by_kind: Counter[str] = Counter()
        self.claims_by_origin: Counter[str] = Counter()
        self.high_risk_claim_count = 0
        self.high_risk_verified_span_count = 0
        self.verified_evidence_span_count = 0
        self.referenced_source_ids: set[str] = set()

    def add_error(self, code: str, json_path: str, message: str) -> None:
        self.errors.append(
            {
                "code": code,
                "json_path": json_path,
                "message": message,
            }
        )

    def validate(self) -> dict[str, Any]:
        self.validate_schema()
        if isinstance(self.book.get("learning_materials"), dict):
            self.validate_learning_materials(self.book["learning_materials"])

        summary = self.summary()
        return {
            "schema_version": BOOK_LEARNING_MATERIALS_CONTRACT_AUDIT_VERSION,
            "status": "FAIL" if self.errors else "PASS",
            "input": {
                "book_file": str(self.book_file),
                "clean_chunks_file": str(self.clean_chunks_file),
                "book_schema_version": self.book.get("schema_version"),
                "book_slug": (self.book.get("book") or {}).get("slug")
                if isinstance(self.book.get("book"), dict)
                else None,
                "source_pdf": (self.book.get("book") or {}).get("source_pdf")
                if isinstance(self.book.get("book"), dict)
                else None,
            },
            "summary": summary,
            "errors": self.sorted_errors(),
            "warnings": self.warnings,
        }

    def sorted_errors(self) -> list[dict[str, str]]:
        return sorted(self.errors, key=lambda item: (item["json_path"], item["code"], item["message"]))

    def summary(self) -> dict[str, Any]:
        errors_by_code = Counter(error["code"] for error in self.errors)
        return {
            "grounded_content_count": self.grounded_content_count,
            "source_grounded_count": self.claims_by_origin["source_grounded"],
            "pedagogical_generation_count": self.claims_by_origin[
                "pedagogical_generation"
            ],
            "insufficient_source_evidence_count": self.claims_by_origin[
                "insufficient_source_evidence"
            ],
            "high_risk_claim_count": self.high_risk_claim_count,
            "high_risk_verified_span_count": self.high_risk_verified_span_count,
            "verified_evidence_span_count": self.verified_evidence_span_count,
            "unique_referenced_source_chunk_count": len(self.referenced_source_ids),
            "invalid_claim_count": len(
                {
                    error["json_path"]
                    for error in self.errors
                    if error["json_path"].startswith("$.learning_materials")
                }
            ),
            "claims_by_kind": dict(sorted(self.claims_by_kind.items())),
            "claims_by_origin": dict(sorted(self.claims_by_origin.items())),
            "errors_by_code": dict(sorted(errors_by_code.items())),
        }

    def validate_schema(self) -> None:
        if not isinstance(self.book, dict):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", "$", "Book JSON must be an object.")
            return

        schema_version = self.book.get("schema_version")
        if schema_version != BOOK_LEARNING_MATERIALS_SCHEMA_VERSION:
            self.add_error(
                "UNSUPPORTED_SCHEMA_VERSION",
                "$.schema_version",
                f"Expected {BOOK_LEARNING_MATERIALS_SCHEMA_VERSION}, got {schema_version!r}.",
            )

        generation = self.book.get("generation")
        pipeline_version = generation.get("pipeline_version") if isinstance(generation, dict) else None
        if pipeline_version != BOOK_LEARNING_MATERIALS_SCHEMA_VERSION:
            self.add_error(
                "PIPELINE_VERSION_MISMATCH",
                "$.generation.pipeline_version",
                f"Expected pipeline_version {BOOK_LEARNING_MATERIALS_SCHEMA_VERSION}, got {pipeline_version!r}.",
            )

        for key in ["book", "generation", "learning_materials", "source_chunks", "audit"]:
            if key not in self.book:
                self.add_error(
                    "INVALID_TOP_LEVEL_SHAPE",
                    f"$.{key}",
                    f"Missing required top-level field: {key}",
                )
        if "source_chunks" in self.book and not isinstance(self.book.get("source_chunks"), list):
            self.add_error(
                "INVALID_TOP_LEVEL_SHAPE",
                "$.source_chunks",
                "source_chunks must be an array.",
            )

    def validate_learning_materials(self, materials: dict[str, Any]) -> None:
        if "book_overview" in materials:
            self.validate_grounded_content(
                materials["book_overview"],
                "$.learning_materials.book_overview",
                allowed_kinds={"source_summary"},
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
            )

        self.validate_grounded_array(
            materials.get("audience"),
            "$.learning_materials.audience",
            allowed_kinds={"learner_instruction", "other"},
            allowed_origins={
                "pedagogical_generation",
                "source_grounded",
                "insufficient_source_evidence",
            },
            required=False,
        )
        self.validate_grounded_array(
            materials.get("usage_instructions"),
            "$.learning_materials.usage_instructions",
            allowed_kinds={"learner_instruction"},
            allowed_origins={
                "pedagogical_generation",
                "source_grounded",
                "insufficient_source_evidence",
            },
            required=False,
        )

        self.validate_study_plan(materials.get("study_plan"))
        self.validate_global_key_terms(materials.get("global_key_terms"))
        self.validate_final_review(materials.get("final_review"))
        self.validate_chapters(materials.get("chapters"))

    def validate_grounded_array(
        self,
        value: Any,
        path: str,
        *,
        allowed_kinds: set[str],
        allowed_origins: set[str],
        required: bool,
        chapter_number: int | None = None,
    ) -> None:
        if value is None:
            if required:
                self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "Missing required array.")
            return
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "Expected an array.")
            return
        for index, item in enumerate(value):
            self.validate_grounded_content(
                item,
                f"{path}[{index}]",
                allowed_kinds=allowed_kinds,
                allowed_origins=allowed_origins,
                chapter_number=chapter_number,
            )

    def validate_study_plan(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", "$.learning_materials.study_plan", "study_plan must be an array.")
            return
        for index, item in enumerate(value):
            path = f"$.learning_materials.study_plan[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "study_plan item must be an object.")
                continue
            self.validate_grounded_content(
                item.get("focus"),
                f"{path}.focus",
                allowed_kinds={"study_plan"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
            )
            activities = item.get("activities")
            if not isinstance(activities, list):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{path}.activities", "activities must be an array.")
                continue
            for activity_index, activity in enumerate(activities):
                self.validate_grounded_content(
                    activity,
                    f"{path}.activities[{activity_index}]",
                    allowed_kinds={"study_plan"},
                    allowed_origins={
                        "pedagogical_generation",
                        "source_grounded",
                        "insufficient_source_evidence",
                    },
                )

    def validate_global_key_terms(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", "$.learning_materials.global_key_terms", "global_key_terms must be an array.")
            return
        for index, item in enumerate(value):
            path = f"$.learning_materials.global_key_terms[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "global_key_terms item must be an object.")
                continue
            if not isinstance(item.get("term"), str) or not item["term"].strip():
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{path}.term", "term must be a non-empty string.")
            self.validate_grounded_content(
                item.get("meaning"),
                f"{path}.meaning",
                allowed_kinds={"definition"},
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
            )

    def validate_final_review(self, value: Any) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", "$.learning_materials.final_review", "final_review must be an object.")
            return
        self.validate_grounded_content(
            value.get("summary"),
            "$.learning_materials.final_review.summary",
            allowed_kinds={"source_summary", "self_assessment"},
            allowed_origins={
                "source_grounded",
                "pedagogical_generation",
                "insufficient_source_evidence",
            },
        )
        questions = value.get("questions")
        if not isinstance(questions, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", "$.learning_materials.final_review.questions", "questions must be an array.")
            return
        for index, item in enumerate(questions):
            path = f"$.learning_materials.final_review.questions[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "question item must be an object.")
                continue
            self.validate_grounded_content(
                item.get("question"),
                f"{path}.question",
                allowed_kinds={"practice_question"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
            )
            self.validate_grounded_content(
                item.get("answer"),
                f"{path}.answer",
                allowed_kinds={"practice_answer"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
            )

    def validate_chapters(self, value: Any) -> None:
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", "$.learning_materials.chapters", "chapters must be an array.")
            return
        seen_numbers: set[int] = set()
        for index, chapter in enumerate(value):
            path = f"$.learning_materials.chapters[{index}]"
            if not isinstance(chapter, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "chapter must be an object.")
                continue
            chapter_number = chapter.get("chapter_number")
            if not isinstance(chapter_number, int) or chapter_number <= 0:
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{path}.chapter_number", "chapter_number must be a positive integer.")
                chapter_number = None
            elif chapter_number in seen_numbers:
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{path}.chapter_number", f"Duplicate chapter_number: {chapter_number}")
            else:
                seen_numbers.add(chapter_number)

            if not isinstance(chapter.get("chapter_title"), str) or not chapter["chapter_title"].strip():
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{path}.chapter_title", "chapter_title must be a non-empty string.")

            self.validate_source_id_array(
                chapter.get("source_chunk_ids"),
                f"{path}.source_chunk_ids",
                chapter_number=chapter_number,
                allow_empty=True,
            )

            self.validate_grounded_content(
                chapter.get("estimated_study_time"),
                f"{path}.estimated_study_time",
                allowed_kinds={"study_plan"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
                chapter_number=chapter_number,
            )
            self.validate_grounded_content(
                chapter.get("chapter_summary"),
                f"{path}.chapter_summary",
                allowed_kinds={"source_summary"},
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
                chapter_number=chapter_number,
            )
            self.validate_grounded_array(
                chapter.get("learning_objectives"),
                f"{path}.learning_objectives",
                allowed_kinds={"learning_objective"},
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
                required=True,
                chapter_number=chapter_number,
            )
            self.validate_chapter_key_terms(chapter.get("key_terms"), path, chapter_number)
            self.validate_core_lessons(chapter.get("core_lessons"), path, chapter_number)
            self.validate_worked_examples(chapter.get("worked_examples"), path, chapter_number)
            self.validate_common_misconceptions(chapter.get("common_misconceptions"), path, chapter_number)
            self.validate_practice_questions(chapter.get("practice_questions"), path, chapter_number)
            self.validate_grounded_array(
                chapter.get("review_checklist"),
                f"{path}.review_checklist",
                allowed_kinds={"self_assessment"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
                required=True,
                chapter_number=chapter_number,
            )

    def validate_chapter_key_terms(self, value: Any, chapter_path: str, chapter_number: int | None) -> None:
        path = f"{chapter_path}.key_terms"
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "key_terms must be an array.")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", item_path, "key_terms item must be an object.")
                continue
            if not isinstance(item.get("term"), str) or not item["term"].strip():
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{item_path}.term", "term must be a non-empty string.")
            self.validate_grounded_content(
                item.get("meaning"),
                f"{item_path}.meaning",
                allowed_kinds={"definition"},
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
                chapter_number=chapter_number,
            )

    def validate_core_lessons(self, value: Any, chapter_path: str, chapter_number: int | None) -> None:
        path = f"{chapter_path}.core_lessons"
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "core_lessons must be an array.")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", item_path, "core_lessons item must be an object.")
                continue
            if not isinstance(item.get("title"), str) or not item["title"].strip():
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{item_path}.title", "title must be a non-empty string.")
            self.validate_grounded_content(
                item.get("explanation"),
                f"{item_path}.explanation",
                allowed_kinds={
                    "source_summary",
                    "official_rule",
                    "task_format",
                    "strategy",
                    "factual_explanation",
                    "pronunciation_rule",
                    "grammar_rule",
                },
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
                chapter_number=chapter_number,
            )

    def validate_worked_examples(self, value: Any, chapter_path: str, chapter_number: int | None) -> None:
        path = f"{chapter_path}.worked_examples"
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "worked_examples must be an array.")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", item_path, "worked_examples item must be an object.")
                continue
            if not isinstance(item.get("title"), str) or not item["title"].strip():
                self.add_error("INVALID_TOP_LEVEL_SHAPE", f"{item_path}.title", "title must be a non-empty string.")
            self.validate_grounded_content(
                item.get("example"),
                f"{item_path}.example",
                allowed_kinds={"pedagogical_example"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
                chapter_number=chapter_number,
            )
            self.validate_grounded_content(
                item.get("explanation"),
                f"{item_path}.explanation",
                allowed_kinds={
                    "strategy",
                    "factual_explanation",
                    "official_rule",
                    "task_format",
                    "pronunciation_rule",
                    "grammar_rule",
                },
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
                chapter_number=chapter_number,
            )

    def validate_common_misconceptions(self, value: Any, chapter_path: str, chapter_number: int | None) -> None:
        path = f"{chapter_path}.common_misconceptions"
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "common_misconceptions must be an array.")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", item_path, "common_misconceptions item must be an object.")
                continue
            self.validate_grounded_content(
                item.get("misconception"),
                f"{item_path}.misconception",
                allowed_kinds={"misconception_statement"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
                chapter_number=chapter_number,
            )
            self.validate_grounded_content(
                item.get("correction"),
                f"{item_path}.correction",
                allowed_kinds={"misconception_correction"},
                allowed_origins={"source_grounded", "insufficient_source_evidence"},
                chapter_number=chapter_number,
            )

    def validate_practice_questions(self, value: Any, chapter_path: str, chapter_number: int | None) -> None:
        path = f"{chapter_path}.practice_questions"
        if not isinstance(value, list):
            self.add_error("INVALID_TOP_LEVEL_SHAPE", path, "practice_questions must be an array.")
            return
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not isinstance(item, dict):
                self.add_error("INVALID_TOP_LEVEL_SHAPE", item_path, "practice_questions item must be an object.")
                continue
            self.validate_grounded_content(
                item.get("question"),
                f"{item_path}.question",
                allowed_kinds={"practice_question"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
                chapter_number=chapter_number,
            )
            self.validate_grounded_content(
                item.get("answer"),
                f"{item_path}.answer",
                allowed_kinds={"practice_answer"},
                allowed_origins={
                    "pedagogical_generation",
                    "source_grounded",
                    "insufficient_source_evidence",
                },
                chapter_number=chapter_number,
            )

    def validate_grounded_content(
        self,
        value: Any,
        path: str,
        *,
        allowed_kinds: set[str],
        allowed_origins: set[str],
        chapter_number: int | None = None,
    ) -> None:
        if not isinstance(value, dict):
            self.add_error(
                "INVALID_GROUNDED_CONTENT_SHAPE",
                path,
                "Grounded content must be an object.",
            )
            return

        missing = sorted(GROUNDED_CONTENT_FIELDS - set(value))
        if missing:
            self.add_error(
                "INVALID_GROUNDED_CONTENT_SHAPE",
                path,
                "Missing grounded-content fields: " + ", ".join(missing),
            )
            return

        self.grounded_content_count += 1
        claim_kind = value.get("claim_kind")
        origin = value.get("origin")

        if claim_kind not in CLAIM_KINDS:
            self.add_error(
                "INVALID_CLAIM_KIND",
                f"{path}.claim_kind",
                f"Unknown claim kind: {claim_kind!r}",
            )
        elif claim_kind not in allowed_kinds:
            self.add_error(
                "INVALID_CLAIM_KIND",
                f"{path}.claim_kind",
                f"Claim kind {claim_kind} is not allowed for this field.",
            )
        else:
            self.claims_by_kind[claim_kind] += 1

        if origin not in ORIGINS:
            self.add_error(
                "INVALID_ORIGIN",
                f"{path}.origin",
                f"Unknown origin: {origin!r}",
            )
        elif origin not in allowed_origins:
            self.add_error(
                "PEDAGOGICAL_ORIGIN_NOT_ALLOWED",
                f"{path}.origin",
                f"Origin {origin} is not allowed for this field.",
            )
        else:
            self.claims_by_origin[origin] += 1

        is_high_risk = claim_kind in HIGH_RISK_CLAIM_KINDS
        if is_high_risk:
            self.high_risk_claim_count += 1
            if origin == "pedagogical_generation":
                self.add_error(
                    "HIGH_RISK_PEDAGOGICAL_GENERATION_FORBIDDEN",
                    path,
                    f"High-risk claim kind {claim_kind} cannot use pedagogical_generation.",
                )

        if origin == "pedagogical_generation" and claim_kind not in PEDAGOGICAL_GENERATION_ALLOWED_KINDS:
            self.add_error(
                "PEDAGOGICAL_ORIGIN_NOT_ALLOWED",
                path,
                f"pedagogical_generation is not allowed for claim kind {claim_kind}.",
            )

        source_ids = self.validate_source_id_array(
            value.get("source_chunk_ids"),
            f"{path}.source_chunk_ids",
            chapter_number=chapter_number,
            allow_empty=True,
        )
        grounded_ids = self.validate_source_id_array(
            value.get("grounded_in_source_chunk_ids"),
            f"{path}.grounded_in_source_chunk_ids",
            chapter_number=chapter_number,
            allow_empty=True,
        )

        text = value.get("text")
        reason = value.get("reason")
        evidence_spans = value.get("evidence_spans")
        if not isinstance(evidence_spans, list):
            self.add_error(
                "INVALID_GROUNDED_CONTENT_SHAPE",
                f"{path}.evidence_spans",
                "evidence_spans must be an array.",
            )
            evidence_spans = []

        if origin == "source_grounded":
            if not isinstance(text, str) or not text.strip():
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.text",
                    "source_grounded text must be a non-empty string.",
                )
            if not source_ids:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.source_chunk_ids",
                    "source_grounded content must cite at least one source chunk.",
                )
                if chapter_number is not None:
                    self.add_error(
                        "INHERITED_CITATION_NOT_SUPPORTED",
                        f"{path}.source_chunk_ids",
                        "Chapter-scoped source_grounded content must carry explicit local source_chunk_ids.",
                    )
            if grounded_ids:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.grounded_in_source_chunk_ids",
                    "source_grounded content must not use grounded_in_source_chunk_ids.",
                )
            if reason is not None:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.reason",
                    "source_grounded reason must be null.",
                )
            if is_high_risk and not evidence_spans:
                self.add_error(
                    "HIGH_RISK_EVIDENCE_SPAN_REQUIRED",
                    f"{path}.evidence_spans",
                    "High-risk source_grounded content requires at least one evidence span.",
                )
        elif origin == "pedagogical_generation":
            if not isinstance(text, str) or not text.strip():
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.text",
                    "pedagogical_generation text must be a non-empty string.",
                )
            if source_ids:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.source_chunk_ids",
                    "pedagogical_generation must not use source_chunk_ids.",
                )
            if evidence_spans:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.evidence_spans",
                    "pedagogical_generation must not use evidence_spans.",
                )
            if reason is not None:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.reason",
                    "pedagogical_generation reason must be null.",
                )
        elif origin == "insufficient_source_evidence":
            if text is not None:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.text",
                    "insufficient_source_evidence text must be null.",
                )
            if source_ids:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.source_chunk_ids",
                    "insufficient_source_evidence must not use source_chunk_ids.",
                )
            if grounded_ids:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.grounded_in_source_chunk_ids",
                    "insufficient_source_evidence must not use grounded_in_source_chunk_ids.",
                )
            if evidence_spans:
                self.add_error(
                    "INVALID_ORIGIN_FIELD_COMBINATION",
                    f"{path}.evidence_spans",
                    "insufficient_source_evidence must not use evidence_spans.",
                )
            if not isinstance(reason, str) or not reason.strip():
                self.add_error(
                    "MISSING_INSUFFICIENT_EVIDENCE_REASON",
                    f"{path}.reason",
                    "insufficient_source_evidence requires a non-empty reason.",
                )

        self.validate_evidence_spans(
            spans=evidence_spans,
            path=f"{path}.evidence_spans",
            source_ids=source_ids,
            chapter_number=chapter_number,
            is_high_risk_source_grounded=bool(is_high_risk and origin == "source_grounded"),
        )

    def validate_source_id_array(
        self,
        value: Any,
        path: str,
        *,
        chapter_number: int | None,
        allow_empty: bool,
    ) -> list[str]:
        if not isinstance(value, list):
            self.add_error("INVALID_GROUNDED_CONTENT_SHAPE", path, "Expected an array of source IDs.")
            return []
        ids: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                self.add_error("SOURCE_CHUNK_ID_NOT_FOUND", f"{path}[{index}]", "Source chunk ID must be a non-empty string.")
                continue
            ids.append(item.strip())

        duplicates = [node_id for node_id, count in Counter(ids).items() if count > 1]
        for duplicate in duplicates:
            self.add_error("DUPLICATE_SOURCE_CHUNK_ID", path, f"Duplicate source chunk ID: {duplicate}")

        if not ids and not allow_empty:
            self.add_error("SOURCE_CHUNK_ID_NOT_FOUND", path, "At least one source chunk ID is required.")

        for node_id in ids:
            self.referenced_source_ids.add(node_id)
            chunk = self.clean_chunks.get(node_id)
            if chunk is None:
                self.add_error("SOURCE_CHUNK_ID_NOT_FOUND", path, f"Source chunk ID not found: {node_id}")
                continue
            self.validate_chunk_consistency(
                chunk=chunk,
                node_id=node_id,
                path=path,
                chapter_number=chapter_number,
            )
        return ids

    def validate_chunk_consistency(
        self,
        *,
        chunk: dict[str, Any],
        node_id: str,
        path: str,
        chapter_number: int | None,
    ) -> None:
        if chapter_number is not None and chunk.get("chapter_number") is not None:
            try:
                chunk_chapter = int(chunk.get("chapter_number"))
            except (TypeError, ValueError):
                chunk_chapter = None
            if chunk_chapter is not None and chunk_chapter != chapter_number:
                self.add_error(
                    "CHAPTER_MISMATCH",
                    path,
                    f"Source chunk {node_id} belongs to chapter {chunk_chapter}, not {chapter_number}.",
                )

        book_source = self.book.get("book", {}).get("source_pdf") if isinstance(self.book.get("book"), dict) else None
        chunk_source = chunk.get("source_pdf")
        if (
            isinstance(book_source, str)
            and book_source.strip()
            and isinstance(chunk_source, str)
            and chunk_source.strip()
            and book_source.strip() != chunk_source.strip()
        ):
            self.add_error(
                "SOURCE_DOCUMENT_MISMATCH",
                path,
                f"Source chunk {node_id} belongs to {chunk_source}, not {book_source}.",
            )

    def validate_evidence_spans(
        self,
        *,
        spans: list[Any],
        path: str,
        source_ids: list[str],
        chapter_number: int | None,
        is_high_risk_source_grounded: bool,
    ) -> None:
        seen: set[tuple[str, str]] = set()
        verified_for_this_content = 0
        for index, span in enumerate(spans):
            span_path = f"{path}[{index}]"
            if not isinstance(span, dict):
                self.add_error("INVALID_GROUNDED_CONTENT_SHAPE", span_path, "Evidence span must be an object.")
                continue
            node_id = span.get("node_id")
            quote = span.get("quote")
            if not isinstance(node_id, str) or not node_id.strip():
                self.add_error("SOURCE_CHUNK_ID_NOT_FOUND", f"{span_path}.node_id", "Evidence span node_id must be non-empty.")
                continue
            node_id = node_id.strip()
            if not isinstance(quote, str) or not quote.strip():
                self.add_error("EVIDENCE_SPAN_QUOTE_TOO_SHORT", f"{span_path}.quote", "Evidence span quote must be non-empty.")
                continue

            normalized_quote = normalize_text(quote)
            key = (node_id, normalized_quote)
            if key in seen:
                self.add_error("DUPLICATE_EVIDENCE_SPAN", span_path, "Duplicate evidence span.")
            seen.add(key)

            if node_id not in source_ids:
                self.add_error(
                    "EVIDENCE_SPAN_NODE_NOT_CITED",
                    f"{span_path}.node_id",
                    "Evidence span node_id must appear in source_chunk_ids.",
                )

            words = normalized_quote.split()
            if len(words) < 4:
                self.add_error(
                    "EVIDENCE_SPAN_QUOTE_TOO_SHORT",
                    f"{span_path}.quote",
                    "Evidence span quote must contain at least 4 words.",
                )
            if len(words) > 80:
                self.add_error(
                    "EVIDENCE_SPAN_QUOTE_TOO_LONG",
                    f"{span_path}.quote",
                    "Evidence span quote must contain at most 80 words.",
                )

            chunk = self.clean_chunks.get(node_id)
            if chunk is None:
                self.add_error("SOURCE_CHUNK_ID_NOT_FOUND", span_path, f"Source chunk ID not found: {node_id}")
                continue
            self.validate_chunk_consistency(
                chunk=chunk,
                node_id=node_id,
                path=span_path,
                chapter_number=chapter_number,
            )
            text = chunk.get("text")
            if isinstance(text, str) and normalized_quote not in normalize_text(text):
                self.add_error(
                    "EVIDENCE_SPAN_QUOTE_NOT_FOUND",
                    f"{span_path}.quote",
                    "Evidence quote was not found exactly in normalized clean source text.",
                )
                continue
            if 4 <= len(words) <= 80 and node_id in source_ids:
                verified_for_this_content += 1
                self.verified_evidence_span_count += 1

        if is_high_risk_source_grounded and verified_for_this_content > 0:
            self.high_risk_verified_span_count += 1


def validate_book_contract(
    *,
    book_file: str | Path,
    clean_chunks_file: str | Path,
) -> dict[str, Any]:
    book_path = Path(book_file)
    clean_path = Path(clean_chunks_file)
    book = load_json(book_path, "Book file")
    clean_chunks, clean_errors = load_clean_chunks(clean_path)
    validator = ContractValidator(
        book=book if isinstance(book, dict) else {},
        clean_chunks=clean_chunks,
        book_file=book_path,
        clean_chunks_file=clean_path,
        initial_errors=clean_errors,
    )
    if not isinstance(book, dict):
        validator.add_error("INVALID_TOP_LEVEL_SHAPE", "$", "Book JSON must be an object.")
    return validator.validate()


def format_text_report(audit: dict[str, Any], output_path: Path) -> str:
    summary = audit["summary"]
    input_info = audit["input"]
    lines = [
        "BOOK LEARNING MATERIALS CONTRACT AUDIT",
        f"Book file: {input_info.get('book_file')}",
        f"Clean chunks file: {input_info.get('clean_chunks_file')}",
        f"Book schema: {input_info.get('book_schema_version')}",
        f"Source PDF: {input_info.get('source_pdf')}",
        f"Book slug: {input_info.get('book_slug')}",
        f"Status: {audit.get('status')}",
        "",
        "CONTENT ORIGINS",
        f"Source grounded: {summary['source_grounded_count']}",
        f"Pedagogical generation: {summary['pedagogical_generation_count']}",
        f"Insufficient source evidence: {summary['insufficient_source_evidence_count']}",
        "",
        "HIGH-RISK CLAIMS",
        f"Total: {summary['high_risk_claim_count']}",
        f"With verified evidence spans: {summary['high_risk_verified_span_count']}",
        f"Invalid: {summary['invalid_claim_count']}",
        "",
        "EVIDENCE",
        f"Verified evidence spans: {summary['verified_evidence_span_count']}",
        f"Unique referenced source chunks: {summary['unique_referenced_source_chunk_count']}",
        "",
        "CLAIMS BY KIND",
    ]
    for key, count in summary["claims_by_kind"].items():
        lines.append(f"{key}: {count}")
    lines.extend(["", "CLAIMS BY ORIGIN"])
    for key, count in summary["claims_by_origin"].items():
        lines.append(f"{key}: {count}")
    lines.extend(["", "ERRORS BY CODE"])
    if summary["errors_by_code"]:
        for key, count in summary["errors_by_code"].items():
            lines.append(f"{key}: {count}")
    else:
        lines.append("none")
    lines.extend(["", "ERROR DETAILS"])
    if audit["errors"]:
        for error in audit["errors"][:100]:
            lines.append(
                f"- {error['code']} | {error['json_path']} | {error['message']}"
            )
    else:
        lines.append("- none")
    lines.extend(["", "WARNINGS"])
    lines.extend([f"- {warning}" for warning in audit["warnings"]] or ["- none"])
    lines.extend(["", "OUTPUT", f"JSON: {output_path}", ""])
    return "\n".join(lines)


def ensure_can_write(paths: list[Path], overwrite: bool) -> None:
    if overwrite:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        raise BookLearningMaterialsContractError(
            "Output already exists. Use --overwrite to replace: "
            + ", ".join(str(path) for path in existing)
        )
