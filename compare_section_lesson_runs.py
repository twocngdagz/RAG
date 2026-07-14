import argparse
import json
import sys
from pathlib import Path
from typing import Any


SOURCE_COMPARE_FIELDS = [
    "index_id",
    "storage_dir",
    "query",
    "filters",
    "ordering",
    "requested_section",
    "include_descendants",
    "resolved_chapter_number",
    "expanded_section_titles",
    "retrieved_chunk_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare an old section PDF lesson run against a clean-index lesson run."
        )
    )
    parser.add_argument(
        "--old-lesson",
        required=True,
        help="Path to the old-index generated lesson JSON.",
    )
    parser.add_argument(
        "--clean-lesson",
        required=True,
        help="Path to the clean-index generated lesson JSON.",
    )
    parser.add_argument(
        "--old-audit",
        help="Optional path to the old lesson audit JSON.",
    )
    parser.add_argument(
        "--clean-audit",
        help="Optional path to the clean lesson audit JSON.",
    )
    parser.add_argument(
        "--output",
        help="Path for the comparison JSON report.",
    )
    parser.add_argument(
        "--report",
        help="Path for the comparison text report.",
    )
    return parser.parse_args()


def derive_audit_path(lesson_path: Path) -> Path:
    name = lesson_path.name
    if name.endswith(".generated.json"):
        stem = name[: -len(".generated.json")]
        return lesson_path.with_name(f"{stem}.audit.json")
    return lesson_path.with_suffix(".audit.json")


def derive_comparison_paths(clean_lesson_path: Path) -> tuple[Path, Path]:
    name = clean_lesson_path.name
    if name.endswith(".generated.json"):
        stem = name[: -len(".generated.json")]
        return (
            clean_lesson_path.with_name(f"{stem}.comparison.json"),
            clean_lesson_path.with_name(f"{stem}.comparison.txt"),
        )
    return (
        clean_lesson_path.with_suffix(".comparison.json"),
        clean_lesson_path.with_suffix(".comparison.txt"),
    )


def load_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    return data


def preview_start(text: Any, max_chars: int = 80) -> str | None:
    if not isinstance(text, str):
        return None

    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact

    return compact[: max_chars - 3] + "..."


def starts_with_requested_section(preview: Any, requested_section: Any) -> bool | None:
    if not isinstance(preview, str) or not isinstance(requested_section, str):
        return None

    if not requested_section.strip():
        return None

    return preview.lstrip().startswith(requested_section)


def source_chunk_map(lesson: dict[str, Any]) -> dict[str, dict[str, Any]]:
    chunks = lesson.get("source_chunks")
    if not isinstance(chunks, list):
        return {}

    mapped: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        node_id = chunk.get("node_id")
        if isinstance(node_id, str) and node_id:
            mapped[node_id] = chunk

    return mapped


def source_chunk_ids(lesson: dict[str, Any]) -> list[str]:
    chunks = lesson.get("source_chunks")
    if not isinstance(chunks, list):
        return []

    ids: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        node_id = chunk.get("node_id")
        if isinstance(node_id, str) and node_id:
            ids.append(node_id)

    return ids


def has_boundary_warning(audit: dict[str, Any] | None) -> bool:
    if not isinstance(audit, dict):
        return False

    warnings = audit.get("warnings") or []
    if isinstance(warnings, list):
        for warning in warnings:
            if (
                isinstance(warning, str)
                and "first_chunk_preview_does_not_show_section_heading" in warning
            ):
                return True

    checks = audit.get("checks")
    if isinstance(checks, dict):
        boundary = checks.get("boundary_contamination")
        if isinstance(boundary, dict):
            boundary_warnings = boundary.get("warnings") or []
            if isinstance(boundary_warnings, list) and boundary_warnings:
                return True

    return False


