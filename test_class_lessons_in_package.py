"""Class lessons cross into the package, and nothing they arrive beside moves.

B20.1 built the transform stage: per concept, an outside generator writes the
thing a teacher stands up and delivers — a goal, the techniques that reach it,
the examples worked in front of the class — and the runner stores it. The
exporter did not read any of it. A package was assembled from the enrichment
alone, so every technique and worked example the generator wrote was ignored,
silently, by the one piece of machinery whose whole job is to carry teaching
across.

Chapter 5 is the material here, because it is the chapter that has actually been
through the live contract: five concepts, eleven techniques, sixteen worked
examples. Chapter 3 is the control, and the harder half of the claim — it has no
class lessons, and it must still export at exactly the fingerprint it exports at
today, byte for byte.

A TECHNIQUE'S METHOD CROSSES UNDER THE NAME ITS BLOCK CARRIES. The contract asks
the generator for `steps`, a name and an instruction each; a `concept_explanation`
block carries its method in `how_to`. Nothing translated between them, so the
import refused every technique block chapter 5 produced. The assertions below read
the field the consumer reads, and hold it against the steps in the material.

A CONCEPT'S TEACHING IS SELECTED BY `teaches`. The consumer picks a concept's
blocks with `block.teaches == concept stable_key`. Putting the concept only in
the block key left every concept with zero teaching steps. Class-lesson blocks
carry `teaches`; chapter-level enrichment blocks do not.

WHY A FIXTURE MAPPING FOR CHAPTER 5. Approval is a person reading generated
content, and it is not this suite's to grant. Chapter 5's real draft stays
unapproved in `manifests/drafts/` — three of its five concepts have no questions
yet, so it cannot be published at all — and this suite asserts that it is still
unapproved rather than quietly fixing it. The fixture mapping beside these
fixtures is approved only here, and carries the two concepts that draft matched
to a bank, copied from it.

    python test_class_lessons_in_package.py
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import class_lesson_store
import class_lesson_contract as contract
import enrichment_comparison
import export_lesson_package as ex
import lesson_export_manifest as manifest_module
import lesson_package
import teaching_document as td

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


def copy(value):
    return json.loads(json.dumps(value))


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures" / "b21"

# Chapter 5's own material, tracked in the repository. The class lessons and the
# question bank are not tracked — they are generated — so committed copies of
# both live in the fixtures, which is what makes this suite reproducible.
CH5_SOURCE = read(ROOT / "output" / "math5a.chapter05.book_learning_materials.json")
CH5_COACH = read(ROOT / "output" / "math5a.chapter05.enrichment.json")
CH5_MANIFEST = read(FIXTURES / "math5a.chapter05.export_manifest.json")
CH5_LESSONS = read(FIXTURES / "math5a.chapter05.class_lessons.json")
ITEMS = read(FIXTURES / "math_practice_items.json")

# Where chapter 5's concepts are decided. A draft today; the approved mapping the
# day somebody approves it. Either way it is the mapping, never the generator,
# that says what a concept is called and what it claims a learner can do.
CH5_MAPPING_PATH = next(
    path
    for path in (
        ROOT / "manifests" / "math5a.chapter05.export_manifest.json",
        ROOT / "manifests" / "drafts" / "math5a.chapter05.export_manifest.json",
    )
    if path.exists()
)
CH5_MAPPING = read(CH5_MAPPING_PATH)

DECLARED = [concept["stable_key"] for concept in CH5_MANIFEST["concepts"]]
GENERATOR = CH5_MANIFEST["class_lessons"]["generator_version"]


def only(store: dict, keys: list[str]) -> dict:
    """The same store carrying only these concepts' lessons. Selection, never editing."""
    return {**store, "concepts": {k: v for k, v in store["concepts"].items() if k in set(keys)}}


def export5(*, manifest=CH5_MANIFEST, lessons=None):
    return ex.export_chapter(
        "math5a",
        5,
        CH5_SOURCE,
        manifest=manifest,
        teaching_document=CH5_COACH,
        practice_items=ITEMS,
        class_lessons=only(CH5_LESSONS, DECLARED) if lessons is None else lessons,
        asset_base=FIXTURES,
    )


print("every class lesson chapter 5 has becomes blocks, and each belongs to its concept")

statements = {concept["stable_key"]: concept["statement"] for concept in CH5_MAPPING["concepts"]}
lessons = class_lesson_store.lessons(CH5_LESSONS)

check("chapter 5 has a class lesson for every concept the mapping declares",
      sorted(lessons) == sorted(statements), f"{sorted(lessons)} vs {sorted(statements)}")

