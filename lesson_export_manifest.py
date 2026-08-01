"""The declared mapping from a chapter's material to a lesson package.

RAG's generated chapters carry no stable keys, no objective statements and no
objective references — a chapter is titles, explanations, examples and questions,
each with its own provenance. That is enough to say WHERE a sentence came from
and not enough to say WHAT it teaches or assesses.

The exporter must not fill that gap by guessing. Deriving an objective from an
explanation's wording, or aligning a practice question to whichever objective is
nearest it in the file, publishes an alignment nobody authored — and every piece
of evidence a learner then produces is recorded against a goal that may have
nothing to do with what they did. Rejecting an unmapped chapter is the cheaper
mistake by a wide margin: it is visible, and it is fixed by writing the mapping
down.

So the mapping is declared, persisted beside the material, and read here. It
supplies what the chapter cannot:

    lesson       stable key, title, domain
    objectives   stable key, statement, type — authored, not extracted
    activities   stable key, which chapter elements they are built from, which
                 objectives they serve, and the response/evaluation/scheduling
                 contract they are delivered under
    resources    only material explicitly declared reusable

Element references are PATHS into the chapter — `core_lessons.2.explanation` —
so the manifest points at content rather than restating it. A path that does not
resolve is an error, not an empty block: the mapping and the material have
drifted apart, and shipping the half that still resolves would quietly drop
teaching.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MANIFEST_FILE = "output/{slug}.chapter{n:02d}.export_manifest.json"

MANIFEST_SCHEMA_VERSION = "lesson.export_manifest.v1"


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
            f"cannot be exported: its objectives and alignments would have to be "
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

    objective_keys: set[str] = set()

    for index, objective in enumerate(manifest.get("objectives") or []):
        path = f"objectives.{index}"
        key = str((objective or {}).get("stable_key") or "").strip()

        if not key:
            problems.append(f"{path}.stable_key is missing")
        else:
            objective_keys.add(key)

        # The statement is AUTHORED here because the chapter has none. An
        # objective read off an explanation would be a summary of teaching, not
        # a statement of what a learner can do.
        if not str((objective or {}).get("statement") or "").strip():
            problems.append(f"{path}.statement is missing")

        if not str((objective or {}).get("objective_type") or "").strip():
            problems.append(f"{path}.objective_type is missing")

    framework = manifest.get("competency_framework") or {}

    if not str(framework.get("stable_key") or "").strip():
        problems.append("competency_framework.stable_key is missing")

    if not str(framework.get("title") or "").strip():
        problems.append("competency_framework.title is missing")

    if not manifest.get("activities"):
        problems.append("activities is empty; a lesson with no activities teaches nothing")

    for index, activity in enumerate(manifest.get("activities") or []):
        problems.extend(_activity_problems(activity or {}, f"activities.{index}", objective_keys))

    for index, resource in enumerate(manifest.get("resources") or []):
        path = f"resources.{index}"

        if not str((resource or {}).get("stable_key") or "").strip():
            problems.append(f"{path}.stable_key is missing")

        # Resources are for material declared reusable. An ordinary example
        # stays a block in the activity that uses it; promoting every example to
        # a resource would invent a reuse claim nobody made.
        if not (resource or {}).get("elements"):
            problems.append(f"{path}.elements is empty")

    return problems


def _activity_problems(activity: dict[str, Any], path: str, objective_keys: set[str]) -> list[str]:
    problems: list[str] = []

    if not str(activity.get("stable_key") or "").strip():
        problems.append(f"{path}.stable_key is missing")

    if not activity.get("elements"):
        problems.append(f"{path}.elements is empty; it names no chapter content")

    alignments = activity.get("objective_alignments") or []

    if not alignments:
        problems.append(
            f"{path}.objective_alignments is empty; there is no fallback that "
            f"aligns an activity to every objective in the chapter"
        )

    for alignment_index, alignment in enumerate(alignments):
        alignment_path = f"{path}.objective_alignments.{alignment_index}"
        key = str((alignment or {}).get("objective_stable_key") or "").strip()

        if not key:
            problems.append(f"{alignment_path}.objective_stable_key is missing")
        elif key not in objective_keys:
            problems.append(f"{alignment_path} names {key!r}, which this manifest does not declare")

        if not str((alignment or {}).get("alignment_role") or "").strip():
            problems.append(f"{alignment_path}.alignment_role is missing")

    # The delivery contract is declared, not guessed. Whether a question is
    # answerable, and how it is marked, is a teaching decision.
    for field in ("type", "evidence_mode", "response", "evaluation", "scheduling"):
        if not activity.get(field):
            problems.append(f"{path}.{field} is missing")

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
