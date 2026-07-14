import argparse
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")
ROMAN_NUMERAL_PATTERN = r"[ivxlcdm]+"
NON_CHAPTER_TITLES = {
    "acknowledgments",
    "appendix",
    "appendices",
    "bibliography",
    "epilogue",
    "glossary",
    "index",
    "preface",
    "references",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve the best available document structure from existing PDF inspection signals."
    )
    parser.add_argument("chunks_path", help="Path to the chunks JSON file.")
    parser.add_argument("--body-outline", help="Path to a body outline JSON report.")
    parser.add_argument(
        "--section-candidates",
        help="Path to a section/topic candidates JSON report.",
    )
    parser.add_argument("--section-outline", help="Path to a section outline JSON report.")
    parser.add_argument(
        "--strict-section-outline",
        help="Path to a strict section outline JSON report.",
    )
    return parser.parse_args()


def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Required file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"Path is not a file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_optional_report(path_value: str | None) -> tuple[dict | None, str | None]:
    if not path_value:
        return None, None

    path = Path(path_value)
    report = load_json_file(path)
    if not isinstance(report, dict):
        raise SystemExit(f"Optional report must contain a top-level object: {path}")

    return report, str(path)


def validate_chunks(chunks: Any) -> list[dict]:
    if not isinstance(chunks, list):
        raise SystemExit("Chunks JSON must contain a top-level array.")

    for position, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            raise SystemExit(f"Chunk #{position} must be an object.")

    return chunks


def output_stem(chunks_path: Path) -> str:
    for suffix in [
        ".chapter_chunks.json",
        ".chunks.json",
        ".json",
    ]:
        if chunks_path.name.endswith(suffix):
            return chunks_path.name[: -len(suffix)]

    return chunks_path.stem


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def clean_toc_line(line: str) -> str:
    line = normalize_text(line)
    line = re.sub(r"(?:\.\s*){2,}", " ", line)
    return normalize_text(line)


def is_toc_header_or_footer(line: str) -> bool:
    normalized_line = normalize_text(line)
    lower_line = normalized_line.lower()

    if lower_line in {"table of contents", "contents"}:
        return True

    if re.fullmatch(ROMAN_NUMERAL_PATTERN, lower_line):
        return True

    return bool(
        re.fullmatch(
            rf"(?:{ROMAN_NUMERAL_PATTERN}|\d+)\s*\|\s*table of contents",
            lower_line,
        )
        or re.fullmatch(
            rf"table of contents\s*\|\s*(?:{ROMAN_NUMERAL_PATTERN}|\d+)",
            lower_line,
        )
    )


def line_has_trailing_page(line: str) -> bool:
    cleaned_line = clean_toc_line(line)
    return bool(
        re.match(
            rf"^.+\s+(?:\d{{1,4}}|{ROMAN_NUMERAL_PATTERN})$",
            cleaned_line,
            flags=re.IGNORECASE,
        )
    )


def extract_trailing_page(line: str) -> tuple[str, int | str | None]:
    cleaned_line = clean_toc_line(line)
    match = re.match(
        rf"^(?P<title>.+?)\s+(?P<page>\d{{1,4}}|{ROMAN_NUMERAL_PATTERN})$",
        cleaned_line,
        flags=re.IGNORECASE,
    )
    if not match:
        return cleaned_line, None

    title = normalize_text(match.group("title"))
    page_text = match.group("page")
    if page_text.isdigit():
        return title, int(page_text)

    return title, page_text.lower()


def is_non_chapter_title(title: str) -> bool:
    normalized_title = title.strip(" .:-").casefold()
    return normalized_title in NON_CHAPTER_TITLES


def parse_toc_entry(line: str) -> dict | None:
    title_with_number, page = extract_trailing_page(line)
    if page is None:
        return None

    chapter_match = re.match(
        r"^(?P<chapter_number>\d{1,3})\.\s+(?P<title>.+)$",
        title_with_number,
    )
    if chapter_match and isinstance(page, int):
        title = normalize_text(chapter_match.group("title"))
        return {
            "entry_type": "chapter",
            "chapter_number": int(chapter_match.group("chapter_number")),
            "chapter_title": title,
            "page_start": page,
        }

    return {
        "entry_type": "section",
        "section_title": title_with_number,
        "page_start": page,
    }


