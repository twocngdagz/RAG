import argparse
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")
DEFAULT_MAX_PER_CHAPTER = 12
MAX_HEADING_LENGTH = 140
MIN_HEADING_LENGTH = 8
GENERIC_HEADINGS = {
    "activity",
    "answer",
    "answers",
    "example",
    "examples",
    "exercise",
    "exercises",
    "note",
    "notes",
    "question",
    "questions",
    "review",
    "summary",
    "tip",
    "tips",
}
QUESTION_STARTERS = (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a strict per-chapter section/topic outline from PDF candidates."
    )
    parser.add_argument(
        "section_topic_candidates_path",
        help="Path to a section/topic candidates JSON report.",
    )
    parser.add_argument(
        "--max-per-chapter",
        type=int,
        default=DEFAULT_MAX_PER_CHAPTER,
        help=f"Maximum strict outline entries to keep per chapter. Defaults to {DEFAULT_MAX_PER_CHAPTER}.",
    )
    parser.add_argument(
        "--include-medium",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include medium-confidence numbered/question candidates. Defaults to true.",
    )
    parser.add_argument(
        "--high-only",
        action="store_true",
        help="Keep only high-confidence candidates.",
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


def normalized_heading(candidate: dict) -> str:
    return normalize_text(
        str(candidate.get("normalized_heading") or candidate.get("line") or "")
    )


def normalize_key(value: str) -> str:
    normalized = normalize_text(value).casefold()
    normalized = re.sub(r"[\u2018\u2019]", "'", normalized)
    normalized = re.sub(r"[\u201c\u201d]", '"', normalized)
    return normalized


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


def is_file_name_or_page_label(heading: str) -> bool:
    return bool(
        heading.lower().endswith((".pdf", ".txt", ".json", ".py"))
        or re.fullmatch(r"(?:page\s*)?\d{1,4}", heading, flags=re.IGNORECASE)
        or re.search(r"^\d{1,4}\s*\|", heading)
        or re.search(r"\|\s*\d{1,4}$", heading)
    )


def has_mostly_punctuation(heading: str) -> bool:
    if any(character in heading for character in "<>{}[]`"):
        return True

    punctuation_count = sum(
        1 for character in heading if not character.isalnum() and not character.isspace()
    )
    alpha_numeric_count = sum(1 for character in heading if character.isalnum())
    if alpha_numeric_count == 0:
        return True

    return punctuation_count > 8 and punctuation_count / len(heading) > 0.2


def is_code_fragment(heading: str) -> bool:
    lower_heading = heading.lower()
    code_prefixes = (
        "class ",
        "const ",
        "def ",
        "from ",
        "function ",
        "import ",
        "let ",
        "print(",
        "return ",
        "var ",
    )
    return bool(
        lower_heading.startswith(code_prefixes)
        or "```" in heading
        or re.search(r"[{}<>]=?|==|=>|::", heading)
    )


def is_exercise_or_numbered_question(heading: str) -> bool:
    if re.fullmatch(r"\d{1,3}[.)]", heading):
        return True

    if re.match(r"^\d{1,3}[.)]\s+\S+", heading) and not re.match(
        r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})*\s+\S+", heading
    ):
        return True

    return bool(re.fullmatch(r"\(?[a-zA-Z]\)", heading))


def is_generic_heading_without_title(heading: str) -> bool:
    lower_heading = heading.strip(":. ").casefold()
    if lower_heading in GENERIC_HEADINGS:
        return True

    match = re.match(
        r"^(activity|answer|example|exercise|note|question|review|summary|tip)\s*\d*[:.]?\s*(.*)$",
        lower_heading,
    )
    if not match:
        return False

    title = match.group(2).strip()
    return len(title) < 5 or sum(1 for character in title if character.isalpha()) < 3


