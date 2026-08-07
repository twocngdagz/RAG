"""A DRAFT lesson plan for a chapter, for a person to read, correct and approve.

WHAT A LESSON PLAN IS DERIVED FROM. The chapter's enrichment — the class material
an external generator already wrote. Its `learning_goals` are what the chapter
teaches, in the chapter's own words; its `techniques` are the methods it teaches
for them; its `mastery_checklist` is what it says a learner should be able to
check. A concept's statement is that chapter's own learning goal — "You will find
the value of any digit" — and never a label from somewhere else.

The first version of this module read the exercise bank's `skill` labels instead
and proposed concepts called "Place value" and "Rounding". That threw away every
sentence the class material had written for all nine chapters and replaced it
with the bank's filing system. Nothing here writes teaching; it maps what an
external generator already wrote onto what the bank can ask.

WHAT A DRAFT IS. A proposal, and it says so in the file. Every draft is written
`"approved": false`, and the exporter refuses to publish from anything not
explicitly approved. That refusal is the point: a chapter's concepts are what a
learner's mastery is claimed about, and a machine's mapping of them must not
reach a learner because it happened to look plausible in a diff.

WHAT IT PROPOSES, AND WHAT IT LEAVES EMPTY ON PURPOSE:

    concepts        one per learning goal in the enrichment, in the enrichment's
                    own order — the chapter's teaching order
    statement       that goal, verbatim
    bank            the skill whose questions match the goal, matched by shared
                    words and reported with the words that matched. A goal with
                    no matching questions keeps its concept and gets no bank: it
                    is taught and not yet practised, and inventing questions for
                    it would be worse than saying so
    objective_type  `procedure` only where a technique in the enrichment gives an
                    ordered method for the goal, naming which technique. Absent
                    where the material does not say
    assessed        true only where the chapter's own mastery checklist claims the
                    learner is checked on it, or the bank can ask it. Absent where
                    the material does not say
    required_form   what shape a correct answer must take, read from the bank's
                    own answers (`answer_kind`, `answer_den`, whether each
                    reduces). `whole_number` when every answer is a plain number;
                    `simplest_fraction` when every answer is a reduced non-whole
                    fraction. Absent — and named in needs_review — when the
                    answers do not agree, because a wrong form marks a correct
                    learner wrong

A skill the bank can ask and no goal matched is NOT attached to whichever concept
is nearest — the draft names it as unmatched so a person sees the gap.

It proposes no resources (declaring material reusable is an authoring decision),
no diagrams (which drawing suits which example is a teaching decision), no
assets, and no `authored_by` — an empty name is what makes approval an act
rather than a default.

REVIEW LESSONS. A review teaches nothing of its own, so its draft declares no
concepts. It names the lessons it reviews, read from its own material: its
learning goals and the book's own summary of it, matched against what each
teaching chapter says it teaches.

    python draft_export_manifest.py --slug math5a --chapter 5
    python draft_export_manifest.py --slug math5a --all
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import domain_packs
import enrichment_concepts
import lesson_export_manifest as manifest_module
import math_practice_items
import teaching_document
from book_learning_materials_contract import atomic_write_json

# Drafts live one directory below the approved manifests they hope to become, so
# approving one is: read it, fix it, sign it, flip `approved`, move it up.
DRAFT_FILE = "manifests/drafts/{slug}.chapter{n:02d}.export_manifest.json"

# 2.1.0: required_form is proposed from the bank's answers. 2.0.0: concepts are
# the enrichment's learning goals. 1.0.0 read the exercise bank's skill labels.
DRAFT_GENERATOR_VERSION = "draft_export_manifest/2.1.0"

# What subject this lesson and its questions belong to, as chapter 3's approved
# manifest names it. Not the pack slug: `math5a` is which book, `math` is which
# subject, and Ela files activities under the second.
PROPOSED_DOMAIN = "math"

# The delivery and marking declaration chapter 3's approved banks carry, with the
# teaching taken out. `guidance` is a sentence telling a learner how to do the
# maths — an authoring decision this generator does not write. `required_form` is
# proposed separately from the answers themselves: copying chapter 3's
# `simplest_fraction` onto a bank of angle questions would mark a correct
# whole-number answer as the wrong shape.
BANK_TEMPLATE: dict[str, Any] = {
    "source": "math_practice_items",
    "type": "response.free_text",
    "domain": PROPOSED_DOMAIN,
    "evidence_mode": "cued_recall",
    "answer_visibility": "after_submission",
    "response": {"kind": "short_answer", "required": True},
    "evaluation": {"authority": "deterministic", "marking": {"marker": "ela.math.numeric"}},
    "scheduling": {"policy": "skill_practice", "subject": "learning_item"},
}

# Forms the answers themselves can imply. Closed, and only these two: a bank of
# plain numbers and a bank of reduced fractions. Anything else is left unset.
FORM_WHOLE_NUMBER = "whole_number"
FORM_SIMPLEST_FRACTION = "simplest_fraction"

# The one value this repository has ever emitted for it, and the only one the
# enrichment gives evidence for: a technique is an ordered method, and a goal
# carried out by one is a procedure. Where no technique matches, the field is
# left out rather than defaulted -- see the module docstring.
PROCEDURE = "procedure"

# How many ordered steps a technique needs before it counts as evidence that its
# goal is carried out by a method. One step is a remark, not a procedure.
STEPS_FOR_A_PROCEDURE = 2

# What a chapter's own material calls itself when it teaches nothing new.
REVIEW_TITLE = re.compile(r"^\s*review\b", re.IGNORECASE)

# Dropped from the front of a goal before it becomes a stable key: every goal in
# every chapter opens with it, so it identifies nothing.
GOAL_OPENER = re.compile(r"^you\s+will\s+", re.IGNORECASE)


class DraftRefused(Exception):
    """A draft cannot be written for this chapter, and why."""


def draft_path(slug: str, chapter: int) -> Path:
    return Path(DRAFT_FILE.format(slug=slug, n=chapter))


def build_draft(
    *,
    slug: str,
    chapter_number: int,
    materials: dict[str, Any],
    items: list[dict[str, Any]],
    enrichment: dict[str, Any] | None,
    pack,
    sources: dict[str, str],
    taught_chapters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One chapter's proposed lesson plan, derived from its enrichment."""
    chapter = _chapter(materials, chapter_number)
    lesson_stable_key = f"{slug}:ch{chapter_number:02d}"
    teaches = _teaching_titles(chapter)
    titled_review = bool(
        REVIEW_TITLE.match(str(chapter.get("chapter_title") or ""))
        or REVIEW_TITLE.match(str((enrichment or {}).get("lesson_title") or ""))
    )

    if titled_review and teaches:
        raise DraftRefused(
            f"chapter {chapter_number} is titled a review but its material carries "
            f"{len(teaches)} teaching lesson(s); the book's own pages disagree about what "
            f"this chapter is and this module may not pick"
        )

    if enrichment is None:
        raise DraftRefused(
            f"chapter {chapter_number} has no enrichment, and a lesson plan is derived from "
            f"one. Without it there are no learning goals to propose concepts from, and "
            f"reading the exercise bank's labels instead is the mistake this module was "
            f"rewritten to stop making"
        )

    goals = _goals(enrichment)
    review = _review_coverage(
        chapter=chapter,
        goals=goals,
        taught=taught_chapters or [],
    ) if titled_review else None

    proposals = [] if review else _proposals(
        goals=goals,
        enrichment=enrichment,
        items=items,
        chapter_number=chapter_number,
        lesson_stable_key=lesson_stable_key,
    )

    draft: dict[str, Any] = {
        "manifest_schema_version": manifest_module.MANIFEST_SCHEMA_VERSION,
        # Checked by the exporter, which refuses anything not explicitly true.
        "approved": False,
        # Filled in below, once the rest of the file exists to be checked.
        "draft": {},
        # Empty on purpose. `manually_authored` is a claim that a person wrote
        # this, and the exporter refuses to make it on nobody's behalf.
        "authored_by": "",
        "competency_framework": {
            "stable_key": f"{slug}:framework",
            "title": pack.title,
        },
        "lesson": {
            "stable_key": lesson_stable_key,
            "title": _lesson_title(chapter),
            "domain": PROPOSED_DOMAIN,
        },
        "teaching_document": {"generator_version": _generator_version(enrichment)},
        "concepts": [proposal["concept"] for proposal in proposals],
        "objective_associations": [],
        "resources": [],
        "assets": [],
        "diagrams": [],
    }

    if review:
        # Where a review's questions come from, said in the mapping rather than
        # left to the exporter: a review has no concepts of its own, and the
        # lessons it covers are the only thing that says what it can ask.
        draft["reviews"] = review["reviews"]

    draft["draft"] = _draft_note(
        slug=slug,
        chapter=chapter,
        chapter_number=chapter_number,
        enrichment=enrichment,
        proposals=proposals,
        items=items,
        review=review,
        teaches=teaches,
        sources=sources,
    )
    # The exporter's own list of what still stands between this draft and a
    # package, computed by the validator that will refuse it rather than guessed
    # at here. A draft that proposes a concept with no questions is not
    # exportable, and saying so is more useful than looking complete.
    draft["draft"]["not_exportable_until"] = manifest_module.validate(draft)

    return draft


