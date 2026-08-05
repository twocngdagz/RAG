"""One complete chapter, exercising every relationship the importer has to build.

The importer's job, stated as relationships: each concept becomes a schedulable
card tied 1:1 to its objective; the card's bank hangs under it; the teaching
document stores as ordered blocks; a resource carries lesson-level link
semantics including what using it costs; pictures come out of the file rather
than off a network; and every element says where it came from.

A teaching-only slice would prove none of that. The half the importer depends on
is exactly the half a teaching-only slice leaves out.

    python test_representative_package.py
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import export_lesson_package as ex
import lesson_package

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures" / "b17"
SOURCE = json.loads((ROOT / "tests" / "fixtures" / "b11" / "math5a.chapter03.book_learning_materials.json").read_text())
MANIFEST = json.loads((FIXTURES / "math5a.chapter03.export_manifest.json").read_text())
COACH = json.loads((FIXTURES / "math5a.chapter03.enrichment.json").read_text())
ITEMS = json.loads((FIXTURES / "math_practice_items.json").read_text())


def export(manifest=MANIFEST):
    return ex.export_chapter(
        "math5a",
        3,
        SOURCE,
        manifest=manifest,
        teaching_document=COACH,
        practice_items=ITEMS,
        asset_base=FIXTURES,
    )


package = export()
resource = package["resources"][0]


print("concepts: one card, one objective, one statement")

check("the lesson introduces its concepts", len(package["concepts"]) == 5, str(len(package["concepts"])))
check(
    "every concept states what a learner can do",
    all(concept["statement"].strip() for concept in package["concepts"]),
)
check(
    "every concept says whether a learner is measured against it",
    all("assessed" in concept for concept in package["concepts"]),
    "an importer refuses to publish an assessed objective nothing can produce evidence for",
)
check(
    "keys are unique, so a card maps 1:1",
    len({concept["stable_key"] for concept in package["concepts"]}) == len(package["concepts"]),
)
check(
    "the objective graph names concepts this package defines",
    all(
        association["from_objective_stable_key"] in {c["stable_key"] for c in package["concepts"]}
        and association["to_objective_stable_key"] in {c["stable_key"] for c in package["concepts"]}
        for association in package["objective_associations"]
    ),
    str(package["objective_associations"]),
)


print("\nbanks: a returning card has somewhere to draw from")

banks = {concept["stable_key"]: concept["exercises"] for concept in package["concepts"]}

check("every card has a bank", all(banks.values()), str({k: len(v) for k, v in banks.items()}))
check("a card can ask something different next time", all(len(bank) > 1 for bank in banks.values()))
check(
    "every exercise is a complete activity definition",
    all(
        exercise["definition"]["contract"] == "learning.activity.v1"
        for bank in banks.values()
        for exercise in bank
    ),
)
check(
    "every exercise produces evidence against a named concept",
    all(
        exercise["objective_alignments"][0]["alignment_role"] == "assesses"
        for bank in banks.values()
        for exercise in bank
    ),
)
check(
    "every exercise can be marked without asking a model",
    all(
        exercise["definition"]["evaluation"]["authority"] == "deterministic"
        and exercise["definition"]["evaluation"]["marking"]["expected"]["plain"]
        for bank in banks.values()
        for exercise in bank
    ),
)
check(
    "exercise keys are unique across the whole lesson",
    len({exercise["stable_key"] for bank in banks.values() for exercise in bank})
    == sum(len(bank) for bank in banks.values()),
)


print("\nthe teaching document: the taught thing, in order")

blocks = package["teaching_document"]["blocks"]

check("it is stored as ordered blocks", [b["position"] for b in blocks] == list(range(len(blocks))))
check("every block says what kind of teaching it is", all(b["type"] for b in blocks))
check("every block is addressable", len({b["key"] for b in blocks}) == len(blocks))
check(
    "the method comes before the examples that use it",
    next(i for i, b in enumerate(blocks) if b["section"] == "core_method")
    < next(i for i, b in enumerate(blocks) if b["section"] == "worked_examples"),
    "a worked example before its method teaches backwards",
)


print("\na resource with lesson-level link semantics")

link = resource["links"][0]

check("the resource is built from real chapter content", len(resource["definition"]["definition"]["blocks"]) == 2)
check("the link is scoped to the lesson", link["scope"] == "lesson", str(link))
check("it names the lesson it belongs to", link["lesson_stable_key"] == package["lesson"]["stable_key"])
check("it declares when it may appear", bool(link.get("availability")), str(link))
check("it declares which phases may show it", bool(link.get("phase_visibility")), str(link))
check(
    "it declares what using it costs",
    link["assistance_effect"]["evidence_classification"] == "assisted",
    str(link.get("assistance_effect")),
)
check(
    "exercises link to it by key, and the key resolves",
    all(
        reference["resource_stable_key"] == resource["stable_key"]
        for bank in banks.values()
        for exercise in bank
        for reference in exercise["resource_links"]
    ),
)


print("\npictures the learner never waits for")

assets = {asset["stable_key"]: asset for asset in package["assets"]}
raster = assets["math5a:ch03:asset:two-thirds-photo"]

check("the picture is in the file, not behind a URL", "content" in raster and "url" not in raster, str(sorted(raster)))
check("its bytes survive the crossing", base64.b64decode(raster["content"]) == (FIXTURES / "two-thirds.png").read_bytes())
check("it says what it illustrates", raster["illustrates"] in {c["stable_key"] for c in package["concepts"]})
check(
    "every picture carries provenance, caption and alt text",
    all(asset["provenance"] and asset["caption"] and asset["alt_text"] for asset in package["assets"]),
)


print("\nprovenance on every element")

all_blocks = (
    [("teaching_document", block) for block in blocks]
    + [
        (exercise["stable_key"], block)
        for bank in banks.values()
        for exercise in bank
        for block in exercise["definition"]["presentation"]["blocks"]
    ]
    + [(resource["stable_key"], block) for block in resource["definition"]["definition"]["blocks"]]
)

check("every block carries an origin", all(b["provenance"].get("origin") for _, b in all_blocks), str(len(all_blocks)))
check(
    "grounded blocks name the book and its chunks",
    all(
        b["provenance"]["source_resource_id"] == "math5a:book" and b["provenance"]["source_chunk_ids"]
        for _, b in all_blocks
        if b["provenance"]["origin"] == "source_grounded"
    ),
)
check(
    "no block claims a person wrote the book's content",
    all(b["provenance"]["origin"] != "manually_authored" for _, b in all_blocks),
)
check(
    "generated content names the generator that wrote it",
    all(
        b["provenance"]["generator_version"]
        for _, b in all_blocks
        if b["provenance"]["origin"] == "pedagogical_generation"
    ),
)


print("\nstable ordering and identifiers")

again = export()

check("the same chapter exports to the same hash", again["content_hash"] == package["content_hash"])
check(
    "identifiers are stable across runs",
    [c["stable_key"] for c in again["concepts"]] == [c["stable_key"] for c in package["concepts"]],
)
check(
    "bank order is stable across runs",
    [e["stable_key"] for c in again["concepts"] for e in c["exercises"]]
    == [e["stable_key"] for c in package["concepts"] for e in c["exercises"]],
)

swapped = json.loads(json.dumps(MANIFEST))
swapped["concepts"] = [swapped["concepts"][1], swapped["concepts"][0]] + swapped["concepts"][2:]

check(
    "teaching the concepts in a different order is a different lesson",
    export(swapped)["content_hash"] != package["content_hash"],
)

check("the whole package is structurally importable", lesson_package.structural_problems(package) == [])


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the representative slice is complete")
raise SystemExit(1 if fails else 0)
