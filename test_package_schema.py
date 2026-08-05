"""The emitted package: required fields, a fingerprint over the whole file, and
concepts that survive.

A package is what RAG hands Ela. It must be identifiable later — which producer,
which pack rules, which source revision — and it must be possible to tell one
file from another, because an importer that could not would store a lesson it
already had, or miss one it did not.

v2's fingerprint covers the whole file rather than a projection of chosen
identity fields, so nothing can change without the hash moving. Whether a change
is an ENRICHMENT or an erasure is a separate question with a separate answer:
`enrichment_comparison`, which compares element by element and refuses removals.

    python test_package_schema.py
"""
from __future__ import annotations

import domain_packs
import lesson_package as lp

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


PACK = domain_packs.get("math5a")

GROUNDED = {
    "origin": "source_grounded",
    "source_resource_id": "math5a:book",
    "source_chunk_ids": ["math5a:ch03:chunk14"],
}

AUTHORED = {"origin": "manually_authored", "author_reference": "ela:content-team"}

GENERATED = {
    "origin": "pedagogical_generation",
    "grounded_in_source_chunk_ids": ["math5a:ch03:chunk14"],
    "generation_reason": "Written for the learner from this chapter's pages",
    "generator_version": "math5a-pack:1.0.0",
}


def sample_teaching_document(text: str = "Four quarters make one whole.") -> dict:
    return {
        "source_label": "math5a:ch03",
        "title": "Fractions",
        "generator_version": "enrich_lessons/pte_lesson_enrichment.v1",
        "blocks": [
            {
                "key": "core_method",
                "type": "method",
                "version": 1,
                "section": "core_method",
                "position": 0,
                "content": {"name": "Match, add, simplify", "steps": [{"step": "Match", "detail": text}]},
                "provenance": GENERATED,
            },
            {
                "key": "worked_examples.0",
                "type": "worked_example",
                "version": 1,
                "section": "worked_examples",
                "position": 1,
                "content": {"title": "Add two thirds", "model_answer": "$\\frac{2}{3}$"},
                "provenance": GENERATED,
            },
        ],
    }


def sample_exercise(key: str = "q1", objective: str = "math5a:ch03:convert") -> dict:
    return {
        "stable_key": f"math5a:ch03:{key}",
        "objective_alignments": [
            {"objective_stable_key": objective, "alignment_role": "assesses"},
        ],
        "resource_links": [],
        "definition": {
            "contract": "learning.activity.v1",
            "type": "response.free_text",
            "type_version": 1,
            "domain": "math",
            "evidence_mode": "cued_recall",
            "answer_visibility": "after_submission",
            "presentation": {
                "blocks": [
                    {
                        "type": "text",
                        "version": 1,
                        "content": {"key": "question", "text": "Work out $\\frac{1}{3} + \\frac{3}{10}$."},
                        "provenance": GENERATED,
                    },
                ],
            },
            "response": {"kind": "short_answer", "required": True},
            "evaluation": {
                "authority": "deterministic",
                "marking": {"marker": "ela.math.numeric", "expected": {"plain": "19/30"}},
            },
            "scheduling": {"policy": "skill_practice", "subject": "learning_item"},
            "provenance": GENERATED,
        },
    }


def sample_concept(key: str = "convert", exercises: list[dict] | None = None) -> dict:
    return {
        "stable_key": f"math5a:ch03:{key}",
        "statement": "Convert an improper fraction into a mixed number.",
        "objective_type": "procedure",
        "assessed": True,
        "provenance": AUTHORED,
        "exercises": exercises if exercises is not None else [sample_exercise(f"{key}-q1", f"math5a:ch03:{key}")],
    }


def sample_asset(svg: str = "<svg/>") -> dict:
    return {
        "stable_key": "math5a:ch03:asset:bar",
        "media_type": "image/svg+xml",
        "encoding": "inline_svg",
        "svg": svg,
        "byte_length": len(svg.encode("utf-8")),
        "sha256": "not-checked-here",
        "alt_text": "A bar in thirds.",
        "caption": "Two thirds shaded.",
        "illustrates": "worked_examples.0",
        "provenance": GENERATED,
    }


def sample_package(**overrides) -> dict:
    kwargs = {
        "pack": PACK,
        "content_revision": "chapter03@r7",
        "lesson": {
            "stable_key": "math5a:ch03",
            "title": "Fractions",
            "domain": "math",
            "provenance": AUTHORED,
        },
        "teaching_document": sample_teaching_document(),
        "concepts": [sample_concept()],
        "resources": [],
        "assets": [sample_asset()],
    }
    kwargs.update(overrides)

    return lp.build_package(**kwargs)


print("required top-level fields")

package = sample_package()

for field in lp.REQUIRED_TOP_LEVEL_FIELDS:
    check(f"emits {field}", field in package, str(sorted(package)))

check("names the schema", package["schema_version"] == "learning.package.v2", package["schema_version"])
check("names the producer", package["producer_version"].startswith("rag-lesson-package/"), package["producer_version"])
check("names the pack it was written under", package["pack_version"] == PACK.version, package["pack_version"])
check("names the source revision", package["content_revision"] == "chapter03@r7", package["content_revision"])
check("passes its own structural check", lp.structural_problems(package) == [], str(lp.structural_problems(package)))
check(
    "a concept is its own objective — there is no second list",
    "objectives" not in package,
    str(sorted(package)),
)


