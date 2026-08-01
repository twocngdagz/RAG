"""What RAG hands Ela: one lesson per chapter, versioned, hashed, and traceable.

Nothing here reaches a learner. This is the envelope — Ela imports it in B11.1,
and only then does anything become visible. The package exists so that what was
generated can be identified later: which producer made it, under which pack's
rules, from which source revision, and whether the content has changed since.

Four versions travel with every package, and they answer different questions:

    schema_version   what SHAPE this file is, so a reader knows how to parse it
    producer_version what CODE emitted it, so a bad run is identifiable
    pack_version     which RULES it was written under, so a lesson emitted last
                     month is not silently assumed to match today's
    content_revision which REVISION of the source material it came from

The CONTENT HASH covers the lesson as a learner would meet it: the material, the
order it is met in, which objectives each activity claims to serve, and which
resources it links. Rerun the producer against unchanged material and the hash is
identical, so an importer can tell "generated again" from "genuinely different".
Reorder two activities and it moves, because that is a different lesson. Bump the
producer's own version and it does not: that is a fact about the tool.

Activities carry COMPLETE `learning.activity.v1` definitions. Ela validates and
stores that shape directly, so emitting a package-only arrangement of blocks
would mean the importer had to reconstruct the real thing — and a reconstruction
is a second definition of what an activity is, in the repository that does not
own the contract.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The shape of the file. Bump when a reader would have to parse it differently.
SCHEMA_VERSION = "learning.package.v1"

# The code that emits it. Bump when the emitter's behaviour changes.
PRODUCER_VERSION = "rag-lesson-package/1.0.0"

ACTIVITY_CONTRACT = "learning.activity.v1"

# Ela's vocabulary for how one objective relates to another. Mirrored, and a
# test asserts the mirror holds.
OBJECTIVE_ASSOCIATION_TYPES = (
    "requires",
    "builds_on",
    "is_child_of",
    "is_equivalent_to",
    "aligns_with",
)

# What a resource link must say. Storing a role and nothing else leaves the
# importer to decide when a resource may appear and what using it costs, which
# are teaching decisions the exporter does not get to delegate.
REQUIRED_LINK_FIELDS = ("role", "availability", "phase_visibility", "assistance_effect")

REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "producer_version",
    "pack_slug",
    "pack_version",
    "content_revision",
    "content_hash",
    "lesson",
    "objectives",
    "objective_associations",
    "activities",
    "resources",
)


class PackageRefused(Exception):
    """The material cannot be emitted as a package, and why."""


def content_hash(package: dict[str, Any]) -> str:
    """The SHA-256 of the lesson a learner would meet.

    Covers the material AND the relationships between its parts. Hashing the
    three collections alone would call two lessons identical when one had been
    reordered, or when an activity had been realigned to a different objective —
    both of which change what the lesson teaches.
    """
    semantic = {
        "lesson": _lesson_identity(package.get("lesson") or {}),
        # Positions are included explicitly rather than relied on implicitly, so
        # the hash states that order is part of the meaning.
        "objectives": [
            {"position": index, **_objective_identity(objective)}
            for index, objective in enumerate(package.get("objectives") or [])
        ],
        "activities": [
            {"position": index, **_activity_identity(activity)}
            for index, activity in enumerate(package.get("activities") or [])
        ],
        "objective_associations": [
            {"position": index, **_association_identity(association)}
            for index, association in enumerate(package.get("objective_associations") or [])
        ],
        "resources": [
            {"position": index, **_resource_identity(resource)}
            for index, resource in enumerate(package.get("resources") or [])
        ],
    }

    canonical = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _lesson_identity(lesson: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_key": lesson.get("stable_key"),
        "title": lesson.get("title"),
        "domain": lesson.get("domain"),
        "provenance": lesson.get("provenance"),
    }


def _objective_identity(objective: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_key": objective.get("stable_key"),
        "statement": objective.get("statement"),
        "objective_type": objective.get("objective_type"),
        "provenance": objective.get("provenance"),
    }


def _association_identity(association: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_objective_stable_key": association.get("from_objective_stable_key"),
        "to_objective_stable_key": association.get("to_objective_stable_key"),
        "association_type": association.get("association_type"),
        "strength": association.get("strength"),
    }


def _activity_identity(activity: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_key": activity.get("stable_key"),
        # Which objectives this claims to serve is part of what the lesson
        # teaches, not metadata about it.
        "objective_alignments": activity.get("objective_alignments"),
        "definition": activity.get("definition"),
        "resource_links": activity.get("resource_links"),
    }


def _resource_identity(resource: dict[str, Any]) -> dict[str, Any]:
    return {
        "stable_key": resource.get("stable_key"),
        "definition": resource.get("definition"),
        "links": resource.get("links"),
    }


def build_package(
    *,
    pack,
    content_revision: str,
    lesson: dict[str, Any],
    objectives: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    resources: list[dict[str, Any]] | None = None,
    objective_associations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble one chapter's package, hash included.

    The hash is computed from the assembled content rather than passed in, so a
    caller cannot hand over a hash that does not describe what it ships with.
    """
    package = {
        "schema_version": SCHEMA_VERSION,
        "producer_version": PRODUCER_VERSION,
        "pack_slug": pack.slug,
        "pack_version": pack.version,
        "content_revision": content_revision,
        "lesson": lesson,
        "objectives": objectives,
        "objective_associations": objective_associations or [],
        "activities": activities,
        "resources": resources or [],
    }

    package["content_hash"] = content_hash(package)

    return package


