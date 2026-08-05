"""A concept's question bank: the exercises it asks, and how each one is marked.

A concept is the schedulable card, and a card that returns asks a DIFFERENT
question each time — otherwise a learner practises remembering one answer rather
than the method. So a concept ships with a bank, not a question, and the bank is
part of the package rather than something Ela composes later.

The exercises come from `math_practice_items`, where the answers are worked out
by exact rational arithmetic rather than by a model. That is why this bank can
carry a deterministic marking contract at all: the expected answer is computed,
independently re-derived from the item's own `check_expr`, and shipped as fact.

WHAT IS DECLARED AND WHAT IS TRANSFORMED. The manifest declares which skill a
concept's bank draws from and how its exercises are delivered — the activity
type, the evidence mode, the marker, the scheduling. This module transforms:
it selects the declared skill's items, refuses any that belong to another
chapter, and translates each item's computed answer into the marker's fields.
It never decides what a question assesses; putting an item in a concept's bank
IS the author saying so, and the alignment is emitted from that.
"""

from __future__ import annotations

from typing import Any

import lesson_package
import lesson_provenance
import math_practice_items

# Where a bank may come from. One name, checked, because "source": "items" that
# silently produced nothing would ship a concept with an empty bank.
BANK_SOURCES = ("math_practice_items",)

# What a bank must declare before its exercises can be delivered. Same fields an
# activity has always required: whether a response is collected, how it is
# marked, and how it is scheduled are teaching decisions, never defaults.
REQUIRED_BANK_FIELDS = ("source", "skill", "type", "evidence_mode", "response", "evaluation", "scheduling")


class BankRefused(Exception):
    """A concept's bank cannot be assembled, and why."""


def build(
    *,
    concept: dict[str, Any],
    chapter_number: int,
    lesson_stable_key: str,
    items: list[dict[str, Any]],
    pack,
    path: str,
) -> list[dict[str, Any]]:
    """Every exercise in one concept's bank, in a stable order."""
    declared = concept.get("bank") or {}
    skill = str(declared.get("skill") or "").strip()

    selected = [item for item in items if str(item.get("skill") or "").strip() == skill]

    if not selected:
        raise BankRefused(
            f"{path}.bank draws on skill {skill!r}, which the item bank has no questions for; "
            f"a concept with no exercises is a card that can never be asked"
        )

    wrong_chapter = sorted({item.get("chapter") for item in selected if item.get("chapter") != chapter_number})

    if wrong_chapter:
        raise BankRefused(
            f"{path}.bank draws on skill {skill!r}, whose questions belong to chapter "
            f"{', '.join(str(number) for number in wrong_chapter)} rather than {chapter_number}"
        )

    # Sorted by the generator's own id, so the same bank exports in the same
    # order every run. Bank order is not teaching order — a returning card draws
    # from it — but a package that reshuffled itself between runs would look
    # like new material to an importer on every export.
    return [
        _exercise(
            item=item,
            declared=declared,
            concept=concept,
            lesson_stable_key=lesson_stable_key,
            pack=pack,
            path=f"{path}.bank.{index}",
        )
        for index, item in enumerate(sorted(selected, key=lambda item: str(item.get("id") or "")))
    ]


def problems(declared: Any, path: str) -> list[str]:
    """Everything a bank declaration fails to say, with the path to each gap."""
    if not isinstance(declared, dict):
        return [f"{path}.bank is missing; a concept without one is a card with nothing to ask"]

    found = [f"{path}.bank.{field} is missing" for field in REQUIRED_BANK_FIELDS if not declared.get(field)]

    source = str(declared.get("source") or "").strip()

    if source and source not in BANK_SOURCES:
        found.append(f"{path}.bank.source {source!r} is not one of {', '.join(BANK_SOURCES)}")

    marking = (declared.get("evaluation") or {}).get("marking") or {}

    if (declared.get("evaluation") or {}).get("authority") == "deterministic" and not marking.get("marker"):
        found.append(f"{path}.bank.evaluation.marking names no marker, so nothing can mark an answer")

    return found


