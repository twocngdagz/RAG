import argparse
import json
import re
from pathlib import Path


EXTRACTED_DIR = Path("extracted")
HIGH_CONFIDENCE_RULES = {"starts_with_chapter"}
MEDIUM_CONFIDENCE_RULES = {"numbered_heading", "mostly_uppercase_short_line"}
LOW_CONFIDENCE_RULES = {"short_title_like_line"}
ALLOWED_DEFAULT_RULES = HIGH_CONFIDENCE_RULES | MEDIUM_CONFIDENCE_RULES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reduce noisy PDF heading candidates into a cleaner outline."
    )
    parser.add_argument(
        "candidates_path",
        help="Path to a structure candidates JSON file.",
    )
    parser.add_argument(
        "--include-low-confidence",
        action="store_true",
        help="Include short_title_like_line candidates in the outline.",
    )
    parser.add_argument(
        "--max-heading-length",
        type=int,
        default=120,
        help="Maximum heading length to keep. Defaults to 120.",
    )
    return parser.parse_args()


def load_report(candidates_path: Path) -> dict:
    if not candidates_path.exists():
        raise SystemExit(f"Structure candidates file does not exist: {candidates_path}")

    if not candidates_path.is_file():
        raise SystemExit(f"Structure candidates path is not a file: {candidates_path}")

    with candidates_path.open("r", encoding="utf-8") as file:
        report = json.load(file)

    if not isinstance(report, dict):
        raise SystemExit("Structure candidates JSON must contain a top-level object.")

    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        raise SystemExit("Structure candidates JSON must contain a candidates array.")

    return report


def output_stem(candidates_path: Path) -> str:
    if candidates_path.name.endswith(".structure_candidates.json"):
        return candidates_path.name[: -len(".structure_candidates.json")]

    return candidates_path.stem


