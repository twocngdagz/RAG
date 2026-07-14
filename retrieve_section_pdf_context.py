import argparse
import os
import re
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

from clean_section_chunk_lookup import (
    CleanChunkLookupError,
    load_and_resolve_clean_chunks_by_ids,
)
from pdf_artifact_paths import get_clean_pdf_defaults
from retrieval_ordering import (
    RetrievalOrderingError,
    build_section_coverage,
    order_retrieved_nodes,
)
from section_scope import SectionScopeError, resolve_section_scope


load_dotenv()

DEFAULT_QUERY = "Explain the main idea from this section."
DEFAULT_STORAGE_DIR = "./storage/section_clean_pdf_sample"
DEFAULT_INDEX_ID = "section_clean_pdf_sample"
DEFAULT_TOP_K = 5
DEFAULT_STRUCTURE_RESOLUTION = "extracted/sample.structure_resolution.json"
TEXT_PREVIEW_MAX_CHARS = 1000
FALLBACK_CANDIDATE_TOP_K = 10
FALLBACK_MAX_NEW_CHUNKS = 5

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


class LessonFallbackRetrievalError(ValueError):
    pass


def parse_bool(value: str) -> bool:
    normalized_value = value.strip().lower()

    if normalized_value == "true":
        return True

    if normalized_value == "false":
        return False

    raise argparse.ArgumentTypeError("--front-matter must be either true or false.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrieve context from a section-enriched PDF index."
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="Optional retrieval query. Uses the default query when omitted.",
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
        help=f"Number of matching chunks to retrieve. Defaults to {DEFAULT_TOP_K}.",
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
        help="Result presentation order. Defaults to semantic.",
    )
    return parser.parse_args()


def query_from_args(args: argparse.Namespace) -> str:
    return " ".join(args.query).strip() or DEFAULT_QUERY


def validate_storage_dir(storage_dir: Path) -> None:
    if not storage_dir.exists():
        raise SystemExit(
            f"Storage directory does not exist: {storage_dir}\n"
            "Build the section PDF index first:\n"
            'python build_section_pdf_index.py "extracted/sample.section_chunks.json"'
        )

    if not storage_dir.is_dir():
        raise SystemExit(f"Storage path is not a directory: {storage_dir}")


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


def create_retriever(
    index,
    metadata_filters: MetadataFilters | None,
    top_k: int,
):
    retriever_args = {"similarity_top_k": top_k}

    if metadata_filters is not None:
        retriever_args["filters"] = metadata_filters

    return index.as_retriever(**retriever_args)


def get_node_text(node) -> str:
    try:
        return node.get_content(metadata_mode=MetadataMode.NONE) or ""
    except Exception:
        return getattr(node, "text", "") or ""


def text_preview(text: str) -> str:
    normalized_text = re.sub(r"\s+", " ", text).strip()

    if len(normalized_text) <= TEXT_PREVIEW_MAX_CHARS:
        return normalized_text

    return f"{normalized_text[: TEXT_PREVIEW_MAX_CHARS - 3].rstrip()}..."


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


def load_index(storage_dir: Path, index_id: str):
    try:
        storage_context = StorageContext.from_defaults(
            persist_dir=str(storage_dir),
        )
        return load_index_from_storage(
            storage_context,
            index_id=index_id,
        )
    except Exception as error:
        raise SystemExit(
            f"Could not load index '{index_id}' from storage directory '{storage_dir}'.\n"
            f"Error: {error}"
        ) from error


def load_index_for_fallback(storage_dir: Path, index_id: str):
    if not storage_dir.exists():
        raise LessonFallbackRetrievalError(
            f"Clean section index storage directory does not exist: {storage_dir}"
        )

    if not storage_dir.is_dir():
        raise LessonFallbackRetrievalError(
            f"Clean section index storage path is not a directory: {storage_dir}"
        )

    try:
        storage_context = StorageContext.from_defaults(
            persist_dir=str(storage_dir),
        )
        return load_index_from_storage(
            storage_context,
            index_id=index_id,
        )
    except Exception as error:
        raise LessonFallbackRetrievalError(
            f"Could not load clean section index '{index_id}' from '{storage_dir}': {error}"
        ) from error


def normalize_source_pdf(value: str | Path) -> str:
    text = str(value).strip()
    while text.startswith("./"):
        text = text[2:]
    return Path(text).as_posix()


