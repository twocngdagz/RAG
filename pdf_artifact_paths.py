import argparse
import re
from pathlib import Path
from typing import Any


KNOWN_SUFFIXES = (
    ".section_clean_chunks.json",
    ".section_chunks.json",
    ".structure_resolution.json",
    ".pdf",
)


def slugify_name(name: str) -> str:
    slug = name.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")

    if not slug:
        raise ValueError(f"Unable to derive a non-empty document slug from: {name!r}")

    return slug


def infer_document_slug(path: str | Path) -> str:
    path_obj = Path(path)
    filename = path_obj.name

    for suffix in KNOWN_SUFFIXES:
        if filename.endswith(suffix):
            return slugify_name(filename[: -len(suffix)])

    return slugify_name(path_obj.stem)


def get_clean_section_artifacts(section_chunks_path: str | Path) -> dict[str, Any]:
    path_obj = Path(section_chunks_path)
    document_slug = infer_document_slug(path_obj)
    parent = path_obj.parent

    return {
        "document_slug": document_slug,
        "section_chunks_path": str(path_obj),
        "structure_resolution_path": str(parent / f"{document_slug}.structure_resolution.json"),
        "clean_chunks_path": str(parent / f"{document_slug}.section_clean_chunks.json"),
        "clean_report_path": str(parent / f"{document_slug}.section_clean_chunks.txt"),
        "clean_index_id": f"section_clean_pdf_{document_slug}",
        "clean_storage_dir": str(Path("storage") / f"section_clean_pdf_{document_slug}"),
    }


def get_clean_index_defaults(section_chunks_or_clean_chunks_path: str | Path) -> dict[str, Any]:
    path_obj = Path(section_chunks_or_clean_chunks_path)
    document_slug = infer_document_slug(path_obj)
    parent = path_obj.parent

    return {
        "document_slug": document_slug,
        "structure_resolution_path": str(parent / f"{document_slug}.structure_resolution.json"),
        "clean_chunks_path": str(parent / f"{document_slug}.section_clean_chunks.json"),
        "clean_report_path": str(parent / f"{document_slug}.section_clean_chunks.txt"),
        "clean_index_id": f"section_clean_pdf_{document_slug}",
        "clean_storage_dir": str(Path("storage") / f"section_clean_pdf_{document_slug}"),
        "storage_dir": f"./storage/section_clean_pdf_{document_slug}",
        "index_id": f"section_clean_pdf_{document_slug}",
    }


def get_clean_pdf_defaults(source_pdf_path: str | Path) -> dict[str, Any]:
    document_slug = infer_document_slug(source_pdf_path)

    return {
        "document_slug": document_slug,
        "source_pdf": str(Path(source_pdf_path)),
        "clean_chunks_path": str(Path("extracted") / f"{document_slug}.section_clean_chunks.json"),
        "clean_index_id": f"section_clean_pdf_{document_slug}",
        "clean_storage_dir": str(Path("storage") / f"section_clean_pdf_{document_slug}"),
        "storage_dir": str(Path("storage") / f"section_clean_pdf_{document_slug}"),
        "index_id": f"section_clean_pdf_{document_slug}",
    }


