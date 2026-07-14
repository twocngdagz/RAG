import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import ask_section_pdf_lesson as qa
from api import app


LESSON_TEXT = "Complete lesson chunk text about short-term memory. " * 20
FALLBACK_TEXT = "Complete fallback chunk text about retrieval algorithms. " * 20
INSUFFICIENT_ANSWER = (
    "The lesson materials do not provide enough information to answer that question."
)
EXPECTED_PUBLIC_KEYS = {
    "answer",
    "source_chunk_ids",
    "confidence",
    "follow_up_questions",
    "grounding",
}
EXPECTED_GROUNDING_KEYS = {
    "fallback_attempted",
    "lesson_source_chunk_ids",
    "retrieved_source_chunk_ids",
}


@pytest.fixture(autouse=True)
def isolate_project_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def source_chunk(node_id: str = "lesson_1") -> dict:
    return {
        "node_id": node_id,
        "source_pdf": "input/pdfs/sample.pdf",
        "chapter": "CHAPTER 6",
        "chapter_number": 6,
        "section": "Memory",
        "topic": "Memory",
        "page_start": 300,
        "page_end": 300,
        "text_preview": "truncated preview",
    }


def clean_chunk(node_id: str, text: str = LESSON_TEXT) -> dict:
    return {
        "id": node_id,
        "source_pdf": "input/pdfs/sample.pdf",
        "source_type": "pdf",
        "book_id": "sample",
        "book_title": "sample",
        "chapter": "CHAPTER 6",
        "chapter_number": 6,
        "section": "Memory",
        "topic": "Memory",
        "content_type": "unknown",
        "page_start": 300,
        "page_end": 300,
        "is_front_matter": False,
        "text": text,
        "metadata": {},
    }


