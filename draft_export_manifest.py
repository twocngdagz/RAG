"""A DRAFT mapping for a chapter, for a person to read, correct and approve.

B17's text promised manifests "authored from generated drafts" and no generator
was ever built, so the one manifest that exists was written from a blank file.
Doing that eight more times by hand is the slow half of the work; the fast half —
listing what the exercise bank can already ask of a chapter, and which of the
chapter's own words bear on it — is mechanical, and this does it.

WHAT A DRAFT IS. It is a proposal, and it says so in the file. Every draft is
written `"approved": false`, and the exporter refuses to publish from anything
not explicitly approved. That refusal is the point of this module: a chapter's
concepts are what a learner's mastery is claimed about, and a machine's guess at
them must not reach a learner because it happened to look plausible in a diff.
Approving is a person's act — read it, fix it, sign it, move it to `manifests/`.

WHAT IT PROPOSES AND WHAT IT REFUSES TO. It proposes what it can point at:

    concepts        one per skill the computed bank can ask of this chapter, in
                    the bank's own order — a concept with no questions is a card
                    that can never be asked, so the bank is what makes a concept
                    proposable at all
    statement       the bank's skill title, VERBATIM and provisional. A sentence
                    about what a learner can do is a teaching judgement; a title
                    copied across is visibly a placeholder, and a fabricated
                    sentence is not
    objective_type  `procedure`, the only value this repository has ever emitted
    assessed        true, because every one of these questions is machine-marked
                    and so can produce evidence
    bank            the delivery and marking declaration chapter 3's approved
                    manifest uses, minus the parts that are teaching: no
                    guidance, no required answer form

It proposes no resources (declaring material reusable is an authoring decision),
no diagrams (which drawing suits which example is a teaching decision), no
assets, and no `authored_by` — an empty name is what makes approval an act
rather than a default.

REVIEW LESSONS. A review teaches nothing and carries no exercises of its own, so
its draft declares no concepts. It names the lessons it reviews instead, read
from the bank's own `REVIEW_COVERS`, per the decision that a review lesson is an
on-demand mixed quiz drawing on the concepts of the lessons it covers.

    python draft_export_manifest.py --slug math5a --chapter 5
    python draft_export_manifest.py --slug math5a --all
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

import domain_packs
import lesson_export_manifest as manifest_module
import math_practice_items
import teaching_document
from book_learning_materials_contract import atomic_write_json

# Drafts live one directory below the approved manifests they hope to become, so
# approving one is: read it, fix it, sign it, flip `approved`, move it up.
DRAFT_FILE = "manifests/drafts/{slug}.chapter{n:02d}.export_manifest.json"

DRAFT_GENERATOR_VERSION = "draft_export_manifest/1.0.0"

# The delivery and marking declaration chapter 3's approved banks carry, with the
# teaching taken out. `guidance` is a sentence telling a learner how to do the
# maths and `required_form` says what shape an answer must take -- both are
# authoring decisions, and one of them is subject-specific enough that copying
# chapter 3's would put "simplest fraction" on a bank of angle questions.
# What subject this lesson and its questions belong to, as chapter 3's approved
# manifest names it. Not the pack slug: `math5a` is which book, `math` is which
# subject, and Ela files activities under the second.
PROPOSED_DOMAIN = "math"

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

# The one value this repository has ever emitted for it. A second one invented
# here would be a vocabulary Ela never agreed to.
PROPOSED_OBJECTIVE_TYPE = "procedure"


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
    coach: dict[str, Any] | None,
    pack,
    sources: dict[str, str],
) -> dict[str, Any]:
    """One chapter's proposed mapping, marked as the proposal it is."""
    chapter = _chapter(materials, chapter_number)
    lesson_stable_key = f"{slug}:ch{chapter_number:02d}"
    reviews = [
        f"{slug}:ch{covered:02d}"
        for covered in math_practice_items.chapters_for_lesson(chapter_number)
        if covered != chapter_number
    ]
    teaches = _teaching_titles(chapter)

    if reviews and teaches:
        raise DraftRefused(
            f"chapter {chapter_number} is declared a review of "
            f"{', '.join(reviews)} but its material carries {len(teaches)} teaching "
            f"lesson(s); the bank and the book disagree about what this chapter is and "
            f"this module may not pick"
        )

    concepts = [] if reviews else _concepts(
        slug=slug,
        chapter_number=chapter_number,
        items=items,
        lesson_stable_key=lesson_stable_key,
    )

    draft: dict[str, Any] = {
        "manifest_schema_version": manifest_module.MANIFEST_SCHEMA_VERSION,
        # Checked by the exporter, which refuses anything not explicitly true.
        "approved": False,
        "draft": _draft_note(
            slug=slug,
            chapter=chapter,
            chapter_number=chapter_number,
            concepts=concepts,
            items=items,
            reviews=reviews,
            teaches=teaches,
            coach=coach,
            sources=sources,
        ),
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
        "teaching_document": {"generator_version": _generator_version(coach)},
        "concepts": concepts,
        "objective_associations": [],
        "resources": [],
        "assets": [],
        "diagrams": [],
    }

    if reviews:
        # Where a review's questions come from, said in the mapping rather than
        # left to the exporter: a review has no concepts of its own, and the
        # lessons it covers are the only thing that says what it can ask.
        draft["reviews"] = reviews

    return draft


