import argparse
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")
DEFAULT_MAX_HEADING_LENGTH = 120
DEFAULT_MAX_ENTRIES_PER_CHAPTER = 25
CONFIDENCE_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
}
DEFAULT_ALLOWED_TYPES = {
    "numbered_heading",
    "question_heading",
    "heading_followed_by_body",
}
SHORT_TITLE_TYPE = "short_title_like_line"
UPPERCASE_TYPE = "mostly_uppercase_short_line"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reduce noisy PDF section/topic candidates into a cleaner outline."
    )
    parser.add_argument(
        "section_topic_candidates_path",
        help="Path to a section/topic candidates JSON report.",
    )
    parser.add_argument(
        "chapter_chunks_path",
        help="Path to the chapter-enriched PDF chunks JSON file.",
    )
    parser.add_argument(
        "--include-short-title-like",
        action="store_true",
        help="Keep short_title_like_line candidates instead of excluding them by default.",
    )
    parser.add_argument(
        "--include-uppercase-headings",
        action="store_true",
        help="Keep mostly_uppercase_short_line candidates instead of excluding them by default.",
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
        help="Minimum candidate confidence to keep. Defaults to medium.",
    )
    parser.add_argument(
        "--max-entries-per-chapter",
        type=int,
        default=DEFAULT_MAX_ENTRIES_PER_CHAPTER,
        help=(
            "Maximum kept outline entries per chapter. "
            f"Defaults to {DEFAULT_MAX_ENTRIES_PER_CHAPTER}."
        ),
    )
    return parser.parse_args()


def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Required file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"Path is not a file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_candidates_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise SystemExit("Section/topic candidates JSON must contain a top-level object.")

    chapters = report.get("chapters")
    if not isinstance(chapters, list):
        raise SystemExit("Section/topic candidates JSON must contain a chapters array.")


def validate_chunks(chunks: list) -> None:
    if not isinstance(chunks, list):
        raise SystemExit("Chapter chunks JSON must contain a top-level array.")


def output_stem(path: Path) -> str:
    if path.name.endswith(".section_topic_candidates.json"):
        return path.name[: -len(".section_topic_candidates.json")]

    return path.stem


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def chunk_lookup(chunks: list[dict]) -> dict[str, dict]:
    return {str(chunk.get("id")): chunk for chunk in chunks if chunk.get("id")}


def chapter_source_chunk_lookup(chunks: list[dict]) -> dict[Any, str]:
    lookup: dict[Any, str] = {}

    for chunk in chunks:
        if chunk.get("is_front_matter"):
            continue

        chapter_number = chunk.get("chapter_number")
        source_chunk_id = chunk.get("chapter_source_chunk_id")
        if chapter_number is not None and source_chunk_id and chapter_number not in lookup:
            lookup[chapter_number] = str(source_chunk_id)

    return lookup


def confidence_is_allowed(confidence: str, min_confidence: str) -> bool:
    return CONFIDENCE_ORDER.get(confidence, 0) >= CONFIDENCE_ORDER[min_confidence]


def is_url_or_email(heading: str) -> bool:
    return bool(
        re.search(r"https?://|www\.|\S+@\S+\.\S+", heading, flags=re.IGNORECASE)
    )


def is_standalone_page_number(heading: str) -> bool:
    return bool(re.fullmatch(r"(?:page\s*)?\d{1,4}", heading, flags=re.IGNORECASE))


def is_footer_or_header_text(heading: str) -> bool:
    patterns = [
        r"copyright",
        r"\u00a9",
        r"all rights reserved",
        r"printed in",
        r"oreilly\.com",
        r"o'reilly",
        r"isbn",
        r"^\d{1,4}\s*\|",
        r"\|\s*\d{1,4}$",
        r"chapter\s+\d+\s*\|",
        r"\|\s*chapter\s+\d+",
    ]
    return any(re.search(pattern, heading, flags=re.IGNORECASE) for pattern in patterns)


def is_table_or_figure_noise(heading: str, preview_after: str) -> bool:
    combined = f"{heading} {preview_after}".lower()
    table_terms = [
        "figure ",
        "table ",
        "source:",
        "% exposure",
        "pop.",
        "rank ",
        "score ",
        "benchmark",
        "dataset",
        "accuracy",
    ]

    if any(term in combined for term in table_terms):
        return True

    words = heading.split()
    if len(words) >= 4:
        title_case_count = sum(1 for word in words if word[:1].isupper())
        short_word_count = sum(1 for word in words if len(word) <= 3)
        if title_case_count == len(words) and short_word_count >= 2:
            return True

    return False


