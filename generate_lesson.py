import argparse
import os
import sys

from dotenv import load_dotenv
from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.openai_like import OpenAILike


load_dotenv()

STORAGE_DIR = os.getenv("STORAGE_DIR", "./storage/year5_math_tiny")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "mistralai/mistral-medium-3.5-128b")

INDEX_ID = "year5_math_tiny"

LESSON_QUERY = """
Generate a Year 5 math lesson about place value.
Include explanation, worked examples, practice questions, answer key, and common mistakes.
"""

RETRIEVAL_REQUIREMENTS = (
    "Include explanation, worked examples, practice questions, answer key, "
    "and common mistakes."
)


def require_env() -> None:
    if not NVIDIA_API_KEY:
        print("Missing NVIDIA_API_KEY.")
        print("Create a real .env file from .env.example and add your NVIDIA API key.")
        sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a lesson from retrieved local context."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional lesson query. Uses the default place value query when omitted.",
    )
    parser.add_argument("--topic", help="Exact topic metadata filter.")
    parser.add_argument("--section", help="Exact section metadata filter.")
    parser.add_argument(
        "--content-type",
        dest="content_type",
        help="Exact content_type metadata filter.",
    )

    args = parser.parse_args()
    lesson_query = " ".join(args.query).strip() or LESSON_QUERY.strip()

    return args, lesson_query


def load_index():
    storage_context = StorageContext.from_defaults(
        persist_dir=STORAGE_DIR,
    )

    return load_index_from_storage(
        storage_context,
        index_id=INDEX_ID,
    )


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


def build_retrieval_query(lesson_query: str) -> str:
    return f"{lesson_query}\n{RETRIEVAL_REQUIREMENTS}"


def format_context(results) -> str:
    context_blocks = []

    for position, result in enumerate(results, start=1):
        node = result.node
        metadata = node.metadata or {}

        context_blocks.append(
            "\n".join(
                [
                    f"Context chunk #{position}",
                    f"Score: {result.score}",
                    f"Node ID: {node.node_id}",
                    f"Content type: {metadata.get('content_type')}",
                    f"Chapter: {metadata.get('chapter')}",
                    f"Section: {metadata.get('section')}",
                    f"Topic: {metadata.get('topic')}",
                    f"Pages: {metadata.get('page_start')}–{metadata.get('page_end')}",
                    "Text:",
                    node.get_content(),
                ]
            )
        )

    return "\n\n---\n\n".join(context_blocks)


def build_prompt(query: str, context: str) -> str:
    return f"""
You are creating learning material for a Year 5 student.

User's requested lesson:
{query}

Use only the retrieved context below.
Do not invent facts that are not supported by the context.
Do not add new worked-example numbers or practice-question numbers that are not in the retrieved context.
You may calculate answers for practice questions found in the retrieved context.
If the retrieved context does not contain information for a section, write "Not available in retrieved context." for that section.
Keep the explanation simple and student-friendly.
Base the lesson topic on the user's requested lesson and the retrieved context.

Learning material target:
- Domain: Math
- Grade: Year 5

Retrieved context:
{context}

Create the lesson with this exact structure:

# Lesson title

# Simple explanation

# Key idea

# Worked examples

# Practice questions

# Answer key

# Common mistakes
"""


def main() -> None:
    require_env()
    args, lesson_query = parse_args()
    metadata_filters, active_filters = build_metadata_filters(args)
    retrieval_query = build_retrieval_query(lesson_query)

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    Settings.llm = OpenAILike(
        model=NVIDIA_MODEL,
        api_base=NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        is_chat_model=True,
        context_window=262144,
        max_tokens=2500,
    )

    index = load_index()

    retriever = create_retriever(index, metadata_filters)

    results = retriever.retrieve(retrieval_query)
    context = format_context(results)
    prompt = build_prompt(lesson_query, context)

    print("Retrieved context used for lesson generation:")
    print(f"Lesson query: {lesson_query}")
    print_active_filters(active_filters)
    print("=" * 80)
    print(context)
    print("=" * 80)
    print("")

    response = Settings.llm.complete(prompt)

    print("Generated lesson:")
    print("=" * 80)
    print(response)


if __name__ == "__main__":
    main()
