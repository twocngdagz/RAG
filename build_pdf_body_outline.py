import argparse
import json
import re
from pathlib import Path


EXTRACTED_DIR = Path("extracted")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter PDF outline candidates down to likely in-body outline markers."
    )
    parser.add_argument("outline_path", help="Path to an outline candidates JSON file.")
    parser.add_argument("chunks_path", help="Path to the source chunks JSON file.")
    parser.add_argument(
        "--keep-toc",
        action="store_true",
        help="Include likely TOC entries in body_outline for debugging with is_toc=true.",
    )
    return parser.parse_args()


def load_json_file(path: Path):
    if not path.exists():
        raise SystemExit(f"Required file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"Path is not a file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_outline_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise SystemExit("Outline JSON must contain a top-level object.")

    if not isinstance(report.get("outline"), list):
        raise SystemExit("Outline JSON must contain an outline array.")


def validate_chunks(chunks: list) -> None:
    if not isinstance(chunks, list):
        raise SystemExit("Chunks JSON must contain a top-level array.")


def output_stem(outline_path: Path) -> str:
    if outline_path.name.endswith(".outline_candidates.json"):
        return outline_path.name[: -len(".outline_candidates.json")]

    return outline_path.stem


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def chunk_lookup(chunks: list[dict]) -> dict[str, dict]:
    return {chunk.get("id"): chunk for chunk in chunks}


def first_body_chapter_page(outline: list[dict]) -> int | None:
    pages = [
        item.get("page_start")
        for item in outline
        if re.fullmatch(r"CHAPTER\s+\d+", str(item.get("heading") or ""))
        and isinstance(item.get("page_start"), int)
    ]
    return min(pages) if pages else None


def count_chapter_like_lines(text: str) -> int:
    patterns = [
        r"\b\d+\.\s+[A-Z][A-Za-z].*?(?:\.\s*){3,}\s*\d+\b",
        r"\bCHAPTER\s+\d+\b",
        r"\bChapter\s+\d+\b",
    ]
    return sum(len(re.findall(pattern, text)) for pattern in patterns)


def looks_like_chapter_listing(heading: str, preview: str, chunk_text: str) -> bool:
    if re.match(r"^\d+\.\s+\S+", heading) and re.search(
        r"(?:\.\s*){3,}\s*\d+\b", preview + " " + chunk_text
    ):
        return True

    return False


def is_body_chapter_heading(heading: str) -> bool:
    return bool(
        re.fullmatch(r"CHAPTER\s+\d+", heading)
        or re.fullmatch(r"Chapter\s+\d+", heading)
        or re.match(r"^Chapter\s+\d+\s*[:\-]\s+\S+", heading)
    )


def heading_is_standalone_in_chunk(heading: str, chunk_text: str) -> bool:
    return any(line.strip() == heading for line in chunk_text.splitlines())


def preview_looks_like_body(preview: str) -> bool:
    normalized_preview = preview.lower()
    return not (
        "table of contents" in normalized_preview
        or normalized_preview.startswith("table of contents")
        or re.search(r"(?:\.\s*){3,}\s*\d+\b", preview)
    )


def classify_outline_item(
    item: dict,
    chunk: dict | None,
    first_body_page: int | None,
) -> tuple[bool, str]:
    heading = normalize_text(str(item.get("heading") or ""))
    preview = normalize_text(str(item.get("preview") or ""))
    chunk_text = str((chunk or {}).get("text") or "")
    normalized_chunk_text = chunk_text.lower()
    page_start = item.get("page_start")

    if "table of contents" in normalized_chunk_text or "contents" in normalized_chunk_text:
        return True, "likely_table_of_contents"

    if count_chapter_like_lines(chunk_text) >= 3:
        return True, "many_chapter_lines_close_together"

    if first_body_page is not None and isinstance(page_start, int) and page_start < first_body_page:
        return True, "before_first_body_chapter_marker"

    if looks_like_chapter_listing(heading, preview, chunk_text):
        return True, "chapter_listing_with_page_references"

    if (
        first_body_page is not None
        and isinstance(page_start, int)
        and page_start <= first_body_page
        and not is_body_chapter_heading(heading)
    ):
        return True, "early_duplicate_or_toc_like_entry"

    if is_body_chapter_heading(heading) and (
        heading_is_standalone_in_chunk(heading, chunk_text)
        or preview_looks_like_body(preview)
    ):
        return False, "likely_body_chapter_marker"

    return True, "not_likely_body_marker"


def build_body_outline(
    outline_report: dict,
    chunks: list[dict],
    keep_toc: bool,
) -> tuple[list[dict], list[dict]]:
    chunks_by_id = chunk_lookup(chunks)
    source_outline = outline_report["outline"]
    first_body_page = first_body_chapter_page(source_outline)
    body_outline = []
    excluded_toc_entries = []

    for item in source_outline:
        chunk = chunks_by_id.get(item.get("chunk_id"))
        is_toc, reason = classify_outline_item(item, chunk, first_body_page)
        entry = {
            "chunk_id": item.get("chunk_id"),
            "page_start": item.get("page_start"),
            "page_end": item.get("page_end"),
            "heading": item.get("heading"),
            "rule": item.get("rule"),
            "confidence": item.get("confidence"),
            "preview": item.get("preview"),
            "is_toc": is_toc,
            "reason": reason,
        }

        if is_toc:
            excluded_toc_entries.append(entry)
            if not keep_toc:
                continue

        entry["position"] = len(body_outline) + 1
        body_outline.append(entry)

    return body_outline, excluded_toc_entries


def build_output_report(
    outline_path: Path,
    chunks_path: Path,
    outline_report: dict,
    body_outline: list[dict],
    excluded_toc_entries: list[dict],
    keep_toc: bool,
) -> dict:
    return {
        "source_outline_file": str(outline_path),
        "source_chunks_file": str(chunks_path),
        "input_outline_count": outline_report.get("outline_count", len(outline_report["outline"])),
        "body_outline_count": len(body_outline),
        "excluded_toc_count": len(excluded_toc_entries),
        "keep_toc": keep_toc,
        "body_outline": body_outline,
        "excluded_toc_entries": excluded_toc_entries,
    }


def format_text_report(report: dict) -> str:
    lines = [
        "BODY OUTLINE",
        "=" * 80,
        f"Source outline file: {report['source_outline_file']}",
        f"Source chunks file: {report['source_chunks_file']}",
        f"Input outline count: {report['input_outline_count']}",
        f"Body outline count: {report['body_outline_count']}",
        f"Excluded TOC count: {report['excluded_toc_count']}",
        f"Keep TOC: {report['keep_toc']}",
        "",
    ]

    for item in report["body_outline"]:
        toc_marker = " | TOC" if item.get("is_toc") else ""
        lines.append(f"Page {item['page_start']} | {item['heading']}{toc_marker}")
        lines.append(f"  Chunk: {item['chunk_id']} | Reason: {item['reason']}")
        if item.get("preview"):
            lines.append(f"  Preview: {item['preview']}")
        lines.append("")

    lines.extend(["", "EXCLUDED TOC ENTRIES", "=" * 80])

    for item in report["excluded_toc_entries"]:
        lines.append(f"Page {item['page_start']} | {item['heading']} | {item['reason']}")
        lines.append(f"  Chunk: {item['chunk_id']}")
        if item.get("preview"):
            lines.append(f"  Preview: {item['preview']}")
        lines.append("")

    return "\n".join(lines)


def write_report(outline_path: Path, report: dict) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(outline_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.body_outline.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.body_outline.txt"

    json_output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_report(report), encoding="utf-8")

    return json_output_path, txt_output_path


def main() -> None:
    args = parse_args()
    outline_path = Path(args.outline_path)
    chunks_path = Path(args.chunks_path)
    outline_report = load_json_file(outline_path)
    chunks = load_json_file(chunks_path)

    validate_outline_report(outline_report)
    validate_chunks(chunks)

    body_outline, excluded_toc_entries = build_body_outline(
        outline_report=outline_report,
        chunks=chunks,
        keep_toc=args.keep_toc,
    )
    output_report = build_output_report(
        outline_path=outline_path,
        chunks_path=chunks_path,
        outline_report=outline_report,
        body_outline=body_outline,
        excluded_toc_entries=excluded_toc_entries,
        keep_toc=args.keep_toc,
    )
    json_output_path, txt_output_path = write_report(outline_path, output_report)

    print("PDF body outline report created.")
    print(f"Source outline file: {outline_path}")
    print(f"Source chunks file: {chunks_path}")
    print(f"Input outline count: {output_report['input_outline_count']}")
    print(f"Body outline count: {output_report['body_outline_count']}")
    print(f"Excluded TOC count: {output_report['excluded_toc_count']}")
    print(f"Keep TOC: {args.keep_toc}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


if __name__ == "__main__":
    main()
