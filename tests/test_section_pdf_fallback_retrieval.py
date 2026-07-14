import json
from pathlib import Path

import pytest

import ask_section_pdf_lesson as qa
import retrieve_section_pdf_context as retrieval


FULL_TEXT = "Complete clean chunk text. " * 30


@pytest.fixture(autouse=True)
def isolate_project_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def lesson_chunk(
    node_id: str,
    *,
    source_pdf: str | None = "input/pdfs/sample.pdf",
    chapter_number=6,
) -> dict:
    chunk = {
        "node_id": node_id,
        "chapter_number": chapter_number,
        "section": "Memory",
        "page_start": 300,
        "page_end": 300,
    }
    if source_pdf is not None:
        chunk["source_pdf"] = source_pdf
    return chunk


def clean_chunk(
    node_id: str,
    *,
    source_pdf: str = "input/pdfs/sample.pdf",
    chapter_number=6,
    text: str = FULL_TEXT,
) -> dict:
    return {
        "id": node_id,
        "source_pdf": source_pdf,
        "chapter_number": chapter_number,
        "section": "Memory",
        "topic": "Memory",
        "page_start": 300,
        "page_end": 300,
        "text": text,
        "metadata": {},
    }


def candidate(
    node_id: str | None,
    *,
    source_pdf: str = "input/pdfs/sample.pdf",
    chapter_number=6,
    score: float = 0.7,
    section: str = "Memory",
    page_start: int = 300,
) -> dict:
    return {
        "node_id": node_id,
        "score": score,
        "source_pdf": source_pdf,
        "chapter_number": chapter_number,
        "section": section,
        "page_start": page_start,
        "page_end": page_start,
        "text": "retrieved preview that must not be returned",
    }


def make_lesson(
    *,
    source_chunks: list[dict] | None = None,
    source: dict | None = None,
) -> dict:
    if source_chunks is None:
        source_chunks = [
            lesson_chunk("sample_chunk_324"),
            lesson_chunk("sample_chunk_325"),
        ]
    if source is None:
        source = {"resolved_chapter_number": 6, "filters": {"chapter_number": 6}}
    return {
        "title": "Memory Lesson",
        "source": source,
        "source_chunks": source_chunks,
    }


def write_clean_chunks(
    chunks: list[dict] | None = None,
    *,
    path: Path | None = None,
) -> Path:
    if chunks is None:
        chunks = [
            clean_chunk("sample_chunk_324"),
            clean_chunk("sample_chunk_325"),
            clean_chunk("sample_chunk_326"),
            clean_chunk("sample_chunk_327"),
            clean_chunk("sample_chunk_328"),
            clean_chunk("sample_chunk_329"),
            clean_chunk("sample_chunk_330"),
            clean_chunk("sample_chunk_331"),
        ]
    output = path or Path("extracted/sample.section_clean_chunks.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(chunks, indent=2) + "\n", encoding="utf-8")
    return output


def patch_retrieval(monkeypatch, candidates: list[dict], calls: list[dict] | None = None):
    def fake_retrieve(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        return candidates

    monkeypatch.setattr(
        retrieval,
        "retrieve_section_context_candidates",
        fake_retrieve,
    )


def run_result(monkeypatch, *, lesson: dict | None = None, candidates: list[dict] | None = None):
    write_clean_chunks()
    patch_retrieval(
        monkeypatch,
        candidates
        if candidates is not None
        else [candidate("sample_chunk_326"), candidate("sample_chunk_327")],
    )
    return retrieval.retrieve_lesson_fallback_context(
        lesson or make_lesson(),
        "What tools can an AI agent use?",
    )


def test_clean_artifacts_are_derived_from_source_pdf(monkeypatch):
    result = run_result(monkeypatch)
    assert result["source_pdf"] == "input/pdfs/sample.pdf"
    assert result["document_slug"] == "sample"
    assert result["storage_dir"] == "storage/section_clean_pdf_sample"
    assert result["index_id"] == "section_clean_pdf_sample"
    assert result["clean_chunks_file"] == "extracted/sample.section_clean_chunks.json"


def test_explicit_clean_chunks_file_changes_only_text_lookup(monkeypatch, tmp_path: Path):
    lesson = make_lesson(
        source_chunks=[
            lesson_chunk("book_chunk_1", source_pdf="input/pdfs/My Book.pdf"),
        ],
        source={"resolved_chapter_number": 6},
    )
    custom_path = tmp_path / "custom.clean.json"
    write_clean_chunks(
        [
            clean_chunk("book_chunk_1", source_pdf="input/pdfs/My Book.pdf"),
            clean_chunk("book_chunk_2", source_pdf="input/pdfs/My Book.pdf"),
        ],
        path=custom_path,
    )
    calls: list[dict] = []
    patch_retrieval(
        monkeypatch,
        [candidate("book_chunk_2", source_pdf="input/pdfs/My Book.pdf")],
        calls,
    )

    result = retrieval.retrieve_lesson_fallback_context(
        lesson,
        "What is memory?",
        clean_chunks_file=custom_path,
    )

    assert result["clean_chunks_file"] == str(custom_path)
    assert result["storage_dir"] == "storage/section_clean_pdf_my_book"
    assert result["index_id"] == "section_clean_pdf_my_book"
    assert calls[0]["storage_dir"] == "storage/section_clean_pdf_my_book"


def test_multiple_source_pdfs_are_rejected(monkeypatch):
    patch_retrieval(monkeypatch, [])
    lesson = make_lesson(
        source_chunks=[
            lesson_chunk("sample_chunk_324", source_pdf="input/pdfs/sample.pdf"),
            lesson_chunk("sample_chunk_325", source_pdf="input/pdfs/other.pdf"),
        ]
    )
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "What is memory?")


def test_missing_source_pdf_is_rejected(monkeypatch):
    patch_retrieval(monkeypatch, [])
    lesson = make_lesson(source_chunks=[lesson_chunk("sample_chunk_324", source_pdf=None)])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "What is memory?")


