import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")
DEFAULT_MAX_HEADING_LENGTH = 140
PREVIEW_CHAR_LIMIT = 350
CONFIDENCE_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect possible section and topic headings inside chapter-enriched PDF chunks."
    )
    parser.add_argument(
        "chapter_chunks_path",
        help="Path to a chapter-enriched PDF chunks JSON file.",
    )
    parser.add_argument(
        "--include-front-matter",
        action="store_true",
        help="Scan front matter chunks as well as chapter body chunks.",
    )
    parser.add_argument(
        "--max-heading-length",
        type=int,
        default=DEFAULT_MAX_HEADING_LENGTH,
        help=f"Maximum heading length to keep. Defaults to {DEFAULT_MAX_HEADING_LENGTH}.",
    )
    parser.add_argument(
        "--min-confidence",
        choices=["low", "medium", "high"],
        default="medium",
        help="Minimum candidate confidence to include. Defaults to medium.",
    )
    return parser.parse_args()


def load_chunks(chapter_chunks_path: Path) -> list[dict]:
    if not chapter_chunks_path.exists():
        raise SystemExit(
            f"Chapter chunks JSON file does not exist: {chapter_chunks_path}"
        )

    if not chapter_chunks_path.is_file():
        raise SystemExit(
            f"Chapter chunks JSON path is not a file: {chapter_chunks_path}"
        )

    with chapter_chunks_path.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    if not isinstance(chunks, list):
        raise SystemExit("Chapter chunks JSON must contain a top-level JSON array.")

    return chunks


def output_stem(chapter_chunks_path: Path) -> str:
    if chapter_chunks_path.name.endswith(".chapter_chunks.json"):
        return chapter_chunks_path.name[: -len(".chapter_chunks.json")]

    return chapter_chunks_path.stem


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_heading(line: str) -> str:
    return normalize_text(line.strip(" \t"))


def nonempty_lines(lines: list[str], start: int, stop: int) -> list[str]:
    return [
        normalize_text(line)
        for line in lines[start:stop]
        if normalize_text(line)
    ]


def build_preview_before(lines: list[str], line_index: int) -> str:
    start = max(0, line_index - 3)
    preview = " ".join(nonempty_lines(lines, start, line_index))
    return preview[:PREVIEW_CHAR_LIMIT]


def build_preview_after(lines: list[str], line_index: int) -> str:
    end = min(len(lines), line_index + 4)
    preview = " ".join(nonempty_lines(lines, line_index + 1, end))
    return preview[:PREVIEW_CHAR_LIMIT]


def next_nonempty_line(lines: list[str], line_index: int) -> str | None:
    for next_line in lines[line_index + 1 :]:
        normalized_line = normalize_text(next_line)
        if normalized_line:
            return normalized_line

    return None


def is_standalone_page_number(line: str) -> bool:
    return bool(re.fullmatch(r"(?:page\s*)?\d{1,4}", line, flags=re.IGNORECASE))


def is_url_or_email(line: str) -> bool:
    return bool(
        re.search(r"https?://|www\.|\S+@\S+\.\S+", line, flags=re.IGNORECASE)
    )


def is_footer_or_header_text(line: str) -> bool:
    footer_patterns = [
        r"copyright",
        r"\u00a9",
        r"all rights reserved",
        r"printed in",
        r"oreilly\.com",
        r"o'reilly",
        r"isbn",
        r"chapter\s+\d+\s*\|",
        r"\|\s*chapter\s+\d+",
        r"^\d{1,4}\s*\|",
        r"\|\s*\d{1,4}$",
    ]
    return any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in footer_patterns)


