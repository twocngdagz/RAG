import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ask_section_pdf_lesson as qa
from api import app


FULL_TEXT_325 = (
    "FULL CLEAN TEXT 325. Short-term memory is the model context that keeps "
    "information available for the current task. Long-term memory stores "
    "information in external sources so it can be retrieved later."
)
FULL_TEXT_326 = (
    "FULL CLEAN TEXT 326. Memory systems help AI agents retain information "
    "between sessions and retrieve relevant information when needed."
)
TRUNCATED_PREVIEW_325 = "TRUNCATED PREVIEW 325..."
TRUNCATED_PREVIEW_326 = "TRUNCATED PREVIEW 326..."


@pytest.fixture(autouse=True)
def isolate_project_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def source_chunk(
    node_id: str,
    *,
    source_pdf: str | None = "input/pdfs/sample.pdf",
    text_preview: str = "TRUNCATED PREVIEW...",
) -> dict:
    chunk = {
        "node_id": node_id,
        "text_preview": text_preview,
        "chapter": "CHAPTER 6",
        "chapter_number": 6,
        "section": "Memory",
        "topic": "Memory",
        "page_start": 300,
        "page_end": 301,
    }
    if source_pdf is not None:
        chunk["source_pdf"] = source_pdf
    return chunk


def clean_chunk(node_id: str, text: str, *, source_pdf: str = "input/pdfs/sample.pdf") -> dict:
    return {
        "id": node_id,
        "source_pdf": source_pdf,
        "source_type": "pdf",
        "book_id": "sample",
        "book_title": "sample",
        "chapter": "CHAPTER 6",
        "chapter_number": 6,
        "section": "Memory",
        "topic": "Memory",
        "content_type": "unknown",
        "page_start": 300,
        "page_end": 301,
        "is_front_matter": False,
        "text": text,
        "metadata": {},
        "boundary_cleanup": {"applied": True},
    }


def write_clean_chunks(
    chunks: list[dict] | None = None,
    *,
    slug: str = "sample",
    path: Path | None = None,
) -> Path:
    if chunks is None:
        chunks = [
            clean_chunk("sample_chunk_325", FULL_TEXT_325),
            clean_chunk("sample_chunk_326", FULL_TEXT_326),
        ]

    output_path = path or Path("extracted") / f"{slug}.section_clean_chunks.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(chunks, indent=2) + "\n", encoding="utf-8")
    return output_path


def make_lesson(
    tmp_path: Path,
    *,
    source_chunks: list[dict] | None = None,
    title: str = "Memory Lesson",
    write_clean: bool = True,
    clean_slug: str = "sample",
) -> Path:
    if source_chunks is None:
        source_chunks = [
            source_chunk(
                "sample_chunk_325",
                text_preview=TRUNCATED_PREVIEW_325,
            ),
            source_chunk(
                "sample_chunk_326",
                text_preview=TRUNCATED_PREVIEW_326,
            ),
        ]

    lesson = {
        "title": title,
        "introduction": "This lesson explains memory in AI agents.",
        "key_ideas": [
            {
                "idea": "AI models use short-term and long-term memory.",
                "source_chunk_ids": ["sample_chunk_325"],
            }
        ],
        "explanation": "Short-term memory is limited. Long-term memory persists.",
        "summary": "Memory helps AI agents retain information.",
        "source_chunks": source_chunks,
    }
    path = tmp_path / "lesson.generated.json"
    path.write_text(json.dumps(lesson, indent=2) + "\n", encoding="utf-8")

    if write_clean:
        write_clean_chunks(slug=clean_slug)

    return path