checked = {}
refusals = []

for key, lesson in lessons.items():
    try:
        checked[key] = contract.validate(
            lesson, concept_key=key, concept_statement=statements[key]
        )
    except contract.ClassLessonRefused as error:
        refusals.append(f"{key}: {error}")

check("every one of them still satisfies the contract it was generated under",
      not refusals, "; ".join(refusals)[:200])
check("and every one of them teaches the concept the mapping states, in the mapping's words",
      all(checked[key]["concept_statement"] == statements[key] for key in checked))

entries = [
    {
        "concept_stable_key": key,
        "class_lesson": lesson,
        "provenance": {
            "origin": "pedagogical_generation",
            "grounded_in_source_chunk_ids": [],
            "generation_reason": "fixture",
            "generator_version": GENERATOR,
        },
    }
    for key, lesson in checked.items()
]
built = td.with_class_lessons({"blocks": []}, entries)["blocks"]
kinds = [block["type"] for block in built]

check("eleven techniques become eleven blocks",
      kinds.count("concept_explanation") == 11, str(kinds.count("concept_explanation")))
check("sixteen worked examples become sixteen blocks",
      kinds.count("worked_example") == 16, str(kinds.count("worked_example")))
check("each concept's goal becomes one block", kinds.count("goals") == 5, str(kinds.count("goals")))
check("no block belongs to the chapter at large",
      all(block["teaches"] for block in built))
check("a concept's blocks are its own",
      all(block["key"].startswith(f"class_lesson.{block['teaches']}.")
          for block in built))
check("and they arrive in the order they are taught: goal, then method, then examples",
      [kinds[index] for index in range(6)]
      == ["goals", "concept_explanation", "concept_explanation", "worked_example",
          "worked_example", "worked_example"],
      str(kinds[:6]))
check("the consumer's field is teaches, not a name only RAG knows",
      all("teaches" in block and "concept_stable_key" not in block for block in built))

technique = next(block for block in built if block["type"] == "concept_explanation")

check("a technique's method rides where a concept_explanation carries it",
      len(technique["content"]["how_to"]) >= 2 and all(technique["content"]["how_to"]),
      str(technique["content"])[:160])
check("and nowhere else, so a reader has one place to look",
      "steps" not in technique["content"], str(sorted(technique["content"])))
check("each step keeps its name and its instruction, neither summarised away",
      technique["content"]["how_to"]
      == [f"{step['step']}: {step['detail']}"
          for step in checked[built[0]["teaches"]]["techniques"][0]["steps"]],
      str(technique["content"]["how_to"])[:160])

check("and the rest of what the contract asked for",
      all(technique["content"][field]
          for field in ("name", "purpose", "example", "why_it_matters", "common_error")),
      str(sorted(technique["content"])))

taught = [line for block in built if block["type"] == "concept_explanation"
          for line in block["content"]["how_to"]]

check("a step named for the move keeps the instruction that says how to make it",
      any(line.startswith("Write: ") and "\\frac{1}{2}" in line for line in taught),
      str([line for line in taught if line.startswith("Write")])[:200])

methodless = copy(entries)
methodless[0]["class_lesson"]["techniques"][0]["steps"] = []

try:
    td.with_class_lessons({"blocks": []}, methodless)
    check("a technique with no method is refused, never published as an empty heading", False,
          "it became a heading with nothing under it")
except td.TeachingDocumentRefused as error:
    check("a technique with no method is refused, never published as an empty heading", True)
    check("and the refusal names the block and the field it is missing",
          "how_to" in str(error) and "techniques.0" in str(error), str(error)[:200])

example = next(block for block in built if block["type"] == "worked_example")

check("a worked example keeps its decoding, its plan and the teacher's annotations",
      bool(example["content"]["decoding"]) and bool(example["content"]["plan"])
      and bool(example["content"]["annotations"]),
      str(sorted(example["content"])))

# An illustration of a concept's teaching carries teaches too — derived from the
# block it follows, never guessed. A chapter-level picture with no concept on its
# anchor stays untagged (chapter 3's enrichment diagrams stay that way).
picture_doc = td.with_illustrations(
    {"blocks": [block for block in built if block["teaches"] == DECLARED[0]][:1]},
    [
        {
            "key": "illustration.fixture",
            "appears_after": built[0]["key"],
            "content": {
                "caption": "a picture",
                "alt_text": "alt",
                "asset_stable_key": "math5a:ch05:fixture",
            },
            "provenance": built[0]["provenance"],
        }
    ],
)
picture = next(block for block in picture_doc["blocks"] if block["type"] == "illustration")