def _concepts(
    *,
    slug: str,
    chapter_number: int,
    items: list[dict[str, Any]],
    lesson_stable_key: str,
) -> list[dict[str, Any]]:
    """One proposed concept per skill the bank can ask of this chapter."""
    return [
        {
            "stable_key": f"{lesson_stable_key}:{skill.replace('_', '-')}",
            # Provisional, and visibly so: the bank's own title for the skill.
            "statement": _skill_title(items, skill),
            "objective_type": PROPOSED_OBJECTIVE_TYPE,
            "assessed": True,
            "bank": {**copy.deepcopy(BANK_TEMPLATE), "skill": skill},
        }
        for skill in _skills_of(items, chapter_number)
    ]


def _skills_of(items: list[dict[str, Any]], chapter_number: int) -> list[str]:
    """The chapter's skills in the bank's own order.

    Not sorted: the bank generates its skills in teaching order, and re-sorting
    them would hand the reviewer a running order the book never had. Order of
    first appearance is stable across runs because the bank is.
    """
    found: list[str] = []

    for item in items:
        skill = str(item.get("skill") or "").strip()

        if item.get("chapter") == chapter_number and skill and skill not in found:
            found.append(skill)

    return found


def _skill_title(items: list[dict[str, Any]], skill: str) -> str:
    for item in items:
        if item.get("skill") == skill and str(item.get("skill_title") or "").strip():
            return str(item["skill_title"]).strip()

    return skill


def _draft_note(
    *,
    slug: str,
    chapter: dict[str, Any],
    chapter_number: int,
    concepts: list[dict[str, Any]],
    items: list[dict[str, Any]],
    reviews: list[str],
    teaches: list[str],
    coach: dict[str, Any] | None,
    sources: dict[str, str],
) -> dict[str, Any]:
    """Everything a person needs to judge this draft, and nothing they must keep.

    All of it in one block, so approving is: read it, fix what it names, delete
    this block, sign, flip and move. The rest of the file is already the shape an
    approved manifest has.
    """
    return {
        "generator": DRAFT_GENERATOR_VERSION,
        "written_from": sources,
        "what_this_is": (
            "A proposal, not a mapping. Nothing here was read by a person. The exporter "
            "refuses to publish it while approved is false."
        ),
        "to_approve": [
            "Read what_the_material_says below against the chapter itself.",
            *(
                [
                    "Rewrite every concept statement: they are the bank's skill titles, not "
                    "sentences about what a learner can do.",
                    "Settle every concept stable_key now — after approval a learner's evidence "
                    "is filed under it and it cannot move.",
                ]
                if concepts
                else []
            ),
            "Fill authored_by with who approved it.",
            "Delete this draft block, set approved to true, and move the file to "
            f"manifests/{slug}.chapter{chapter_number:02d}.export_manifest.json.",
        ],
        "needs_review": _needs_review(
            concepts=concepts, reviews=reviews, teaches=teaches, coach=coach
        ),
        "what_the_material_says": {
            "chapter_title_as_printed": str(chapter.get("chapter_title") or ""),
            "learning_objectives": _texts(chapter.get("learning_objectives")),
            "teaching_lessons": teaches,
            "worked_examples": len(chapter.get("worked_examples") or []),
            "practice_questions": len(chapter.get("practice_questions") or []),
            "review_checklist": len(chapter.get("review_checklist") or []),
        },
        "concepts": [
            _concept_note(concept, items) for concept in concepts
        ],
    }


