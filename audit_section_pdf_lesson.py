import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from retrieval_ordering import (
    RetrievalOrderingError,
    build_section_position_map,
)


DEFAULT_STRUCTURE_RESOLUTION = "extracted/sample.structure_resolution.json"
TEXT_PREVIEW_MAX_CHARS = 300

REQUIRED_TOP_LEVEL_FIELDS = [
    "title",
    "learning_objectives",
    "introduction",
    "key_ideas",
    "explanation",
    "worked_examples",
    "common_misconceptions",
    "practice_questions",
    "summary",
    "source",
    "source_chunks",
]

REQUIRED_SOURCE_FIELDS = [
    "index_id",
    "storage_dir",
    "query",
    "filters",
    "retrieved_chunk_count",
    "ordering",
    "section_coverage",
    "requested_section",
    "include_descendants",
    "resolved_chapter_number",
    "expanded_section_titles",
]

REQUIRED_SOURCE_CHUNK_FIELDS = [
    "node_id",
    "score",
    "source_pdf",
    "book_title",
    "chapter",
    "chapter_number",
    "section",
    "topic",
    "page_start",
    "page_end",
    "text_preview",
]

SOURCE_REFERENCE_SECTIONS = [
    ("key_ideas", "source_chunk_ids"),
    ("worked_examples", "source_chunk_ids"),
    ("common_misconceptions", "source_chunk_ids"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit grounding and quality for a generated section PDF lesson JSON file."
    )
    parser.add_argument(
        "lesson_json_path",
        help="Path to a generated section PDF lesson JSON file.",
    )
    parser.add_argument(
        "--structure-resolution",
        default=DEFAULT_STRUCTURE_RESOLUTION,
        help="Path to structure resolution JSON for document-order auditing.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as audit failures.",
    )
    return parser.parse_args()


def derive_output_paths(input_path: Path) -> tuple[Path, Path]:
    input_name = input_path.name

    if input_name.endswith(".generated.json"):
        audit_stem = input_name[: -len(".generated.json")]
        output_json = input_path.with_name(f"{audit_stem}.audit.json")
        output_text = input_path.with_name(f"{audit_stem}.audit.txt")
        return output_json, output_text

    output_json = input_path.with_suffix(".audit.json")
    output_text = input_path.with_suffix(".audit.txt")
    return output_json, output_text


def sortable_number(value: Any) -> tuple[int, int | float]:
    if value is None:
        return (1, 0)

    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, 0)


def chunk_document_sort_key(
    source_chunk: dict[str, Any],
    section_positions: dict[tuple[int | None, str], int],
) -> tuple:
    chapter_number = source_chunk.get("chapter_number")
    section_title = source_chunk.get("section")
    section_position = section_positions.get((chapter_number, section_title))

    return (
        sortable_number(chapter_number),
        sortable_number(section_position),
        sortable_number(source_chunk.get("page_start")),
        sortable_number(source_chunk.get("page_end")),
        str(source_chunk.get("node_id") or ""),
    )


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []

    for value in values:
        if value in seen:
            continue

        seen.add(value)
        unique_values.append(value)

    return unique_values


def collect_source_references(
    lesson_json: dict[str, Any],
    source_chunk_id_set: set[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    cited_ids: list[str] = []
    invalid_references: list[dict[str, Any]] = []

    for section_key, id_field in SOURCE_REFERENCE_SECTIONS:
        items = lesson_json.get(section_key, [])

        if not isinstance(items, list):
            continue

        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue

            source_chunk_ids = item.get(id_field)

            if source_chunk_ids is None:
                continue

            if not isinstance(source_chunk_ids, list):
                invalid_references.append(
                    {
                        "section": section_key,
                        "index": position,
                        "source_chunk_id": source_chunk_ids,
                        "reason": f"{id_field} is not a list",
                    }
                )
                continue

            for source_chunk_id in source_chunk_ids:
                if not isinstance(source_chunk_id, str):
                    invalid_references.append(
                        {
                            "section": section_key,
                            "index": position,
                            "source_chunk_id": source_chunk_id,
                            "reason": "source_chunk_id is not a string",
                        }
                    )
                    continue

                if source_chunk_id not in source_chunk_id_set:
                    invalid_references.append(
                        {
                            "section": section_key,
                            "index": position,
                            "source_chunk_id": source_chunk_id,
                            "reason": "source_chunk_id is not in source_chunks",
                        }
                    )
                    continue

                cited_ids.append(source_chunk_id)

    return unique_preserve_order(cited_ids), invalid_references


def is_front_matter_request(source: dict[str, Any]) -> bool:
    filters = source.get("filters")

    if isinstance(filters, dict) and filters.get("is_front_matter") is True:
        return True

    return False


def normalize_title(value: Any) -> str:
    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value).strip()).lower()


