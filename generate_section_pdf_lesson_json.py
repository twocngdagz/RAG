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

from retrieval_ordering import (
    RetrievalOrderingError,
    build_section_coverage,
    order_retrieved_nodes,
)
from section_scope import SectionScopeError, resolve_section_scope


load_dotenv()

DEFAULT_QUERY = "Generate a student-friendly lesson from this section."
DEFAULT_STORAGE_DIR = "./storage/section_clean_pdf_sample"
DEFAULT_INDEX_ID = "section_clean_pdf_sample"
DEFAULT_TOP_K = 8
DEFAULT_OUTPUT = "output/section_pdf_lesson.generated.json"
DEFAULT_STRUCTURE_RESOLUTION = "extracted/sample.structure_resolution.json"
TEXT_PREVIEW_MAX_CHARS = 300

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "mistralai/mistral-medium-3.5-128b")


class SectionPdfLessonGenerationError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        raw_model_response: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.raw_model_response = raw_model_response


def require_env() -> None:
    if not NVIDIA_API_KEY:
        raise SectionPdfLessonGenerationError(
            "Missing NVIDIA_API_KEY.\n"
            "Create a real .env file from .env.example and add your NVIDIA API key.",
            code="missing_api_key",
        )


def parse_bool(value: str) -> bool:
    normalized_value = value.strip().lower()

    if normalized_value == "true":
        return True

    if normalized_value == "false":
        return False

    raise argparse.ArgumentTypeError("--front-matter must be either true or false.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate grounded JSON lesson material from a section-enriched PDF index."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional lesson query. Uses the default query when omitted.",
    )
    parser.add_argument(
        "--storage-dir",
        default=DEFAULT_STORAGE_DIR,
        help="Persisted section PDF index storage directory.",
    )
    parser.add_argument(
        "--index-id",
        default=DEFAULT_INDEX_ID,
        help="Persisted section PDF index id.",
    )
    parser.add_argument("--chapter", help="Exact chapter metadata filter.")
    parser.add_argument(
        "--chapter-number",
        type=int,
        help="Exact integer chapter_number metadata filter.",
    )
    parser.add_argument("--section", help="Exact section metadata filter.")
    parser.add_argument("--topic", help="Exact topic metadata filter.")
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
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help=f"Number of chunks to retrieve. Defaults to {DEFAULT_TOP_K}.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path. Defaults to {DEFAULT_OUTPUT}.",
    )
    parser.add_argument(
        "--structure-resolution",
        default=DEFAULT_STRUCTURE_RESOLUTION,
        help="Resolved document structure JSON used for descendant section expansion.",
    )
    parser.add_argument(
        "--include-descendants",
        action="store_true",
        help="Include descendant subsection titles for the requested --section.",
    )
    parser.add_argument(
        "--ordering",
        choices=("semantic", "document"),
        default="semantic",
        help="Source chunk and context order after semantic selection. Defaults to semantic.",
    )
    return parser.parse_args()


def lesson_query_from_args(args: argparse.Namespace) -> str:
    return " ".join(args.query).strip() or DEFAULT_QUERY


def validate_storage_dir(storage_dir: Path) -> None:
    if not storage_dir.exists():
        raise SectionPdfLessonGenerationError(
            f"Storage directory does not exist: {storage_dir}\n"
            "Build the section PDF index first:\n"
            'python build_section_pdf_index.py "extracted/sample.section_chunks.json"',
            code="missing_storage",
        )

    if not storage_dir.is_dir():
        raise SectionPdfLessonGenerationError(
            f"Storage path is not a directory: {storage_dir}",
            code="missing_storage",
        )


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
    include_section: bool = True,
) -> tuple[MetadataFilters | None, dict[str, Any]]:
    active_filters: dict[str, Any] = {}

    if args.chapter:
        active_filters["chapter"] = args.chapter

    if args.chapter_number is not None:
        active_filters["chapter_number"] = args.chapter_number

    if include_section and args.section:
        active_filters["section"] = args.section

    if args.topic:
        active_filters["topic"] = args.topic

    if args.content_type:
        active_filters["content_type"] = args.content_type

    if args.front_matter is not None:
        active_filters["is_front_matter"] = args.front_matter

    return metadata_filters_from_dict(active_filters), active_filters