def is_formula_or_numeric_noise(heading: str) -> bool:
    digit_count = sum(1 for character in heading if character.isdigit())
    letter_count = sum(1 for character in heading if character.isalpha())

    if re.search(r"[=×*/<>]", heading):
        return True

    if "%" in heading:
        return True

    if re.search(r"\b(?:FLOP|FLOPs|PPL|BPB|BPC|ACC|SOTA)\b", heading):
        return True

    if re.match(r"^\d+(?:\.\d+)?\s+", heading) and not re.match(
        r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})*\s+[A-Za-z]", heading
    ):
        return True

    if digit_count >= 3 and not heading.lower().startswith("factor "):
        return True

    if digit_count >= 2 and letter_count <= 5:
        return True

    return False


def is_table_row_sentence_noise(heading: str) -> bool:
    lower_heading = heading.lower()

    if " and others" in lower_heading:
        return True

    if re.search(r"\b(?:billion|trillion|million)\b", lower_heading) and any(
        character.isdigit() for character in heading
    ):
        return True

    if "," in heading and len(heading.split()) > 8:
        return True

    return False


def is_prompt_or_placeholder_noise(heading: str) -> bool:
    lower_heading = heading.lower()
    prompt_prefixes = (
        "user:",
        "assistant:",
        "system:",
        "generated answer:",
        "context:",
        "description:",
        "input:",
        "output:",
    )

    if lower_heading.startswith(prompt_prefixes):
        return True

    if "[" in heading or "]" in heading:
        return True

    if ".pdf" in lower_heading:
        return True

    if lower_heading.startswith(("category question", "instruction group")):
        return True

    return False


def is_question_example_noise(heading: str) -> bool:
    if not heading.endswith("?"):
        return False

    words = heading.split()
    if len(words) < 3:
        return True

    if heading[0].islower():
        return True

    lower_heading = heading.lower()
    example_terms = {
        "animal",
        "animals",
        "sharks",
        "dolphins",
        "cats",
        "dogs",
    }
    if any(term in lower_heading for term in example_terms):
        return True

    return False


def is_sentence_fragment_noise(heading: str) -> bool:
    words = heading.split()
    lower_heading = heading.lower()

    if heading[0].islower():
        return True

    if re.search(r"[\"'”’]\d{1,3}$", heading):
        return True

    sentence_markers = (
        " because ",
        " however ",
        " whereas ",
        " although ",
        " while ",
    )
    if len(words) >= 9 and any(marker in lower_heading for marker in sentence_markers):
        return True

    if len(words) >= 10 and heading.endswith(("‐", "-", "–")):
        return True

    return False


def has_too_many_punctuation_symbols(heading: str) -> bool:
    if "<" in heading or ">" in heading:
        return True

    punctuation_count = sum(
        1 for character in heading if not character.isalnum() and not character.isspace()
    )
    if punctuation_count <= 8:
        return False

    return len(heading) > 0 and punctuation_count / len(heading) > 0.2


def has_enough_letters(heading: str) -> bool:
    return sum(1 for character in heading if character.isalpha()) >= 3


def is_repeated_chapter_marker(heading: str) -> bool:
    return bool(re.fullmatch(r"chapter\s+\d+", heading, flags=re.IGNORECASE))


def is_exercise_or_list_item(heading: str) -> bool:
    if re.fullmatch(r"\d{1,3}[.)]", heading):
        return True

    if re.match(r"^\d{1,3}[.)]\s+\S+", heading) and not re.match(
        r"^\d{1,2}\.\d{1,2}", heading
    ):
        return True

    return bool(re.fullmatch(r"\(?[a-zA-Z]\)", heading))


def is_sentence_noise(heading: str) -> bool:
    words = heading.split()
    if len(words) > 16:
        return True

    if heading.endswith((".", ",", ";")):
        return True

    return False


def looks_like_chapter_opening_title(
    candidate: dict,
    chapter_source_chunks: dict[Any, str],
) -> bool:
    chapter_number = candidate.get("chapter_number")
    source_chunk_id = chapter_source_chunks.get(chapter_number)
    return bool(source_chunk_id and candidate.get("chunk_id") == source_chunk_id)


def outline_level_for(candidate_type: str, keep_reason: str) -> str:
    if keep_reason == "chapter_opening_title":
        return "chapter_title"

    if candidate_type == "numbered_heading":
        return "numbered_section"

    if candidate_type == "question_heading":
        return "topic_question"

    if candidate_type == "mostly_uppercase_short_line":
        return "heading"

    return "section_or_topic"


