"""Where a chapter's class lessons are kept, and what reading one promises.

Two things now read this file. `run_class_lessons.py` writes it, one concept at a
time, and `export_lesson_package.py` carries what it holds into the package. So
the file's shape is defined here rather than inside either of them: a second
definition drifts the first time a field moves, and the drift would surface as a
package quietly missing a concept's teaching.

ONE FILE PER CHAPTER, KEYED BY CONCEPT. Keyed rather than listed, because a
chapter run twice must not produce two lessons for one concept, and because a run
that stopped at the fifth concept resumes by asking which keys are already there.
Both promises are the same rule read from different ends.

READING IS CHECKED, NOT HOPEFUL. A file under a schema this module does not know
is refused rather than parsed optimistically, and so is one holding another
chapter's lessons — the second would otherwise teach one chapter's material under
another chapter's name, which is the failure nobody would see until a learner
met it.

This module knows where class lessons live. It does not know what one IS: that is
`class_lesson_contract.py`, and it is the contract a reply is held to, whoever
generated it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import class_lesson_contract as contract
from book_learning_materials_contract import atomic_write_json

# Class lessons are generated content, so they live in output/ beside the
# enrichments they are written from, one file per chapter.
STORE_FILE = "output/{slug}.chapter{n:02d}.class_lessons.json"

STORE_SCHEMA_VERSION = "class_lesson_set.v1"


class ClassLessonsRefused(Exception):
    """A chapter's class lessons cannot be read, and why."""


def store_path(slug: str, chapter: int) -> Path:
    return Path(STORE_FILE.format(slug=slug, n=chapter))


def empty_store(slug: str, chapter: int) -> dict[str, Any]:
    return {
        "schema_version": STORE_SCHEMA_VERSION,
        "book_slug": slug,
        "lesson_stable_key": f"{slug}:ch{chapter:02d}",
        # Keyed by concept, so a chapter run twice cannot produce two lessons for
        # one concept however many times it is repeated.
        "concepts": {},
    }


def load(path: Path, slug: str, chapter: int) -> dict[str, Any]:
    """What has been generated for this chapter so far, or an empty set."""
    if not path.exists():
        return empty_store(slug, chapter)

    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ClassLessonsRefused(f"{path} is not readable JSON: {error}") from error

    assert_holds(store, slug=slug, chapter=chapter, source=str(path))

    return store


def assert_holds(store: dict[str, Any], *, slug: str, chapter: int, source: str) -> None:
    """Refuse a store that is not this chapter's, or not a shape this code knows.

    Both refusals exist for the same reason and neither is theoretical: a file
    under an unknown schema would be read for fields that may mean something else
    in it, and a file holding another chapter's lessons would attach one
    chapter's teaching to another's concepts.
    """
    schema = str(store.get("schema_version") or "").strip()

    if schema != STORE_SCHEMA_VERSION:
        raise ClassLessonsRefused(
            f"{source} is {schema or 'unversioned'!r}, not {STORE_SCHEMA_VERSION!r}; this code "
            f"knows where a class lesson lives in that shape and not in another"
        )

    held = str(store.get("lesson_stable_key") or "").strip()
    expected = f"{slug}:ch{chapter:02d}"

    if held != expected:
        raise ClassLessonsRefused(
            f"{source} holds {held or 'nothing'!r} but this is {expected!r}; one chapter's class "
            f"lessons would be read as another's"
        )


def lesson_of(store: dict[str, Any], concept_key: str) -> dict[str, Any] | None:
    """The concept's class lesson as it stands, or None if it has never run."""
    entry = (store.get("concepts") or {}).get(concept_key)

    return entry.get("class_lesson") if isinstance(entry, dict) else None


def lessons(store: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Every class lesson this store holds, by concept, in the order it was written.

    A concept with an entry and no lesson in it is absent from the result rather
    than present and empty: the two are the same fact — nothing has been
    generated for it — and a caller that had to tell them apart would be deciding
    what an empty lesson means.
    """
    found: dict[str, dict[str, Any]] = {}

    for key, entry in (store.get("concepts") or {}).items():
        lesson = entry.get("class_lesson") if isinstance(entry, dict) else None

        if lesson:
            found[str(key)] = lesson

    return found


def record(store: dict[str, Any], concept_key: str, lesson: dict[str, Any], report: dict) -> None:
    """Keep this run's result, and what the run did, next to the lesson.

    `runs` is the list of what each pass added, so how many times a concept has
    been run and what each run was worth are the same fact read two ways.
    """
    entry = (store.setdefault("concepts", {})).setdefault(concept_key, {"runs": [], "class_lesson": {}})
    entry["runs"] = list(entry.get("runs") or []) + [contract.summary(report)]
    entry["class_lesson"] = lesson


def save(path: Path, store: dict[str, Any]) -> None:
    """Written after every concept, so an interrupted chapter keeps what it did."""
    atomic_write_json(path, store)