def make_lesson_file(tmp_path: Path) -> Path:
    lesson = {
        "title": "Memory Lesson",
        "introduction": "This lesson explains memory in AI systems.",
        "key_ideas": [
            {
                "idea": "Memory helps AI systems retain context.",
                "source_chunk_ids": ["lesson_1"],
            }
        ],
        "explanation": "Short-term memory is current context.",
        "summary": "Memory supports recall.",
        "source_chunks": [source_chunk("lesson_1"), source_chunk("lesson_2")],
    }
    lesson_path = tmp_path / "lesson.generated.json"
    lesson_path.write_text(json.dumps(lesson, indent=2) + "\n", encoding="utf-8")

    clean_path = Path("extracted/sample.section_clean_chunks.json")
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.write_text(
        json.dumps(
            [
                clean_chunk("lesson_1"),
                clean_chunk("lesson_2", "Second lesson clean text. " * 20),
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return lesson_path


def response(
    *,
    answer: str = "Short-term memory keeps information in current context.",
    source_chunk_ids: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    return {
        "answer": answer,
        "source_chunk_ids": ["lesson_1"] if source_chunk_ids is None else source_chunk_ids,
        "confidence": confidence,
        "follow_up_questions": [
            "How does memory help an AI system?",
            "What is long-term memory?",
        ],
    }


def insufficient_response() -> dict:
    return response(
        answer=INSUFFICIENT_ANSWER,
        source_chunk_ids=[],
        confidence="low",
    )


def combined_insufficient_response() -> dict:
    return response(
        answer=(
            "The lesson materials and additional chapter context do not provide "
            "enough information to answer that question."
        ),
        source_chunk_ids=[],
        confidence="low",
    )


class FakeCompleter:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.payloads:
            raise AssertionError("Unexpected completion call")
        return json.dumps(self.payloads.pop(0))


class FakeFallback:
    def __init__(self, chunks: list[dict] | None = None):
        self.chunks = chunks if chunks is not None else [fallback_chunk("fallback_1")]
        self.calls: list[dict] = []

    def __call__(
        self,
        lesson: dict,
        question: str,
        *,
        clean_chunks_file=None,
        fallback_storage_dir=None,
        fallback_index_id=None,
        fallback_top_k=None,
        max_fallback_chunks=None,
    ) -> dict:
        self.calls.append(
            {
                "lesson": lesson,
                "question": question,
                "clean_chunks_file": clean_chunks_file,
                "fallback_storage_dir": fallback_storage_dir,
                "fallback_index_id": fallback_index_id,
                "fallback_top_k": fallback_top_k,
                "max_fallback_chunks": max_fallback_chunks,
            }
        )
        return {
            "source_pdf": "input/pdfs/sample.pdf",
            "document_slug": "sample",
            "chapter_number": 6,
            "storage_dir": fallback_storage_dir or "./storage/section_clean_pdf_sample",
            "index_id": fallback_index_id or "section_clean_pdf_sample",
            "clean_chunks_file": "extracted/sample.section_clean_chunks.json",
            "candidate_count": 10,
            "selected_count": len(self.chunks),
            "chunks": self.chunks,
        }


def fallback_chunk(node_id: str) -> dict:
    return {
        "node_id": node_id,
        "score": 0.8,
        "source_pdf": "input/pdfs/sample.pdf",
        "chapter_number": 6,
        "section": "Retrieval",
        "topic": "Retrieval",
        "page_start": 280,
        "page_end": 280,
        "text": FALLBACK_TEXT,
    }


def assert_public_response_contract(payload: dict) -> None:
    assert set(payload) == EXPECTED_PUBLIC_KEYS
    assert set(payload["grounding"]) == EXPECTED_GROUNDING_KEYS
    assert "insufficient_evidence" not in payload
    assert "source" not in payload
    assert "allow_index_fallback" not in payload
    assert "index_fallback_attempted" not in payload
    assert "fallback_storage_dir" not in payload
    assert "fallback_index_id" not in payload
    assert "fallback_chapter_number" not in payload
    assert "fallback_candidates" not in payload
    assert "new_fallback_chunks_selected" not in payload


def assert_public_provenance(payload: dict) -> None:
    grounding = payload["grounding"]
    lesson_ids = grounding["lesson_source_chunk_ids"]
    retrieved_ids = grounding["retrieved_source_chunk_ids"]

    assert len(lesson_ids) == len(set(lesson_ids))
    assert len(retrieved_ids) == len(set(retrieved_ids))
    assert not (set(lesson_ids) & set(retrieved_ids))
    assert lesson_ids + retrieved_ids == payload["source_chunk_ids"]


def test_api_default_omits_index_fallback(tmp_path: Path, monkeypatch):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    monkeypatch.setattr(qa, "default_complete", FakeCompleter([response()]))
    monkeypatch.setattr(qa, "default_fallback_retrieval", fallback)

    api_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What is short-term memory?",
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert fallback.calls == []
    assert_public_response_contract(payload)
    assert_public_provenance(payload)
    assert payload["grounding"]["fallback_attempted"] is False
    assert payload["grounding"]["lesson_source_chunk_ids"] == ["lesson_1"]
    assert payload["grounding"]["retrieved_source_chunk_ids"] == []


def test_api_supported_question_with_fallback_enabled_does_not_retrieve(
    tmp_path: Path, monkeypatch
):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    monkeypatch.setattr(qa, "default_complete", FakeCompleter([response()]))
    monkeypatch.setattr(qa, "default_fallback_retrieval", fallback)

    api_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What is short-term memory?",
            "allow_index_fallback": True,
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert fallback.calls == []
    assert_public_response_contract(payload)
    assert_public_provenance(payload)
    assert payload["grounding"]["fallback_attempted"] is False
    assert payload["grounding"]["lesson_source_chunk_ids"] == ["lesson_1"]
    assert payload["grounding"]["retrieved_source_chunk_ids"] == []


def test_api_insufficient_evidence_with_fallback_disabled(tmp_path: Path, monkeypatch):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    monkeypatch.setattr(qa, "default_complete", FakeCompleter([insufficient_response()]))
    monkeypatch.setattr(qa, "default_fallback_retrieval", fallback)

    api_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What does the chapter say about retrieval algorithms?",
            "allow_index_fallback": False,
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert fallback.calls == []
    assert_public_response_contract(payload)
    assert_public_provenance(payload)
    assert payload["source_chunk_ids"] == []
    assert payload["confidence"] == "low"
    assert payload["grounding"]["fallback_attempted"] is False
    assert payload["grounding"]["lesson_source_chunk_ids"] == []
    assert payload["grounding"]["retrieved_source_chunk_ids"] == []


def test_api_insufficient_evidence_with_fallback_enabled_uses_retrieved_chunks(
    tmp_path: Path, monkeypatch
):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback([fallback_chunk("fallback_1")])
    monkeypatch.setattr(
        qa,
        "default_complete",
        FakeCompleter(
            [
                insufficient_response(),
                response(
                    answer="Retrieval algorithms find relevant stored information.",
                    source_chunk_ids=["lesson_1", "fallback_1"],
                ),
            ]
        ),
    )
    monkeypatch.setattr(qa, "default_fallback_retrieval", fallback)

    api_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What does the chapter say about retrieval algorithms?",
            "allow_index_fallback": True,
            "fallback_storage_dir": "./storage/custom_clean",
            "fallback_index_id": "custom_clean_index",
            "fallback_top_k": 12,
            "max_fallback_chunks": 3,
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert fallback.calls[0]["fallback_storage_dir"] == "./storage/custom_clean"
    assert fallback.calls[0]["fallback_index_id"] == "custom_clean_index"
    assert fallback.calls[0]["fallback_top_k"] == 12
    assert fallback.calls[0]["max_fallback_chunks"] == 3
    assert_public_response_contract(payload)
    assert_public_provenance(payload)
    assert payload["grounding"]["fallback_attempted"] is True
    assert payload["source_chunk_ids"] == ["lesson_1", "fallback_1"]
    assert payload["grounding"]["lesson_source_chunk_ids"] == ["lesson_1"]
    assert payload["grounding"]["retrieved_source_chunk_ids"] == ["fallback_1"]


def test_api_combined_insufficient_fallback_attempted_has_empty_provenance(
    tmp_path: Path, monkeypatch
):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback([fallback_chunk("fallback_1")])
    monkeypatch.setattr(
        qa,
        "default_complete",
        FakeCompleter([insufficient_response(), combined_insufficient_response()]),
    )
    monkeypatch.setattr(qa, "default_fallback_retrieval", fallback)

    api_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What does the chapter say about unknown material?",
            "allow_index_fallback": True,
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert_public_response_contract(payload)
    assert_public_provenance(payload)
    assert payload["source_chunk_ids"] == []
    assert payload["confidence"] == "low"
    assert payload["grounding"] == {
        "fallback_attempted": True,
        "lesson_source_chunk_ids": [],
        "retrieved_source_chunk_ids": [],
    }


def test_api_validates_fallback_limits(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)

    top_k_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What is memory?",
            "fallback_top_k": 0,
        },
    )
    assert top_k_response.status_code == 422

    max_chunks_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What is memory?",
            "max_fallback_chunks": 11,
        },
    )
    assert max_chunks_response.status_code == 422


def test_api_old_request_shape_still_works(tmp_path: Path, monkeypatch):
    lesson_file = make_lesson_file(tmp_path)
    monkeypatch.setattr(qa, "default_complete", FakeCompleter([response()]))

    api_response = TestClient(app).post(
        "/section-pdf-lessons/ask",
        json={
            "lesson_file": str(lesson_file),
            "question": "What is memory?",
        },
    )

    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["answer"]
    assert payload["source_chunk_ids"] == ["lesson_1"]
    assert payload["confidence"] == "high"
    assert len(payload["follow_up_questions"]) == 2
    assert_public_response_contract(payload)


def test_openapi_documents_allow_index_fallback_default_false():
    schema = TestClient(app).get("/openapi.json").json()
    matching = {
        name: value
        for name, value in schema["components"]["schemas"].items()
        if "allow_index_fallback" in value.get("properties", {})
    }

    assert matching

    for value in matching.values():
        assert value["properties"]["allow_index_fallback"]["default"] is False
