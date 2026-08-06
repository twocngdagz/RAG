"""What a class lesson is: the contract, and the checks that hold a reply to it.

Extraction gives a book's topics. Enrichment gives a chapter's detail. Neither
gives a CLASS LESSON — the goal, the method with its steps, and the examples
worked in front of the class, for ONE concept. A person did that transformation
by hand for one chapter, and nothing said who does it for the rest.

So it is contracted out. `docs/class-lesson-contract.md` is the brief, written to
be handed to any generator with nothing else attached: a chat model, a model
behind an API, or a person the work goes to. This module is the executable half
of that document, and it does exactly two things with it.

IT HANDS THE DOCUMENT OVER, BYTE FOR BYTE. `build_prompt` carries the contract
file's own text into the prompt and appends the run's context beneath it. The
generator therefore reads the same bytes a reviewer reads, and the document
cannot drift from what is actually being asked for — the drift `--check` exists
to catch for the enrichment prompt cannot happen here, because there is only one
copy.

IT REFUSES A REPLY THAT DOES NOT SATISFY IT. Every floor the document states is
checked: the shape, the concept it claims to be for, every required field, and
the counts — one technique, two steps, two worked examples, one annotation. A
key the contract does not list is refused rather than stored, because a generator
that invents a field is a generator that has stopped following the document.

WHAT AN ELEMENT'S IDENTITY IS, AND WHY IT IS THE NAME. Runs are unlimited and
each one expands the lesson, so a run must be able to tell "this technique is
already here" from "this technique is new". A technique is identified by its
`name` and a worked example by its `title` — the author's own handle on the
thing, normalised for case and spacing. Content digests are the stricter choice
and are wrong here: the generator is asked to repeat what exists, and a repeat
that gained a comma would arrive as a second copy of the same teaching.

The consequence is stated in the document and is deliberate: rewording an
existing technique changes nothing, because the stored one is kept. Enrichment
adds; changing what is already taught is an edit, and an edit is named by
whoever makes it.

NOTHING IS EVER DELETED, and that is structural rather than hoped for. `merge`
starts from what is stored and only ever appends, so a reply that quietly
dropped half the lesson cannot take it away. `assert_nothing_lost` then checks
the result against the input anyway — the guarantee is cheap to verify and a
merge bug would otherwise be invisible until a learner met the hole.

ILLUSTRATIONS ARE NOT ASKED FOR AND NOT ACCEPTED. They attach afterwards through
the package's asset channel, where an asset names the concept it illustrates.
The prompt never mentions generating one, and a reply carrying an image — a
markdown image, an SVG, a data URI, an image file name — is refused. In maths a
picture carries mathematical content, and one drawn blind by a text generator
would teach whatever it happened to draw.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import domain_packs

ROOT = Path(__file__).resolve().parent

# The contract itself. A document rather than a string constant, because the
# thing being handed to an outside generator has to be readable by the person
# who hands it over.
CONTRACT_DOC = ROOT / "docs" / "class-lesson-contract.md"

SCHEMA_VERSION = "class_lesson.v1"

# The whole shape. Anything else in a reply is refused, so this list is the only
# place a class lesson's keys are declared.
REQUIRED_KEYS = (
    "schema_version",
    "concept_key",
    "concept_statement",
    "goal",
    "techniques",
    "worked_examples",
)

TECHNIQUE_FIELDS = ("name", "purpose", "steps", "example", "why_it_matters", "common_error")
STEP_FIELDS = ("step", "detail")
WORKED_EXAMPLE_FIELDS = ("title", "input", "decoding", "plan", "model_answer", "annotations")
ANNOTATION_FIELDS = ("part", "comment")

# Every field name a class lesson has, and what a field name looks like in a
# book's wording rules. Together they keep the book block from asking for a key
# this contract would refuse.
_CONTRACT_FIELDS = frozenset(
    REQUIRED_KEYS + TECHNIQUE_FIELDS + STEP_FIELDS + WORKED_EXAMPLE_FIELDS + ANNOTATION_FIELDS
)
_FIELD_NAME_RE = re.compile(r"\b[a-z][a-z]*(?:_[a-z]+)+\b")

# The floors the document states, in the one place they are enforced.
MIN_TECHNIQUES = 1
MIN_STEPS = 2
MIN_WORKED_EXAMPLES = 2
MIN_ANNOTATIONS = 1

# The context blocks the run appends under the contract. Named here because the
# document tells the generator to expect exactly these headings.
BOOK_HEADING = "=== THE BOOK ==="
CONCEPT_HEADING = "=== THE CONCEPT ==="
OTHER_CONCEPTS_HEADING = "=== THE OTHER CONCEPTS IN THIS LESSON ==="
MATERIAL_HEADING = "=== THE CHAPTER'S ENRICHED MATERIAL ==="
CURRENT_HEADING = "=== THE CONCEPT'S CURRENT CLASS LESSON ==="

# What a picture looks like in text. Deliberately narrow: it matches an image
# that was PRODUCED — markup, a data URI, a link, a file name — and not a
# sentence telling a learner to draw a bar model, which is teaching and belongs.
_ILLUSTRATION_RE = re.compile(
    r"!\[|<svg\b|</svg>|data:image/|<img\b|\.(?:svg|png|jpe?g|gif|webp)\b",
    re.IGNORECASE,
)

# What an invented field would be called if it were carrying a picture. Only used
# to say so in the refusal — an unlisted key is refused whatever it is called.
_PICTURE_WORDS = ("illustration", "image", "picture", "diagram", "figure", "svg", "asset")

class ClassLessonRefused(Exception):
    """A reply is not a class lesson under this contract, and why."""


class ClassLessonAddedNothing(Exception):
    """A run repeated the current lesson back and added nothing to it."""


class ClassLessonLostContent(Exception):
    """A merge did not keep everything the stored lesson had. A bug, not a reply."""


# --------------------------------------------------------------------------- #
# 1. The prompt: the contract document, then this run's context.
# --------------------------------------------------------------------------- #

def contract_text() -> str:
    """The contract document, verbatim. These bytes go into the prompt."""
    return CONTRACT_DOC.read_text(encoding="utf-8").strip()


def build_prompt(
    *,
    pack: domain_packs.DomainPack,
    concept_key: str,
    concept_statement: str,
    other_concepts: list[dict[str, str]],
    material: dict[str, Any],
    current: dict[str, Any] | None,
) -> str:
    """Everything the generator is given for one concept, in one message.

    `current` is the concept's class lesson as it stands, or None on the first
    run. It is sent IN FULL: a generator that cannot see what exists cannot
    expand it, and would write the same lesson again.
    """
    return "\n".join(
        [
            contract_text(),
            "",
            _book_block(pack),
            "",
            _concept_block(concept_key, concept_statement),
            "",
            _other_concepts_block(other_concepts),
            "",
            MATERIAL_HEADING,
            render_material(material),
            "",
            _current_block(current),
        ]
    )


def _book_block(pack: domain_packs.DomainPack) -> str:
    lines = [
        BOOK_HEADING,
        f"book: {pack.slug} — {pack.title}",
        f"learners: {pack.audience}",
    ]
    rules = _wording_rules(pack)

    if rules:
        lines += ["how to write for them:"] + rules

    return "\n".join(lines)


def _wording_rules(pack: domain_packs.DomainPack) -> list[str]:
    """The book's wording rules, minus any rule about a field this shape has not got.

    A pack's `payload_note` says how this book is written — its maths notation,
    its reading age, what a complete answer looks like — and it was written for
    the enrichment run, so some of its lines name that document's fields. Those
    lines are dropped rather than passed on: a rule telling the generator to fill
    `useful_language` would be asking for a key this contract refuses on arrival,
    and a prompt that contradicts itself is answered inconsistently.
    """
    kept: list[str] = []

    for line in pack.payload_note.strip().splitlines():
        named = set(_FIELD_NAME_RE.findall(line))

        if named and not named & _CONTRACT_FIELDS:
            continue

        kept.append(line)

    return kept


def _concept_block(concept_key: str, concept_statement: str) -> str:
    return "\n".join(
        [
            CONCEPT_HEADING,
            f"concept_key: {concept_key}",
            f"concept_statement: {concept_statement}",
            "Copy both of those into your reply exactly as they are written here.",
        ]
    )


def _other_concepts_block(other_concepts: list[dict[str, str]]) -> str:
    lines = [OTHER_CONCEPTS_HEADING]

    if not other_concepts:
        lines.append("none — this lesson has one concept, and it is yours.")
        return "\n".join(lines)

    lines.append("Taught in their own runs. Do not teach them here.")
    lines += [
        f"- {other.get('stable_key', '')} — {other.get('statement', '')}"
        for other in other_concepts
    ]

    return "\n".join(lines)


def _current_block(current: dict[str, Any] | None) -> str:
    if not current:
        return "\n".join(
            [
                CURRENT_HEADING,
                "none yet — this is the first run for this concept. Write it from the "
                "material above.",
            ]
        )

    return "\n".join(
        [
            CURRENT_HEADING,
            "This already exists and has been kept. Repeat every technique and worked "
            "example below in your reply, unchanged and under the same names and titles, "
            "then ADD new ones. Nothing here may be deleted, replaced or reworded.",
            "```json",
            json.dumps(current, ensure_ascii=False, indent=2),
            "```",
        ]
    )


def render_material(material: dict[str, Any]) -> str:
    """The chapter's enrichment as teaching notes, for the whole chapter.

    Not sliced to the concept. Which technique and which example serve which
    concept is a teaching judgement, and this module has no basis for making it —
    guessing would hand the generator the wrong half of a chapter and call it
    context. The generator is given all of it and told which concept to teach.

    Every teaching section is rendered. `practice_plan` is not: it is a study
    routine, not teaching about the concept, and the prompt is long enough
    without it. `metadata` is bookkeeping and goes the same way.
    """
    if not isinstance(material, dict):
        raise ClassLessonRefused("the chapter's enriched material is not an object")

    out: list[str] = [
        f"lesson_title: {_text(material.get('lesson_title'))}",
        f"source_label: {_text(material.get('source_label'))}",
    ]

    overview = material.get("overview") or {}

    if isinstance(overview, dict) and _text(overview.get("what_it_is")):
        out += ["", "WHAT THE CHAPTER IS ABOUT:", _text(overview.get("what_it_is"))]

        for rule in _lines(overview.get("critical_rules")):
            out.append(f"- rule: {rule}")

    for label, key in (("LEARNING GOALS", "learning_goals"), ("SELF-CHECK", "mastery_checklist"),
                       ("STRATEGY NOTES", "strategy_notes")):
        lines = _lines(material.get(key))

        if lines:
            out += ["", f"{label} (whole chapter):"] + [f"- {line}" for line in lines]

    method = material.get("core_method") or {}

    if isinstance(method, dict) and _text(method.get("name")):
        out += ["", f"THE CHAPTER'S METHOD — {_text(method.get('name'))}", _text(method.get("summary"))]
        out += [
            f"  {index}. {_text(step.get('step'))}: {_text(step.get('detail'))}"
            for index, step in enumerate(method.get("steps") or [], start=1)
            if isinstance(step, dict)
        ]

        if _text(method.get("formula")):
            out.append(f"  formula: {_text(method.get('formula'))}")

    techniques = [t for t in (material.get("techniques") or []) if isinstance(t, dict)]

    if techniques:
        out += ["", "TECHNIQUES (whole chapter):"]

        for technique in techniques:
            out.append(f"- {_text(technique.get('name'))} — {_text(technique.get('purpose'))}")
            out += [f"    how to: {line}" for line in _lines(technique.get("how_to"))]

            for field, label in (("example", "example"), ("why_it_matters", "why it matters"),
                                 ("common_error", "common error")):
                if _text(technique.get(field)):
                    out.append(f"    {label}: {_text(technique.get(field))}")

    examples = [w for w in (material.get("worked_examples") or []) if isinstance(w, dict)]

    if examples:
        out += ["", "WORKED EXAMPLES (whole chapter):"]

        for example in examples:
            out.append(f"- {_text(example.get('title'))}")

            for field, label in (("input", "input"), ("decoding", "decoding"), ("plan", "plan"),
                                 ("model_answer", "model answer")):
                if _text(example.get(field)):
                    out.append(f"    {label}: {_text(example.get(field))}")

            out += [
                f"    note on {_text(note.get('part'))}: {_text(note.get('comment'))}"
                for note in (example.get("annotations") or [])
                if isinstance(note, dict)
            ]

    mistakes = [m for m in (material.get("common_mistakes") or []) if isinstance(m, dict)]

    if mistakes:
        out += ["", "COMMON MISTAKES (whole chapter):"]
        out += [
            f"- {_text(m.get('mistake'))} — why it hurts: {_text(m.get('why_it_hurts'))} "
            f"— fix: {_text(m.get('fix'))}"
            for m in mistakes
        ]

    language = [c for c in (material.get("useful_language") or []) if isinstance(c, dict)]

    if language:
        out += ["", "USEFUL LANGUAGE (whole chapter):"]

        for category in language:
            out.append(f"- {_text(category.get('category'))}:")
            out += [
                f"    {_text(entry.get('item'))} — {_text(entry.get('when_to_use'))}"
                for entry in (category.get("items") or [])
                if isinstance(entry, dict)
            ]

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 2. The check: a reply either satisfies the document or is refused.
# --------------------------------------------------------------------------- #

def validate(document: Any, *, concept_key: str, concept_statement: str) -> dict[str, Any]:
    """The reply as a class lesson, or a refusal naming the part that is missing.

    Returns the document cleaned to exactly the contract's shape — strings
    stripped, nothing else carried — so what is stored is what was checked.
    """
    if not isinstance(document, dict):
        raise ClassLessonRefused("the reply is not a JSON object")

    schema = _text(document.get("schema_version"))

    if schema != SCHEMA_VERSION:
        raise ClassLessonRefused(
            f"the reply is {schema or 'unversioned'!r}, not {SCHEMA_VERSION!r}; the contract "
            f"names one shape and this is not it"
        )

    unknown = sorted(set(document) - set(REQUIRED_KEYS))

    if unknown:
        raise ClassLessonRefused(
            f"the reply carries {', '.join(unknown)}, which the contract does not list. "
            f"A generator inventing a field has stopped following the document"
            + (
                " — and illustrations in particular are attached afterwards, never generated here"
                if any(word in key.lower() for key in unknown for word in _PICTURE_WORDS)
                else ""
            )
        )

    missing = [key for key in REQUIRED_KEYS if key not in document]

    if missing:
        raise ClassLessonRefused(f"the reply has no {', '.join(missing)}")

    _assert_is_for(document, concept_key=concept_key, concept_statement=concept_statement)
    _assert_no_illustration(document)

    goal = _text(document.get("goal"))

    if not goal:
        raise ClassLessonRefused("the reply has an empty goal; a lesson with no goal teaches nothing")

    techniques = [_technique(item, index) for index, item in enumerate(_listed(document, "techniques"))]

    if len(techniques) < MIN_TECHNIQUES:
        raise ClassLessonRefused(
            f"the reply has {len(techniques)} techniques; the contract's floor is "
            f"{MIN_TECHNIQUES}, because a concept with no method is a goal nobody was shown "
            f"how to reach"
        )

    examples = [
        _worked_example(item, index) for index, item in enumerate(_listed(document, "worked_examples"))
    ]

    if len(examples) < MIN_WORKED_EXAMPLES:
        raise ClassLessonRefused(
            f"the reply has {len(examples)} worked_examples; the contract's floor is "
            f"{MIN_WORKED_EXAMPLES}, because one example teaches the example and a second "
            f"teaches the method"
        )

    _assert_named_once("techniques", [technique["name"] for technique in techniques])
    _assert_named_once("worked_examples", [example["title"] for example in examples])

    return {
        "schema_version": SCHEMA_VERSION,
        "concept_key": _text(document.get("concept_key")),
        "concept_statement": _text(document.get("concept_statement")),
        "goal": goal,
        "techniques": techniques,
        "worked_examples": examples,
    }


def _assert_is_for(document: dict[str, Any], *, concept_key: str, concept_statement: str) -> None:
    """A reply for the wrong concept is refused, never filed under the right one."""
    claimed_key = _text(document.get("concept_key"))

    if claimed_key != concept_key.strip():
        raise ClassLessonRefused(
            f"the reply is for concept_key {claimed_key or 'nothing'!r} but this run asked for "
            f"{concept_key!r}; filing it here would teach one concept under another's name"
        )

    claimed_statement = _flat(document.get("concept_statement"))

    if claimed_statement != _flat(concept_statement):
        raise ClassLessonRefused(
            f"the reply restates the concept as {_text(document.get('concept_statement'))!r} "
            f"instead of copying {concept_statement!r}; the statement is approved before the "
            f"run and is not the generator's to rewrite"
        )


def _assert_no_illustration(document: dict[str, Any]) -> None:
    """No picture is generated here — checked, not merely left out of the prompt."""
    for path, value in _strings(document):
        if _ILLUSTRATION_RE.search(value):
            raise ClassLessonRefused(
                f"{path} contains an illustration ({_ILLUSTRATION_RE.search(value).group(0)!r}). "
                f"Pictures are attached afterwards through the package's asset channel, where "
                f"one names the concept it illustrates; a text generator drawing blind teaches "
                f"whatever it happened to draw"
            )


def _technique(item: Any, index: int) -> dict[str, Any]:
    path = f"techniques[{index}]"

    if not isinstance(item, dict):
        raise ClassLessonRefused(f"{path} is not an object")

    _assert_present(path, item, TECHNIQUE_FIELDS)

    steps = [step for step in (item.get("steps") or []) if isinstance(step, dict)]

    if len(steps) < MIN_STEPS:
        raise ClassLessonRefused(
            f"{path} has {len(steps)} steps; the contract's floor is {MIN_STEPS}, because a "
            f"method with one step is a sentence"
        )

    for position, step in enumerate(steps):
        _assert_present(f"{path}.steps[{position}]", step, STEP_FIELDS)

    return {
        "name": _text(item.get("name")),
        "purpose": _text(item.get("purpose")),
        "steps": [{"step": _text(s.get("step")), "detail": _text(s.get("detail"))} for s in steps],
        "example": _text(item.get("example")),
        "why_it_matters": _text(item.get("why_it_matters")),
        "common_error": _text(item.get("common_error")),
    }


def _worked_example(item: Any, index: int) -> dict[str, Any]:
    path = f"worked_examples[{index}]"

    if not isinstance(item, dict):
        raise ClassLessonRefused(f"{path} is not an object")

    _assert_present(path, item, WORKED_EXAMPLE_FIELDS)

    annotations = [note for note in (item.get("annotations") or []) if isinstance(note, dict)]

    if len(annotations) < MIN_ANNOTATIONS:
        raise ClassLessonRefused(
            f"{path} has {len(annotations)} annotations; the contract's floor is "
            f"{MIN_ANNOTATIONS}, because the annotations are the teacher's voice beside the maths"
        )

    for position, note in enumerate(annotations):
        _assert_present(f"{path}.annotations[{position}]", note, ANNOTATION_FIELDS)

    return {
        "title": _text(item.get("title")),
        "input": _text(item.get("input")),
        "decoding": _text(item.get("decoding")),
        "plan": _text(item.get("plan")),
        "model_answer": _text(item.get("model_answer")),
        "annotations": [
            {"part": _text(note.get("part")), "comment": _text(note.get("comment"))}
            for note in annotations
        ],
    }


def _assert_present(path: str, item: dict[str, Any], fields: tuple[str, ...]) -> None:
    empty = [field for field in fields if not item.get(field)]

    if empty:
        raise ClassLessonRefused(f"{path} has no {', '.join(empty)}")


def _assert_named_once(section: str, names: list[str]) -> None:
    """Two techniques under one name would be one technique after the merge."""
    seen: set[str] = set()

    for name in names:
        if _identity(name) in seen:
            raise ClassLessonRefused(
                f"{section} names {name!r} twice; items are matched by name, so a repeated "
                f"name is two pieces of teaching the lesson can only keep one of"
            )

        seen.add(_identity(name))


def _listed(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)

    if not isinstance(value, list):
        raise ClassLessonRefused(f"{key} is not a list")

    return value


# --------------------------------------------------------------------------- #
# 3. The merge: runs are unlimited, and each one only ever adds.
# --------------------------------------------------------------------------- #

def elements(lesson: dict[str, Any]) -> dict[str, str]:
    """Every addressable part of a class lesson: identity -> what it is, for a human."""
    found = {"goal": f"the goal ({_short(lesson.get('goal'))})"}

    for technique in lesson.get("techniques") or []:
        found[f"techniques/{_identity(technique.get('name'))}"] = f"technique {technique.get('name')!r}"

    for example in lesson.get("worked_examples") or []:
        found[f"worked_examples/{_identity(example.get('title'))}"] = (
            f"worked example {example.get('title')!r}"
        )

    return found


def merge(previous: dict[str, Any] | None, incoming: dict[str, Any]) -> tuple[dict[str, Any], dict]:
    """The stored lesson with this run's new material appended, and what changed.

    Starts from what is stored, so nothing can be lost however the reply came
    back: a technique already there is kept as it was and its repeat ignored, and
    only genuinely new names and titles are added. `removed` is therefore always
    empty, and it is reported anyway — "N added, 0 removed" is the sentence the
    enrichment rule already prints, and this is the same promise about the same
    kind of content.
    """
    if previous is None:
        return incoming, {"added": [description for description in elements(incoming).values()],
                          "removed": []}

    merged = json.loads(json.dumps(previous))
    added: list[str] = []

    for section, key in (("techniques", "name"), ("worked_examples", "title")):
        known = {_identity(item.get(key)) for item in merged.get(section) or []}

        for item in incoming.get(section) or []:
            if _identity(item.get(key)) in known:
                continue

            merged.setdefault(section, []).append(item)
            known.add(_identity(item.get(key)))
            added.append(f"{section[:-1].replace('_', ' ')} {item.get(key)!r}")

    return merged, {"added": added, "removed": []}


def summary(report: dict[str, Any]) -> str:
    """The sentence a run prints, in the enrichment rule's own words."""
    return f"{len(report['added'])} added, {len(report['removed'])} removed"