def metadata_filters_from_dict(active_filters: dict[str, Any]) -> MetadataFilters | None:
    if not active_filters:
        return None

    return MetadataFilters(
        filters=[
            exact_match_filter(key=key, value=value)
            for key, value in active_filters.items()
        ]
    )


def create_retriever(index, metadata_filters: MetadataFilters | None, top_k: int):
    retriever_args = {"similarity_top_k": top_k}

    if metadata_filters is not None:
        retriever_args["filters"] = metadata_filters

    return index.as_retriever(**retriever_args)


def get_node_text(node) -> str:
    try:
        return node.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(node, "text", "") or ""


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_text_preview(text: str, max_chars: int = TEXT_PREVIEW_MAX_CHARS) -> str:
    normalized_text = normalize_whitespace(text)

    if len(normalized_text) <= max_chars:
        return normalized_text

    return f"{normalized_text[: max_chars - 3].rstrip()}..."


def format_filter_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()

    return str(value)


def print_active_filters(active_filters: dict[str, Any]) -> None:
    print("Filters applied:")

    if not active_filters:
        print("- None")
    else:
        for key, value in active_filters.items():
            print(f"- {key}: {format_filter_value(value)}")

    print("")


def load_section_index(storage_dir: Path, index_id: str):
    try:
        storage_context = StorageContext.from_defaults(
            persist_dir=str(storage_dir),
        )
        return load_index_from_storage(
            storage_context,
            index_id=index_id,
        )
    except Exception as error:
        raise SectionPdfLessonGenerationError(
            f"Could not load index '{index_id}' from storage directory '{storage_dir}'.\n"
            f"Error: {error}",
            code="index_load_failed",
        ) from error


def resolve_scope_from_args(args: argparse.Namespace) -> dict | None:
    if args.include_descendants and not args.section:
        raise SectionPdfLessonGenerationError(
            "--include-descendants requires --section.",
            code="invalid_request",
        )

    if not args.section:
        return None

    if not args.include_descendants:
        return {
            "requested_section": args.section,
            "chapter": args.chapter,
            "chapter_number": args.chapter_number,
            "parent_level": None,
            "include_descendants": False,
            "section_titles": [args.section],
        }

    try:
        scope = resolve_section_scope(
            structure_resolution_path=args.structure_resolution,
            section_title=args.section,
            chapter_number=args.chapter_number,
            include_descendants=True,
        )
    except SectionScopeError as error:
        error_message = str(error)
        if "file does not exist" in error_message:
            raise SectionPdfLessonGenerationError(
                f"Structure resolution file not found: {args.structure_resolution}",
                code="missing_structure_resolution",
            ) from error

        if "Section title not found" in error_message:
            raise SectionPdfLessonGenerationError(
                f"Section not found: {args.section}",
                code="section_not_found",
            ) from error

        if "multiple chapters" in error_message or "multiple times" in error_message:
            raise SectionPdfLessonGenerationError(
                error_message,
                code="ambiguous_section",
            ) from error

        raise SectionPdfLessonGenerationError(
            f"Section scope resolution error: {error}",
            code="section_scope_failed",
        ) from error

    if args.chapter and scope.get("chapter") != args.chapter:
        raise SectionPdfLessonGenerationError(
            f"Requested chapter filter {args.chapter!r} does not match resolved "
            f"section chapter {scope.get('chapter')!r}.",
            code="invalid_request",
        )

    return scope


def print_section_scope(scope: dict | None) -> None:
    if scope is None:
        return

    section_titles = scope.get("section_titles") or []

    print(f"Requested section: {scope.get('requested_section')}")
    print(f"Include descendants: {scope.get('include_descendants')}")

    if scope.get("include_descendants"):
        print(f"Resolved chapter: {scope.get('chapter')}")
        print(f"Resolved chapter number: {scope.get('chapter_number')}")

    print(f"Expanded section count: {len(section_titles)}")
    print("Expanded sections:")

    for section_title in section_titles:
        print(f"- {section_title}")

    print("")


def score_value(result) -> float:
    if result.score is None:
        return float("-inf")

    return float(result.score)