def is_file_name(line: str, chunk: dict[str, Any]) -> bool:
    source_pdf = chunk.get("source_pdf")
    possible_names = set()

    if source_pdf:
        source_path = Path(str(source_pdf))
        possible_names.add(source_path.name.lower())
        possible_names.add(source_path.stem.lower())

    source_metadata = chunk.get("metadata") or {}
    if isinstance(source_metadata, dict):
        file_name = source_metadata.get("file_name")
        file_path = source_metadata.get("file_path")

        if file_name:
            file_path_from_name = Path(str(file_name))
            possible_names.add(file_path_from_name.name.lower())
            possible_names.add(file_path_from_name.stem.lower())

        if file_path:
            file_path_from_metadata = Path(str(file_path))
            possible_names.add(file_path_from_metadata.name.lower())
            possible_names.add(file_path_from_metadata.stem.lower())

    normalized_line = line.lower()
    return normalized_line in possible_names or normalized_line.endswith(".pdf")


def is_repeated_chapter_marker(line: str) -> bool:
    return bool(re.fullmatch(r"chapter\s+\d+", line, flags=re.IGNORECASE))


def is_table_of_contents_line(line: str) -> bool:
    return bool(
        re.search(r"(?:\.\s*){3,}\d+\s*$", line)
        or re.search(r"\btable of contents\b", line, flags=re.IGNORECASE)
        or re.fullmatch(r"contents", line, flags=re.IGNORECASE)
        or re.match(r"^chapter\s+\d+[:.\-\s].+\s+\d{1,4}$", line, flags=re.IGNORECASE)
    )


def has_too_many_punctuation_symbols(line: str) -> bool:
    if "<" in line or ">" in line:
        return True

    punctuation_count = sum(
        1 for character in line if not character.isalnum() and not character.isspace()
    )
    if punctuation_count <= 8:
        return False

    return len(line) > 0 and punctuation_count / len(line) > 0.2


def is_pure_bullet_or_marker(line: str) -> bool:
    return bool(re.fullmatch(r"[\-\*\u2022\u25e6\u25aa\u2013\u2014\s]+", line))


def is_exercise_number_only(line: str) -> bool:
    return bool(
        re.fullmatch(r"\d{1,3}\.", line)
        or re.fullmatch(r"\(?[a-zA-Z]\)", line)
        or re.fullmatch(r"\d{1,3}\)", line)
    )


def line_has_enough_letters(line: str) -> bool:
    return sum(1 for character in line if character.isalpha()) >= 2


def is_noise_line(line: str, chunk: dict[str, Any], max_heading_length: int) -> bool:
    if len(line) < 3:
        return True

    if len(line) > max_heading_length:
        return True

    if is_standalone_page_number(line):
        return True

    if is_url_or_email(line):
        return True

    if is_footer_or_header_text(line):
        return True

    if is_file_name(line, chunk):
        return True

    if is_repeated_chapter_marker(line):
        return True

    if is_table_of_contents_line(line):
        return True

    if has_too_many_punctuation_symbols(line):
        return True

    if is_pure_bullet_or_marker(line):
        return True

    if is_exercise_number_only(line):
        return True

    if not line_has_enough_letters(line):
        return True

    return False


def mostly_uppercase_short_line(line: str) -> bool:
    if len(line) > 90:
        return False

    letters = [character for character in line if character.isalpha()]
    if len(letters) < 3:
        return False

    uppercase_count = sum(1 for character in letters if character.isupper())
    return uppercase_count / len(letters) >= 0.8


def is_question_heading(line: str) -> bool:
    if len(line) > DEFAULT_MAX_HEADING_LENGTH:
        return False

    if not line.endswith("?"):
        return False

    words = line.split()
    return 3 <= len(words) <= 18


def is_body_paragraph_line(line: str | None) -> bool:
    if not line:
        return False

    if is_standalone_page_number(line) or is_url_or_email(line):
        return False

    words = line.split()
    letters = [character for character in line if character.isalpha()]
    return len(words) >= 8 and len(letters) >= 40