def toc_candidate_chunk_indices(chunks: list[dict]) -> list[int]:
    start_indices = [
        index
        for index, chunk in enumerate(chunks)
        if "table of contents" in str(chunk.get("text") or "").lower()
    ]
    if not start_indices:
        return []

    start_index = start_indices[0]
    indices = []
    empty_or_non_toc_streak = 0

    for index in range(start_index, len(chunks)):
        text = str(chunks[index].get("text") or "")
        lines = [line for line in text.splitlines() if normalize_text(line)]
        toc_like_line_count = sum(
            1
            for line in lines
            if line_has_trailing_page(line) or "table of contents" in line.lower()
        )

        if toc_like_line_count:
            indices.append(index)
            empty_or_non_toc_streak = 0
            continue

        empty_or_non_toc_streak += 1
        if empty_or_non_toc_streak >= 1:
            break

    return indices


def extract_toc_outline(chunks: list[dict]) -> dict:
    chunk_indices = toc_candidate_chunk_indices(chunks)
    chapters = []
    non_chapter_entries = []
    current_chapter: dict | None = None

    for chunk_index in chunk_indices:
        chunk = chunks[chunk_index]
        for raw_line in str(chunk.get("text") or "").splitlines():
            line = normalize_text(raw_line)
            if not line or is_toc_header_or_footer(line):
                continue

            entry = parse_toc_entry(line)
            if entry is None:
                continue

            if entry["entry_type"] == "chapter":
                current_chapter = {
                    "chapter_number": entry["chapter_number"],
                    "chapter_title": entry["chapter_title"],
                    "page_start": entry["page_start"],
                    "sections": [],
                }
                chapters.append(current_chapter)
                continue

            section_title = entry["section_title"]
            if is_non_chapter_title(section_title):
                non_chapter_entries.append(
                    {
                        "title": section_title,
                        "page_start": entry["page_start"],
                    }
                )
                continue

            if current_chapter is None:
                non_chapter_entries.append(
                    {
                        "title": section_title,
                        "page_start": entry["page_start"],
                    }
                )
                continue

            if not isinstance(entry["page_start"], int):
                non_chapter_entries.append(
                    {
                        "title": section_title,
                        "page_start": entry["page_start"],
                    }
                )
                continue

            current_chapter["sections"].append(
                {
                    "section_title": section_title,
                    "page_start": entry["page_start"],
                    "level": 1,
                }
            )

    section_count = sum(len(chapter["sections"]) for chapter in chapters)
    has_page_numbers = bool(
        chapters
        and all(isinstance(chapter.get("page_start"), int) for chapter in chapters)
    )

    return {
        "available": bool(chapters or non_chapter_entries),
        "chunk_indices": chunk_indices,
        "chapter_count": len(chapters),
        "section_count": section_count,
        "has_page_numbers": has_page_numbers,
        "outline": {
            "chapters": chapters,
            "non_chapter_entries": non_chapter_entries,
        },
    }


def confidence_rank(confidence: str) -> int:
    return {
        "low": 1,
        "medium": 2,
        "high": 3,
    }.get(confidence, 0)


def score_toc(toc: dict) -> dict:
    if not toc["available"]:
        return {
            "available": False,
            "chapter_count": 0,
            "section_count": 0,
            "has_page_numbers": False,
            "noise_score": 1.0,
            "confidence": "low",
            "reason": "No TOC-like structure found in chunks.",
        }

    chapter_count = toc["chapter_count"]
    section_count = toc["section_count"]
    has_page_numbers = toc["has_page_numbers"]
    noise_score = 0.1 if chapter_count >= 5 and section_count >= 20 else 0.35

    if chapter_count >= 5 and section_count >= 20 and has_page_numbers:
        confidence = "high"
        reason = "TOC-like structure found with chapter and section page numbers."
    elif chapter_count >= 3 and has_page_numbers:
        confidence = "medium"
        reason = "TOC-like structure found, but section coverage is limited."
    else:
        confidence = "low"
        reason = "TOC-like entries found, but structure is sparse."

    return {
        "available": True,
        "chapter_count": chapter_count,
        "section_count": section_count,
        "has_page_numbers": has_page_numbers,
        "noise_score": noise_score,
        "confidence": confidence,
        "reason": reason,
    }


def score_body_outline(report: dict | None) -> dict:
    if not report:
        return unavailable_source("Body outline file was not provided.")

    body_outline = report.get("body_outline")
    if not isinstance(body_outline, list):
        return unavailable_source("Body outline report does not contain body_outline.")

    chapter_count = len(
        [
            item
            for item in body_outline
            if re.search(r"\bCHAPTER\s+\d+\b", str(item.get("heading") or ""))
        ]
    )
    has_page_numbers = any(item.get("page_start") is not None for item in body_outline)
    noise_score = 0.2 if chapter_count >= 5 else 0.5
    confidence = "high" if chapter_count >= 5 and noise_score <= 0.2 else "medium"
    reason = (
        "Body outline contains clean chapter markers."
        if confidence == "high"
        else "Body outline contains chapter markers only."
    )

    return {
        "available": True,
        "chapter_count": chapter_count,
        "section_count": 0,
        "has_page_numbers": has_page_numbers,
        "noise_score": noise_score,
        "confidence": confidence,
        "reason": reason,
    }


