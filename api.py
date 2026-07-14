import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from llama_index.core import Settings, StorageContext, load_index_from_storage
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.openai_like import OpenAILike
from pydantic import BaseModel, ConfigDict, model_validator

import generate_lesson_json as lesson_generator
import generate_section_pdf_lesson_json as section_pdf_lesson_generator
import generate_structured_pdf_lesson_json as pdf_lesson_generator
import ask_section_pdf_lesson as section_pdf_lesson_qa
from retrieve_section_pdf_context import (
    DEFAULT_INDEX_ID as DEFAULT_FALLBACK_INDEX_ID,
    DEFAULT_STORAGE_DIR as DEFAULT_FALLBACK_STORAGE_DIR,
    FALLBACK_CANDIDATE_TOP_K,
    FALLBACK_MAX_NEW_CHUNKS,
    LessonFallbackRetrievalError,
)


app = FastAPI(title="Tiny Learning RAG API")
CHUNKS_FILE = Path("chunks.json")


class GenerateLessonRequest(BaseModel):
    query: str | None = None
    topic: str | None = None
    section: str | None = None
    content_type: str | None = None


class GeneratePdfLessonRequest(BaseModel):
    query: str | None = None
    storage_dir: str | None = None
    index_id: str | None = None
    chapter: str | None = None
    chapter_number: int | None = None
    content_type: str | None = None
    front_matter: bool | None = None


class SectionPdfLessonRequest(BaseModel):
    query: str = section_pdf_lesson_generator.DEFAULT_QUERY
    storage_dir: str = section_pdf_lesson_generator.DEFAULT_STORAGE_DIR
    index_id: str = section_pdf_lesson_generator.DEFAULT_INDEX_ID
    structure_resolution: str = (
        section_pdf_lesson_generator.DEFAULT_STRUCTURE_RESOLUTION
    )
    chapter: str | None = None
    chapter_number: int | None = None
    section: str | None = None
    topic: str | None = None
    content_type: str | None = None
    front_matter: bool | None = None
    include_descendants: bool = False
    top_k: int = section_pdf_lesson_generator.DEFAULT_TOP_K
    ordering: Literal["semantic", "document"] = "semantic"

    @model_validator(mode="after")
    def validate_request(self):
        if self.top_k < 1 or self.top_k > 50:
            raise ValueError("top_k must be between 1 and 50.")

        if self.include_descendants and not (self.section or "").strip():
            raise ValueError("include_descendants=true requires section.")

        return self


class SectionPdfLessonAskRequest(BaseModel):
    lesson_file: str
    question: str
    clean_chunks_file: str | None = None
    allow_index_fallback: bool = False
    fallback_storage_dir: str = DEFAULT_FALLBACK_STORAGE_DIR
    fallback_index_id: str = DEFAULT_FALLBACK_INDEX_ID
    fallback_top_k: int = FALLBACK_CANDIDATE_TOP_K
    max_fallback_chunks: int = FALLBACK_MAX_NEW_CHUNKS

    @model_validator(mode="after")
    def validate_request(self):
        if not self.lesson_file.strip():
            raise ValueError("lesson_file must not be blank.")

        if not self.question.strip():
            raise ValueError("question must not be blank.")

        if self.clean_chunks_file is not None and not self.clean_chunks_file.strip():
            raise ValueError("clean_chunks_file must not be blank when provided.")

        if self.fallback_top_k < 1 or self.fallback_top_k > 50:
            raise ValueError("fallback_top_k must be between 1 and 50.")

        if self.max_fallback_chunks < 1 or self.max_fallback_chunks > 10:
            raise ValueError("max_fallback_chunks must be between 1 and 10.")

        if self.allow_index_fallback:
            if not self.fallback_storage_dir.strip():
                raise ValueError(
                    "fallback_storage_dir must not be blank when fallback is enabled."
                )

            if not self.fallback_index_id.strip():
                raise ValueError(
                    "fallback_index_id must not be blank when fallback is enabled."
                )

        return self


class SectionPdfLessonAskGrounding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fallback_attempted: bool
    lesson_source_chunk_ids: list[str]
    retrieved_source_chunk_ids: list[str]


class SectionPdfLessonAskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    source_chunk_ids: list[str]
    confidence: Literal["high", "medium", "low"]
    follow_up_questions: list[str]
    grounding: SectionPdfLessonAskGrounding


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None

    value = value.strip()
    return value or None


def configure_models() -> None:
    if not lesson_generator.NVIDIA_API_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing NVIDIA_API_KEY. Create a real .env file from "
                ".env.example and add your NVIDIA API key."
            ),
        )

    Settings.embed_model = OllamaEmbedding(
        model_name=lesson_generator.OLLAMA_EMBED_MODEL,
        base_url=lesson_generator.OLLAMA_BASE_URL,
    )

    Settings.llm = OpenAILike(
        model=lesson_generator.NVIDIA_MODEL,
        api_base=lesson_generator.NVIDIA_BASE_URL,
        api_key=lesson_generator.NVIDIA_API_KEY,
        is_chat_model=True,
        context_window=262144,
        max_tokens=1600,
        timeout=120,
    )


def configure_pdf_models() -> None:
    if not pdf_lesson_generator.NVIDIA_API_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing NVIDIA_API_KEY. Create a real .env file from "
                ".env.example and add your NVIDIA API key."
            ),
        )

    Settings.embed_model = OllamaEmbedding(
        model_name=pdf_lesson_generator.OLLAMA_EMBED_MODEL,
        base_url=pdf_lesson_generator.OLLAMA_BASE_URL,
    )

    Settings.llm = OpenAILike(
        model=pdf_lesson_generator.NVIDIA_MODEL,
        api_base=pdf_lesson_generator.NVIDIA_BASE_URL,
        api_key=pdf_lesson_generator.NVIDIA_API_KEY,
        is_chat_model=True,
        context_window=262144,
        max_tokens=2200,
        timeout=120,
    )


def parse_json_response(raw_response: str):
    try:
        return json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Model response was not valid JSON.",
                "error": str(error),
                "raw_model_response": raw_response,
            },
        ) from error


def load_chunks() -> list[dict]:
    try:
        with CHUNKS_FILE.open("r", encoding="utf-8") as file:
            chunks = json.load(file)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Missing required file: {CHUNKS_FILE}",
        ) from error
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=500,
            detail=f"Invalid JSON in {CHUNKS_FILE}: {error}",
        ) from error

    if not isinstance(chunks, list):
        raise HTTPException(
            status_code=500,
            detail=f"{CHUNKS_FILE} must contain a top-level JSON array.",
        )

    return chunks


def build_structure(chunks: list[dict]) -> dict:
    books = {}

    for chunk in chunks:
        try:
            book_key = (
                chunk["domain"],
                chunk["grade"],
                chunk["book_id"],
                chunk["book_title"],
            )
            chapter_key = chunk["chapter"]
            section_key = chunk["section"]
            topic_key = chunk["topic"]
            content_type = chunk["content_type"]
        except KeyError as error:
            raise HTTPException(
                status_code=500,
                detail=f"Chunk is missing required field: {error.args[0]}",
            ) from error

        book = books.setdefault(
            book_key,
            {
                "domain": chunk["domain"],
                "grade": chunk["grade"],
                "book_id": chunk["book_id"],
                "book_title": chunk["book_title"],
                "chapters": {},
            },
        )
        chapter = book["chapters"].setdefault(chapter_key, {"sections": {}})
        section = chapter["sections"].setdefault(section_key, {"topics": {}})
        topic = section["topics"].setdefault(
            topic_key,
            {
                "content_types": set(),
                "chunk_count": 0,
            },
        )
        topic["content_types"].add(content_type)
        topic["chunk_count"] += 1

    return {
        "books": [
            {
                "domain": book["domain"],
                "grade": book["grade"],
                "book_id": book["book_id"],
                "book_title": book["book_title"],
                "chapters": [
                    {
                        "chapter": chapter_name,
                        "sections": [
                            {
                                "section": section_name,
                                "topics": [
                                    {
                                        "topic": topic_name,
                                        "content_types": sorted(
                                            topic["content_types"]
                                        ),
                                        "chunk_count": topic["chunk_count"],
                                    }
                                    for topic_name, topic in sorted(
                                        section["topics"].items()
                                    )
                                ],
                            }
                            for section_name, section in sorted(
                                chapter["sections"].items()
                            )
                        ],
                    }
                    for chapter_name, chapter in sorted(book["chapters"].items())
                ],
            }
            for _, book in sorted(books.items())
        ]
    }


