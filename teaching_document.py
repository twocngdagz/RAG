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

PICTURES ARE MET IN THE TEACHING, NOT BESIDE IT. A computed diagram enters the
block list immediately after the block it illustrates, so the wizard shows the
worked example and then draws it. The block carries the asset's key, its caption
and its alt text; the picture itself rides in the package's asset channel.

A CLASS LESSON BELONGS TO ONE CONCEPT, AND ADDS. B20.1's transform stage writes,
per concept, the thing a teacher stands up and delivers: a goal, the techniques
that reach it, and the examples worked in front of the class. Those become blocks
too — the SAME block types, because a goal is a goal and a worked example is a
worked example whichever document it came from — but each one names the concept
it belongs to, because the wizard teaches one concept at a time and blocks pooled
at the chapter level cannot be split back apart. They are ADDED: the chapter's own
overview, method, goals, mistakes and practice plan stay exactly where they were.
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

# What a picture is, as a block. Named once here because the package's
# structural check reads the same constant: a block of this type must name an
# asset the package actually contains.
ILLUSTRATION_BLOCK_TYPE = "illustration"

# Where a class lesson's blocks say they came from. Not one of SECTION_ORDER,
# because they did not come out of the Coach document at all: they came from the
# class-lesson contract, one concept at a time. Saying so is the difference
# between "the chapter's goals" and "this concept's goal", which is a difference
# a learner meets.
CLASS_LESSON_SECTION = "class_lesson"

