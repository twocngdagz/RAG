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
    concepts           stable key, statement, type — authored, not extracted.
                       The statement is written ONCE: a concept is its own
                       objective, and two names for one idea is the disease
                       this vocabulary was cured of.
    bank               which skill's questions a concept asks, and the contract
                       they are delivered and marked under
    resources          only material explicitly declared reusable
    assets             pictures sealed into the package, each saying what it
                       illustrates and where it came from

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

# Manifests are AUTHORED, so they live with the code rather than in output/,
# which is generated and gitignored. This pointed at output/ and B11.1 wrote the
# real manifest to `manifests/` anyway, leaving two copies and no rule about
# which one wins.
MANIFEST_FILE = "manifests/{slug}.chapter{n:02d}.export_manifest.json"

MANIFEST_SCHEMA_VERSION = "lesson.export_manifest.v2"


class ManifestMissing(Exception):
    """No mapping exists for this chapter, so it cannot be exported."""


class ManifestInvalid(Exception):
    """A mapping exists but does not say enough to export from."""


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

    problems = validate(manifest)

    if problems:
        raise ManifestInvalid(f"{path} cannot be exported from:\n  " + "\n  ".join(problems))

    return manifest


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