def _exercise(
    *,
    item: dict[str, Any],
    declared: dict[str, Any],
    concept: dict[str, Any],
    lesson_stable_key: str,
    pack,
    path: str,
) -> dict[str, Any]:
    prompt = str(item.get("prompt") or "").strip()

    if not prompt:
        raise BankRefused(f"{path} -> item {item.get('id')!r} has no question a learner could read")

    provenance = {
        "origin": lesson_provenance.PEDAGOGICAL_GENERATION,
        # Deliberately empty, and honest. The SKILL comes from the chapter; these
        # particular numbers were produced by a parametric generator and rest on
        # no passage of the book. Naming chunks here would claim the book asks
        # this question, which it does not.
        "grounded_in_source_chunk_ids": [],
        "generation_reason": (
            f"Parametric practice for {item.get('skill_title') or item.get('skill')}; "
            f"the answer is computed by exact rational arithmetic, not by a model"
        ),
        "generator_version": math_practice_items.GENERATOR_VERSION,
    }

    definition = {
        "contract": lesson_package.ACTIVITY_CONTRACT,
        "type": declared["type"],
        "type_version": declared.get("type_version", 1),
        "domain": declared.get("domain", pack.slug),
        "evidence_mode": declared["evidence_mode"],
        "answer_visibility": declared.get("answer_visibility", "after_submission"),
        "presentation": {
            "blocks": [
                {
                    "type": "text",
                    "version": 1,
                    "content": {"key": "question", "text": prompt},
                    "provenance": provenance,
                }
            ]
        },
        "response": declared["response"],
        "evaluation": _evaluation(declared["evaluation"], item, path),
        "scheduling": declared["scheduling"],
        "provenance": provenance,
    }

    if declared.get("guidance"):
        definition["presentation"]["guidance"] = declared["guidance"]

    return {
        "stable_key": f"{lesson_stable_key}:{item['id']}",
        # Containment IS the alignment: the author put this question in this
        # concept's bank. Emitting it keeps Ela's alignment machinery intact and
        # leaves room for the capstone exception, where a manifest declares
        # extra objectives an exercise also feeds.
        "objective_alignments": [
            {
                "objective_stable_key": concept["stable_key"],
                "alignment_role": declared.get("alignment_role", "assesses"),
            },
            *(declared.get("also_aligns_to") or []),
        ],
        "resource_links": declared.get("resource_links", []),
        "definition": definition,
    }


def _evaluation(declared: dict[str, Any], item: dict[str, Any], path: str) -> dict[str, Any]:
    """The declared marking contract, with this item's computed answer filled in.

    The marker and the form an answer must take are the author's decisions and
    are copied through. What the answer IS was worked out by the generator, so
    it is carried as fact rather than restated by a person who might mistype it.
    """
    if declared.get("authority") != "deterministic":
        return declared

    kind = str(item.get("answer_kind") or "").strip()

    if kind not in ("number", "ratio"):
        raise BankRefused(
            f"{path} -> item {item.get('id')!r} answers with {kind!r}, which the numeric marker "
            f"cannot express; a question nothing can mark produces no evidence"
        )

    expected: dict[str, Any] = {
        "kind": kind,
        "plain": str(item.get("answer_plain") or "").strip(),
        "tex": str(item.get("answer_tex") or "").strip(),
        "numerator": item.get("answer_num"),
        "denominator": item.get("answer_den"),
    }

    if kind == "ratio":
        expected["ratio"] = list(item.get("answer_ratio") or [])

    if not expected["plain"]:
        raise BankRefused(f"{path} -> item {item.get('id')!r} carries no answer to mark against")

    marking = {**(declared.get("marking") or {}), "expected": expected}

    # The item's own second opinion: the sum that produces the answer, worked out
    # by a different implementation from the one that generated it. Carried so a
    # reader can re-derive the answer rather than trust it.
    if str(item.get("check_expr") or "").strip():
        marking["verified_by"] = str(item["check_expr"]).strip()

    return {**declared, "marking": marking}