def structural_problems(package: dict[str, Any]) -> list[str]:
    """Everything that would stop Ela accepting this, with the path to each.

    Returns paths rather than a boolean, because "the package is bad" is not
    actionable and "activities.1 aligns to objective 'convert' which the package
    does not define" tells whoever fixes it what to do.
    """
    problems: list[str] = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in package:
            problems.append(f"missing {field}")

    objective_keys: set[str] = set()

    for index, objective in enumerate(package.get("objectives") or []):
        path = f"objectives.{index}"
        key = str(objective.get("stable_key") or "").strip()

        if not key:
            problems.append(f"{path} has no stable_key")
        elif key in objective_keys:
            # Collapsing duplicates into a set hid this. Two objectives sharing
            # a key leave the importer no way to decide which one an alignment
            # or an upsert means.
            problems.append(f"{path} repeats stable_key {key!r}")
        else:
            objective_keys.add(key)

        if not str(objective.get("statement") or "").strip():
            problems.append(f"{path} has no statement")

        problems.extend(_provenance_problems(objective.get("provenance"), path))

    problems.extend(_association_problems(package, objective_keys))

    resource_keys: set[str] = set()

    for index, resource in enumerate(package.get("resources") or []):
        path = f"resources.{index}"
        key = str(resource.get("stable_key") or "").strip()

        if not key:
            problems.append(f"{path} has no stable_key")
        elif key in resource_keys:
            problems.append(f"{path} repeats stable_key {key!r}")
        else:
            resource_keys.add(key)

        problems.extend(_resource_problems(resource, path, package))

    activity_keys: set[str] = set()

    for index, activity in enumerate(package.get("activities") or []):
        path = f"activities.{index}"
        key = str(activity.get("stable_key") or "").strip()

        if key and key in activity_keys:
            problems.append(f"{path} repeats stable_key {key!r}")
        elif key:
            activity_keys.add(key)

        problems.extend(_activity_problems(activity, path, objective_keys, resource_keys))

    return problems


def _association_problems(package: dict[str, Any], objective_keys: set[str]) -> list[str]:
    """The objective graph: how objectives relate to each other.

    Distinct from an activity's alignments, which say what an activity assesses.
    This says one objective requires or builds on another — the structure a
    later batch reads to decide what a learner is ready for.
    """
    problems: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for index, association in enumerate(package.get("objective_associations") or []):
        path = f"objective_associations.{index}"
        source = str((association or {}).get("from_objective_stable_key") or "").strip()
        target = str((association or {}).get("to_objective_stable_key") or "").strip()
        kind = str((association or {}).get("association_type") or "").strip()

        for label, key in (("from", source), ("to", target)):
            if not key:
                problems.append(f"{path} has no {label}_objective_stable_key")
            elif key not in objective_keys:
                problems.append(f"{path}.{label} names {key!r}, which this package does not define")

        if kind not in OBJECTIVE_ASSOCIATION_TYPES:
            problems.append(
                f"{path}.association_type {kind!r} is not one of {', '.join(OBJECTIVE_ASSOCIATION_TYPES)}"
            )

        if source and source == target:
            problems.append(f"{path} relates {source!r} to itself")

        signature = (source, target, kind)

        if signature in seen:
            problems.append(f"{path} repeats the association {source!r} -{kind}-> {target!r}")

        seen.add(signature)

    return problems


