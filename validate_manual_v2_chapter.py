import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

from book_learning_materials_contract import (
    BOOK_LEARNING_MATERIALS_SCHEMA_VERSION,
    BookLearningMaterialsContractError,
    ContractValidator,
    atomic_write_json,
    atomic_write_text,
    format_text_report,
    load_json,
)
from book_learning_materials_v2_generation import (
    BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION,
    iter_grounded_content,
    validate_substantive_v2_chapter,
)


class ManualV2ChapterValidationError(RuntimeError):
    pass


SUBSTANTIVE_COUNT_FIELDS = [
    "learning_objectives",
    "key_terms",
    "core_lessons",
    "worked_examples",
    "common_misconceptions",
    "practice_questions",
    "review_checklist",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a standalone manually generated book_learning_materials.v2 chapter."
    )
    parser.add_argument("--chapter-file", required=True)
    parser.add_argument("--base-book-file", required=True)
    parser.add_argument("--chapter-number", required=True, type=int)
    parser.add_argument("--assembled-book-output", required=True)
    parser.add_argument("--contract-audit-output", required=True)
    parser.add_argument("--contract-report-output", required=True)
    parser.add_argument("--substantive-audit-output", required=True)
    return parser.parse_args(argv)


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    value = load_json(path, label)
    if not isinstance(value, dict):
        raise ManualV2ChapterValidationError(f"{label} must be a JSON object: {path}")
    return value


def validate_manual_chapter_number(
    chapter: dict[str, Any],
    *,
    chapter_number: int,
) -> None:
    actual = chapter.get("chapter_number")
    if actual != chapter_number:
        raise ManualV2ChapterValidationError(
            f"Manual chapter_number mismatch: expected {chapter_number}, got {actual!r}."
        )


def clean_chunks_path_from_base_book(base_book: dict[str, Any]) -> Path:
    generation = base_book.get("generation")
    clean_chunks_path = (
        generation.get("clean_chunks_path") if isinstance(generation, dict) else None
    )
    if not isinstance(clean_chunks_path, str) or not clean_chunks_path.strip():
        raise ManualV2ChapterValidationError(
            "Base book is missing generation.clean_chunks_path."
        )
    return Path(clean_chunks_path)


def normalize_node_id(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def collect_referenced_source_chunk_ids(book: dict[str, Any]) -> list[str]:
    referenced: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        node_id = normalize_node_id(value)
        if node_id is None or node_id in seen:
            return
        seen.add(node_id)
        referenced.append(node_id)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"source_chunk_ids", "grounded_in_source_chunk_ids"}:
                    if isinstance(child, list):
                        for item in child:
                            add(item)
                    continue
                if key == "evidence_spans" and isinstance(child, list):
                    for span in child:
                        if isinstance(span, dict):
                            add(span.get("node_id"))
                    continue
                walk(child)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(book)
    return referenced


def clean_chunk_node_id(chunk: dict[str, Any]) -> str | None:
    for key in ("node_id", "id", "chunk_id"):
        node_id = normalize_node_id(chunk.get(key))
        if node_id is not None:
            return node_id
    return None


def clean_chunk_items(data: Any) -> tuple[list[Any] | None, str]:
    if isinstance(data, dict):
        for key in ("chunks", "nodes", "items"):
            if key in data:
                return data.get(key), f"$.{key}"
    return data, "$"


