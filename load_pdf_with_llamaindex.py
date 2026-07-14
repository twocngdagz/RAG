import argparse
import json
from pathlib import Path
from typing import Any

from llama_index.core import SimpleDirectoryReader
from llama_index.core.schema import MetadataMode


EXTRACTED_DIR = Path("extracted")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load one PDF with LlamaIndex and save extracted documents."
    )
    parser.add_argument("pdf_path", help="Path to the PDF file to inspect.")
    return parser.parse_args()


def get_document_id(document: Any) -> str | None:
    for attribute in ("doc_id", "id_", "node_id"):
        value = getattr(document, attribute, None)
        if value:
            return str(value)

    return None


def get_document_text(document: Any) -> str:
    try:
        return document.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(document, "text", "") or ""


def format_text_output(payload: dict) -> str:
    lines = [
        f"Source PDF: {payload['source_pdf']}",
        f"Document count: {payload['document_count']}",
        f"Total characters: {payload['total_characters']}",
        "",
    ]

    for document in payload["documents"]:
        lines.extend(
            [
                "=" * 80,
                f"Document #{document['document_number']}",
                f"Document ID: {document['document_id']}",
                f"Character count: {document['character_count']}",
                "Metadata:",
                json.dumps(document["metadata"], indent=2, ensure_ascii=False),
                "",
                document["text"],
                "",
            ]
        )

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    pdf_path = Path(args.pdf_path)

    if not pdf_path.exists():
        raise SystemExit(f"PDF file does not exist: {pdf_path}")

    if not pdf_path.is_file():
        raise SystemExit(f"PDF path is not a file: {pdf_path}")

    documents = SimpleDirectoryReader(input_files=[str(pdf_path)]).load_data()

    extracted_documents = []
    empty_text_count = 0

    for document_number, document in enumerate(documents, start=1):
        text = get_document_text(document)
        metadata = getattr(document, "metadata", None) or {}
        character_count = len(text)

        if not text.strip():
            empty_text_count += 1

        extracted_documents.append(
            {
                "document_number": document_number,
                "document_id": get_document_id(document),
                "character_count": character_count,
                "metadata": metadata,
                "text": text,
            }
        )

    total_characters = sum(
        document["character_count"] for document in extracted_documents
    )
    payload = {
        "source_pdf": str(pdf_path),
        "document_count": len(extracted_documents),
        "total_characters": total_characters,
        "documents": extracted_documents,
    }

    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    json_output_path = EXTRACTED_DIR / f"{pdf_path.stem}.llamaindex.documents.json"
    txt_output_path = EXTRACTED_DIR / f"{pdf_path.stem}.llamaindex.txt"

    json_output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    txt_output_path.write_text(format_text_output(payload), encoding="utf-8")

    print("PDF loading completed.")
    print(f"PDF path: {pdf_path}")
    print(f"LlamaIndex documents returned: {len(extracted_documents)}")
    print(f"Total extracted characters: {total_characters}")
    print(f"JSON output path: {json_output_path}")
    print(f"TXT output path: {txt_output_path}")

    if extracted_documents and empty_text_count > len(extracted_documents) / 2:
        print(
            "Warning: most returned documents have empty text. "
            "The PDF may be scanned/image-based and may need OCR or LlamaParse later."
        )


if __name__ == "__main__":
    main()
