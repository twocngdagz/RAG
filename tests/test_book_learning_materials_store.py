"""Tests for the chapter-document storage layer.

Chapters are stored one row per chapter, keyed by a stable id, with the whole
contract-validated document in a JSON column and queryable metadata lifted out.
Re-loading a chapter must replace its row without touching siblings, and the
document must round-trip byte-for-identical.
"""

import json

import pytest
from sqlalchemy.orm import Session

import book_learning_materials_store as store


def make_document(*, slug="pte", number=1, title="Lesson 1", backend="codex-cli", model="gpt-5.5"):
    return {
        "schema_version": "book_learning_materials.v2",
        "book": {"slug": slug, "title": slug, "source_pdf": "input/pdfs/pte.pdf"},
        "generation": {"backend": backend, "model": model, "generated_at": "2026-07-15T00:00:00+00:00"},
        "learning_materials": {"chapters": [{"chapter_number": number, "chapter_title": title,
                                             "learning_objectives": []}]},
        "source_chunks": [],
        "audit": {"status": "PASS"},
    }


@pytest.fixture
def session():
    engine = store.create_db("sqlite:///:memory:")
    with Session(engine) as s:
        yield s


# --------------------------------------------------------------------------- #
# Stable id + metadata extraction
# --------------------------------------------------------------------------- #

def test_stable_chapter_id_zero_pads():
    assert store.stable_chapter_id("pte", 3) == "pte:ch03"
    assert store.stable_chapter_id("pte", 17) == "pte:ch17"


def test_metadata_is_lifted_from_the_document():
    meta = store.extract_metadata(make_document(number=6, title="Summarize Written Text", model="gpt-5.5"))
    assert meta["book_slug"] == "pte"
    assert meta["chapter_number"] == 6
    assert meta["chapter_title"] == "Summarize Written Text"
    assert meta["backend"] == "codex-cli"
    assert meta["model"] == "gpt-5.5"


def test_extract_metadata_rejects_multi_chapter_document():
    doc = make_document()
    doc["learning_materials"]["chapters"].append({"chapter_number": 2})
    with pytest.raises(store.StoreError):
        store.extract_metadata(doc)


def test_extract_metadata_requires_integer_chapter_number():
    doc = make_document()
    doc["learning_materials"]["chapters"][0]["chapter_number"] = "1"
    with pytest.raises(store.StoreError):
        store.extract_metadata(doc)


# --------------------------------------------------------------------------- #
# Upsert + round-trip
# --------------------------------------------------------------------------- #

def test_upsert_stores_document_and_round_trips(session):
    doc = make_document(number=1)
    store.upsert_chapter(session, doc, contract_status="PASS")
    session.commit()

    record = store.get_chapter(session, "pte", 1)
    assert record.id == "pte:ch01"
    assert record.contract_status == "PASS"
    assert json.loads(record.document) == doc  # exact round-trip


def test_reloading_a_chapter_replaces_its_row_not_siblings(session):
    store.upsert_chapter(session, make_document(number=1, title="v1"), contract_status="PASS")
    store.upsert_chapter(session, make_document(number=2, title="other"), contract_status="PASS")
    session.commit()

    # Re-generate chapter 1 with a new title; chapter 2 must be untouched.
    store.upsert_chapter(session, make_document(number=1, title="v2-regenerated"), contract_status="PASS")
    session.commit()

    assert len(store.list_chapters(session)) == 2  # no duplicate row
    assert store.get_chapter(session, "pte", 1).chapter_title == "v2-regenerated"
    assert store.get_chapter(session, "pte", 2).chapter_title == "other"


def test_list_is_ordered_and_index_item_omits_the_body(session):
    for n in (3, 1, 2):
        store.upsert_chapter(session, make_document(number=n, title=f"L{n}"), contract_status="PASS")
    session.commit()

    items = store.list_chapters(session)
    assert [r.chapter_number for r in items] == [1, 2, 3]
    index = items[0].index_item()
    assert index["id"] == "pte:ch01"
    assert "document" not in index  # list view stays light


# --------------------------------------------------------------------------- #
# Contract error classification on load
# --------------------------------------------------------------------------- #

def test_empty_clean_chunk_is_non_blocking():
    audit = {"status": "FAIL", "errors": [{"code": "EMPTY_CLEAN_CHUNK_TEXT", "json_path": "$[248]"}]}
    assert store.blocking_contract_errors(audit) == []


def test_structural_errors_are_blocking():
    audit = {"status": "FAIL", "errors": [
        {"code": "INVALID_TOP_LEVEL_SHAPE", "json_path": "$.learning_materials"},
        {"code": "EMPTY_CLEAN_CHUNK_TEXT", "json_path": "$[248]"},
    ]}
    blocking = store.blocking_contract_errors(audit)
    assert [e["code"] for e in blocking] == ["INVALID_TOP_LEVEL_SHAPE"]


# --------------------------------------------------------------------------- #
# End-to-end against the real chapters (skips if not present)
# --------------------------------------------------------------------------- #

def test_all_real_chapters_load_and_round_trip(session):
    from pathlib import Path

    files = sorted(Path("output").glob("pte.chapter*.book_learning_materials.json"))
    clean = Path("extracted/pte.section_clean_chunks.json")
    if not files or not clean.exists():
        pytest.skip("real chapters or clean index not present")

    for f in files:
        record, blocking = store.load_chapter_file(session, f, clean_chunks_file=clean)
        assert not blocking, f"{f.name} had blocking errors: {blocking}"
        assert record is not None
    session.commit()

    assert len(store.list_chapters(session, "pte")) == len(files)
    assert store.verify_round_trip(session, [str(f) for f in files])
