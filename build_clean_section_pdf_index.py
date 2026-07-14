import argparse
import json
import os
import shutil
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.ollama import OllamaEmbedding

from pdf_artifact_paths import get_clean_index_defaults


load_dotenv()

DEFAULT_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

REQUIRED_FIELDS = [
    "id",
    "text",
    "chapter",
    "chapter_number",
    "section",
    "topic",
    "page_start",
    "page_end",
    "source_pdf",
    "book_title",
    "boundary_cleanup",
]

FLAT_METADATA_FIELDS = [
    "source_pdf",
    "source_type",
    "domain",
    "grade",
    "book_id",
    "book_title",
    "chapter",
    "chapter_number",
    "section",
    "topic",
    "content_type",
    "page_start",
    "page_end",
    "section_page_start",
    "section_source",
    "section_confidence",
    "section_level",
    "is_front_matter",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a separate local PDF vector index from cleaned section chunks."
        )
    )
    parser.add_argument(
        "cleaned_chunks_json",
        help="Path to cleaned section chunks JSON file.",
    )
    parser.add_argument(
        "--storage-dir",
        default=None,
        help=(
            "Directory where the clean section PDF index will be persisted. "
            "Defaults from the cleaned chunks path when omitted."
        ),
    )
    parser.add_argument(
        "--index-id",
        default=None,
        help=(
            "Index ID for the clean section PDF index. "
            "Defaults from the cleaned chunks path when omitted."
        ),
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_OLLAMA_EMBED_MODEL,
        help="Ollama embedding model name.",
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_BASE_URL,
        help="Ollama base URL.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite an existing storage directory if present.",
    )
    return parser.parse_args()


def validate_input_path(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Cleaned chunks file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"Cleaned chunks path is not a file: {path}")


