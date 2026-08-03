"""The lesson's teaching document: the Coach page, turned into ordered blocks.

A v1 package shipped whatever handful of chapter claims a manifest happened to
name. That is not a lesson — it is a sample of one. The taught thing a learner
actually meets is the Coach document: the method, the techniques that explain
each idea, every worked example with its decoding, plan and annotations, the
mistakes to avoid, the practice plan, the checklist. v2 carries all of it.

WHAT A BLOCK IS. One deliverable unit — the amount of teaching a wizard shows
before the learner moves on. That rule decides how each section becomes blocks,
and it is the only reason the split differs between sections:

    one block per item     techniques, worked examples, useful-language
                           categories, common mistakes — each is independently
                           teachable and is met on its own
    one block per section   the method, the overview, the goals list, the
                           practice plan, the checklist, the strategy notes —
                           each reads as a single screen

ORDER IS THE COACH'S OWN. `SECTION_ORDER` is the order the Coach page renders
in, not a teaching decision this module gets to make. Blocks come out in that
order and carry their position explicitly, so a reader never has to infer it.

NOTHING IS SILENTLY DROPPED. A document carrying a section this module does not
know how to publish is REFUSED, not exported without it. Quietly shipping the
sections we happen to recognise would lose teaching and say nothing, and the
loss would surface as a learner meeting a lesson with a hole in it.
"""

from __future__ import annotations

from typing import Any

import lesson_provenance

# The shape the Coach document is written in. A different one is refused rather
# than parsed hopefully: this module knows where teaching lives in THIS shape.
COACH_SCHEMA_VERSION = "pte_lesson_enrichment.v1"

# The order CoachView renders these in, which is the order a learner meets them.
SECTION_ORDER = (
    "core_method",
    "overview",
    "learning_goals",
    "techniques",
    "worked_examples",
    "useful_language",
    "common_mistakes",
    "practice_plan",
    "mastery_checklist",
    "strategy_notes",
)

# Sections whose items are each independently teachable: one block each.
PER_ITEM_SECTIONS = ("techniques", "worked_examples", "useful_language", "common_mistakes")

# What a block of each section IS, named for the teaching it carries rather than
# for the field it came out of.
BLOCK_TYPE = {
    "core_method": "method",
    "overview": "overview",
    "learning_goals": "goals",
    "techniques": "concept_explanation",
    "worked_examples": "worked_example",
    "useful_language": "language",
    "common_mistakes": "common_mistake",
    "practice_plan": "practice_plan",
    "mastery_checklist": "checklist",
    "strategy_notes": "strategy_notes",
}

# Sections a teaching document cannot be published without. The other two are
# genuinely optional — the Coach page hides them when empty — so an otherwise
# complete lesson is not refused over them.
REQUIRED_SECTIONS = tuple(
    section for section in SECTION_ORDER if section not in ("useful_language", "strategy_notes")
)

# Keys that identify the document rather than teach anything. Everything else in
# the document must be a section this module publishes, or the export stops.
NON_SECTION_KEYS = (
    "schema_version",
    "task_type",
    "lesson_title",
    "source_label",
    "modality",
    "metadata",
)


class TeachingDocumentRefused(Exception):
    """The teaching document cannot be published as blocks, and why."""


def build(
    document: dict[str, Any],
    *,
    slug: str,
    chapter_number: int,
    grounded_in_source_chunk_ids: list[str],
    generator_version: str,
) -> dict[str, Any]:
    """The whole Coach document as ordered blocks, or a refusal naming the gap.

    `generator_version` is passed in rather than read out of the document,
    because the document does not record which run produced it. The manifest
    declares it, for the same reason `authored_by` is declared: naming a
    generator RAG cannot verify would be inventing a fact about authorship.
    """
    _assert_publishable(document, slug=slug, chapter_number=chapter_number)

    provenance = {
        "origin": lesson_provenance.PEDAGOGICAL_GENERATION,
        # What the enrichment run was shown: this chapter's source material.
        "grounded_in_source_chunk_ids": sorted(set(grounded_in_source_chunk_ids)),
        "generation_reason": _generation_reason(document),
        "generator_version": generator_version,
    }

    blocks: list[dict[str, Any]] = []

    for section in SECTION_ORDER:
        for key, content in _section_blocks(section, document.get(section)):
            blocks.append(
                {
                    "key": key,
                    "type": BLOCK_TYPE[section],
                    "version": 1,
                    "section": section,
                    # Stated rather than implied. Order is part of what the
                    # lesson teaches, and a reader should not have to trust that
                    # nobody re-sorted the list on the way here.
                    "position": len(blocks),
                    "content": content,
                    "provenance": provenance,
                }
            )

    if not blocks:
        raise TeachingDocumentRefused("the teaching document produced no blocks; there is nothing to teach")

    return {
        "source_label": str(document.get("source_label") or "").strip(),
        "title": str(document.get("lesson_title") or "").strip(),
        "generator_version": generator_version,
        "blocks": blocks,
    }


def _assert_publishable(document: dict[str, Any], *, slug: str, chapter_number: int) -> None:
    if not isinstance(document, dict):
        raise TeachingDocumentRefused("the teaching document is not an object")

    schema = str(document.get("schema_version") or "").strip()

    if schema != COACH_SCHEMA_VERSION:
        raise TeachingDocumentRefused(
            f"the teaching document is {schema or 'unversioned'!r}, not {COACH_SCHEMA_VERSION!r}; "
            f"this exporter does not know where teaching lives in that shape"
        )

    expected_label = f"{slug}:ch{chapter_number:02d}"
    label = str(document.get("source_label") or "").strip()

    if label != expected_label:
        raise TeachingDocumentRefused(
            f"the teaching document identifies as {label!r} but the lesson is {expected_label!r}; "
            f"publishing it would attach one chapter's teaching to another"
        )

    known = set(SECTION_ORDER) | set(NON_SECTION_KEYS)
    unknown = sorted(set(document) - known)

    if unknown:
        raise TeachingDocumentRefused(
            f"the teaching document carries {', '.join(unknown)}, which this exporter cannot "
            f"publish; exporting without it would drop teaching and say nothing"
        )

    for section in REQUIRED_SECTIONS:
        if not document.get(section):
            raise TeachingDocumentRefused(
                f"the teaching document has no {section}; a lesson without it is not the taught thing"
            )


