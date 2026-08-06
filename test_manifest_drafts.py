"""A lesson plan is derived from the chapter's enrichment, and it is still a draft.

Two claims, and this suite exists because the first one was broken once already.

DERIVED, NOT INVENTED. A concept's statement is that chapter's own learning goal —
"You will find the value of any digit" — read from the enrichment an external
generator wrote. The first generator read the exercise bank's `skill` labels
instead and proposed a concept called "Place value", throwing away the class
material written for all nine chapters. So: statements are the goals, verbatim
and in order; a goal with no questions keeps its concept; a skill with no goal is
reported rather than hung on whichever concept is nearest; and `objective_type`
and `assessed` appear only where the material gives evidence for them.

STILL A DRAFT. The moment a machine can propose what a chapter teaches, the
exporter needs a way to tell a proposal from a decision. A concept is what mastery
is claimed about; publish a guessed one and every attempt a learner makes is filed
against a goal nobody set, in a package that looks exactly like teaching somebody
wrote. So approval is stated, and the exporter refuses everything else. Absent is
not approved. `"true"` is not approved. Approved-but-unsigned is not exportable
either, because `manually_authored` is a claim about a person.

And the one mapping that IS approved must be untouched by all of it: chapter 3
exports the same package it exported yesterday, at the same fingerprint.

    python test_manifest_drafts.py
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import derive_clean_chunks
import domain_packs
import draft_export_manifest as drafts
import enrichment_concepts
import export_lesson_package as ex
import lesson_export_manifest as manifest_module
import math_practice_items

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


ROOT = Path(__file__).resolve().parent
PACK = domain_packs.get("math5a")
DRAFTS = ROOT / "manifests" / "drafts"

# Rebuilt rather than read: the bank's generator is seeded, so this is the same
# 200 questions output/math_practice_items.json holds — and that file is
# gitignored, so a suite reading it would find nothing on a clean checkout.
ITEMS = math_practice_items.build_items(200, seed=12345)

CHAPTER_03_HASH = "0cc0598abed2"

TEACHING_CHAPTERS = (1, 2, 5, 6, 7)
REVIEW_CHAPTERS = (4, 8, 9)


def materials(chapter: int) -> dict:
    return json.loads(Path(PACK.base_path(chapter)).read_text())


def enrichment(chapter: int) -> dict:
    return json.loads(Path(PACK.enrich_path(chapter)).read_text())


def build(chapter: int) -> dict:
    """The draft the command writes for one chapter, built the way it builds it."""
    return drafts.build_draft(
        slug="math5a",
        chapter_number=chapter,
        materials=materials(chapter),
        items=ITEMS,
        enrichment=enrichment(chapter),
        pack=PACK,
        sources={
            "materials": PACK.base_path(chapter),
            "enrichment": PACK.enrich_path(chapter),
            "exercise_bank": math_practice_items.OUTPUT_FILE,
        },
        taught_chapters=drafts.read_taught_chapters("math5a", PACK, exclude=chapter),
    )


BUILT = {chapter: build(chapter) for chapter in TEACHING_CHAPTERS + REVIEW_CHAPTERS}


def refuses_unapproved(manifest: dict, label: str) -> None:
    try:
        ex.export_chapter("math5a", 5, materials(5), manifest=manifest)
        check(label, False, "it exported")
    except manifest_module.ManifestUnapproved as error:
        check(label, "not approved" in str(error), str(error)[:120])
    except Exception as error:  # noqa: BLE001 - any other refusal is the wrong one
        check(label, False, f"{type(error).__name__}: {str(error)[:100]}")


print("every draft on disk is a proposal, and says so")

committed = sorted(DRAFTS.glob("math5a.chapter*.export_manifest.json"))

check("the eight unauthored chapters have drafts", len(committed) == 8, str([p.name for p in committed]))
check(
    "and none of them is approved",
    all(json.loads(path.read_text())[manifest_module.APPROVAL_FIELD] is False for path in committed),
    str([path.name for path in committed if json.loads(path.read_text()).get("approved") is not False]),
)
check(
    "chapter 3 keeps its approved mapping and was not redrafted",
    not (DRAFTS / "math5a.chapter03.export_manifest.json").exists(),
    "a draft was written beside an approved mapping",
)
check(
    "each committed draft is exactly what the generator writes today",
    all(
        json.loads(path.read_text()) == BUILT[int(path.name.split(".chapter")[1][:2])]
        for path in committed
    ),
    "a committed draft and a fresh one disagree",
)

print("\na concept is the chapter's own learning goal, never a label from the bank")

for chapter in TEACHING_CHAPTERS:
    draft = BUILT[chapter]
    goals = enrichment(chapter)["learning_goals"]

    check(
        f"chapter {chapter}: one concept per learning goal, in the enrichment's order",
        [concept["statement"] for concept in draft["concepts"]] == goals,
        str([concept["statement"] for concept in draft["concepts"]])[:200],
    )
    check(
        f"chapter {chapter}: and every statement is that goal verbatim, not a summary of it",
        all(concept["statement"] in goals for concept in draft["concepts"]),
        "a statement was reworded",
    )

# The B21a regression, named: "Place value" is the bank's filing label for a set
# of questions. It is not a sentence about what a learner can do, and a lesson
# plan built out of those labels throws away the class material entirely.
titles = {item["skill_title"] for item in ITEMS}
statements = [
    concept["statement"] for chapter in TEACHING_CHAPTERS for concept in BUILT[chapter]["concepts"]
]

check(
    "no statement anywhere is an exercise-bank skill title",
    not (titles & set(statements)),
    str(sorted(titles & set(statements))),
)
check(
    "every concept key is unique and made from its own goal",
    len({
        concept["stable_key"] for chapter in TEACHING_CHAPTERS for concept in BUILT[chapter]["concepts"]
    }) == len(statements),
    "two concepts share a key",
)

print("\na goal with no matching questions is still a concept, and no questions are invented")

for chapter in TEACHING_CHAPTERS:
    draft = BUILT[chapter]
    unbanked = [concept for concept in draft["concepts"] if not concept.get("bank")]
    coverage = draft["draft"]["coverage"]

    check(
        f"chapter {chapter}: {len(unbanked)} taught-but-unpractised concept(s), counted honestly",
        coverage["taught_but_not_yet_practised"] == len(unbanked)
        and coverage["concepts"] == len(draft["concepts"])
        and coverage["with_questions"] == len(draft["concepts"]) - len(unbanked),
        str(coverage),
    )
    check(
        f"chapter {chapter}: every bank names a skill this chapter's questions belong to",
        all(
            any(
                item["skill"] == concept["bank"]["skill"] and item["chapter"] == chapter
                for item in ITEMS
            )
            for concept in draft["concepts"]
            if concept.get("bank")
        ),
        "a bank names questions from somewhere else",
    )

check(
    "at least one chapter carries a concept the bank cannot ask at all",
    any(
        not concept.get("bank")
        for chapter in TEACHING_CHAPTERS
        for concept in BUILT[chapter]["concepts"]
    ),
    "every concept happened to have questions, so the rule was never exercised",
)
check(
    "and the draft names those concepts where a reviewer will read it",
    all(
        any("taught and not yet practised" in note for note in BUILT[chapter]["draft"]["needs_review"])
        for chapter in TEACHING_CHAPTERS
        if any(not concept.get("bank") for concept in BUILT[chapter]["concepts"])
    ),
    "a concept without questions passed unmentioned",
)

print("\na skill with no goal is reported, not silently attached")

for chapter in TEACHING_CHAPTERS:
    draft = BUILT[chapter]
    askable = [item["skill"] for item in ITEMS if item["chapter"] == chapter]
    declared = {concept["bank"]["skill"] for concept in draft["concepts"] if concept.get("bank")}
    reported = {entry["skill"] for entry in draft["draft"]["skills_without_a_concept"]}

    check(
        f"chapter {chapter}: every askable skill is either declared or named as unmatched",
        declared | reported == set(askable) and not (declared & reported),
        f"declared {sorted(declared)}, reported {sorted(reported)}, askable {sorted(set(askable))}",
    )
    check(
        f"chapter {chapter}: and each unmatched skill says why, with its questions counted",
        all(
            entry["why"] and entry["exercises_in_bank"] > 0
            for entry in draft["draft"]["skills_without_a_concept"]
        ),
        str(draft["draft"]["skills_without_a_concept"])[:160],
    )

check(
    "some skill in this book really did go unmatched, so the rule was exercised",
    any(BUILT[chapter]["draft"]["skills_without_a_concept"] for chapter in TEACHING_CHAPTERS),
    "every skill matched, so nothing tested the report",
)

print("\nobjective_type and assessed are the material's evidence, never a default")

typed = [
    (chapter, concept, note)
    for chapter in TEACHING_CHAPTERS
    for concept, note in zip(BUILT[chapter]["concepts"], BUILT[chapter]["draft"]["concepts"])
]

check(
    "every objective_type points at a technique in the enrichment with ordered steps",
    all(
        note["objective_type_from"]
        and note["objective_type_from"]["at"].startswith("techniques.")
        and note["objective_type_from"]["ordered_steps"] >= drafts.STEPS_FOR_A_PROCEDURE
        for _, concept, note in typed
        if concept.get("objective_type")
    ),
    str([note["objective_type_from"] for _, c, note in typed if c.get("objective_type")])[:200],
)
check(
    "and a concept the material gives no method for carries no objective_type at all",
    all(
        note["objective_type_from"] is None and "objective_type" not in concept
        for _, concept, note in typed
        if not concept.get("objective_type")
    ),
    "a concept without evidence still carried the field",
)
check(
    "some concept really is left without one, so it is evidence and not a stamp",
    any(not concept.get("objective_type") for _, concept, _ in typed),
    "every concept was typed, so the absent case was never taken",
)
check(
    "every assessed concept points at a mastery-checklist line or at questions",
    all(
        note["assessed_from"]
        and (note["assessed_from"]["mastery_checklist"] or note["assessed_from"]["and_the_bank_can_ask_it"])
        for _, concept, note in typed
        if concept.get("assessed")
    ),
    "assessed was claimed with nothing behind it",
)
check(
    "some concept is left unassessed, and none is ever written assessed: false",
    any(not concept.get("assessed") for _, concept, _ in typed)
    and all(concept.get("assessed") is not False for _, concept, _ in typed),
    "assessed was defaulted one way or the other",
)

print("\nthe draft says plainly how each concept was matched")

check(
    "every draft states the matching rule it used",
    all(
        BUILT[chapter]["draft"]["how_matches_were_made"] == enrichment_concepts.MATCH_RULE
        for chapter in BUILT
    ),
    "a draft matched without saying how",
)
check(
    "and every bank shows the words that won it and what it beat",
    all(
        note["questions"]["matched_on"]
        and note["questions"]["score"] >= enrichment_concepts.MATCH_THRESHOLD
        and "beat_for_this_concept" in note["questions"]
        for _, concept, note in typed
        if concept.get("bank")
    ),
    "a bank was attached without saying why",
)
check(
    "a concept with no bank says why, and what it came closest to",
    all(
        note["no_questions_because"]
        and ("closest_it_did_not_match" in note or "skills_that_tied" in note)
        for _, concept, note in typed
        if not concept.get("bank")
    ),
    "a gap was left unexplained",
)

print("\na review teaches nothing, and reads what it reviews off its own pages")

for chapter in REVIEW_CHAPTERS:
    review = BUILT[chapter]
    said = review["draft"]["how_reviews_were_read"]["said"]

    check(
        f"REVIEW at chapter {chapter} declares no concepts of its own",
        review["concepts"] == [] and "skills_without_a_concept" not in review["draft"],
        str(review["concepts"])[:120],
    )
    check(
        f"chapter {chapter}: and names the lessons it reviews ({len(review['reviews'])})",
        review["reviews"] and all(key.startswith("math5a:ch") for key in review["reviews"]),
        str(review.get("reviews")),
    )
    check(
        f"chapter {chapter}: every lesson it names was named by a sentence of its own material",
        all(
            any(key in entry["reviews"] and entry["matched_on"][key] for entry in said)
            for key in review["reviews"]
        ),
        str([entry["reviews"] for entry in said]),
    )
    check(
        f"chapter {chapter}: and the sentences it read are the book's, quoted with their paths",
        all(
            entry["at"] == "chapter_summary" or entry["at"].startswith("learning_goals.")
            for entry in said
        )
        and any(entry["at"] == "chapter_summary" for entry in said),
        str([entry["at"] for entry in said]),
    )
    check(
        f"chapter {chapter}: and the exporter says why it cannot ship yet",
        "concepts is empty" in " ".join(review["draft"]["not_exportable_until"]),
        str(review["draft"]["not_exportable_until"]),
    )

# The coverage comes from the chapter's own material, so where the exercise bank's
# hardcoded table disagrees the draft says so instead of quietly taking the table.
disagreeing = [
    chapter
    for chapter in REVIEW_CHAPTERS
    if sorted(BUILT[chapter]["reviews"])
    != sorted(
        f"math5a:ch{number:02d}"
        for number in math_practice_items.chapters_for_lesson(chapter)
        if number != chapter
    )
]

check(
    "where the material and the bank's table disagree, the draft names both",
    disagreeing
    and all(
        any("exercise bank's own table" in note for note in BUILT[chapter]["draft"]["needs_review"])
        for chapter in disagreeing
    ),
    f"disagreeing: {disagreeing}",
)
check(
    "and a sentence the book reviews but this book never taught is reported, not dropped",
    any(
        not entry["reviews"]
        for chapter in REVIEW_CHAPTERS
        for entry in BUILT[chapter]["draft"]["how_reviews_were_read"]["said"]
    ),
    "no unmatched sentence anywhere, so the report was never exercised",
)

# The bank says chapter 4 reviews others; the book's own title agrees. If a chapter
# were titled a review and still taught, this generator would have to pick which it
# is, and it may not.
contradiction = copy.deepcopy(materials(4))
contradiction["learning_materials"]["chapters"][0]["core_lessons"] = [{"title": "Something taught"}]

try:
    drafts.build_draft(
        slug="math5a", chapter_number=4, materials=contradiction, items=ITEMS,
        enrichment=enrichment(4), pack=PACK, sources={}, taught_chapters=[],
    )
    check("a review whose material teaches is refused", False, "it drafted")
except drafts.DraftRefused as error:
    check("a review whose material teaches is refused", "disagree" in str(error), str(error)[:140])

try:
    drafts.build_draft(
        slug="math5a", chapter_number=5, materials=materials(5), items=ITEMS,
        enrichment=None, pack=PACK, sources={}, taught_chapters=[],
    )
    check("a chapter with no enrichment is refused, not drafted from the bank", False, "it drafted")
except drafts.DraftRefused as error:
    check(
        "a chapter with no enrichment is refused, not drafted from the bank",
        "no enrichment" in str(error),
        str(error)[:140],
    )

print("\nthe exporter refuses a draft, and says approval is why")

draft = BUILT[5]

refuses_unapproved(draft, "a draft mapping is refused")
refuses_unapproved({**draft, manifest_module.APPROVAL_FIELD: None}, "approved: null is refused")
# Silence is not consent: a mapping that never says who read it has not been read,
# and a generator that forgot to write the field would otherwise ship by default.
refuses_unapproved({key: value for key, value in draft.items() if key != manifest_module.APPROVAL_FIELD},
                   "a mapping that says nothing about approval is refused")
refuses_unapproved({**draft, manifest_module.APPROVAL_FIELD: "true"}, "the string 'true' is not approval")
refuses_unapproved({**draft, manifest_module.APPROVAL_FIELD: 1}, "a truthy 1 is not approval")

with tempfile.TemporaryDirectory() as workspace:
    chunks = Path(workspace) / "chapter05.clean_chunks.json"
    derive_clean_chunks.emit_clean_chunks_file(
        slug="math5a", chapter_number=5, book_file=PACK.base_path(5), output_file=chunks
    )
    package_file = Path(workspace) / "chapter05.package.json"

    run = subprocess.run(
        [sys.executable, str(ROOT / "export_lesson_package.py"),
         "--slug", "math5a", "--chapter", "5",
         "--book", PACK.base_path(5),
         "--clean-chunks", str(chunks),
         "--manifest", str(DRAFTS / "math5a.chapter05.export_manifest.json"),
         "--out", str(package_file)],
        capture_output=True, text=True, cwd=ROOT,
    )

    check("the command refuses a draft with exit 1", run.returncode == 1, str(run.returncode))
    check("and writes no package", not package_file.exists(), "a package was written from a draft")
    check(
        "and the refusal is about approval, not about the material",
        "not approved" in run.stderr,
        run.stderr[:200],
    )
    # Chapter 5's material does not pass the source contract, and would have been
    # the first thing to fail. The person who pointed the exporter at a draft
    # needs to be told it is a draft.
    check(
        "which is checked before the source contract, so the reason named is the real one",
        "source contract" not in run.stderr,
        run.stderr[:200],
    )

print("\napproval is a person's act, and it takes more than a flag")

# The concepts a person would keep on a first pass: the ones the bank can actually
# ask. The rest are what not_exportable_until is about, and they are tested above.
signable = {
    **copy.deepcopy(draft),
    manifest_module.APPROVAL_FIELD: True,
    "concepts": [concept for concept in draft["concepts"] if concept.get("bank")],
}

check(
    "a draft trimmed to its answerable concepts is the shape an approved mapping has",
    manifest_module.validate(signable) == [],
    str(manifest_module.validate(signable)),
)

try:
    ex.export_chapter(
        "math5a", 5, materials(5), manifest=signable,
        teaching_document=enrichment(5), practice_items=ITEMS,
    )
    check("approving without signing still refuses", False, "it exported")
except manifest_module.ManifestUnapproved as error:
    check("approving without signing still refuses", False, f"still unapproved: {error}")
except ex.ExportRefused as error:
    check("approving without signing still refuses", "does not say who wrote it" in str(error), str(error)[:140])

check(
    "a draft leaves the name empty for whoever approves it",
    draft["authored_by"] == "",
    repr(draft["authored_by"]),
)

print("\nwhat stands between a draft and a package is the validator's own list")

for chapter in TEACHING_CHAPTERS + REVIEW_CHAPTERS:
    check(
        f"chapter {chapter}: not_exportable_until is exactly what the exporter would say",
        BUILT[chapter]["draft"]["not_exportable_until"] == manifest_module.validate(BUILT[chapter]),
        str(BUILT[chapter]["draft"]["not_exportable_until"])[:160],
    )

check(
    "a concept with no bank is named there rather than papered over",
    any(
        "bank is missing" in problem
        for chapter in TEACHING_CHAPTERS
        for problem in BUILT[chapter]["draft"]["not_exportable_until"]
    ),
    "no draft admitted an unanswerable concept",
)
check(
    "no draft declares resources, assets or diagrams",
    not any(
        BUILT[chapter]["resources"] or BUILT[chapter]["assets"] or BUILT[chapter]["diagrams"]
        for chapter in BUILT
    ),
    "a draft made an authoring decision",
)
check(
    "and no bank carries guidance, because guidance is teaching",
    not any(
        concept["bank"].get("guidance")
        for chapter in TEACHING_CHAPTERS
        for concept in BUILT[chapter]["concepts"]
        if concept.get("bank")
    ),
    "a draft wrote teaching",
)

print("\nchapter 3, already approved, exports exactly what it exported before")

package = ex.export_chapter(
    "math5a", 3, materials(3),
    manifest=json.loads((ROOT / "manifests" / "math5a.chapter03.export_manifest.json").read_text()),
    teaching_document=enrichment(3),
    practice_items=ITEMS,
    asset_base=ROOT / "manifests",
)

check(
    "the approved mapping still exports",
    package["lesson"]["stable_key"] == "math5a:ch03" and len(package["concepts"]) == 5,
    str(package["lesson"]),
)
check(
    f"at content_hash {CHAPTER_03_HASH}",
    package["content_hash"].startswith(CHAPTER_03_HASH),
    package["content_hash"][:24],
)
check(
    "and the chunks it is validated against are the derived ones",
    derive_clean_chunks.derive(materials(3), chapter_number=3)
    == json.loads((ROOT / "tests" / "fixtures" / "b11" / "math5a.chapter03.clean_chunks.json").read_text()),
    "the derivation and the parsed file disagree",
)

print("\nthe matcher shares words, weights them, and stays quiet when it cannot tell")

check(
    "LaTeX, punctuation and everyday words are dropped; plurals and -ing are stemmed",
    enrichment_concepts.words("You will round $4{,}865$ to the nearest hundreds.")
    == {"round", "nearest", "hundred"}
    and enrichment_concepts.words("Rounding lines") == {"round", "lin"},
    str(enrichment_concepts.words("You will round $4{,}865$ to the nearest hundreds.")),
)

field = {
    "one_only": enrichment_concepts.words("angle protractor"),
    "shared_a": enrichment_concepts.words("angle line"),
    "shared_b": enrichment_concepts.words("angle point"),
}

check(
    "a word only one candidate uses carries a match; a word all of them use does not",
    [match.key for match in enrichment_concepts.matched("protractor", field)] == ["one_only"]
    and enrichment_concepts.matched("angle", field) == [],
    str(enrichment_concepts.matched("angle", field)),
)
check(
    "and the words that produced a match are reported with it",
    enrichment_concepts.matched("angle protractor", field)[0].matched_on == ("angl", "protractor"),
    str(enrichment_concepts.matched("angle protractor", field)[0]),
)

tie = enrichment_concepts.assign(["add and subtract"], {"adds": {"add"}, "subtracts": {"subtract"}})

check(
    "a candidate goes to the one sentence it matched best",
    [assignment.sentence_index for assignment in enrichment_concepts.assign(
        ["a protractor", "a point"], field
    )] == [0, None, 1],
    str([(a.key, a.sentence_index) for a in enrichment_concepts.assign(["a protractor", "a point"], field)]),
)
check(
    "and two sentences that match a candidate equally leave it unassigned",
    [assignment.sentence_index for assignment in enrichment_concepts.assign(
        ["a protractor", "a protractor"], field
    )] == [None, None, None],
    str([(a.key, a.sentence_index, a.tied_between)
         for a in enrichment_concepts.assign(["a protractor", "a protractor"], field)]),
)
check(
    "one sentence may still match two candidates — the draft reports both",
    [assignment.sentence_index for assignment in tie] == [0, 0],
    str([(a.key, a.sentence_index) for a in tie]),
)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "a lesson plan comes from the chapter, and still says it is a draft")
raise SystemExit(1 if fails else 0)
