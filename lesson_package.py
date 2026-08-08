"""What RAG hands Ela: one lesson per chapter, whole, versioned, hashed, traceable.

Nothing here reaches a learner. This is the envelope — Ela imports it, and only
then does anything become visible. The package exists so that what was generated
can be identified later: which producer made it, under which pack's rules, from
which source revision, and whether the content has changed since.

v2 CARRIES THE WHOLE LESSON. v1 shipped whichever chapter claims a manifest
named, arranged as a couple of activities. That is a sample of a lesson, not a
lesson. v2 carries what a classroom carries:

    teaching_document  the taught thing, as ordered blocks — the method, each
                       concept explained, every worked example with its
                       decoding, plan and annotations, the mistakes to avoid,
                       and where a concept has a class lesson, its goal,
                       techniques and worked examples, each block naming the
                       concept it belongs to
    concepts           the masterable abilities this lesson introduces. A
                       concept IS the objective: one entity, one statement,
                       authored once. It is also the schedulable card.
    exercises          each concept's question bank, inside the concept, so a
                       returning card can ask a different question each time
    assets             the pictures, inside the file — SVG as text, everything
                       else as base64
    resources          material declared reusable, with its link semantics

Four versions travel with every package, and they answer different questions:

    schema_version   what SHAPE this file is, so a reader knows how to parse it
    producer_version what CODE emitted it, so a bad run is identifiable
    pack_version     which RULES it was written under, so a lesson emitted last
                     month is not silently assumed to match today's
    content_revision which REVISION of the source material it came from

THE CONTENT HASH COVERS THE FILE, EVERY BYTE OF IT. Not a projection of selected
identity fields, as v1 hashed: the whole teaching document, every concept and
every exercise in its bank, the objective graph, the resources, and every byte
of every asset — which is why "N added, 0 removed" covers pictures too. Nothing
is excluded but the hash itself.

v1 kept the envelope out so that a producer bump would not look like new
content. That could not survive contact with a package that carries provenance:
an assembled resource records which code assembled it, so the producer's version
is INSIDE the content whether the envelope is hashed or not, and an exclusion
list that leaks is worse than none. The whole file it is. Two different
questions now have two different answers, which is the honest split: the hash
says whether this is the same FILE, and the enrichment comparison says whether
this is the same LESSON.

Exercises carry COMPLETE `learning.activity.v1` definitions. Ela validates and
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
SCHEMA_VERSION = "learning.package.v2"

# The code that emits it. Bump when the emitter's behaviour changes.
PRODUCER_VERSION = "rag-lesson-package/2.0.0"

ACTIVITY_CONTRACT = "learning.activity.v1"

# Ela's vocabulary for how one objective relates to another. Mirrored, and a
# test asserts the mirror holds. A concept IS an objective, so these relate
# concepts — there is no second graph and no second vocabulary.
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
    "competency_framework",
    "teaching_document",
    "concepts",
    "objective_associations",
    "resources",
    "assets",
)

# The only field outside the fingerprint, and only because a value cannot
# contain its own hash. Stated as an EXCLUSION so that a field added to the
# package later is covered by default: the opposite would let new content escape
# the hash silently, which is the one mistake this hash exists to make
# impossible.
UNFINGERPRINTED_FIELDS = ("content_hash",)


class PackageRefused(Exception):
    """The material cannot be emitted as a package, and why."""


def content_hash(package: dict[str, Any]) -> str:
    """The SHA-256 of the package, every byte of it.

    Key order is canonicalised so re-serialising the same package cannot move the
    hash; LIST order is not, because the order blocks and exercises come in is
    part of what the lesson teaches.
    """
    fingerprinted = {
        field: value for field, value in package.items() if field not in UNFINGERPRINTED_FIELDS
    }

    canonical = json.dumps(fingerprinted, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_package(
    *,
    pack,
    content_revision: str,
    lesson: dict[str, Any],
    teaching_document: dict[str, Any],
    concepts: list[dict[str, Any]],
    resources: list[dict[str, Any]] | None = None,
    objective_associations: list[dict[str, Any]] | None = None,
    competency_framework: dict[str, Any] | None = None,
    assets: list[dict[str, Any]] | None = None,
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
        # Which framework these concepts belong to. Carried at the top level
        # because it describes the whole set, not any one of them.
        "competency_framework": competency_framework or {},
        "teaching_document": teaching_document,
        "concepts": concepts,
        "objective_associations": objective_associations or [],
        "resources": resources or [],
        "assets": assets or [],
    }

    package["content_hash"] = content_hash(package)

    return package


def structural_problems(package: dict[str, Any]) -> list[str]:
    """Everything that would stop Ela accepting this, with the path to each.

    Returns paths rather than a boolean, because "the package is bad" is not
    actionable and "concepts.1.exercises.0 aligns to objective 'convert' which
    this package does not define" tells whoever fixes it what to do.
    """
    problems: list[str] = []

    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in package:
            problems.append(f"missing {field}")

    concept_keys, exercise_keys, concept_problems = _concept_problems(package)
    problems.extend(concept_problems)

    problems.extend(_teaching_document_problems(package.get("teaching_document"), concept_keys))
    problems.extend(_association_problems(package, concept_keys))

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

    # Resolved after the collections above, because an asset says what it
    # illustrates and that has to be something this package actually contains.
    problems.extend(
        _asset_problems(
            package,
            addressable=concept_keys
            | exercise_keys
            | resource_keys
            | _teaching_block_keys(package)
            | {str((package.get("lesson") or {}).get("stable_key") or "").strip()},
        )
    )

    problems.extend(_illustration_problems(package))

    problems.extend(_exercise_link_problems(package, resource_keys))

    return problems


def _concept_problems(package: dict[str, Any]) -> tuple[set[str], set[str], list[str]]:
    """A concept is an objective, a card, and a question bank — all three or none."""
    problems: list[str] = []
    concept_keys: set[str] = set()
    exercise_keys: set[str] = set()

    concepts = package.get("concepts") or []

    if not concepts:
        problems.append("concepts is empty; a lesson that introduces nothing teaches nothing")

    for index, concept in enumerate(concepts):
        path = f"concepts.{index}"
        key = str(concept.get("stable_key") or "").strip()

        if not key:
            problems.append(f"{path} has no stable_key")
        elif key in concept_keys:
            # Two concepts sharing a key leave the importer no way to decide
            # which card an alignment or an upsert means.
            problems.append(f"{path} repeats stable_key {key!r}")
        else:
            concept_keys.add(key)

        # The statement is the objective, written once. It is what a learner is
        # told they will be able to do and what mastery is claimed about.
        if not str(concept.get("statement") or "").strip():
            problems.append(f"{path} has no statement")

        if not str(concept.get("objective_type") or "").strip():
            problems.append(f"{path} has no objective_type")

        problems.extend(_provenance_problems(concept.get("provenance"), path))

        if not concept.get("exercises"):
            problems.append(
                f"{path} has no exercises; a concept card with an empty bank can never be asked"
            )

        for exercise_index, exercise in enumerate(concept.get("exercises") or []):
            exercise_path = f"{path}.exercises.{exercise_index}"
            exercise_key = str(exercise.get("stable_key") or "").strip()

            if exercise_key and exercise_key in exercise_keys:
                problems.append(f"{exercise_path} repeats stable_key {exercise_key!r}")
            elif exercise_key:
                exercise_keys.add(exercise_key)

    # Alignments are checked in a second pass, because an exercise may legitimately
    # align to a concept declared after it — the capstone exception.
    for index, concept in enumerate(package.get("concepts") or []):
        for exercise_index, exercise in enumerate(concept.get("exercises") or []):
            problems.extend(
                _exercise_problems(
                    exercise,
                    f"concepts.{index}.exercises.{exercise_index}",
                    concept_keys,
                )
            )

    return concept_keys, exercise_keys, problems


def _teaching_document_problems(document: Any, concept_keys: set[str]) -> list[str]:
    """The taught thing, in order, with every block saying where it came from."""
    if not isinstance(document, dict):
        return ["teaching_document is missing"]

    problems: list[str] = []
    blocks = document.get("blocks") or []

    if not blocks:
        return problems + ["teaching_document.blocks is empty; the lesson teaches nothing"]

    if not str(document.get("generator_version") or "").strip():
        problems.append("teaching_document names no generator_version")

    seen: set[str] = set()

    for index, block in enumerate(blocks):
        path = f"teaching_document.blocks.{index}"

        if not isinstance(block, dict):
            problems.append(f"{path} is not an object")
            continue

        key = str(block.get("key") or "").strip()

        if not key:
            problems.append(f"{path} has no key")
        elif key in seen:
            problems.append(f"{path} repeats key {key!r}")
        else:
            seen.add(key)

        for field in ("type", "section", "content"):
            if not block.get(field):
                problems.append(f"{path}.{field} is missing")

        # Position is asserted rather than assumed. A block list that arrived
        # re-sorted would teach in an order nobody authored.
        if block.get("position") != index:
            problems.append(f"{path}.position is {block.get('position')!r}, not {index}")

        # A block may teach ONE concept rather than the chapter at large — a
        # class lesson's blocks do. The consumer selects teaching by `teaches`;
        # if the block says so, the concept has to be one this package defines:
        # teaching filed under a card that is not here is met by nobody, and
        # the package would import without complaint.
        if "teaches" in block:
            concept = str(block.get("teaches") or "").strip()

            if not concept:
                problems.append(f"{path}.teaches is empty")
            elif concept not in concept_keys:
                problems.append(
                    f"{path} belongs to concept {concept!r}, which this package does not define"
                )

        problems.extend(_provenance_problems(block.get("provenance"), path))

    return problems


def _teaching_block_keys(package: dict[str, Any]) -> set[str]:
    return {
        str(block.get("key") or "").strip()
        for block in ((package.get("teaching_document") or {}).get("blocks") or [])
        if isinstance(block, dict)
    }


def _asset_problems(package: dict[str, Any], *, addressable: set[str]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()

    for index, asset in enumerate(package.get("assets") or []):
        path = f"assets.{index}"

        if not isinstance(asset, dict):
            problems.append(f"{path} is not an object")
            continue

        key = str(asset.get("stable_key") or "").strip()

        if not key:
            problems.append(f"{path} has no stable_key")
        elif key in seen:
            problems.append(f"{path} repeats stable_key {key!r}")
        else:
            seen.add(key)

        for field in ("media_type", "encoding", "alt_text", "caption"):
            if not str(asset.get(field) or "").strip():
                problems.append(f"{path}.{field} is missing")

        # The picture itself rides in the field its encoding names — an inline
        # SVG in `svg`, encoded bytes in `content` — so which field must be
        # there is read off the encoding rather than fixed here.
        from lesson_assets import PAYLOAD_FIELD

        payload = PAYLOAD_FIELD.get(str(asset.get("encoding") or "").strip())

        if payload and not str(asset.get(payload) or "").strip():
            problems.append(f"{path}.{payload} is missing")

        illustrates = str(asset.get("illustrates") or "").strip()

        if not illustrates:
            problems.append(f"{path} does not say what it illustrates")
        elif illustrates not in addressable:
            problems.append(
                f"{path} illustrates {illustrates!r}, which this package does not contain"
            )

        problems.extend(_provenance_problems(asset.get("provenance"), path))

    return problems


def _illustration_problems(package: dict[str, Any]) -> list[str]:
    """A block that shows a picture must name one this package carries.

    An illustration block pointing at an asset that is not in the file is a hole
    in the lesson that only appears when a learner reaches it — the package
    imports cleanly and the picture is simply never there. So the reference is
    resolved here, where it is still an export refusal.
    """
    from teaching_document import ILLUSTRATION_BLOCK_TYPE

    problems: list[str] = []
    assets = {str(asset.get("stable_key") or "").strip() for asset in package.get("assets") or []}

    for index, block in enumerate((package.get("teaching_document") or {}).get("blocks") or []):
        if not isinstance(block, dict) or block.get("type") != ILLUSTRATION_BLOCK_TYPE:
            continue

        path = f"teaching_document.blocks.{index}"
        content = block.get("content") or {}
        key = str(content.get("asset_stable_key") or "").strip()

        if not key:
            problems.append(f"{path} shows a picture but names no asset_stable_key")
        elif key not in assets:
            problems.append(f"{path} shows {key!r}, which this package does not carry")

        # Restated on the block as well as on the asset: what a learner reads
        # under the picture travels with the block that renders it.
        for field in ("caption", "alt_text"):
            if not str(content.get(field) or "").strip():
                problems.append(f"{path}.content.{field} is missing")

    return problems


def _association_problems(package: dict[str, Any], concept_keys: set[str]) -> list[str]:
    """The objective graph: how one concept relates to another.

    Distinct from an exercise's alignments, which say what it assesses. This says
    one concept requires or builds on another — the structure a later batch reads
    to decide what a learner is ready for.
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
            elif key not in concept_keys:
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