def coerce_chapter_number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)

    return None


def extract_lesson_source_chunks_for_fallback(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(lesson, dict):
        raise LessonFallbackRetrievalError("Lesson must be a dictionary.")

    source_chunks = lesson.get("source_chunks")
    if not isinstance(source_chunks, list) or not source_chunks:
        raise LessonFallbackRetrievalError(
            "Cannot prepare fallback retrieval because lesson source_chunks is empty."
        )

    usable_chunks: list[dict[str, Any]] = []
    node_ids: list[str] = []

    for position, source_chunk in enumerate(source_chunks, start=1):
        if not isinstance(source_chunk, dict):
            raise LessonFallbackRetrievalError(
                f"Lesson source_chunks[{position}] must be an object."
            )

        node_id = source_chunk.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise LessonFallbackRetrievalError(
                "Cannot prepare fallback retrieval because lesson source chunks "
                "contain missing node IDs."
            )

        normalized_chunk = dict(source_chunk)
        normalized_chunk["node_id"] = node_id.strip()
        usable_chunks.append(normalized_chunk)
        node_ids.append(node_id.strip())

    duplicate_node_ids = [
        node_id for node_id in node_ids if node_ids.count(node_id) > 1
    ]
    if duplicate_node_ids:
        raise LessonFallbackRetrievalError(
            "Cannot prepare fallback retrieval because lesson source chunks "
            "contain duplicate node IDs: "
            + ", ".join(sorted(set(duplicate_node_ids)))
        )

    return usable_chunks


def resolve_lesson_source_pdf(source_chunks: list[dict[str, Any]]) -> str:
    source_pdfs = []

    for source_chunk in source_chunks:
        source_pdf = source_chunk.get("source_pdf")
        if not isinstance(source_pdf, str) or not source_pdf.strip():
            raise LessonFallbackRetrievalError(
                "Cannot prepare fallback retrieval because lesson source chunks "
                "do not identify one consistent source PDF."
            )
        source_pdfs.append(normalize_source_pdf(source_pdf))

    unique_source_pdfs = []
    for source_pdf in source_pdfs:
        if source_pdf not in unique_source_pdfs:
            unique_source_pdfs.append(source_pdf)

    if len(unique_source_pdfs) != 1:
        raise LessonFallbackRetrievalError(
            "Cannot prepare fallback retrieval because lesson source chunks "
            "do not identify one consistent source PDF."
        )

    return unique_source_pdfs[0]


def consistent_chapter_from_values(
    values: list[Any],
    label: str,
) -> int | None:
    chapter_numbers = []

    for value in values:
        chapter_number = coerce_chapter_number(value)
        if chapter_number is not None:
            chapter_numbers.append(chapter_number)

    unique_values = sorted(set(chapter_numbers))
    if len(unique_values) > 1:
        raise LessonFallbackRetrievalError(
            f"Cannot prepare fallback retrieval because {label} spans multiple chapters."
        )

    return unique_values[0] if unique_values else None


def resolve_fallback_chapter_number(
    lesson: dict[str, Any],
    source_chunks: list[dict[str, Any]],
    clean_lesson_chunks: list[dict[str, Any]],
) -> int:
    source = lesson.get("source") if isinstance(lesson.get("source"), dict) else {}
    filters = source.get("filters") if isinstance(source.get("filters"), dict) else {}

    available: list[tuple[str, int]] = []

    resolved_chapter_number = coerce_chapter_number(
        source.get("resolved_chapter_number")
    )
    if resolved_chapter_number is not None:
        available.append(("lesson.source.resolved_chapter_number", resolved_chapter_number))

    filter_chapter_number = coerce_chapter_number(filters.get("chapter_number"))
    if filter_chapter_number is not None:
        available.append(("lesson.source.filters.chapter_number", filter_chapter_number))

    source_chunk_chapter = consistent_chapter_from_values(
        [chunk.get("chapter_number") for chunk in source_chunks],
        "lesson source chunks",
    )
    if source_chunk_chapter is not None:
        available.append(("lesson.source_chunks.chapter_number", source_chunk_chapter))

    clean_chunk_chapter = consistent_chapter_from_values(
        [chunk.get("chapter_number") for chunk in clean_lesson_chunks],
        "clean artifact matching lesson chunks",
    )
    if clean_chunk_chapter is not None:
        available.append(("clean_chunks.chapter_number", clean_chunk_chapter))

    if not available:
        raise LessonFallbackRetrievalError(
            "Cannot prepare fallback retrieval because the lesson chapter could "
            "not be determined consistently."
        )

    selected_chapter = available[0][1]
    conflicts = [
        f"{label}={chapter_number}"
        for label, chapter_number in available[1:]
        if chapter_number != selected_chapter
    ]
    if conflicts:
        raise LessonFallbackRetrievalError(
            "Cannot prepare fallback retrieval because the lesson chapter could "
            "not be determined consistently. Conflicts: "
            + ", ".join(conflicts)
        )

    return selected_chapter


def candidate_from_result(result) -> dict[str, Any]:
    node = result.node
    metadata = node.metadata or {}

    return {
        "node_id": getattr(node, "node_id", None),
        "score": result.score,
        "source_pdf": metadata.get("source_pdf"),
        "chapter_number": metadata.get("chapter_number"),
        "section": metadata.get("section"),
        "topic": metadata.get("topic"),
        "page_start": metadata.get("page_start"),
        "page_end": metadata.get("page_end"),
    }


def retrieve_section_context_candidates(
    *,
    query: str,
    storage_dir: str | Path,
    index_id: str,
    chapter_number: int,
    top_k: int,
) -> list[dict[str, Any]]:
    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    index = load_index_for_fallback(
        storage_dir=Path(storage_dir),
        index_id=index_id,
    )
    results = retrieve_once(
        index=index,
        query=query,
        active_filters={"chapter_number": chapter_number},
        top_k=top_k,
    )
    return [candidate_from_result(result) for result in results]


def validate_clean_chunk_source_and_chapter(
    *,
    chunk: dict[str, Any],
    node_id: str,
    expected_source_pdf: str,
    expected_chapter_number: int,
) -> None:
    source_pdf = chunk.get("source_pdf")
    if not isinstance(source_pdf, str) or normalize_source_pdf(source_pdf) != expected_source_pdf:
        raise LessonFallbackRetrievalError(
            f"Clean fallback chunk {node_id} belongs to {source_pdf}, "
            f"expected {expected_source_pdf}."
        )

    chapter_number = coerce_chapter_number(chunk.get("chapter_number"))
    if chapter_number != expected_chapter_number:
        raise LessonFallbackRetrievalError(
            f"Clean fallback chunk {node_id} belongs to chapter {chunk.get('chapter_number')}, "
            f"expected chapter {expected_chapter_number}."
        )


def validate_clean_chunk_source(
    *,
    chunk: dict[str, Any],
    node_id: str,
    expected_source_pdf: str,
) -> None:
    source_pdf = chunk.get("source_pdf")
    if not isinstance(source_pdf, str) or normalize_source_pdf(source_pdf) != expected_source_pdf:
        raise LessonFallbackRetrievalError(
            f"Clean fallback chunk {node_id} belongs to {source_pdf}, "
            f"expected {expected_source_pdf}."
        )


def select_fallback_candidate_ids(
    *,
    candidates: list[dict[str, Any]],
    expected_source_pdf: str,
    expected_chapter_number: int,
    existing_lesson_ids: set[str],
    max_new_chunks: int = FALLBACK_MAX_NEW_CHUNKS,
) -> list[dict[str, Any]]:
    selected_candidates: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    for candidate in candidates:
        node_id = candidate.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise LessonFallbackRetrievalError(
                "Retrieved fallback candidate is missing a usable node ID."
            )
        node_id = node_id.strip()

        source_pdf = candidate.get("source_pdf")
        if not isinstance(source_pdf, str) or normalize_source_pdf(source_pdf) != expected_source_pdf:
            raise LessonFallbackRetrievalError(
                f"Retrieved fallback candidate {node_id} belongs to {source_pdf}, "
                f"expected {expected_source_pdf}."
            )

        chapter_number = coerce_chapter_number(candidate.get("chapter_number"))
        if chapter_number != expected_chapter_number:
            raise LessonFallbackRetrievalError(
                f"Retrieved fallback candidate {node_id} belongs to chapter "
                f"{candidate.get('chapter_number')}, expected chapter {expected_chapter_number}."
            )

        if node_id in existing_lesson_ids:
            continue

        if node_id in selected_ids:
            continue

        selected_candidate = dict(candidate)
        selected_candidate["node_id"] = node_id
        selected_candidates.append(selected_candidate)
        selected_ids.add(node_id)

        if len(selected_candidates) >= max_new_chunks:
            break

    return selected_candidates


def retrieve_lesson_fallback_context(
    lesson: dict,
    question: str,
    *,
    clean_chunks_file: str | Path | None = None,
    storage_dir: str | Path | None = None,
    index_id: str | None = None,
    candidate_top_k: int = FALLBACK_CANDIDATE_TOP_K,
    max_new_chunks: int = FALLBACK_MAX_NEW_CHUNKS,
) -> dict:
    if not isinstance(question, str) or not question.strip():
        raise LessonFallbackRetrievalError(
            "Fallback retrieval question must be a non-empty string."
        )

    source_chunks = extract_lesson_source_chunks_for_fallback(lesson)
    source_pdf = resolve_lesson_source_pdf(source_chunks)
    artifact_defaults = get_clean_pdf_defaults(source_pdf)
    clean_path = (
        Path(clean_chunks_file)
        if clean_chunks_file is not None
        else Path(artifact_defaults["clean_chunks_path"])
    )
    lesson_node_ids = [chunk["node_id"] for chunk in source_chunks]
    existing_lesson_ids = set(lesson_node_ids)

    try:
        clean_lesson_chunks = load_and_resolve_clean_chunks_by_ids(
            clean_chunks_file=clean_path,
            node_ids=lesson_node_ids,
            require_text=False,
        )
    except CleanChunkLookupError as error:
        raise LessonFallbackRetrievalError(str(error)) from error

    for node_id, clean_chunk in zip(lesson_node_ids, clean_lesson_chunks):
        validate_clean_chunk_source(
            chunk=clean_chunk,
            node_id=node_id,
            expected_source_pdf=source_pdf,
        )

    chapter_number = resolve_fallback_chapter_number(
        lesson=lesson,
        source_chunks=source_chunks,
        clean_lesson_chunks=clean_lesson_chunks,
    )

    for node_id, clean_chunk in zip(lesson_node_ids, clean_lesson_chunks):
        clean_chapter_number = coerce_chapter_number(clean_chunk.get("chapter_number"))
        if clean_chapter_number is not None and clean_chapter_number != chapter_number:
            raise LessonFallbackRetrievalError(
                f"Clean lesson source chunk {node_id} belongs to chapter "
                f"{clean_chunk.get('chapter_number')}, expected chapter {chapter_number}."
            )

    resolved_storage_dir = (
        str(storage_dir) if storage_dir is not None else artifact_defaults["storage_dir"]
    )
    resolved_index_id = index_id or artifact_defaults["index_id"]
    candidates = retrieve_section_context_candidates(
        query=question.strip(),
        storage_dir=resolved_storage_dir,
        index_id=resolved_index_id,
        chapter_number=chapter_number,
        top_k=candidate_top_k,
    )

    selected_candidates = select_fallback_candidate_ids(
        candidates=candidates,
        expected_source_pdf=source_pdf,
        expected_chapter_number=chapter_number,
        existing_lesson_ids=existing_lesson_ids,
        max_new_chunks=max_new_chunks,
    )
    selected_ids = [candidate["node_id"] for candidate in selected_candidates]

    try:
        selected_clean_chunks = load_and_resolve_clean_chunks_by_ids(
            clean_chunks_file=clean_path,
            node_ids=selected_ids,
            require_text=True,
        )
    except CleanChunkLookupError as error:
        raise LessonFallbackRetrievalError(str(error)) from error

    output_chunks = []
    for candidate, clean_chunk in zip(selected_candidates, selected_clean_chunks):
        node_id = candidate["node_id"]
        validate_clean_chunk_source_and_chapter(
            chunk=clean_chunk,
            node_id=node_id,
            expected_source_pdf=source_pdf,
            expected_chapter_number=chapter_number,
        )
        output_chunks.append(
            {
                "node_id": node_id,
                "score": candidate.get("score"),
                "source_pdf": source_pdf,
                "chapter_number": chapter_number,
                "section": candidate.get("section") or clean_chunk.get("section"),
                "topic": candidate.get("topic") or clean_chunk.get("topic"),
                "page_start": candidate.get("page_start") or clean_chunk.get("page_start"),
                "page_end": candidate.get("page_end") or clean_chunk.get("page_end"),
                "text": clean_chunk["text"],
            }
        )

    return {
        "source_pdf": source_pdf,
        "document_slug": artifact_defaults["document_slug"],
        "chapter_number": chapter_number,
        "storage_dir": resolved_storage_dir,
        "index_id": resolved_index_id,
        "clean_chunks_file": str(clean_path),
        "candidate_count": len(candidates),
        "selected_count": len(output_chunks),
        "chunks": output_chunks,
    }


def resolve_scope_from_args(args: argparse.Namespace) -> dict | None:
    if args.include_descendants and not args.section:
        raise SystemExit("--include-descendants requires --section.")

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
        raise SystemExit(f"Section scope resolution error: {error}") from error

    if args.chapter and scope.get("chapter") != args.chapter:
        raise SystemExit(
            f"Requested chapter filter {args.chapter!r} does not match resolved "
            f"section chapter {scope.get('chapter')!r}."
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


def print_section_coverage(section_coverage: dict | None) -> None:
    if section_coverage is None:
        return

    print(f"Covered section count: {section_coverage['covered_section_count']}")
    print(f"Missing section count: {section_coverage['missing_section_count']}")
    print("")
    print("Covered sections:")

    for section_title in section_coverage["covered_section_titles"]:
        print(f"- {section_title}")

    print("")
    print("Missing sections:")

    for section_title in section_coverage["missing_section_titles"]:
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


def print_no_results(active_filters: dict[str, Any]) -> None:
    print("No matching chunks found. Try relaxing filters.")

    if "section" in active_filters:
        print(
            "Section filters require an exact title. "
            "Check section names in extracted/sample.section_chunks.txt."
        )


def print_result(position: int, result) -> None:
    node = result.node
    metadata = node.metadata or {}

    print("=" * 80)
    print(f"Result #{position}")
    print(f"Score: {result.score}")
    print(f"Node ID: {node.node_id}")
    print(f"Source PDF: {metadata.get('source_pdf')}")
    print(f"Chapter: {metadata.get('chapter')}")
    print(f"Chapter number: {metadata.get('chapter_number')}")
    print(f"Section: {metadata.get('section')}")
    print(f"Section page start: {metadata.get('section_page_start')}")
    print(f"Section source: {metadata.get('section_source')}")
    print(f"Section confidence: {metadata.get('section_confidence')}")
    print(f"Topic: {metadata.get('topic')}")
    print(f"Content type: {metadata.get('content_type')}")
    print(f"Pages: {metadata.get('page_start')}-{metadata.get('page_end')}")
    print(f"Is front matter: {metadata.get('is_front_matter')}")
    print("")
    print("Text preview:")
    print(text_preview(get_node_text(node)))
    print("")


def main() -> None:
    args = parse_args()
    query = query_from_args(args)
    storage_dir = Path(args.storage_dir)
    validate_storage_dir(storage_dir)
    section_scope = resolve_scope_from_args(args)
    metadata_filters, active_filters = build_metadata_filters(
        args,
        include_section=not bool(args.include_descendants and args.section),
    )

    Settings.embed_model = OllamaEmbedding(
        model_name=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    index = load_index(storage_dir=storage_dir, index_id=args.index_id)

    if args.include_descendants and section_scope is not None:
        results = retrieve_with_section_scope(
            index=index,
            query=query,
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
        results = retriever.retrieve(query)

    try:
        results = order_retrieved_nodes(
            results,
            ordering=args.ordering,
            structure_resolution_path=args.structure_resolution,
        )
    except RetrievalOrderingError as error:
        raise SystemExit(f"Retrieval ordering error: {error}") from error

    section_coverage = None
    if section_scope is not None and args.include_descendants:
        section_coverage = build_section_coverage(
            expanded_section_titles=section_scope.get("section_titles") or [],
            retrieved_nodes=results,
        )

    print("Section PDF retrieval completed.")
    print(f"Query: {query}")
    print(f"Storage directory: {storage_dir}")
    print(f"Index ID: {args.index_id}")
    print(f"Ordering: {args.ordering}")
    print_section_scope(section_scope)
    print_section_coverage(section_coverage)
    print_active_filters(active_filters)
    print(f"Results found: {len(results)}")
    print("")

    if not results:
        print_no_results(active_filters)
        return

    for position, result in enumerate(results, start=1):
        print_result(position, result)


if __name__ == "__main__":
    main()
