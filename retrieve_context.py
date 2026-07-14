import argparse
import os

from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.ollama import OllamaEmbedding


load_dotenv()

STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage/year5_math_tiny")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
INDEX_ID = "year5_math_tiny"

DEFAULT_QUERY = "What is place value and what mistakes do students make?"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Retrieve chunks from the local learning-material index."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional retrieval query. Uses the default query when omitted.",
    )
    parser.add_argument("--topic", help="Exact topic metadata filter.")
    parser.add_argument("--section", help="Exact section metadata filter.")
    parser.add_argument(
        "--content-type",
        dest="content_type",
        help="Exact content_type metadata filter.",
    )

    args = parser.parse_args()
    query = " ".join(args.query).strip() or DEFAULT_QUERY

    return args, query


def build_metadata_filters(args):
    active_filters = {
        "topic": args.topic,
        "section": args.section,
        "content_type": args.content_type,
    }
    active_filters = {
        key: value for key, value in active_filters.items() if value
    }

    if not active_filters:
        return None, active_filters

    return (
        MetadataFilters(
            filters=[
                ExactMatchFilter(key=key, value=value)
                for key, value in active_filters.items()
            ]
        ),
        active_filters,
    )


def create_retriever(index, metadata_filters):
    retriever_args = {"similarity_top_k": 4}

    if metadata_filters is not None:
        retriever_args["filters"] = metadata_filters

    return index.as_retriever(**retriever_args)


def print_active_filters(active_filters: dict[str, str]) -> None:
    print("Active filters:")

    if not active_filters:
        print("- None")
    else:
        for key, value in active_filters.items():
            print(f"- {key}: {value}")

    print("")


def main() -> None:
    args, query = parse_args()
    metadata_filters, active_filters = build_metadata_filters(args)

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    storage_context = StorageContext.from_defaults(
        persist_dir=STORAGE_DIR,
    )

    index = load_index_from_storage(
        storage_context,
        index_id=INDEX_ID,
    )

    retriever = create_retriever(index, metadata_filters)

    results = retriever.retrieve(query)

    print("Retrieval test completed.")
    print(f"Query: {query}")
    print_active_filters(active_filters)
    print(f"Results found: {len(results)}")
    print("")

    for position, result in enumerate(results, start=1):
        node = result.node
        metadata = node.metadata or {}

        print("=" * 80)
        print(f"Result #{position}")
        print(f"Score: {result.score}")
        print(f"Node ID: {node.node_id}")
        print(f"Content type: {metadata.get('content_type')}")
        print(f"Chapter: {metadata.get('chapter')}")
        print(f"Section: {metadata.get('section')}")
        print(f"Topic: {metadata.get('topic')}")
        print(f"Pages: {metadata.get('page_start')}–{metadata.get('page_end')}")
        print("")
        print(node.get_content())
        print("")


if __name__ == "__main__":
    main()