@app.get("/structure")
def get_structure():
    return build_structure(load_chunks())


@app.post("/lessons/generate")
def generate_lesson(request: GenerateLessonRequest):
    configure_models()

    lesson_query = clean_optional(request.query) or lesson_generator.DEFAULT_QUERY
    args = SimpleNamespace(
        topic=clean_optional(request.topic),
        section=clean_optional(request.section),
        content_type=clean_optional(request.content_type),
    )
    metadata_filters, active_filters = lesson_generator.build_metadata_filters(args)
    retrieval_query = lesson_generator.build_retrieval_query(lesson_query)

    try:
        index = lesson_generator.load_index()
        retriever = lesson_generator.create_retriever(index, metadata_filters)
        results = retriever.retrieve(retrieval_query)
        context = lesson_generator.format_context(results)
        source_chunks = lesson_generator.build_source_chunks(results)
        prompt = lesson_generator.build_prompt(lesson_query, context, source_chunks)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval failed: {error}",
        ) from error

    print("API lesson generation request:")
    print(f"Lesson query: {lesson_query}")
    lesson_generator.print_active_filters(active_filters)
    print("Retrieved context summary:")
    print("=" * 80)
    print(context)
    print("=" * 80)

    try:
        response = Settings.llm.complete(prompt)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"NVIDIA API call failed: {error}",
        ) from error

    return parse_json_response(str(response).strip())


@app.post("/pdf-lessons/generate")
def generate_pdf_lesson(request: GeneratePdfLessonRequest):
    configure_pdf_models()

    lesson_query = clean_optional(request.query) or pdf_lesson_generator.DEFAULT_QUERY
    storage_dir = Path(
        clean_optional(request.storage_dir)
        or pdf_lesson_generator.DEFAULT_STORAGE_DIR
    )
    index_id = clean_optional(request.index_id) or pdf_lesson_generator.DEFAULT_INDEX_ID

    try:
        pdf_lesson_generator.validate_storage_dir(storage_dir)
    except SystemExit as error:
        raise HTTPException(
            status_code=500,
            detail=str(error),
        ) from error

    args = SimpleNamespace(
        chapter=clean_optional(request.chapter),
        chapter_number=request.chapter_number,
        content_type=clean_optional(request.content_type),
        front_matter=request.front_matter,
    )
    metadata_filters, active_filters = pdf_lesson_generator.build_metadata_filters(args)

    try:
        storage_context = StorageContext.from_defaults(
            persist_dir=str(storage_dir),
        )
        index = load_index_from_storage(
            storage_context,
            index_id=index_id,
        )
        retriever = pdf_lesson_generator.create_retriever(index, metadata_filters)
        results = retriever.retrieve(lesson_query)
        source_chunks = pdf_lesson_generator.build_source_chunks(results)
        source_info = pdf_lesson_generator.build_source_info(
            index_id=index_id,
            storage_dir=storage_dir,
            active_filters=active_filters,
            source_chunks=source_chunks,
        )
        context = pdf_lesson_generator.format_context(results)
        context_summary = pdf_lesson_generator.format_context_summary(results)
        prompt = pdf_lesson_generator.build_prompt(
            lesson_query=lesson_query,
            context=context,
            source_info=source_info,
            source_chunks=source_chunks,
        )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Structured PDF retrieval failed: {error}",
        ) from error

    print("API structured PDF lesson generation request:")
    print(f"Lesson query: {lesson_query}")
    print(f"Storage directory: {storage_dir}")
    print(f"Index ID: {index_id}")
    pdf_lesson_generator.print_active_filters(active_filters)
    print(f"Retrieved chunks: {len(results)}")
    print("Retrieved context summary:")
    print("=" * 80)
    print(context_summary)
    print("=" * 80)

    try:
        response = Settings.llm.complete(prompt)
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"NVIDIA API call failed: {error}",
        ) from error

    lesson_json = parse_json_response(str(response).strip())
    retrieved_node_ids = [source_chunk["node_id"] for source_chunk in source_chunks]
    try:
        pdf_lesson_generator.validate_source_references(
            lesson_json,
            retrieved_node_ids,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Model returned invalid source references.",
                "error": str(error),
            },
        ) from error

    return pdf_lesson_generator.apply_grounding_metadata(
        lesson_json=lesson_json,
        source_info=source_info,
        source_chunks=source_chunks,
    )