def get_book_learning_material_paths(
    source_pdf_path: str | Path,
    *,
    output: str | Path | None = None,
    report: str | Path | None = None,
) -> dict[str, Any]:
    document_slug = infer_document_slug(source_pdf_path)
    extracted_dir = Path("extracted")
    output_path = (
        Path(output)
        if output is not None
        else Path("output") / f"{document_slug}.book_learning_materials.generated.json"
    )
    report_path = (
        Path(report)
        if report is not None
        else output_path.with_suffix(".txt")
    )

    return {
        "slug": document_slug,
        "source_pdf": str(Path(source_pdf_path)),
        "raw_chunks": str(extracted_dir / f"{document_slug}.chunks.json"),
        "raw_chunks_report": str(extracted_dir / f"{document_slug}.chunks.txt"),
        "structure_candidates": str(
            extracted_dir / f"{document_slug}.structure_candidates.json"
        ),
        "structure_candidates_report": str(
            extracted_dir / f"{document_slug}.structure_candidates.txt"
        ),
        "outline_candidates": str(
            extracted_dir / f"{document_slug}.outline_candidates.json"
        ),
        "outline_candidates_report": str(
            extracted_dir / f"{document_slug}.outline_candidates.txt"
        ),
        "body_outline": str(extracted_dir / f"{document_slug}.body_outline.json"),
        "body_outline_report": str(extracted_dir / f"{document_slug}.body_outline.txt"),
        "chapter_chunks": str(extracted_dir / f"{document_slug}.chapter_chunks.json"),
        "chapter_chunks_report": str(
            extracted_dir / f"{document_slug}.chapter_chunks.txt"
        ),
        "section_topic_candidates": str(
            extracted_dir / f"{document_slug}.section_topic_candidates.json"
        ),
        "section_topic_candidates_report": str(
            extracted_dir / f"{document_slug}.section_topic_candidates.txt"
        ),
        "section_outline": str(extracted_dir / f"{document_slug}.section_outline.json"),
        "section_outline_report": str(
            extracted_dir / f"{document_slug}.section_outline.txt"
        ),
        "strict_section_outline": str(
            extracted_dir / f"{document_slug}.strict_section_outline.json"
        ),
        "strict_section_outline_report": str(
            extracted_dir / f"{document_slug}.strict_section_outline.txt"
        ),
        "structure_resolution": str(
            extracted_dir / f"{document_slug}.structure_resolution.json"
        ),
        "structure_resolution_report": str(
            extracted_dir / f"{document_slug}.structure_resolution.txt"
        ),
        "section_chunks": str(extracted_dir / f"{document_slug}.section_chunks.json"),
        "section_chunks_report": str(
            extracted_dir / f"{document_slug}.section_chunks.txt"
        ),
        "clean_chunks": str(
            extracted_dir / f"{document_slug}.section_clean_chunks.json"
        ),
        "clean_report": str(
            extracted_dir / f"{document_slug}.section_clean_chunks.txt"
        ),
        "clean_index_id": f"section_clean_pdf_{document_slug}",
        "clean_storage_dir": str(Path("storage") / f"section_clean_pdf_{document_slug}"),
        "chapter_packages_json": str(
            Path("output") / f"{document_slug}.chapter_packages.generated.json"
        ),
        "output_json": str(output_path),
        "output_report": str(report_path),
    }


def format_artifact_summary(path: str | Path) -> str:
    path_obj = Path(path)
    filename = path_obj.name

    if filename.endswith(".section_chunks.json"):
        artifacts = get_clean_section_artifacts(path_obj)
    else:
        defaults = get_clean_index_defaults(path_obj)
        artifacts = {
            "document_slug": defaults["document_slug"],
            "structure_resolution_path": defaults["structure_resolution_path"],
            "clean_chunks_path": defaults["clean_chunks_path"],
            "clean_report_path": defaults["clean_report_path"],
            "clean_index_id": defaults["clean_index_id"],
            "clean_storage_dir": defaults["clean_storage_dir"],
        }

    return "\n".join(
        [
            f"Document slug: {artifacts['document_slug']}",
            f"Structure resolution: {artifacts['structure_resolution_path']}",
            f"Clean chunks: {artifacts['clean_chunks_path']}",
            f"Clean report: {artifacts['clean_report_path']}",
            f"Clean index ID: {artifacts['clean_index_id']}",
            f"Clean storage dir: {artifacts['clean_storage_dir']}",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive reusable clean-section artifact paths and index IDs."
    )
    parser.add_argument(
        "path",
        help=(
            "Path to a section chunks, clean chunks, structure resolution, or PDF file."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(format_artifact_summary(args.path))


if __name__ == "__main__":
    main()
