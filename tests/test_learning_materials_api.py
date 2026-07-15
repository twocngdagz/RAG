"""Tests for the read-only learning-materials API.

The API serves already-generated chapters from the store, deriving nothing at
request time: an index (no bodies), a full contract-valid chapter document, and
individual sections for lazy loading.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import book_learning_materials_store as store
from learning_materials_api import create_app


def make_document(*, slug="pte", number=1, title="Lesson 1"):
    return {
        "schema_version": "book_learning_materials.v2",
        "book": {"slug": slug, "title": slug, "source_pdf": "input/pdfs/pte.pdf"},
        "generation": {"backend": "codex-cli", "model": "gpt-5.5",
                       "generated_at": "2026-07-15T00:00:00+00:00"},
        "learning_materials": {"chapters": [{
            "chapter_number": number,
            "chapter_title": title,
            "key_terms": [{"term": "Answer short question",
                           "meaning": {"text": "A brief spoken response.", "claim_kind": "definition",
                                       "origin": "source_grounded", "source_chunk_ids": ["c1"],
                                       "grounded_in_source_chunk_ids": [],
                                       "evidence_spans": [{"node_id": "c1", "quote": "brief spoken response"}],
                                       "reason": None}}],
            "learning_objectives": [],
        }]},
        "source_chunks": [],
        "audit": {"status": "PASS"},
    }


def make_enrichment(*, slug="pte", n=1):
    return {
        "schema_version": "pte_lesson_enrichment.v1",
        "task_type": "answer_short_question",
        "lesson_title": f"Lesson {n}",
        "source_label": f"{slug}:ch{n:02d}",
        "core_method": {"name": "Cue → Type → Key → Answer"},
        "techniques": [{"name": "Question-Word Prediction"}],
    }


@pytest.fixture
def client(tmp_path):
    engine = store.create_db(f"sqlite:///{tmp_path}/api.db")
    with Session(engine) as s:
        store.upsert_chapter(s, make_document(number=1, title="Lesson 1"), contract_status="PASS")
        store.upsert_chapter(s, make_document(number=2, title="Lesson 2"), contract_status="PASS")
        store.upsert_enrichment(s, make_enrichment(n=1))  # only chapter 1 is enriched
        s.commit()
    return TestClient(create_app(engine))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_books_lists_slug_and_count(client):
    r = client.get("/books")
    assert r.status_code == 200
    assert r.json() == [{"slug": "pte", "chapter_count": 2}]


def test_chapter_index_is_light_and_ordered(client):
    r = client.get("/books/pte/chapters")
    assert r.status_code == 200
    body = r.json()
    assert [c["chapter_number"] for c in body] == [1, 2]
    assert body[0]["id"] == "pte:ch01"
    assert body[0]["model"] == "gpt-5.5"
    # index carries no document body
    assert "document" not in body[0] and "learning_materials" not in body[0]


def test_index_404_for_unknown_book(client):
    assert client.get("/books/nope/chapters").status_code == 404


def test_full_chapter_returns_the_document(client):
    r = client.get("/books/pte/chapters/1")
    assert r.status_code == 200
    doc = r.json()
    chapter = doc["learning_materials"]["chapters"][0]
    assert chapter["chapter_title"] == "Lesson 1"
    # the grounding metadata is present for the frontend to render
    meaning = chapter["key_terms"][0]["meaning"]
    assert meaning["origin"] == "source_grounded"
    assert meaning["evidence_spans"][0]["quote"] == "brief spoken response"


def test_full_chapter_404_for_missing_number(client):
    assert client.get("/books/pte/chapters/99").status_code == 404


def test_section_endpoint_returns_one_section(client):
    r = client.get("/books/pte/chapters/1/sections/key_terms")
    assert r.status_code == 200
    body = r.json()
    assert body["section"] == "key_terms"
    assert body["content"][0]["term"] == "Answer short question"


def test_section_endpoint_rejects_unknown_section(client):
    r = client.get("/books/pte/chapters/1/sections/not_a_section")
    assert r.status_code == 404


def test_section_endpoint_404_for_missing_chapter(client):
    assert client.get("/books/pte/chapters/99/sections/key_terms").status_code == 404


# --------------------------------------------------------------------------- #
# Enrichment (teaching layer)
# --------------------------------------------------------------------------- #

def test_index_flags_which_chapters_are_enriched(client):
    body = client.get("/books/pte/chapters").json()
    by_num = {c["chapter_number"]: c for c in body}
    assert by_num[1]["has_enrichment"] is True
    assert by_num[2]["has_enrichment"] is False


def test_enrichment_endpoint_returns_the_teaching_document(client):
    r = client.get("/books/pte/chapters/1/enrichment")
    assert r.status_code == 200
    doc = r.json()
    assert doc["schema_version"] == "pte_lesson_enrichment.v1"
    assert doc["core_method"]["name"] == "Cue → Type → Key → Answer"


def test_enrichment_404_when_absent(client):
    assert client.get("/books/pte/chapters/2/enrichment").status_code == 404
    assert client.get("/books/pte/chapters/99/enrichment").status_code == 404
