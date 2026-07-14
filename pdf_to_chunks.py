import argparse
import json
import re
from pathlib import Path
from typing import Any

from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import MetadataMode


EXTRACTED_DIR = Path("extracted")
LOW_TEXT_WARNING_THRESHOLD = 500


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert LlamaIndex-loaded PDF documents into structured chunks."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to convert.")
    return parser.parse_args()


def validate_pdf_path(pdf_path: Path) -> None:
    if not pdf_path.exists():
        raise SystemExit(f"PDF file does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise SystemExit(f"PDF path is not a file: {pdf_path}")

    if pdf_path.suffix.lower() != ".pdf":
        raise SystemExit(f"Input file must be a PDF: {pdf_path}")


def to_json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def get_document_text(document: Any) -> str:
    try:
        return document.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(document, "text", "") or ""


def get_page_number(metadata: dict, fallback: int) -> int:
    for key in ("page_label", "page_number", "page"):
        value = metadata.get(key)
        if value is None:
            continue

        if isinstance(value, int):
            return value

        match = re.search(r"\d+", str(value))
        if match:
            return int(match.group(0))

    return fallback


def build_chunks(pdf_path: Path, documents: list[Any]) -> list[dict]:
    chunks = []

    for document_number, document in enumerate(documents, start=1):
        metadata = to_json_safe(getattr(document, "metadata", None) or {})
        text = get_document_text(document)
        page_number = get_page_number(metadata, document_number)

        chunks.append(
            {
                "id": f"{pdf_path.stem}_chunk_{document_number:03d}",
                "source_pdf": str(pdf_path),
                "source_type": "pdf",
                "domain": None,
                "grade": None,
                "book_id": pdf_path.stem,
                "book_title": pdf_path.stem,
                "chapter": None,
                "section": None,
                "topic": None,
                "content_type": "unknown",
                "page_start": page_number,
                "page_end": page_number,
                "text": text,
                "metadata": metadata,
            }
        )

    return chunks


def format_chunks_text(pdf_path: Path, chunks: list[dict], total_characters: int) -> str:
    lines = [
        f"Source PDF: {pdf_path}",
        f"Chunks: {len(chunks)}",
        f"Total characters: {total_characters}",
        "",
    ]

    for chunk in chunks:
        lines.extend(
            [
                "=" * 80,
                f"Chunk ID: {chunk['id']}",
                f"Page range: {chunk['page_start']}–{chunk['page_end']}",
                f"Content type: {chunk['content_type']}",
                "Metadata:",
                json.dumps(chunk["metadata"], indent=2, ensure_ascii=False),
                "",
                chunk["text"],
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf_path)
    validate_pdf_path(pdf_path)

    documents = SimpleDirectoryReader(input_files=[str(pdf_path)]).load_data()
    chunks = build_chunks(pdf_path, documents)
    total_characters = sum(len(chunk["text"]) for chunk in chunks)

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    json_output_path = EXTRACTED_DIR / f"{pdf_path.stem}.chunks.json"
    txt_output_path = EXTRACTED_DIR / f"{pdf_path.stem}.chunks.txt"

    json_output_path.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(
        format_chunks_text(pdf_path, chunks, total_characters),
        encoding="utf-8",
    )

    print("PDF chunks created successfully.")
    print(f"PDF path: {pdf_path}")
    print(f"Documents loaded: {len(documents)}")
    print(f"Chunks created: {len(chunks)}")
    print(f"Total extracted characters: {total_characters}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")

    if total_characters < LOW_TEXT_WARNING_THRESHOLD:
        print(
            "Warning: total extracted characters is very low. "
            "The PDF may be scanned/image-based and may need OCR or LlamaParse later."
        )


if __name__ == "__main__":
    main()