def normalize_heading(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def clean_heading_for_rule(rule: str, heading: str) -> str:
    if rule == "numbered_heading" and is_toc_numbered_heading(heading):
        heading = re.sub(r"\s*(?:\.\s*){3,}\s*\d+\s*$", "", heading)

    return normalize_heading(heading)


def is_standalone_page_number(heading: str) -> bool:
    return bool(re.fullmatch(r"(?:page\s*)?\d{1,4}", heading, flags=re.IGNORECASE))


def is_url_or_email(heading: str) -> bool:
    return bool(
        re.search(r"https?://|www\.|\S+@\S+\.\S+", heading, flags=re.IGNORECASE)
    )


def is_footer_like(heading: str) -> bool:
    footer_patterns = [
        r"copyright",
        r"©",
        r"all rights reserved",
        r"printed in",
        r"oreilly\.com",
        r"o'reilly",
        r"isbn",
        r"us\s*\$",
        r"can\s*\$",
    ]
    return any(re.search(pattern, heading, flags=re.IGNORECASE) for pattern in footer_patterns)


def has_too_many_punctuation_symbols(heading: str) -> bool:
    punctuation_count = sum(
        1 for character in heading if not character.isalnum() and not character.isspace()
    )
    return punctuation_count > 6 or (
        len(heading) > 0 and punctuation_count / len(heading) > 0.25
    )


def is_repeated_file_name(heading: str, source_file: str | None) -> bool:
    if not source_file:
        return False

    source_name = Path(source_file).name.lower()
    source_stem = Path(source_file).stem.lower()
    normalized_heading = heading.lower()
    return normalized_heading in {source_name, source_stem}


def is_numeric_noise(heading: str) -> bool:
    compact = re.sub(r"\s+", "", heading)
    if not compact:
        return True

    digit_count = sum(1 for character in compact if character.isdigit())
    alpha_count = sum(1 for character in compact if character.isalpha())
    return digit_count >= 4 and alpha_count == 0


def is_running_header(heading: str) -> bool:
    return bool(
        re.search(r"^\d+\s*\|\s*chapter\b", heading, flags=re.IGNORECASE)
        or re.search(r"\bchapter\s+\d+:", heading, flags=re.IGNORECASE)
        and "|" in heading
    )


def is_toc_numbered_heading(heading: str) -> bool:
    return bool(re.match(r"^\d+\.\s+.+(?:\.\s*){3,}\s*\d+\s*$", heading))


def is_decimal_section_heading(heading: str) -> bool:
    return bool(re.match(r"^\d{1,2}\.\d{1,2}(?:\.\d{1,2})*\s+[A-Z]", heading))


def is_actual_chapter_heading(heading: str) -> bool:
    return bool(
        re.match(r"^chapter\s+\d+$", heading, flags=re.IGNORECASE)
        or re.match(r"^chapter\s+\d+\s*[:\-]\s+\S+", heading, flags=re.IGNORECASE)
    )


def is_allowed_numbered_heading(heading: str) -> bool:
    return is_toc_numbered_heading(heading) or is_decimal_section_heading(heading)


def is_allowed_uppercase_heading(heading: str) -> bool:
    return bool(re.match(r"^CHAPTER\s+\d+\b", heading))


def is_allowed_rule_specific_heading(
    rule: str,
    original_heading: str,
    cleaned_heading: str,
) -> bool:
    if rule == "starts_with_chapter":
        return is_actual_chapter_heading(cleaned_heading)

    if rule == "numbered_heading":
        return is_allowed_numbered_heading(original_heading)

    if rule == "mostly_uppercase_short_line":
        return is_allowed_uppercase_heading(cleaned_heading)

    return True


def should_keep_heading(
    candidate: dict,
    allowed_rules: set[str],
    max_heading_length: int,
    source_file: str | None,
    seen_headings: set[str],
) -> tuple[bool, str]:
    rule = candidate.get("rule")
    original_heading = normalize_heading(str(candidate.get("line") or ""))
    heading = clean_heading_for_rule(str(rule), original_heading)

    if rule not in allowed_rules:
        return False, "rule_not_allowed"

    if len(heading) < 3:
        return False, "too_short"

    if len(heading) > max_heading_length:
        return False, "too_long"

    if is_standalone_page_number(heading):
        return False, "standalone_page_number"

    if is_url_or_email(heading):
        return False, "url_or_email"

    if is_footer_like(heading):
        return False, "footer_like"

    if has_too_many_punctuation_symbols(heading):
        return False, "too_much_punctuation"

    if is_repeated_file_name(heading, source_file):
        return False, "repeated_file_name"

    if is_numeric_noise(heading):
        return False, "numeric_noise"

    if is_running_header(heading):
        return False, "running_header"

    if not is_allowed_rule_specific_heading(str(rule), original_heading, heading):
        return False, "rule_specific_noise"

    normalized_key = heading.casefold()
    if normalized_key in seen_headings:
        return False, "duplicate"

    seen_headings.add(normalized_key)
    return True, heading


def confidence_for_rule(rule: str) -> str:
    if rule in HIGH_CONFIDENCE_RULES:
        return "high"

    if rule in MEDIUM_CONFIDENCE_RULES:
        return "medium"

    return "low"


def build_outline(report: dict, include_low_confidence: bool, max_heading_length: int) -> list[dict]:
    allowed_rules = set(ALLOWED_DEFAULT_RULES)
    if include_low_confidence:
        allowed_rules |= LOW_CONFIDENCE_RULES

    source_file = report.get("source_chunks_file")
    seen_headings: set[str] = set()
    outline = []

    for candidate in report["candidates"]:
        keep, heading_or_reason = should_keep_heading(
            candidate=candidate,
            allowed_rules=allowed_rules,
            max_heading_length=max_heading_length,
            source_file=source_file,
            seen_headings=seen_headings,
        )

        if not keep:
            continue

        rule = candidate["rule"]
        outline.append(
            {
                "position": len(outline) + 1,
                "chunk_id": candidate.get("chunk_id"),
                "page_start": candidate.get("page_start"),
                "page_end": candidate.get("page_end"),
                "heading": heading_or_reason,
                "rule": rule,
                "confidence": confidence_for_rule(rule),
                "preview": candidate.get("preview"),
            }
        )

    return outline


def build_output_report(
    candidates_path: Path,
    report: dict,
    outline: list[dict],
    include_low_confidence: bool,
    max_heading_length: int,
) -> dict:
    return {
        "source_candidates_file": str(candidates_path),
        "source_chunks_file": report.get("source_chunks_file"),
        "input_candidate_count": report.get("candidate_count"),
        "outline_count": len(outline),
        "include_low_confidence": include_low_confidence,
        "max_heading_length": max_heading_length,
        "outline": outline,
    }


def format_text_report(output_report: dict) -> str:
    lines = [
        "PDF Outline Candidates",
        "=" * 80,
        f"Source candidates file: {output_report['source_candidates_file']}",
        f"Source chunks file: {output_report['source_chunks_file']}",
        f"Input candidate count: {output_report['input_candidate_count']}",
        f"Outline count: {output_report['outline_count']}",
        f"Include low confidence: {output_report['include_low_confidence']}",
        f"Max heading length: {output_report['max_heading_length']}",
        "",
    ]

    for item in output_report["outline"]:
        lines.append(
            f"Page {item['page_start']} | {item['confidence']} | {item['heading']}"
        )
        lines.append(f"  Chunk: {item['chunk_id']} | Rule: {item['rule']}")
        if item.get("preview"):
            lines.append(f"  Preview: {item['preview']}")
        lines.append("")

    return "\n".join(lines)


def write_report(candidates_path: Path, output_report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(candidates_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.outline_candidates.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.outline_candidates.txt"

    json_output_path.write_text(
        json.dumps(output_report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(output_report), encoding="utf-8")

    return json_output_path, txt_output_path


def main() -> None:
    args = parse_args()
    candidates_path = Path(args.candidates_path)
    report = load_report(candidates_path)
    outline = build_outline(
        report=report,
        include_low_confidence=args.include_low_confidence,
        max_heading_length=args.max_heading_length,
    )
    output_report = build_output_report(
        candidates_path=candidates_path,
        report=report,
        outline=outline,
        include_low_confidence=args.include_low_confidence,
        max_heading_length=args.max_heading_length,
    )
    json_output_path, txt_output_path = write_report(candidates_path, output_report)

    print("PDF outline candidate report created.")
    print(f"Source candidates file: {candidates_path}")
    print(f"Input candidate count: {report.get('candidate_count')}")
    print(f"Outline count: {len(outline)}")
    print(f"Include low confidence: {args.include_low_confidence}")
    print(f"Max heading length: {args.max_heading_length}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


if __name__ == "__main__":
    main()