def count_chapters_from_grouped_report(report: dict) -> int:
    chapters = report.get("chapters")
    if not isinstance(chapters, list):
        return 0

    return len(
        [
            chapter
            for chapter in chapters
            if isinstance(chapter, dict)
            and (
                chapter.get("candidate_count")
                or chapter.get("outline_count")
                or chapter.get("chapter")
            )
        ]
    )


def has_pages_in_grouped_report(report: dict, nested_key: str) -> bool:
    chapters = report.get("chapters")
    if not isinstance(chapters, list):
        return False

    for chapter in chapters:
        items = chapter.get(nested_key) if isinstance(chapter, dict) else None
        if not isinstance(items, list):
            continue

        if any(item.get("page_start") is not None for item in items if isinstance(item, dict)):
            return True

    return False


def score_section_candidates(report: dict | None) -> dict:
    if not report:
        return unavailable_source("Section candidates file was not provided.")

    section_count = int(report.get("candidate_count") or 0)
    chapter_count = count_chapters_from_grouped_report(report)
    has_page_numbers = has_pages_in_grouped_report(report, "candidates")

    if section_count > 500:
        noise_score = 0.8
        confidence = "low"
        reason = "Too many noisy heading candidates."
    elif section_count >= 50:
        noise_score = 0.6
        confidence = "medium"
        reason = "Candidate report exists but still needs cleanup."
    else:
        noise_score = 0.3
        confidence = "low"
        reason = "Too few candidates for complete structure."

    return {
        "available": True,
        "chapter_count": chapter_count,
        "section_count": section_count,
        "has_page_numbers": has_page_numbers,
        "noise_score": noise_score,
        "confidence": confidence,
        "reason": reason,
    }


def score_section_outline(report: dict | None) -> dict:
    if not report:
        return unavailable_source("Section outline file was not provided.")

    section_count = int(report.get("outline_count") or 0)
    chapter_count = count_chapters_from_grouped_report(report)
    has_page_numbers = has_pages_in_grouped_report(report, "outline")

    if section_count > 200:
        noise_score = 0.6
        confidence = "low"
        reason = "Still too noisy for assignment."
    elif section_count >= 40:
        noise_score = 0.4
        confidence = "medium"
        reason = "Section outline exists with moderate noise."
    else:
        noise_score = 0.2
        confidence = "low"
        reason = "Section outline is too sparse for full structure."

    return {
        "available": True,
        "chapter_count": chapter_count,
        "section_count": section_count,
        "has_page_numbers": has_page_numbers,
        "noise_score": noise_score,
        "confidence": confidence,
        "reason": reason,
    }


def score_strict_section_outline(report: dict | None) -> dict:
    if not report:
        return unavailable_source("Strict section outline file was not provided.")

    section_count = int(report.get("strict_outline_count") or 0)
    chapter_count = len(
        [
            chapter
            for chapter in report.get("chapters", [])
            if isinstance(chapter, dict) and int(chapter.get("outline_count") or 0) > 0
        ]
    )
    has_page_numbers = has_pages_in_grouped_report(report, "outline")

    if section_count >= 20 and chapter_count >= 5:
        noise_score = 0.15
        confidence = "medium"
        reason = "Strict outline has enough useful entries across chapters."
    else:
        noise_score = 0.1
        confidence = "low"
        reason = "Too few entries for full structure."

    return {
        "available": True,
        "chapter_count": chapter_count,
        "section_count": section_count,
        "has_page_numbers": has_page_numbers,
        "noise_score": noise_score,
        "confidence": confidence,
        "reason": reason,
    }


def unavailable_source(reason: str) -> dict:
    return {
        "available": False,
        "chapter_count": 0,
        "section_count": 0,
        "has_page_numbers": False,
        "noise_score": 1.0,
        "confidence": "low",
        "reason": reason,
    }


def chapter_metadata_summary(chunks: list[dict]) -> dict:
    chapter_numbers = OrderedDict()
    page_numbers = []

    for chunk in chunks:
        chapter = chunk.get("chapter")
        chapter_number = chunk.get("chapter_number")
        if chapter is not None or chapter_number is not None:
            chapter_numbers[(chapter_number, chapter)] = True

        if chunk.get("page_start") is not None:
            page_numbers.append(chunk.get("page_start"))

    return {
        "available": bool(chapter_numbers),
        "chapter_count": len(chapter_numbers),
        "has_page_numbers": bool(page_numbers),
    }