print("\nthe fingerprint covers the whole file")

check("same material twice, same hash", sample_package()["content_hash"] == sample_package()["content_hash"])
check("the file states its own fingerprint", lp.content_hash(package) == package["content_hash"])
check(
    "re-serialising it does not move the hash",
    lp.content_hash(dict(reversed(list(package.items())))) == package["content_hash"],
    "key order is canonicalised",
)

reworded = sample_package(teaching_document=sample_teaching_document("Four quarters make a whole one."))

check("a changed word in the teaching changes the hash", reworded["content_hash"] != package["content_hash"])

repainted = sample_package(assets=[sample_asset("<svg viewBox='0 0 2 2'/>")])

check(
    "a changed byte in a picture changes the hash",
    repainted["content_hash"] != package["content_hash"],
    "a picture is content, so the hash covers it",
)
check(
    "removing the picture changes the hash",
    sample_package(assets=[])["content_hash"] != package["content_hash"],
)

reordered = sample_package(concepts=[sample_concept("explain"), sample_concept()])
same_content_original_order = sample_package(concepts=[sample_concept(), sample_concept("explain")])

check(
    "reordering the lesson changes the hash",
    reordered["content_hash"] != same_content_original_order["content_hash"],
    "order is part of what a lesson teaches",
)

realigned = sample_package(
    concepts=[
        sample_concept(),
        sample_concept("explain", exercises=[sample_exercise("shared-q", "math5a:ch03:convert")]),
    ],
)
aligned = sample_package(
    concepts=[
        sample_concept(),
        sample_concept("explain", exercises=[sample_exercise("shared-q", "math5a:ch03:explain")]),
    ],
)

check(
    "realigning an exercise changes the hash",
    realigned["content_hash"] != aligned["content_hash"],
    "what an exercise claims to assess is part of the lesson",
)


print("\nconcepts round-trip with their banks")

two = sample_package(
    concepts=[
        sample_concept(),
        sample_concept("explain"),
    ],
)

alignments = {
    exercise["stable_key"]: [a["objective_stable_key"] for a in exercise["objective_alignments"]]
    for concept in two["concepts"]
    for exercise in concept["exercises"]
}

check(
    "each exercise keeps its own alignment",
    alignments == {
        "math5a:ch03:convert-q1": ["math5a:ch03:convert"],
        "math5a:ch03:explain-q1": ["math5a:ch03:explain"],
    },
    str(alignments),
)
check("no all-to-all fallback", all(len(keys) == 1 for keys in alignments.values()), str(alignments))
check("two concepts survive", len(two["concepts"]) == 2, str(len(two["concepts"])))
check("each keeps its bank", all(concept["exercises"] for concept in two["concepts"]))


print("\nan unusable package is refused, with the path")


def refused(package: dict, fragment: str, label: str) -> None:
    problems = lp.structural_problems(package)
    check(label, any(fragment in problem for problem in problems), str(problems))


refused(
    sample_package(concepts=[{**sample_concept(), "exercises": []}]),
    "can never be asked",
    "a concept with an empty bank is refused",
)
refused(
    sample_package(concepts=[sample_concept("convert", exercises=[{**sample_exercise(), "objective_alignments": []}])]),
    "objective_alignments",
    "an exercise with no alignment is refused",
)
refused(
    sample_package(concepts=[sample_concept("convert", exercises=[sample_exercise("q1", "math5a:ch03:nowhere")])]),
    "does not define",
    "an alignment to an undefined concept is refused",
)
refused(
    sample_package(concepts=[{**sample_concept(), "statement": ""}]),
    "has no statement",
    "a concept with no statement is refused",
)
refused(
    sample_package(
        concepts=[
            sample_concept(
                "convert",
                exercises=[
                    {
                        **sample_exercise(),
                        "definition": {**sample_exercise()["definition"], "presentation": {"blocks": []}},
                    }
                ],
            )
        ],
    ),
    "presentation.blocks is empty",
    "an exercise with no blocks inside its definition is refused",
)
refused(
    sample_package(teaching_document={**sample_teaching_document(), "blocks": []}),
    "teaches nothing",
    "a lesson with no teaching document is refused",
)

shuffled = sample_teaching_document()
shuffled["blocks"] = [shuffled["blocks"][1], shuffled["blocks"][0]]

refused(
    sample_package(teaching_document=shuffled),
    "position",
    "a teaching document that arrived re-sorted is refused",
)
refused(
    sample_package(assets=[{**sample_asset(), "illustrates": "nothing-here"}]),
    "does not contain",
    "a picture attached to nothing in the package is refused",
)
refused(
    sample_package(assets=[{**sample_asset(), "alt_text": ""}]),
    "alt_text",
    "a picture nobody described is refused",
)
refused(
    sample_package(assets=[{key: value for key, value in sample_asset().items() if key != "svg"}]),
    "svg is missing",
    "an inline SVG with no markup in it is refused",
)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "package schema holds")
raise SystemExit(1 if fails else 0)