# What each part of a class lesson IS, as a block. No new vocabulary: the goal is
# the same kind of block the chapter's goals are, a technique explains a concept
# exactly as an enrichment technique does, and a worked example is a worked
# example. A second set of types for the same teaching would leave a renderer
# with two ways to show one thing.
CLASS_LESSON_BLOCK_TYPE = {
    "goal": BLOCK_TYPE["learning_goals"],
    "techniques": BLOCK_TYPE["techniques"],
    "worked_examples": BLOCK_TYPE["worked_examples"],
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


def with_class_lessons(
    document: dict[str, Any], class_lessons: list[dict[str, Any]]
) -> dict[str, Any]:
    """The same document, with each concept's class lesson added as its own blocks.

    ADDED, and that word is the whole design. A class lesson is the classroom
    teaching for ONE concept; the enrichment is what surrounds it — the chapter's
    method, its overview, its goals, the mistakes to avoid, the practice plan.
    Letting one stand in for the other would lose whichever of them the generator
    did not happen to cover, and the loss would be invisible: the package would
    still look like a complete lesson.

    Each entry is `{concept_stable_key, class_lesson, provenance}`. The lesson has
    already been held to `class_lesson_contract` by whoever read it off disk —
    this module places teaching, it does not decide what a class lesson is.

    Blocks come out in the order the entries arrive, and per concept in the order
    the teaching is delivered: the goal, then the techniques that reach it, then
    the examples worked in front of the class.
    """
    if not class_lessons:
        return document

    blocks = list(document.get("blocks") or [])
    keys = {str(block.get("key") or "") for block in blocks}

    for entry in class_lessons:
        for block in _class_lesson_blocks(entry):
            if block["key"] in keys:
                raise TeachingDocumentRefused(
                    f"the class lesson block {block['key']!r} is already in this teaching "
                    f"document; two blocks under one key leave a reader no way to say which "
                    f"teaching is which"
                )

            keys.add(block["key"])
            blocks.append(block)

    # Restated across the whole list, so no block carries a number describing
    # where it used to be.
    return {**document, "blocks": [{**block, "position": index} for index, block in enumerate(blocks)]}


def _class_lesson_blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """One concept's class lesson, as the blocks a learner is taught through."""
    concept_stable_key = _text(entry.get("concept_stable_key"))
    lesson = entry.get("class_lesson") or {}
    provenance = entry.get("provenance") or {}

    if not concept_stable_key:
        raise TeachingDocumentRefused(
            "a class lesson arrived without the concept it belongs to; blocks pooled at the "
            "chapter level cannot be split back apart"
        )

    goal = _text(lesson.get("goal"))

    if not goal:
        raise TeachingDocumentRefused(
            f"the class lesson for {concept_stable_key!r} has no goal, so it teaches nothing"
        )

    built: list[dict[str, Any]] = [
        _class_lesson_block(concept_stable_key, "goal", "goal", {"lines": [goal]}, provenance)
    ]

    for index, technique in enumerate(lesson.get("techniques") or []):
        built.append(
            _class_lesson_block(
                concept_stable_key,
                f"techniques.{index}",
                "techniques",
                {
                    "name": _text(technique.get("name")),
                    "purpose": _text(technique.get("purpose")),
                    # `steps` rather than the enrichment's `how_to`, because the
                    # contract asks for a name AND an instruction per step and
                    # flattening them into one line would throw the name away.
                    # The package already carries steps in that shape: it is how
                    # the chapter's own method is written.
                    "steps": [
                        {"step": _text(step.get("step")), "detail": _text(step.get("detail"))}
                        for step in (technique.get("steps") or [])
                        if isinstance(step, dict)
                    ],
                    "example": _text(technique.get("example")),
                    "why_it_matters": _text(technique.get("why_it_matters")),
                    "common_error": _text(technique.get("common_error")),
                },
                provenance,
            )
        )

    for index, example in enumerate(lesson.get("worked_examples") or []):
        built.append(
            _class_lesson_block(
                concept_stable_key,
                f"worked_examples.{index}",
                "worked_examples",
                {
                    "title": _text(example.get("title")),
                    "input": _text(example.get("input")),
                    "decoding": _text(example.get("decoding")),
                    "plan": _text(example.get("plan")),
                    "model_answer": _text(example.get("model_answer")),
                    "annotations": [
                        {"part": _text(note.get("part")), "comment": _text(note.get("comment"))}
                        for note in (example.get("annotations") or [])
                        if isinstance(note, dict)
                    ],
                },
                provenance,
            )
        )

    return built


def _class_lesson_block(
    concept_stable_key: str,
    part: str,
    kind: str,
    content: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        # The concept is inside the key as well as beside it, because keys have
        # to be unique across a document that may carry several concepts' class
        # lessons and a chapter's own teaching at the same time.
        "key": f"{CLASS_LESSON_SECTION}.{concept_stable_key}.{part}",
        "type": CLASS_LESSON_BLOCK_TYPE[kind],
        "version": 1,
        "section": CLASS_LESSON_SECTION,
        # Whose teaching this is. The wizard runs explain -> worked example -> try
        # per concept, and it can only do that if each block says which concept it
        # belongs to.
        "concept_stable_key": concept_stable_key,
        "content": content,
        "provenance": provenance,
    }


def with_illustrations(
    document: dict[str, Any], illustrations: list[dict[str, Any]]
) -> dict[str, Any]:
    """The same document, with each picture placed after the block it illustrates.

    Inserted rather than appended, because a diagram that arrived at the end of
    the lesson would be met after the teaching it explains — and position is
    what a wizard shows a learner next. Positions are restated afterwards, so
    the list never carries numbers that describe where a block used to be.

    An illustration naming a block this document does not have is REFUSED. The
    alternative — dropping it, or parking it at the end — would ship a lesson
    whose picture sits somewhere nobody chose.
    """
    if not illustrations:
        return document

    blocks = list(document.get("blocks") or [])
    keys = {str(block.get("key") or "") for block in blocks}
    placed: dict[str, list[dict[str, Any]]] = {}

    for illustration in illustrations:
        anchor = str(illustration.get("appears_after") or "").strip()

        if anchor not in keys:
            raise TeachingDocumentRefused(
                f"the illustration {illustration.get('key')!r} appears after {anchor!r}, which this "
                f"teaching document does not contain; a picture with no place in the lesson is "
                f"met nowhere"
            )

        placed.setdefault(anchor, []).append(illustration)

    arranged: list[dict[str, Any]] = []

    for block in blocks:
        arranged.append(block)

        for illustration in placed.get(str(block.get("key") or ""), []):
            arranged.append(
                {
                    "key": illustration["key"],
                    "type": ILLUSTRATION_BLOCK_TYPE,
                    "version": 1,
                    # The picture belongs to the same part of the lesson as the
                    # teaching it draws, so it carries that section rather than
                    # a section of its own.
                    "section": block.get("section"),
                    "content": illustration["content"],
                    "provenance": illustration["provenance"],
                }
            )

    return {
        **document,
        "blocks": [{**block, "position": index} for index, block in enumerate(arranged)],
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