def is_formula_or_numeric_noise(heading: str) -> bool:
    if re.search(r"[=×*/]", heading):
        return True

    if re.search(r"\b(?:PPL|BPB|BPC|ACC|FLOP|FLOPs|MFU|MBU|QPS|GB|TPU|GPU)\b", heading):
        return True

    digit_count = sum(1 for character in heading if character.isdigit())
    alpha_count = sum(1 for character in heading if character.isalpha())
    if digit_count >= 3 and alpha_count <= 12:
        return True

    if "%" in heading:
        return True

    return False


def is_caption_or_table_noise(heading: str, preview_after: str) -> bool:
    combined = f"{heading} {preview_after}".lower()
    table_terms = [
        "% exposure",
        "accuracy",
        "benchmark",
        "caption",
        "dataset",
        "instruction group instruction",
        "model number of parameters",
        "pop.",
        "rank ",
        "score ",
        "source:",
    ]
    return bool(
        re.match(r"^(figure|fig\.|table)\s+\d", heading, flags=re.IGNORECASE)
        or any(term in combined for term in table_terms)
    )


def is_weak_short_title_like(candidate: dict) -> bool:
    return str(candidate.get("candidate_type") or "") in {
        "short_title_like_line",
        "weak_title_like_line",
    }


def is_mostly_uppercase_non_title(candidate: dict, heading: str) -> bool:
    if str(candidate.get("candidate_type") or "") != "mostly_uppercase_short_line":
        return False

    words = heading.split()
    return not (2 <= len(words) <= 8 and has_body_text_after(candidate))


def is_question_example_noise(heading: str, preview_after: str) -> bool:
    lower_combined = f"{heading} {preview_after}".lower()
    example_terms = {
        "animal",
        "animals",
        "cats",
        "dogs",
        "dolphins",
        "sharks",
    }
    return any(term in lower_combined for term in example_terms)


def numbered_heading_title(heading: str) -> str | None:
    match = re.match(
        r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})*\.?\s+(?P<title>.+)$",
        heading,
    )
    if not match:
        return None

    title = normalize_text(match.group("title"))
    if len(title) < 5:
        return None

    if sum(1 for character in title if character.isalpha()) < 3:
        return None

    if title[0].islower():
        return None

    return title


def is_valid_question_heading(heading: str) -> bool:
    if not heading.endswith("?"):
        return False

    if not heading[:1].isupper():
        return False

    words = heading.split()
    if not 3 <= len(words) <= 18:
        return False

    return heading.lower().startswith(QUESTION_STARTERS)


def passes_common_strict_exclusions(candidate: dict) -> tuple[bool, str]:
    heading = normalized_heading(candidate)
    preview_after = normalize_text(str(candidate.get("preview_after") or ""))

    if len(heading) < MIN_HEADING_LENGTH:
        return False, "too_short"

    if len(heading) > MAX_HEADING_LENGTH:
        return False, "too_long"

    if is_url_or_email(heading):
        return False, "url_or_email"

    if is_file_name_or_page_label(heading):
        return False, "file_name_or_page_label"

    if has_mostly_punctuation(heading):
        return False, "mostly_punctuation"

    if is_code_fragment(heading):
        return False, "code_fragment"

    if is_exercise_or_numbered_question(heading):
        return False, "exercise_or_numbered_question"

    if is_generic_heading_without_title(heading):
        return False, "generic_heading"

    if is_formula_or_numeric_noise(heading):
        return False, "formula_or_numeric_noise"

    if is_caption_or_table_noise(heading, preview_after):
        return False, "caption_or_table_noise"

    if is_weak_short_title_like(candidate):
        return False, "weak_short_title_like"

    if is_mostly_uppercase_non_title(candidate, heading):
        return False, "mostly_uppercase_non_title"

    return True, "passed_common_exclusions"


