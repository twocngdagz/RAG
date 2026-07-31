"""The chapter mapping is declared, never inferred.

RAG's chapters carry no stable keys, no objective statements and no objective
references. An exporter that filled those gaps by reading explanations or by
taking whichever objective sits nearest a question would publish an alignment
nobody authored — and every piece of evidence a learner produced afterwards
would be recorded against a goal that may have nothing to do with what they did.

So: an unmapped chapter is refused, a mapping that does not say enough is
refused, and nothing is derived from text, position or proximity.

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
FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "b11"
SOURCE = json.loads((FIXTURES / "math5a.chapter03.book_learning_materials.json").read_text())
REAL_MANIFEST = json.loads((FIXTURES / "math5a.chapter03.export_manifest.json").read_text())


def export_with(manifest: dict):
    """Export the fixture chapter under a modified mapping."""
    return ex.export_chapter("math5a", 3, SOURCE, manifest=manifest)


print("a declared mapping exports")

package = ex.export_chapter("math5a", 3, SOURCE, manifest=REAL_MANIFEST)

check("one chapter becomes one lesson", package["lesson"]["stable_key"] == "math5a:ch03", str(package["lesson"]))
check("objectives come from the manifest", len(package["objectives"]) == 2, str(len(package["objectives"])))
check(
    "each activity keeps the alignment it declared",
    [[a["objective_stable_key"] for a in act["objective_alignments"]] for act in package["activities"]]
    == [["math5a:ch03:fraction-as-division"], ["math5a:ch03:unlike-fractions"]],
)
check(
    "blocks live inside the activity definition",
    all(act["definition"]["presentation"]["blocks"] for act in package["activities"]),
)
check(
    "a grounded block keeps the book's chunk references",
    package["activities"][0]["definition"]["presentation"]["blocks"][0]["provenance"]["source_chunk_ids"],
)
check(
    "the source resource identity B11.1 needs is carried",
    package["activities"][0]["definition"]["presentation"]["blocks"][0]["provenance"]["source_resource_id"]
    == "math5a:book",
)
check("the assembled package is structurally usable", ex.lesson_package.structural_problems(package) == [])

again = ex.export_chapter("math5a", 3, SOURCE, manifest=REAL_MANIFEST)
check("exporting twice gives the same hash", again["content_hash"] == package["content_hash"])


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

no_alignment = json.loads(json.dumps(REAL_MANIFEST))
no_alignment["activities"][0]["objective_alignments"] = []

try:
    export_with(no_alignment)
    check("an activity with no alignment is refused", False, "it exported")
except manifest_module.ManifestInvalid as error:
    check("an activity with no alignment is refused", True)
    check("the refusal rules out an all-to-all fallback", "fallback" in str(error), str(error)[:140])

no_statement = json.loads(json.dumps(REAL_MANIFEST))
no_statement["objectives"][0]["statement"] = ""

try:
    export_with(no_statement)
    check("an objective with no statement is refused", False, "it exported")
except manifest_module.ManifestInvalid as error:
    check("an objective with no statement is refused", True, str(error)[:100])

dangling = json.loads(json.dumps(REAL_MANIFEST))
dangling["activities"][0]["objective_alignments"][0]["objective_stable_key"] = "math5a:ch03:nowhere"

try:
    export_with(dangling)
    check("an alignment to an undeclared objective is refused", False, "it exported")
except manifest_module.ManifestInvalid as error:
    check("an alignment to an undeclared objective is refused", True, str(error)[:100])

drifted = json.loads(json.dumps(REAL_MANIFEST))
drifted["activities"][0]["elements"] = ["core_lessons.99.explanation"]

try:
    export_with(drifted)
    check("a reference that no longer resolves is refused", False, "it exported")
except ex.ExportRefused as error:
    check("a reference that no longer resolves is refused", True)
    check(
        "the refusal names the element and the path",
        "core_lessons.99" in str(error) and "activities.0" in str(error),
        str(error)[:140],
    )


print("\nmanually_authored requires evidence of authorship")

anonymous = json.loads(json.dumps(REAL_MANIFEST))
anonymous.pop("authored_by")

try:
    export_with(anonymous)
    check("an unattributed manifest is refused", False, "it exported")
except ex.ExportRefused as error:
    check("an unattributed manifest is refused", True)
    check(
        "the refusal says authorship cannot be assumed",
        "who wrote it" in str(error),
        str(error)[:140],
    )

check(
    "authorship is recorded, not inferred",
    package["objectives"][0]["provenance"]["author_reference"] == "ela:content-team",
    str(package["objectives"][0]["provenance"]),
)
check(
    "no block claims manual authorship",
    all(
        block["provenance"]["origin"] != "manually_authored"
        for act in package["activities"]
        for block in act["definition"]["presentation"]["blocks"]
    ),
    "book content is grounded, not authored",
)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the mapping is declared, not inferred")
raise SystemExit(1 if fails else 0)