def warning_count(audit: dict[str, Any] | None) -> int | None:
    if not isinstance(audit, dict):
        return None

    summary = audit.get("summary")
    if isinstance(summary, dict) and "warning_count" in summary:
        value = summary.get("warning_count")
        if isinstance(value, int):
            return value

    warnings = audit.get("warnings")
    if isinstance(warnings, list):
        return len(warnings)

    return None


def audit_failures(audit: dict[str, Any] | None) -> list[Any]:
    if not isinstance(audit, dict):
        return []

    failures = audit.get("failures")
    if isinstance(failures, list):
        return failures

    return []


def audit_status(audit: dict[str, Any] | None) -> str | None:
    if not isinstance(audit, dict):
        return None

    status = audit.get("status")
    return status if isinstance(status, str) else None


def compare_source_metadata(
    old_source: dict[str, Any],
    clean_source: dict[str, Any],
) -> dict[str, Any]:
    comparison: dict[str, Any] = {}

    for field in SOURCE_COMPARE_FIELDS:
        old_value = old_source.get(field)
        clean_value = clean_source.get(field)
        comparison[field] = {
            "old": old_value,
            "clean": clean_value,
            "same": old_value == clean_value,
        }

    return comparison


def compare_source_chunks(
    old_lesson: dict[str, Any],
    clean_lesson: dict[str, Any],
    requested_section: Any,
) -> list[dict[str, Any]]:
    old_map = source_chunk_map(old_lesson)
    clean_map = source_chunk_map(clean_lesson)
    ordered_ids = list(
        dict.fromkeys(source_chunk_ids(old_lesson) + source_chunk_ids(clean_lesson))
    )

    rows: list[dict[str, Any]] = []
    for node_id in ordered_ids:
        old_chunk = old_map.get(node_id)
        clean_chunk = clean_map.get(node_id)
        old_preview = old_chunk.get("text_preview") if old_chunk else None
        clean_preview = clean_chunk.get("text_preview") if clean_chunk else None

        rows.append(
            {
                "node_id": node_id,
                "old_section": old_chunk.get("section") if old_chunk else None,
                "clean_section": clean_chunk.get("section") if clean_chunk else None,
                "old_page_start": old_chunk.get("page_start") if old_chunk else None,
                "clean_page_start": (
                    clean_chunk.get("page_start") if clean_chunk else None
                ),
                "old_preview_start": preview_start(old_preview),
                "clean_preview_start": preview_start(clean_preview),
                "preview_changed": old_preview != clean_preview,
                "old_preview_starts_with_requested_section": starts_with_requested_section(
                    old_preview,
                    requested_section,
                ),
                "clean_preview_starts_with_requested_section": starts_with_requested_section(
                    clean_preview,
                    requested_section,
                ),
            }
        )

    return rows


def determine_status(
    *,
    inconclusive: bool,
    clean_has_no_failures: bool,
    warning_count_reduced: bool,
    first_chunk_preview_improved: bool,
    old_warning_count_value: int | None,
    clean_warning_count_value: int | None,
) -> str:
    if inconclusive:
        return "INCONCLUSIVE"

    if not clean_has_no_failures:
        return "REGRESSED"

    if (
        old_warning_count_value is not None
        and clean_warning_count_value is not None
        and clean_warning_count_value > old_warning_count_value
    ):
        return "REGRESSED"

    if warning_count_reduced or first_chunk_preview_improved:
        return "IMPROVED"

    return "SAME_PASS"