def score_chapter_only(chunks: list[dict]) -> dict:
    summary = chapter_metadata_summary(chunks)
    if not summary["available"]:
        return unavailable_source("Chunks do not contain chapter metadata.")

    chapter_count = summary["chapter_count"]
    confidence = "medium" if chapter_count >= 1 else "low"
    return {
        "available": True,
        "chapter_count": chapter_count,
        "section_count": 0,
        "has_page_numbers": summary["has_page_numbers"],
        "noise_score": 0.2 if chapter_count >= 5 else 0.35,
        "confidence": confidence,
        "reason": "Chapter metadata already exists.",
    }


def score_flat_chunks(chunks: list[dict]) -> dict:
    return {
        "available": bool(chunks),
        "chapter_count": 0,
        "section_count": 0,
        "has_page_numbers": False,
        "noise_score": 0.5,
        "confidence": "low",
        "reason": "Fallback only.",
    }


def build_chapter_only_outline(chunks: list[dict]) -> dict:
    chapters: OrderedDict[Any, dict] = OrderedDict()

    for chunk in chunks:
        chapter = chunk.get("chapter")
        chapter_number = chunk.get("chapter_number")
        if chapter is None and chapter_number is None:
            continue

        key = (chapter_number, chapter)
        if key not in chapters:
            chapters[key] = {
                "chapter_number": chapter_number,
                "chapter_title": chapter,
                "page_start": chunk.get("chapter_source_page", chunk.get("page_start")),
                "sections": [],
            }

    return {
        "chapters": list(chapters.values()),
        "non_chapter_entries": [],
    }


def build_flat_outline(chunks: list[dict]) -> dict:
    return {
        "chapters": [
            {
                "chapter_number": None,
                "chapter_title": "Flat document chunks",
                "page_start": chunks[0].get("page_start") if chunks else None,
                "sections": [],
            }
        ]
        if chunks
        else [],
        "non_chapter_entries": [],
    }


def source_selection_score(source_name: str, source_score: dict, source_order: list[str]) -> tuple:
    confidence = confidence_rank(str(source_score.get("confidence")))
    available = 1 if source_score.get("available") else 0
    chapter_count = int(source_score.get("chapter_count") or 0)
    section_count = int(source_score.get("section_count") or 0)
    has_page_numbers = 1 if source_score.get("has_page_numbers") else 0
    noise_score = float(source_score.get("noise_score") or 1.0)
    order_score = len(source_order) - source_order.index(source_name)

    return (
        available,
        confidence,
        has_page_numbers,
        min(section_count, 200),
        min(chapter_count, 50),
        -noise_score,
        order_score,
    )


def select_source(sources: dict[str, dict], toc_outline: dict, chunks: list[dict]) -> tuple[str, str, dict]:
    if (
        sources["toc"]["available"]
        and sources["toc"]["chapter_count"] >= 5
        and sources["toc"]["section_count"] >= 20
        and sources["toc"]["has_page_numbers"]
    ):
        return (
            "toc",
            "TOC contains reliable chapters, sections, and page numbers.",
            toc_outline,
        )

    if (
        sources["body_outline"]["available"]
        and sources["body_outline"]["chapter_count"] >= 5
        and sources["toc"]["confidence"] != "high"
    ):
        return (
            "body_outline",
            "Body outline contains reliable in-body chapter markers.",
            build_chapter_only_outline(chunks),
        )

    if (
        sources["strict_section_outline"]["available"]
        and sources["strict_section_outline"]["section_count"] >= 20
        and sources["strict_section_outline"]["chapter_count"] >= 5
    ):
        return (
            "strict_section_outline",
            "Strict section outline contains enough useful entries.",
            {"chapters": [], "non_chapter_entries": []},
        )

    if sources["chapter_only"]["available"]:
        return (
            "chapter_only",
            "Sections are unreliable, so existing chapter metadata is the best fallback.",
            build_chapter_only_outline(chunks),
        )

    source_order = [
        "toc",
        "body_outline",
        "section_candidates",
        "section_outline",
        "strict_section_outline",
        "chapter_only",
        "flat_chunks",
    ]
    selected_source = max(
        source_order,
        key=lambda source_name: source_selection_score(
            source_name,
            sources[source_name],
            source_order,
        ),
    )
    return (
        selected_source,
        sources[selected_source]["reason"],
        build_flat_outline(chunks),
    )


