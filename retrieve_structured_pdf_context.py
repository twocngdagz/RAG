import argparse
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.schema import MetadataMode
from llama_index.core.vector_stores import (
    ExactMatchFilter,
    FilterOperator,
    MetadataFilters,
)
from llama_index.embeddings.ollama import OllamaEmbedding


load_dotenv()

DEFAULT_QUERY = "What are the main learning topics in this chapter?"
DEFAULT_STORAGE_DIR = "./storage/structured_pdf_sample"
DEFAULT_INDEX_ID = "structured_pdf_sample"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
SIMILARITY_TOP_K = 5


def parse_bool(value: str) -> bool:
    normalized_value = value.strip().lower()

    if normalized_value == "true":
        return True

    if normalized_value == "false":
        return False

    raise argparse.ArgumentTypeError(
        "--front-matter must be either true or false."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve context from a structured PDF index."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional retrieval query. Uses the default query when omitted.",
    )
    parser.add_argument(
        "--storage-dir",
        default=DEFAULT_STORAGE_DIR,
        help="Persisted structured PDF index storage directory.",
    )
    parser.add_argument(
        "--index-id",
        default=DEFAULT_INDEX_ID,
        help="Persisted structured PDF index id.",
    )
    parser.add_argument("--chapter", help="Exact chapter metadata filter.")
    parser.add_argument(
        "--chapter-number",
        type=int,
        help="Exact integer chapter_number metadata filter.",
    )
    parser.add_argument(
        "--content-type",
        dest="content_type",
        help="Exact content_type metadata filter.",
    )
    parser.add_argument(
        "--front-matter",
        dest="front_matter",
        type=parse_bool,
        help="Exact boolean is_front_matter metadata filter: true or false.",
    )
    return parser.parse_args()


def query_from_args(args: argparse.Namespace) -> str:
    return " ".join(args.query).strip() or DEFAULT_QUERY


def validate_storage_dir(storage_dir: Path) -> None:
    if not storage_dir.exists():
        raise SystemExit(f"Storage directory does not exist: {storage_dir}")

    if not storage_dir.is_dir():
        raise SystemExit(f"Storage path is not a directory: {storage_dir}")


def build_metadata_filters(
    args: argparse.Namespace,
) -> tuple[MetadataFilters | None, dict[str, Any]]:
    active_filters: dict[str, Any] = {}

    if args.chapter:
        active_filters["chapter"] = args.chapter

    if args.chapter_number is not None:
        active_filters["chapter_number"] = args.chapter_number

    if args.content_type:
        active_filters["content_type"] = args.content_type

    if args.front_matter is not None:
        active_filters["is_front_matter"] = args.front_matter

    if not active_filters:
        return None, active_filters

    return (
        MetadataFilters(
            filters=[
                exact_match_filter(key=key, value=value)
                for key, value in active_filters.items()
            ]
        ),
        active_filters,
    )


def exact_match_filter(key: str, value: Any) -> ExactMatchFilter:
    if isinstance(value, bool):
        # LlamaIndex currently validates filter values as strict int/float/str/list,
        # so bool exact matches need to bypass Pydantic while preserving EQ semantics.
        return ExactMatchFilter.model_construct(
            key=key,
            value=value,
            operator=FilterOperator.EQ,
        )

    return ExactMatchFilter(key=key, value=value)


def create_retriever(index, metadata_filters: MetadataFilters | None):
    retriever_args = {"similarity_top_k": SIMILARITY_TOP_K}

    if metadata_filters is not None:
        retriever_args["filters"] = metadata_filters

    return index.as_retriever(**retriever_args)


def get_node_text(node) -> str:
    try:
        return node.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(node, "text", "") or ""


def format_filter_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()

    return str(value)


def print_active_filters(active_filters: dict[str, Any]) -> None:
    print("Active filters:")

    if not active_filters:
        print("- None")
    else:
        for key, value in active_filters.items():
            print(f"- {key}: {format_filter_value(value)}")

    print("")


def source_metadata_summary(source_metadata: Any) -> str:
    if not isinstance(source_metadata, dict) or not source_metadata:
        return "None"

    summary_fields = [
        "page_label",
        "file_name",
        "file_path",
        "file_type",
        "file_size",
        "creation_date",
        "last_modified_date",
    ]
    summary = {
        field: source_metadata[field]
        for field in summary_fields
        if field in source_metadata
    }

    if not summary:
        summary = source_metadata

    return json.dumps(summary, ensure_ascii=False, default=str)


def main() -> None:
    args = parse_args()
    query = query_from_args(args)
    storage_dir = Path(args.storage_dir)
    validate_storage_dir(storage_dir)
    metadata_filters, active_filters = build_metadata_filters(args)

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    storage_context = StorageContext.from_defaults(
        persist_dir=str(storage_dir),
    )
    index = load_index_from_storage(
        storage_context,
        index_id=args.index_id,
    )
    retriever = create_retriever(index, metadata_filters)
    results = retriever.retrieve(query)

    print("Structured PDF retrieval completed.")
    print(f"Query: {query}")
    print(f"Storage directory: {storage_dir}")
    print(f"Index ID: {args.index_id}")
    print_active_filters(active_filters)
    print(f"Results found: {len(results)}")
    print("")

    for position, result in enumerate(results, start=1):
        node = result.node
        metadata = node.metadata or {}
        source_metadata = metadata.get("source_metadata")

        print("=" * 80)
        print(f"Result #{position}")
        print(f"Score: {result.score}")
        print(f"Node ID: {node.node_id}")
        print(f"Source PDF: {metadata.get('source_pdf')}")
        print(f"Chapter: {metadata.get('chapter')}")
        print(f"Chapter number: {metadata.get('chapter_number')}")
        print(f"Section: {metadata.get('section')}")
        print(f"Topic: {metadata.get('topic')}")
        print(f"Content type: {metadata.get('content_type')}")
        print(f"Pages: {metadata.get('page_start')}–{metadata.get('page_end')}")
        print(f"Is front matter: {metadata.get('is_front_matter')}")
        print(f"Source metadata summary: {source_metadata_summary(source_metadata)}")
        print("")
        print(get_node_text(node))
        print("")


if __name__ == "__main__":
    main()
