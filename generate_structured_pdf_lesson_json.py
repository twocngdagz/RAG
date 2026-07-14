import argparse
import json
import os
import re
import sys
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
from llama_index.llms.openai_like import OpenAILike


load_dotenv()

DEFAULT_QUERY = "Generate a student-friendly lesson from this PDF chapter."
DEFAULT_STORAGE_DIR = "./storage/structured_pdf_sample"
DEFAULT_INDEX_ID = "structured_pdf_sample"
OUTPUT_FILE = Path("output/structured_pdf_lesson.generated.json")
SIMILARITY_TOP_K = 8
TEXT_PREVIEW_MAX_CHARS = 300

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "mistralai/mistral-medium-3.5-128b")


def require_env() -> None:
    if not NVIDIA_API_KEY:
        print("Missing NVIDIA_API_KEY.")
        print("Create a real .env file from .env.example and add your NVIDIA API key.")
        sys.exit(1)


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
        description="Generate structured JSON lesson material from a structured PDF index."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional lesson query. Uses the default query when omitted.",
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


def lesson_query_from_args(args: argparse.Namespace) -> str:
    return " ".join(args.query).strip() or DEFAULT_QUERY


def validate_storage_dir(storage_dir: Path) -> None:
    if not storage_dir.exists():
        raise SystemExit(f"Storage directory does not exist: {storage_dir}")

    if not storage_dir.is_dir():
        raise SystemExit(f"Storage path is not a directory: {storage_dir}")


def exact_match_filter(key: str, value: Any) -> ExactMatchFilter:
    if isinstance(value, bool):
        # LlamaIndex validates filter values as strict int/float/str/list,
        # so bool exact matches need to bypass Pydantic while preserving EQ semantics.
        return ExactMatchFilter.model_construct(
            key=key,
            value=value,
            operator=FilterOperator.EQ,
        )

    return ExactMatchFilter(key=key, value=value)


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


def build_text_preview(text: str, max_chars: int = TEXT_PREVIEW_MAX_CHARS) -> str:
    normalized_text = re.sub(r"\s+", " ", text).strip()

    if len(normalized_text) <= max_chars:
        return normalized_text

    return f"{normalized_text[: max_chars - 3].rstrip()}..."


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


def build_source_chunks(results) -> list[dict]:
    source_chunks = []

    for result in results:
        node = result.node
        metadata = node.metadata or {}
        text = get_node_text(node)

        source_chunks.append(
            {
                "node_id": node.node_id,
                "source_pdf": metadata.get("source_pdf"),
                "chapter": metadata.get("chapter"),
                "chapter_number": metadata.get("chapter_number"),
                "section": metadata.get("section"),
                "topic": metadata.get("topic"),
                "content_type": metadata.get("content_type"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "is_front_matter": metadata.get("is_front_matter"),
                "text_preview": build_text_preview(text),
            }
        )

    return source_chunks


def single_value(values: list[Any]) -> Any:
    non_empty_values = [value for value in values if value is not None]
    unique_values = []

    for value in non_empty_values:
        if value not in unique_values:
            unique_values.append(value)

    if len(unique_values) == 1:
        return unique_values[0]

    return None


def build_source_info(
    index_id: str,
    storage_dir: Path,
    active_filters: dict[str, Any],
    source_chunks: list[dict],
) -> dict:
    chapter = active_filters.get("chapter")
    chapter_number = active_filters.get("chapter_number")

    if chapter is None:
        chapter = single_value([chunk["chapter"] for chunk in source_chunks])

    if chapter_number is None:
        chapter_number = single_value(
            [chunk["chapter_number"] for chunk in source_chunks]
        )

    return {
        "index_id": index_id,
        "storage_dir": str(storage_dir),
        "chapter": chapter,
        "chapter_number": chapter_number,
        "filters": active_filters,
    }


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
                    f"Source PDF: {metadata.get('source_pdf')}",
                    f"Chapter: {metadata.get('chapter')}",
                    f"Chapter number: {metadata.get('chapter_number')}",
                    f"Section: {metadata.get('section')}",
                    f"Topic: {metadata.get('topic')}",
                    f"Content type: {metadata.get('content_type')}",
                    f"Pages: {metadata.get('page_start')}-{metadata.get('page_end')}",
                    f"Is front matter: {metadata.get('is_front_matter')}",
                    "Text:",
                    get_node_text(node),
                ]
            )
        )

    return "\n\n---\n\n".join(context_blocks)


