"""Turn a RAG claim's origin into the provenance record Ela actually validates.

RAG records an origin and the evidence behind it in its own shape. Ela's
contract is origin-specific and strict: each origin has fields it MUST carry and
fields it MAY NOT, because `generator_version` under `source_grounded` says both
"this is what the book says" and "a model wrote it", and one of those is a lie to
whoever reads the content later.

So this translates rather than copies. A package that shipped RAG's internal
shape would be rejected at import, or — worse — accepted and stored as a
provenance record that means something different from what RAG knew.

The three origins carry different evidence because they ARE different claims:

    source_grounded          which resource, and which chunks of it. The strongest
                             claim available: the book says this.
    source_transformed       which chunks, and what was done to them. Reworded,
                             simplified, or reordered — still the book's content,
                             no longer the book's words.
    pedagogical_generation   what it was grounded in, why it was written, and
                             which generator wrote it. A model made this up, in
                             service of teaching, from material it was shown.

`insufficient_source_evidence` is not a way to ship content. It records that the
generator could not support a claim, and content carrying it must not reach a
learner — B11 stops rather than emitting it.
"""

from __future__ import annotations

from typing import Any

MANUALLY_AUTHORED = "manually_authored"
SOURCE_GROUNDED = "source_grounded"
SOURCE_TRANSFORMED = "source_transformed"
PEDAGOGICAL_GENERATION = "pedagogical_generation"
INSUFFICIENT_SOURCE_EVIDENCE = "insufficient_source_evidence"

# What Ela requires per origin. Mirrored deliberately rather than imported —
# the two repositories do not share code — and a test asserts they agree.
REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    SOURCE_GROUNDED: ("source_resource_id", "source_chunk_ids"),
    SOURCE_TRANSFORMED: ("source_chunk_ids", "transformation"),
    PEDAGOGICAL_GENERATION: (
        "grounded_in_source_chunk_ids",
        "generation_reason",
        "generator_version",
    ),
    INSUFFICIENT_SOURCE_EVIDENCE: (),
    # A person wrote it. RAG does not emit this, but a package may legitimately
    # carry hand-authored material, and rejecting it as an unknown origin would
    # be wrong.
    MANUALLY_AUTHORED: (),
}

# Fields each origin may add, and no others.
OPTIONAL_FIELDS: dict[str, tuple[str, ...]] = {
    SOURCE_GROUNDED: ("evidence_spans",),
    SOURCE_TRANSFORMED: ("source_resource_id", "evidence_spans"),
    PEDAGOGICAL_GENERATION: ("generator_prompt_version",),
    INSUFFICIENT_SOURCE_EVIDENCE: ("reason", "attempted_source_chunk_ids"),
    MANUALLY_AUTHORED: ("author_reference",),
}


class UnsupportedProvenance(Exception):
    """A claim whose origin cannot be expressed as a provenance record."""


def translate(claim: dict[str, Any], *, source_path: str, source_resource_id: str) -> dict[str, Any]:
    """The provenance record for one claim, or a refusal naming where it came from.

    `source_path` is carried into every failure because "provenance is missing"
    is not actionable and "chapter03.core_lessons.2.claims.0 is missing chunk
    references" tells whoever fixes it exactly which claim to look at.

    `source_resource_id` is the identity B11.1 needs to tie imported content back
    to the book it came from. It is passed in rather than guessed, because the
    exporter does not get to decide what a claim was grounded in.
    """
    origin = str(claim.get("origin") or "").strip()

    if origin == INSUFFICIENT_SOURCE_EVIDENCE:
        raise UnsupportedProvenance(
            f"{source_path} is marked insufficient_source_evidence and cannot be published"
        )

    if origin not in REQUIRED_FIELDS:
        raise UnsupportedProvenance(f"{source_path} has unknown origin {origin!r}")

    chunk_ids = _chunk_ids(claim)

    if origin == MANUALLY_AUTHORED:
        # Handled explicitly. Falling through to the generated-content branch
        # produced a record carrying `generator_version` under an origin that
        # says a person wrote it — a contradiction Ela rejects, and a claim
        # about authorship that nothing supports.
        author = str(claim.get("author_reference") or "").strip()

        if not author:
            raise UnsupportedProvenance(
                f"{source_path} claims manual authorship but does not say who wrote it"
            )

        return {"origin": origin, "author_reference": author}

    if origin == SOURCE_GROUNDED:
        record = {
            "origin": origin,
            "source_resource_id": source_resource_id,
            "source_chunk_ids": chunk_ids,
        }
    elif origin == SOURCE_TRANSFORMED:
        record = {
            "origin": origin,
            "source_chunk_ids": chunk_ids,
            "transformation": str(claim.get("transformation") or "").strip(),
            "source_resource_id": source_resource_id,
        }
    else:
        record = {
            "origin": origin,
            "grounded_in_source_chunk_ids": chunk_ids,
            "generation_reason": str(claim.get("generation_reason") or "").strip(),
            "generator_version": str(claim.get("generator_version") or "").strip(),
        }

    # Optional evidence the claim carries is PRESERVED, not dropped. Evidence
    # spans are the strongest thing a grounded claim has — the exact words in
    # the source it rests on — and discarding them at the boundary means the
    # importer can never show a learner or a reviewer why the system believes
    # what it says.
    for field in OPTIONAL_FIELDS[origin]:
        value = claim.get(field)

        if isinstance(value, (list, tuple)):
            value = [item for item in value if item not in (None, "")]

            if value:
                record[field] = list(value)
        elif str(value or "").strip():
            record[field] = str(value).strip()

    missing = [
        field
        for field in REQUIRED_FIELDS[origin]
        if not record.get(field) and record.get(field) != []
    ]

    if missing:
        raise UnsupportedProvenance(
            f"{source_path} claims {origin} but supplies no {', '.join(missing)}"
        )

    if origin in (SOURCE_GROUNDED, SOURCE_TRANSFORMED) and not chunk_ids:
        raise UnsupportedProvenance(f"{source_path} claims {origin} with no source chunks")

    return record


def _chunk_ids(claim: dict[str, Any]) -> list[str]:
    raw = (
        claim.get("source_chunk_ids")
        or claim.get("grounded_in_source_chunk_ids")
        or claim.get("chunk_ids")
        or []
    )

    return [str(value) for value in raw if str(value).strip()]