def grounded_response(
    *,
    source_chunk_ids: list[str] | None = None,
    confidence: str = "high",
    answer: str | None = None,
    follow_up_questions: list[str] | None = None,
    extra_fields: dict | None = None,
) -> dict:
    payload = {
        "answer": answer
        or (
            "Short-term memory keeps information in the current context window, "
            "while long-term memory stores information externally for later retrieval."
        ),
        "source_chunk_ids": source_chunk_ids
        if source_chunk_ids is not None
        else ["sample_chunk_325"],
        "confidence": confidence,
        "follow_up_questions": follow_up_questions
        or [
            "Why is short-term memory limited?",
            "How can external storage provide long-term memory?",
            "How does retrieval help an AI system remember information?",
        ],
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


def fake_complete(payload: dict, prompts: list[str] | None = None):
    def _complete(prompt: str) -> str:
        if prompts is not None:
            prompts.append(prompt)
        return json.dumps(payload)

    return _complete


def test_valid_grounded_answer(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    response = qa.ask_lesson_question(
        lesson_path,
        "What is the difference between short-term memory and long-term memory?",
        complete_fn=fake_complete(grounded_response()),
    )

    assert response["confidence"] == "high"
    assert response["source_chunk_ids"] == ["sample_chunk_325"]
    assert "short-term memory" in response["answer"].lower()
    assert 2 <= len(response["follow_up_questions"]) <= 3


def test_automatic_clean_artifact_derivation_from_source_pdf(tmp_path: Path):
    lesson_path = make_lesson(
        tmp_path,
        source_chunks=[
            source_chunk(
                "sample_chunk_325",
                source_pdf="input/pdfs/My Book.pdf",
                text_preview=TRUNCATED_PREVIEW_325,
            )
        ],
        write_clean=False,
    )
    write_clean_chunks(
        [clean_chunk("sample_chunk_325", FULL_TEXT_325, source_pdf="input/pdfs/My Book.pdf")],
        slug="my_book",
    )

    lesson = qa.load_lesson(lesson_path)
    path = qa.resolve_clean_chunks_file(lesson)
    resolved = qa.resolve_full_lesson_source_chunks(lesson)

    assert path == Path("extracted/my_book.section_clean_chunks.json")
    assert resolved[0]["text"] == FULL_TEXT_325


def test_explicit_clean_chunks_file_override(tmp_path: Path):
    lesson_path = make_lesson(
        tmp_path,
        source_chunks=[
            source_chunk(
                "sample_chunk_325",
                source_pdf=None,
                text_preview=TRUNCATED_PREVIEW_325,
            )
        ],
        write_clean=False,
    )
    custom_path = write_clean_chunks(
        [clean_chunk("sample_chunk_325", FULL_TEXT_325)],
        path=tmp_path / "custom.clean.json",
    )

    response = qa.ask_lesson_question(
        lesson_path,
        "What is memory?",
        clean_chunks_file=custom_path,
        complete_fn=fake_complete(grounded_response()),
    )

    assert response["source_chunk_ids"] == ["sample_chunk_325"]


def test_full_text_is_used_instead_of_truncated_preview(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    prompts: list[str] = []

    qa.ask_lesson_question(
        lesson_path,
        "What is short-term memory?",
        complete_fn=fake_complete(grounded_response(), prompts),
    )

    assert FULL_TEXT_325 in prompts[0]
    assert TRUNCATED_PREVIEW_325 not in prompts[0]


def test_source_chunk_order_is_preserved(tmp_path: Path):
    lesson_path = make_lesson(
        tmp_path,
        source_chunks=[
            source_chunk("sample_chunk_326", text_preview=TRUNCATED_PREVIEW_326),
            source_chunk("sample_chunk_325", text_preview=TRUNCATED_PREVIEW_325),
        ],
    )
    lesson = qa.load_lesson(lesson_path)
    resolved = qa.resolve_full_lesson_source_chunks(lesson)

    assert [chunk["node_id"] for chunk in resolved] == [
        "sample_chunk_326",
        "sample_chunk_325",
    ]


def test_missing_clean_chunks_file_is_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, write_clean=False)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "missing_clean_chunks_file"


def test_invalid_clean_chunks_json_is_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, write_clean=False)
    path = Path("extracted/sample.section_clean_chunks.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "invalid_clean_chunks_json"


def test_missing_node_id_in_clean_artifact_is_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, write_clean=False)
    write_clean_chunks([clean_chunk("sample_chunk_999", "Some other text.")])

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )

    assert error.value.code == "unresolved_source_chunks"
    assert "sample_chunk_325" in str(error.value)
    assert "sample_chunk_326" in str(error.value)


