"""One complete chapter, exercising every relationship B11.1 has to import.

B11 ships ONE representative package rather than manifests for every chapter —
authoring the corpus is content work, not this batch. What this proves is that a
real chapter can cross into Ela intact: objectives, a teaching activity built
from ordered claims of several kinds, an evidence-producing activity with a
marking contract, a resource with lesson-level link semantics, provenance on
every block, and identifiers stable enough to import against twice.

A teaching-only manifest would prove none of that. The half B11.1 depends on is
exactly the half a teaching-only slice leaves out.

    python test_representative_package.py
"""
from __future__ import annotations

import json
from pathlib import Path

import export_lesson_package as ex
import lesson_package

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures" / "b11"
SOURCE = json.loads((FIXTURES / "math5a.chapter03.book_learning_materials.json").read_text())
MANIFEST = json.loads((FIXTURES / "math5a.chapter03.export_manifest.json").read_text())

package = ex.export_chapter("math5a", 3, SOURCE, manifest=MANIFEST)

teaching = next(a for a in package["activities"] if a["stable_key"] == "math5a:ch03:teach")
practice = next(a for a in package["activities"] if a["stable_key"] == "math5a:ch03:practice")
resource = package["resources"][0]


print("objectives")

check("at least one objective", len(package["objectives"]) >= 1, str(len(package["objectives"])))
check(
    "every objective states what a learner can do",
    all(o["statement"].strip() for o in package["objectives"]),
)


print("\na teaching activity built from ordered claims of several kinds")

blocks = teaching["definition"]["presentation"]["blocks"]
keys = [b["content"]["key"] for b in blocks]

check("draws on more than one kind of chapter content", len(blocks) >= 4, str(keys))
check(
    "includes a core lesson, a key term, an example and a correction",
    keys == [
        "core_lessons_0_explanation",
        "key_terms_0_meaning",
        "worked_examples_0_example",
        "common_misconceptions_0_correction",
    ],
    str(keys),
)
check(
    "keeps the declared order",
    keys.index("core_lessons_0_explanation") < keys.index("worked_examples_0_example"),
    "a worked example before its explanation teaches backwards",
)


print("\nan evidence-producing activity with a real evaluation contract")

evaluation = practice["definition"]["evaluation"]

check("collects an answer", practice["definition"]["response"]["kind"] == "short_answer", str(practice["definition"]["response"]))
check("the answer is required", practice["definition"]["response"]["required"] is True)
check("marking is deterministic", evaluation["authority"] == "deterministic", str(evaluation))
check("names a marker", bool(evaluation.get("marking", {}).get("marker")), str(evaluation))
check("names what it expects", bool(evaluation.get("marking", {}).get("expected")), str(evaluation))
check(
    "produces evidence against a named objective",
    [a["objective_stable_key"] for a in practice["objective_alignments"]] == ["math5a:ch03:unlike-fractions"],
    str(practice["objective_alignments"]),
)
check(
    "assesses rather than teaches",
    practice["objective_alignments"][0]["alignment_role"] == "assesses",
)
check(
    "the teaching activity does NOT claim to assess",
    all(a["alignment_role"] == "teaches" for a in teaching["objective_alignments"]),
    str(teaching["objective_alignments"]),
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
    "activities link to it by key, and the key resolves",
    all(
        l["resource_stable_key"] == resource["stable_key"]
        for a in package["activities"]
        for l in a["resource_links"]
    ),
)


print("\nprovenance on every block")

all_blocks = [
    (a["stable_key"], b)
    for a in package["activities"]
    for b in a["definition"]["presentation"]["blocks"]
] + [(resource["stable_key"], b) for b in resource["definition"]["definition"]["blocks"]]

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


print("\nstable ordering and identifiers")

again = ex.export_chapter("math5a", 3, SOURCE, manifest=MANIFEST)

check("the same chapter exports to the same hash", again["content_hash"] == package["content_hash"])
check(
    "identifiers are stable across runs",
    [a["stable_key"] for a in again["activities"]] == [a["stable_key"] for a in package["activities"]],
)

swapped = json.loads(json.dumps(MANIFEST))
swapped["activities"] = [swapped["activities"][1], swapped["activities"][0]]
reordered = ex.export_chapter("math5a", 3, SOURCE, manifest=swapped)

check(
    "practising before being taught is a different lesson",
    reordered["content_hash"] != package["content_hash"],
)

check("the whole package is structurally importable", lesson_package.structural_problems(package) == [])


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the representative slice is complete")
raise SystemExit(1 if fails else 0)
