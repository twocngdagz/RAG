"""What RAG hands Ela: one lesson, versioned, hashed, and traceable.

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

The CONTENT HASH is separate from all four, and covers only the semantic
content — the objectives, activities and resources a learner would meet. Rerun
the producer with no change to the material and the hash is identical, so an
importer can tell "generated again" from "genuinely different". Change a word a
learner reads and it moves. Change the producer's own version and it does not:
that is a fact about the tool, not about the lesson.

Provenance is required on every generated teaching element rather than on the
package as a whole. A package is not one claim; it is many, and they do not all
come from the same place. An explanation grounded in the source and an example
the model invented are different things, and a learner deserves a system that
knows which is which.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# The shape of the file. Bump when a reader would have to parse it differently.
SCHEMA_VERSION = "learning.package.v1"

# The code that emits it. Bump when the emitter's behaviour changes.
PRODUCER_VERSION = "rag-lesson-package/1.0.0"

# Every element a learner could read must say where it came from. These mirror
# `ORIGINS` in book_learning_materials_contract, because a package that invented
# its own provenance vocabulary would be describing something the rest of the
# pipeline cannot check.
REQUIRED_PROVENANCE_FIELDS = ("origin", "generated_by")

# The parts of a package that carry teaching a learner would meet. Anything
# listed here needs provenance on every entry.
TEACHING_COLLECTIONS = ("objectives", "activities", "resources")


def content_hash(package: dict[str, Any]) -> str:
    """The SHA-256 of what a learner would meet, and nothing else.

    Canonicalised — sorted keys, no incidental whitespace — so two runs that
    produced the same material agree regardless of dict ordering. Only the
    semantic content is covered: emitting the same lesson from a newer producer
    must not look like a new lesson, because for the learner it is not one.
    """
    semantic = {key: package.get(key, []) for key in TEACHING_COLLECTIONS}
    semantic["lesson_key"] = package.get("lesson_key")

    canonical = json.dumps(semantic, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_package(
    *,
    lesson_key: str,
    pack,
    content_revision: str,
    objectives: list[dict[str, Any]],
    activities: list[dict[str, Any]],
    resources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble one lesson package, hash included.

    The hash is computed from the assembled content rather than passed in, so a
    caller cannot hand over a hash that does not describe what it ships with.
    """
    package = {
        "schema_version": SCHEMA_VERSION,
        "producer_version": PRODUCER_VERSION,
        "pack_slug": pack.slug,
        "pack_version": pack.version,
        "content_revision": content_revision,
        "lesson_key": lesson_key,
        "objectives": objectives,
        "activities": activities,
        "resources": resources or [],
    }

    package["content_hash"] = content_hash(package)

    return package


def missing_provenance(package: dict[str, Any]) -> list[str]:
    """Every teaching element that cannot say where it came from.

    Returns paths rather than a boolean, because "the package is bad" is not
    actionable and "activities.1.blocks.0 has no origin" is. An empty list means
    every element is accounted for.
    """
    problems: list[str] = []

    for collection in TEACHING_COLLECTIONS:
        for index, element in enumerate(package.get(collection) or []):
            path = f"{collection}.{index}"

            if not isinstance(element, dict):
                problems.append(f"{path} is not an object")
                continue

            problems.extend(_provenance_problems(element.get("provenance"), path))

            # Blocks carry their own provenance: one activity can mix an
            # explanation from the source with an example the model wrote.
            for block_index, block in enumerate(element.get("blocks") or []):
                block_path = f"{path}.blocks.{block_index}"

                if not isinstance(block, dict):
                    problems.append(f"{block_path} is not an object")
                    continue

                problems.extend(_provenance_problems(block.get("provenance"), block_path))

    return problems


def _provenance_problems(provenance: Any, path: str) -> list[str]:
    if not isinstance(provenance, dict):
        return [f"{path} has no provenance"]

    return [
        f"{path}.provenance is missing {field}"
        for field in REQUIRED_PROVENANCE_FIELDS
        if not str(provenance.get(field) or "").strip()
    ]
