import argparse
import json
import sys
from pathlib import Path
from typing import Any


AUDIT_JSON_PATH = Path("output/structured_pdf_lesson.audit.json")
AUDIT_TXT_PATH = Path("output/structured_pdf_lesson.audit.txt")

REQUIRED_TOP_LEVEL_FIELDS = [
    "lesson_title",
    "key_ideas",
    "source_chunks",
]
REQUIRED_SOURCE_CHUNK_FIELDS = [
    "node_id",
    "chapter",
    "chapter_number",
    "page_start",
    "page_end",
    "text_preview",
]
REQUIRED_KEY_IDEA_FIELDS = [
    "idea",
    "source_chunk_ids",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit grounding for a generated structured PDF lesson JSON file."
    )
    parser.add_argument(
        "lesson_json_path",
        help="Path to a generated structured PDF lesson JSON file.",
    )
    return parser.parse_args()


def unique_preserve_order(values: list[Any]) -> list[Any]:
    unique_values = []

    for value in values:
        if value not in unique_values:
            unique_values.append(value)

    return unique_values


def sort_values(values: list[Any]) -> list[Any]:
    def sort_key(value: Any) -> tuple[int, Any]:
        if isinstance(value, bool):
            return (2, str(value))

        if isinstance(value, (int, float)):
            return (0, value)

        try:
            return (0, int(str(value)))
        except (TypeError, ValueError):
            return (1, str(value))

    return sorted(values, key=sort_key)


def page_values(source_chunk: dict[str, Any]) -> list[Any]:
    page_start = source_chunk.get("page_start")
    page_end = source_chunk.get("page_end")

    if page_start is None and page_end is None:
        return []

    if page_start == page_end or page_end is None:
        return [page_start]

    if page_start is None:
        return [page_end]

    if isinstance(page_start, int) and isinstance(page_end, int):
        if page_end >= page_start and page_end - page_start <= 100:
            return list(range(page_start, page_end + 1))

    return [f"{page_start}-{page_end}"]


def text_value(value: Any, default: str = "None") -> str:
    if value is None:
        return default

    if isinstance(value, str):
        return value

    return str(value)


def comma_list(values: list[Any]) -> str:
    if not values:
        return "None"

    return ", ".join(text_value(value) for value in values)


def build_failure_report(source_path: Path, error_message: str) -> dict[str, Any]:
    return {
        "source_file": str(source_path),
        "status": "fail",
        "passed": False,
        "lesson_title": None,
        "errors": [error_message],
        "counts": {
            "key_ideas": 0,
            "source_chunks": 0,
            "cited_source_chunks": 0,
            "uncited_source_chunks": 0,
            "key_ideas_missing_sources": 0,
            "invalid_source_references": 0,
            "source_chunks_missing_text_preview": 0,
        },
        "pages_used": [],
        "chapters_used": [],
        "chunk_ids_used": [],
        "cited_source_chunk_ids": [],
        "uncited_source_chunk_ids": [],
        "invalid_source_references": [],
        "key_ideas_missing_sources": [],
        "source_chunks_missing_text_preview": [],
    }


