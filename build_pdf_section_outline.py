import argparse
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")
DEFAULT_MAX_PER_CHAPTER = 30
MAX_HEADING_LENGTH = 140
CONFIDENCE_ORDER = {
    "low": 1,
    "medium": 2,
    "high": 3,
}
GENERIC_HEADINGS = {
    "answer",
    "answers",
    "example",
    "examples",
    "note",
    "notes",
    "question",
    "questions",
    "tip",
    "tips",
}
PREFERRED_TYPES = {
    "numbered_heading",
    "question_heading",
    "heading_followed_by_body",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reduce noisy PDF section/topic candidates into a cleaner per-chapter outline."
    )
    parser.add_argument(
        "section_topic_candidates_path",
        help="Path to a section/topic candidates JSON report.",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include low-confidence candidates after the same noise filtering.",
    )
    parser.add_argument(
        "--max-per-chapter",
        type=int,
        default=DEFAULT_MAX_PER_CHAPTER,
        help=f"Maximum outline entries to keep per chapter. Defaults to {DEFAULT_MAX_PER_CHAPTER}.",
    )
    return parser.parse_args()


def load_candidates_report(candidates_path: Path) -> dict:
    if not candidates_path.exists():
        raise SystemExit(f"Section/topic candidates file does not exist: {candidates_path}")

    if not candidates_path.is_file():
        raise SystemExit(f"Section/topic candidates path is not a file: {candidates_path}")

    with candidates_path.open("r", encoding="utf-8") as file:
        report = json.load(file)

    if not isinstance(report, dict):
        raise SystemExit("Section/topic candidates JSON must contain a top-level object.")

    chapters = report.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise SystemExit("Section/topic candidates JSON must contain chapter groups.")

    for position, chapter in enumerate(chapters, start=1):
        if not isinstance(chapter, dict):
            raise SystemExit(f"chapters[{position}] must be an object.")

        candidates = chapter.get("candidates")
        if not isinstance(candidates, list):
            raise SystemExit(f"chapters[{position}] must contain a candidates array.")

    return report


def output_stem(candidates_path: Path) -> str:
    if candidates_path.name.endswith(".section_topic_candidates.json"):
        return candidates_path.name[: -len(".section_topic_candidates.json")]

    return candidates_path.stem


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_key(value: str) -> str:
    normalized = normalize_text(value).casefold()
    normalized = re.sub(r"[\u2018\u2019]", "'", normalized)
    normalized = re.sub(r"[\u201c\u201d]", '"', normalized)
    return normalized


def confidence_is_allowed(confidence: str, include_low_confidence: bool) -> bool:
    minimum = "low" if include_low_confidence else "medium"
    return CONFIDENCE_ORDER.get(confidence, 0) >= CONFIDENCE_ORDER[minimum]


def has_body_text_after(candidate: dict) -> bool:
    preview_after = normalize_text(str(candidate.get("preview_after") or ""))
    words = preview_after.split()
    letters = [character for character in preview_after if character.isalpha()]
    return (
        len(words) >= 8
        and len(letters) >= 35
        and bool(re.search(r"[.!?]", preview_after))
    )


def is_url_or_email(heading: str) -> bool:
    return bool(
        re.search(r"https?://|www\.|\S+@\S+\.\S+", heading, flags=re.IGNORECASE)
    )


def is_page_label(heading: str) -> bool:
    return bool(
        re.fullmatch(r"(?:page\s*)?\d{1,4}", heading, flags=re.IGNORECASE)
        or re.search(r"^\d{1,4}\s*\|", heading)
        or re.search(r"\|\s*\d{1,4}$", heading)
    )


def is_header_or_footer(heading: str) -> bool:
    patterns = [
        r"copyright",
        r"\u00a9",
        r"all rights reserved",
        r"printed in",
        r"oreilly\.com",
        r"o'reilly",
        r"isbn",
        r"chapter\s+\d+\s*\|",
        r"\|\s*chapter\s+\d+",
    ]
    return any(re.search(pattern, heading, flags=re.IGNORECASE) for pattern in patterns)


def is_repeated_chapter_marker(heading: str) -> bool:
    return bool(re.fullmatch(r"chapter\s+\d+", heading, flags=re.IGNORECASE))


def is_exercise_or_list_fragment(heading: str) -> bool:
    if re.fullmatch(r"\d{1,3}[.)]", heading):
        return True

    if re.match(r"^\d{1,3}[.)]\s+\S+", heading) and not re.match(
        r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})*\s+", heading
    ):
        return True

    return bool(re.fullmatch(r"\(?[a-zA-Z]\)", heading))