# --------------------------------------------------------------------------- #
# Concepts, from the enrichment
# --------------------------------------------------------------------------- #

def _proposals(
    *,
    goals: list[str],
    enrichment: dict[str, Any],
    items: list[dict[str, Any]],
    chapter_number: int,
    lesson_stable_key: str,
) -> list[dict[str, Any]]:
    """One proposal per learning goal: the concept, and the evidence behind it."""
    skills = _skills_of(items, chapter_number)
    skill_vocabulary = {skill: _skill_words(items, skill) for skill in skills}
    banks = enrichment_concepts.assign(goals, skill_vocabulary)
    by_goal: dict[int, list[enrichment_concepts.Assignment]] = {}

    for assignment in banks:
        if assignment.sentence_index is not None:
            by_goal.setdefault(assignment.sentence_index, []).append(assignment)

    techniques = _technique_words(enrichment)
    checklist = _checklist_words(enrichment)
    keys = _stable_keys(goals, lesson_stable_key)
    proposals: list[dict[str, Any]] = []

    for index, goal in enumerate(goals):
        offered = sorted(
            by_goal.get(index, []),
            key=lambda assignment: (-assignment.match.score, -assignment.match.of_candidate, assignment.key),
        )
        chosen, shared_with = _one_bank(offered)
        method = enrichment_concepts.matched(goal, techniques)
        checked = enrichment_concepts.matched(goal, checklist)
        concept: dict[str, Any] = {
            "stable_key": keys[index],
            "statement": goal,
        }
        procedure = [match for match in method if _steps(enrichment, match.key) >= STEPS_FOR_A_PROCEDURE]

        if procedure:
            concept["objective_type"] = PROCEDURE

        if checked or chosen:
            concept["assessed"] = True

        form_from: dict[str, Any] | None = None

        if chosen:
            asked = [item for item in items if item.get("skill") == chosen.key]
            form, form_from = _required_form(asked)
            concept["bank"] = _bank(chosen.key, required_form=form)

        proposals.append(
            {
                "concept": concept,
                "goal_at": f"learning_goals.{index}",
                "bank_from": chosen,
                "bank_shared_with": shared_with,
                "technique_matches": procedure or method,
                "checklist_matches": checked,
                "required_form_from": form_from,
                # What it came closest to and did not take, so a reviewer fixing a
                # gap can see whether the material nearly said it or never did.
                "closest_skills": [] if chosen else enrichment_concepts.score(goal, skill_vocabulary)[:2],
                "closest_techniques": [] if procedure else enrichment_concepts.score(goal, techniques)[:1],
            }
        )

    return proposals