def audit_lesson(source_path: Path, lesson_json: Any) -> dict[str, Any]:
    errors = []

    if not isinstance(lesson_json, dict):
        return build_failure_report(
            source_path=source_path,
            error_message="Lesson JSON must be a top-level object.",
        )

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in lesson_json:
            errors.append(f"Missing top-level field: {field}")

    lesson_title = lesson_json.get("lesson_title")
    key_ideas = lesson_json.get("key_ideas")
    source_chunks = lesson_json.get("source_chunks")

    if not isinstance(source_chunks, list):
        errors.append("source_chunks must be a list.")
        source_chunks = []

    if not isinstance(key_ideas, list):
        errors.append("key_ideas must be a list.")
        key_ideas = []

    source_chunk_ids = []
    source_chunks_missing_text_preview = []

    for position, source_chunk in enumerate(source_chunks, start=1):
        if not isinstance(source_chunk, dict):
            errors.append(f"source_chunks[{position}] must be an object.")
            continue

        for field in REQUIRED_SOURCE_CHUNK_FIELDS:
            if field not in source_chunk:
                errors.append(f"source_chunks[{position}] is missing field: {field}")

        node_id = source_chunk.get("node_id")
        if isinstance(node_id, str) and node_id.strip():
            source_chunk_ids.append(node_id)
        else:
            errors.append(f"source_chunks[{position}].node_id must be a non-empty string.")

        text_preview = source_chunk.get("text_preview")
        if not isinstance(text_preview, str) or not text_preview.strip():
            source_chunks_missing_text_preview.append(
                text_value(node_id, default=f"source_chunks[{position}]")
            )

    duplicate_source_chunk_ids = [
        source_chunk_id
        for source_chunk_id in unique_preserve_order(source_chunk_ids)
        if source_chunk_ids.count(source_chunk_id) > 1
    ]
    if duplicate_source_chunk_ids:
        errors.append(
            "Duplicate source chunk IDs found: "
            f"{comma_list(duplicate_source_chunk_ids)}"
        )

    source_chunk_id_set = set(source_chunk_ids)
    cited_source_chunk_ids = []
    invalid_source_references = []
    key_ideas_missing_sources = []

    for position, key_idea in enumerate(key_ideas, start=1):
        if not isinstance(key_idea, dict):
            errors.append(f"key_ideas[{position}] must be an object.")
            key_ideas_missing_sources.append(
                {"key_idea_index": position, "idea": None}
            )
            continue

        for field in REQUIRED_KEY_IDEA_FIELDS:
            if field not in key_idea:
                errors.append(f"key_ideas[{position}] is missing field: {field}")

        idea = key_idea.get("idea")
        source_chunk_ids_for_idea = key_idea.get("source_chunk_ids")

        if not isinstance(source_chunk_ids_for_idea, list):
            errors.append(f"key_ideas[{position}].source_chunk_ids must be a list.")
            key_ideas_missing_sources.append(
                {
                    "key_idea_index": position,
                    "idea": idea if isinstance(idea, str) else None,
                }
            )
            continue

        if not source_chunk_ids_for_idea:
            key_ideas_missing_sources.append(
                {
                    "key_idea_index": position,
                    "idea": idea if isinstance(idea, str) else None,
                }
            )

        for source_chunk_id in source_chunk_ids_for_idea:
            if not isinstance(source_chunk_id, str):
                invalid_source_references.append(
                    {
                        "key_idea_index": position,
                        "source_chunk_id": source_chunk_id,
                        "reason": "source_chunk_id is not a string",
                    }
                )
                continue

            if source_chunk_id not in source_chunk_id_set:
                invalid_source_references.append(
                    {
                        "key_idea_index": position,
                        "source_chunk_id": source_chunk_id,
                        "reason": "source_chunk_id is not in source_chunks",
                    }
                )
                continue

            cited_source_chunk_ids.append(source_chunk_id)

    cited_source_chunk_ids = unique_preserve_order(cited_source_chunk_ids)
    uncited_source_chunk_ids = [
        source_chunk_id
        for source_chunk_id in source_chunk_ids
        if source_chunk_id not in cited_source_chunk_ids
    ]

    pages_used = sort_values(
        unique_preserve_order(
            [
                page
                for source_chunk in source_chunks
                if isinstance(source_chunk, dict)
                for page in page_values(source_chunk)
                if page is not None
            ]
        )
    )
    chapters_used = unique_preserve_order(
        [
            source_chunk.get("chapter")
            for source_chunk in source_chunks
            if isinstance(source_chunk, dict) and source_chunk.get("chapter") is not None
        ]
    )

    passed = (
        not errors
        and not invalid_source_references
        and not key_ideas_missing_sources
        and not source_chunks_missing_text_preview
    )

    return {
        "source_file": str(source_path),
        "status": "pass" if passed else "fail",
        "passed": passed,
        "lesson_title": lesson_title,
        "errors": errors,
        "counts": {
            "key_ideas": len(key_ideas),
            "source_chunks": len(source_chunks),
            "cited_source_chunks": len(cited_source_chunk_ids),
            "uncited_source_chunks": len(uncited_source_chunk_ids),
            "key_ideas_missing_sources": len(key_ideas_missing_sources),
            "invalid_source_references": len(invalid_source_references),
            "source_chunks_missing_text_preview": len(
                source_chunks_missing_text_preview
            ),
        },
        "pages_used": pages_used,
        "chapters_used": chapters_used,
        "chunk_ids_used": source_chunk_ids,
        "cited_source_chunk_ids": cited_source_chunk_ids,
        "uncited_source_chunk_ids": uncited_source_chunk_ids,
        "invalid_source_references": invalid_source_references,
        "key_ideas_missing_sources": key_ideas_missing_sources,
        "source_chunks_missing_text_preview": source_chunks_missing_text_preview,
    }