def is_bullet_or_marker(heading: str) -> bool:
    return bool(re.fullmatch(r"[\-\*\u2022\u25e6\u25aa\u2013\u2014\s]+", heading))


def has_too_much_punctuation(heading: str) -> bool:
    if any(character in heading for character in "<>{}[]`"):
        return True

    punctuation_count = sum(
        1 for character in heading if not character.isalnum() and not character.isspace()
    )
    return punctuation_count > 8 and punctuation_count / max(1, len(heading)) > 0.2


def is_code_fragment(heading: str) -> bool:
    lower_heading = heading.lower()
    code_prefixes = (
        "def ",
        "class ",
        "import ",
        "from ",
        "return ",
        "const ",
        "let ",
        "var ",
        "function ",
        "print(",
    )
    return bool(
        lower_heading.startswith(code_prefixes)
        or "```" in heading
        or re.search(r"[{}<>]=?|==|=>|::", heading)
    )


def is_caption_or_table_noise(heading: str, preview_after: str) -> bool:
    combined = f"{heading} {preview_after}".lower()
    caption_patterns = [
        r"^figure\s+\d",
        r"^fig\.\s*\d",
        r"^table\s+\d",
        r"^source:",
        r"\bcaption\b",
    ]
    if any(re.search(pattern, heading, flags=re.IGNORECASE) for pattern in caption_patterns):
        return True

    table_terms = [
        "% exposure",
        "pop.",
        "rank ",
        "score ",
        "benchmark",
        "dataset",
        "accuracy",
        "model number of parameters",
        "instruction group instruction",
    ]
    if any(term in combined for term in table_terms):
        return True

    if "," in heading and not re.search(r"^factor\s+\d+:", heading, flags=re.IGNORECASE):
        return True

    if re.search(r"\b(?:human|model|input|output|prompt|label|response)\b", heading, flags=re.IGNORECASE):
        if not re.search(r"[.!?]", preview_after):
            return True

    digit_count = sum(1 for character in heading if character.isdigit())
    if digit_count >= 3 and not heading.lower().startswith(("factor ", "step ")):
        return True

    if "%" in heading:
        return True

    return False


def is_formula_or_metric_noise(heading: str) -> bool:
    if re.search(r"[=×*/]", heading):
        return True

    if re.search(r"\b(?:PPL|BPB|BPC|ACC|FLOP|FLOPs|MFU|MBU|QPS|GB|TPU|GPU)\b", heading):
        return True

    return False


def is_generic_heading_without_title(heading: str) -> bool:
    lower_heading = heading.strip(":. ").casefold()
    if lower_heading in GENERIC_HEADINGS:
        return True

    match = re.match(r"^(example|answer|note|tip)\s*\d*[:.]?\s*(.*)$", lower_heading)
    return bool(match and not match.group(2).strip())


def is_sentence_fragment(heading: str) -> bool:
    words = heading.split()
    lower_heading = heading.lower()

    if not heading:
        return True

    if heading[0].islower():
        return True

    if heading.endswith((".", ",", ";")):
        return True

    if "," in heading and len(words) >= 6:
        return True

    if re.search(r"\)\s*,?\s+and\b", heading):
        return True

    if len(words) > 16:
        return True

    sentence_markers = (
        " because ",
        " however ",
        " whereas ",
        " although ",
        " while ",
    )
    return len(words) >= 9 and any(marker in lower_heading for marker in sentence_markers)


def has_enough_letters(heading: str) -> bool:
    return sum(1 for character in heading if character.isalpha()) >= 3


def is_low_value_short_phrase(candidate: dict, heading: str, repeated_count: int) -> bool:
    candidate_type = str(candidate.get("candidate_type") or "")
    words = heading.split()

    if candidate_type in {"numbered_heading", "question_heading"}:
        return False

    if has_body_text_after(candidate):
        return False

    if repeated_count > 1:
        return True

    return len(words) <= 2


def likely_real_high_confidence(candidate: dict) -> bool:
    candidate_type = str(candidate.get("candidate_type") or "")
    confidence = str(candidate.get("confidence") or "")
    return confidence == "high" and candidate_type in {
        "numbered_heading",
        "question_heading",
    }


def candidate_type_is_supported(candidate: dict, include_low_confidence: bool) -> bool:
    candidate_type = str(candidate.get("candidate_type") or "")
    if candidate_type in PREFERRED_TYPES:
        return True

    if candidate_type == "short_title_like_line":
        return True

    if candidate_type == "mostly_uppercase_short_line":
        return include_low_confidence

    if candidate_type == "weak_title_like_line":
        return include_low_confidence

    return False