def _concept_note(concept: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
    """What the bank knows about one proposed concept, for the person rewriting it."""
    skill = concept["bank"]["skill"]
    asked = [item for item in items if item.get("skill") == skill]

    return {
        "stable_key": concept["stable_key"],
        "skill": skill,
        "statement_is_provisional": True,
        "exercises_in_bank": len(asked),
        "sample_question": str(asked[0].get("prompt") or "") if asked else "",
        # The bank's own word for what the question asks of a learner. Carried
        # rather than turned into objective_type, because Ela's vocabulary for
        # objective_type is not written down anywhere this repository can read.
        "bank_calls_this": str(asked[0].get("capability") or "") if asked else "",
    }


def _needs_review(
    *,
    concepts: list[dict[str, Any]],
    reviews: list[str],
    teaches: list[str],
    coach: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []

    if reviews:
        notes.append(
            f"This is a review lesson. It teaches nothing and has no questions of its "
            f"own, so it declares no concepts; reviews names the lessons it draws on "
            f"({', '.join(reviews)}), read from the bank's REVIEW_COVERS. Confirm that "
            f"list is the one the book reviews."
        )
        notes.append(
            "The exporter cannot publish a review lesson yet: it refuses a manifest with "
            "no concepts. Approving this one needs that work first."
        )
    elif not concepts:
        notes.append(
            "The exercise bank can ask nothing about this chapter, so this draft proposes "
            "no concepts at all. A lesson with no concepts cannot be exported."
        )

    if concepts:
        notes.append(
            "Every statement is the bank's skill title copied across, which is a name for "
            "a skill and not a statement of what a learner can do. Rewrite all of them."
        )

        if len(concepts) > len(teaches):
            # A count, not a judgement: the bank was written against the book's
            # topics and the chapter against its pages, and where the bank offers
            # more cards than the chapter has explanations, some of these concepts
            # may be taught somewhere else in the book or not at all.
            notes.append(
                f"The bank proposes {len(concepts)} concept(s) but this chapter's material "
                f"carries {len(teaches)} teaching lesson(s). Check that the chapter actually "
                f"teaches each one before a learner is scheduled a card for it."
            )
        notes.append(
            f"Every objective_type is {PROPOSED_OBJECTIVE_TYPE!r}, the only value this "
            f"repository has ever emitted. Where the bank calls a skill 'recall' rather "
            f"than 'application', that may be the wrong word for it."
        )
        notes.append(
            "Every concept is assessed: true, because every question in these banks is "
            "machine-marked and can produce evidence. Say so deliberately."
        )
        notes.append(
            "No bank declares guidance -- chapter 3's approved banks carry a one-line "
            "reminder of the method, and writing teaching is not this generator's to do."
        )
        notes.append(
            "No bank declares evaluation.marking.required_form. Chapter 3 requires answers "
            "in simplest fraction form; decide what shape these answers must take."
        )

    notes.append(
        "No resources are declared. Material is reusable because an author says so, and "
        "chapter 3 promotes its review checklist that way."
    )
    notes.append(
        "No diagrams are declared. Which drawing teaches which example is a teaching "
        "decision, and a wrong picture in maths teaches something false."
    )

    generator_version = _generator_version(coach)

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


def _generator_version(coach: dict[str, Any] | None) -> str:
    """What wrote the teaching document, as far as the document itself admits.

    The Coach document records its SCHEMA but not its run, and this module may not
    invent one. `enrich_lessons/<schema>` says exactly that much: the tool in this
    repository that writes documents of this shape wrote one of this shape.
    """
    if not isinstance(coach, dict):
        return ""

    schema = str(coach.get("schema_version") or "").strip()

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


def emit_draft_file(
    *,
    slug: str,
    chapter_number: int,
    book_file: str | Path,
    output_file: str | Path,
    coach_file: str | Path | None = None,
    practice_items_file: str | Path | None = None,
) -> dict[str, Any]:
    """Read the chapter, propose the mapping, and write it as a draft."""
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

    coach_path = Path(coach_file or pack.enrich_path(chapter_number))
    coach = _read_json(coach_path, "the teaching document", required=False)

    draft = build_draft(
        slug=slug,
        chapter_number=chapter_number,
        materials=materials,
        items=items,
        coach=coach,
        pack=pack,
        sources={
            "materials": str(book_file),
            "exercise_bank": str(practice_items_file or math_practice_items.OUTPUT_FILE),
            "teaching_document": str(coach_path) if coach is not None else "",
        },
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
    parser = argparse.ArgumentParser(description="Draft one chapter's export mapping for approval.")
    parser.add_argument("--slug", required=True, help="domain pack slug, e.g. math5a")
    parser.add_argument("--chapter", type=int, help="chapter number; omit with --all")
    parser.add_argument("--all", action="store_true", help="every chapter without an approved manifest")
    parser.add_argument("--book", help="the learning materials to read (default: the path the pack declares)")
    parser.add_argument("--enrichment", help="the teaching document (default: the path the pack declares)")
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
                coach_file=args.enrichment,
                practice_items_file=args.practice_items,
            )
        except DraftRefused as error:
            print(f"refused: chapter {chapter}: {error}", file=sys.stderr)
            return 1

        reviews = draft.get("reviews") or []
        shape = (
            f"reviews {', '.join(reviews)}"
            if reviews
            else f"{len(draft['concepts'])} proposed concept(s)"
        )
        print(f"wrote {destination} — DRAFT, not approved: {shape}")
        written += 1

    print(f"{written} draft(s) written; none is approved and none will export until one is.")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
