import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.ollama import OllamaEmbedding


load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
DEFAULT_QUERY = "What are the main learning topics in this PDF?"
SIMILARITY_TOP_K = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve context from a persisted PDF LlamaIndex index."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file used to build the index.")
    parser.add_argument("query", nargs="*", help="Optional retrieval query.")
    return parser.parse_args()


def validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"PDF file does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise SystemExit(f"PDF path is not a file: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit(f"Input file must be a PDF: {pdf_path}")


def get_index_id(pdf_path: Path) -> str:
    return f"pdf_{pdf_path.stem}"


def get_storage_dir(pdf_path: Path) -> Path:
    return Path("storage") / f"pdf_{pdf_path.stem}"


def get_node_text(node) -> str:
    try:
        return node.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(node, "text", "") or ""


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf_path)
    validate_pdf_path(pdf_path)

    query = " ".join(args.query).strip() or DEFAULT_QUERY
    index_id = get_index_id(pdf_path)
    storage_dir = get_storage_dir(pdf_path)

    if not storage_dir.exists():
        raise SystemExit(
            "Missing persisted PDF index storage directory: "
            f"{storage_dir}\n"
            "Build the PDF index first:\n"
            f'python build_pdf_index.py "{pdf_path}"'
        )

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    storage_context = StorageContext.from_defaults(
        persist_dir=str(storage_dir),
    )
    index = load_index_from_storage(
        storage_context,
        index_id=index_id,
    )
    retriever = index.as_retriever(
        similarity_top_k=SIMILARITY_TOP_K,
    )
    results = retriever.retrieve(query)

    print("PDF retrieval completed.")
    print(f"PDF path: {pdf_path}")
    print(f"Query: {query}")
    print(f"Index ID: {index_id}")
    print(f"Storage directory: ./{storage_dir}")
    print(f"Results found: {len(results)}")
    print("")

    for position, result in enumerate(results, start=1):
        node = result.node
        metadata = node.metadata or {}
        text = get_node_text(node)

        print("=" * 80)
        print(f"Result #{position}")
        print(f"Score: {result.score}")
        print(f"Node ID: {node.node_id}")
        print("Metadata:")
        print(json.dumps(metadata, indent=2, ensure_ascii=False, default=str))
        print("")
        print("Text:")
        print(text)
        print("")


if __name__ == "__main__":
    main()