def format_text_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        f"GROUNDING AUDIT: {report['status'].upper()}",
        "",
        f"Lesson: {text_value(report.get('lesson_title'), default='Unknown')}",
        f"Key ideas: {counts['key_ideas']}",
        f"Source chunks: {counts['source_chunks']}",
        f"Cited source chunks: {counts['cited_source_chunks']}",
        f"Uncited source chunks: {counts['uncited_source_chunks']}",
        f"Invalid source references: {counts['invalid_source_references']}",
        f"Key ideas missing sources: {counts['key_ideas_missing_sources']}",
        (
            "Source chunks missing text preview: "
            f"{counts['source_chunks_missing_text_preview']}"
        ),
        f"Pages used: {comma_list(report['pages_used'])}",
        f"Chapters used: {comma_list(report['chapters_used'])}",
        f"Chunk IDs used: {comma_list(report['chunk_ids_used'])}",
    ]

    if report["uncited_source_chunk_ids"]:
        lines.extend(
            [
                f"Uncited chunk IDs: {comma_list(report['uncited_source_chunk_ids'])}",
            ]
        )

    if report["cited_source_chunk_ids"]:
        lines.extend(
            [
                f"Cited chunk IDs: {comma_list(report['cited_source_chunk_ids'])}",
            ]
        )

    if report["errors"]:
        lines.extend(["", "ERRORS"])
        lines.extend(f"- {error}" for error in report["errors"])

    if report["invalid_source_references"]:
        lines.extend(["", "INVALID SOURCE REFERENCES"])
        for invalid_reference in report["invalid_source_references"]:
            lines.append(
                "- key_ideas[{key_idea_index}] references {source_chunk_id}: "
                "{reason}".format(**invalid_reference)
            )

    if report["key_ideas_missing_sources"]:
        lines.extend(["", "KEY IDEAS MISSING SOURCES"])
        for missing_source in report["key_ideas_missing_sources"]:
            lines.append(
                "- key_ideas[{key_idea_index}]: {idea}".format(
                    key_idea_index=missing_source["key_idea_index"],
                    idea=text_value(missing_source.get("idea"), default="No idea text"),
                )
            )

    if report["source_chunks_missing_text_preview"]:
        lines.extend(["", "SOURCE CHUNKS MISSING TEXT PREVIEW"])
        lines.extend(
            f"- {source_chunk_id}"
            for source_chunk_id in report["source_chunks_missing_text_preview"]
        )

    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any]) -> str:
    AUDIT_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    formatted_json = json.dumps(report, indent=2, ensure_ascii=False)
    AUDIT_JSON_PATH.write_text(f"{formatted_json}\n", encoding="utf-8")

    text_report = format_text_report(report)
    AUDIT_TXT_PATH.write_text(text_report, encoding="utf-8")
    return text_report


def main() -> None:
    args = parse_args()
    lesson_json_path = Path(args.lesson_json_path)

    if not lesson_json_path.exists():
        report = build_failure_report(
            source_path=lesson_json_path,
            error_message=f"Generated lesson JSON file does not exist: {lesson_json_path}",
        )
        print(write_reports(report), end="")
        sys.exit(1)

    try:
        lesson_json = json.loads(lesson_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        report = build_failure_report(
            source_path=lesson_json_path,
            error_message=f"JSON parsing error: {error}",
        )
        print(write_reports(report), end="")
        sys.exit(1)

    report = audit_lesson(source_path=lesson_json_path, lesson_json=lesson_json)
    print(write_reports(report), end="")
    print(f"\nSaved JSON audit report to: {AUDIT_JSON_PATH}")
    print(f"Saved text audit report to: {AUDIT_TXT_PATH}")

    if not report["passed"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
