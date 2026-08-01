"""The emitted package: required fields, a stable hash, and objectives that survive.

A package is what RAG hands Ela. It must be identifiable later — which producer,
which pack rules, which source revision — and it must be possible to tell "we
generated this again" from "this is genuinely different", because otherwise every
rerun looks like new material and a learner sees the same lesson twice.

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


def sample_objective(key: str = "convert") -> dict:
    return {
        "stable_key": f"math5a:ch03:{key}",
        "statement": "Convert an improper fraction into a mixed number.",
        "objective_type": "procedure",
        "provenance": GROUNDED,
    }


def sample_activity(key: str = "teach", objective: str = "math5a:ch03:convert") -> dict:
    return {
        "stable_key": f"math5a:ch03:{key}",
        "objective_alignments": [
            {"objective_stable_key": objective, "alignment_role": "assesses"},
        ],
        "resource_links": [],
        "definition": {
            "contract": "learning.activity.v1",
            "type": "response.acknowledgement",
            "type_version": 1,
            "domain": "math",
            "evidence_mode": "exposure",
            "answer_visibility": "never",
            "presentation": {
                "blocks": [
                    {
                        "type": "text",
                        "version": 1,
                        "content": {"key": "explanation", "text": "Four quarters make one whole."},
                        "provenance": GROUNDED,
                    },
                ],
            },
            "response": {"kind": "acknowledgement", "required": False},
            "evaluation": {"authority": "unscored"},
            "scheduling": {"policy": "skill_practice", "subject": "learning_item"},
            "provenance": GROUNDED,
        },
    }


def sample_package(**overrides) -> dict:
    kwargs = {
        "pack": PACK,
        "content_revision": "chapter03@r7",
        "lesson": {
            "stable_key": "math5a:ch03",
            "title": "Improper fractions and mixed numbers",
            "domain": "math",
            "provenance": GROUNDED,
        },
        "objectives": [sample_objective()],
        "activities": [sample_activity()],
        "resources": [],
    }
    kwargs.update(overrides)

    return lp.build_package(**kwargs)


print("required top-level fields")

package = sample_package()

for field in lp.REQUIRED_TOP_LEVEL_FIELDS:
    check(f"emits {field}", field in package, str(sorted(package)))

check("names the schema", package["schema_version"] == "learning.package.v1", package["schema_version"])
check("names the producer", package["producer_version"].startswith("rag-lesson-package/"), package["producer_version"])
check("names the pack it was written under", package["pack_version"] == PACK.version, package["pack_version"])
check("names the source revision", package["content_revision"] == "chapter03@r7", package["content_revision"])
check("passes its own structural check", lp.structural_problems(package) == [], str(lp.structural_problems(package)))


print("\nhash is stable across runs, and moves only when the lesson does")

check(
    "same material twice, same hash",
    sample_package()["content_hash"] == sample_package()["content_hash"],
)

# A rerun from a newer producer is not a new lesson for the learner.
original_producer = lp.PRODUCER_VERSION
lp.PRODUCER_VERSION = "rag-lesson-package/9.9.9"
newer = sample_package()
lp.PRODUCER_VERSION = original_producer

check(
    "a newer producer does not change the hash",
    newer["content_hash"] == package["content_hash"],
    f"{newer['content_hash'][:12]} vs {package['content_hash'][:12]}",
)

reworded = sample_package(
    activities=[
        {
            **sample_activity(),
            "definition": {
                **sample_activity()["definition"],
                "presentation": {
                    "blocks": [
                        {
                            "type": "text",
                            "version": 1,
                            "content": {"key": "explanation", "text": "Four quarters make a whole one."},
                            "provenance": GROUNDED,
                        },
                    ],
                },
            },
        }
    ],
)

check(
    "a changed word changes the hash",
    reworded["content_hash"] != package["content_hash"],
)

reordered = sample_package(
    objectives=[sample_objective("explain"), sample_objective()],
    activities=[
        sample_activity("practice", "math5a:ch03:explain"),
        sample_activity(),
    ],
)
same_content_original_order = sample_package(
    objectives=[sample_objective(), sample_objective("explain")],
    activities=[
        sample_activity(),
        sample_activity("practice", "math5a:ch03:explain"),
    ],
)

check(
    "reordering the lesson changes the hash",
    reordered["content_hash"] != same_content_original_order["content_hash"],
    "order is part of what a lesson teaches",
)

realigned = sample_package(
    objectives=[sample_objective(), sample_objective("explain")],
    activities=[sample_activity("teach", "math5a:ch03:explain")],
)
aligned = sample_package(
    objectives=[sample_objective(), sample_objective("explain")],
    activities=[sample_activity()],
)

check(
    "realigning an activity changes the hash",
    realigned["content_hash"] != aligned["content_hash"],
    "what an activity claims to teach is part of the lesson",
)


print("\nobjective associations round-trip")

two = sample_package(
    objectives=[sample_objective(), sample_objective("explain")],
    activities=[
        sample_activity("teach", "math5a:ch03:convert"),
        sample_activity("explain-why", "math5a:ch03:explain"),
    ],
)

alignments = {
    activity["stable_key"]: [a["objective_stable_key"] for a in activity["objective_alignments"]]
    for activity in two["activities"]
}

check(
    "each activity keeps its own alignment",
    alignments == {
        "math5a:ch03:teach": ["math5a:ch03:convert"],
        "math5a:ch03:explain-why": ["math5a:ch03:explain"],
    },
    str(alignments),
)
check("no all-to-all fallback", all(len(keys) == 1 for keys in alignments.values()), str(alignments))
check("two objectives survive", len(two["objectives"]) == 2, str(len(two["objectives"])))


print("\nan unusable package is refused, with the path")

no_alignment = sample_package(
    activities=[{**sample_activity(), "objective_alignments": []}],
)
check(
    "an activity with no alignment is refused",
    any("objective_alignments" in problem for problem in lp.structural_problems(no_alignment)),
    str(lp.structural_problems(no_alignment)),
)

dangling = sample_package(
    activities=[sample_activity("teach", "math5a:ch03:nowhere")],
)
check(
    "an alignment to an undefined objective is refused",
    any("does not define" in problem for problem in lp.structural_problems(dangling)),
    str(lp.structural_problems(dangling)),
)

no_statement = sample_package(
    objectives=[{**sample_objective(), "statement": ""}],
)
check(
    "an objective with no statement is refused",
    any("has no statement" in problem for problem in lp.structural_problems(no_statement)),
    str(lp.structural_problems(no_statement)),
)

blocks_outside = sample_package(
    activities=[
        {
            **sample_activity(),
            "definition": {
                **sample_activity()["definition"],
                "presentation": {"blocks": []},
            },
        }
    ],
)
check(
    "an activity with no blocks inside its definition is refused",
    any("presentation.blocks is empty" in problem for problem in lp.structural_problems(blocks_outside)),
    str(lp.structural_problems(blocks_outside)),
)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "package schema holds")
raise SystemExit(1 if fails else 0)