def is_strong_title_like_line(line: str) -> bool:
    if line.endswith((".", ",", ";", ":")):
        return False

    if line[0] in "\"'([{/" or not (line[0].isupper() or line[0].isdigit()):
        return False

    words = line.split()
    if not 1 <= len(words) <= 14:
        return False

    title_like_words = 0
    for word in words:
        clean_word = word.strip("\"'()[]{}:")
        if not clean_word:
            continue

        if clean_word[0].isupper() or clean_word.isdigit():
            title_like_words += 1

    return title_like_words >= max(1, len(words) // 2)


def is_weak_title_like_line(line: str) -> bool:
    if line.endswith((".", ",", ";")):
        return False

    if line[0] in "\"'([{/" or not line[0].isupper():
        return False

    words = line.split()
    if not 2 <= len(words) <= 18:
        return False

    first_word = words[0].strip("\"'()[]{}:")
    return bool(first_word and first_word[0].isupper())


def match_numbered_heading(line: str) -> tuple[str, str] | None:
    match = re.match(
        r"^(?P<number>\d{1,2}(?:\.\d{1,2})+\.?|\d{1,2}\.)\s*(?P<title>.*)$",
        line,
    )
    if not match:
        return None

    number = match.group("number")
    title = normalize_text(match.group("title"))
    if not title and re.fullmatch(r"\d{1,2}\.", line):
        return None

    is_decimal_heading = bool(re.fullmatch(r"\d{1,2}(?:\.\d{1,2})+\.?", number))
    if is_decimal_heading:
        confidence = "high" if title else "medium"
    else:
        confidence = "low"

    return "numbered_heading", confidence


def starts_like_question_heading(line: str) -> bool:
    question_starters = (
        "what ",
        "why ",
        "how ",
        "when ",
        "where ",
        "who ",
        "which ",
        "can ",
        "could ",
        "should ",
        "does ",
        "do ",
        "is ",
        "are ",
        "will ",
    )
    return line.lower().startswith(question_starters)


def classify_candidate(
    line: str,
    lines: list[str],
    line_index: int,
) -> tuple[str, str] | None:
    numbered_heading = match_numbered_heading(line)
    if numbered_heading:
        return numbered_heading

    following_line = next_nonempty_line(lines, line_index)
    followed_by_body = is_body_paragraph_line(following_line)

    if is_question_heading(line) and starts_like_question_heading(line):
        return "question_heading", "high" if followed_by_body else "medium"

    if mostly_uppercase_short_line(line):
        return "mostly_uppercase_short_line", "medium"

    if is_strong_title_like_line(line):
        if followed_by_body:
            return "heading_followed_by_body", "medium"

        return "short_title_like_line", "medium"

    if is_weak_title_like_line(line):
        return "weak_title_like_line", "low"

    return None


def confidence_is_allowed(confidence: str, min_confidence: str) -> bool:
    return CONFIDENCE_ORDER[confidence] >= CONFIDENCE_ORDER[min_confidence]


def detect_candidates(
    chunks: list[dict],
    include_front_matter: bool,
    max_heading_length: int,
    min_confidence: str,
) -> list[dict]:
    candidates = []

    for chunk in chunks:
        if chunk.get("is_front_matter") and not include_front_matter:
            continue

        text = str(chunk.get("text") or "")
        lines = text.splitlines()

        for line_index, line in enumerate(lines):
            normalized_line = normalize_heading(line)
            if is_noise_line(normalized_line, chunk, max_heading_length):
                continue

            classification = classify_candidate(normalized_line, lines, line_index)
            if not classification:
                continue

            candidate_type, confidence = classification
            if not confidence_is_allowed(confidence, min_confidence):
                continue

            candidates.append(
                {
                    "candidate_id": f"section_candidate_{len(candidates) + 1:03d}",
                    "chunk_id": chunk.get("id"),
                    "chapter": chunk.get("chapter"),
                    "chapter_number": chunk.get("chapter_number"),
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "line": normalized_line,
                    "normalized_heading": normalized_line,
                    "candidate_type": candidate_type,
                    "confidence": confidence,
                    "line_number": line_index + 1,
                    "preview_before": build_preview_before(lines, line_index),
                    "preview_after": build_preview_after(lines, line_index),
                }
            )

    return candidates


def group_candidates_by_chapter(candidates: list[dict]) -> list[dict]:
    grouped_candidates: OrderedDict[tuple[Any, Any], list[dict]] = OrderedDict()

    for candidate in candidates:
        key = (candidate.get("chapter_number"), candidate.get("chapter"))
        grouped_candidates.setdefault(key, []).append(candidate)

    chapters = []
    for (chapter_number, chapter), chapter_candidates in grouped_candidates.items():
        chapters.append(
            {
                "chapter": chapter,
                "chapter_number": chapter_number,
                "candidate_count": len(chapter_candidates),
                "candidates": chapter_candidates,
            }
        )

    return chapters


def build_report(
    chapter_chunks_path: Path,
    chunks: list[dict],
    candidates: list[dict],
    include_front_matter: bool,
    max_heading_length: int,
    min_confidence: str,
) -> dict:
    scanned_chunk_count = sum(
        1
        for chunk in chunks
        if include_front_matter or not chunk.get("is_front_matter")
    )

    return {
        "source_chunks_file": str(chapter_chunks_path),
        "chunk_count": len(chunks),
        "scanned_chunk_count": scanned_chunk_count,
        "include_front_matter": include_front_matter,
        "max_heading_length": max_heading_length,
        "min_confidence": min_confidence,
        "candidate_count": len(candidates),
        "chapters": group_candidates_by_chapter(candidates),
    }


def format_text_report(report: dict) -> str:
    lines = [
        "PDF Section/Topic Candidate Report",
        "=" * 80,
        f"Source chunks file: {report['source_chunks_file']}",
        f"Chunk count: {report['chunk_count']}",
        f"Scanned chunk count: {report['scanned_chunk_count']}",
        f"Candidate count: {report['candidate_count']}",
        f"Include front matter: {report['include_front_matter']}",
        f"Max heading length: {report['max_heading_length']}",
        f"Minimum confidence: {report['min_confidence']}",
        "",
    ]

    for chapter in report["chapters"]:
        chapter_title = chapter["chapter"] or "FRONT MATTER"
        lines.extend(
            [
                chapter_title,
                "-" * len(chapter_title),
            ]
        )

        for candidate in chapter["candidates"]:
            lines.append(
                "Page {page_start} | {confidence} | {candidate_type} | {line}".format(
                    page_start=candidate["page_start"],
                    confidence=candidate["confidence"],
                    candidate_type=candidate["candidate_type"],
                    line=candidate["line"],
                )
            )
            lines.append(
                f"  Chunk: {candidate['chunk_id']} | Line: {candidate['line_number']}"
            )
            if candidate.get("preview_after"):
                lines.append(f"  After: {candidate['preview_after']}")
            lines.append("")

    return "\n".join(lines)


def write_report(chapter_chunks_path: Path, report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(chapter_chunks_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.section_topic_candidates.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.section_topic_candidates.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def print_summary(report: dict, json_output_path: Path, txt_output_path: Path) -> None:
    print("PDF section/topic candidate detection completed.")
    print(f"Source chunks file: {report['source_chunks_file']}")
    print(f"Chunks: {report['chunk_count']}")
    print(f"Scanned chunks: {report['scanned_chunk_count']}")
    print(f"Candidate count: {report['candidate_count']}")
    print(f"Include front matter: {report['include_front_matter']}")
    print(f"Minimum confidence: {report['min_confidence']}")
    print(f"Max heading length: {report['max_heading_length']}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    chapter_chunks_path = Path(args.chapter_chunks_path)
    chunks = load_chunks(chapter_chunks_path)
    candidates = detect_candidates(
        chunks=chunks,
        include_front_matter=args.include_front_matter,
        max_heading_length=args.max_heading_length,
        min_confidence=args.min_confidence,
    )
    report = build_report(
        chapter_chunks_path=chapter_chunks_path,
        chunks=chunks,
        candidates=candidates,
        include_front_matter=args.include_front_matter,
        max_heading_length=args.max_heading_length,
        min_confidence=args.min_confidence,
    )
    json_output_path, txt_output_path = write_report(chapter_chunks_path, report)
    print_summary(report, json_output_path, txt_output_path)


if __name__ == "__main__":
    main()