def filtered_clean_chunk_lookup(
    *,
    clean_chunks_path: Path,
    referenced_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    data = load_json(clean_chunks_path, "Clean chunks file")
    chunks, base_path = clean_chunk_items(data)
    if not isinstance(chunks, list):
        return (
            {},
            [
                {
                    "code": "INVALID_TOP_LEVEL_SHAPE",
                    "json_path": "$",
                    "message": "Clean chunks JSON must be an array or supported wrapper.",
                }
            ],
            [],
        )

    referenced = set(referenced_ids)
    lookup: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, Any]] = []

    for index, chunk in enumerate(chunks):
        path = f"{base_path}[{index}]"
        if not isinstance(chunk, dict):
            continue
        node_id = clean_chunk_node_id(chunk)
        if node_id is None:
            continue
        text = chunk.get("text")
        has_text = isinstance(text, str) and bool(text.strip())
        if node_id not in referenced:
            if not has_text:
                warnings.append(
                    {
                        "code": "UNREFERENCED_EMPTY_CLEAN_CHUNK_IGNORED",
                        "source_chunk_id": node_id,
                        "json_path": path,
                    }
                )
            continue
        if node_id in lookup:
            errors.append(
                {
                    "code": "DUPLICATE_CLEAN_CHUNK_ID",
                    "json_path": path,
                    "message": f"Duplicate clean chunk ID: {node_id}",
                }
            )
            continue
        if not has_text:
            errors.append(
                {
                    "code": "EMPTY_CLEAN_CHUNK_TEXT",
                    "json_path": path,
                    "message": f"Clean chunk has empty text: {node_id}",
                }
            )
        lookup[node_id] = chunk

    for node_id in referenced_ids:
        if node_id not in lookup:
            errors.append(
                {
                    "code": "SOURCE_CHUNK_ID_NOT_FOUND",
                    "json_path": "$",
                    "message": f"Referenced source chunk ID not found: {node_id}",
                }
            )

    return lookup, errors, warnings