def _generation_reason(document: dict[str, Any]) -> str:
    """What the enrichment run says it did — its own words, not a summary of ours."""
    note = str((document.get("metadata") or {}).get("provenance_note") or "").strip()

    if not note:
        raise TeachingDocumentRefused(
            "the teaching document records no provenance_note, so it cannot say what it "
            "generated or from what; pedagogical_generation without a reason is unpublishable"
        )

    return note


def _section_blocks(section: str, value: Any) -> list[tuple[str, dict[str, Any]]]:
    if not value:
        # Only the optional sections reach here; the required ones were checked.
        return []

    if section in PER_ITEM_SECTIONS:
        return [
            (f"{section}.{index}", _item_content(section, item, f"{section}.{index}"))
            for index, item in enumerate(value)
        ]

    return [(section, _whole_section_content(section, value))]


def _item_content(section: str, item: Any, path: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise TeachingDocumentRefused(f"{path} is not an object a learner could be shown")

    if section == "techniques":
        return _required(
            path,
            {
                "name": _text(item.get("name")),
                "purpose": _text(item.get("purpose")),
                "how_to": _lines(item.get("how_to")),
                "example": _text(item.get("example")),
                "why_it_matters": _text(item.get("why_it_matters")),
                "common_error": _text(item.get("common_error")),
            },
            must_have=("name", "how_to"),
        )

    if section == "worked_examples":
        # decoding, plan and annotations are the example's teaching. An example
        # shipped as answer-only shows a learner what to write and not how the
        # method got there, which is the one thing a worked example is for.
        return _required(
            path,
            {
                "title": _text(item.get("title")),
                "input": _text(item.get("input")),
                "decoding": _text(item.get("decoding")),
                "plan": _text(item.get("plan")),
                "model_answer": _text(item.get("model_answer")),
                "annotations": [
                    {"part": _text(note.get("part")), "comment": _text(note.get("comment"))}
                    for note in (item.get("annotations") or [])
                    if isinstance(note, dict)
                ],
            },
            must_have=("title", "input", "model_answer"),
        )

    if section == "useful_language":
        return _required(
            path,
            {
                "category": _text(item.get("category")),
                "items": [
                    {"item": _text(entry.get("item")), "when_to_use": _text(entry.get("when_to_use"))}
                    for entry in (item.get("items") or [])
                    if isinstance(entry, dict)
                ],
            },
            must_have=("category", "items"),
        )

    return _required(
        path,
        {
            "mistake": _text(item.get("mistake")),
            "why_it_hurts": _text(item.get("why_it_hurts")),
            "fix": _text(item.get("fix")),
        },
        must_have=("mistake", "fix"),
    )


def _whole_section_content(section: str, value: Any) -> dict[str, Any]:
    if section == "core_method":
        return _required(
            section,
            {
                "name": _text(value.get("name")),
                "summary": _text(value.get("summary")),
                "steps": [
                    {"step": _text(step.get("step")), "detail": _text(step.get("detail"))}
                    for step in (value.get("steps") or [])
                    if isinstance(step, dict)
                ],
                "formula": _text(value.get("formula")),
            },
            must_have=("name", "steps"),
        )

    if section == "overview":
        return _required(
            section,
            {
                "what_it_is": _text(value.get("what_it_is")),
                "format_facts": _pairs(value.get("format_facts"), "label", "value"),
                "scoring_factors": _pairs(value.get("scoring_factors"), "name", "what_it_measures"),
                "critical_rules": _lines(value.get("critical_rules")),
            },
            must_have=("what_it_is",),
        )

    if section == "practice_plan":
        return _required(
            section,
            {
                "time_budget": [
                    {
                        "phase": _text(phase.get("phase")),
                        "minutes": _text(phase.get("minutes")),
                        "focus": _text(phase.get("focus")),
                    }
                    for phase in (value.get("time_budget") or [])
                    if isinstance(phase, dict)
                ],
                "drills": _pairs(value.get("drills"), "name", "instructions"),
                "routine": _text(value.get("routine")),
            },
            must_have=("drills",),
        )

    # learning_goals, mastery_checklist, strategy_notes: a list a learner reads
    # in one sitting, so one block, with the lines kept in the order written.
    return _required(section, {"lines": _lines(value)}, must_have=("lines",))


def _required(path: str, content: dict[str, Any], *, must_have: tuple[str, ...]) -> dict[str, Any]:
    missing = [field for field in must_have if not content.get(field)]

    if missing:
        raise TeachingDocumentRefused(f"{path} has no {', '.join(missing)}, so it teaches nothing")

    return content


def _pairs(value: Any, first: str, second: str) -> list[dict[str, str]]:
    return [
        {first: _text(entry.get(first)), second: _text(entry.get(second))}
        for entry in (value or [])
        if isinstance(entry, dict)
    ]


def _lines(value: Any) -> list[str]:
    return [_text(line) for line in (value or []) if _text(line)]


def _text(value: Any) -> str:
    return str(value).strip() if value is not None and str(value).strip() else ""
