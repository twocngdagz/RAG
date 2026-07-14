import json
import os
from pathlib import Path

from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.ollama import OllamaEmbedding


load_dotenv()

CHUNKS_FILE = Path("chunks.json")
STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage/year5_math_tiny")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

REQUIRED_FIELDS = [
    "id",
    "domain",
    "grade",
    "book_id",
    "book_title",
    "chapter",
    "section",
    "topic",
    "content_type",
    "page_start",
    "page_end",
    "text",
]


def load_chunks() -> list[dict]:
    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(f"Missing required file: {CHUNKS_FILE}")

    with CHUNKS_FILE.open("r", encoding="utf-8") as file:
        chunks = json.load(file)

    if not isinstance(chunks, list):
        raise ValueError("chunks.json must contain a top-level JSON array.")

    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            raise ValueError(f"Chunk #{index} must be a JSON object.")

        missing_fields = [field for field in REQUIRED_FIELDS if field not in chunk]

        if missing_fields:
            raise ValueError(
                f"Chunk #{index} is missing required fields: {', '.join(missing_fields)}"
            )

        if not chunk["id"]:
            raise ValueError(f"Chunk #{index} has an empty id.")

        if not chunk["text"]:
            raise ValueError(f"Chunk #{index} has empty text.")

    return chunks


def build_nodes(chunks: list[dict]) -> list[TextNode]:
    nodes = []

    for chunk in chunks:
        metadata = {
            key: value
            for key, value in chunk.items()
            if key not in ["id", "text"]
        }

        nodes.append(
            TextNode(
                id_=chunk["id"],
                text=chunk["text"],
                metadata=metadata,
            )
        )

    return nodes


def main() -> None:
    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    chunks = load_chunks()
    nodes = build_nodes(chunks)

    index = VectorStoreIndex(nodes)
    index.set_index_id("year5_math_tiny")
    index.storage_context.persist(persist_dir=STORAGE_DIR)

    print("Index built successfully.")
    print(f"Chunks indexed: {len(nodes)}")
    print(f"Storage directory: {STORAGE_DIR}")
    print(f"Embedding model: {OLLAMA_EMBED_MODEL}")
    print(f"Ollama base URL: {OLLAMA_BASE_URL}")


if __name__ == "__main__":
    main()