def should_keep_candidate(
    candidate: dict,
    seen_headings: set[str],
    include_medium: bool,
) -> tuple[bool, str]:
    heading = normalized_heading(candidate)
    heading_key = normalize_key(heading)
    candidate_type = str(candidate.get("candidate_type") or "")
    confidence = str(candidate.get("confidence") or "")
    preview_after = normalize_text(str(candidate.get("preview_after") or ""))

    if heading_key in seen_headings:
        return False, "duplicate_in_chapter"

    passes_exclusions, exclusion_reason = passes_common_strict_exclusions(candidate)
    if not passes_exclusions:
        return False, exclusion_reason

    if candidate_type == "numbered_heading":
        if not numbered_heading_title(heading):
            return False, "numbered_heading_without_meaningful_title"

        if confidence == "high":
            seen_headings.add(heading_key)
            return True, "high_confidence_numbered_heading"

        if include_medium and confidence == "medium":
            seen_headings.add(heading_key)
            return True, "medium_numbered_heading_with_title"

        return False, "numbered_heading_confidence_not_allowed"

    if candidate_type == "question_heading":
        if not is_valid_question_heading(heading):
            return False, "invalid_question_heading"

        if is_question_example_noise(heading, preview_after):
            return False, "question_example_noise"

        if confidence == "high":
            seen_headings.add(heading_key)
            return True, "high_confidence_question_heading"

        if include_medium and confidence == "medium" and has_body_text_after(candidate):
            seen_headings.add(heading_key)
            return True, "medium_question_heading_with_body"

        return False, "question_heading_confidence_not_allowed"

    return False, "candidate_type_not_allowed"


def build_outline_entry(candidate: dict, position: int, keep_reason: str) -> dict:
    heading = normalized_heading(candidate)
    return {
        "position": position,
        "candidate_id": candidate.get("candidate_id"),
        "chunk_id": candidate.get("chunk_id"),
        "page_start": candidate.get("page_start"),
        "page_end": candidate.get("page_end"),
        "heading": heading,
        "normalized_heading": heading,
        "candidate_type": candidate.get("candidate_type"),
        "confidence": candidate.get("confidence"),
        "line_number": candidate.get("line_number"),
        "keep_reason": keep_reason,
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
        "heading": normalized_heading(candidate),
        "candidate_type": candidate.get("candidate_type"),
        "confidence": candidate.get("confidence"),
        "reason": reason,
    }