def test_duplicate_node_ids_in_lesson_source_chunks_are_rejected(tmp_path: Path):
    lesson_path = make_lesson(
        tmp_path,
        source_chunks=[
            source_chunk("sample_chunk_325"),
            source_chunk("sample_chunk_325"),
        ],
    )

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "invalid_source_chunks"


def test_duplicate_matching_node_ids_in_clean_artifact_are_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, write_clean=False)
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_325", "First full text."),
            clean_chunk("sample_chunk_325", "Duplicate full text."),
            clean_chunk("sample_chunk_326", FULL_TEXT_326),
        ]
    )

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "invalid_clean_chunks_json"
    assert "sample_chunk_325" in str(error.value)


def test_empty_full_chunk_text_is_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, write_clean=False)
    write_clean_chunks(
        [
            clean_chunk("sample_chunk_325", "   "),
            clean_chunk("sample_chunk_326", FULL_TEXT_326),
        ]
    )

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "unresolved_source_chunks"
    assert "sample_chunk_325" in str(error.value)


def test_inconsistent_source_pdfs_are_rejected_during_automatic_derivation(tmp_path: Path):
    lesson_path = make_lesson(
        tmp_path,
        source_chunks=[
            source_chunk("sample_chunk_325", source_pdf="input/pdfs/sample.pdf"),
            source_chunk("sample_chunk_326", source_pdf="input/pdfs/other.pdf"),
        ],
        write_clean=False,
    )

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "source_document_error"


def test_model_is_not_called_when_chunk_resolution_fails(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, write_clean=False)
    called = False

    def complete(_prompt: str) -> str:
        nonlocal called
        called = True
        return json.dumps(grounded_response())

    with pytest.raises(qa.LessonQuestionError):
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=complete,
        )

    assert called is False


def test_existing_output_file_is_rejected_without_overwrite(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    output_path = tmp_path / "answer.json"
    output_path.write_text("original", encoding="utf-8")

    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question_to_file(
            lesson_path,
            "What is memory?",
            output_path,
            complete_fn=fake_complete(grounded_response()),
        )

    assert error.value.code == "output_exists"
    assert output_path.read_text(encoding="utf-8") == "original"


def test_model_is_not_called_when_output_already_exists(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    output_path = tmp_path / "answer.json"
    output_path.write_text("original", encoding="utf-8")
    called = False

    def complete(_prompt: str) -> str:
        nonlocal called
        called = True
        return json.dumps(grounded_response())

    with pytest.raises(qa.LessonQuestionError):
        qa.ask_lesson_question_to_file(
            lesson_path,
            "What is memory?",
            output_path,
            complete_fn=complete,
        )

    assert called is False


def test_overwrite_allows_replacement(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    output_path = tmp_path / "answer.json"
    output_path.write_text("original", encoding="utf-8")

    qa.ask_lesson_question_to_file(
        lesson_path,
        "What is memory?",
        output_path,
        overwrite=True,
        complete_fn=fake_complete(grounded_response()),
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["source_chunk_ids"] == ["sample_chunk_325"]
    assert output_path.read_text(encoding="utf-8") != "original"


def test_answer_cites_valid_source_chunk_id(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    response = qa.ask_lesson_question(
        lesson_path,
        "What is short-term memory?",
        complete_fn=fake_complete(grounded_response()),
    )
    assert response["source_chunk_ids"] == ["sample_chunk_325"]


def test_multiple_valid_source_chunk_ids_accepted(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    response = qa.ask_lesson_question(
        lesson_path,
        "How does memory help agents?",
        complete_fn=fake_complete(
            grounded_response(source_chunk_ids=["sample_chunk_325", "sample_chunk_326"])
        ),
    )
    assert response["source_chunk_ids"] == ["sample_chunk_325", "sample_chunk_326"]


def test_invented_source_chunk_id_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(
                grounded_response(source_chunk_ids=["invented_chunk"])
            ),
        )
    assert error.value.code == "invalid_grounding"


def test_duplicate_source_chunk_ids_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(
                grounded_response(
                    source_chunk_ids=["sample_chunk_325", "sample_chunk_325"]
                )
            ),
        )
    assert error.value.code == "invalid_grounding"


def test_unsupported_confidence_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response(confidence="certain")),
        )
    assert error.value.code == "invalid_grounding"


def test_missing_required_response_field_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    payload = grounded_response()
    del payload["confidence"]
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(payload),
        )
    assert error.value.code == "invalid_grounding"


def test_unexpected_top_level_field_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(
                grounded_response(extra_fields={"notes": "extra"})
            ),
        )
    assert error.value.code == "invalid_grounding"


