import argparse
import json
import os
import sys
from pathlib import Path

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
OUTPUT_FILE = Path("output/lesson.generated.json")
DEFAULT_QUERY = "Generate a Year 5 math lesson about place value."
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
        description="Generate a structured JSON lesson from retrieved local context."
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
    lesson_query = " ".join(args.query).strip() or DEFAULT_QUERY

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


def build_source_chunks(results) -> list[dict]:
    source_chunks = []

    for result in results:
        node = result.node
        metadata = node.metadata or {}

        source_chunks.append(
            {
                "node_id": node.node_id,
                "content_type": metadata.get("content_type"),
                "chapter": metadata.get("chapter"),
                "section": metadata.get("section"),
                "topic": metadata.get("topic"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
            }
        )

    return source_chunks


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
                    f"Pages: {metadata.get('page_start')}-{metadata.get('page_end')}",
                    "Text:",
                    node.get_content(),
                ]
            )
        )

    return "\n\n---\n\n".join(context_blocks)


def build_prompt(query: str, context: str, source_chunks: list[dict]) -> str:
    source_chunks_json = json.dumps(source_chunks)
    content_types = sorted(
        {
            source_chunk["content_type"]
            for source_chunk in source_chunks
            if source_chunk["content_type"]
        }
    )
    content_types_json = json.dumps(content_types)

    return f"""
Return valid JSON only.
No Markdown, no code fences, no comments, no text outside the JSON object.

Create structured learning material for a Year 5 student.
Requested lesson:
{query}

Rules:
Use only the retrieved context.
Do not invent unsupported book facts.
Do not add new example numbers or question numbers not in the retrieved context.
You may calculate answers for practice questions found in the retrieved context.
If a string field is unsupported, use "Not available in retrieved context."
If a list field is unsupported, use [].
Available retrieved content_type values: {content_types_json}
Only populate worked_examples from retrieved chunks with content_type "worked_example".
Only populate practice_questions from retrieved chunks with content_type "exercise".
Only populate answer_key from retrieved chunks with content_type "exercise".
Only populate common_mistakes from retrieved chunks with content_type "common_mistake".
Do not turn common mistakes into worked examples, practice questions, or answer keys.
Keep the lesson student-friendly.

Retrieved context:
{context}

The source_chunks field must exactly equal:
{source_chunks_json}

Return this JSON shape:
{{
  "lesson_title": "string",
  "grade": "Year 5",
  "domain": "Math",
  "topic": "string",
  "simple_explanation": "string",
  "key_idea": "string",
  "worked_examples": [
    {{
      "question": "string",
      "solution": "string"
    }}
  ],
  "practice_questions": [
    {{
      "question": "string"
    }}
  ],
  "answer_key": [
    {{
      "question": "string",
      "answer": "string"
    }}
  ],
  "common_mistakes": [
    {{
      "mistake": "string",
      "correction": "string"
    }}
  ],
  "source_chunks": [
    {{
      "node_id": "string",
      "content_type": "string",
      "chapter": "string",
      "section": "string",
      "topic": "string",
      "page_start": 0,
      "page_end": 0
    }}
  ]
}}
"""


def parse_json_response(raw_response: str):
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as error:
        print("Raw model response:")
        print("=" * 80)
        print(raw_response)
        print("=" * 80)
        print(f"JSON parsing error: {error}")
        sys.exit(1)


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
        max_tokens=1600,
        timeout=120,
    )

    index = load_index()
    retriever = create_retriever(index, metadata_filters)

    results = retriever.retrieve(retrieval_query)
    context = format_context(results)
    source_chunks = build_source_chunks(results)
    prompt = build_prompt(lesson_query, context, source_chunks)

    print("Retrieved context used for JSON lesson generation:")
    print(f"Lesson query: {lesson_query}")
    print_active_filters(active_filters)
    print("=" * 80)
    print(context)
    print("=" * 80)
    print("")

    try:
        response = Settings.llm.complete(prompt)
    except Exception as error:
        print(f"NVIDIA API call failed: {error}")
        sys.exit(1)
    lesson_json = parse_json_response(str(response).strip())
    formatted_json = json.dumps(lesson_json, indent=2, ensure_ascii=False)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(f"{formatted_json}\n", encoding="utf-8")

    print("Generated JSON lesson:")
    print("=" * 80)
    print(formatted_json)
    print("=" * 80)
    print(f"Saved JSON to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
