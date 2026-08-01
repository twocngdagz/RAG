"""Provenance survives the crossing from RAG to Ela, or emission stops.

RAG records where a claim came from in its own shape. Ela's contract is
origin-specific and strict, because "the book says this" and "a model wrote this
to help" are different claims and one of them must never be mistaken for the
other. A package that shipped RAG's internal shape would be rejected at import
or, worse, stored as a record meaning something else.

The planted errors matter more than the happy path. A check that only ever sees
good input is not a check — so two of these are deliberately broken in ways that
MUST be caught, and two are unusual but legitimate and MUST NOT be.

    python test_provenance_continuity.py
"""
from __future__ import annotations

import lesson_provenance as prov

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


def translate(claim: dict, path: str = "chapter03.core_lessons.0.claims.0"):
    return prov.translate(claim, source_path=path, source_resource_id="math5a:book")


print("a grounded claim keeps its evidence")

grounded = translate(
    {
        "origin": "source_grounded",
        "source_chunk_ids": ["math5a:ch03:chunk14", "math5a:ch03:chunk15"],
    }
)

check("origin survives", grounded["origin"] == "source_grounded", str(grounded))
check(
    "the resource identity B11.1 needs is carried",
    grounded["source_resource_id"] == "math5a:book",
    str(grounded),
)
check(
    "chunk references survive",
    grounded["source_chunk_ids"] == ["math5a:ch03:chunk14", "math5a:ch03:chunk15"],
    str(grounded),
)
check(
    "no generator identity is invented for grounded content",
    "generator_version" not in grounded,
    str(grounded),
)


print("\na generated claim keeps its grounding and its author")

generated = translate(
    {
        "origin": "pedagogical_generation",
        "grounded_in_source_chunk_ids": ["math5a:ch03:chunk14"],
        "generation_reason": "A second worked example at a smaller size",
        "generator_version": "math5a-pack:1.0.0",
    }
)

check(
    "grounding survives",
    generated["grounded_in_source_chunk_ids"] == ["math5a:ch03:chunk14"],
    str(generated),
)
check("the reason survives", generated["generation_reason"].startswith("A second"), str(generated))
check("the generator is named", generated["generator_version"] == "math5a-pack:1.0.0", str(generated))
check(
    "no source_resource_id is claimed for invented content",
    "source_resource_id" not in generated,
    "that field says the book contains this",
)


print("\nPLANTED ERRORS — each of these must be caught")

# 1. Content the generator itself could not support.
try:
    translate({"origin": "insufficient_source_evidence", "text": None})
    check("insufficient evidence is refused", False, "it was translated")
except prov.UnsupportedProvenance as error:
    check("insufficient evidence is refused", True)
    check(
        "the refusal names where it came from",
        "chapter03.core_lessons.0.claims.0" in str(error),
        str(error),
    )

# 2. A grounded claim with nothing behind it — the shape of a lie told
#    consistently, which is exactly what the import check cannot catch later.
try:
    translate({"origin": "source_grounded", "source_chunk_ids": []})
    check("grounded with no chunks is refused", False, "it was translated")
except prov.UnsupportedProvenance as error:
    check("grounded with no chunks is refused", True)
    check("the refusal says what was missing", "chunk" in str(error).lower(), str(error))

# 3. Generated content that will not say who generated it.
try:
    translate(
        {
            "origin": "pedagogical_generation",
            "grounded_in_source_chunk_ids": ["math5a:ch03:chunk14"],
            "generation_reason": "An extra example",
        }
    )
    check("generation with no generator is refused", False, "it was translated")
except prov.UnsupportedProvenance as error:
    check("generation with no generator is refused", True)
    check("the refusal names the field", "generator_version" in str(error), str(error))

# 4. An origin nothing downstream understands.
try:
    translate({"origin": "vibes"})
    check("an unknown origin is refused", False, "it was translated")
except prov.UnsupportedProvenance as error:
    check("an unknown origin is refused", True)


print("\nUNUSUAL BUT LEGITIMATE — none of these may be flagged")

# 1. Reworded book content is not invented content. It keeps chunk references
#    and says what was done to them.
try:
    transformed = translate(
        {
            "origin": "source_transformed",
            "source_chunk_ids": ["math5a:ch03:chunk14"],
            "transformation": "simplified for a grade 5 reading level",
        }
    )
    check("reworded source content is allowed", True)
    check(
        "the transformation is recorded",
        transformed["transformation"].startswith("simplified"),
        str(transformed),
    )
except prov.UnsupportedProvenance as error:
    check("reworded source content is allowed", False, str(error))

# 2. Many chunks behind one claim is normal for a summary, not suspicious.
try:
    wide = translate(
        {
            "origin": "source_grounded",
            "source_chunk_ids": [f"math5a:ch03:chunk{n}" for n in range(1, 12)],
        }
    )
    check("a claim grounded in many chunks is allowed", len(wide["source_chunk_ids"]) == 11)
except prov.UnsupportedProvenance as error:
    check("a claim grounded in many chunks is allowed", False, str(error))


print("\nthe required fields match what Ela validates")

check(
    "grounded requires resource and chunks",
    prov.REQUIRED_FIELDS["source_grounded"] == ("source_resource_id", "source_chunk_ids"),
)
check(
    "generation requires grounding, reason and generator",
    prov.REQUIRED_FIELDS["pedagogical_generation"]
    == ("grounded_in_source_chunk_ids", "generation_reason", "generator_version"),
)


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "provenance survives the crossing")
raise SystemExit(1 if fails else 0)