def test_empty_source_chunks_are_rejected(monkeypatch):
    patch_retrieval(monkeypatch, [])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(
            make_lesson(source_chunks=[]),
            "What is memory?",
        )


def test_original_question_is_passed_unchanged(monkeypatch):
    write_clean_chunks()
    calls: list[dict] = []
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")], calls)
    question = "What tools can an AI agent use?"
    retrieval.retrieve_lesson_fallback_context(make_lesson(), question)
    assert calls[0]["query"] == question


def test_retrieval_arguments_use_required_defaults(monkeypatch):
    write_clean_chunks()
    calls: list[dict] = []
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")], calls)
    retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")
    assert calls[0]["top_k"] == 10
    assert calls[0]["storage_dir"] == "storage/section_clean_pdf_sample"
    assert calls[0]["index_id"] == "section_clean_pdf_sample"
    assert calls[0]["chapter_number"] == 6


def test_chapter_resolves_from_resolved_chapter_number(monkeypatch):
    result = run_result(
        monkeypatch,
        lesson=make_lesson(
            source={"resolved_chapter_number": "6"},
            source_chunks=[
                lesson_chunk("sample_chunk_324", chapter_number=None),
                lesson_chunk("sample_chunk_325", chapter_number=None),
            ],
        ),
    )
    assert result["chapter_number"] == 6


def test_chapter_resolves_from_source_filters_chapter_number(monkeypatch):
    result = run_result(
        monkeypatch,
        lesson=make_lesson(
            source={"filters": {"chapter_number": "6"}},
            source_chunks=[
                lesson_chunk("sample_chunk_324", chapter_number=None),
                lesson_chunk("sample_chunk_325", chapter_number=None),
            ],
        ),
    )
    assert result["chapter_number"] == 6


def test_chapter_resolves_from_consistent_lesson_source_chunks(monkeypatch):
    result = run_result(
        monkeypatch,
        lesson=make_lesson(source={}),
    )
    assert result["chapter_number"] == 6


def test_chapter_resolves_from_matching_clean_artifact(monkeypatch):
    lesson = make_lesson(
        source={},
        source_chunks=[
            lesson_chunk("sample_chunk_324", chapter_number=None),
            lesson_chunk("sample_chunk_325", chapter_number=None),
        ],
    )
    result = run_result(monkeypatch, lesson=lesson)
    assert result["chapter_number"] == 6


