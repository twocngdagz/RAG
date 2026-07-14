import argparse
import json
import os
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.ollama import OllamaEmbedding


load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

REQUIRED_FIELDS = [
    "id",
    "source_pdf",
    "source_type",
    "book_id",
    "book_title",
    "chapter",
    "chapter_number",
    "section",
    "section_page_start",
    "section_source",
    "section_confidence",
    "section_level",
    "topic",
    "content_type",
    "page_start",
    "page_end",
    "is_front_matter",
    "text",
    "metadata",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a section-enriched local PDF vector index."
    )
    parser.add_argument(
        "section_chunks_path",
        help="Path to a section-enriched PDF chunks JSON file.",
    )
    return parser.parse_args()


def validate_input_path(path: Path) -> None:
    if not path.exists():
        raise SystemExit(f"Section chunks file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"Section chunks path is not a file: {path}")


def load_json_file(path: Path) -> Any:
    validate_input_path(path)

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def validate_chunks(data: Any) -> list[dict]:
    if not isinstance(data, list):
        raise SystemExit("Section chunks JSON must contain a top-level array.")

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

        if not isinstance(chunk["metadata"], dict):
            raise SystemExit(f"Chunk #{position} metadata must be a JSON object.")

    return data


def source_stem(section_chunks_path: Path) -> str:
    for suffix in [
        ".section_chunks.json",
        ".chapter_chunks.json",
        ".chunks.json",
    ]:
        if section_chunks_path.name.endswith(suffix):
            return section_chunks_path.name[: -len(suffix)]

    return section_chunks_path.stem


def derive_index_id(section_chunks_path: Path) -> str:
    return f"section_pdf_{source_stem(section_chunks_path)}"


def derive_storage_dir(section_chunks_path: Path) -> Path:
    return Path("storage") / derive_index_id(section_chunks_path)


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def build_nodes(chunks: list[dict]) -> list[TextNode]:
    nodes = []

    for chunk in chunks:
        metadata = {}
        for key, value in chunk.items():
            if key in {"id", "text"}:
                continue

            if key == "metadata":
                metadata["source_metadata"] = json_safe(value)
            else:
                metadata[key] = json_safe(value)

        nodes.append(
            TextNode(
                id_=chunk["id"],
                text=chunk["text"] or "",
                metadata=metadata,
            )
        )

    return nodes


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
        chunk["section"]
        for chunk in chunks
        if chunk.get("section") is not None
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
) -> None:
    total_characters = sum(len(chunk["text"] or "") for chunk in chunks)
    front_matter_count = sum(1 for chunk in chunks if chunk.get("is_front_matter"))
    section_assigned_count = sum(1 for chunk in chunks if chunk.get("section") is not None)
    unassigned_count = len(chunks) - section_assigned_count
    counts_by_chapter = chapter_counts(chunks)
    counts_by_section = section_counts(chunks)
    chapters = ordered_chapters(chunks)
    sections = unique_sections(chunks)

    print("Section PDF index built successfully.")
    print(f"Chunks loaded: {len(chunks)}")
    print(f"Chunks indexed: {len(nodes)}")
    print(f"Total characters indexed: {total_characters}")
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
    print(f"Storage directory: ./{storage_dir}")
    print(f"Embedding model: {OLLAMA_EMBED_MODEL}")


def main() -> None:
    args = parse_args()
    section_chunks_path = Path(args.section_chunks_path)

    chunks = validate_chunks(load_json_file(section_chunks_path))
    nodes = build_nodes(chunks)
    index_id = derive_index_id(section_chunks_path)
    storage_dir = derive_storage_dir(section_chunks_path)

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    index = VectorStoreIndex(nodes)
    index.set_index_id(index_id)
    index.storage_context.persist(persist_dir=str(storage_dir))

    print_summary(
        chunks=chunks,
        nodes=nodes,
        index_id=index_id,
        storage_dir=storage_dir,
    )


if __name__ == "__main__":
    main()
