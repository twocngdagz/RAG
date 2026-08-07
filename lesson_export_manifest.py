"""The declared mapping from a chapter's material to a lesson package.

RAG's generated chapters carry no stable keys, no objective statements and no
objective references — a chapter is titles, explanations, examples and questions,
each with its own provenance. That is enough to say WHERE a sentence came from
and not enough to say WHAT it teaches or assesses.

The exporter must not fill that gap by guessing. Deriving a concept from an
explanation's wording, or attaching a practice question to whichever concept is
nearest it in the file, publishes an alignment nobody authored — and every piece
of evidence a learner then produces is recorded against a goal that may have
nothing to do with what they did. Rejecting an unmapped chapter is the cheaper
mistake by a wide margin: it is visible, and it is fixed by writing the mapping
down.

So the mapping is declared, persisted in `manifests/` where authored things
live, and read here. It supplies what the chapter cannot:

    lesson             stable key, title, domain
    teaching_document  which generator produced the Coach document being
                       published, which the document itself does not record
    class_lessons      which generator produced the chapter's class lessons,
                       which the class-lesson store does not record either.
                       Declared only by a chapter that HAS them
    concepts           stable key, statement, type — authored, not extracted.
                       The statement is written ONCE: a concept is its own
                       objective, and two names for one idea is the disease
                       this vocabulary was cured of.
    bank               which skill's questions a concept asks, and the contract
                       they are delivered and marked under
    resources          only material explicitly declared reusable
    assets             pictures sealed into the package, each saying what it
                       illustrates and where it came from
    diagrams           pictures COMPUTED from the maths: which drawing, which
                       worked example or exercise supplies the numbers, and
                       where in the lesson the learner meets it. The numbers are
                       read from the material rather than restated here, so a
                       diagram cannot come to show a different sum from the one
                       it sits beside

Element references are PATHS into the chapter — `review_checklist.2` — so the
manifest points at content rather than restating it. A path that does not
resolve is an error, not an empty block: the mapping and the material have
drifted apart, and shipping the half that still resolves would quietly drop
teaching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import exercise_bank
import lesson_diagrams

# Where a diagram may read its numbers from: a worked example of the teaching
# document being published, or one exercise out of a concept's bank. Both are
# material this package already carries, so the picture and the question a
# learner meets can never be two different sums.
DIAGRAM_SOURCES = ("worked_examples.", "exercises.")

# Manifests are AUTHORED, so they live with the code rather than in output/,
# which is generated and gitignored. This pointed at output/ and B11.1 wrote the
# real manifest to `manifests/` anyway, leaving two copies and no rule about
# which one wins.
MANIFEST_FILE = "manifests/{slug}.chapter{n:02d}.export_manifest.json"

MANIFEST_SCHEMA_VERSION = "lesson.export_manifest.v2"

# Where a mapping says a person has read it. Required, and required to be exactly
# true: a draft that lost its marker, a field misspelled, a generator that never
# learned to write one — every one of those means nobody said yes, and every one
# of them would pass a check that only looked for `false`.
APPROVAL_FIELD = "approved"


class ManifestMissing(Exception):
    """No mapping exists for this chapter, so it cannot be exported."""


class ManifestInvalid(Exception):
    """A mapping exists but does not say enough to export from."""


class ManifestUnapproved(Exception):
    """A mapping exists and nobody has approved it, so it may not be published."""


def manifest_path(slug: str, chapter: int) -> Path:
    return Path(MANIFEST_FILE.format(slug=slug, n=chapter))


def load(slug: str, chapter: int) -> dict[str, Any]:
    """Read the mapping for one chapter, or refuse and say what is missing."""
    path = manifest_path(slug, chapter)

    if not path.exists():
        raise ManifestMissing(
            f"no export manifest at {path}. A chapter without a declared mapping "
            f"cannot be exported: its concepts and alignments would have to be "
            f"invented, and evidence would be recorded against goals nobody set."
        )

    try:
        manifest = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        raise ManifestInvalid(f"{path} is not readable JSON: {error}") from error

    assert_approved(manifest, str(path))

    problems = validate(manifest)

    if problems:
        raise ManifestInvalid(f"{path} cannot be exported from:\n  " + "\n  ".join(problems))

    return manifest


def assert_approved(manifest: dict[str, Any], source: str) -> None:
    """Refuse a mapping nobody has said yes to.

    A draft mapping is a machine's guess at what a chapter teaches: which abilities
    it introduces, what each one claims a learner can do, and which questions
    measure it. Publish that unread and every piece of evidence a learner produces
    is filed against a goal nobody set — and it will look, from the outside, exactly
    like teaching somebody wrote.

    So approval is stated, not assumed. `approved` must be exactly `true`. Absent
    is not approved: a mapping that never says who read it has not been read, and
    treating silence as consent is how a draft ships by accident.
    """
    if manifest.get(APPROVAL_FIELD) is True:
        return

    stated = repr(manifest[APPROVAL_FIELD]) if APPROVAL_FIELD in manifest else "not stated at all"

    raise ManifestUnapproved(
        f"{source} is not approved ({APPROVAL_FIELD} is {stated}), so it cannot be exported. "
        f"A mapping decides what a lesson claims to teach and what a learner's evidence is "
        f"filed against; until a person has read this one and set {APPROVAL_FIELD} to true, "
        f"publishing it would put a guess in front of a learner."
    )


def validate(manifest: dict[str, Any]) -> list[str]:
    """Everything the mapping fails to say, with the path to each gap."""
    problems: list[str] = []

    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        problems.append(
            f"manifest_schema_version is not {MANIFEST_SCHEMA_VERSION}"
        )

    lesson = manifest.get("lesson") or {}

    for field in ("stable_key", "title", "domain"):
        if not str(lesson.get(field) or "").strip():
            problems.append(f"lesson.{field} is missing")

    # The Coach document does not record which run wrote it, so the manifest
    # says. Naming a generator RAG cannot verify would be inventing a fact about
    # authorship, exactly as `authored_by` would be if it were defaulted.
    if not str((manifest.get("teaching_document") or {}).get("generator_version") or "").strip():
        problems.append(
            "teaching_document.generator_version is missing; the teaching document does not "
            "record which run produced it and the exporter may not invent one"
        )

    # Declared only by a chapter that has class lessons, so its ABSENCE is not a
    # gap and is not checked here — whether this chapter has any is a fact about
    # a file on disk, and the exporter is where that is known. What is checked is
    # the shape: a block that says a generator was named, with no name in it,
    # would be worse than no block at all.
    if "class_lessons" in manifest:
        if not str((manifest.get("class_lessons") or {}).get("generator_version") or "").strip():
            problems.append(
                "class_lessons.generator_version is missing; the class lessons do not record "
                "which generator wrote them and the exporter may not invent one"
            )

    concept_keys: set[str] = set()

    if not manifest.get("concepts"):
        problems.append("concepts is empty; a lesson that introduces nothing teaches nothing")

    for index, concept in enumerate(manifest.get("concepts") or []):
        path = f"concepts.{index}"
        key = str((concept or {}).get("stable_key") or "").strip()

        if not key:
            problems.append(f"{path}.stable_key is missing")
        else:
            concept_keys.add(key)

        # The statement is AUTHORED here because the chapter has none. A concept
        # read off an explanation would be a summary of teaching, not a statement
        # of what a learner can do.
        if not str((concept or {}).get("statement") or "").strip():
            problems.append(f"{path}.statement is missing")

        if not str((concept or {}).get("objective_type") or "").strip():
            problems.append(f"{path}.objective_type is missing")

        problems.extend(exercise_bank.problems((concept or {}).get("bank"), path))

    for index, concept in enumerate(manifest.get("concepts") or []):
        bank = (concept or {}).get("bank") or {}

        for alignment_index, alignment in enumerate(bank.get("also_aligns_to") or []):
            alignment_path = f"concepts.{index}.bank.also_aligns_to.{alignment_index}"
            key = str((alignment or {}).get("objective_stable_key") or "").strip()

            if not key:
                problems.append(f"{alignment_path}.objective_stable_key is missing")
            elif key not in concept_keys:
                problems.append(f"{alignment_path} names {key!r}, which this manifest does not declare")

            if not str((alignment or {}).get("alignment_role") or "").strip():
                problems.append(f"{alignment_path}.alignment_role is missing")

    framework = manifest.get("competency_framework") or {}

    if not str(framework.get("stable_key") or "").strip():
        problems.append("competency_framework.stable_key is missing")

    if not str(framework.get("title") or "").strip():
        problems.append("competency_framework.title is missing")

    for index, resource in enumerate(manifest.get("resources") or []):
        path = f"resources.{index}"

        if not str((resource or {}).get("stable_key") or "").strip():
            problems.append(f"{path}.stable_key is missing")

        # Resources are for material declared reusable. An ordinary example
        # stays a block in the teaching document; promoting every example to a
        # resource would invent a reuse claim nobody made.
        if not (resource or {}).get("elements"):
            problems.append(f"{path}.elements is empty")

    for index, asset in enumerate(manifest.get("assets") or []):
        path = f"assets.{index}"

        for field in ("stable_key", "media_type", "alt_text", "caption", "illustrates"):
            if not str((asset or {}).get(field) or "").strip():
                problems.append(f"{path}.{field} is missing")

        if not (asset or {}).get("provenance"):
            problems.append(f"{path}.provenance is missing")

    for index, diagram in enumerate(manifest.get("diagrams") or []):
        path = f"diagrams.{index}"

        # No caption, no alt text and no provenance here: a computed diagram
        # writes its own from the numbers it drew. A caption authored by hand
        # could say quarters while the picture shows thirds, and the learner who
        # cannot see the picture is the one who would never find out.
        for field in ("stable_key", "kind", "illustrates", "numbers_from", "appears_after"):
            if not str((diagram or {}).get(field) or "").strip():
                problems.append(f"{path}.{field} is missing")

        kind = str((diagram or {}).get("kind") or "").strip()

        if kind and kind not in lesson_diagrams.KINDS:
            problems.append(
                f"{path}.kind {kind!r} is not one of {', '.join(lesson_diagrams.KINDS)}"
            )

        reference = str((diagram or {}).get("numbers_from") or "").strip()

        if reference and not reference.startswith(DIAGRAM_SOURCES):
            problems.append(
                f"{path}.numbers_from {reference!r} names neither a worked example "
                f"({DIAGRAM_SOURCES[0]}<n>) nor an exercise ({DIAGRAM_SOURCES[1]}<item id>)"
            )

    return problems


def resolve_element(chapter: dict[str, Any], reference: str) -> Any:
    """Follow a manifest path into the chapter, or say it does not resolve.

    Dotted, with integer segments indexing lists: `core_lessons.2.explanation`.
    A reference that does not resolve is an error rather than an empty block —
    the mapping and the material have drifted, and shipping whatever still
    resolves would drop teaching without saying so.
    """
    node: Any = chapter

    for segment in reference.split("."):
        if isinstance(node, list):
            if not segment.isdigit() or int(segment) >= len(node):
                raise ManifestInvalid(f"{reference!r} does not resolve: no index {segment}")
            node = node[int(segment)]
            continue

        if not isinstance(node, dict) or segment not in node:
            raise ManifestInvalid(f"{reference!r} does not resolve: no {segment!r}")

        node = node[segment]

    return node
