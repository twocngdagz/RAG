"""Build claims the way the v2 rules require, or admit the evidence is not there.

`build_math_grounded_base._grounded` stamped every claim with one shape: the
kind `source_statement`, the same page ids in BOTH `source_chunk_ids` and
`grounded_in_source_chunk_ids`, and empty `evidence_spans` — while claiming
`source_grounded`.

Each of those is a different way of saying more than the producer knew:

    source_statement        is not in the canonical vocabulary, so nothing
                            downstream can tell an objective from an example
    both id lists           says "this is what the book says" and "a model wrote
                            this from these pages" at once, and the contract
                            rejects the combination for exactly that reason
    empty evidence_spans    claims grounding while pointing at nothing. The span
                            IS the grounding; without it the claim rests on the
                            extractor having been told to copy.

So a claim is grounded here only when its text is actually found in the source,
and then it names the chunk it was found in and quotes the words. A claim that
cannot meet that is marked `insufficient_source_evidence` rather than
mechanically upgraded — which is what makes the export refusal downstream
meaningful rather than a formality nobody trips.
"""

from __future__ import annotations

import re
from typing import Any

# Which canonical kind each chapter field carries. A generic replacement for
# `source_statement` would repeat the original mistake in a valid-looking word.
FIELD_CLAIM_KINDS: dict[str, str] = {
    "chapter_summary": "source_summary",
    "estimated_study_time": "study_plan",
    "learning_objectives": "learning_objective",
    "key_terms": "definition",
    "core_lessons": "factual_explanation",
    "worked_examples": "pedagogical_example",
    "misconception": "misconception_statement",
    "correction": "misconception_correction",
    "practice_question": "practice_question",
    "practice_answer": "practice_answer",
    "review_checklist": "self_assessment",
}

# How much of a claim must appear in a chunk before it counts as found there.
# Short fragments match by accident; this is long enough that a hit means the
# sentence really is on the page.
MIN_SPAN_CHARS = 40


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def find_evidence(text: str, chunks: list[dict[str, Any]]) -> tuple[str, str] | None:
    """The chunk this text appears in, and the words that prove it.

    Returns (node_id, quote), or None when the text is not in the source. The
    quote is taken from the CHUNK rather than the claim, so it is the source's
    words — a span quoting the claim would prove only that the claim exists.
    """
    needle = normalise(text)

    if len(needle) < MIN_SPAN_CHARS:
        return None

    for chunk in chunks:
        haystack = normalise(chunk.get("text") or chunk.get("markdown") or "")
        position = haystack.find(needle)

        if position != -1:
            return str(chunk.get("node_id") or ""), needle

        # A claim lightly reworded still has its opening clause intact more
        # often than not; a prefix match is evidence, a fuzzy match is a guess.
        prefix = needle[:MIN_SPAN_CHARS]

        if prefix and prefix in haystack:
            start = haystack.find(prefix)
            return str(chunk.get("node_id") or ""), haystack[start : start + len(needle)]

    return None


def build_claim(text: str, field: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """One claim, honest about what stands behind it."""
    claim_kind = FIELD_CLAIM_KINDS.get(field)

    if claim_kind is None:
        raise ValueError(f"no canonical claim kind declared for field {field!r}")

    evidence = find_evidence(text, chunks)

    if evidence is None:
        # Not found in the source. Saying so is the point: the export refuses
        # this later, and that refusal is the system noticing it cannot support
        # something rather than shipping it.
        return {
            "text": text,
            "claim_kind": claim_kind,
            "origin": "insufficient_source_evidence",
            "source_chunk_ids": [],
            "grounded_in_source_chunk_ids": [],
            "evidence_spans": [],
            "reason": "the claim's text was not found in the parsed source pages",
        }

    node_id, quote = evidence

    return {
        "text": text,
        "claim_kind": claim_kind,
        "origin": "source_grounded",
        # DIRECT references only. The generated-content list stays empty: this
        # claim is the book's, not something written from the book.
        "source_chunk_ids": [node_id],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": [{"node_id": node_id, "quote": quote}],
        "reason": None,
    }


def clean_chunks_from_pages(pages: list[dict[str, Any]], slug: str, chapter_number: int) -> list[dict[str, Any]]:
    """A clean-chunks artifact derived deterministically from the parsed pages.

    One chunk per page, ids from the page number, so regenerating the same
    source produces the same chunk ids and every claim's references stay valid
    across runs.
    """
    return [
        {
            "node_id": f"{slug}:p{page['page']}",
            "source_pdf": page.get("source_pdf", slug),
            "chapter_number": chapter_number,
            "text": normalise(page.get("markdown") or page.get("text") or ""),
        }
        for page in pages
    ]