check("an illustration of a concept's teaching carries teaches too",
      picture.get("teaches") == DECLARED[0], str(picture.get("teaches")))
check("and a chapter-level picture with no concept on its anchor stays untagged",
      "teaches" not in td.with_illustrations(
          {"blocks": [{"key": "worked_examples.0", "section": "worked_examples",
                       "type": "worked_example", "content": {}, "provenance": {}}]},
          [{"key": "illustration.loose", "appears_after": "worked_examples.0",
            "content": {"caption": "c", "alt_text": "a", "asset_stable_key": "x"},
            "provenance": {}}],
      )["blocks"][1])


print("\nthe export reads them, and the package carries them under their concepts")

package = export5()
blocks = package["teaching_document"]["blocks"]
class_blocks = [block for block in blocks if block["section"] == td.CLASS_LESSON_SECTION]
concept_keys = {concept["stable_key"] for concept in package["concepts"]}

check("the package carries the class lessons of the concepts it declares",
      {block["teaches"] for block in class_blocks} == concept_keys,
      str(sorted({block["teaches"] for block in class_blocks})))
check("twelve blocks for two concepts: two goals, four techniques, six examples",
      len(class_blocks) == 12
      and [block["type"] for block in class_blocks].count("worked_example") == 6,
      str(len(class_blocks)))
check("every concept has at least one block whose teaches equals its stable_key",
      all(any(block.get("teaches") == key for block in class_blocks) for key in concept_keys),
      str(sorted(concept_keys)))
check("chapter-level blocks carry no teaches — they belong to no single concept",
      all("teaches" not in block for block in blocks if block["section"] != td.CLASS_LESSON_SECTION))

published = [block for block in class_blocks if block["type"] == "concept_explanation"]
methods = [line for block in published for line in block["content"]["how_to"]]
generated = [
    f"{step['step']}: {step['detail']}"
    for key in DECLARED
    for technique in checked[key]["techniques"]
    for step in technique["steps"]
]

check("every technique the export publishes carries its method where the consumer reads it",
      len(published) == 4 and all(block["content"]["how_to"] for block in published),
      str([len(block["content"]["how_to"]) for block in published]))
check("and every step of chapter 5's real material arrives with both of its halves",
      methods == generated, str(methods[:2]))
check("no technique block carries a method anywhere else",
      all("steps" not in block["content"] for block in published))
check("positions are restated across the whole document",
      [block["position"] for block in blocks] == list(range(len(blocks))))
check("every block is still addressable on its own",
      len({block["key"] for block in blocks}) == len(blocks))
check("the whole package is structurally importable",
      lesson_package.structural_problems(package) == [],
      str(lesson_package.structural_problems(package)[:3]))

teaching = [block for block in blocks if block["section"] != td.CLASS_LESSON_SECTION]

check("class lesson blocks come after the chapter's own teaching, not instead of it",
      max(block["position"] for block in teaching)
      < min(block["position"] for block in class_blocks))
check("a class lesson block says a generator wrote it",
      {block["provenance"]["origin"] for block in class_blocks} == {"pedagogical_generation"},
      str({block["provenance"]["origin"] for block in class_blocks}))
check("and names the generator the mapping declared, never one RAG made up",
      {block["provenance"]["generator_version"] for block in class_blocks} == {GENERATOR},
      str({block["provenance"]["generator_version"] for block in class_blocks}))
check("it rests on exactly what the chapter's own teaching rests on",
      {tuple(block["provenance"]["grounded_in_source_chunk_ids"]) for block in class_blocks}
      == {tuple(teaching[0]["provenance"]["grounded_in_source_chunk_ids"])})
check("and says what it is, so nobody has to guess later",
      all(contract.SCHEMA_VERSION in block["provenance"]["generation_reason"]
          for block in class_blocks))


print("\nclass lessons ADD; the enrichment's own material stays exactly where it was")

plain = export5(lessons={})
plain_sections = {block["section"] for block in plain["teaching_document"]["blocks"]}
report = enrichment_comparison.compare(plain, package)

check("the chapter's overview, method, goals, mistakes and practice plan are all still there",
      {"overview", "core_method", "learning_goals", "common_mistakes", "practice_plan"}
      <= plain_sections & {block["section"] for block in blocks},
      str(sorted(plain_sections)))
check("every block the enrichment produced survives, unchanged",
      all(block in blocks for block in plain["teaching_document"]["blocks"]))