def validate_contract_with_filtered_clean_chunks(
    *,
    book: dict[str, Any],
    book_file: Path,
    clean_chunks_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    referenced_ids = collect_referenced_source_chunk_ids(book)
    clean_chunks, clean_errors, warnings = filtered_clean_chunk_lookup(
        clean_chunks_path=clean_chunks_path,
        referenced_ids=referenced_ids,
    )
    validator = ContractValidator(
        book=book,
        clean_chunks=clean_chunks,
        book_file=book_file,
        clean_chunks_file=clean_chunks_path,
        initial_errors=clean_errors,
    )
    return validator.validate(), warnings


def assemble_book_with_manual_chapter(
    *,
    base_book: dict[str, Any],
    manual_chapter: dict[str, Any],
    chapter_number: int,
    chapter_file: Path,
    base_book_file: Path,
) -> dict[str, Any]:
    schema_version = base_book.get("schema_version")
    if schema_version != BOOK_LEARNING_MATERIALS_SCHEMA_VERSION:
        raise ManualV2ChapterValidationError(
            "Base book schema_version mismatch: expected "
            f"{BOOK_LEARNING_MATERIALS_SCHEMA_VERSION}, got {schema_version!r}."
        )

    materials = base_book.get("learning_materials")
    chapters = materials.get("chapters") if isinstance(materials, dict) else None
    if not isinstance(chapters, list):
        raise ManualV2ChapterValidationError(
            "Base book is missing learning_materials.chapters."
        )

    replacement_index = None
    for index, chapter in enumerate(chapters):
        if isinstance(chapter, dict) and chapter.get("chapter_number") == chapter_number:
            replacement_index = index
            break
    if replacement_index is None:
        raise ManualV2ChapterValidationError(
            f"Chapter {chapter_number} was not found in base book learning_materials.chapters."
        )

    assembled = copy.deepcopy(base_book)
    assembled["learning_materials"]["chapters"][replacement_index] = copy.deepcopy(
        manual_chapter
    )
    generation = assembled.setdefault("generation", {})
    if not isinstance(generation, dict):
        raise ManualV2ChapterValidationError("Base book generation must be an object.")
    generation["manual_validation"] = {
        "artifact_type": "manual_v2_chapter_validation",
        "chapter_number": chapter_number,
        "chapter_file": str(chapter_file),
        "base_book_file": str(base_book_file),
    }
    return assembled


def source_chunk_ids(chapter: dict[str, Any]) -> list[str]:
    values = chapter.get("source_chunk_ids")
    if not isinstance(values, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        node_id = value.strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        output.append(node_id)
    return output


def substantive_counts(chapter: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for field in SUBSTANTIVE_COUNT_FIELDS:
        value = chapter.get(field)
        counts[field] = len(value) if isinstance(value, list) else 0
    return counts


def distinct_source_grounded_chunk_ids(
    chapter: dict[str, Any],
    *,
    allowed_ids: list[str],
) -> list[str]:
    allowed = set(allowed_ids)
    found: set[str] = set()
    for _path, grounded_object in iter_grounded_content(
        chapter, "$.learning_materials.chapters[0]"
    ):
        if grounded_object.get("origin") != "source_grounded":
            continue
        for node_id in grounded_object.get("source_chunk_ids") or []:
            if isinstance(node_id, str) and node_id in allowed:
                found.add(node_id)
    return sorted(found)


def build_substantive_audit(
    *,
    chapter: dict[str, Any],
    chapter_number: int,
    warnings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    allowed_ids = source_chunk_ids(chapter)
    errors = validate_substantive_v2_chapter(
        candidate=chapter,
        allowed_ids=allowed_ids,
    )
    grounded_ids = distinct_source_grounded_chunk_ids(
        chapter,
        allowed_ids=allowed_ids,
    )
    return {
        "status": "FAIL" if errors else "PASS",
        "chapter_number": chapter_number,
        "prompt_version": BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION,
        "counts": substantive_counts(chapter),
        "distinct_source_grounded_chunk_ids": grounded_ids,
        "distinct_source_grounded_chunk_count": len(grounded_ids),
        "warnings": warnings or [],
        "errors": errors,
    }


def validate_manual_v2_chapter(args: argparse.Namespace) -> dict[str, Any]:
    chapter_file = Path(args.chapter_file)
    base_book_file = Path(args.base_book_file)
    assembled_book_output = Path(args.assembled_book_output)
    contract_audit_output = Path(args.contract_audit_output)
    contract_report_output = Path(args.contract_report_output)
    substantive_audit_output = Path(args.substantive_audit_output)

    manual_chapter = load_json_object(chapter_file, "Manual chapter file")
    validate_manual_chapter_number(
        manual_chapter,
        chapter_number=args.chapter_number,
    )

    base_book = load_json_object(base_book_file, "Base book file")
    clean_chunks_path = clean_chunks_path_from_base_book(base_book)
    assembled = assemble_book_with_manual_chapter(
        base_book=base_book,
        manual_chapter=manual_chapter,
        chapter_number=args.chapter_number,
        chapter_file=chapter_file,
        base_book_file=base_book_file,
    )

    atomic_write_json(assembled_book_output, assembled)
    contract_audit, adapter_warnings = validate_contract_with_filtered_clean_chunks(
        book=assembled,
        book_file=assembled_book_output,
        clean_chunks_path=clean_chunks_path,
    )
    substantive_audit = build_substantive_audit(
        chapter=manual_chapter,
        chapter_number=args.chapter_number,
        warnings=adapter_warnings,
    )

    atomic_write_json(contract_audit_output, contract_audit)
    atomic_write_text(
        contract_report_output,
        format_text_report(contract_audit, contract_audit_output),
    )
    atomic_write_json(substantive_audit_output, substantive_audit)

    return {
        "assembled_book": assembled,
        "contract_audit": contract_audit,
        "substantive_audit": substantive_audit,
    }


def run(args: argparse.Namespace) -> int:
    result = validate_manual_v2_chapter(args)
    contract_audit = result["contract_audit"]
    substantive_audit = result["substantive_audit"]

    print("Manual v2 chapter validation completed.")
    print(f"Chapter file: {args.chapter_file}")
    print(f"Base book file: {args.base_book_file}")
    print(f"Chapter number: {args.chapter_number}")
    print(f"Assembled book output: {args.assembled_book_output}")
    print(f"Contract audit output: {args.contract_audit_output}")
    print(f"Contract report output: {args.contract_report_output}")
    print(f"Substantive audit output: {args.substantive_audit_output}")
    print(f"Contract status: {contract_audit.get('status')}")
    print(
        "Contract invalid claim count: "
        f"{(contract_audit.get('summary') or {}).get('invalid_claim_count')}"
    )
    print(f"Substantive status: {substantive_audit.get('status')}")
    print(
        "Distinct source-grounded chunk count: "
        f"{substantive_audit.get('distinct_source_grounded_chunk_count')}"
    )
    return 0 if contract_audit.get("status") == "PASS" and substantive_audit.get("status") == "PASS" else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run(args)
    except (BookLearningMaterialsContractError, ManualV2ChapterValidationError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