def build_report(
    chunks_path: Path,
    chunks: list[dict],
    toc: dict,
    body_outline_report: dict | None,
    section_candidates_report: dict | None,
    section_outline_report: dict | None,
    strict_section_outline_report: dict | None,
) -> dict:
    sources = {
        "toc": score_toc(toc),
        "body_outline": score_body_outline(body_outline_report),
        "section_candidates": score_section_candidates(section_candidates_report),
        "section_outline": score_section_outline(section_outline_report),
        "strict_section_outline": score_strict_section_outline(strict_section_outline_report),
        "chapter_only": score_chapter_only(chunks),
        "flat_chunks": score_flat_chunks(chunks),
    }
    selected_source, selection_reason, selected_outline = select_source(
        sources=sources,
        toc_outline=toc["outline"],
        chunks=chunks,
    )

    return {
        "source_chunks_file": str(chunks_path),
        "selected_source": selected_source,
        "selected_confidence": sources[selected_source]["confidence"],
        "selection_reason": selection_reason,
        "sources": sources,
        "selected_outline": selected_outline,
    }


def format_source_score(name: str, source: dict) -> str:
    return (
        f"{name}: {source['confidence']} | "
        f"available={str(source['available']).lower()} | "
        f"chapters={source['chapter_count']} | "
        f"sections={source['section_count']} | "
        f"page_numbers={str(source['has_page_numbers']).lower()} | "
        f"noise={source['noise_score']} | "
        f"{source['reason']}"
    )


def format_text_report(report: dict) -> str:
    lines = [
        "STRUCTURE RESOLUTION",
        "=" * 80,
        "",
        f"Selected source: {report['selected_source']}",
        f"Confidence: {report['selected_confidence']}",
        f"Reason: {report['selection_reason']}",
        "",
        "SOURCE SCORES",
        "-" * 80,
    ]

    for source_name, source in report["sources"].items():
        lines.append(format_source_score(source_name, source))

    lines.extend(["", "SELECTED OUTLINE PREVIEW", "-" * 80])
    chapters = report["selected_outline"].get("chapters") or []
    for chapter in chapters[:5]:
        chapter_number = chapter.get("chapter_number")
        chapter_title = chapter.get("chapter_title")
        page_start = chapter.get("page_start")
        label = (
            f"CHAPTER {chapter_number}: {chapter_title}"
            if chapter_number is not None
            else str(chapter_title)
        )
        if page_start is not None:
            label += f" (p. {page_start})"
        lines.append(label)

        for section in (chapter.get("sections") or [])[:8]:
            section_title = section.get("section_title")
            section_page = section.get("page_start")
            if section_page is not None:
                lines.append(f"* {section_title} (p. {section_page})")
            else:
                lines.append(f"* {section_title}")
        lines.append("")

    non_chapter_entries = report["selected_outline"].get("non_chapter_entries") or []
    if non_chapter_entries:
        lines.extend(["NON-CHAPTER ENTRIES", "-" * 80])
        for entry in non_chapter_entries[:20]:
            page_start = entry.get("page_start")
            if page_start is not None:
                lines.append(f"* {entry.get('title')} (p. {page_start})")
            else:
                lines.append(f"* {entry.get('title')}")

    return "\n".join(lines).rstrip() + "\n"


def write_report(chunks_path: Path, report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(chunks_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.structure_resolution.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.structure_resolution.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def print_summary(report: dict, json_output_path: Path, txt_output_path: Path) -> None:
    print("Document structure resolution completed.")
    print(f"Source chunks file: {report['source_chunks_file']}")
    print(f"Selected source: {report['selected_source']}")
    print(f"Selected confidence: {report['selected_confidence']}")
    print(f"Selection reason: {report['selection_reason']}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    chunks_path = Path(args.chunks_path)
    chunks = validate_chunks(load_json_file(chunks_path))

    body_outline_report, _ = load_optional_report(args.body_outline)
    section_candidates_report, _ = load_optional_report(args.section_candidates)
    section_outline_report, _ = load_optional_report(args.section_outline)
    strict_section_outline_report, _ = load_optional_report(args.strict_section_outline)

    toc = extract_toc_outline(chunks)
    report = build_report(
        chunks_path=chunks_path,
        chunks=chunks,
        toc=toc,
        body_outline_report=body_outline_report,
        section_candidates_report=section_candidates_report,
        section_outline_report=section_outline_report,
        strict_section_outline_report=strict_section_outline_report,
    )
    json_output_path, txt_output_path = write_report(chunks_path, report)
    print_summary(report, json_output_path, txt_output_path)


if __name__ == "__main__":
    main()