def preview_shows_section_heading(
    preview: str,
    requested_section: str | None,
    chunk_section: str | None,
) -> bool:
    preview_normalized = normalize_title(preview)

    for title in (requested_section, chunk_section):
        if not title:
            continue

        title_normalized = normalize_title(title)
        if title_normalized and title_normalized in preview_normalized:
            return True

    return False


def build_failure_audit(
    *,
    input_file: str,
    output_json: str,
    output_text: str,
    failures: list[str],
) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "input_file": input_file,
        "output_json": output_json,
        "output_text": output_text,
        "summary": {
            "title": None,
            "requested_section": None,
            "include_descendants": None,
            "ordering": None,
            "retrieved_chunk_count": 0,
            "source_chunk_count": 0,
            "expanded_section_count": 0,
            "covered_section_count": 0,
            "missing_section_count": 0,
            "invalid_source_reference_count": len(
                [failure for failure in failures if "source reference" in failure.lower()]
            ),
            "chapter_boundary_violation_count": 0,
            "out_of_scope_section_count": 0,
            "coverage_mismatch_count": 0,
            "document_order_valid": None,
            "uncited_source_chunk_count": 0,
            "warning_count": 0,
        },
        "checks": {},
        "warnings": [],
        "failures": failures,
    }


def audit_lesson(
    *,
    lesson_json: dict[str, Any],
    input_path: Path,
    output_json_path: Path,
    output_text_path: Path,
    structure_resolution_path: str,
    strict: bool,
) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []

    missing_required_fields = [
        field for field in REQUIRED_TOP_LEVEL_FIELDS if field not in lesson_json
    ]
    if missing_required_fields:
        failures.extend(
            f"Missing required top-level field: {field}" for field in missing_required_fields
        )

    source = lesson_json.get("source")
    source_chunks = lesson_json.get("source_chunks")

    if not isinstance(source, dict):
        failures.append("source must be an object.")
        source = {}
    else:
        missing_source_fields = [
            field for field in REQUIRED_SOURCE_FIELDS if field not in source
        ]
        if missing_source_fields:
            failures.extend(
                f"Missing required source field: {field}" for field in missing_source_fields
            )

    if not isinstance(source_chunks, list):
        failures.append("source_chunks must be a list.")
        source_chunks = []

    duplicate_node_ids: list[str] = []
    missing_preview_node_ids: list[str] = []
    preview_too_long_node_ids: list[str] = []
    node_ids: list[str] = []

    for position, source_chunk in enumerate(source_chunks, start=1):
        if not isinstance(source_chunk, dict):
            failures.append(f"source_chunks[{position}] must be an object.")
            continue

        missing_chunk_fields = [
            field
            for field in REQUIRED_SOURCE_CHUNK_FIELDS
            if field not in source_chunk
        ]
        if missing_chunk_fields:
            failures.extend(
                f"source_chunks[{position}] missing field: {field}"
                for field in missing_chunk_fields
            )

        node_id = source_chunk.get("node_id")
        if isinstance(node_id, str) and node_id:
            node_ids.append(node_id)
        else:
            failures.append(f"source_chunks[{position}].node_id must be a non-empty string.")

        text_preview = source_chunk.get("text_preview")
        if not isinstance(text_preview, str) or not text_preview.strip():
            if isinstance(node_id, str) and node_id:
                missing_preview_node_ids.append(node_id)
        elif len(text_preview) > TEXT_PREVIEW_MAX_CHARS:
            if isinstance(node_id, str) and node_id:
                preview_too_long_node_ids.append(node_id)

    duplicate_node_ids = [
        node_id
        for node_id in unique_preserve_order(node_ids)
        if node_ids.count(node_id) > 1
    ]
    if duplicate_node_ids:
        failures.append(
            "Duplicate source chunk node_id values: " + ", ".join(duplicate_node_ids)
        )

    retrieved_chunk_count = source.get("retrieved_chunk_count")
    source_chunk_count = len(source_chunks)
    if retrieved_chunk_count != source_chunk_count:
        failures.append(
            "source.retrieved_chunk_count does not match len(source_chunks): "
            f"{retrieved_chunk_count} != {source_chunk_count}"
        )

    source_chunk_id_set = set(node_ids)
    cited_source_chunk_ids, invalid_source_references = collect_source_references(
        lesson_json,
        source_chunk_id_set,
    )

    if invalid_source_references:
        failures.append(
            "Invalid source references found: "
            f"{len(invalid_source_references)} reference(s) point to unknown node IDs."
        )

    uncited_source_chunk_ids = [
        node_id for node_id in node_ids if node_id not in cited_source_chunk_ids
    ]
    if uncited_source_chunk_ids:
        warnings.append(
            "Uncited retrieved source chunks: " + ", ".join(uncited_source_chunk_ids)
        )

    chapter_boundary_violations: list[dict[str, Any]] = []
    resolved_chapter_number = source.get("resolved_chapter_number")
    if resolved_chapter_number is not None:
        for source_chunk in source_chunks:
            if not isinstance(source_chunk, dict):
                continue

            if source_chunk.get("chapter_number") != resolved_chapter_number:
                chapter_boundary_violations.append(
                    {
                        "node_id": source_chunk.get("node_id"),
                        "chapter_number": source_chunk.get("chapter_number"),
                        "expected_chapter_number": resolved_chapter_number,
                        "reason": "resolved_chapter_number mismatch",
                    }
                )

    filters = source.get("filters")
    filter_chapter_number = None
    if isinstance(filters, dict):
        filter_chapter_number = filters.get("chapter_number")

    if filter_chapter_number is not None:
        for source_chunk in source_chunks:
            if not isinstance(source_chunk, dict):
                continue

            if source_chunk.get("chapter_number") != filter_chapter_number:
                chapter_boundary_violations.append(
                    {
                        "node_id": source_chunk.get("node_id"),
                        "chapter_number": source_chunk.get("chapter_number"),
                        "expected_chapter_number": filter_chapter_number,
                        "reason": "filters.chapter_number mismatch",
                    }
                )

    if chapter_boundary_violations:
        failures.append(
            "Chapter boundary violations found: "
            f"{len(chapter_boundary_violations)} chunk(s) outside expected chapter."
        )

    expanded_section_titles = source.get("expanded_section_titles") or []
    if not isinstance(expanded_section_titles, list):
        expanded_section_titles = []
        failures.append("source.expanded_section_titles must be a list.")

    expanded_section_title_set = {
        str(title) for title in expanded_section_titles if title is not None
    }
    front_matter_request = is_front_matter_request(source)
    out_of_scope_sections: list[dict[str, Any]] = []

    for source_chunk in source_chunks:
        if not isinstance(source_chunk, dict):
            continue

        chunk_section = source_chunk.get("section")
        if chunk_section is None:
            if front_matter_request:
                continue

            out_of_scope_sections.append(
                {
                    "node_id": source_chunk.get("node_id"),
                    "section": chunk_section,
                    "reason": "null section outside front matter request",
                }
            )
            continue

        if str(chunk_section) not in expanded_section_title_set:
            out_of_scope_sections.append(
                {
                    "node_id": source_chunk.get("node_id"),
                    "section": chunk_section,
                    "reason": "section not in expanded_section_titles",
                }
            )

    requested_section = source.get("requested_section")
    include_descendants = source.get("include_descendants")
    if (
        requested_section
        and include_descendants is False
        and expanded_section_titles
        and expanded_section_titles != [requested_section]
    ):
        warnings.append(
            "Exact section request expected expanded_section_titles to contain only "
            f"requested_section ({requested_section!r}), found: "
            f"{expanded_section_titles!r}"
        )

    if out_of_scope_sections:
        failures.append(
            "Out-of-scope sections found: "
            f"{len(out_of_scope_sections)} chunk(s) outside expanded section titles."
        )

    section_coverage = source.get("section_coverage") or {}
    coverage_mismatches: list[str] = []

    if not isinstance(section_coverage, dict):
        failures.append("source.section_coverage must be an object.")
        section_coverage = {}

    covered_section_titles = section_coverage.get("covered_section_titles") or []
    missing_section_titles = section_coverage.get("missing_section_titles") or []

    if not isinstance(covered_section_titles, list):
        covered_section_titles = []
        failures.append("source.section_coverage.covered_section_titles must be a list.")

    if not isinstance(missing_section_titles, list):
        missing_section_titles = []
        failures.append("source.section_coverage.missing_section_titles must be a list.")

    expanded_section_count = section_coverage.get("expanded_section_count")
    covered_section_count = section_coverage.get("covered_section_count")
    missing_section_count = section_coverage.get("missing_section_count")

    if expanded_section_count != len(expanded_section_titles):
        coverage_mismatches.append(
            "expanded_section_count does not match len(expanded_section_titles): "
            f"{expanded_section_count} != {len(expanded_section_titles)}"
        )

    for title in covered_section_titles:
        if str(title) not in expanded_section_title_set:
            coverage_mismatches.append(
                f"covered_section_titles contains out-of-scope title: {title!r}"
            )

    for title in missing_section_titles:
        if str(title) not in expanded_section_title_set:
            coverage_mismatches.append(
                f"missing_section_titles contains out-of-scope title: {title!r}"
            )

    if (
        isinstance(covered_section_count, int)
        and isinstance(missing_section_count, int)
        and isinstance(expanded_section_count, int)
        and covered_section_count + missing_section_count != expanded_section_count
    ):
        coverage_mismatches.append(
            "covered_section_count + missing_section_count does not equal "
            f"expanded_section_count: {covered_section_count} + {missing_section_count} "
            f"!= {expanded_section_count}"
        )

    actual_covered_sections = unique_preserve_order(
        [
            str(source_chunk.get("section"))
            for source_chunk in source_chunks
            if isinstance(source_chunk, dict)
            and source_chunk.get("section") in expanded_section_title_set
        ]
    )
    expected_covered_sections = [
        str(title) for title in covered_section_titles if title is not None
    ]

    if set(actual_covered_sections) != set(expected_covered_sections):
        coverage_mismatches.append(
            "Actual sections in source_chunks do not match covered_section_titles: "
            f"actual={actual_covered_sections!r}, expected={expected_covered_sections!r}"
        )

    if coverage_mismatches:
        failures.extend(
            f"Section coverage mismatch: {mismatch}" for mismatch in coverage_mismatches
        )

    ordering = source.get("ordering")
    document_order_violations: list[dict[str, Any]] = []
    document_order_valid = True
    structure_resolution_warning: str | None = None

    if ordering == "document":
        section_positions: dict[tuple[int | None, str], int] = {}
        chapter_number_for_map = (
            resolved_chapter_number
            if isinstance(resolved_chapter_number, int)
            else filter_chapter_number
            if isinstance(filter_chapter_number, int)
            else None
        )

        try:
            section_positions = build_section_position_map(
                structure_resolution_path,
                chapter_number=chapter_number_for_map,
            )
        except RetrievalOrderingError as error:
            structure_resolution_warning = (
                "Full outline-order audit unavailable; "
                f"falling back to page_start ordering. ({error})"
            )
            warnings.append(structure_resolution_warning)

        expected_order = sorted(
            [
                source_chunk
                for source_chunk in source_chunks
                if isinstance(source_chunk, dict)
            ],
            key=lambda source_chunk: chunk_document_sort_key(
                source_chunk,
                section_positions,
            ),
        )
        actual_order = [
            source_chunk
            for source_chunk in source_chunks
            if isinstance(source_chunk, dict)
        ]

        for position, (actual_chunk, expected_chunk) in enumerate(
            zip(actual_order, expected_order),
            start=1,
        ):
            if actual_chunk.get("node_id") != expected_chunk.get("node_id"):
                document_order_violations.append(
                    {
                        "position": position,
                        "node_id": actual_chunk.get("node_id"),
                        "expected_node_id": expected_chunk.get("node_id"),
                    }
                )

        document_order_valid = not document_order_violations
        if not document_order_valid:
            failures.append(
                "Document ordering violations found when ordering=document: "
                f"{len(document_order_violations)} chunk(s) out of order."
            )
    elif ordering == "semantic":
        page_starts = [
            source_chunk.get("page_start")
            for source_chunk in source_chunks
            if isinstance(source_chunk, dict)
        ]
        if page_starts != sorted(page_starts, key=lambda value: sortable_number(value)):
            warnings.append("Semantic ordering is not page sorted.")

    if missing_preview_node_ids:
        failures.append(
            "Source chunks missing text preview: "
            + ", ".join(missing_preview_node_ids)
        )

    if preview_too_long_node_ids:
        failures.append(
            "Source chunks with text preview too long: "
            + ", ".join(preview_too_long_node_ids)
        )

    boundary_contamination_warnings: list[dict[str, Any]] = []
    if requested_section and source_chunks and ordering == "document" and document_order_valid:
        first_chunk = source_chunks[0]
        if isinstance(first_chunk, dict):
            preview = first_chunk.get("text_preview")
            if isinstance(preview, str) and preview.strip():
                if not preview_shows_section_heading(
                    preview=preview,
                    requested_section=str(requested_section),
                    chunk_section=(
                        str(first_chunk.get("section"))
                        if first_chunk.get("section") is not None
                        else None
                    ),
                ):
                    boundary_contamination_warnings.append(
                        {
                            "type": "first_chunk_preview_does_not_show_section_heading",
                            "node_id": first_chunk.get("node_id"),
                            "section": first_chunk.get("section"),
                            "page_start": first_chunk.get("page_start"),
                            "preview": preview,
                        }
                    )
                    warnings.append(
                        "first_chunk_preview_does_not_show_section_heading: "
                        f"{first_chunk.get('node_id')} | {first_chunk.get('section')} | "
                        f"page {first_chunk.get('page_start')}"
                    )

    hard_failure_count = len(failures)
    warning_count = len(warnings)

    if hard_failure_count:
        status = "FAIL"
    elif strict and warning_count:
        status = "FAIL"
        failures.append("Strict mode enabled and warnings were found.")
    elif warning_count:
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    return {
        "status": status,
        "input_file": str(input_path),
        "output_json": str(output_json_path),
        "output_text": str(output_text_path),
        "summary": {
            "title": lesson_json.get("title"),
            "requested_section": requested_section,
            "include_descendants": include_descendants,
            "ordering": ordering,
            "retrieved_chunk_count": retrieved_chunk_count,
            "source_chunk_count": source_chunk_count,
            "expanded_section_count": expanded_section_count,
            "covered_section_count": covered_section_count,
            "missing_section_count": missing_section_count,
            "invalid_source_reference_count": len(invalid_source_references),
            "chapter_boundary_violation_count": len(chapter_boundary_violations),
            "out_of_scope_section_count": len(out_of_scope_sections),
            "coverage_mismatch_count": len(coverage_mismatches),
            "document_order_valid": document_order_valid if ordering == "document" else None,
            "uncited_source_chunk_count": len(uncited_source_chunk_ids),
            "warning_count": warning_count,
        },
        "checks": {
            "required_fields": {
                "passed": not missing_required_fields,
                "missing": missing_required_fields,
            },
            "source_references": {
                "passed": not invalid_source_references,
                "invalid_source_references": invalid_source_references,
                "cited_source_chunk_ids": cited_source_chunk_ids,
                "uncited_source_chunk_ids": uncited_source_chunk_ids,
            },
            "chapter_boundaries": {
                "passed": not chapter_boundary_violations,
                "violations": chapter_boundary_violations,
            },
            "section_scope": {
                "passed": not out_of_scope_sections,
                "out_of_scope_sections": out_of_scope_sections,
            },
            "section_coverage": {
                "passed": not coverage_mismatches,
                "expanded_section_titles": expanded_section_titles,
                "covered_section_titles": covered_section_titles,
                "missing_section_titles": missing_section_titles,
                "mismatches": coverage_mismatches,
            },
            "ordering": {
                "passed": document_order_valid if ordering == "document" else True,
                "ordering": ordering,
                "document_order_valid": (
                    document_order_valid if ordering == "document" else None
                ),
                "document_order_violations": document_order_violations,
                "structure_resolution_warning": structure_resolution_warning,
            },
            "text_previews": {
                "passed": not missing_preview_node_ids and not preview_too_long_node_ids,
                "missing_preview_node_ids": missing_preview_node_ids,
                "preview_too_long_node_ids": preview_too_long_node_ids,
            },
            "boundary_contamination": {
                "passed": True,
                "warnings": boundary_contamination_warnings,
            },
        },
        "warnings": warnings,
        "failures": failures,
    }