def test_missing_chapter_metadata_is_rejected(monkeypatch):
    lesson = make_lesson(
        source={},
        source_chunks=[
            lesson_chunk("sample_chunk_324", chapter_number=None),
            lesson_chunk("sample_chunk_325", chapter_number=None),
        ],
    )
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_324", chapter_number=None),
            clean_chunk("sample_chunk_325", chapter_number=None),
        ]
    )
    patch_retrieval(monkeypatch, [])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "Question?")


def test_conflicting_chapter_metadata_is_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(monkeypatch, [])
    lesson = make_lesson(source={"resolved_chapter_number": 6, "filters": {"chapter_number": 5}})
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "Question?")


def test_multi_chapter_lesson_source_chunks_are_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(monkeypatch, [])
    lesson = make_lesson(
        source={},
        source_chunks=[
            lesson_chunk("sample_chunk_324", chapter_number=6),
            lesson_chunk("sample_chunk_325", chapter_number=7),
        ],
    )
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "Question?")


def test_missing_lesson_node_ids_are_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(monkeypatch, [])
    lesson = make_lesson(source_chunks=[{"source_pdf": "input/pdfs/sample.pdf"}])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "Question?")


def test_duplicate_lesson_node_ids_are_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(monkeypatch, [])
    lesson = make_lesson(
        source_chunks=[
            lesson_chunk("sample_chunk_324"),
            lesson_chunk("sample_chunk_324"),
        ]
    )
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(lesson, "Question?")


def test_existing_lesson_chunk_ids_are_excluded(monkeypatch):
    result = run_result(
        monkeypatch,
        candidates=[
            candidate("sample_chunk_324", score=0.9),
            candidate("sample_chunk_326", score=0.8),
        ],
    )
    assert [chunk["node_id"] for chunk in result["chunks"]] == ["sample_chunk_326"]


def test_duplicate_candidate_ids_are_removed_preserving_ranking(monkeypatch):
    result = run_result(
        monkeypatch,
        candidates=[
            candidate("sample_chunk_326", score=0.9),
            candidate("sample_chunk_326", score=0.8),
            candidate("sample_chunk_327", score=0.7),
        ],
    )
    assert [chunk["node_id"] for chunk in result["chunks"]] == [
        "sample_chunk_326",
        "sample_chunk_327",
    ]


def test_cross_chapter_candidate_is_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326", chapter_number=5)])
    with pytest.raises(retrieval.LessonFallbackRetrievalError) as error:
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")
    assert "expected chapter 6" in str(error.value)


def test_cross_document_candidate_is_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(
        monkeypatch,
        [candidate("sample_chunk_326", source_pdf="input/pdfs/other.pdf")],
    )
    with pytest.raises(retrieval.LessonFallbackRetrievalError) as error:
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")
    assert "input/pdfs/other.pdf" in str(error.value)


def test_candidate_with_missing_node_id_is_rejected(monkeypatch):
    write_clean_chunks()
    patch_retrieval(monkeypatch, [candidate(None)])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")


def test_no_more_than_five_new_chunks_are_returned(monkeypatch):
    result = run_result(
        monkeypatch,
        candidates=[candidate(f"sample_chunk_{number}") for number in range(326, 333)],
    )
    assert result["selected_count"] == 5
    assert len(result["chunks"]) == 5


def test_retrieval_ranking_is_preserved_after_exclusions(monkeypatch):
    result = run_result(
        monkeypatch,
        candidates=[
            candidate("sample_chunk_324", score=1.0),
            candidate("sample_chunk_328", score=0.9),
            candidate("sample_chunk_326", score=0.8),
            candidate("sample_chunk_327", score=0.7),
        ],
    )
    assert [chunk["node_id"] for chunk in result["chunks"]] == [
        "sample_chunk_328",
        "sample_chunk_326",
        "sample_chunk_327",
    ]


def test_zero_valid_new_candidates_returns_empty_result(monkeypatch):
    result = run_result(
        monkeypatch,
        candidates=[
            candidate("sample_chunk_324", score=0.9),
            candidate("sample_chunk_325", score=0.8),
        ],
    )
    assert result["candidate_count"] == 2
    assert result["selected_count"] == 0
    assert result["chunks"] == []