def _bank(skill: str, *, required_form: str | None) -> dict[str, Any]:
    """The declaration a concept's questions are delivered and marked under.

    `skill` sits second, where chapter 3's approved manifest puts it: the source
    and the skill together are what the bank IS, and the rest is contract.
    `required_form` is set only when the answers themselves imply one shape.
    """
    declared = copy.deepcopy(BANK_TEMPLATE)

    if required_form:
        declared["evaluation"]["marking"]["required_form"] = required_form

    return {"source": declared.pop("source"), "skill": skill, **declared}


def _required_form(items: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    """What shape every answer in this bank must take, read from the answers.

    Returns `(form, evidence)`. `form` is set only when every answer agrees:
    all plain numbers (`answer_den == 1`) imply `whole_number`; all reduced
    non-whole fractions imply `simplest_fraction`. Mixed kinds, mixed dens, an
    unreduced fraction, or an empty bank leave `form` unset — a wrong form marks
    a correct learner wrong, so the draft names the gap rather than guessing.
    """
    evidence: dict[str, Any] = {
        "exercises_in_bank": len(items),
        "answer_kinds": sorted({str(item.get("answer_kind") or "") for item in items}),
        "answer_dens": sorted({item.get("answer_den") for item in items}),
        "all_reduced": bool(items) and all(item.get("answer_is_reduced") for item in items),
    }

    if not items:
        evidence["why_unset"] = "the bank has no answers to read a form from"
        return None, evidence

    kinds = {str(item.get("answer_kind") or "").strip() for item in items}

    if kinds != {"number"}:
        evidence["why_unset"] = (
            f"the answers are {', '.join(sorted(kinds)) or 'untyped'}, and only a bank of "
            f"numbers can imply whole_number or simplest_fraction"
        )
        return None, evidence

    dens = {item.get("answer_den") for item in items}

    if dens == {1}:
        evidence["form"] = FORM_WHOLE_NUMBER
        evidence["because"] = "every answer has answer_den 1 — a plain number"
        return FORM_WHOLE_NUMBER, evidence

    if 1 in dens:
        evidence["why_unset"] = (
            "some answers are whole numbers (answer_den 1) and some are not, so the bank "
            "does not imply one form"
        )
        return None, evidence

    if not all(item.get("answer_is_reduced") for item in items):
        evidence["why_unset"] = (
            "at least one answer is not reduced, so simplest_fraction cannot be claimed "
            "from the bank"
        )
        return None, evidence

    evidence["form"] = FORM_SIMPLEST_FRACTION
    evidence["because"] = (
        "every answer is a non-whole number (answer_den != 1) and every one is reduced"
    )
    return FORM_SIMPLEST_FRACTION, evidence


def _one_bank(
    offered: list[enrichment_concepts.Assignment],
) -> tuple[enrichment_concepts.Assignment | None, list[enrichment_concepts.Assignment]]:
    """Which of the skills that matched this goal becomes its bank.

    A concept declares one bank. Where one skill matched the goal better than the
    rest it is the obvious one; where two matched it equally the material has not
    said which, and both are reported unattached rather than one being picked.
    """
    if not offered:
        return None, []

    if len(offered) > 1 and _tie(offered[0].match, offered[1].match):
        return None, offered

    return offered[0], offered[1:]


def _tie(first: enrichment_concepts.Match, second: enrichment_concepts.Match) -> bool:
    return (round(first.score, 6), round(first.of_candidate, 6)) == (
        round(second.score, 6),
        round(second.of_candidate, 6),
    )


def _goals(enrichment: dict[str, Any]) -> list[str]:
    goals = [
        str(goal).strip()
        for goal in enrichment.get("learning_goals") or []
        if str(goal or "").strip()
    ]

    if not goals:
        raise DraftRefused(
            "the enrichment declares no learning_goals, so there is nothing to propose "
            "concepts from; a lesson plan is derived from the chapter's own goals"
        )

    return goals


def _stable_keys(goals: list[str], lesson_stable_key: str) -> list[str]:
    """A key per goal, made from the goal's own words.

    The statement and the key come from the same sentence, so a reader can see
    that one is the other. After approval a learner's evidence is filed under the
    key and it can never move, which is why the draft asks for it to be settled.
    """
    keys = [f"{lesson_stable_key}:{_slug(goal)}" for goal in goals]
    repeated = sorted({key for key in keys if keys.count(key) > 1})

    if repeated:
        raise DraftRefused(
            f"two learning goals produce the same stable key ({', '.join(repeated)}); "
            f"two concepts cannot share the key a learner's evidence is filed under, and "
            f"choosing which goal keeps it is not this module's to do"
        )

    return keys


def _slug(goal: str) -> str:
    text = GOAL_OPENER.sub("", enrichment_concepts.LATEX.sub(" ", goal.strip().lower()))
    # An apostrophe closes a word rather than breaking it: "a triangle's base"
    # is triangles-base, not triangle-s-base.
    text = text.replace("'", "").replace("’", "")

    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def _skills_of(items: list[dict[str, Any]], chapter_number: int) -> list[str]:
    """The chapter's skills in the bank's own order."""
    found: list[str] = []

    for item in items:
        skill = str(item.get("skill") or "").strip()

        if item.get("chapter") == chapter_number and skill and skill not in found:
            found.append(skill)

    return found


def _skill_words(items: list[dict[str, Any]], skill: str) -> set[str]:
    """What a skill is about, in the words the bank uses for it.

    Its title, and the words most of its questions share. One question's ribbon
    or protractor is that question's furniture; a word half of them use is what
    the skill asks about. The skill's identifier is deliberately not read: it is
    a filing label, and reading labels is what produced concepts called "Place
    value" instead of "You will find the value of any digit".
    """
    asked = [item for item in items if item.get("skill") == skill]

    return enrichment_concepts.words(_skill_title(items, skill)) | enrichment_concepts.common_words(
        [str(item.get("prompt") or "") for item in asked]
    )


def _skill_title(items: list[dict[str, Any]], skill: str) -> str:
    for item in items:
        if item.get("skill") == skill and str(item.get("skill_title") or "").strip():
            return str(item["skill_title"]).strip()

    return skill


def _technique_words(enrichment: dict[str, Any]) -> dict[str, set[str]]:
    """Each technique's vocabulary, keyed by where it lives in the enrichment."""
    return {
        f"techniques.{index}": enrichment_concepts.words(
            technique.get("name"),
            technique.get("purpose"),
            technique.get("why_it_matters"),
            *(technique.get("how_to") or []),
        )
        for index, technique in enumerate(enrichment.get("techniques") or [])
        if isinstance(technique, dict)
    }


def _checklist_words(enrichment: dict[str, Any]) -> dict[str, set[str]]:
    return {
        f"mastery_checklist.{index}": enrichment_concepts.words(line)
        for index, line in enumerate(enrichment.get("mastery_checklist") or [])
        if str(line or "").strip()
    }


def _steps(enrichment: dict[str, Any], reference: str) -> int:
    index = int(reference.split(".")[1])
    technique = (enrichment.get("techniques") or [])[index]

    return len([step for step in technique.get("how_to") or [] if str(step or "").strip()])


def _at(enrichment: dict[str, Any], reference: str) -> str:
    """The sentence a `techniques.3`-style reference points at, for the report."""
    section, _, index = reference.partition(".")
    entry = (enrichment.get(section) or [])[int(index)]

    return str(entry.get("name") if isinstance(entry, dict) else entry or "")


# --------------------------------------------------------------------------- #
# Reviews, from the chapter's own material
# --------------------------------------------------------------------------- #

def _review_coverage(
    *,
    chapter: dict[str, Any],
    goals: list[str],
    taught: list[dict[str, Any]],
) -> dict[str, Any]:
    """Which lessons this review reviews, read from what it says it reviews.

    Its own learning goals and the book's own summary of the chapter, matched
    against what each teaching chapter says it teaches. Not a table of chapter
    numbers held somewhere else: the book's pages are what say what a review
    covers, and a table is a shape somebody chose.
    """
    candidates = {
        chapter_entry["lesson_stable_key"]: enrichment_concepts.words(
            chapter_entry["title"], *chapter_entry["goals"]
        )
        for chapter_entry in taught
    }
    summary = str(((chapter.get("chapter_summary") or {}).get("text")) or "").strip()
    sentences = ([("chapter_summary", summary)] if summary else []) + [
        (f"learning_goals.{index}", goal) for index, goal in enumerate(goals)
    ]
    said: list[dict[str, Any]] = []
    covered: set[str] = set()

    for source, sentence in sentences:
        matches = enrichment_concepts.matched(sentence, candidates)
        covered.update(match.key for match in matches)

        said.append(
            {
                "at": source,
                "says": sentence,
                "reviews": [match.key for match in matches],
                "matched_on": {match.key: list(match.matched_on) for match in matches},
                "closest_it_did_not_match": [
                    {"lesson": match.key, **match.as_note()}
                    for match in enrichment_concepts.score(sentence, candidates)[:2]
                    if not matches
                ],
            }
        )

    order = [chapter_entry["lesson_stable_key"] for chapter_entry in taught]

    return {
        "reviews": [key for key in order if key in covered],
        "said": said,
        "considered": order,
    }


# --------------------------------------------------------------------------- #
# The draft block: everything a person needs to judge this, and nothing to keep
# --------------------------------------------------------------------------- #

def _draft_note(
    *,
    slug: str,
    chapter: dict[str, Any],
    chapter_number: int,
    enrichment: dict[str, Any],
    proposals: list[dict[str, Any]],
    items: list[dict[str, Any]],
    review: dict[str, Any] | None,
    teaches: list[str],
    sources: dict[str, str],
) -> dict[str, Any]:
    """All of it in one block, so approving is: read it, fix what it names, delete
    this block, sign, flip and move. The rest of the file is already the shape an
    approved manifest has.
    """
    unmatched = _skills_without_a_concept(
        proposals=proposals, items=items, chapter_number=chapter_number
    )

    note: dict[str, Any] = {
        "generator": DRAFT_GENERATOR_VERSION,
        "written_from": sources,
        "what_this_is": (
            "A proposal, not a mapping. Nothing here was read by a person. The exporter "
            "refuses to publish it while approved is false."
        ),
        "how_it_was_derived": (
            "Every concept is one of this chapter's own learning goals from its enrichment, "
            "in the enrichment's order, stated in the enrichment's words. Nothing here was "
            "written by this generator: it matched the goals to the questions the exercise "
            "bank can ask, to the techniques that carry them out, and to the mastery "
            "checklist that says they are checked."
        ),
        "how_matches_were_made": enrichment_concepts.MATCH_RULE,
        "to_approve": _to_approve(slug, chapter_number, proposals, review),
        "coverage": _coverage(proposals=proposals, unmatched=unmatched, review=review),
        "needs_review": _needs_review(
            slug=slug,
            proposals=proposals,
            unmatched=unmatched,
            review=review,
            chapter_number=chapter_number,
            enrichment=enrichment,
        ),
        "what_the_material_says": {
            "chapter_title_as_printed": str(chapter.get("chapter_title") or ""),
            "enrichment_lesson_title": str(enrichment.get("lesson_title") or ""),
            "learning_goals": len(enrichment.get("learning_goals") or []),
            "techniques": len(enrichment.get("techniques") or []),
            "mastery_checklist": len(enrichment.get("mastery_checklist") or []),
            "learning_objectives": _texts(chapter.get("learning_objectives")),
            "teaching_lessons": teaches,
            "worked_examples": len(chapter.get("worked_examples") or []),
            "practice_questions": len(chapter.get("practice_questions") or []),
            "review_checklist": len(chapter.get("review_checklist") or []),
        },
    }

    if review:
        # Not `reviews`: that name is taken by the mapping's own list of lesson
        # keys, and one word for two shapes is what this vocabulary keeps curing.
        note["how_reviews_were_read"] = review
    else:
        declared_by = {
            proposal["concept"]["bank"]["skill"]: proposal["concept"]["stable_key"]
            for proposal in proposals
            if proposal["concept"].get("bank")
        }
        note["concepts"] = [
            _concept_note(proposal, items=items, enrichment=enrichment, declared_by=declared_by)
            for proposal in proposals
        ]
        note["skills_without_a_concept"] = unmatched

    return note


def _concept_note(
    proposal: dict[str, Any],
    *,
    items: list[dict[str, Any]],
    enrichment: dict[str, Any],
    declared_by: dict[str, str],
) -> dict[str, Any]:
    """How this one concept was derived, in enough detail to check in a glance."""
    concept = proposal["concept"]
    chosen = proposal["bank_from"]
    note: dict[str, Any] = {
        "stable_key": concept["stable_key"],
        "statement_is": f"the chapter's own {proposal['goal_at']}, verbatim",
    }

    if chosen:
        asked = [item for item in items if item.get("skill") == chosen.key]
        note["questions"] = {
            "skill": chosen.key,
            "skill_title": _skill_title(items, chosen.key),
            "exercises_in_bank": len(asked),
            "sample_question": str(asked[0].get("prompt") or "") if asked else "",
            # The bank's own word for what the question asks of a learner. Carried
            # rather than turned into objective_type, because Ela's vocabulary for
            # objective_type is not written down anywhere this repository can read.
            "bank_calls_this": str(asked[0].get("capability") or "") if asked else "",
            **chosen.match.as_note(),
            "beat_for_this_concept": [
                {"skill": assignment.key, **assignment.match.as_note()}
                for assignment in proposal["bank_shared_with"]
            ],
            "this_skill_also_matched": [
                {"at": f"learning_goals.{index}", **runner.as_note()}
                for index, runner in chosen.runners_up
            ],
        }
    else:
        note["questions"] = None
        note["no_questions_because"] = (
            "two skills matched this goal equally and a concept declares one bank"
            if proposal["bank_shared_with"]
            else "no skill in the bank matched this goal"
        )

        if proposal["bank_shared_with"]:
            note["skills_that_tied"] = [
                {"skill": assignment.key, **assignment.match.as_note()}
                for assignment in proposal["bank_shared_with"]
            ]
        else:
            note["closest_it_did_not_match"] = [
                {
                    "skill": match.key,
                    **match.as_note(),
                    "declared_by": declared_by.get(match.key, ""),
                }
                for match in proposal["closest_skills"]
            ]

    if concept.get("objective_type"):
        first = proposal["technique_matches"][0]
        note["objective_type_from"] = {
            "technique": _at(enrichment, first.key),
            "at": first.key,
            "ordered_steps": _steps(enrichment, first.key),
            **first.as_note(),
        }
    else:
        note["objective_type_from"] = None
        note["closest_technique_it_did_not_match"] = [
            {
                "technique": _at(enrichment, match.key),
                "at": match.key,
                "ordered_steps": _steps(enrichment, match.key),
                **match.as_note(),
            }
            for match in proposal["closest_techniques"]
        ]

    if concept.get("assessed"):
        note["assessed_from"] = {
            "mastery_checklist": [
                {"at": match.key, "says": _at(enrichment, match.key), **match.as_note()}
                for match in proposal["checklist_matches"]
            ],
            "and_the_bank_can_ask_it": bool(chosen),
        }
    else:
        note["assessed_from"] = None

    if chosen:
        note["required_form_from"] = proposal.get("required_form_from")
    else:
        note["required_form_from"] = None

    return note


def _skills_without_a_concept(
    *, proposals: list[dict[str, Any]], items: list[dict[str, Any]], chapter_number: int
) -> list[dict[str, Any]]:
    """Every skill the bank can ask of this chapter that no concept declares.

    Named, not attached. A skill quietly hung on the nearest concept would file a
    learner's evidence against a goal that has nothing to do with what they did.
    """
    declared = {
        proposal["concept"]["bank"]["skill"]
        for proposal in proposals
        if proposal["concept"].get("bank")
    }
    passed_over: dict[str, str] = {}

    for proposal in proposals:
        concept_key = proposal["concept"]["stable_key"]
        chosen = proposal["bank_from"]

        for assignment in proposal["bank_shared_with"]:
            passed_over[assignment.key] = (
                f"it matched {concept_key}, which declares {chosen.key} instead — that skill "
                f"matched the same goal better"
                if chosen
                else f"it matched {concept_key} exactly as well as another skill did, and a "
                f"concept declares one bank"
            )

    unmatched: list[dict[str, Any]] = []

    for skill in _skills_of(items, chapter_number):
        if skill in declared:
            continue

        asked = [item for item in items if item.get("skill") == skill]
        entry = {
            "skill": skill,
            "skill_title": _skill_title(items, skill),
            "exercises_in_bank": len(asked),
            "sample_question": str(asked[0].get("prompt") or "") if asked else "",
            "why": passed_over.get(
                skill, "no learning goal in this chapter's enrichment matched it"
            ),
        }
        unmatched.append(entry)

    return unmatched


def _coverage(
    *,
    proposals: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    review: dict[str, Any] | None,
) -> dict[str, Any]:
    """The counts, so the report is a number and not an impression."""
    if review:
        return {
            "concepts": 0,
            "reviews": len(review["reviews"]),
            "lessons_considered": len(review["considered"]),
            "sentences_that_matched_nothing": len(
                [said for said in review["said"] if not said["reviews"]]
            ),
        }

    return {
        "concepts": len(proposals),
        "with_questions": len([p for p in proposals if p["concept"].get("bank")]),
        "taught_but_not_yet_practised": len([p for p in proposals if not p["concept"].get("bank")]),
        "skills_without_a_concept": len(unmatched),
        "objective_type_from_the_material": len(
            [p for p in proposals if p["concept"].get("objective_type")]
        ),
        "assessed_from_the_material": len([p for p in proposals if p["concept"].get("assessed")]),
    }


def _to_approve(
    slug: str,
    chapter_number: int,
    proposals: list[dict[str, Any]],
    review: dict[str, Any] | None,
) -> list[str]:
    return [
        "Read what_the_material_says and every concept note against the chapter itself.",
        *(
            [
                "Check each statement is a goal this chapter really teaches — they are the "
                "enrichment's own sentences, so a wrong one is fixed in the enrichment, not here.",
                "Settle every concept stable_key now — after approval a learner's evidence "
                "is filed under it and it cannot move.",
                "Decide what to do about every concept with no questions and every skill with "
                "no concept: not_exportable_until lists the ones that block a package.",
            ]
            if proposals
            else []
        ),
        *(
            ["Confirm reviews names the lessons this review actually reviews."]
            if review
            else []
        ),
        "Fill authored_by with who approved it.",
        "Delete this draft block, set approved to true, and move the file to "
        f"manifests/{slug}.chapter{chapter_number:02d}.export_manifest.json.",
    ]


def _needs_review(
    *,
    slug: str,
    proposals: list[dict[str, Any]],
    unmatched: list[dict[str, Any]],
    review: dict[str, Any] | None,
    chapter_number: int,
    enrichment: dict[str, Any],
) -> list[str]:
    notes: list[str] = []

    if review:
        notes.append(
            f"This is a review lesson. It teaches nothing of its own, so it declares no "
            f"concepts; reviews names the lessons it draws on "
            f"({', '.join(review['reviews']) or 'none'}), read from its own chapter summary "
            f"and learning goals. Confirm that list is the one the book reviews."
        )

        silent = [said for said in review["said"] if not said["reviews"]]

        if silent:
            notes.append(
                f"{len(silent)} of this review's own sentences matched no lesson in this book: "
                + "; ".join(f"{said['at']} ({said['says']})" for said in silent)
                + ". Either this book does not teach what its review revises, or the wording "
                "differs enough that shared words could not see it."
            )

        declared = math_practice_items.chapters_for_lesson(chapter_number)
        from_the_bank = [
            f"{slug}:ch{number:02d}" for number in declared if number != chapter_number
        ]

        if sorted(from_the_bank) != sorted(review["reviews"]):
            notes.append(
                f"The exercise bank's own table says this review covers "
                f"{', '.join(from_the_bank) or 'nothing'}, which is not what the chapter's "
                f"material says ({', '.join(review['reviews']) or 'nothing'}). One of them is "
                f"wrong and a person has to say which."
            )

        notes.append(
            "The exporter cannot publish a review lesson yet: it refuses a manifest with "
            "no concepts. Approving this one needs that work first."
        )

        return notes

    notes.append(
        f"Every statement is one of this chapter's {len(enrichment.get('learning_goals') or [])} "
        f"learning goals from its enrichment, verbatim and in the enrichment's order. This "
        f"generator wrote none of them."
    )

    without_questions = [p for p in proposals if not p["concept"].get("bank")]

    if without_questions:
        notes.append(
            f"{len(without_questions)} of {len(proposals)} concept(s) have no questions: "
            + ", ".join(p["concept"]["stable_key"] for p in without_questions)
            + ". They are taught and not yet practised. No questions were invented for them, "
            "and the exporter will not publish a concept without a bank."
        )

    if unmatched:
        notes.append(
            f"{len(unmatched)} skill(s) the bank can ask of this chapter matched no concept: "
            + ", ".join(f"{entry['skill']} ({entry['exercises_in_bank']} questions)" for entry in unmatched)
            + ". They were left unattached rather than hung on the nearest concept."
        )

    missing_type = [p for p in proposals if not p["concept"].get("objective_type")]

    if missing_type:
        notes.append(
            f"{len(missing_type)} concept(s) carry no objective_type: no technique in this "
            f"chapter's enrichment gives an ordered method for them, so the material does not "
            f"say what kind of thing they are. The field is absent rather than defaulted."
        )

    if len(missing_type) < len(proposals):
        notes.append(
            f"Where objective_type is set it reads {PROCEDURE!r}, on the evidence that a named "
            f"technique carries the goal out in ordered steps. It is also the only value this "
            f"repository has ever emitted, so check it against Ela's vocabulary."
        )

    unassessed = [p for p in proposals if not p["concept"].get("assessed")]

    if unassessed:
        notes.append(
            f"{len(unassessed)} concept(s) carry no assessed flag: the mastery checklist does "
            f"not name them and the bank cannot ask them, so nothing in the material claims "
            f"they produce evidence."
        )

    notes.append(
        "No bank declares guidance -- chapter 3's approved banks carry a one-line "
        "reminder of the method, and writing teaching is not this generator's to do."
    )

    with_form = [
        p
        for p in proposals
        if ((p["concept"].get("bank") or {}).get("evaluation") or {}).get("marking", {}).get(
            "required_form"
        )
    ]
    without_form = [
        p
        for p in proposals
        if p["concept"].get("bank")
        and not ((p["concept"].get("bank") or {}).get("evaluation") or {})
        .get("marking", {})
        .get("required_form")
    ]

    if with_form:
        named = ", ".join(
            f"{p['concept']['stable_key']}="
            f"{p['concept']['bank']['evaluation']['marking']['required_form']}"
            for p in with_form
        )
        notes.append(
            f"{len(with_form)} bank(s) propose evaluation.marking.required_form from their "
            f"answers: {named}."
        )

    if without_form:
        named = ", ".join(
            f"{p['concept']['stable_key']} ({(p.get('required_form_from') or {}).get('why_unset', 'unset')})"
            for p in without_form
        )
        notes.append(
            f"{len(without_form)} bank(s) leave evaluation.marking.required_form unset because "
            f"their answers do not imply one form: {named}. A wrong form marks a correct "
            f"learner wrong, so decide what shape those answers must take."
        )

    if not with_form and not without_form:
        notes.append(
            "No bank declares evaluation.marking.required_form — this chapter has no "
            "questions yet, so nothing implies a form."
        )

    notes.append(
        "No resources are declared. Material is reusable because an author says so, and "
        "chapter 3 promotes its review checklist that way."
    )
    notes.append(
        "No diagrams are declared. Which drawing teaches which example is a teaching "
        "decision, and a wrong picture in maths teaches something false."
    )

    generator_version = _generator_version(enrichment)

    if generator_version:
        notes.append(
            f"teaching_document.generator_version reads {generator_version!r}, taken "
            f"from the document's own schema version. Confirm which run actually wrote it."
        )
    else:
        notes.append(
            "teaching_document.generator_version is empty: no teaching document of the shape "
            f"{teaching_document.COACH_SCHEMA_VERSION!r} was found for this chapter, and "
            "without one there is nothing to publish as the lesson."
        )

    notes.append("authored_by is empty. Approving this mapping means putting a name to it.")

    return notes


def _generator_version(enrichment: dict[str, Any] | None) -> str:
    """What wrote the teaching document, as far as the document itself admits.

    The Coach document records its SCHEMA but not its run, and this module may not
    invent one. `enrich_lessons/<schema>` says exactly that much: the tool in this
    repository that writes documents of this shape wrote one of this shape.
    """
    if not isinstance(enrichment, dict):
        return ""

    schema = str(enrichment.get("schema_version") or "").strip()

    if schema != teaching_document.COACH_SCHEMA_VERSION:
        return ""

    return f"enrich_lessons/{schema}"


def _lesson_title(chapter: dict[str, Any]) -> str:
    """The chapter's title without the number the book prints in front of it.

    The printed "3" in "3 Fractions" numbers the chapter within the book; it is not
    part of the lesson's name, and chapter 3's approved manifest drops it. The
    printed form is kept in the draft block either way, so the reviewer sees both.
    """
    title = str(chapter.get("chapter_title") or "").strip()
    head, _, tail = title.partition(" ")

    return tail.strip() if head.isdigit() and tail.strip() else title


def _teaching_titles(chapter: dict[str, Any]) -> list[str]:
    return [
        str(lesson.get("title") or "").strip()
        for lesson in chapter.get("core_lessons") or []
        if isinstance(lesson, dict) and str(lesson.get("title") or "").strip()
    ]


def _texts(claims: Any) -> list[str]:
    return [
        str(claim.get("text") or "").strip()
        for claim in claims or []
        if isinstance(claim, dict) and str(claim.get("text") or "").strip()
    ]


def _chapter(materials: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    chapters = (materials.get("learning_materials") or materials).get("chapters") or []

    for chapter in chapters:
        if chapter.get("chapter_number") == chapter_number:
            return chapter

    raise DraftRefused(f"the material has no chapter {chapter_number}")


# --------------------------------------------------------------------------- #
# Reading the files
# --------------------------------------------------------------------------- #

def read_taught_chapters(slug: str, pack, *, exclude: int) -> list[dict[str, Any]]:
    """What every other chapter of this book says it teaches, for a review to match.

    A chapter that teaches nothing of its own is skipped: a review does not review
    another review.
    """
    found: list[dict[str, Any]] = []

    for number in domain_packs.chapters_with_materials(pack):
        if number == exclude:
            continue

        materials = _read_json(pack.base_path(number), "the learning materials", required=False)
        enrichment = _read_json(pack.enrich_path(number), "the enrichment", required=False)

        if not isinstance(materials, dict) or not isinstance(enrichment, dict):
            continue

        try:
            chapter = _chapter(materials, number)
        except DraftRefused:
            continue

        if not _teaching_titles(chapter):
            continue

        found.append(
            {
                "chapter_number": number,
                "lesson_stable_key": f"{slug}:ch{number:02d}",
                "title": _lesson_title(chapter),
                "goals": [str(goal) for goal in enrichment.get("learning_goals") or []],
            }
        )

    return found


def emit_draft_file(
    *,
    slug: str,
    chapter_number: int,
    book_file: str | Path,
    output_file: str | Path,
    enrichment_file: str | Path | None = None,
    practice_items_file: str | Path | None = None,
) -> dict[str, Any]:
    """Read the chapter, derive the lesson plan, and write it as a draft."""
    pack = domain_packs.get(slug)
    materials = _read_json(book_file, "the learning materials", required=True)
    book_slug = str((materials.get("book") or {}).get("slug") or "").strip()

    if book_slug and book_slug != slug:
        raise DraftRefused(
            f"{book_file} is book {book_slug!r} but the draft was asked for under {slug!r}; "
            f"a mapping cannot describe one book under another's rules"
        )

    items = _read_json(
        practice_items_file or math_practice_items.OUTPUT_FILE, "the exercise bank", required=True
    )

    if not isinstance(items, list):
        raise DraftRefused("the exercise bank is not a list of questions")

    enrichment_path = Path(enrichment_file or pack.enrich_path(chapter_number))
    enrichment = _read_json(enrichment_path, "the enrichment", required=False)

    draft = build_draft(
        slug=slug,
        chapter_number=chapter_number,
        materials=materials,
        items=items,
        enrichment=enrichment,
        pack=pack,
        sources={
            "materials": str(book_file),
            "enrichment": str(enrichment_path) if enrichment is not None else "",
            "exercise_bank": str(practice_items_file or math_practice_items.OUTPUT_FILE),
        },
        taught_chapters=read_taught_chapters(slug, pack, exclude=chapter_number),
    )

    atomic_write_json(Path(output_file), draft)

    return draft


def _read_json(path: str | Path, what: str, *, required: bool) -> Any:
    location = Path(path)

    if not location.exists():
        if required:
            raise DraftRefused(f"{what} is not at {location}; nothing was drafted")

        return None

    try:
        return json.loads(location.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DraftRefused(f"{what} at {location} is not readable JSON: {error}") from error


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Draft one chapter's lesson plan for approval.")
    parser.add_argument("--slug", required=True, help="domain pack slug, e.g. math5a")
    parser.add_argument("--chapter", type=int, help="chapter number; omit with --all")
    parser.add_argument("--all", action="store_true", help="every chapter without an approved manifest")
    parser.add_argument("--book", help="the learning materials to read (default: the path the pack declares)")
    parser.add_argument("--enrichment", help="the enrichment to derive from (default: the path the pack declares)")
    parser.add_argument("--practice-items", help="the exercise bank (default: the generator's own output)")
    parser.add_argument("--out", help="where to write the draft (default: manifests/drafts/)")

    args = parser.parse_args(argv)

    if args.all == (args.chapter is not None):
        print("refused: name exactly one of --chapter N or --all", file=sys.stderr)
        return 2

    if args.all and (args.book or args.out or args.enrichment):
        print("refused: --book, --enrichment and --out name one file, so they cannot be used with --all",
              file=sys.stderr)
        return 2

    pack = domain_packs.get(args.slug)
    chapters = domain_packs.chapters_with_materials(pack) if args.all else [args.chapter]

    if not chapters:
        print(f"refused: no {args.slug} learning materials found at {pack.base_file}", file=sys.stderr)
        return 1

    written = 0

    for chapter in chapters:
        approved = manifest_module.manifest_path(args.slug, chapter)

        # A chapter someone has already approved is not redrafted. Overwriting an
        # approved mapping with a guess is the one thing this module must never do,
        # and writing a draft beside it invites exactly that mistake later.
        if args.all and approved.exists():
            print(f"chapter {chapter}: already approved at {approved}, not drafted")
            continue

        destination = args.out or draft_path(args.slug, chapter)

        try:
            draft = emit_draft_file(
                slug=args.slug,
                chapter_number=chapter,
                book_file=args.book or pack.base_path(chapter),
                output_file=destination,
                enrichment_file=args.enrichment,
                practice_items_file=args.practice_items,
            )
        except DraftRefused as error:
            print(f"refused: chapter {chapter}: {error}", file=sys.stderr)
            return 1

        coverage = draft["draft"]["coverage"]
        shape = (
            f"reviews {', '.join(draft.get('reviews') or []) or 'nothing'}"
            if draft.get("reviews") is not None
            else (
                f"{coverage['concepts']} concept(s), {coverage['with_questions']} with questions, "
                f"{coverage['skills_without_a_concept']} skill(s) unmatched"
            )
        )
        print(f"wrote {destination} — DRAFT, not approved: {shape}")
        written += 1

    print(f"{written} draft(s) written; none is approved and none will export until one is.")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