def candidate_type_allowed(
    candidate: dict,
    include_short_title_like: bool,
    include_uppercase_headings: bool,
    chapter_source_chunks: dict[Any, str],
) -> tuple[bool, str]:
    candidate_type = str(candidate.get("candidate_type") or "")

    if candidate_type in DEFAULT_ALLOWED_TYPES:
        return True, "allowed_candidate_type"

    if candidate_type == UPPERCASE_TYPE:
        if include_uppercase_headings:
            return True, "uppercase_heading_included"

        return False, "uppercase_heading_excluded"

    if candidate_type == SHORT_TITLE_TYPE:
        if include_short_title_like:
            return True, "short_title_like_included"

        if looks_like_chapter_opening_title(candidate, chapter_source_chunks):
            return True, "chapter_opening_title"

        return False, "short_title_like_excluded"

    return False, "candidate_type_not_allowed"


def should_keep_candidate(
    candidate: dict,
    chunk: dict | None,
    seen_by_chapter: set[tuple[Any, str]],
    include_short_title_like: bool,
    include_uppercase_headings: bool,
    max_heading_length: int,
    min_confidence: str,
    chapter_source_chunks: dict[Any, str],
) -> tuple[bool, str]:
    heading = normalize_text(str(candidate.get("normalized_heading") or candidate.get("line") or ""))
    preview_after = normalize_text(str(candidate.get("preview_after") or ""))
    confidence = str(candidate.get("confidence") or "low")
    chapter_number = candidate.get("chapter_number")

    if not confidence_is_allowed(confidence, min_confidence):
        return False, "confidence_below_minimum"

    if len(heading) < 3:
        return False, "too_short"

    if len(heading) > max_heading_length:
        return False, "too_long"

    if not has_enough_letters(heading):
        return False, "not_enough_letters"

    if is_standalone_page_number(heading):
        return False, "standalone_page_number"

    if is_url_or_email(heading):
        return False, "url_or_email"

    if is_footer_or_header_text(heading):
        return False, "footer_or_header_text"

    if is_repeated_chapter_marker(heading):
        return False, "repeated_chapter_marker"

    if is_exercise_or_list_item(heading):
        return False, "exercise_or_list_item"

    if has_too_many_punctuation_symbols(heading):
        return False, "too_much_punctuation"

    if is_prompt_or_placeholder_noise(heading):
        return False, "prompt_or_placeholder_noise"

    if is_question_example_noise(heading):
        return False, "question_example_noise"

    if is_sentence_fragment_noise(heading):
        return False, "sentence_fragment_noise"

    if is_formula_or_numeric_noise(heading):
        return False, "formula_or_numeric_noise"

    type_allowed, type_reason = candidate_type_allowed(
        candidate=candidate,
        include_short_title_like=include_short_title_like,
        include_uppercase_headings=include_uppercase_headings,
        chapter_source_chunks=chapter_source_chunks,
    )
    if not type_allowed:
        return False, type_reason

    if type_reason != "chapter_opening_title" and is_sentence_noise(heading):
        return False, "sentence_like_noise"

    if is_table_row_sentence_noise(heading):
        return False, "table_row_sentence_noise"

    if is_table_or_figure_noise(heading, preview_after):
        return False, "table_or_figure_noise"

    if chunk and chunk.get("is_front_matter"):
        return False, "front_matter"

    seen_key = (chapter_number, heading.casefold())
    if seen_key in seen_by_chapter:
        return False, "duplicate_in_chapter"

    seen_by_chapter.add(seen_key)
    return True, type_reason


def flatten_candidates(report: dict) -> list[dict]:
    candidates = []
    for chapter in report["chapters"]:
        chapter_candidates = chapter.get("candidates")
        if not isinstance(chapter_candidates, list):
            continue

        candidates.extend(chapter_candidates)

    return candidates


def build_outline_entry(candidate: dict, keep_reason: str) -> dict:
    candidate_type = str(candidate.get("candidate_type") or "")
    heading = normalize_text(str(candidate.get("normalized_heading") or candidate.get("line") or ""))

    return {
        "candidate_id": candidate.get("candidate_id"),
        "chunk_id": candidate.get("chunk_id"),
        "chapter": candidate.get("chapter"),
        "chapter_number": candidate.get("chapter_number"),
        "page_start": candidate.get("page_start"),
        "page_end": candidate.get("page_end"),
        "heading": heading,
        "candidate_type": candidate_type,
        "confidence": candidate.get("confidence"),
        "outline_level": outline_level_for(candidate_type, keep_reason),
        "line_number": candidate.get("line_number"),
        "keep_reason": keep_reason,
        "preview_before": candidate.get("preview_before"),
        "preview_after": candidate.get("preview_after"),
    }