def merge_results(result_batches: list[list], top_k: int) -> list:
    merged_results = {}

    for results in result_batches:
        for result in results:
            node_id = result.node.node_id
            existing_result = merged_results.get(node_id)

            if existing_result is None or score_value(result) > score_value(
                existing_result
            ):
                merged_results[node_id] = result

    return sorted(
        merged_results.values(),
        key=score_value,
        reverse=True,
    )[:top_k]


def retrieve_once(
    index,
    query: str,
    active_filters: dict[str, Any],
    top_k: int,
) -> list:
    metadata_filters = metadata_filters_from_dict(active_filters)
    retriever = create_retriever(
        index=index,
        metadata_filters=metadata_filters,
        top_k=top_k,
    )
    return retriever.retrieve(query)


def retrieve_with_section_scope(
    index,
    query: str,
    args: argparse.Namespace,
    scope: dict,
    base_filters: dict[str, Any],
) -> list:
    resolved_filters = dict(base_filters)
    resolved_filters["chapter_number"] = scope["chapter_number"]
    result_batches = []

    for section_title in scope["section_titles"]:
        section_filters = dict(resolved_filters)
        section_filters["section"] = section_title
        result_batches.append(
            retrieve_once(
                index=index,
                query=query,
                active_filters=section_filters,
                top_k=args.top_k,
            )
        )

    return merge_results(result_batches=result_batches, top_k=args.top_k)


def build_context(results) -> str:
    context_blocks = []

    for position, result in enumerate(results, start=1):
        node = result.node
        metadata = node.metadata or {}

        context_blocks.append(
            "\n".join(
                [
                    f"Context chunk #{position}",
                    f"Node ID: {node.node_id}",
                    f"Source PDF: {metadata.get('source_pdf')}",
                    f"Book title: {metadata.get('book_title')}",
                    f"Chapter: {metadata.get('chapter')}",
                    f"Chapter number: {metadata.get('chapter_number')}",
                    f"Section: {metadata.get('section')}",
                    f"Topic: {metadata.get('topic')}",
                    f"Page start: {metadata.get('page_start')}",
                    f"Page end: {metadata.get('page_end')}",
                    "Text:",
                    get_node_text(node),
                ]
            )
        )

    return "\n\n---\n\n".join(context_blocks)


def build_source_info(
    index_id: str,
    storage_dir: str,
    query: str,
    active_filters: dict[str, Any],
    retrieved_chunk_count: int,
    section_scope: dict | None,
    ordering: str,
    section_coverage: dict,
) -> dict:
    source_filters = dict(active_filters)

    if section_scope is not None and section_scope.get("requested_section"):
        source_filters["section"] = section_scope["requested_section"]

    source_info = {
        "index_id": index_id,
        "storage_dir": storage_dir,
        "query": query,
        "filters": source_filters,
        "retrieved_chunk_count": retrieved_chunk_count,
        "ordering": ordering,
        "section_coverage": section_coverage,
    }

    if section_scope is not None:
        source_info.update(
            {
                "requested_section": section_scope.get("requested_section"),
                "include_descendants": section_scope.get("include_descendants"),
                "resolved_chapter": section_scope.get("chapter"),
                "resolved_chapter_number": section_scope.get("chapter_number"),
                "expanded_section_titles": section_scope.get("section_titles") or [],
            }
        )

    return source_info