def test_supported_answer_without_citations_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(
                grounded_response(
                    source_chunk_ids=[],
                    answer="Short-term memory is the context window.",
                    confidence="high",
                )
            ),
        )
    assert error.value.code == "invalid_grounding"


def test_insufficient_evidence_answer_accepted_using_full_text(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    prompts: list[str] = []
    response = qa.ask_lesson_question(
        lesson_path,
        "What year was the Eiffel Tower completed?",
        complete_fn=fake_complete(
            grounded_response(
                answer=(
                    "The lesson materials do not provide enough information "
                    "to answer that question."
                ),
                source_chunk_ids=[],
                confidence="low",
                follow_up_questions=[
                    "What does the lesson say about short-term memory?",
                    "How does the lesson describe long-term memory?",
                ],
            ),
            prompts,
        ),
    )
    assert FULL_TEXT_325 in prompts[0]
    assert response["source_chunk_ids"] == []
    assert response["confidence"] == "low"


def test_missing_lesson_file_error(tmp_path: Path):
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            tmp_path / "missing.json",
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "missing_lesson_file"


def test_invalid_lesson_json_error(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "invalid_lesson_json"


def test_empty_source_chunks_error(tmp_path: Path):
    lesson_path = make_lesson(tmp_path, source_chunks=[])
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "What is memory?",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "empty_source_chunks"


def test_empty_question_rejected(tmp_path: Path):
    lesson_path = make_lesson(tmp_path)
    with pytest.raises(qa.LessonQuestionError) as error:
        qa.ask_lesson_question(
            lesson_path,
            "   ",
            complete_fn=fake_complete(grounded_response()),
        )
    assert error.value.code == "empty_question"


def test_api_endpoint_returns_expected_schema_with_auto_resolution(
    tmp_path: Path, monkeypatch
):
    lesson_path = make_lesson(tmp_path)
    monkeypatch.setattr(
        qa,
        "default_complete",
        fake_complete(grounded_response()),
    )

    client = TestClient(app)
    response = client.post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_path),
            "question": "What is memory?",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "answer",
        "source_chunk_ids",
        "confidence",
        "follow_up_questions",
        "grounding",
    }
    assert set(payload["grounding"]) == {
        "fallback_attempted",
        "lesson_source_chunk_ids",
        "retrieved_source_chunk_ids",
    }


def test_api_endpoint_accepts_explicit_clean_chunks_override(
    tmp_path: Path, monkeypatch
):
    lesson_path = make_lesson(
        tmp_path,
        source_chunks=[
            source_chunk(
                "sample_chunk_325",
                source_pdf=None,
                text_preview=TRUNCATED_PREVIEW_325,
            )
        ],
        write_clean=False,
    )
    clean_path = write_clean_chunks(
        [clean_chunk("sample_chunk_325", FULL_TEXT_325)],
        path=tmp_path / "custom.clean.json",
    )
    monkeypatch.setattr(
        qa,
        "default_complete",
        fake_complete(grounded_response(source_chunk_ids=["sample_chunk_325"])),
    )

    client = TestClient(app)
    response = client.post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_path),
            "clean_chunks_file": str(clean_path),
            "question": "What is memory?",
        },
    )

    assert response.status_code == 200
    assert response.json()["source_chunk_ids"] == ["sample_chunk_325"]


def test_existing_api_endpoints_remain_importable():
    client = TestClient(app)
    routes = {route.path for route in app.routes}
    assert "/structure" in routes
    assert "/lessons/generate" in routes
    assert "/pdf-lessons/generate" in routes
    assert "/section-pdf-lessons/generate" in routes
    assert "/section-pdf-lessons/ask" in routes
    response = client.get("/structure")
    assert response.status_code in {200, 500}