SECTION_PDF_ERROR_STATUS = {
    "missing_storage": 404,
    "missing_structure_resolution": 404,
    "section_not_found": 404,
    "ambiguous_section": 400,
    "no_matching_chunks": 404,
    "missing_api_key": 503,
    "invalid_model_json": 502,
    "invalid_source_references": 502,
    "nvidia_api_failed": 502,
    "invalid_request": 422,
}


@app.post("/section-pdf-lessons/generate")
def generate_section_pdf_lesson(request: SectionPdfLessonRequest):
    query = clean_optional(request.query) or section_pdf_lesson_generator.DEFAULT_QUERY
    storage_dir = (
        clean_optional(request.storage_dir)
        or section_pdf_lesson_generator.DEFAULT_STORAGE_DIR
    )
    index_id = (
        clean_optional(request.index_id)
        or section_pdf_lesson_generator.DEFAULT_INDEX_ID
    )
    structure_resolution = (
        clean_optional(request.structure_resolution)
        or section_pdf_lesson_generator.DEFAULT_STRUCTURE_RESOLUTION
    )

    try:
        lesson_json = section_pdf_lesson_generator.generate_section_pdf_lesson(
            query=query,
            storage_dir=storage_dir,
            index_id=index_id,
            structure_resolution=structure_resolution,
            chapter=clean_optional(request.chapter),
            chapter_number=request.chapter_number,
            section=clean_optional(request.section),
            topic=clean_optional(request.topic),
            content_type=clean_optional(request.content_type),
            front_matter=request.front_matter,
            include_descendants=request.include_descendants,
            top_k=request.top_k,
            ordering=request.ordering,
        )
    except section_pdf_lesson_generator.SectionPdfLessonGenerationError as error:
        if error.raw_model_response is not None:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Model response was not valid JSON.",
                    "error": str(error),
                    "raw_model_response": error.raw_model_response,
                },
            ) from error

        status_code = SECTION_PDF_ERROR_STATUS.get(error.code, 500)
        raise HTTPException(
            status_code=status_code,
            detail=str(error),
        ) from error

    source = lesson_json.get("source", {})
    print("API section PDF lesson generation request:")
    print(f"Lesson query: {source.get('query')}")
    print(f"Storage directory: {source.get('storage_dir')}")
    print(f"Index ID: {source.get('index_id')}")
    print(f"Requested section: {source.get('requested_section')}")
    print(f"Include descendants: {source.get('include_descendants')}")
    print(f"Expanded section count: {len(source.get('expanded_section_titles', []))}")
    print(f"Retrieved chunks: {source.get('retrieved_chunk_count')}")
    print(
        "Retrieved chunk IDs: "
        + ", ".join(
            source_chunk.get("node_id", "")
            for source_chunk in lesson_json.get("source_chunks", [])
        )
    )

    return lesson_json


SECTION_PDF_ASK_ERROR_STATUS = {
    "missing_lesson_file": 404,
    "missing_clean_chunks_file": 404,
    "invalid_lesson_json": 400,
    "invalid_clean_chunks_json": 400,
    "empty_source_chunks": 400,
    "invalid_source_chunks": 400,
    "source_document_error": 400,
    "unresolved_source_chunks": 400,
    "empty_question": 400,
    "missing_api_key": 503,
    "invalid_model_json": 502,
    "invalid_grounding": 502,
    "nvidia_api_failed": 502,
}