def build_source_chunks(results) -> list[dict]:
    source_chunks = []

    for result in results:
        node = result.node
        metadata = node.metadata or {}
        text = get_node_text(node)

        source_chunks.append(
            {
                "node_id": node.node_id,
                "score": result.score,
                "source_pdf": metadata.get("source_pdf"),
                "book_title": metadata.get("book_title"),
                "chapter": metadata.get("chapter"),
                "chapter_number": metadata.get("chapter_number"),
                "section": metadata.get("section"),
                "topic": metadata.get("topic"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
                "text_preview": build_text_preview(text),
            }
        )

    return source_chunks


def build_prompt(
    query: str,
    context: str,
    source_chunk_ids: list[str],
    section_scope: dict | None,
) -> str:
    source_chunk_ids_json = json.dumps(source_chunk_ids, ensure_ascii=False)
    section_scope_text = ""

    if section_scope is not None and section_scope.get("include_descendants"):
        section_scope_json = json.dumps(
            {
                "parent_section": section_scope.get("requested_section"),
                "chapter": section_scope.get("chapter"),
                "chapter_number": section_scope.get("chapter_number"),
                "expanded_section_titles": section_scope.get("section_titles") or [],
            },
            ensure_ascii=False,
        )
        section_scope_text = f"""
The retrieved context belongs to one parent section and its subsections.
Use only these resolved section titles; do not invent section titles:
{section_scope_json}
"""

    return f"""
Return valid JSON only.
No Markdown, no code fences, no comments, no text outside the JSON object.

Create a student-friendly lesson using only the retrieved PDF context.

Requested lesson:
{query}

Rules:
- Use only the retrieved PDF context.
- Do not invent unsupported facts.
- Do not use outside knowledge.
- Keep the lesson practical and clear.
- If a string field is unsupported, use "Not available in retrieved context."
- If a list field is unsupported, use [].
- Every key_ideas item must include source_chunk_ids.
- worked_examples items may include source_chunk_ids when supported by retrieved context.
- common_misconceptions items may include source_chunk_ids when supported by retrieved context.
- source_chunk_ids must only use node IDs from the retrieved source chunk IDs list.
- Do not include source or source_chunks fields. The application will attach them after validation.

Retrieved source chunk IDs:
{source_chunk_ids_json}

{section_scope_text}

Retrieved PDF context:
{context}

Return this JSON shape:
{{
  "title": "string",
  "learning_objectives": [
    "string"
  ],
  "introduction": "string",
  "key_ideas": [
    {{
      "idea": "string",
      "source_chunk_ids": [
        "string"
      ]
    }}
  ],
  "explanation": "string",
  "worked_examples": [
    {{
      "title": "string",
      "explanation": "string",
      "source_chunk_ids": [
        "string"
      ]
    }}
  ],
  "common_misconceptions": [
    {{
      "misconception": "string",
      "correction": "string",
      "source_chunk_ids": [
        "string"
      ]
    }}
  ],
  "practice_questions": [
    {{
      "question": "string",
      "answer": "string"
    }}
  ],
  "summary": "string"
}}
"""


def parse_json_response(raw_response: str) -> Any:
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise SectionPdfLessonGenerationError(
            f"JSON parsing error: {error}",
            code="invalid_model_json",
            raw_model_response=raw_response,
        ) from error


def validate_source_id_list(
    value: Any,
    field_path: str,
    retrieved_node_id_set: set[str],
    unknown_references: list[str],
    *,
    required: bool,
) -> None:
    if value is None and not required:
        return

    if not isinstance(value, list):
        raise ValueError(f"{field_path} must be a list.")

    if required and not value:
        raise ValueError(f"{field_path} must contain at least one source chunk ID.")

    for source_chunk_id in value:
        if not isinstance(source_chunk_id, str):
            raise ValueError(f"{field_path} must contain strings.")

        if source_chunk_id not in retrieved_node_id_set:
            unknown_references.append(source_chunk_id)


def validate_optional_source_lists(
    lesson_json: dict,
    key: str,
    id_field: str,
    retrieved_node_id_set: set[str],
    unknown_references: list[str],
) -> None:
    items = lesson_json.get(key, [])

    if items is None:
        return

    if not isinstance(items, list):
        raise ValueError(f"{key} must be a list.")

    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{key}[{position}] must be an object.")

        validate_source_id_list(
            item.get(id_field),
            f"{key}[{position}].{id_field}",
            retrieved_node_id_set,
            unknown_references,
            required=False,
        )


def validate_lesson_json(lesson_json: Any, retrieved_node_ids: list[str]) -> None:
    if not isinstance(lesson_json, dict):
        raise ValueError("Lesson JSON must be an object.")

    key_ideas = lesson_json.get("key_ideas")
    if not isinstance(key_ideas, list):
        raise ValueError("key_ideas must be a list.")

    retrieved_node_id_set = set(retrieved_node_ids)
    unknown_references: list[str] = []

    for position, key_idea in enumerate(key_ideas, start=1):
        if not isinstance(key_idea, dict):
            raise ValueError(f"key_ideas[{position}] must be an object.")

        if "idea" not in key_idea:
            raise ValueError(f"key_ideas[{position}].idea is required.")

        if "source_chunk_ids" not in key_idea:
            raise ValueError(f"key_ideas[{position}].source_chunk_ids is required.")

        validate_source_id_list(
            key_idea.get("source_chunk_ids"),
            f"key_ideas[{position}].source_chunk_ids",
            retrieved_node_id_set,
            unknown_references,
            required=True,
        )

    validate_optional_source_lists(
        lesson_json=lesson_json,
        key="worked_examples",
        id_field="source_chunk_ids",
        retrieved_node_id_set=retrieved_node_id_set,
        unknown_references=unknown_references,
    )
    validate_optional_source_lists(
        lesson_json=lesson_json,
        key="common_misconceptions",
        id_field="source_chunk_ids",
        retrieved_node_id_set=retrieved_node_id_set,
        unknown_references=unknown_references,
    )

    if unknown_references:
        unique_unknown_references = sorted(set(unknown_references))
        raise ValueError(
            "Unknown source chunk IDs referenced: "
            f"{', '.join(unique_unknown_references)}. "
            "Generated source references may only use retrieved chunk IDs."
        )


def attach_grounding_metadata(
    lesson_json: dict,
    source_info: dict,
    source_chunks: list[dict],
) -> dict:
    lesson_json["source"] = source_info
    lesson_json["source_chunks"] = source_chunks
    return lesson_json


def print_summary(
    query: str,
    active_filters: dict[str, Any],
    index_id: str,
    storage_dir: str,
    source_chunks: list[dict],
    lesson_json: dict,
    output_path: Path,
    section_scope: dict | None,
) -> None:
    print("Section PDF lesson JSON generation completed.")
    print(f"Query: {query}")
    print_section_scope(section_scope)
    print_active_filters(active_filters)
    print(f"Index ID: {index_id}")
    print(f"Storage directory: {storage_dir}")
    print(f"Retrieved chunk count: {len(source_chunks)}")
    print(
        "Retrieved chunk IDs: "
        + ", ".join(source_chunk["node_id"] for source_chunk in source_chunks)
    )
    print(f"Generated lesson title: {lesson_json.get('title')}")
    print(f"Output path: {output_path}")


def args_from_values(
    *,
    chapter: str | None,
    chapter_number: int | None,
    section: str | None,
    topic: str | None,
    content_type: str | None,
    front_matter: bool | None,
    include_descendants: bool,
    structure_resolution: str,
    top_k: int,
    ordering: str,
) -> argparse.Namespace:
    return argparse.Namespace(
        chapter=chapter,
        chapter_number=chapter_number,
        section=section,
        topic=topic,
        content_type=content_type,
        front_matter=front_matter,
        include_descendants=include_descendants,
        structure_resolution=structure_resolution,
        top_k=top_k,
        ordering=ordering,
    )


def configure_models() -> None:
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
        max_tokens=2600,
        timeout=120,
    )