def build_chapter_outline(
    chapter: dict,
    include_medium: bool,
    max_per_chapter: int,
) -> tuple[dict, list[dict]]:
    seen_headings: set[str] = set()
    outline = []
    excluded = []

    for candidate in chapter.get("candidates") or []:
        keep, reason = should_keep_candidate(
            candidate=candidate,
            seen_headings=seen_headings,
            include_medium=include_medium,
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

    return (
        {
            "chapter": chapter.get("chapter"),
            "chapter_number": chapter.get("chapter_number"),
            "input_candidate_count": len(chapter.get("candidates") or []),
            "outline_count": len(outline),
            "outline": outline,
        },
        excluded,
    )


def build_strict_outline(
    candidates_report: dict,
    include_medium: bool,
    max_per_chapter: int,
) -> tuple[list[dict], list[dict]]:
    chapters = []
    excluded = []

    for chapter in candidates_report["chapters"]:
        chapter_outline, chapter_excluded = build_chapter_outline(
            chapter=chapter,
            include_medium=include_medium,
            max_per_chapter=max_per_chapter,
        )
        chapters.append(chapter_outline)
        excluded.extend(chapter_excluded)

    return chapters, excluded


def strict_outline_count(chapters: list[dict]) -> int:
    return sum(chapter["outline_count"] for chapter in chapters)


def build_report(
    candidates_path: Path,
    candidates_report: dict,
    chapters: list[dict],
    excluded: list[dict],
    include_medium: bool,
    high_only: bool,
    max_per_chapter: int,
) -> dict:
    input_candidate_count = candidates_report.get("candidate_count")
    if not isinstance(input_candidate_count, int):
        input_candidate_count = sum(
            len(chapter.get("candidates") or [])
            for chapter in candidates_report["chapters"]
        )

    kept_type_counts = Counter(
        item["candidate_type"]
        for chapter in chapters
        for item in chapter["outline"]
    )
    excluded_reason_counts = Counter(item["reason"] for item in excluded)
    outline_count = strict_outline_count(chapters)

    return {
        "source_candidates_file": str(candidates_path),
        "source_chunks_file": candidates_report.get("source_chunks_file"),
        "input_candidate_count": input_candidate_count,
        "strict_outline_count": outline_count,
        "excluded_count": input_candidate_count - outline_count,
        "include_medium": include_medium,
        "high_only": high_only,
        "max_per_chapter": max_per_chapter,
        "max_heading_length": MAX_HEADING_LENGTH,
        "kept_candidate_type_counts": dict(sorted(kept_type_counts.items())),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "chapters": chapters,
        "excluded_candidates": excluded,
    }


def format_text_report(report: dict) -> str:
    lines = [
        "PDF Strict Section Outline",
        "=" * 80,
        f"Source candidates file: {report['source_candidates_file']}",
        f"Source chunks file: {report['source_chunks_file']}",
        f"Input candidate count: {report['input_candidate_count']}",
        f"Strict outline count: {report['strict_outline_count']}",
        f"Excluded count: {report['excluded_count']}",
        f"Include medium: {report['include_medium']}",
        f"High only: {report['high_only']}",
        f"Max per chapter: {report['max_per_chapter']}",
        "",
        "KEPT CANDIDATE TYPE COUNTS",
        "-" * 80,
    ]

    for candidate_type, count in report["kept_candidate_type_counts"].items():
        lines.append(f"{candidate_type}: {count}")

    lines.extend(["", "EXCLUDED REASON COUNTS", "-" * 80])
    for reason, count in report["excluded_reason_counts"].items():
        lines.append(f"{reason}: {count}")

    lines.extend(["", "STRICT OUTLINE", "=" * 80])

    for chapter in report["chapters"]:
        chapter_title = chapter["chapter"] or "FRONT MATTER"
        lines.extend(["", chapter_title, "-" * len(chapter_title)])

        if not chapter["outline"]:
            lines.append("No strict outline entries kept.")
            continue

        for item in chapter["outline"]:
            lines.append(
                "Page {page_start} | {confidence} | {candidate_type} | {heading}".format(
                    page_start=item["page_start"],
                    confidence=item["confidence"],
                    candidate_type=item["candidate_type"],
                    heading=item["heading"],
                )
            )
            if item.get("preview_after"):
                lines.append(f"  After: {item['preview_after']}")

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

    return "\n".join(lines)


def write_report(candidates_path: Path, report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(candidates_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.strict_section_outline.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.strict_section_outline.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def print_summary(report: dict, json_output_path: Path, txt_output_path: Path) -> None:
    print("PDF strict section outline report created.")
    print(f"Source candidates file: {report['source_candidates_file']}")
    print(f"Source chunks file: {report['source_chunks_file']}")
    print(f"Input candidate count: {report['input_candidate_count']}")
    print(f"Strict outline count: {report['strict_outline_count']}")
    print(f"Excluded count: {report['excluded_count']}")
    print(f"Include medium: {report['include_medium']}")
    print(f"High only: {report['high_only']}")
    print(f"Max per chapter: {report['max_per_chapter']}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    candidates_path = Path(args.section_topic_candidates_path)
    include_medium = bool(args.include_medium and not args.high_only)
    candidates_report = load_candidates_report(candidates_path)
    chapters, excluded = build_strict_outline(
        candidates_report=candidates_report,
        include_medium=include_medium,
        max_per_chapter=args.max_per_chapter,
    )
    report = build_report(
        candidates_path=candidates_path,
        candidates_report=candidates_report,
        chapters=chapters,
        excluded=excluded,
        include_medium=include_medium,
        high_only=args.high_only,
        max_per_chapter=args.max_per_chapter,
    )
    json_output_path, txt_output_path = write_report(candidates_path, report)
    print_summary(report, json_output_path, txt_output_path)


if __name__ == "__main__":
    main()