def format_text_report(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    checks = audit.get("checks", {})
    lines = [
        f"SECTION PDF LESSON AUDIT: {audit['status']}",
        "",
        f"Input: {audit['input_file']}",
        f"Title: {summary.get('title')}",
        f"Requested section: {summary.get('requested_section')}",
        f"Include descendants: {summary.get('include_descendants')}",
        f"Ordering: {summary.get('ordering')}",
        "",
        "SUMMARY",
        f"Retrieved chunks: {summary.get('retrieved_chunk_count')}",
        f"Expanded sections: {summary.get('expanded_section_count')}",
        f"Covered sections: {summary.get('covered_section_count')}",
        f"Missing sections: {summary.get('missing_section_count')}",
        f"Invalid source references: {summary.get('invalid_source_reference_count')}",
        f"Chapter boundary violations: {summary.get('chapter_boundary_violation_count')}",
        f"Out-of-scope sections: {summary.get('out_of_scope_section_count')}",
        f"Coverage mismatches: {summary.get('coverage_mismatch_count')}",
        f"Document order valid: {summary.get('document_order_valid')}",
        f"Warnings: {summary.get('warning_count')}",
    ]

    if audit.get("failures"):
        lines.extend(["", "FAILURES"])
        lines.extend(f"- {failure}" for failure in audit["failures"])

    if audit.get("warnings"):
        lines.extend(["", "WARNINGS"])
        lines.extend(f"- {warning}" for warning in audit["warnings"])

    boundary_warnings = checks.get("boundary_contamination", {}).get("warnings", [])
    if boundary_warnings:
        lines.extend(["", "BOUNDARY CONTAMINATION"])
        for warning in boundary_warnings:
            lines.append(
                "- {type}: {node_id} | {section} | page {page_start}".format(
                    type=warning.get("type"),
                    node_id=warning.get("node_id"),
                    section=warning.get("section"),
                    page_start=warning.get("page_start"),
                )
            )

    source_references = checks.get("source_references", {})
    cited_ids = set(source_references.get("cited_source_chunk_ids", []))

    lines.extend(["", "SOURCE CHUNKS"])
    input_path = Path(audit["input_file"])
    if input_path.exists():
        try:
            lesson_json = json.loads(input_path.read_text(encoding="utf-8"))
            source_chunks = lesson_json.get("source_chunks", [])
            if isinstance(source_chunks, list):
                for source_chunk in source_chunks:
                    if not isinstance(source_chunk, dict):
                        continue

                    node_id = source_chunk.get("node_id")
                    cited = "yes" if node_id in cited_ids else "no"
                    lines.append(
                        f"{node_id} | {source_chunk.get('section')} | "
                        f"page {source_chunk.get('page_start')} | cited: {cited}"
                    )
        except (json.JSONDecodeError, OSError):
            lines.append("(Could not load source chunk listing.)")

    return "\n".join(lines) + "\n"


def write_reports(
    audit: dict[str, Any],
    *,
    output_json_path: Path,
    output_text_path: Path,
) -> str:
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_text_path.parent.mkdir(parents=True, exist_ok=True)

    formatted_json = json.dumps(audit, indent=2, ensure_ascii=False)
    output_json_path.write_text(f"{formatted_json}\n", encoding="utf-8")

    text_report = format_text_report(audit)
    output_text_path.write_text(text_report, encoding="utf-8")
    return text_report


def main() -> None:
    args = parse_args()
    input_path = Path(args.lesson_json_path)
    output_json_path, output_text_path = derive_output_paths(input_path)

    if not input_path.exists():
        audit = build_failure_audit(
            input_file=str(input_path),
            output_json=str(output_json_path),
            output_text=str(output_text_path),
            failures=[f"Input file does not exist: {input_path}"],
        )
        print(write_reports(
            audit,
            output_json_path=output_json_path,
            output_text_path=output_text_path,
        ), end="")
        sys.exit(1)

    try:
        lesson_json = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        audit = build_failure_audit(
            input_file=str(input_path),
            output_json=str(output_json_path),
            output_text=str(output_text_path),
            failures=[f"JSON parsing error: {error}"],
        )
        print(write_reports(
            audit,
            output_json_path=output_json_path,
            output_text_path=output_text_path,
        ), end="")
        sys.exit(1)

    if not isinstance(lesson_json, dict):
        audit = build_failure_audit(
            input_file=str(input_path),
            output_json=str(output_json_path),
            output_text=str(output_text_path),
            failures=["Top-level lesson JSON value must be an object."],
        )
        print(write_reports(
            audit,
            output_json_path=output_json_path,
            output_text_path=output_text_path,
        ), end="")
        sys.exit(1)

    audit = audit_lesson(
        lesson_json=lesson_json,
        input_path=input_path,
        output_json_path=output_json_path,
        output_text_path=output_text_path,
        structure_resolution_path=args.structure_resolution,
        strict=args.strict,
    )

    print(write_reports(
        audit,
        output_json_path=output_json_path,
        output_text_path=output_text_path,
    ), end="")

    if audit["status"] == "FAIL":
        sys.exit(1)


if __name__ == "__main__":
    main()