def generate_section_pdf_lesson(
    *,
    query: str,
    storage_dir: str = DEFAULT_STORAGE_DIR,
    index_id: str = DEFAULT_INDEX_ID,
    structure_resolution: str = DEFAULT_STRUCTURE_RESOLUTION,
    chapter: str | None = None,
    chapter_number: int | None = None,
    section: str | None = None,
    topic: str | None = None,
    content_type: str | None = None,
    front_matter: bool | None = None,
    include_descendants: bool = False,
    top_k: int = DEFAULT_TOP_K,
    ordering: str = "semantic",
) -> dict:
    require_env()
    lesson_query = query.strip() or DEFAULT_QUERY
    storage_path = Path(storage_dir)
    validate_storage_dir(storage_path)
    args = args_from_values(
        chapter=chapter,
        chapter_number=chapter_number,
        section=section,
        topic=topic,
        content_type=content_type,
        front_matter=front_matter,
        include_descendants=include_descendants,
        structure_resolution=structure_resolution,
        top_k=top_k,
        ordering=ordering,
    )
    section_scope = resolve_scope_from_args(args)
    metadata_filters, active_filters = build_metadata_filters(
        args,
        include_section=not bool(include_descendants and section),
    )
    configure_models()
    index = load_section_index(storage_dir=storage_path, index_id=index_id)

    if args.include_descendants and section_scope is not None:
        results = retrieve_with_section_scope(
            index=index,
            query=lesson_query,
            args=args,
            scope=section_scope,
            base_filters=active_filters,
        )
    else:
        retriever = create_retriever(
            index=index,
            metadata_filters=metadata_filters,
            top_k=args.top_k,
        )
        results = retriever.retrieve(lesson_query)

    try:
        results = order_retrieved_nodes(
            results,
            ordering=ordering,
            structure_resolution_path=structure_resolution,
        )
    except RetrievalOrderingError as error:
        raise SectionPdfLessonGenerationError(
            str(error),
            code="invalid_request",
        ) from error

    if not results:
        message = "No chunks matched the query and filters. Try relaxing filters."
        if "section" in active_filters:
            message += (
                " Section filters require an exact title. "
                "Check section names in extracted/sample.section_chunks.txt."
            )
        raise SectionPdfLessonGenerationError(message, code="no_matching_chunks")

    source_chunks = build_source_chunks(results)
    section_coverage = build_section_coverage(
        expanded_section_titles=(
            section_scope.get("section_titles") if section_scope is not None else []
        )
        or [],
        retrieved_nodes=results,
    )
    retrieved_node_ids = [source_chunk["node_id"] for source_chunk in source_chunks]
    source_info = build_source_info(
        index_id=index_id,
        storage_dir=storage_dir,
        query=lesson_query,
        active_filters=active_filters,
        retrieved_chunk_count=len(source_chunks),
        section_scope=section_scope,
        ordering=ordering,
        section_coverage=section_coverage,
    )
    prompt = build_prompt(
        query=lesson_query,
        context=build_context(results),
        source_chunk_ids=retrieved_node_ids,
        section_scope=section_scope,
    )

    try:
        response = Settings.llm.complete(prompt)
    except Exception as error:
        raise SectionPdfLessonGenerationError(
            f"NVIDIA API call failed: {error}",
            code="nvidia_api_failed",
        ) from error

    lesson_json = parse_json_response(str(response).strip())
    try:
        validate_lesson_json(lesson_json, retrieved_node_ids)
    except ValueError as error:
        raise SectionPdfLessonGenerationError(
            f"Source reference validation error: {error}",
            code="invalid_source_references",
        ) from error

    return attach_grounding_metadata(
        lesson_json=lesson_json,
        source_info=source_info,
        source_chunks=source_chunks,
    )