def build_excluded_entry(candidate: dict, reason: str) -> dict:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "chunk_id": candidate.get("chunk_id"),
        "chapter": candidate.get("chapter"),
        "chapter_number": candidate.get("chapter_number"),
        "page_start": candidate.get("page_start"),
        "page_end": candidate.get("page_end"),
        "heading": normalize_text(
            str(candidate.get("normalized_heading") or candidate.get("line") or "")
        ),
        "candidate_type": candidate.get("candidate_type"),
        "confidence": candidate.get("confidence"),
        "reason": reason,
    }


def build_outline(
    candidates_report: dict,
    chunks: list[dict],
    include_short_title_like: bool,
    include_uppercase_headings: bool,
    max_heading_length: int,
    min_confidence: str,
    max_entries_per_chapter: int,
) -> tuple[list[dict], list[dict]]:
    chunks_by_id = chunk_lookup(chunks)
    chapter_source_chunks = chapter_source_chunk_lookup(chunks)
    seen_by_chapter: set[tuple[Any, str]] = set()
    chapter_counts: Counter[Any] = Counter()
    outline = []
    excluded = []

    for candidate in flatten_candidates(candidates_report):
        chunk = chunks_by_id.get(str(candidate.get("chunk_id")))
        chapter_number = candidate.get("chapter_number")

        keep, reason = should_keep_candidate(
            candidate=candidate,
            chunk=chunk,
            seen_by_chapter=seen_by_chapter,
            include_short_title_like=include_short_title_like,
            include_uppercase_headings=include_uppercase_headings,
            max_heading_length=max_heading_length,
            min_confidence=min_confidence,
            chapter_source_chunks=chapter_source_chunks,
        )

        if keep and max_entries_per_chapter > 0:
            if chapter_counts[chapter_number] >= max_entries_per_chapter:
                keep = False
                reason = "max_entries_per_chapter_reached"

        if keep:
            chapter_counts[chapter_number] += 1
            outline.append(build_outline_entry(candidate, reason))
        else:
            excluded.append(build_excluded_entry(candidate, reason))

    for position, item in enumerate(outline, start=1):
        item["position"] = position

    return outline, excluded


def group_outline_by_chapter(outline: list[dict]) -> list[dict]:
    grouped: OrderedDict[tuple[Any, Any], list[dict]] = OrderedDict()

    for item in outline:
        key = (item.get("chapter_number"), item.get("chapter"))
        grouped.setdefault(key, []).append(item)

    chapters = []
    for (chapter_number, chapter), items in grouped.items():
        chapters.append(
            {
                "chapter": chapter,
                "chapter_number": chapter_number,
                "outline_count": len(items),
                "outline": items,
            }
        )

    return chapters


def build_report(
    candidates_path: Path,
    chunks_path: Path,
    candidates_report: dict,
    outline: list[dict],
    excluded: list[dict],
    include_short_title_like: bool,
    include_uppercase_headings: bool,
    max_heading_length: int,
    min_confidence: str,
    max_entries_per_chapter: int,
) -> dict:
    excluded_reason_counts = Counter(item["reason"] for item in excluded)
    kept_type_counts = Counter(item["candidate_type"] for item in outline)
    input_candidate_count = candidates_report.get(
        "candidate_count", len(flatten_candidates(candidates_report))
    )

    return {
        "source_candidates_file": str(candidates_path),
        "source_chunks_file": str(chunks_path),
        "input_candidate_count": input_candidate_count,
        "outline_count": len(outline),
        "excluded_count": len(excluded),
        "include_short_title_like": include_short_title_like,
        "include_uppercase_headings": include_uppercase_headings,
        "max_heading_length": max_heading_length,
        "min_confidence": min_confidence,
        "max_entries_per_chapter": max_entries_per_chapter,
        "kept_candidate_type_counts": dict(sorted(kept_type_counts.items())),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "chapters": group_outline_by_chapter(outline),
        "excluded_candidates": excluded,
    }


