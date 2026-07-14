import argparse
import json
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


EXTRACTED_DIR = Path("extracted")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Assign section metadata to chapter-enriched PDF chunks using a resolved document structure."
    )
    parser.add_argument("chapter_chunks_path", help="Path to chapter-enriched PDF chunks JSON.")
    parser.add_argument(
        "structure_resolution_path",
        help="Path to a document structure resolution JSON report.",
    )
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
        raise SystemExit("Chapter chunks JSON must contain a top-level array.")

    for position, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            raise SystemExit(f"Chunk #{position} must be a JSON object.")

        if not chunk.get("id"):
            raise SystemExit(f"Chunk #{position} is missing an id.")

    return chunks


def validate_structure_resolution(report: Any) -> dict:
    if not isinstance(report, dict):
        raise SystemExit("Structure resolution JSON must contain a top-level object.")

    selected_outline = report.get("selected_outline")
    if not isinstance(selected_outline, dict):
        raise SystemExit("Structure resolution JSON must contain selected_outline.")

    chapters = selected_outline.get("chapters")
    if not isinstance(chapters, list):
        raise SystemExit("Structure resolution selected_outline must contain chapters.")

    return report


def output_stem(chunks_path: Path) -> str:
    for suffix in [
        ".chapter_chunks.json",
        ".chunks.json",
        ".json",
    ]:
        if chunks_path.name.endswith(suffix):
            return chunks_path.name[: -len(suffix)]

    return chunks_path.stem


def selected_chapters(report: dict) -> list[dict]:
    return report["selected_outline"]["chapters"]


def selected_section_count(report: dict) -> int:
    return sum(len(chapter.get("sections") or []) for chapter in selected_chapters(report))


def build_sections_by_chapter(report: dict) -> dict[Any, list[dict]]:
    sections_by_chapter: dict[Any, list[dict]] = {}

    for chapter in selected_chapters(report):
        chapter_number = chapter.get("chapter_number")
        sections = []

        for section in chapter.get("sections") or []:
            page_start = section.get("page_start")
            if not isinstance(page_start, int):
                continue

            section_title = section.get("section_title")
            if not section_title:
                continue

            sections.append(
                {
                    "section": section_title,
                    "page_start": page_start,
                    "level": section.get("level"),
                }
            )

        sections_by_chapter[chapter_number] = sorted(
            sections,
            key=lambda item: item["page_start"],
        )

    return sections_by_chapter


def find_section_for_chunk(
    chunk: dict,
    sections_by_chapter: dict[Any, list[dict]],
) -> dict | None:
    if chunk.get("is_front_matter"):
        return None

    chapter_number = chunk.get("chapter_number")
    page_start = chunk.get("page_start")

    if not isinstance(page_start, int):
        return None

    sections = sections_by_chapter.get(chapter_number) or []
    sections_on_same_page = [
        section for section in sections if section["page_start"] == page_start
    ]
    if sections_on_same_page:
        # TOC entries can share a page. With page-only metadata, assign the first
        # same-page section to that page and let following pages use the later entry.
        return sections_on_same_page[0]

    selected_section = None

    for section in sections:
        if page_start < section["page_start"]:
            break

        selected_section = section

    return selected_section


def clear_section_fields(chunk: dict) -> None:
    chunk["section"] = None
    chunk["section_page_start"] = None
    chunk["section_source"] = None
    chunk["section_confidence"] = None
    chunk["section_level"] = None
    chunk["topic"] = None


def assign_sections(
    chunks: list[dict],
    structure_resolution: dict,
) -> list[dict]:
    sections_by_chapter = build_sections_by_chapter(structure_resolution)
    selected_source = structure_resolution.get("selected_source")
    selected_confidence = structure_resolution.get("selected_confidence")
    enriched_chunks = []

    for chunk in chunks:
        enriched_chunk = dict(chunk)
        section = find_section_for_chunk(enriched_chunk, sections_by_chapter)

        if section is None:
            clear_section_fields(enriched_chunk)
        else:
            enriched_chunk["section"] = section["section"]
            enriched_chunk["section_page_start"] = section["page_start"]
            enriched_chunk["section_source"] = selected_source
            enriched_chunk["section_confidence"] = selected_confidence
            enriched_chunk["section_level"] = section.get("level")
            enriched_chunk["topic"] = section["section"]

        enriched_chunks.append(enriched_chunk)

    return enriched_chunks


def section_counts_by_chapter(enriched_chunks: list[dict]) -> OrderedDict[str, Counter]:
    counts: OrderedDict[str, Counter] = OrderedDict()

    for chunk in enriched_chunks:
        if chunk.get("is_front_matter"):
            continue

        chapter = chunk.get("chapter") or f"CHAPTER {chunk.get('chapter_number')}"
        counts.setdefault(chapter, Counter())
        section = chunk.get("section") or "Unassigned"
        counts[chapter][section] += 1

    return counts


def sample_assignments(enriched_chunks: list[dict]) -> list[dict]:
    sample_indices = {0}

    for index, chunk in enumerate(enriched_chunks):
        if chunk.get("is_front_matter"):
            continue

        page_start = chunk.get("page_start")
        chapter_number = chunk.get("chapter_number")
        section = chunk.get("section")

        if chapter_number in {1, 2} and page_start in {1, 2, 3, 8, 12, 49, 50, 51}:
            sample_indices.add(index)

        if section and len(sample_indices) < 14:
            sample_indices.add(index)

    return [
        enriched_chunks[index]
        for index in sorted(sample_indices)
        if 0 <= index < len(enriched_chunks)
    ][:16]