check("so a re-export reads as twelve added and nothing removed",
      enrichment_comparison.summary(report) == "12 added, 0 removed",
      enrichment_comparison.summary(report))

try:
    enrichment_comparison.assert_additive(report)
    check("which is an enrichment, and ships", True)
except enrichment_comparison.EnrichmentRemovedContent as error:
    check("which is an enrichment, and ships", False, str(error)[:160])

check("teaching that arrived is teaching the fingerprint covers",
      plain["content_hash"] != package["content_hash"])

one_concept = export5(lessons=only(CH5_LESSONS, DECLARED[:1]))
one_blocks = [
    block for block in one_concept["teaching_document"]["blocks"]
    if block["section"] == td.CLASS_LESSON_SECTION
]

check("a concept nobody has run the transform stage for is silence, not a refusal",
      {block["teaches"] for block in one_blocks} == {DECLARED[0]},
      str(sorted({block["teaches"] for block in one_blocks})))
check("and the concept it was run for keeps everything it had, in the same place",
      one_blocks
      == [block for block in class_blocks if block["teaches"] == DECLARED[0]],
      f"{len(one_blocks)} blocks")


print("\nand the export finds them where the transform stage leaves them, unasked")

scratch = Path(tempfile.mkdtemp())
(scratch / "output").mkdir()
(scratch / "output" / "math5a.chapter05.class_lessons.json").write_text(
    json.dumps(only(CH5_LESSONS, DECLARED), ensure_ascii=False), encoding="utf-8"
)
here = Path.cwd()

try:
    os.chdir(scratch)
    discovered = ex.export_chapter(
        "math5a",
        5,
        CH5_SOURCE,
        manifest=CH5_MANIFEST,
        teaching_document=CH5_COACH,
        practice_items=ITEMS,
        asset_base=FIXTURES,
    )
finally:
    os.chdir(here)
    shutil.rmtree(scratch, ignore_errors=True)

check("nobody has to point the exporter at them",
      discovered["content_hash"] == package["content_hash"], discovered["content_hash"][:12])


print("\na chapter with no class lessons exports exactly as it did before this existed")

CH3_SOURCE = read(ROOT / "output" / "math5a.chapter03.book_learning_materials.json")
CH3_COACH = read(ROOT / "output" / "math5a.chapter03.enrichment.json")
CH3_MANIFEST_PATH = ROOT / "manifests" / "math5a.chapter03.export_manifest.json"
CH3_MANIFEST = read(CH3_MANIFEST_PATH)
CH3_HASH = "0cc0598abed2181027b35f9602e287aa06b9c90469ef52566c4fc52f9fa00a73"


def export3(**kwargs):
    return ex.export_chapter(
        "math5a",
        3,
        CH3_SOURCE,
        manifest=CH3_MANIFEST,
        teaching_document=CH3_COACH,
        practice_items=ITEMS,
        asset_base=CH3_MANIFEST_PATH.parent,
        **kwargs,
    )


chapter3 = export3()

check("chapter 3 has no class lessons to read",
      not class_lesson_store.store_path("math5a", 3).exists(),
      str(class_lesson_store.store_path('math5a', 3)))
check("and exports at the fingerprint it has always exported at",
      chapter3["content_hash"] == CH3_HASH, chapter3["content_hash"][:12])
check("no block in it belongs to a concept",
      all("teaches" not in block and "concept_stable_key" not in block
          for block in chapter3["teaching_document"]["blocks"]))
check("looking for class lessons and finding none is the same as being told there are none",
      export3(class_lessons={})["content_hash"] == CH3_HASH)

on_disk = ROOT / "output" / "math5a.chapter03.package.json"

if on_disk.exists():
    check("and the package on disk is byte-for-byte what this export produces",
          json.dumps(read(on_disk), ensure_ascii=False, sort_keys=True)
          == json.dumps(chapter3, ensure_ascii=False, sort_keys=True))
else:
    print("  [ -- ] no package at output/math5a.chapter03.package.json to compare against; "
          "the fingerprint above is the check that ran")


print("\napproval is not the exporter's to grant, and class lessons are not a way round it")

check("chapter 5's real mapping is still a draft nobody has approved",
      CH5_MAPPING.get("approved") is not True, str(CH5_MAPPING.get("approved")))

try:
    export5(manifest=CH5_MAPPING)
    check("an unapproved mapping is refused even though the class lessons are real", False,
          "it exported")
except manifest_module.ManifestUnapproved as error:
    check("an unapproved mapping is refused even though the class lessons are real", True)
    check("and the refusal says a person has to read it first",
          "approved" in str(error) and "publishing it would put a guess in front of a learner"
          in str(error), str(error)[:160])

