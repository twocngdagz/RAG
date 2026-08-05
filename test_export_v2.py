"""The v2 package: the whole lesson crosses, and enrichment cannot erase.

v1 shipped a sample — whichever chapter claims a manifest named, arranged as two
activities. A learner cannot be taught from a sample, so v2 carries the taught
thing whole: every Coach section as ordered blocks, every concept as the
schedulable card it is, every concept's question bank, and the pictures, inside
the file.

Four properties, and the fourth is the one that has teeth. A re-export that
quietly dropped a worked example would look exactly like a successful
enrichment, and Ela would import the loss as a revision without a second
thought. So removal is caught here, named, and refused.

    python test_export_v2.py
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import enrichment_comparison
import export_lesson_package as ex
import lesson_package
import teaching_document as td

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures" / "b17"
# The chapter material is untouched by B17 — v2 changes what a package carries,
# not what the generator produces — so the committed chapter is B11's.
SOURCE = json.loads((ROOT / "tests" / "fixtures" / "b11" / "math5a.chapter03.book_learning_materials.json").read_text())
MANIFEST = json.loads((FIXTURES / "math5a.chapter03.export_manifest.json").read_text())
COACH = json.loads((FIXTURES / "math5a.chapter03.enrichment.json").read_text())
ITEMS = json.loads((FIXTURES / "math_practice_items.json").read_text())


def export(*, manifest=MANIFEST, document=COACH, items=ITEMS):
    return ex.export_chapter(
        "math5a",
        3,
        SOURCE,
        manifest=manifest,
        teaching_document=document,
        practice_items=items,
        asset_base=FIXTURES,
    )


def copy(value):
    return json.loads(json.dumps(value))


package = export()


print("every Coach section becomes blocks, in the Coach's own order")

blocks = package["teaching_document"]["blocks"]
sections = [block["section"] for block in blocks]

check("the package names its schema", package["schema_version"] == "learning.package.v2", str(package["schema_version"]))
check(
    "every section the document carries is published",
    {section for section in td.SECTION_ORDER if COACH.get(section)} == set(sections),
    str(sorted(set(sections))),
)
check(
    "sections come in the order the Coach page renders them",
    [section for section in td.SECTION_ORDER if section in sections]
    == list(dict.fromkeys(sections)),
    str(list(dict.fromkeys(sections))),
)
check(
    "positions are stated, not implied",
    [block["position"] for block in blocks] == list(range(len(blocks))),
    str([block["position"] for block in blocks][:6]),
)
check(
    "each worked example is its own block",
    sections.count("worked_examples") == len(COACH["worked_examples"]),
    f"{sections.count('worked_examples')} blocks for {len(COACH['worked_examples'])} examples",
)
check(
    "each technique explaining a concept is its own block",
    sections.count("techniques") == len(COACH["techniques"]),
    f"{sections.count('techniques')} blocks for {len(COACH['techniques'])} techniques",
)
check(
    "each mistake to avoid is its own block",
    sections.count("common_mistakes") == len(COACH["common_mistakes"]),
    f"{sections.count('common_mistakes')} blocks for {len(COACH['common_mistakes'])} mistakes",
)
check(
    "the method is one block",
    sections.count("core_method") == 1,
    str(sections.count("core_method")),
)

example = next(block for block in blocks if block["section"] == "worked_examples")

check(
    "a worked example carries its decoding, its plan and its annotations",
    bool(example["content"]["decoding"])
    and bool(example["content"]["plan"])
    and bool(example["content"]["annotations"]),
    str(sorted(example["content"])),
)
check(
    "the model answer travels with it",
    bool(example["content"]["model_answer"]),
    str(example["content"].get("model_answer"))[:60],
)
check(
    "every block says where it came from",
    all(block["provenance"]["origin"] == "pedagogical_generation" for block in blocks),
    str({block["provenance"]["origin"] for block in blocks}),
)
check(
    "and what it was written from",
    all(block["provenance"]["grounded_in_source_chunk_ids"] for block in blocks),
)

unknown_section = {**copy(COACH), "vocabulary_drills": ["something new"]}

try:
    export(document=unknown_section)
    check("a section this exporter cannot publish is refused", False, "it exported without it")
except ex.ExportRefused as error:
    check("a section this exporter cannot publish is refused", True)
    check(
        "the refusal says why dropping it silently is worse",
        "vocabulary_drills" in str(error) and "drop teaching" in str(error),
        str(error)[:160],
    )

missing_examples = copy(COACH)
missing_examples["worked_examples"] = []

try:
    export(document=missing_examples)
    check("a document with no worked examples is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a document with no worked examples is refused", True, str(error)[:100])

other_chapter = {**copy(COACH), "source_label": "math5a:ch07"}

try:
    export(document=other_chapter)
    check("another chapter's teaching is refused", False, "it exported")
except ex.ExportRefused as error:
    check("another chapter's teaching is refused", True)
    check(
        "the refusal says whose teaching it would have attached",
        "math5a:ch07" in str(error),
        str(error)[:160],
    )


print("\nconcepts are first-class, and each carries its bank")

concepts = package["concepts"]
banks = {concept["stable_key"]: concept["exercises"] for concept in concepts}

check("five concepts", len(concepts) == 5, str(len(concepts)))
check(
    "every concept states what a learner will be able to do",
    all(concept["statement"].strip() for concept in concepts),
)
check(
    "the statement is written once — the concept IS the objective",
    "objectives" not in package,
    str(sorted(package)),
)
check(
    "forty-three exercises, in their banks",
    sum(len(bank) for bank in banks.values()) == 43,
    str({key: len(bank) for key, bank in banks.items()}),
)
check(
    "every concept's bank has questions in it",
    all(bank for bank in banks.values()),
    str({key: len(bank) for key, bank in banks.items()}),
)
check(
    "each exercise assesses the concept whose bank it is in",
    all(
        alignment["objective_stable_key"] == key and alignment["alignment_role"] == "assesses"
        for key, bank in banks.items()
        for exercise in bank
        for alignment in exercise["objective_alignments"][:1]
    ),
)
check(
    "no exercise gains an alignment nobody declared",
    all(len(exercise["objective_alignments"]) == 1 for bank in banks.values() for exercise in bank),
)

exercise = banks["math5a:ch03:add-unlike-fractions"][0]
marking = exercise["definition"]["evaluation"]["marking"]

check(
    "an exercise is a complete activity definition",
    exercise["definition"]["contract"] == "learning.activity.v1",
    str(exercise["definition"].get("contract")),
)
check("it asks a question", bool(exercise["definition"]["presentation"]["blocks"][0]["content"]["text"]))
check("it collects an answer", exercise["definition"]["response"]["required"] is True)
check("it is marked deterministically", exercise["definition"]["evaluation"]["authority"] == "deterministic")
check("one generic numeric marker, named", marking["marker"] == "ela.math.numeric", str(marking.get("marker")))
check(
    "the computed answer travels with the question",
    bool(marking["expected"]["plain"]) and marking["expected"]["numerator"] is not None,
    str(marking.get("expected")),
)
check(
    "and the sum that re-derives it",
    bool(marking.get("verified_by")),
    str(marking.get("verified_by")),
)
check(
    "a returning card can ask a different question each time",
    len({exercise["stable_key"] for exercise in banks["math5a:ch03:add-unlike-fractions"]}) > 1,
)
check(
    "help on struggle is linked, and says what using it costs",
    all(
        link["resource_stable_key"] == "math5a:ch03:review-checklist"
        for bank in banks.values()
        for exercise in bank
        for link in exercise["resource_links"]
    ),
)

empty_bank = copy(MANIFEST)
empty_bank["concepts"][0]["bank"]["skill"] = "long_division"

try:
    export(manifest=empty_bank)
    check("a concept with nothing to ask is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a concept with nothing to ask is refused", True)
    check(
        "the refusal says what an empty bank would mean",
        "can never be asked" in str(error),
        str(error)[:160],
    )

foreign_items = copy(ITEMS)

for item in foreign_items:
    item["chapter"] = 7

try:
    export(items=foreign_items)
    check("questions from another chapter are refused", False, "it exported")
except ex.ExportRefused as error:
    check("questions from another chapter are refused", True, str(error)[:120])


print("\nthe pictures ride inside the file, and the hash covers them")

assets = {asset["stable_key"]: asset for asset in package["assets"]}
svg = assets["math5a:ch03:asset:three-quarters-bar"]
raster = assets["math5a:ch03:asset:two-thirds-photo"]

check("SVG rides as text", svg["encoding"] == "inline_svg" and svg["svg"].startswith("<svg"), svg["encoding"])
check("raster rides as base64", raster["encoding"] == "base64", raster["encoding"])
check(
    "the encoded bytes are the file's bytes",
    base64.b64decode(raster["content"]) == (FIXTURES / "two-thirds.png").read_bytes(),
)
check(
    "every picture is described for a learner who cannot see it",
    all(asset["alt_text"] and asset["caption"] for asset in package["assets"]),
)
check(
    "every picture says where it came from",
    {asset["provenance"]["origin"] for asset in package["assets"]}
    == {"pedagogical_generation", "manually_authored"},
    str({asset["provenance"]["origin"] for asset in package["assets"]}),
)
check("every picture says what it illustrates", all(asset["illustrates"] for asset in package["assets"]))

check("the same inputs export to the same hash", export()["content_hash"] == package["content_hash"])
check(
    "the file states its own fingerprint",
    lesson_package.content_hash(package) == package["content_hash"],
)
check(
    "re-serialising the same package does not move it",
    lesson_package.content_hash(dict(reversed(list(package.items())))) == package["content_hash"],
    "key order is canonicalised; block order is not",
)

repainted = copy(MANIFEST)
repainted["assets"][0]["svg"] = repainted["assets"][0]["svg"].replace("#cfe8ff", "#ffd8b1")
recoloured = export(manifest=repainted)

check(
    "changing one byte of a diagram changes the hash",
    recoloured["content_hash"] != package["content_hash"],
    "a picture is content, not decoration",
)

without_pictures = copy(MANIFEST)
without_pictures["assets"] = []

check(
    "removing the pictures changes the hash",
    export(manifest=without_pictures)["content_hash"] != package["content_hash"],
)

reworded = copy(COACH)
reworded["core_method"]["summary"] = reworded["core_method"]["summary"] + " Take your time."

check(
    "a changed word in the teaching changes the hash",
    export(document=reworded)["content_hash"] != package["content_hash"],
)

reordered = copy(COACH)
reordered["worked_examples"] = [reordered["worked_examples"][1], reordered["worked_examples"][0]] + reordered["worked_examples"][2:]

check(
    "teaching in a different order is a different lesson",
    export(document=reordered)["content_hash"] != package["content_hash"],
)

check("the whole package is structurally importable", lesson_package.structural_problems(package) == [])


print("\nenrichment adds — and a re-export proves it, or refuses")

richer_document = copy(COACH)
richer_document["worked_examples"].append(
    {
        "title": "Add three eighths and one quarter",
        "input": "Work out $\\frac{3}{8} + \\frac{1}{4}$.",
        "decoding": "The bottom numbers are different, so they must be made to match.",
        "plan": "Change one quarter into two eighths, then add the top numbers.",
        "model_answer": "$\\frac{1}{4} = \\frac{2}{8}$, so $\\frac{3}{8} + \\frac{2}{8} = \\frac{5}{8}$.",
        "annotations": [{"part": "$\\frac{2}{8}$", "comment": "The same amount, written in eighths."}],
    }
)

enriched = export(document=richer_document)
report = enrichment_comparison.compare(package, enriched)

check("one more example reads as one addition", enrichment_comparison.summary(report) == "1 added, 0 removed", enrichment_comparison.summary(report))
check("and the addition is the example that was added", "eighths" in report["added"][0], str(report["added"]))

try:
    enrichment_comparison.assert_additive(report)
    check("an additive re-export ships", True)
except enrichment_comparison.EnrichmentRemovedContent as error:
    check("an additive re-export ships", False, str(error)[:120])

richer_still = copy(MANIFEST)
richer_still["assets"].append(
    {
        "stable_key": "math5a:ch03:asset:eighths-bar",
        "media_type": "image/svg+xml",
        "illustrates": "math5a:ch03:add-unlike-fractions",
        "alt_text": "A bar in eighths with five parts shaded.",
        "caption": "Three eighths and two eighths make five eighths.",
        "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 80 20\"><rect width=\"50\" height=\"20\" fill=\"#cfe8ff\"/></svg>",
        "provenance": {
            "origin": "pedagogical_generation",
            "grounded_in_source_chunk_ids": [],
            "generation_reason": "A bar model for the added example",
            "generator_version": "rag-diagrams/0.0.0-fixture",
        },
    }
)

with_picture = enrichment_comparison.compare(package, export(manifest=richer_still))

check(
    "an added picture counts as an addition, because it is inside the thing compared",
    enrichment_comparison.summary(with_picture) == "1 added, 0 removed",
    enrichment_comparison.summary(with_picture),
)

poorer_document = copy(COACH)
dropped = poorer_document["worked_examples"].pop(3)
poorer = export(document=poorer_document)
loss = enrichment_comparison.compare(package, poorer)

check("a dropped example is counted", enrichment_comparison.summary(loss) == "0 added, 1 removed", enrichment_comparison.summary(loss))

try:
    enrichment_comparison.assert_additive(loss)
    check("a re-export that erases teaching is refused", False, "it shipped as an enrichment")
except enrichment_comparison.EnrichmentRemovedContent as error:
    check("a re-export that erases teaching is refused", True)
    check("the refusal names what went missing", dropped["title"][:20] in str(error), str(error)[:200])
    check(
        "and says what the honest way to remove something is",
        "edit" in str(error),
        str(error)[:200],
    )

swapped_document = copy(COACH)
swapped_document["worked_examples"][2] = {
    "title": "A different example entirely",
    "input": "Work out $\\frac{1}{2} + \\frac{1}{2}$.",
    "decoding": "The bottom numbers already match.",
    "plan": "Add the top numbers.",
    "model_answer": "$\\frac{1}{2} + \\frac{1}{2} = 1$.",
    "annotations": [],
}
swap = enrichment_comparison.compare(package, export(document=swapped_document))

check(
    "swapping one example out for another is a removal, not a wash",
    len(swap["removed"]) == 1 and len(swap["added"]) == 1,
    enrichment_comparison.summary(swap),
)

dropped_concept = copy(MANIFEST)
dropped_concept["concepts"] = dropped_concept["concepts"][:-1]
shrunk = enrichment_comparison.compare(package, export(manifest=dropped_concept))

check(
    "dropping a concept takes its whole bank with it, and all of it is counted",
    len(shrunk["removed"]) == 1 + len(banks["math5a:ch03:divide-fraction-by-whole"]),
    f"{enrichment_comparison.summary(shrunk)}: {shrunk['removed'][:3]}",
)

try:
    enrichment_comparison.compare({"schema_version": "learning.package.v1", "lesson": package["lesson"]}, package)
    check("a v1 package is not an enrichment baseline", False, "it was compared")
except enrichment_comparison.PreviousPackageIncomparable as error:
    check("a v1 package is not an enrichment baseline", True)
    check(
        "the refusal says a format change is not an enrichment",
        "learning.package.v1" in str(error) and "not an enrichment" in str(error),
        str(error)[:160],
    )

try:
    enrichment_comparison.compare({**copy(package), "lesson": {"stable_key": "math5a:ch07"}}, package)
    check("another lesson is not an enrichment baseline", False, "it was compared")
except enrichment_comparison.PreviousPackageIncomparable as error:
    check("another lesson is not an enrichment baseline", True, str(error)[:120])


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the v2 package carries the whole lesson, and cannot lose it")
raise SystemExit(1 if fails else 0)