def load_json_file(path: Path) -> Any:
    validate_input_path(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_chunks(data: Any) -> list[dict]:
    if not isinstance(data, list):
        raise SystemExit("Cleaned chunks JSON must contain a top-level array.")

    for position, chunk in enumerate(data, start=1):
        if not isinstance(chunk, dict):
            raise SystemExit(f"Chunk #{position} must be a JSON object.")

        missing_fields = [field for field in REQUIRED_FIELDS if field not in chunk]
        if missing_fields:
            raise SystemExit(
                f"Chunk #{position} is missing required fields: "
                f"{', '.join(missing_fields)}"
            )

        if not chunk["id"]:
            raise SystemExit(f"Chunk #{position} has an empty id.")

        if not isinstance(chunk["text"], str):
            raise SystemExit(f"Chunk #{position} text must be a string.")

        boundary_cleanup = chunk["boundary_cleanup"]
        if not isinstance(boundary_cleanup, dict):
            raise SystemExit(
                f"Chunk #{position} boundary_cleanup must be a JSON object."
            )

    return data


def metadata_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def flatten_boundary_cleanup(boundary_cleanup: dict) -> dict[str, Any]:
    warnings = boundary_cleanup.get("warnings") or []
    warning_count = len(warnings) if isinstance(warnings, list) else 0

    return {
        "boundary_cleanup_applied": bool(boundary_cleanup.get("applied")),
        "boundary_cleanup_prefix_trimmed_chars": int(
            boundary_cleanup.get("prefix_trimmed_chars") or 0
        ),
        "boundary_cleanup_suffix_trimmed_chars": int(
            boundary_cleanup.get("suffix_trimmed_chars") or 0
        ),
        "boundary_cleanup_start_heading": metadata_scalar(
            boundary_cleanup.get("start_heading")
        ),
        "boundary_cleanup_start_heading_found": bool(
            boundary_cleanup.get("start_heading_found")
        ),
        "boundary_cleanup_end_heading": metadata_scalar(
            boundary_cleanup.get("end_heading")
        ),
        "boundary_cleanup_end_heading_found": bool(
            boundary_cleanup.get("end_heading_found")
        ),
        "boundary_cleanup_warning_count": warning_count,
    }


def build_nodes(chunks: list[dict]) -> list[TextNode]:
    nodes = []

    for chunk in chunks:
        metadata: dict[str, Any] = {}

        for field in FLAT_METADATA_FIELDS:
            if field in chunk:
                metadata[field] = metadata_scalar(chunk[field])

        boundary_cleanup = chunk.get("boundary_cleanup") or {}
        if isinstance(boundary_cleanup, dict):
            metadata.update(flatten_boundary_cleanup(boundary_cleanup))

        nodes.append(
            TextNode(
                id_=chunk["id"],
                text=chunk["text"] or "",
                metadata=metadata,
            )
        )

    return nodes


def ensure_storage_dir(storage_dir: Path, overwrite: bool) -> None:
    if not storage_dir.exists():
        return

    if not overwrite:
        raise SystemExit(
            f"Storage directory already exists: {storage_dir}\n"
            "Pass --overwrite to replace it, or choose a different --storage-dir."
        )

    if storage_dir.is_file():
        raise SystemExit(f"Storage path exists and is a file: {storage_dir}")

    shutil.rmtree(storage_dir)


def ordered_chapters(chunks: list[dict]) -> list[str]:
    chapters = []
    seen = set()

    for chunk in chunks:
        chapter = chunk.get("chapter")
        if chunk.get("is_front_matter") or not chapter or chapter in seen:
            continue

        seen.add(chapter)
        chapters.append(chapter)

    return chapters


def chapter_counts(chunks: list[dict]) -> Counter:
    return Counter(
        chunk["chapter"]
        for chunk in chunks
        if not chunk.get("is_front_matter") and chunk.get("chapter")
    )


def section_counts(chunks: list[dict]) -> Counter:
    return Counter(
        chunk["section"] for chunk in chunks if chunk.get("section") is not None
    )


def unique_sections(chunks: list[dict]) -> OrderedDict[tuple[Any, str], None]:
    sections: OrderedDict[tuple[Any, str], None] = OrderedDict()

    for chunk in chunks:
        section = chunk.get("section")
        if section is not None:
            sections.setdefault((chunk.get("chapter_number"), section), None)

    return sections


def print_summary(
    chunks: list[dict],
    nodes: list[TextNode],
    index_id: str,
    storage_dir: Path,
    embedding_model: str,
) -> None:
    total_characters = sum(len(chunk["text"] or "") for chunk in chunks)
    cleaned_count = sum(
        1
        for chunk in chunks
        if isinstance(chunk.get("boundary_cleanup"), dict)
        and chunk["boundary_cleanup"].get("applied")
    )
    unchanged_count = len(chunks) - cleaned_count
    warning_chunk_count = sum(
        1
        for chunk in chunks
        if isinstance(chunk.get("boundary_cleanup"), dict)
        and isinstance(chunk["boundary_cleanup"].get("warnings"), list)
        and chunk["boundary_cleanup"]["warnings"]
    )
    front_matter_count = sum(1 for chunk in chunks if chunk.get("is_front_matter"))
    section_assigned_count = sum(
        1 for chunk in chunks if chunk.get("section") is not None
    )
    unassigned_count = len(chunks) - section_assigned_count
    counts_by_chapter = chapter_counts(chunks)
    counts_by_section = section_counts(chunks)
    chapters = ordered_chapters(chunks)
    sections = unique_sections(chunks)

    print("Clean section PDF index built successfully.")
    print(f"Chunks loaded: {len(chunks)}")
    print(f"Chunks indexed: {len(nodes)}")
    print(f"Total characters indexed: {total_characters}")
    print(f"Cleaned chunks indexed: {cleaned_count}")
    print(f"Unchanged chunks indexed: {unchanged_count}")
    print(f"Chunks with cleanup warnings: {warning_chunk_count}")
    print(f"Front matter chunks: {front_matter_count}")
    print(f"Chapter count: {len(chapters)}")
    print(f"Section-assigned chunks: {section_assigned_count}")
    print(f"Unassigned chunks: {unassigned_count}")
    print(f"Unique sections: {len(sections)}")
    print("")
    print("Chunk count by chapter:")
    for chapter in chapters:
        print(f"{chapter}: {counts_by_chapter.get(chapter, 0)}")
    print("")
    print("Top 20 sections by chunk count:")
    for section, count in counts_by_section.most_common(20):
        print(f"{section}: {count}")
    print("")
    print(f"Index ID: {index_id}")
    print(f"Storage directory: {storage_dir}")
    print(f"Embedding model: {embedding_model}")


def main() -> None:
    args = parse_args()
    cleaned_chunks_path = Path(args.cleaned_chunks_json)
    defaults = get_clean_index_defaults(cleaned_chunks_path)
    storage_dir = Path(args.storage_dir or defaults["storage_dir"])
    index_id = args.index_id or defaults["index_id"]

    chunks = validate_chunks(load_json_file(cleaned_chunks_path))
    ensure_storage_dir(storage_dir, overwrite=args.overwrite)
    nodes = build_nodes(chunks)

    Settings.embed_model = OllamaEmbedding(
        model_name=args.embedding_model,
        base_url=args.ollama_base_url,
    )

    index = VectorStoreIndex(nodes)
    index.set_index_id(index_id)
    index.storage_context.persist(persist_dir=str(storage_dir))

    print_summary(
        chunks=chunks,
        nodes=nodes,
        index_id=index_id,
        storage_dir=storage_dir,
        embedding_model=args.embedding_model,
    )


if __name__ == "__main__":
    main()