def _resource_problems(resource: dict[str, Any], path: str, package: dict[str, Any]) -> list[str]:
    """A resource as Ela's own contract requires it, not as this package finds convenient."""
    problems: list[str] = []
    definition = resource.get("definition")

    if not isinstance(definition, dict):
        return problems + [f"{path}.definition is missing"]

    for field in ("contract", "resource_type", "title", "domain"):
        if not str(definition.get(field) or "").strip():
            problems.append(f"{path}.definition.{field} is missing")

    problems.extend(_provenance_problems(definition.get("provenance"), f"{path}.definition"))

    blocks = ((definition.get("definition") or {}).get("blocks")) or []

    if not blocks:
        problems.append(f"{path}.definition.definition.blocks is empty")

    for block_index, block in enumerate(blocks):
        block_path = f"{path}.definition.definition.blocks.{block_index}"

        if not isinstance(block, dict):
            problems.append(f"{block_path} is not an object")
            continue

        problems.extend(_provenance_problems(block.get("provenance"), block_path))

    links = resource.get("links") or []

    if not links:
        problems.append(f"{path}.links is empty; a resource nothing links to reaches no learner")

    lesson_key = str((package.get("lesson") or {}).get("stable_key") or "").strip()

    for link_index, link in enumerate(links):
        link_path = f"{path}.links.{link_index}"

        if not isinstance(link, dict):
            problems.append(f"{link_path} is not an object")
            continue

        for field in REQUIRED_LINK_FIELDS:
            if not link.get(field):
                problems.append(f"{link_path}.{field} is missing")

        if link.get("scope") == "lesson" and str(link.get("lesson_stable_key") or "").strip() != lesson_key:
            problems.append(f"{link_path} is lesson-scoped but does not name this lesson")

        effect = link.get("assistance_effect") or {}

        # A resource that reveals strategy or answers must say what that costs,
        # or evidence produced afterwards is recorded as though it were unaided.
        if isinstance(effect, dict) and str(effect.get("type") or "").startswith("reveals"):
            if not str(effect.get("evidence_classification") or "").strip():
                problems.append(f"{link_path}.assistance_effect declares no evidence_classification")

    return problems


def _activity_problems(
    activity: dict[str, Any],
    path: str,
    objective_keys: set[str],
    resource_keys: set[str],
) -> list[str]:
    problems: list[str] = []

    if not str(activity.get("stable_key") or "").strip():
        problems.append(f"{path} has no stable_key")

    alignments = activity.get("objective_alignments") or []

    # No fallback. An activity that does not say what it assesses is not
    # assumed to assess everything in the chapter — that would publish an
    # alignment nobody authored, and evidence would be recorded against
    # objectives the activity may not touch.
    if not alignments:
        problems.append(f"{path} lists no objective_alignments")

    for alignment_index, alignment in enumerate(alignments):
        alignment_path = f"{path}.objective_alignments.{alignment_index}"
        key = str((alignment or {}).get("objective_stable_key") or "").strip()

        if not key:
            problems.append(f"{alignment_path} names no objective")
        elif key not in objective_keys:
            problems.append(f"{alignment_path} names {key!r}, which this package does not define")

        if not str((alignment or {}).get("alignment_role") or "").strip():
            problems.append(f"{alignment_path} has no alignment_role")

    for link_index, link in enumerate(activity.get("resource_links") or []):
        key = str((link or {}).get("resource_stable_key") or "").strip()

        if key not in resource_keys:
            problems.append(
                f"{path}.resource_links.{link_index} names {key!r}, which this package does not define"
            )

    problems.extend(_definition_problems(activity.get("definition"), f"{path}.definition"))

    return problems


def _definition_problems(definition: Any, path: str) -> list[str]:
    if not isinstance(definition, dict):
        return [f"{path} is missing"]

    problems: list[str] = []

    if definition.get("contract") != ACTIVITY_CONTRACT:
        problems.append(f"{path}.contract is not {ACTIVITY_CONTRACT}")

    for field in ("type", "domain", "evidence_mode", "response", "evaluation", "scheduling"):
        if not definition.get(field):
            problems.append(f"{path}.{field} is missing")

    problems.extend(_provenance_problems(definition.get("provenance"), path))

    # Blocks live INSIDE the definition, where Ela reads them. A package-only
    # arrangement beside it would be a second answer to what an activity is.
    blocks = ((definition.get("presentation") or {}).get("blocks")) or []

    if not blocks:
        problems.append(f"{path}.presentation.blocks is empty")

    for block_index, block in enumerate(blocks):
        block_path = f"{path}.presentation.blocks.{block_index}"

        if not isinstance(block, dict):
            problems.append(f"{block_path} is not an object")
            continue

        problems.extend(_provenance_problems(block.get("provenance"), block_path))

    return problems


def _provenance_problems(provenance: Any, path: str) -> list[str]:
    """Provenance is per element, because one activity is not one claim.

    An explanation lifted from the book and an example the model invented can
    sit in the same activity, and a learner deserves a system that knows which
    is which.
    """
    if not isinstance(provenance, dict):
        return [f"{path} has no provenance"]

    origin = str(provenance.get("origin") or "").strip()

    if not origin:
        return [f"{path}.provenance has no origin"]

    from lesson_provenance import INSUFFICIENT_SOURCE_EVIDENCE, REQUIRED_FIELDS

    if origin == INSUFFICIENT_SOURCE_EVIDENCE:
        return [f"{path}.provenance is insufficient_source_evidence and cannot be published"]

    if origin not in REQUIRED_FIELDS:
        return [f"{path}.provenance has unknown origin {origin!r}"]

    return [
        f"{path}.provenance is missing {field}"
        for field in REQUIRED_FIELDS[origin]
        if not provenance.get(field) and provenance.get(field) != []
    ]