def is_first_candidate_in_chapter(candidate: dict, first_candidate_id: Any) -> bool:
    return candidate.get("candidate_id") == first_candidate_id


def should_keep_candidate(
    candidate: dict,
    heading_counts: Counter[str],
    seen_headings: set[str],
    include_low_confidence: bool,
    first_candidate_id: Any,
) -> tuple[bool, str]:
    heading = normalize_text(str(candidate.get("normalized_heading") or candidate.get("line") or ""))
    heading_key = normalize_key(heading)
    confidence = str(candidate.get("confidence") or "low")
    preview_after = normalize_text(str(candidate.get("preview_after") or ""))
    repeated_count = heading_counts[heading_key]

    if heading_key in seen_headings:
        return False, "duplicate_in_chapter"

    if not confidence_is_allowed(confidence, include_low_confidence):
        return False, "confidence_below_minimum"

    if len(heading) < 3:
        return False, "too_short"

    if len(heading) > MAX_HEADING_LENGTH:
        return False, "too_long"

    if not has_enough_letters(heading):
        return False, "not_enough_letters"

    if is_url_or_email(heading):
        return False, "url_or_email"

    if is_page_label(heading):
        return False, "page_label"

    if is_header_or_footer(heading):
        return False, "header_or_footer"

    if is_repeated_chapter_marker(heading):
        return False, "repeated_chapter_marker"

    if is_exercise_or_list_fragment(heading):
        return False, "exercise_or_list_fragment"

    if is_bullet_or_marker(heading):
        return False, "bullet_or_marker"

    if has_too_much_punctuation(heading):
        return False, "too_much_punctuation"

    if is_code_fragment(heading):
        return False, "code_fragment"

    if is_caption_or_table_noise(heading, preview_after):
        return False, "caption_or_table_noise"

    if is_formula_or_metric_noise(heading):
        return False, "formula_or_metric_noise"

    if is_generic_heading_without_title(heading):
        return False, "generic_heading"

    if repeated_count > 2:
        return False, "repeated_too_often_in_chapter"

    if not candidate_type_is_supported(candidate, include_low_confidence):
        return False, "candidate_type_not_supported"

    if not likely_real_high_confidence(candidate):
        if not has_body_text_after(candidate):
            return False, "missing_body_text_after"

        if is_sentence_fragment(heading):
            return False, "sentence_fragment"

        if is_low_value_short_phrase(candidate, heading, repeated_count):
            return False, "isolated_short_phrase"

        if str(candidate.get("candidate_type")) == "short_title_like_line":
            words = heading.split()
            if not is_first_candidate_in_chapter(candidate, first_candidate_id) and (
                len(words) > 5 or "," in heading
            ):
                return False, "short_title_like_noise"

    seen_headings.add(heading_key)
    return True, "kept"


def outline_level_for(candidate: dict) -> str:
    candidate_type = str(candidate.get("candidate_type") or "")
    if candidate_type == "numbered_heading":
        return "numbered_section"

    if candidate_type == "question_heading":
        return "topic_question"

    return "section_or_topic"


