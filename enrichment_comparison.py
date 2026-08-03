"""Enrichment never erases — checked, not hoped.

More examples, more explanation, another illustration: enrichment ADDS. That is
a claim about a re-export, and a claim is worth what the check behind it is
worth, so a re-export compares the new package to the old by element identity
and prints what changed:

    43 exercises, 35 blocks -> 44 exercises, 36 blocks     "2 added, 0 removed"

Anything removed refuses to ship as an enrichment. A removal may be perfectly
correct — an example that taught a wrong method has to go — but then it is an
EDIT, and an edit is named by whoever makes it. The difference matters because
Ela re-imports an enrichment as a revision without a second thought, and content
disappearing under that banner is exactly the failure nobody would notice.

WHAT AN ELEMENT'S IDENTITY IS. Where the author gave a thing a stable key — a
concept, an exercise, a resource, an asset — that key is its identity, and
changing what is inside it is a revision of that element rather than a removal.
Teaching-document blocks have no author-given key, so a block is identified by
what it SAYS. That is the strict choice, and deliberately: it means swapping one
worked example for another is caught as a removal instead of hiding inside a
preserved position, and it means rewording a paragraph must be declared as an
edit. Rewording is an edit; the rule loses nothing by saying so.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class PreviousPackageIncomparable(Exception):
    """The old package cannot be diffed against the new one, and why."""


class EnrichmentRemovedContent(Exception):
    """A re-export claiming to be an enrichment dropped something."""


def elements(package: dict[str, Any]) -> dict[str, str]:
    """Every addressable element of a package: identity -> what it is, for a human.

    The description is for the refusal message. Whoever is told "1 removed"
    needs to know WHICH one, and an identity like a content digest tells them
    nothing on its own.
    """
    found: dict[str, str] = {}

    for block in (package.get("teaching_document") or {}).get("blocks") or []:
        section = block.get("section") or "teaching"
        found[f"teaching_document/{section}/{_digest(block.get('content'))}"] = (
            f"{block.get('key')} ({_describe(block.get('content'))})"
        )

    for concept in package.get("concepts") or []:
        key = str(concept.get("stable_key") or "").strip()
        found[f"concepts/{key}"] = f"concept {concept.get('statement') or key}"

        for exercise in concept.get("exercises") or []:
            exercise_key = str(exercise.get("stable_key") or "").strip()
            found[f"concepts/{key}/exercises/{exercise_key}"] = f"exercise {exercise_key}"

    for resource in package.get("resources") or []:
        key = str(resource.get("stable_key") or "").strip()
        found[f"resources/{key}"] = f"resource {key}"

        for block in ((resource.get("definition") or {}).get("definition") or {}).get("blocks") or []:
            found[f"resources/{key}/blocks/{_digest(block.get('content'))}"] = (
                f"{key} block ({_describe(block.get('content'))})"
            )

    for asset in package.get("assets") or []:
        key = str(asset.get("stable_key") or "").strip()
        found[f"assets/{key}"] = f"asset {key} ({asset.get('caption') or asset.get('alt_text')})"

    for association in package.get("objective_associations") or []:
        signature = "|".join(
            str(association.get(field) or "")
            for field in ("from_objective_stable_key", "association_type", "to_objective_stable_key")
        )
        found[f"objective_associations/{signature}"] = f"association {signature}"

    return found


def compare(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """What the re-export added and what it dropped."""
    _assert_comparable(previous, current)

    before = elements(previous)
    after = elements(current)

    return {
        "added": [after[identity] for identity in sorted(set(after) - set(before))],
        "removed": [before[identity] for identity in sorted(set(before) - set(after))],
    }


def summary(report: dict[str, Any]) -> str:
    """The sentence a re-export prints."""
    return f"{len(report['added'])} added, {len(report['removed'])} removed"


def assert_additive(report: dict[str, Any]) -> None:
    """Refuse a re-export that calls itself an enrichment and removes something."""
    removed = report.get("removed") or []

    if not removed:
        return

    raise EnrichmentRemovedContent(
        "this is not an enrichment: "
        + summary(report)
        + ".\n  "
        + "\n  ".join(f"removed: {description}" for description in removed)
        + "\n  An enrichment adds. Removing content is an edit, and an edit is named by "
        "whoever makes it — re-run declaring it as one."
    )


def _assert_comparable(previous: dict[str, Any], current: dict[str, Any]) -> None:
    previous_schema = str(previous.get("schema_version") or "").strip()
    current_schema = str(current.get("schema_version") or "").strip()

    if previous_schema != current_schema:
        raise PreviousPackageIncomparable(
            f"the previous package is {previous_schema or 'unversioned'!r} and this one is "
            f"{current_schema or 'unversioned'!r}; a format change is not an enrichment, and "
            f"diffing across it would report the whole old lesson as removed"
        )

    previous_lesson = (previous.get("lesson") or {}).get("stable_key")
    current_lesson = (current.get("lesson") or {}).get("stable_key")

    if previous_lesson != current_lesson:
        raise PreviousPackageIncomparable(
            f"the previous package is lesson {previous_lesson!r} and this one is "
            f"{current_lesson!r}; these are different lessons"
        )


def _digest(content: Any) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _describe(content: Any) -> str:
    """The first readable thing in a block, so a refusal names what went missing."""
    if isinstance(content, dict):
        for value in content.values():
            if isinstance(value, str) and value.strip():
                return value.strip()[:60]

            if isinstance(value, list) and value and isinstance(value[0], str):
                return value[0].strip()[:60]

    return "no readable text"
