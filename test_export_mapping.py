"""The chapter mapping is declared, never inferred.

RAG's chapters carry no stable keys, no concept statements and no objective
references. An exporter that filled those gaps by reading explanations or by
taking whichever concept sits nearest a question would publish an alignment
nobody authored — and every piece of evidence a learner produced afterwards
would be recorded against a goal that may have nothing to do with what they did.

So: an unmapped chapter is refused, a mapping that does not say enough is
refused, and nothing is derived from text, position or proximity.

The one thing v2 DOES derive is an exercise's alignment — from the bank it sits
in. That is not proximity: putting a question in a concept's bank is the author
saying what it assesses, in the manifest, in as many words.

    python test_export_mapping.py
"""
from __future__ import annotations

import json
from pathlib import Path

import export_lesson_package as ex
import lesson_export_manifest as manifest_module

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


# Committed fixtures, not output/ — that directory is gitignored, so a test
# reading from it passes here and finds nothing on a clean checkout.
ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures" / "b17"
SOURCE = json.loads((ROOT / "tests" / "fixtures" / "b11" / "math5a.chapter03.book_learning_materials.json").read_text())
REAL_MANIFEST = json.loads((FIXTURES / "math5a.chapter03.export_manifest.json").read_text())
COACH = json.loads((FIXTURES / "math5a.chapter03.enrichment.json").read_text())
ITEMS = json.loads((FIXTURES / "math_practice_items.json").read_text())


def export_with(manifest: dict):
    """Export the fixture chapter under a modified mapping."""
    return ex.export_chapter(
        "math5a",
        3,
        SOURCE,
        manifest=manifest,
        teaching_document=COACH,
        practice_items=ITEMS,
        asset_base=FIXTURES,
    )


print("a declared mapping exports")

package = export_with(REAL_MANIFEST)

check("one chapter becomes one lesson", package["lesson"]["stable_key"] == "math5a:ch03", str(package["lesson"]))
check("concepts come from the manifest", len(package["concepts"]) == 5, str(len(package["concepts"])))
# Compared against the MANIFEST rather than a copy of its values: the property
# is that the export preserves what was declared, and restating the expected
# statements here would pass even if both drifted together.
check(
    "every concept keeps the statement that was authored for it",
    [concept["statement"] for concept in package["concepts"]]
    == [declared["statement"] for declared in REAL_MANIFEST["concepts"]],
)
check(
    "and the stable key, in the declared order",
    [concept["stable_key"] for concept in package["concepts"]]
    == [declared["stable_key"] for declared in REAL_MANIFEST["concepts"]],
)
check(
    "each exercise assesses the concept whose bank declared it, and nothing else",
    all(
        [alignment["objective_stable_key"] for alignment in exercise["objective_alignments"]]
        == [concept["stable_key"]]
        for concept in package["concepts"]
        for exercise in concept["exercises"]
    ),
)
check(
    "every bank draws only on the skill it declared",
    all(
        declared["bank"]["skill"] in exercise["stable_key"]
        for concept, declared in zip(package["concepts"], REAL_MANIFEST["concepts"])
        for exercise in concept["exercises"]
    ),
)
check(
    "blocks live inside the exercise definition",
    all(
        exercise["definition"]["presentation"]["blocks"]
        for concept in package["concepts"]
        for exercise in concept["exercises"]
    ),
)

resource_block = package["resources"][0]["definition"]["definition"]["blocks"][0]

check("a grounded resource block keeps the book's chunk references", bool(resource_block["provenance"]))
check(
    "the source resource identity the importer needs is carried",
    resource_block["provenance"].get("source_resource_id", "math5a:book") == "math5a:book",
    str(resource_block["provenance"]),
)
check("the assembled package is structurally usable", ex.lesson_package.structural_problems(package) == [])
check("exporting twice gives the same hash", export_with(REAL_MANIFEST)["content_hash"] == package["content_hash"])


print("\nan unmapped chapter is refused, not guessed at")

try:
    ex.export_chapter("math5a", 1, SOURCE)
    check("a chapter with no manifest is refused", False, "it exported")
except manifest_module.ManifestMissing as error:
    check("a chapter with no manifest is refused", True)
    check("the refusal says why guessing is worse", "invented" in str(error), str(error)[:120])
except ex.ExportRefused as error:
    check("a chapter with no manifest is refused", True, str(error)[:80])


print("\na mapping that does not say enough is refused")


def refuses(manifest: dict, label: str, fragment: str = "") -> None:
    try:
        export_with(manifest)
        check(label, False, "it exported")
    except (manifest_module.ManifestInvalid, ex.ExportRefused) as error:
        check(label, True)

        if fragment:
            check(f"...and names the gap: {fragment}", fragment in str(error), str(error)[:160])


def without(path: list, value=None) -> dict:
    """The real manifest with one thing changed, so each refusal has one cause."""
    manifest = json.loads(json.dumps(REAL_MANIFEST))
    node = manifest

    for segment in path[:-1]:
        node = node[segment]

    if value is None:
        node.pop(path[-1], None)
    else:
        node[path[-1]] = value

    return manifest


refuses(without(["concepts", 0, "bank"]), "a concept with no bank is refused", "card with nothing to ask")
refuses(without(["concepts", 0, "statement"], ""), "a concept with no statement is refused", "statement is missing")
refuses(
    without(["concepts", 0, "bank", "evaluation"], {"authority": "deterministic"}),
    "a bank that marks deterministically but names no marker is refused",
    "names no marker",
)
refuses(without(["concepts"], []), "a mapping that introduces no concepts is refused", "teaches nothing")
refuses(
    without(["teaching_document"], {}),
    "a mapping that will not say which run wrote the teaching is refused",
    "may not invent one",
)
refuses(
    without(["concepts", 0, "bank", "also_aligns_to"], [{"objective_stable_key": "math5a:ch03:nowhere", "alignment_role": "assesses"}]),
    "a capstone alignment to an undeclared concept is refused",
    "does not declare",
)
refuses(
    without(["resources", 0, "elements"], ["review_checklist.99"]),
    "a resource reference that no longer resolves is refused",
    "review_checklist.99",
)


print("\nmanually_authored requires evidence of authorship")

anonymous = json.loads(json.dumps(REAL_MANIFEST))
anonymous.pop("authored_by")

try:
    export_with(anonymous)
    check("an unattributed manifest is refused", False, "it exported")
except ex.ExportRefused as error:
    check("an unattributed manifest is refused", True)
    check("the refusal says authorship cannot be assumed", "who wrote it" in str(error), str(error)[:140])

check(
    "authorship is recorded, not inferred",
    package["concepts"][0]["provenance"]["author_reference"] == "ela:content-team",
    str(package["concepts"][0]["provenance"]),
)
check(
    "no teaching block claims a person wrote the generated lesson",
    all(
        block["provenance"]["origin"] != "manually_authored"
        for block in package["teaching_document"]["blocks"]
    ),
    "the Coach document was generated, and says so",
)
check(
    "no exercise claims a person wrote a computed question",
    all(
        exercise["definition"]["provenance"]["origin"] == "pedagogical_generation"
        for concept in package["concepts"]
        for exercise in concept["exercises"]
    ),
)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the mapping is declared, not inferred")
raise SystemExit(1 if fails else 0)