def format_assignment(chunk: dict) -> str:
    section = chunk.get("section")
    section_label = section if section is not None else "null"
    return (
        f"{chunk.get('id')} | page {chunk.get('page_start')} | "
        f"{chunk.get('chapter')} | section: {section_label}"
    )


def format_text_report(
    chunks_path: Path,
    structure_resolution_path: Path,
    structure_resolution: dict,
    enriched_chunks: list[dict],
) -> str:
    sections_in_outline = selected_section_count(structure_resolution)
    front_matter_count = sum(1 for chunk in enriched_chunks if chunk.get("is_front_matter"))
    with_section_count = sum(1 for chunk in enriched_chunks if chunk.get("section") is not None)
    without_section_count = len(enriched_chunks) - with_section_count
    section_counts = section_counts_by_chapter(enriched_chunks)

    lines = [
        "SUMMARY",
        "=" * 80,
        f"Source chunks file: {chunks_path}",
        f"Structure resolution file: {structure_resolution_path}",
        f"Chunks loaded: {len(enriched_chunks)}",
        f"Selected source: {structure_resolution.get('selected_source')}",
        f"Selected confidence: {structure_resolution.get('selected_confidence')}",
        f"Chapters in selected outline: {len(selected_chapters(structure_resolution))}",
        f"Sections in outline: {sections_in_outline}",
        f"Chunks with section: {with_section_count}",
        f"Chunks without section: {without_section_count}",
        f"Front matter chunks: {front_matter_count}",
        "",
        "SECTION COUNT BY CHAPTER",
        "=" * 80,
    ]

    for chapter, counts in section_counts.items():
        lines.append(f"{chapter}:")
        for section, count in counts.items():
            lines.append(f"{section}: {count} chunks")
        lines.append("")

    lines.extend(
        [
            "SAMPLE ASSIGNMENTS",
            "=" * 80,
        ]
    )
    lines.extend(format_assignment(chunk) for chunk in sample_assignments(enriched_chunks))

    return "\n".join(lines) + "\n"


def write_outputs(
    chunks_path: Path,
    structure_resolution_path: Path,
    structure_resolution: dict,
    enriched_chunks: list[dict],
) -> tuple[Path, Path]:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    stem = output_stem(chunks_path)
    json_output_path = EXTRACTED_DIR / f"{stem}.section_chunks.json"
    txt_output_path = EXTRACTED_DIR / f"{stem}.section_chunks.txt"

    json_output_path.write_text(
        json.dumps(enriched_chunks, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(
        format_text_report(
            chunks_path=chunks_path,
            structure_resolution_path=structure_resolution_path,
            structure_resolution=structure_resolution,
            enriched_chunks=enriched_chunks,
        ),
        encoding="utf-8",
    )

    return json_output_path, txt_output_path


def print_summary(
    chunks_path: Path,
    structure_resolution_path: Path,
    structure_resolution: dict,
    enriched_chunks: list[dict],
    json_output_path: Path,
    txt_output_path: Path,
) -> None:
    sections_in_outline = selected_section_count(structure_resolution)
    front_matter_count = sum(1 for chunk in enriched_chunks if chunk.get("is_front_matter"))
    with_section_count = sum(1 for chunk in enriched_chunks if chunk.get("section") is not None)
    without_section_count = len(enriched_chunks) - with_section_count
    section_counts = section_counts_by_chapter(enriched_chunks)

    print("PDF section assignment completed.")
    print(f"Chunks loaded: {len(enriched_chunks)}")
    print(f"Selected source: {structure_resolution.get('selected_source')}")
    print(f"Selected confidence: {structure_resolution.get('selected_confidence')}")
    print(f"Chapters in selected outline: {len(selected_chapters(structure_resolution))}")
    print(f"Sections in selected outline: {sections_in_outline}")
    print(f"Chunks with section assigned: {with_section_count}")
    print(f"Chunks without section: {without_section_count}")
    print(f"Front matter chunks: {front_matter_count}")
    print(f"Output JSON path: {json_output_path}")
    print(f"Output TXT path: {txt_output_path}")
    print("Section count per chapter:")
    for chapter, counts in section_counts.items():
        print(f"- {chapter}: {len([section for section in counts if section != 'Unassigned'])} sections")


def main() -> None:
    args = parse_args()
    chunks_path = Path(args.chapter_chunks_path)
    structure_resolution_path = Path(args.structure_resolution_path)
    chunks = validate_chunks(load_json_file(chunks_path))
    structure_resolution = validate_structure_resolution(
        load_json_file(structure_resolution_path)
    )
    enriched_chunks = assign_sections(
        chunks=chunks,
        structure_resolution=structure_resolution,
    )
    json_output_path, txt_output_path = write_outputs(
        chunks_path=chunks_path,
        structure_resolution_path=structure_resolution_path,
        structure_resolution=structure_resolution,
        enriched_chunks=enriched_chunks,
    )
    print_summary(
        chunks_path=chunks_path,
        structure_resolution_path=structure_resolution_path,
        structure_resolution=structure_resolution,
        enriched_chunks=enriched_chunks,
        json_output_path=json_output_path,
        txt_output_path=txt_output_path,
    )


if __name__ == "__main__":
    main()
