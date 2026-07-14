import argparse
import copy
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pdf_artifact_paths import get_clean_section_artifacts


DEFAULT_TARGET_NODE_IDS = ["sample_chunk_324", "sample_chunk_244"]


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00ad", "")).strip()


def natural_id_key(value: str | None) -> tuple[Any, ...]:
    if not value:
        return ("", 0)
    parts = re.split(r"(\d+)", value)
    key: list[Any] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part)
    return tuple(key)


def output_paths(input_path: Path, output: str | None, report: str | None) -> tuple[Path, Path]:
    artifacts = get_clean_section_artifacts(input_path)

    if output:
        output_path = Path(output)
    else:
        output_path = Path(artifacts["clean_chunks_path"])

    if report:
        report_path = Path(report)
    else:
        report_path = Path(artifacts["clean_report_path"])

    return output_path, report_path


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def selected_sections_by_chapter(structure_resolution: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    selected_outline = structure_resolution.get("selected_outline") or {}
    chapters = selected_outline.get("chapters")
    if not isinstance(chapters, list):
        raise ValueError("structure resolution must contain selected_outline.chapters")

    sections_by_chapter: dict[int, list[dict[str, Any]]] = {}
    for chapter in chapters:
        chapter_number = chapter.get("chapter_number")
        if chapter_number is None:
            continue
        sections = chapter.get("sections") or []
        ordered_sections: list[dict[str, Any]] = []
        for position, section in enumerate(sections):
            title = section.get("section_title")
            if not title:
                continue
            ordered_sections.append(
                {
                    "title": title,
                    "page_start": section.get("page_start"),
                    "level": section.get("level"),
                    "position": position,
                }
            )
        sections_by_chapter[int(chapter_number)] = ordered_sections
    return sections_by_chapter


def section_lookup(
    sections_by_chapter: dict[int, list[dict[str, Any]]],
) -> dict[tuple[int, str, Any], dict[str, Any]]:
    lookup: dict[tuple[int, str, Any], dict[str, Any]] = {}
    for chapter_number, sections in sections_by_chapter.items():
        for index, section in enumerate(sections):
            section_with_neighbors = dict(section)
            section_with_neighbors["previous"] = sections[index - 1] if index > 0 else None
            section_with_neighbors["next"] = sections[index + 1] if index + 1 < len(sections) else None
            key = (chapter_number, normalize_whitespace(section["title"]).casefold(), section.get("page_start"))
            lookup[key] = section_with_neighbors
            fallback_key = (chapter_number, normalize_whitespace(section["title"]).casefold(), None)
            lookup.setdefault(fallback_key, section_with_neighbors)
    return lookup


def get_section_info(
    chunk: dict[str, Any],
    lookup: dict[tuple[int, str, Any], dict[str, Any]],
) -> dict[str, Any] | None:
    chapter_number = chunk.get("chapter_number")
    section = chunk.get("section")
    if chapter_number is None or not section:
        return None

    normalized_section = normalize_whitespace(str(section)).casefold()
    exact_key = (int(chapter_number), normalized_section, chunk.get("section_page_start"))
    fallback_key = (int(chapter_number), normalized_section, None)
    return lookup.get(exact_key) or lookup.get(fallback_key)


def line_spans(text: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    start = 0
    for line in text.splitlines(keepends=True):
        line_end = start + len(line)
        content_end = line_end - (len(line) - len(line.rstrip("\r\n")))
        spans.append((start, content_end, line[: content_end - start]))
        start = line_end
    if text and (not spans or spans[-1][1] < len(text)):
        spans.append((start, len(text), text[start:]))
    return spans


def title_pattern(title: str) -> re.Pattern[str]:
    normalized_title = normalize_whitespace(title)
    tokens = normalized_title.split()
    separator = r"(?:\s+|\u00ad+|-?\s+)"
    pattern = separator.join(re.escape(token) for token in tokens)
    return re.compile(pattern, re.IGNORECASE)


def is_short_or_generic(title: str) -> bool:
    normalized_title = normalize_whitespace(title).casefold()
    generic_titles = {
        "example",
        "examples",
        "note",
        "tip",
        "answer",
        "question",
        "exercise",
        "summary",
        "review",
        "activity",
        "memory",
        "tools",
        "planning",
        "agents",
        "rag",
    }
    return len(normalized_title) <= 12 or normalized_title in generic_titles


def line_heading_start(line_start: int, line_text: str, title: str) -> int | None:
    stripped = line_text.strip()
    if not stripped:
        return None

    normalized_line = normalize_whitespace(stripped)
    normalized_title = normalize_whitespace(title)
    normalized_line_folded = normalized_line.casefold()
    normalized_title_folded = normalized_title.casefold()

    leading = len(line_text) - len(line_text.lstrip())

    if normalized_line_folded == normalized_title_folded:
        return line_start + leading

    if normalized_line_folded.startswith(normalized_title_folded):
        extra = normalized_line[len(normalized_title) :].strip()
        if len(normalized_line) <= max(80, len(normalized_title) + 40):
            if not extra or re.match(r"^[:\-|]", extra):
                return line_start + leading

    if not is_short_or_generic(title) and len(normalized_line) <= max(120, len(normalized_title) + 80):
        match = title_pattern(title).search(stripped)
        if match and match.start() <= 4:
            return line_start + leading + match.start()

    return None


def match_is_heading_like(text: str, start: int, end: int, title: str) -> bool:
    before = text.rfind("\n", 0, start) + 1
    after = text.find("\n", end)
    if after == -1:
        after = len(text)
    line = text[before:after].strip()
    normalized_line = normalize_whitespace(line)
    normalized_title = normalize_whitespace(title)

    if not normalized_line:
        return False

    if normalized_line.casefold() == normalized_title.casefold():
        return True

    if is_short_or_generic(title):
        if normalized_line.casefold().startswith(normalized_title.casefold()):
            return len(normalized_line) <= max(80, len(normalized_title) + 30)
        return False

    if len(normalized_line) <= max(120, len(normalized_title) + 80):
        line_prefix = normalize_whitespace(text[before:start])
        return len(line_prefix) <= 4

    return False


def find_safe_heading(text: str, title: str, *, min_start: int = 0) -> int | None:
    if not text or not title:
        return None

    for line_start, _line_end, line_text in line_spans(text):
        if line_start < min_start:
            continue
        start = line_heading_start(line_start, line_text, title)
        if start is not None:
            return start

    pattern = title_pattern(title)
    for match in pattern.finditer(text):
        if match.start() < min_start:
            continue
        if match_is_heading_like(text, match.start(), match.end(), title):
            return match.start()

    return None


def safe_trim_allowed(
    *,
    original_text: str,
    cleaned_text: str,
    min_cleaned_length: int,
    required_heading: str | None,
) -> tuple[bool, str | None]:
    if not cleaned_text.strip():
        return False, "trim_skipped_empty_text"

    if len(cleaned_text) < min_cleaned_length and len(original_text) > 500:
        return False, "trim_skipped_below_min_cleaned_length"

    if len(original_text) > 0 and len(cleaned_text) < len(original_text) * 0.10:
        if len(cleaned_text) < 300:
            return False, "trim_skipped_removed_more_than_90_percent"
        if required_heading and find_safe_heading(cleaned_text, required_heading, min_start=0) is None:
            return False, "trim_skipped_removed_more_than_90_percent_without_heading"

    return True, None


def first_chunk_ids_by_section(chunks: list[dict[str, Any]]) -> set[str]:
    groups: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        if chunk.get("chapter_number") is None or not chunk.get("section"):
            continue
        groups[(chunk.get("chapter_number"), chunk.get("section"))].append(chunk)

    first_ids: set[str] = set()
    for group_chunks in groups.values():
        ordered = sorted(
            group_chunks,
            key=lambda chunk: (
                chunk.get("page_start") if chunk.get("page_start") is not None else 10**9,
                chunk.get("page_end") if chunk.get("page_end") is not None else 10**9,
                natural_id_key(chunk.get("id")),
            ),
        )
        if ordered:
            first_ids.add(ordered[0]["id"])
    return first_ids


def should_attempt_prefix(chunk: dict[str, Any], first_ids: set[str]) -> bool:
    if not chunk.get("section"):
        return False
    if not chunk.get("text"):
        return False
    if chunk.get("is_front_matter"):
        return False
    if chunk.get("id") in first_ids:
        return True
    return chunk.get("page_start") == chunk.get("section_page_start")


def cleanup_chunk(
    chunk: dict[str, Any],
    section_info: dict[str, Any] | None,
    first_ids: set[str],
    min_cleaned_length: int,
) -> dict[str, Any]:
    cleaned_chunk = copy.deepcopy(chunk)
    original_text = chunk.get("text") or ""
    text = original_text
    warnings: list[str] = []

    cleanup = {
        "applied": False,
        "original_text_length": len(original_text),
        "cleaned_text_length": len(original_text),
        "prefix_trimmed_chars": 0,
        "suffix_trimmed_chars": 0,
        "start_heading": None,
        "start_heading_found": False,
        "end_heading": None,
        "end_heading_found": False,
        "warnings": warnings,
    }

    current_section = chunk.get("section")

    if section_info and should_attempt_prefix(chunk, first_ids):
        start_heading = str(current_section)
        cleanup["start_heading"] = start_heading
        heading_start = find_safe_heading(text, start_heading)
        if heading_start is None:
            warnings.append(f"start_heading_not_found:{start_heading}")
        else:
            cleanup["start_heading_found"] = True
            if heading_start > 0:
                candidate = text[heading_start:]
                allowed, warning = safe_trim_allowed(
                    original_text=text,
                    cleaned_text=candidate,
                    min_cleaned_length=min_cleaned_length,
                    required_heading=start_heading,
                )
                if allowed:
                    cleanup["prefix_trimmed_chars"] = heading_start
                    text = candidate
                elif warning:
                    warnings.append(warning)

    next_section = section_info.get("next") if section_info else None
    if (
        next_section
        and current_section
        and text
        and not chunk.get("is_front_matter")
        and chunk.get("chapter_number") is not None
    ):
        end_heading = next_section.get("title")
        if end_heading:
            cleanup["end_heading"] = end_heading
            next_heading_start = find_safe_heading(text, str(end_heading), min_start=1)
            if next_heading_start is not None:
                candidate = text[:next_heading_start].rstrip()
                allowed, warning = safe_trim_allowed(
                    original_text=text,
                    cleaned_text=candidate,
                    min_cleaned_length=min_cleaned_length,
                    required_heading=str(current_section),
                )
                if allowed:
                    cleanup["end_heading_found"] = True
                    cleanup["suffix_trimmed_chars"] = len(text) - len(candidate)
                    text = candidate
                elif warning:
                    warnings.append(warning)

    cleanup["applied"] = text != original_text
    cleanup["cleaned_text_length"] = len(text)
    cleaned_chunk["text"] = text
    cleaned_chunk["boundary_cleanup"] = cleanup
    return cleaned_chunk


def stats_by_chapter(cleaned_chunks: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    stats: dict[str, Counter[str]] = defaultdict(Counter)
    for chunk in cleaned_chunks:
        chapter = chunk.get("chapter") or "front_matter"
        cleanup = chunk.get("boundary_cleanup") or {}
        if cleanup.get("applied"):
            stats[chapter]["chunks_cleaned"] += 1
        if cleanup.get("prefix_trimmed_chars"):
            stats[chapter]["prefix_trims"] += 1
        if cleanup.get("suffix_trimmed_chars"):
            stats[chapter]["suffix_trims"] += 1
        if cleanup.get("warnings"):
            stats[chapter]["warnings"] += 1
    return stats


def preview(text: str, limit: int = 250) -> str:
    return normalize_whitespace(text)[:limit]


def target_report_lines(
    original_chunks: list[dict[str, Any]],
    cleaned_chunks: list[dict[str, Any]],
    target_node_ids: list[str],
) -> list[str]:
    original_by_id = {chunk.get("id"): chunk for chunk in original_chunks}
    cleaned_by_id = {chunk.get("id"): chunk for chunk in cleaned_chunks}
    lines = ["IMPORTANT TARGET CHECKS"]

    for node_id in target_node_ids:
        before = original_by_id.get(node_id)
        after = cleaned_by_id.get(node_id)
        lines.append("")
        if before is None or after is None:
            lines.append(f"{node_id}: missing")
            continue
        cleanup = after.get("boundary_cleanup") or {}
        lines.extend(
            [
                f"Node ID: {node_id}",
                f"Chapter: {after.get('chapter')}",
                f"Section: {after.get('section')}",
                f"Page start: {after.get('page_start')}",
                f"Original text first 250 chars: {preview(before.get('text') or '')}",
                f"Cleaned text first 250 chars: {preview(after.get('text') or '')}",
                f"Prefix trimmed chars: {cleanup.get('prefix_trimmed_chars')}",
                f"Suffix trimmed chars: {cleanup.get('suffix_trimmed_chars')}",
                f"Warnings: {cleanup.get('warnings')}",
            ]
        )
    return lines


def build_report(
    *,
    original_chunks: list[dict[str, Any]],
    cleaned_chunks: list[dict[str, Any]],
    output_path: Path,
    report_path: Path,
    target_node_ids: list[str],
) -> str:
    chunks_cleaned = [chunk for chunk in cleaned_chunks if chunk["boundary_cleanup"]["applied"]]
    prefix_trims = [chunk for chunk in cleaned_chunks if chunk["boundary_cleanup"]["prefix_trimmed_chars"]]
    suffix_trims = [chunk for chunk in cleaned_chunks if chunk["boundary_cleanup"]["suffix_trimmed_chars"]]
    warning_chunks = [chunk for chunk in cleaned_chunks if chunk["boundary_cleanup"]["warnings"]]
    total_prefix = sum(chunk["boundary_cleanup"]["prefix_trimmed_chars"] for chunk in cleaned_chunks)
    total_suffix = sum(chunk["boundary_cleanup"]["suffix_trimmed_chars"] for chunk in cleaned_chunks)

    lines = [
        "SUMMARY",
        f"Chunks loaded: {len(original_chunks)}",
        f"Chunks written: {len(cleaned_chunks)}",
        f"Chunks cleaned: {len(chunks_cleaned)}",
        f"Chunks unchanged: {len(cleaned_chunks) - len(chunks_cleaned)}",
        f"Prefix trims applied: {len(prefix_trims)}",
        f"Suffix trims applied: {len(suffix_trims)}",
        f"Total prefix chars trimmed: {total_prefix}",
        f"Total suffix chars trimmed: {total_suffix}",
        f"Chunks with warnings: {len(warning_chunks)}",
        f"Output JSON path: {output_path}",
        f"Output TXT path: {report_path}",
        "",
        "CLEANUP BY CHAPTER",
    ]

    chapter_stats = stats_by_chapter(cleaned_chunks)
    for chapter in sorted(chapter_stats, key=lambda value: natural_id_key(value)):
        stats = chapter_stats[chapter]
        lines.extend(
            [
                f"{chapter}:",
                f"  chunks cleaned: {stats['chunks_cleaned']}",
                f"  prefix trims: {stats['prefix_trims']}",
                f"  suffix trims: {stats['suffix_trims']}",
                f"  warnings: {stats['warnings']}",
            ]
        )

    lines.append("")
    lines.extend(target_report_lines(original_chunks, cleaned_chunks, target_node_ids))

    if warning_chunks:
        lines.extend(["", "WARNINGS"])
        for chunk in warning_chunks[:100]:
            cleanup = chunk["boundary_cleanup"]
            lines.append(f"{chunk.get('id')} | {chunk.get('chapter')} | {chunk.get('section')} | {cleanup['warnings']}")

    return "\n".join(lines) + "\n"


def clean_chunks(
    chunks: list[dict[str, Any]],
    structure_resolution: dict[str, Any],
    min_cleaned_length: int,
) -> list[dict[str, Any]]:
    sections = selected_sections_by_chapter(structure_resolution)
    lookup = section_lookup(sections)
    first_ids = first_chunk_ids_by_section(chunks)

    cleaned_chunks: list[dict[str, Any]] = []
    for chunk in chunks:
        section_info = get_section_info(chunk, lookup)
        cleaned_chunks.append(cleanup_chunk(chunk, section_info, first_ids, min_cleaned_length))
    return cleaned_chunks


def unique_targets(values: list[str] | None) -> list[str]:
    targets: list[str] = []
    for value in DEFAULT_TARGET_NODE_IDS + (values or []):
        if value not in targets:
            targets.append(value)
    return targets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create cleaned section-boundary PDF chunks.")
    parser.add_argument("section_chunks_json", help="Path to extracted/sample.section_chunks.json")
    parser.add_argument("structure_resolution_json", help="Path to extracted/sample.structure_resolution.json")
    parser.add_argument("--output", help="Output JSON path")
    parser.add_argument("--report", help="Output text report path")
    parser.add_argument("--dry-run", action="store_true", help="Analyze and report without writing cleaned JSON")
    parser.add_argument("--min-cleaned-length", type=int, default=100)
    parser.add_argument("--target-node-id", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    section_chunks_path = Path(args.section_chunks_json)
    structure_resolution_path = Path(args.structure_resolution_json)

    if not section_chunks_path.exists():
        raise SystemExit(f"Section chunks file not found: {section_chunks_path}")
    if not structure_resolution_path.exists():
        raise SystemExit(f"Structure resolution file not found: {structure_resolution_path}")

    chunks = load_json(section_chunks_path)
    if not isinstance(chunks, list):
        raise SystemExit("Section chunks JSON must be a top-level array.")

    structure_resolution = load_json(structure_resolution_path)
    if not isinstance(structure_resolution, dict):
        raise SystemExit("Structure resolution JSON must be a top-level object.")

    output_path, report_path = output_paths(section_chunks_path, args.output, args.report)
    target_node_ids = unique_targets(args.target_node_id)

    cleaned_chunks = clean_chunks(chunks, structure_resolution, args.min_cleaned_length)
    report = build_report(
        original_chunks=chunks,
        cleaned_chunks=cleaned_chunks,
        output_path=output_path,
        report_path=report_path,
        target_node_ids=target_node_ids,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    if not args.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(cleaned_chunks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    chunks_cleaned = sum(1 for chunk in cleaned_chunks if chunk["boundary_cleanup"]["applied"])
    prefix_trims = sum(1 for chunk in cleaned_chunks if chunk["boundary_cleanup"]["prefix_trimmed_chars"])
    suffix_trims = sum(1 for chunk in cleaned_chunks if chunk["boundary_cleanup"]["suffix_trimmed_chars"])
    total_prefix = sum(chunk["boundary_cleanup"]["prefix_trimmed_chars"] for chunk in cleaned_chunks)
    total_suffix = sum(chunk["boundary_cleanup"]["suffix_trimmed_chars"] for chunk in cleaned_chunks)
    warning_count = sum(1 for chunk in cleaned_chunks if chunk["boundary_cleanup"]["warnings"])

    print("Section boundary cleanup completed.")
    print(f"Chunks loaded: {len(chunks)}")
    print(f"Chunks written: {len(cleaned_chunks)}")
    print(f"Chunks cleaned: {chunks_cleaned}")
    print(f"Chunks unchanged: {len(cleaned_chunks) - chunks_cleaned}")
    print(f"Prefix trims applied: {prefix_trims}")
    print(f"Suffix trims applied: {suffix_trims}")
    print(f"Total prefix chars trimmed: {total_prefix}")
    print(f"Total suffix chars trimmed: {total_suffix}")
    print(f"Chunks with warnings: {warning_count}")
    if args.dry_run:
        print("Dry run: cleaned JSON was not written.")
    print(f"Output JSON: {output_path}")
    print(f"Output TXT: {report_path}")


if __name__ == "__main__":
    main()