def section_scope_from_source(source_info: dict) -> dict | None:
    if "requested_section" not in source_info:
        return None

    return {
        "requested_section": source_info.get("requested_section"),
        "chapter": source_info.get("resolved_chapter"),
        "chapter_number": source_info.get("resolved_chapter_number"),
        "include_descendants": source_info.get("include_descendants"),
        "section_titles": source_info.get("expanded_section_titles") or [],
    }


def main() -> None:
    args = parse_args()
    query = lesson_query_from_args(args)
    output_path = Path(args.output)

    try:
        lesson_json = generate_section_pdf_lesson(
            query=query,
            storage_dir=args.storage_dir,
            index_id=args.index_id,
            structure_resolution=args.structure_resolution,
            chapter=args.chapter,
            chapter_number=args.chapter_number,
            section=args.section,
            topic=args.topic,
            content_type=args.content_type,
            front_matter=args.front_matter,
            include_descendants=args.include_descendants,
            top_k=args.top_k,
            ordering=args.ordering,
        )
    except SectionPdfLessonGenerationError as error:
        if error.raw_model_response is not None:
            print("Raw model response:")
            print("=" * 80)
            print(error.raw_model_response)
            print("=" * 80)

        print(error)
        sys.exit(1)

    formatted_json = json.dumps(lesson_json, indent=2, ensure_ascii=False)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(f"{formatted_json}\n", encoding="utf-8")

    source_info = lesson_json["source"]

    print_summary(
        query=query,
        active_filters=source_info.get("filters", {}),
        index_id=source_info["index_id"],
        storage_dir=source_info["storage_dir"],
        source_chunks=lesson_json["source_chunks"],
        lesson_json=lesson_json,
        output_path=output_path,
        section_scope=section_scope_from_source(source_info),
    )


if __name__ == "__main__":
    main()