def assert_expanded(report: dict[str, Any]) -> None:
    """A run that repeated the lesson back and added nothing is a wasted request."""
    if report["added"]:
        return

    raise ClassLessonAddedNothing(
        "this run added nothing: every technique and worked example it returned is already "
        "in the lesson. A pass is meant to expand it — ask again."
    )


def assert_nothing_lost(previous: dict[str, Any] | None, merged: dict[str, Any]) -> None:
    """Everything the stored lesson had, the merged one still has."""
    if previous is None:
        return

    lost = sorted(set(elements(previous)) - set(elements(merged)))

    if lost:
        raise ClassLessonLostContent(
            "the merge dropped "
            + ", ".join(elements(previous)[identity] for identity in lost)
            + ". A run adds; it may never take teaching away."
        )


# --------------------------------------------------------------------------- #

def _identity(value: Any) -> str:
    """A name's identity: its own words, insensitive to case and spacing."""
    return " ".join(str(value or "").split()).casefold()


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def _text(value: Any) -> str:
    return str(value).strip() if value is not None and str(value).strip() else ""


def _short(value: Any) -> str:
    return _text(value)[:60]


def _lines(value: Any) -> list[str]:
    return [_text(line) for line in (value or []) if _text(line)]


def _strings(value: Any, path: str = "the reply") -> list[tuple[str, str]]:
    """Every string in the document, with the path to it."""
    if isinstance(value, str):
        return [(path, value)]

    if isinstance(value, dict):
        return [pair for key, item in value.items() for pair in _strings(item, f"{path}.{key}")]

    if isinstance(value, list):
        return [pair for index, item in enumerate(value) for pair in _strings(item, f"{path}[{index}]")]

    return []
