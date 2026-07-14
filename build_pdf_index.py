import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.ollama import OllamaEmbedding


load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
LOW_TEXT_WARNING_THRESHOLD = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a separate local LlamaIndex vector index from one PDF."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to index.")
    return parser.parse_args()


def validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"PDF file does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise SystemExit(f"PDF path is not a file: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit(f"Input file must be a PDF: {pdf_path}")


def get_document_text(document) -> str:
    try:
        return document.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(document, "text", "") or ""


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf_path)
    validate_pdf_path(pdf_path)

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    documents = SimpleDirectoryReader(input_files=[str(pdf_path)]).load_data()

    if not documents:
        raise SystemExit(f"No LlamaIndex documents were loaded from: {pdf_path}")

    total_characters = sum(
        len(get_document_text(document)) for document in documents
    )

    index_id = f"pdf_{pdf_path.stem}"
    storage_dir = Path("storage") / f"pdf_{pdf_path.stem}"

    index = VectorStoreIndex.from_documents(documents)
    index.set_index_id(index_id)
    index.storage_context.persist(persist_dir=str(storage_dir))

    print("PDF index built successfully.")
    print(f"PDF path: {pdf_path}")
    print(f"Documents loaded: {len(documents)}")
    print(f"Total extracted characters: {total_characters}")
    print(f"Index ID: {index_id}")
    print(f"Storage directory: ./{storage_dir}")
    print(f"Embedding model: {OLLAMA_EMBED_MODEL}")

    if total_characters < LOW_TEXT_WARNING_THRESHOLD:
        print(
            "Warning: total extracted characters is very low. "
            "Use a text-based PDF for useful search; scanned/image-based PDFs may need OCR "
            "or LlamaParse later."
        )


if __name__ == "__main__":
    main()