def _exercise_link_problems(package: dict[str, Any], resource_keys: set[str]) -> list[str]:
    problems: list[str] = []

    for index, concept in enumerate(package.get("concepts") or []):
        for exercise_index, exercise in enumerate(concept.get("exercises") or []):
            path = f"concepts.{index}.exercises.{exercise_index}"

            for link_index, link in enumerate(exercise.get("resource_links") or []):
                key = str((link or {}).get("resource_stable_key") or "").strip()

                if key not in resource_keys:
                    problems.append(
                        f"{path}.resource_links.{link_index} names {key!r}, "
                        f"which this package does not define"
                    )

    return problems


def _exercise_problems(
    exercise: dict[str, Any],
    path: str,
    concept_keys: set[str],
) -> list[str]:
    problems: list[str] = []

    if not str(exercise.get("stable_key") or "").strip():
        problems.append(f"{path} has no stable_key")

    alignments = exercise.get("objective_alignments") or []

    # No fallback. An exercise that does not say what it assesses is not assumed
    # to assess everything in the chapter — that would publish an alignment
    # nobody authored, and evidence would be recorded against concepts the
    # exercise may not touch.
    if not alignments:
        problems.append(f"{path} lists no objective_alignments")

    for alignment_index, alignment in enumerate(alignments):
        alignment_path = f"{path}.objective_alignments.{alignment_index}"
        key = str((alignment or {}).get("objective_stable_key") or "").strip()

        if not key:
            problems.append(f"{alignment_path} names no objective")
        elif key not in concept_keys:
            problems.append(f"{alignment_path} names {key!r}, which this package does not define")

        if not str((alignment or {}).get("alignment_role") or "").strip():
            problems.append(f"{alignment_path} has no alignment_role")

    problems.extend(_definition_problems(exercise.get("definition"), f"{path}.definition"))

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
    """Provenance is per element, because one lesson is not one claim.

    An explanation lifted from the book, an example the model invented, and a
    question a generator computed can sit in the same lesson, and a learner
    deserves a system that knows which is which.
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
