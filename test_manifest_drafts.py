"""A draft is a proposal, and a proposal does not reach a learner.

B17 promised manifests "authored from generated drafts" and no generator existed,
so this builds one — and the moment a machine can propose what a chapter teaches,
the exporter needs a way to tell a proposal from a decision. A concept is what
mastery is claimed about; publish a guessed one and every attempt a learner makes
is filed against a goal nobody set, in a package that looks exactly like teaching
somebody wrote.

So approval is stated, and the exporter refuses everything else. Absent is not
approved. `"true"` is not approved. Approved-but-unsigned is not exportable
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


def materials(chapter: int) -> dict:
    return json.loads(Path(PACK.base_path(chapter)).read_text())


def coach(chapter: int) -> dict:
    return json.loads(Path(PACK.enrich_path(chapter)).read_text())


def build(chapter: int) -> dict:
    """The draft the command writes for one chapter, built the way it builds it."""
    return drafts.build_draft(
        slug="math5a",
        chapter_number=chapter,
        materials=materials(chapter),
        items=ITEMS,
        coach=coach(chapter),
        pack=PACK,
        sources={
            "materials": PACK.base_path(chapter),
            "exercise_bank": math_practice_items.OUTPUT_FILE,
            "teaching_document": PACK.enrich_path(chapter),
        },
    )


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
        json.loads(path.read_text()) == build(int(path.name.split(".chapter")[1][:2]))
        for path in committed
    ),
    "a committed draft and a fresh one disagree",
)

print("\nthe exporter refuses a draft, and says approval is why")

draft = build(5)

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

approved_but_unsigned = {**copy.deepcopy(draft), manifest_module.APPROVAL_FIELD: True}

try:
    ex.export_chapter(
        "math5a", 5, materials(5), manifest=approved_but_unsigned,
        teaching_document=coach(5), practice_items=ITEMS,
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
check(
    "and is otherwise the shape an approved mapping has",
    manifest_module.validate(draft) == [],
    str(manifest_module.validate(draft)),
)

print("\nchapter 3, already approved, exports exactly what it exported before")

package = ex.export_chapter(
    "math5a", 3, materials(3),
    manifest=json.loads((ROOT / "manifests" / "math5a.chapter03.export_manifest.json").read_text()),
    teaching_document=coach(3),
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

print("\na draft proposes what it can point at, and nothing else")

skills = [item["skill"] for item in ITEMS if item["chapter"] == 5]
proposed = [concept["bank"]["skill"] for concept in draft["concepts"]]

check(
    "one concept per skill the bank can ask of this chapter, in the bank's order",
    proposed == list(dict.fromkeys(skills)),
    f"{proposed} vs {list(dict.fromkeys(skills))}",
)
check(
    "no concept is proposed that the bank has no questions for",
    all(any(item["skill"] == skill for item in ITEMS) for skill in proposed),
    str(proposed),
)
# The statement is the bank's own title, verbatim. A fabricated sentence about
# what a learner can do would read as authored teaching in the diff that approves
# it; a title copied across is visibly a placeholder.
check(
    "every statement is the bank's skill title, not a sentence somebody made up",
    [concept["statement"] for concept in draft["concepts"]]
    == [next(item["skill_title"] for item in ITEMS if item["skill"] == skill) for skill in proposed],
    str([concept["statement"] for concept in draft["concepts"]]),
)
check(
    "no bank carries guidance, because guidance is teaching",
    not any(concept["bank"].get("guidance") for concept in draft["concepts"]),
    "a draft wrote teaching",
)
check(
    "no resources, assets or diagrams are declared",
    not (draft["resources"] or draft["assets"] or draft["diagrams"]),
    str({"resources": draft["resources"], "assets": draft["assets"], "diagrams": draft["diagrams"]}),
)
check(
    "the draft block says what a person still has to decide",
    len(draft["draft"]["needs_review"]) >= 5 and draft["draft"]["what_this_is"].startswith("A proposal"),
    str(draft["draft"]["needs_review"])[:160],
)
check(
    "and shows the material it was proposed from",
    draft["draft"]["what_the_material_says"]["learning_objectives"]
    == [claim["text"] for claim in materials(5)["learning_materials"]["chapters"][0]["learning_objectives"]],
    str(draft["draft"]["what_the_material_says"])[:160],
)

print("\na review teaches nothing, so its draft invents nothing")

for chapter, covers in ((4, [1, 2, 3]), (8, [1, 2, 3, 5, 6, 7]), (9, [1, 2, 3, 5, 6, 7])):
    review = build(chapter)

    check(
        f"REVIEW at chapter {chapter} declares no concepts of its own",
        review["concepts"] == [],
        str(review["concepts"])[:120],
    )
    check(
        f"and names the lessons it reviews ({len(covers)})",
        review["reviews"] == [f"math5a:ch{number:02d}" for number in covers],
        str(review.get("reviews")),
    )
    check(
        f"and the exporter says why chapter {chapter} cannot ship yet",
        "concepts is empty" in " ".join(manifest_module.validate(review)),
        str(manifest_module.validate(review)),
    )

# The bank says chapter 4 reviews others; the book would have to agree. If a
# chapter were both, this generator would have to pick which it is, and it may not.
contradiction = copy.deepcopy(materials(4))
contradiction["learning_materials"]["chapters"][0]["core_lessons"] = [{"title": "Something taught"}]

try:
    drafts.build_draft(
        slug="math5a", chapter_number=4, materials=contradiction, items=ITEMS,
        coach=coach(4), pack=PACK, sources={},
    )
    check("a review whose material teaches is refused", False, "it drafted")
except drafts.DraftRefused as error:
    check("a review whose material teaches is refused", "disagree" in str(error), str(error)[:140])

print("\nthe thin chapters are reported thin, not padded")

for chapter, concepts, lessons in ((5, 2, 1), (7, 4, 2)):
    thin = build(chapter)
    said = thin["draft"]["what_the_material_says"]

    check(
        f"chapter {chapter}: {concepts} concepts from a chapter with {lessons} teaching lesson(s)",
        len(thin["concepts"]) == concepts and len(said["teaching_lessons"]) == lessons,
        f"{len(thin['concepts'])} concepts, {len(said['teaching_lessons'])} lessons",
    )
    check(
        f"chapter {chapter}: and the draft says so where the reviewer will read it",
        any("teaching lesson(s)" in note for note in thin["draft"]["needs_review"]),
        str(thin["draft"]["needs_review"])[:160],
    )


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "a draft says it is a draft, and nothing exports one")
raise SystemExit(1 if fails else 0)