def format_text_report(report: dict) -> str:
    lines = [
        "PDF Section/Topic Outline",
        "=" * 80,
        f"Source candidates file: {report['source_candidates_file']}",
        f"Source chunks file: {report['source_chunks_file']}",
        f"Input candidate count: {report['input_candidate_count']}",
        f"Outline count: {report['outline_count']}",
        f"Excluded count: {report['excluded_count']}",
        f"Include short title-like: {report['include_short_title_like']}",
        f"Include uppercase headings: {report['include_uppercase_headings']}",
        f"Minimum confidence: {report['min_confidence']}",
        f"Max heading length: {report['max_heading_length']}",
        f"Max entries per chapter: {report['max_entries_per_chapter']}",
        "",
        "KEPT TYPE COUNTS",
        "-" * 80,
    ]

    for candidate_type, count in report["kept_candidate_type_counts"].items():
        lines.append(f"{candidate_type}: {count}")

    lines.extend(["", "EXCLUDED REASON COUNTS", "-" * 80])
    for reason, count in report["excluded_reason_counts"].items():
        lines.append(f"{reason}: {count}")

    lines.extend(["", "OUTLINE", "=" * 80])

    for chapter in report["chapters"]:
        chapter_title = chapter["chapter"] or "FRONT MATTER"
        lines.extend(["", chapter_title, "-" * len(chapter_title)])

        for item in chapter["outline"]:
            lines.append(
                "Page {page_start} | {confidence} | {outline_level} | {heading}".format(
                    page_start=item["page_start"],
                    confidence=item["confidence"],
                    outline_level=item["outline_level"],
                    heading=item["heading"],
                )
            )
            lines.append(
                "  Chunk: {chunk_id} | Candidate: {candidate_id} | Type: {candidate_type} | Reason: {keep_reason}".format(
                    chunk_id=item["chunk_id"],
                    candidate_id=item["candidate_id"],
                    candidate_type=item["candidate_type"],
                    keep_reason=item["keep_reason"],
                )
            )
            if item.get("preview_after"):
                lines.append(f"  After: {item['preview_after']}")
            lines.append("")

    lines.extend(["", "EXCLUDED EXAMPLES", "=" * 80])
    for item in report["excluded_candidates"][:100]:
        lines.append(
            "Page {page_start} | {reason} | {candidate_type} | {heading}".format(
                page_start=item["page_start"],
                reason=item["reason"],
                candidate_type=item["candidate_type"],
                heading=item["heading"],
            )
        )
        lines.append(f"  Chunk: {item['chunk_id']} | Candidate: {item['candidate_id']}")

    return "\n".join(lines)


def write_report(candidates_path: Path, report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(candidates_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.section_topic_outline.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.section_topic_outline.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def print_summary(report: dict, json_output_path: Path, txt_output_path: Path) -> None:
    print("PDF section/topic outline report created.")
    print(f"Source candidates file: {report['source_candidates_file']}")
    print(f"Source chunks file: {report['source_chunks_file']}")
    print(f"Input candidate count: {report['input_candidate_count']}")
    print(f"Outline count: {report['outline_count']}")
    print(f"Excluded count: {report['excluded_count']}")
    print(f"Include short title-like: {report['include_short_title_like']}")
    print(f"Include uppercase headings: {report['include_uppercase_headings']}")
    print(f"Minimum confidence: {report['min_confidence']}")
    print(f"Max heading length: {report['max_heading_length']}")
    print(f"Max entries per chapter: {report['max_entries_per_chapter']}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    candidates_path = Path(args.section_topic_candidates_path)
    chunks_path = Path(args.chapter_chunks_path)
    candidates_report = load_json_file(candidates_path)
    chunks = load_json_file(chunks_path)

    validate_candidates_report(candidates_report)
    validate_chunks(chunks)

    outline, excluded = build_outline(
        candidates_report=candidates_report,
        chunks=chunks,
        include_short_title_like=args.include_short_title_like,
        include_uppercase_headings=args.include_uppercase_headings,
        max_heading_length=args.max_heading_length,
        min_confidence=args.min_confidence,
        max_entries_per_chapter=args.max_entries_per_chapter,
    )
    report = build_report(
        candidates_path=candidates_path,
        chunks_path=chunks_path,
        candidates_report=candidates_report,
        outline=outline,
        excluded=excluded,
        include_short_title_like=args.include_short_title_like,
        include_uppercase_headings=args.include_uppercase_headings,
        max_heading_length=args.max_heading_length,
        min_confidence=args.min_confidence,
        max_entries_per_chapter=args.max_entries_per_chapter,
    )
    json_output_path, txt_output_path = write_report(candidates_path, report)
    print_summary(report, json_output_path, txt_output_path)


if __name__ == "__main__":
    main()