def format_context_summary(results) -> str:
    lines = []

    for position, result in enumerate(results, start=1):
        node = result.node
        metadata = node.metadata or {}
        lines.append(
            " | ".join(
                [
                    f"#{position}",
                    f"score={result.score}",
                    f"node_id={node.node_id}",
                    f"chapter={metadata.get('chapter')}",
                    f"chapter_number={metadata.get('chapter_number')}",
                    f"content_type={metadata.get('content_type')}",
                    f"pages={metadata.get('page_start')}-{metadata.get('page_end')}",
                    f"front_matter={metadata.get('is_front_matter')}",
                ]
            )
        )

    return "\n".join(lines)


def build_prompt(
    lesson_query: str,
    context: str,
    source_info: dict,
    source_chunks: list[dict],
) -> str:
    source_info_json = json.dumps(source_info, ensure_ascii=False, default=str)
    source_chunk_ids_json = json.dumps(
        [source_chunk["node_id"] for source_chunk in source_chunks],
        ensure_ascii=False,
    )

    return f"""
Return valid JSON only.
No Markdown, no code fences, no comments, no text outside the JSON object.

Create a student-friendly lesson based on the user's requested topic and the retrieved PDF context.

Requested lesson:
{lesson_query}

Rules:
- Use only the retrieved PDF context.
- Do not invent unsupported facts.
- Do not use outside knowledge.
- If the retrieved context is not enough to create a lesson, return the JSON schema anyway and write a clear simple_explanation saying the retrieved context is insufficient.
- Keep wording student-friendly.
- If a string field is unsupported, use "Not available in retrieved context."
- If a list field is unsupported, use [].
- The source field should equal the source object provided below.
- Set source_chunks to [] in your model response. The application will attach the exact retrieved source_chunks list, including text_preview, after validation.
- Each key_ideas item must include source_chunk_ids.
- source_chunk_ids must only use node IDs from the retrieved source chunk IDs list.
- Use at least one source_chunk_ids entry for every key idea when the idea is supported by retrieved context.

Source object:
{source_info_json}

Retrieved source chunk IDs:
{source_chunk_ids_json}

Retrieved PDF context:
{context}

Return this JSON shape:
{{
  "lesson_title": "string",
  "source": {{
    "index_id": "string",
    "storage_dir": "string",
    "chapter": "string or null",
    "chapter_number": 0,
    "filters": {{}}
  }},
  "lesson_level": "string",
  "topic": "string",
  "simple_explanation": "string",
  "key_ideas": [
    {{
      "idea": "string",
      "source_chunk_ids": [
        "string"
      ]
    }}
  ],
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
      "source_pdf": "string or null",
      "chapter": "string or null",
      "chapter_number": 0,
      "section": "string or null",
      "topic": "string or null",
      "content_type": "string or null",
      "page_start": "number or string or null",
      "page_end": "number or string or null",
      "is_front_matter": true,
      "text_preview": "string"
    }}
  ]
}}
"""


def parse_json_response(raw_response: str) -> Any:
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as error:
        print("Raw model response:")
        print("=" * 80)
        print(raw_response)
        print("=" * 80)
        print(f"JSON parsing error: {error}")
        sys.exit(1)