unapproved = copy(CH5_MANIFEST)
unapproved["approved"] = False

try:
    export5(manifest=unapproved)
    check("flipping approval off refuses the same way", False, "it exported")
except manifest_module.ManifestUnapproved:
    check("flipping approval off refuses the same way", True)


print("\na class lesson that does not belong here is refused, never filed anyway")

elsewhere = {**copy(CH5_LESSONS), "lesson_stable_key": "math5a:ch07"}

try:
    export5(lessons=elsewhere)
    check("another chapter's class lessons are refused", False, "they were published")
except ex.ExportRefused as error:
    check("another chapter's class lessons are refused", True)
    check("and the refusal names both chapters",
          "math5a:ch07" in str(error) and "math5a:ch05" in str(error), str(error)[:200])

unknown_shape = {**copy(CH5_LESSONS), "schema_version": "class_lesson_set.v2"}

try:
    export5(lessons=unknown_shape)
    check("a store this code does not understand is refused", False, "it was published")
except ex.ExportRefused as error:
    check("a store this code does not understand is refused", True, str(error)[:120])

try:
    export5(lessons=CH5_LESSONS)
    check("a class lesson for a concept the mapping does not declare is refused", False,
          "the other three were dropped in silence")
except ex.ExportRefused as error:
    check("a class lesson for a concept the mapping does not declare is refused", True)
    check("and the refusal names every one that would have been dropped",
          all(key in str(error) for key in set(lessons) - set(DECLARED)), str(error)[:240])

moved_statement = copy(CH5_MANIFEST)
moved_statement["concepts"][0]["statement"] = "You will find the area of any triangle."

try:
    export5(manifest=moved_statement)
    check("a lesson written against a statement that has since moved is refused", False,
          "it shipped teaching the card no longer claims")
except ex.ExportRefused as error:
    check("a lesson written against a statement that has since moved is refused", True)
    check("and the refusal says the statement is approved before the run, not after",
          "not the generator's to rewrite" in str(error), str(error)[:200])

incomplete = copy(CH5_LESSONS)
incomplete["concepts"][DECLARED[0]]["class_lesson"]["worked_examples"][0]["annotations"] = []

try:
    export5(lessons=only(incomplete, DECLARED))
    check("a lesson missing a part the contract requires is refused", False, "it was published")
except ex.ExportRefused as error:
    check("a lesson missing a part the contract requires is refused", True)
    check("and the refusal names the concept and the gap",
          DECLARED[0] in str(error) and "annotations" in str(error), str(error)[:200])

drawn = copy(CH5_LESSONS)
drawn["concepts"][DECLARED[0]]["class_lesson"]["goal"] = "See triangle-height.svg for the picture."

try:
    export5(lessons=only(drawn, DECLARED))
    check("a class lesson that drew a picture is refused", False, "the picture was published")
except ex.ExportRefused as error:
    check("a class lesson that drew a picture is refused", True)
    check("and the refusal says where pictures actually come from",
          "asset channel" in str(error), str(error)[:200])

unattributed = copy(CH5_MANIFEST)
unattributed.pop("class_lessons")

try:
    export5(manifest=unattributed)
    check("class lessons with no declared generator are refused", False,
          "an authorship claim was invented")
except ex.ExportRefused as error:
    check("class lessons with no declared generator are refused", True)
    check("and the refusal says why RAG will not fill it in",
          "inventing a fact about authorship" in str(error), str(error)[:200])

check("a mapping that says a generator was named, with no name in it, is invalid",
      any("class_lessons.generator_version" in problem
          for problem in manifest_module.validate({**copy(CH5_MANIFEST), "class_lessons": {}})),
      str(manifest_module.validate({**copy(CH5_MANIFEST), "class_lessons": {}})))


print("\nand a block cannot belong to a concept the package does not carry")

orphaned = copy(package)
orphaned["teaching_document"]["blocks"][-1]["teaches"] = "math5a:ch05:not-a-concept"
problems = lesson_package.structural_problems(orphaned)

check("the package refuses it structurally",
      any("math5a:ch05:not-a-concept" in problem for problem in problems), str(problems[:2]))

blank = copy(package)
blank["teaching_document"]["blocks"][-1]["teaches"] = ""

check("and a block that says it belongs to a concept must name one",
      any("teaches is empty" in problem
          for problem in lesson_package.structural_problems(blank)),
      str(lesson_package.structural_problems(blank)[:2]))


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "class lessons cross, and nothing beside them moved")
raise SystemExit(1 if fails else 0)