def test_selected_ids_resolve_to_complete_clean_text(monkeypatch):
    result = run_result(monkeypatch, candidates=[candidate("sample_chunk_326")])
    assert result["chunks"][0]["text"] == FULL_TEXT


def test_retrieved_preview_text_is_not_returned_as_evidence(monkeypatch):
    result = run_result(monkeypatch, candidates=[candidate("sample_chunk_326")])
    assert result["chunks"][0]["text"] != "retrieved preview that must not be returned"


def test_missing_selected_id_in_clean_artifact_is_rejected(monkeypatch):
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_324"),
            clean_chunk("sample_chunk_325"),
        ]
    )
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")


def test_duplicate_selected_id_in_clean_artifact_is_rejected(monkeypatch):
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_324"),
            clean_chunk("sample_chunk_325"),
            clean_chunk("sample_chunk_326"),
            clean_chunk("sample_chunk_326"),
        ]
    )
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")


def test_empty_complete_clean_text_is_rejected(monkeypatch):
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_324"),
            clean_chunk("sample_chunk_325"),
            clean_chunk("sample_chunk_326", text="   "),
        ]
    )
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")


def test_clean_artifact_source_pdf_mismatch_is_rejected(monkeypatch):
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_324"),
            clean_chunk("sample_chunk_325"),
            clean_chunk("sample_chunk_326", source_pdf="input/pdfs/other.pdf"),
        ]
    )
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")


def test_clean_artifact_chapter_mismatch_is_rejected(monkeypatch):
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_324"),
            clean_chunk("sample_chunk_325"),
            clean_chunk("sample_chunk_326", chapter_number=5),
        ]
    )
    patch_retrieval(monkeypatch, [candidate("sample_chunk_326")])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "Question?")


def test_resolved_output_order_matches_retrieval_ranking(monkeypatch):
    result = run_result(
        monkeypatch,
        candidates=[
            candidate("sample_chunk_328"),
            candidate("sample_chunk_326"),
            candidate("sample_chunk_327"),
        ],
    )
    assert [chunk["node_id"] for chunk in result["chunks"]] == [
        "sample_chunk_328",
        "sample_chunk_326",
        "sample_chunk_327",
    ]


def test_candidate_retrieval_not_called_when_lesson_metadata_validation_fails(monkeypatch):
    called = False

    def fake_retrieve(**_kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(retrieval, "retrieve_section_context_candidates", fake_retrieve)

    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(
            {"source_chunks": []},
            "Question?",
        )

    assert called is False


def test_existing_retrieval_cli_functions_remain_importable():
    assert callable(retrieval.parse_args)
    assert callable(retrieval.main)
    assert callable(retrieval.retrieve_lesson_fallback_context)


def test_existing_step_32_q_and_a_functions_remain_importable():
    assert callable(qa.ask_lesson_question)
    assert callable(qa.resolve_full_lesson_source_chunks)


def test_existing_step_32_full_text_resolution_remains_unaffected(tmp_path: Path):
    lesson = {
        "title": "Memory Lesson",
        "source_chunks": [
            {
                "node_id": "sample_chunk_324",
                "source_pdf": "input/pdfs/sample.pdf",
                "text_preview": "truncated...",
            }
        ],
    }
    write_clean_chunks([clean_chunk("sample_chunk_324", text=FULL_TEXT)])
    resolved = qa.resolve_full_lesson_source_chunks(lesson)
    assert resolved[0]["text"] == FULL_TEXT.strip()


def test_invalid_question_is_rejected_before_retrieval(monkeypatch):
    called = False

    def fake_retrieve(**_kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(retrieval, "retrieve_section_context_candidates", fake_retrieve)
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context(make_lesson(), "   ")
    assert called is False


def test_invalid_lesson_type_is_rejected(monkeypatch):
    patch_retrieval(monkeypatch, [])
    with pytest.raises(retrieval.LessonFallbackRetrievalError):
        retrieval.retrieve_lesson_fallback_context([], "Question?")  # type: ignore[arg-type]