def build_comparison(
    *,
    old_lesson_path: Path,
    clean_lesson_path: Path,
    old_audit_path: Path,
    clean_audit_path: Path,
    output_json_path: Path,
    output_text_path: Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    failures: list[str] = []

    old_lesson = load_json_object(old_lesson_path)
    clean_lesson = load_json_object(clean_lesson_path)

    if old_lesson is None:
        failures.append(f"Old lesson JSON missing or invalid: {old_lesson_path}")
    if clean_lesson is None:
        failures.append(f"Clean lesson JSON missing or invalid: {clean_lesson_path}")

    old_audit = load_json_object(old_audit_path)
    clean_audit = load_json_object(clean_audit_path)

    if old_audit is None:
        warnings.append(f"Old audit JSON missing or invalid: {old_audit_path}")
    if clean_audit is None:
        warnings.append(f"Clean audit JSON missing or invalid: {clean_audit_path}")

    if old_lesson is None or clean_lesson is None:
        return {
            "status": "INCONCLUSIVE",
            "old_lesson": str(old_lesson_path),
            "clean_lesson": str(clean_lesson_path),
            "old_audit": str(old_audit_path),
            "clean_audit": str(clean_audit_path),
            "output_json": str(output_json_path),
            "output_text": str(output_text_path),
            "summary": {},
            "source_metadata_comparison": {},
            "source_chunk_ids": {},
            "source_chunk_comparison": [],
            "audit_comparison": {},
            "improvements": {},
            "warnings": warnings,
            "failures": failures,
        }

    old_source = old_lesson.get("source")
    clean_source = clean_lesson.get("source")
    if not isinstance(old_source, dict):
        old_source = {}
        failures.append("Old lesson is missing a source object.")
    if not isinstance(clean_source, dict):
        clean_source = {}
        failures.append("Clean lesson is missing a source object.")

    requested_section = clean_source.get("requested_section")
    if requested_section is None:
        requested_section = old_source.get("requested_section")

    old_ids = source_chunk_ids(old_lesson)
    clean_ids = source_chunk_ids(clean_lesson)
    old_id_set = set(old_ids)
    clean_id_set = set(clean_ids)

    source_metadata_comparison = compare_source_metadata(old_source, clean_source)
    source_chunk_comparison = compare_source_chunks(
        old_lesson,
        clean_lesson,
        requested_section,
    )

    old_status = audit_status(old_audit)
    clean_status = audit_status(clean_audit)
    old_warning_count_value = warning_count(old_audit)
    clean_warning_count_value = warning_count(clean_audit)
    old_failures = audit_failures(old_audit)
    clean_failures = audit_failures(clean_audit)

    old_has_boundary_warning = has_boundary_warning(old_audit)
    clean_has_boundary_warning = has_boundary_warning(clean_audit)
    boundary_warning_removed = old_has_boundary_warning and not clean_has_boundary_warning

    warning_count_reduced = (
        old_warning_count_value is not None
        and clean_warning_count_value is not None
        and clean_warning_count_value < old_warning_count_value
    )

    first_old_chunk = None
    first_clean_chunk = None
    old_chunks = old_lesson.get("source_chunks")
    clean_chunks = clean_lesson.get("source_chunks")
    if isinstance(old_chunks, list) and old_chunks and isinstance(old_chunks[0], dict):
        first_old_chunk = old_chunks[0]
    if (
        isinstance(clean_chunks, list)
        and clean_chunks
        and isinstance(clean_chunks[0], dict)
    ):
        first_clean_chunk = clean_chunks[0]

    old_first_preview = (
        first_old_chunk.get("text_preview") if first_old_chunk else None
    )
    clean_first_preview = (
        first_clean_chunk.get("text_preview") if first_clean_chunk else None
    )
    old_first_starts = starts_with_requested_section(
        old_first_preview,
        requested_section,
    )
    clean_first_starts = starts_with_requested_section(
        clean_first_preview,
        requested_section,
    )
    first_chunk_preview_improved = bool(
        clean_first_starts is True and old_first_starts is False
    )

    clean_has_no_failures = clean_status in {"PASS", "PASS_WITH_WARNINGS"} and not clean_failures
    clean_audit_passed = clean_status == "PASS" and not clean_failures

    inconclusive = bool(failures) or old_audit is None or clean_audit is None

    status = determine_status(
        inconclusive=inconclusive,
        clean_has_no_failures=clean_has_no_failures,
        warning_count_reduced=warning_count_reduced,
        first_chunk_preview_improved=first_chunk_preview_improved,
        old_warning_count_value=old_warning_count_value,
        clean_warning_count_value=clean_warning_count_value,
    )

    return {
        "status": status,
        "old_lesson": str(old_lesson_path),
        "clean_lesson": str(clean_lesson_path),
        "old_audit": str(old_audit_path),
        "clean_audit": str(clean_audit_path),
        "output_json": str(output_json_path),
        "output_text": str(output_text_path),
        "summary": {
            "requested_section": requested_section,
            "old_index_id": old_source.get("index_id"),
            "clean_index_id": clean_source.get("index_id"),
            "old_storage_dir": old_source.get("storage_dir"),
            "clean_storage_dir": clean_source.get("storage_dir"),
            "same_source_chunk_id_set": old_id_set == clean_id_set,
            "same_source_chunk_id_order": old_ids == clean_ids,
            "old_audit_status": old_status,
            "clean_audit_status": clean_status,
            "old_warning_count": old_warning_count_value,
            "clean_warning_count": clean_warning_count_value,
            "boundary_warning_removed": boundary_warning_removed,
            "warning_count_reduced": warning_count_reduced,
            "clean_audit_passed": clean_audit_passed,
            "clean_has_no_failures": clean_has_no_failures,
            "first_chunk_preview_improved": first_chunk_preview_improved,
        },
        "source_metadata_comparison": source_metadata_comparison,
        "source_chunk_ids": {
            "old_source_chunk_ids": old_ids,
            "clean_source_chunk_ids": clean_ids,
            "same_source_chunk_id_set": old_id_set == clean_id_set,
            "same_source_chunk_id_order": old_ids == clean_ids,
            "added_source_chunk_ids": [
                node_id for node_id in clean_ids if node_id not in old_id_set
            ],
            "removed_source_chunk_ids": [
                node_id for node_id in old_ids if node_id not in clean_id_set
            ],
        },
        "source_chunk_comparison": source_chunk_comparison,
        "audit_comparison": {
            "old_audit_status": old_status,
            "clean_audit_status": clean_status,
            "old_warning_count": old_warning_count_value,
            "clean_warning_count": clean_warning_count_value,
            "old_failures": old_failures,
            "clean_failures": clean_failures,
            "old_warnings": old_audit.get("warnings") if isinstance(old_audit, dict) else [],
            "clean_warnings": (
                clean_audit.get("warnings") if isinstance(clean_audit, dict) else []
            ),
        },
        "improvements": {
            "boundary_warning_removed": boundary_warning_removed,
            "warning_count_reduced": warning_count_reduced,
            "clean_audit_passed": clean_audit_passed,
            "clean_has_no_failures": clean_has_no_failures,
            "first_chunk_preview_improved": first_chunk_preview_improved,
        },
        "warnings": warnings,
        "failures": failures,
    }


def format_text_report(comparison: dict[str, Any]) -> str:
    summary = comparison.get("summary") or {}
    source_chunk_ids_info = comparison.get("source_chunk_ids") or {}
    improvements = comparison.get("improvements") or {}
    audit_comparison = comparison.get("audit_comparison") or {}

    lines = [
        f"SECTION LESSON RUN COMPARISON: {comparison.get('status')}",
        "",
        f"Old lesson: {comparison.get('old_lesson')}",
        f"Clean lesson: {comparison.get('clean_lesson')}",
        f"Old audit: {comparison.get('old_audit')}",
        f"Clean audit: {comparison.get('clean_audit')}",
        "",
        "SUMMARY",
        f"Requested section: {summary.get('requested_section')}",
        f"Old index ID: {summary.get('old_index_id')}",
        f"Clean index ID: {summary.get('clean_index_id')}",
        f"Same source chunk ID set: {summary.get('same_source_chunk_id_set')}",
        f"Same source chunk ID order: {summary.get('same_source_chunk_id_order')}",
        f"Old audit status: {summary.get('old_audit_status')}",
        f"Clean audit status: {summary.get('clean_audit_status')}",
        f"Old warning count: {summary.get('old_warning_count')}",
        f"Clean warning count: {summary.get('clean_warning_count')}",
        f"Boundary warning removed: {summary.get('boundary_warning_removed')}",
        f"First chunk preview improved: {summary.get('first_chunk_preview_improved')}",
        "",
        "SOURCE CHUNK IDS",
        f"Old: {', '.join(source_chunk_ids_info.get('old_source_chunk_ids') or []) or 'None'}",
        f"Clean: {', '.join(source_chunk_ids_info.get('clean_source_chunk_ids') or []) or 'None'}",
        f"Added: {', '.join(source_chunk_ids_info.get('added_source_chunk_ids') or []) or 'None'}",
        f"Removed: {', '.join(source_chunk_ids_info.get('removed_source_chunk_ids') or []) or 'None'}",
        "",
        "IMPROVEMENTS",
        f"boundary_warning_removed: {improvements.get('boundary_warning_removed')}",
        f"warning_count_reduced: {improvements.get('warning_count_reduced')}",
        f"clean_audit_passed: {improvements.get('clean_audit_passed')}",
        f"clean_has_no_failures: {improvements.get('clean_has_no_failures')}",
        f"first_chunk_preview_improved: {improvements.get('first_chunk_preview_improved')}",
        "",
        "FIRST SOURCE CHUNKS",
    ]

    for row in (comparison.get("source_chunk_comparison") or [])[:3]:
        lines.extend(
            [
                f"- {row.get('node_id')}",
                f"  old preview: {row.get('old_preview_start')}",
                f"  clean preview: {row.get('clean_preview_start')}",
                f"  preview changed: {row.get('preview_changed')}",
                (
                    "  clean starts with requested section: "
                    f"{row.get('clean_preview_starts_with_requested_section')}"
                ),
            ]
        )

    if comparison.get("warnings"):
        lines.extend(["", "WARNINGS"])
        lines.extend(f"- {warning}" for warning in comparison["warnings"])

    if comparison.get("failures"):
        lines.extend(["", "FAILURES"])
        lines.extend(f"- {failure}" for failure in comparison["failures"])

    if audit_comparison.get("old_failures") or audit_comparison.get("clean_failures"):
        lines.extend(["", "AUDIT FAILURES"])
        lines.append(f"Old: {audit_comparison.get('old_failures')}")
        lines.append(f"Clean: {audit_comparison.get('clean_failures')}")

    return "\n".join(lines) + "\n"


def write_reports(
    comparison: dict[str, Any],
    *,
    output_json_path: Path,
    output_text_path: Path,
) -> str:
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_text_path.parent.mkdir(parents=True, exist_ok=True)

    output_json_path.write_text(
        json.dumps(comparison, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    text_report = format_text_report(comparison)
    output_text_path.write_text(text_report, encoding="utf-8")
    return text_report


def main() -> None:
    args = parse_args()

    old_lesson_path = Path(args.old_lesson)
    clean_lesson_path = Path(args.clean_lesson)
    old_audit_path = (
        Path(args.old_audit) if args.old_audit else derive_audit_path(old_lesson_path)
    )
    clean_audit_path = (
        Path(args.clean_audit)
        if args.clean_audit
        else derive_audit_path(clean_lesson_path)
    )

    default_json, default_text = derive_comparison_paths(clean_lesson_path)
    output_json_path = Path(args.output) if args.output else default_json
    output_text_path = Path(args.report) if args.report else default_text

    comparison = build_comparison(
        old_lesson_path=old_lesson_path,
        clean_lesson_path=clean_lesson_path,
        old_audit_path=old_audit_path,
        clean_audit_path=clean_audit_path,
        output_json_path=output_json_path,
        output_text_path=output_text_path,
    )

    text_report = write_reports(
        comparison,
        output_json_path=output_json_path,
        output_text_path=output_text_path,
    )
    print(text_report, end="")

    if comparison["status"] in {"REGRESSED", "INCONCLUSIVE"}:
        sys.exit(1)


if __name__ == "__main__":
    main()