def build_section_pdf_ask_api_response(
    response: dict[str, Any],
    details: dict[str, Any],
) -> dict[str, Any]:
    grounding = response.get("grounding")
    if not isinstance(grounding, dict):
        grounding = {
            "fallback_attempted": bool(details.get("fallback_attempted")),
            "lesson_source_chunk_ids": response.get("source_chunk_ids", []),
            "retrieved_source_chunk_ids": [],
        }

    public_grounding = {
        "fallback_attempted": bool(grounding.get("fallback_attempted")),
        "lesson_source_chunk_ids": grounding.get("lesson_source_chunk_ids", []),
        "retrieved_source_chunk_ids": grounding.get("retrieved_source_chunk_ids", []),
    }

    lesson_ids = public_grounding["lesson_source_chunk_ids"]
    retrieved_ids = public_grounding["retrieved_source_chunk_ids"]
    source_ids = response.get("source_chunk_ids", [])

    if len(lesson_ids) != len(set(lesson_ids)):
        raise section_pdf_lesson_qa.LessonQuestionError(
            "Public grounding lesson_source_chunk_ids must not contain duplicates.",
            code="invalid_grounding",
        )

    if len(retrieved_ids) != len(set(retrieved_ids)):
        raise section_pdf_lesson_qa.LessonQuestionError(
            "Public grounding retrieved_source_chunk_ids must not contain duplicates.",
            code="invalid_grounding",
        )

    if set(lesson_ids) & set(retrieved_ids):
        raise section_pdf_lesson_qa.LessonQuestionError(
            "Public grounding source ID sets overlap.",
            code="invalid_grounding",
        )

    if lesson_ids + retrieved_ids != source_ids:
        raise section_pdf_lesson_qa.LessonQuestionError(
            "Public grounding provenance does not match source_chunk_ids.",
            code="invalid_grounding",
        )

    return {
        "answer": response["answer"],
        "source_chunk_ids": source_ids,
        "confidence": response["confidence"],
        "follow_up_questions": response["follow_up_questions"],
        "grounding": public_grounding,
    }


@app.post("/section-pdf-lessons/ask", response_model=SectionPdfLessonAskResponse)
def ask_section_pdf_lesson(request: SectionPdfLessonAskRequest):
    fallback_error: dict[str, str] = {}

    def api_fallback_retrieval(lesson: dict, question: str, *, clean_chunks_file=None):
        try:
            return section_pdf_lesson_qa.default_fallback_retrieval(
                lesson,
                question,
                clean_chunks_file=clean_chunks_file,
                fallback_storage_dir=request.fallback_storage_dir.strip(),
                fallback_index_id=request.fallback_index_id.strip(),
                fallback_top_k=request.fallback_top_k,
                max_fallback_chunks=request.max_fallback_chunks,
            )
        except LessonFallbackRetrievalError as error:
            fallback_error["message"] = str(error)
            return {
                "storage_dir": request.fallback_storage_dir.strip(),
                "index_id": request.fallback_index_id.strip(),
                "candidate_count": 0,
                "selected_count": 0,
                "chunks": [],
                "error": str(error),
            }

    try:
        response, details = (
            section_pdf_lesson_qa.ask_lesson_question_with_optional_fallback_details(
            lesson_file=request.lesson_file.strip(),
            question=request.question.strip(),
            clean_chunks_file=clean_optional(request.clean_chunks_file),
            allow_index_fallback=request.allow_index_fallback,
            fallback_storage_dir=request.fallback_storage_dir.strip(),
            fallback_index_id=request.fallback_index_id.strip(),
            fallback_top_k=request.fallback_top_k,
            max_fallback_chunks=request.max_fallback_chunks,
            fallback_retrieval_fn=(
                api_fallback_retrieval if request.allow_index_fallback else None
            ),
            )
        )
        api_response = build_section_pdf_ask_api_response(response, details)
    except section_pdf_lesson_qa.LessonQuestionError as error:
        status_code = SECTION_PDF_ASK_ERROR_STATUS.get(error.code, 500)
        raise HTTPException(
            status_code=status_code,
            detail=str(error),
        ) from error

    print("API section PDF lesson ask request:")
    print(f"Lesson file: {request.lesson_file}")
    if request.clean_chunks_file:
        print(f"Clean chunks file: {request.clean_chunks_file}")
    print(f"Question: {request.question}")
    print(f"Allow index fallback: {request.allow_index_fallback}")
    print(f"Index fallback attempted: {details.get('fallback_attempted')}")
    if fallback_error:
        print(f"Fallback retrieval error: {fallback_error['message']}")
    print(f"Confidence: {api_response.get('confidence')}")
    print(f"Cited source chunks: {len(api_response.get('source_chunk_ids', []))}")
    print(
        "Cited fallback chunks: "
        f"{len(api_response['grounding'].get('retrieved_source_chunk_ids', []))}"
    )

    return api_response