def validate_source_references(
    lesson_json: Any,
    retrieved_node_ids: list[str],
) -> None:
    if not isinstance(lesson_json, dict):
        raise ValueError("Lesson JSON must be an object.")

    key_ideas = lesson_json.get("key_ideas")
    if not isinstance(key_ideas, list):
        raise ValueError("key_ideas must be a list.")

    retrieved_node_id_set = set(retrieved_node_ids)
    unknown_references = []

    for idea_position, key_idea in enumerate(key_ideas, start=1):
        if not isinstance(key_idea, dict):
            raise ValueError(f"key_ideas[{idea_position}] must be an object.")

        source_chunk_ids = key_idea.get("source_chunk_ids")
        if not isinstance(source_chunk_ids, list):
            raise ValueError(
                f"key_ideas[{idea_position}].source_chunk_ids must be a list."
            )

        for source_chunk_id in source_chunk_ids:
            if not isinstance(source_chunk_id, str):
                raise ValueError(
                    f"key_ideas[{idea_position}].source_chunk_ids must contain strings."
                )

            if source_chunk_id not in retrieved_node_id_set:
                unknown_references.append(source_chunk_id)

    if unknown_references:
        unique_unknown_references = sorted(set(unknown_references))
        raise ValueError(
            "Unknown source chunk IDs referenced in key_ideas: "
            f"{', '.join(unique_unknown_references)}. "
            "Key ideas may only reference retrieved chunk IDs."
        )


def apply_grounding_metadata(
    lesson_json: dict,
    source_info: dict,
    source_chunks: list[dict],
) -> dict:
    lesson_json["source"] = source_info
    lesson_json["source_chunks"] = source_chunks
    return lesson_json


def main() -> None:
    require_env()
    args = parse_args()
    lesson_query = lesson_query_from_args(args)
    storage_dir = Path(args.storage_dir)
    validate_storage_dir(storage_dir)
    metadata_filters, active_filters = build_metadata_filters(args)

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
        max_tokens=2200,
        timeout=120,
    )

    storage_context = StorageContext.from_defaults(
        persist_dir=str(storage_dir),
    )
    index = load_index_from_storage(
        storage_context,
        index_id=args.index_id,
    )
    retriever = create_retriever(index, metadata_filters)
    results = retriever.retrieve(lesson_query)

    source_chunks = build_source_chunks(results)
    source_info = build_source_info(
        index_id=args.index_id,
        storage_dir=storage_dir,
        active_filters=active_filters,
        source_chunks=source_chunks,
    )
    context = format_context(results)
    context_summary = format_context_summary(results)
    prompt = build_prompt(
        lesson_query=lesson_query,
        context=context,
        source_info=source_info,
        source_chunks=source_chunks,
    )

    print("Structured PDF lesson JSON generation.")
    print(f"Query: {lesson_query}")
    print(f"Storage directory: {storage_dir}")
    print(f"Index ID: {args.index_id}")
    print_active_filters(active_filters)
    print(f"Retrieved chunks: {len(results)}")
    print("Retrieved context summary:")
    print(context_summary or "No retrieved chunks.")
    print("")

    try:
        response = Settings.llm.complete(prompt)
    except Exception as error:
        print(f"NVIDIA API call failed: {error}")
        sys.exit(1)

    lesson_json = parse_json_response(str(response).strip())
    retrieved_node_ids = [source_chunk["node_id"] for source_chunk in source_chunks]
    try:
        validate_source_references(lesson_json, retrieved_node_ids)
    except ValueError as error:
        print(f"Source reference validation error: {error}")
        sys.exit(1)

    lesson_json = apply_grounding_metadata(
        lesson_json=lesson_json,
        source_info=source_info,
        source_chunks=source_chunks,
    )
    formatted_json = json.dumps(lesson_json, indent=2, ensure_ascii=False)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(f"{formatted_json}\n", encoding="utf-8")

    print("Generated structured PDF lesson JSON:")
    print("=" * 80)
    print(formatted_json)
    print("=" * 80)
    print(f"Saved JSON to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
