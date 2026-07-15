"""Tests for the lesson-enrichment (teaching layer) storage.

Enrichment is synthesized teaching stored beside the grounded base, one row per
lesson, keyed by the source_label ("slug:chNN"). Re-loading replaces the row;
the document round-trips; an unknown schema or malformed label is rejected.
"""

import json

import pytest
from sqlalchemy.orm import Session

import book_learning_materials_store as store


def make_enrichment(*, slug="pte", n=1, task="answer_short_question", title="Lesson 1"):
    return {
        "schema_version": "pte_lesson_enrichment.v1",
        "task_type": task,
        "lesson_title": title,
        "source_label": f"{slug}:ch{n:02d}",
        "core_method": {"name": "Cue → Type → Key → Answer"},
        "techniques": [{"name": "Question-Word Prediction"}],
    }


@pytest.fixture
def session():
    engine = store.create_db("sqlite:///:memory:")
    with Session(engine) as s:
        yield s


def test_stable_enrichment_id():
    assert store.stable_enrichment_id("pte", 1) == "pte:ch01:enrichment"
    assert store.stable_enrichment_id("pte", 17) == "pte:ch17:enrichment"


def test_metadata_parses_source_label():
    meta = store.extract_enrichment_metadata(make_enrichment(n=7, task="write_essay"))
    assert meta["book_slug"] == "pte"
    assert meta["chapter_number"] == 7
    assert meta["task_type"] == "write_essay"


def test_unknown_schema_version_is_rejected():
    doc = make_enrichment()
    doc["schema_version"] = "something_else.v9"
    with pytest.raises(store.StoreError):
        store.extract_enrichment_metadata(doc)


@pytest.mark.parametrize("bad", ["", "pte", "pte-ch01", "ch01", "pte:07"])
def test_malformed_source_label_is_rejected(bad):
    doc = make_enrichment()
    doc["source_label"] = bad
    with pytest.raises(store.StoreError):
        store.extract_enrichment_metadata(doc)


def test_upsert_and_round_trip(session):
    doc = make_enrichment(n=1)
    store.upsert_enrichment(session, doc)
    session.commit()

    rec = store.get_enrichment(session, "pte", 1)
    assert rec.id == "pte:ch01:enrichment"
    assert rec.task_type == "answer_short_question"
    assert json.loads(rec.document) == doc  # exact round-trip


def test_reload_replaces_row_not_duplicates(session):
    store.upsert_enrichment(session, make_enrichment(n=1, title="v1"))
    store.upsert_enrichment(session, make_enrichment(n=2, title="other"))
    session.commit()

    store.upsert_enrichment(session, make_enrichment(n=1, title="v2-regenerated"))
    session.commit()

    assert store.chapters_with_enrichment(session, "pte") == [1, 2]
    assert store.get_enrichment(session, "pte", 1).lesson_title == "v2-regenerated"
    assert store.get_enrichment(session, "pte", 2).lesson_title == "other"


def test_get_missing_enrichment_returns_none(session):
    assert store.get_enrichment(session, "pte", 99) is None


def test_real_lesson1_enrichment_loads(session):
    from pathlib import Path

    f = Path("output/pte.chapter01.enrichment.json")
    if not f.exists():
        pytest.skip("lesson 1 enrichment not present")
    rec = store.load_enrichment_file(session, f)
    session.commit()

    assert rec.book_slug == "pte" and rec.chapter_number == 1
    doc = json.loads(rec.document)
    assert doc["schema_version"] == "pte_lesson_enrichment.v1"
    assert len(doc["techniques"]) == 6 and len(doc["worked_examples"]) == 8
