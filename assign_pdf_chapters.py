import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assign chapter metadata to PDF chunks using a body outline."
    )
    parser.add_argument("chunks_path", help="Path to the PDF chunks JSON file.")
    parser.add_argument("body_outline_path", help="Path to the body outline JSON file.")
    return parser.parse_args()


def load_json_file(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Required file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"Path is not a file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_chunks(chunks: Any) -> list[dict]:
    if not isinstance(chunks, list):
        raise SystemExit("Chunks JSON must contain a top-level array.")

    for position, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            raise SystemExit(f"Chunk #{position} must be a JSON object.")

        if not chunk.get("id"):
            raise SystemExit(f"Chunk #{position} is missing an id.")

    return chunks


def validate_body_outline(body_outline_report: Any) -> list[dict]:
    if not isinstance(body_outline_report, dict):
        raise SystemExit("Body outline JSON must contain a top-level object.")

    body_outline = body_outline_report.get("body_outline")
    if not isinstance(body_outline, list):
        raise SystemExit("Body outline JSON must contain a body_outline array.")

    return body_outline


def output_stem(chunks_path: Path) -> str:
    if chunks_path.name.endswith(".chunks.json"):
        return chunks_path.name[: -len(".chunks.json")]

    return chunks_path.stem


def parse_chapter_number(heading: str | None) -> int | None:
    if not heading:
        return None

    match = re.search(r"\bCHAPTER\s+(\d+)\b", heading, flags=re.IGNORECASE)
    if not match:
        return None

    return int(match.group(1))


def chunk_order(chunks: list[dict]) -> dict[str, int]:
    return {chunk["id"]: index for index, chunk in enumerate(chunks)}


def build_chapter_markers(body_outline: list[dict], chunks: list[dict]) -> list[dict]:
    chunk_index_by_id = chunk_order(chunks)
    chunks_by_id = {chunk["id"]: chunk for chunk in chunks}
    markers = []

    for marker in body_outline:
        chunk_id = marker.get("chunk_id")
        if chunk_id not in chunk_index_by_id:
            raise SystemExit(f"Body outline marker chunk not found in chunks: {chunk_id}")

        heading = marker.get("heading")
        chapter_number = parse_chapter_number(heading)
        if chapter_number is None:
            raise SystemExit(f"Could not parse chapter number from heading: {heading}")

        source_chunk = chunks_by_id[chunk_id]
        markers.append(
            {
                "chunk_index": chunk_index_by_id[chunk_id],
                "chunk_id": chunk_id,
                "heading": heading,
                "chapter_number": chapter_number,
                "source_page": source_chunk.get("page_start", marker.get("page_start")),
            }
        )

    return sorted(markers, key=lambda item: item["chunk_index"])


def assign_chapters(chunks: list[dict], chapter_markers: list[dict]) -> list[dict]:
    enriched_chunks = []
    current_marker_index = -1

    for chunk_index, chunk in enumerate(chunks):
        while (
            current_marker_index + 1 < len(chapter_markers)
            and chapter_markers[current_marker_index + 1]["chunk_index"] <= chunk_index
        ):
            current_marker_index += 1

        enriched_chunk = dict(chunk)

        if current_marker_index == -1:
            enriched_chunk["chapter"] = None
            enriched_chunk["chapter_number"] = None
            enriched_chunk["chapter_source_chunk_id"] = None
            enriched_chunk["chapter_source_page"] = None
            enriched_chunk["is_front_matter"] = True
        else:
            marker = chapter_markers[current_marker_index]
            enriched_chunk["chapter"] = marker["heading"]
            enriched_chunk["chapter_number"] = marker["chapter_number"]
            enriched_chunk["chapter_source_chunk_id"] = marker["chunk_id"]
            enriched_chunk["chapter_source_page"] = marker["source_page"]
            enriched_chunk["is_front_matter"] = False

        enriched_chunks.append(enriched_chunk)

    return enriched_chunks


def count_by_chapter(enriched_chunks: list[dict]) -> Counter:
    return Counter(
        chunk["chapter"]
        for chunk in enriched_chunks
        if not chunk.get("is_front_matter")
    )


def sample_assignments(enriched_chunks: list[dict], chapter_markers: list[dict]) -> list[dict]:
    sample_indices = {0}
    sample_indices.update(marker["chunk_index"] for marker in chapter_markers)

    return [
        enriched_chunks[index]
        for index in sorted(sample_indices)
        if 0 <= index < len(enriched_chunks)
    ]


def format_assignment(chunk: dict) -> str:
    label = "front matter" if chunk.get("is_front_matter") else chunk.get("chapter")
    return f"{chunk.get('id')} | page {chunk.get('page_start')} | {label}"


def format_text_report(
    chunks_path: Path,
    body_outline_path: Path,
    enriched_chunks: list[dict],
    chapter_markers: list[dict],
) -> str:
    front_matter_count = sum(1 for chunk in enriched_chunks if chunk["is_front_matter"])
    chapter_counts = count_by_chapter(enriched_chunks)

    lines = [
        "SUMMARY",
        "=" * 80,
        f"Source chunks file: {chunks_path}",
        f"Source body outline file: {body_outline_path}",
        f"Chunks loaded: {len(enriched_chunks)}",
        f"Chapter markers: {len(chapter_markers)}",
        f"Front matter chunks: {front_matter_count}",
        "",
        "CHUNK COUNT BY CHAPTER",
        "=" * 80,
    ]

    for marker in chapter_markers:
        chapter = marker["heading"]
        lines.append(f"{chapter}: {chapter_counts.get(chapter, 0)}")

    lines.extend(
        [
            "",
            "SAMPLE ASSIGNMENTS",
            "=" * 80,
        ]
    )

    for chunk in sample_assignments(enriched_chunks, chapter_markers):
        lines.append(format_assignment(chunk))

    return "\n".join(lines)


def write_outputs(
    chunks_path: Path,
    body_outline_path: Path,
    enriched_chunks: list[dict],
    chapter_markers: list[dict],
) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(chunks_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.chapter_chunks.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.chapter_chunks.txt"

    json_output_path.write_text(
        json.dumps(enriched_chunks, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(
        format_text_report(
            chunks_path=chunks_path,
            body_outline_path=body_outline_path,
            enriched_chunks=enriched_chunks,
            chapter_markers=chapter_markers,
        ),
        encoding="utf-8",
    )

    return json_output_path, txt_output_path


def print_summary(
    chunks: list[dict],
    chapter_markers: list[dict],
    enriched_chunks: list[dict],
    json_output_path: Path,
    txt_output_path: Path,
) -> None:
    front_matter_count = sum(1 for chunk in enriched_chunks if chunk["is_front_matter"])
    chapter_counts = count_by_chapter(enriched_chunks)

    print("PDF chapter assignment completed.")
    print(f"Chunks loaded: {len(chunks)}")
    print(f"Body chapter markers loaded: {len(chapter_markers)}")
    print(f"Enriched chunks written: {len(enriched_chunks)}")
    print(f"Front matter chunks: {front_matter_count}")
    print("Chunk count by chapter:")
    for marker in chapter_markers:
        chapter = marker["heading"]
        print(f"- {chapter}: {chapter_counts.get(chapter, 0)}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")


def main() -> None:
    args = parse_args()
    chunks_path = Path(args.chunks_path)
    body_outline_path = Path(args.body_outline_path)

    chunks = validate_chunks(load_json_file(chunks_path))
    body_outline = validate_body_outline(load_json_file(body_outline_path))
    chapter_markers = build_chapter_markers(body_outline, chunks)
    enriched_chunks = assign_chapters(chunks, chapter_markers)
    json_output_path, txt_output_path = write_outputs(
        chunks_path=chunks_path,
        body_outline_path=body_outline_path,
        enriched_chunks=enriched_chunks,
        chapter_markers=chapter_markers,
    )

    print_summary(
        chunks=chunks,
        chapter_markers=chapter_markers,
        enriched_chunks=enriched_chunks,
        json_output_path=json_output_path,
        txt_output_path=txt_output_path,
    )


if __name__ == "__main__":
    main()