def build_outline_entry(candidate: dict, position: int, keep_reason: str) -> dict:
    return {
        "position": position,
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
        "outline_level": outline_level_for(candidate),
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


def count_headings_for_chapter(candidates: list[dict]) -> Counter[str]:
    return Counter(
        normalize_key(
            str(candidate.get("normalized_heading") or candidate.get("line") or "")
        )
        for candidate in candidates
    )


def build_outline_for_chapter(
    chapter: dict,
    include_low_confidence: bool,
    max_per_chapter: int,
) -> tuple[list[dict], list[dict]]:
    candidates = chapter.get("candidates") or []
    heading_counts = count_headings_for_chapter(candidates)
    first_candidate_id = candidates[0].get("candidate_id") if candidates else None
    seen_headings: set[str] = set()
    outline = []
    excluded = []

    for candidate in candidates:
        keep, reason = should_keep_candidate(
            candidate=candidate,
            heading_counts=heading_counts,
            seen_headings=seen_headings,
            include_low_confidence=include_low_confidence,
            first_candidate_id=first_candidate_id,
        )

        if keep and max_per_chapter > 0 and len(outline) >= max_per_chapter:
            keep = False
            reason = "max_per_chapter_reached"

        if keep:
            outline.append(
                build_outline_entry(
                    candidate=candidate,
                    position=len(outline) + 1,
                    keep_reason=reason,
                )
            )
        else:
            excluded.append(build_excluded_entry(candidate, reason))

    return outline, excluded


def build_section_outline(
    candidates_report: dict,
    include_low_confidence: bool,
    max_per_chapter: int,
) -> tuple[list[dict], list[dict]]:
    chapters = []
    all_excluded = []

    for chapter in candidates_report["chapters"]:
        outline, excluded = build_outline_for_chapter(
            chapter=chapter,
            include_low_confidence=include_low_confidence,
            max_per_chapter=max_per_chapter,
        )
        all_excluded.extend(excluded)
        chapters.append(
            {
                "chapter": chapter.get("chapter"),
                "chapter_number": chapter.get("chapter_number"),
                "input_candidate_count": len(chapter.get("candidates") or []),
                "outline_count": len(outline),
                "outline": outline,
            }
        )

    return chapters, all_excluded


def count_outline_items(chapters: list[dict]) -> int:
    return sum(chapter["outline_count"] for chapter in chapters)


def build_report(
    candidates_path: Path,
    candidates_report: dict,
    chapters: list[dict],
    excluded: list[dict],
    include_low_confidence: bool,
    max_per_chapter: int,
) -> dict:
    kept_type_counts = Counter(
        item["candidate_type"]
        for chapter in chapters
        for item in chapter["outline"]
    )
    excluded_reason_counts = Counter(item["reason"] for item in excluded)
    input_candidate_count = candidates_report.get("candidate_count")
    if not isinstance(input_candidate_count, int):
        input_candidate_count = sum(
            len(chapter.get("candidates") or [])
            for chapter in candidates_report["chapters"]
        )

    outline_count = count_outline_items(chapters)

    return {
        "source_candidates_file": str(candidates_path),
        "source_chunks_file": candidates_report.get("source_chunks_file"),
        "input_candidate_count": input_candidate_count,
        "outline_count": outline_count,
        "excluded_count": input_candidate_count - outline_count,
        "include_low_confidence": include_low_confidence,
        "max_per_chapter": max_per_chapter,
        "max_heading_length": MAX_HEADING_LENGTH,
        "kept_candidate_type_counts": dict(sorted(kept_type_counts.items())),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "chapters": chapters,
        "excluded_candidates": excluded,
    }


def format_text_report(report: dict) -> str:
    lines = [
        "PDF Section Outline",
        "=" * 80,
        f"Source candidates file: {report['source_candidates_file']}",
        f"Source chunks file: {report['source_chunks_file']}",
        f"Input candidate count: {report['input_candidate_count']}",
        f"Outline count: {report['outline_count']}",
        f"Excluded count: {report['excluded_count']}",
        f"Include low confidence: {report['include_low_confidence']}",
        f"Max per chapter: {report['max_per_chapter']}",
        f"Max heading length: {report['max_heading_length']}",
        "",
        "KEPT CANDIDATE TYPE COUNTS",
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

        if not chapter["outline"]:
            lines.append("No outline entries kept.")
            continue

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
                "  Chunk: {chunk_id} | Candidate: {candidate_id} | Type: {candidate_type}".format(
                    chunk_id=item["chunk_id"],
                    candidate_id=item["candidate_id"],
                    candidate_type=item["candidate_type"],
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
    json_output_path = EXTRACTED_DIR / f"{stem}.section_outline.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.section_outline.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def print_summary(report: dict, json_output_path: Path, txt_output_path: Path) -> None:
    print("PDF section outline report created.")
    print(f"Source candidates file: {report['source_candidates_file']}")
    print(f"Source chunks file: {report['source_chunks_file']}")
    print(f"Input candidate count: {report['input_candidate_count']}")
    print(f"Outline count: {report['outline_count']}")
    print(f"Excluded count: {report['excluded_count']}")
    print(f"Include low confidence: {report['include_low_confidence']}")
    print(f"Max per chapter: {report['max_per_chapter']}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    candidates_path = Path(args.section_topic_candidates_path)
    candidates_report = load_candidates_report(candidates_path)
    chapters, excluded = build_section_outline(
        candidates_report=candidates_report,
        include_low_confidence=args.include_low_confidence,
        max_per_chapter=args.max_per_chapter,
    )
    report = build_report(
        candidates_path=candidates_path,
        candidates_report=candidates_report,
        chapters=chapters,
        excluded=excluded,
        include_low_confidence=args.include_low_confidence,
        max_per_chapter=args.max_per_chapter,
    )
    json_output_path, txt_output_path = write_report(candidates_path, report)
    print_summary(report, json_output_path, txt_output_path)


if __name__ == "__main__":
    main()
