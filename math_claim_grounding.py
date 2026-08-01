"""Build claims the way the v2 rules require, or admit the evidence is not there.

`build_math_grounded_base._grounded` stamped every claim with one shape: the
kind `source_statement`, the same page ids in BOTH `source_chunk_ids` and
`grounded_in_source_chunk_ids`, and empty `evidence_spans` — while claiming
`source_grounded`. Each is a way of saying more than the producer knew, and
together they are why no math5a chapter passes the source contract.

Two rules decide a claim's origin, in this order.

**The KIND decides first.** Some claims are written for the learner rather than
taken from the book — a practice question the book does not ask, a study time
nobody stated, a self-assessment prompt. Those are `pedagogical_generation`
however closely the source happens to read, because text matching cannot promote
invented content to grounded. A misconception is the sharpest case: it names a
false belief so the paired correction can refute it, and the source asserts the
truth, never the error.

**Then the EVIDENCE decides.** A grounded claim must be covered — every sentence
of it found in the source, quoted from the source's own words. Accepting a claim
because its opening matched grants grounding to everything the sentence goes on
to assert. A claim that cannot be covered is marked
`insufficient_source_evidence` with `text: null`: carrying the wording of
something the producer could not support ships it anyway.
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

# Kinds the model is asked to invent, from the v2 generation rules. Mirrored
# deliberately; a test asserts the mirror holds.
GENERATED_CLAIM_KINDS = {
    "pedagogical_example",
    "practice_question",
    "practice_answer",
    "learner_instruction",
    "self_assessment",
    "study_plan",
    "misconception_statement",
}

# A span short enough to match by accident proves nothing; one long enough to be
# a page is not a quotation.
MIN_SPAN_WORDS = 4
MAX_SPAN_WORDS = 80


def normalise(text: str) -> str:
    """For COMPARISON only. Never for what is stored."""
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()

    return [value for value in values if value and not (value in seen or seen.add(value))]


def cover_with_spans(text: str, chunks: list[dict[str, Any]]) -> list[dict[str, str]] | None:
    """Spans that together account for the WHOLE claim, or None.

    Sentence by sentence, and every sentence must be found. A claim legitimately
    spanning two pages produces two spans; a claim with one unfounded sentence
    produces None, because the part that is not in the source is exactly the
    part worth catching.
    """
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", str(text or "")) if part.strip()]

    if not sentences:
        return None

    spans: list[dict[str, str]] = []

    for sentence in sentences:
        words = normalise(sentence).split()

        if len(words) < MIN_SPAN_WORDS or len(words) > MAX_SPAN_WORDS:
            return None

        needle = " ".join(words)
        located = None

        for chunk in chunks:
            haystack = normalise(chunk.get("text") or chunk.get("markdown") or "")

            if needle and needle in haystack:
                located = (str(chunk.get("node_id") or ""), sentence)
                break

        if located is None:
            return None

        node_id, quote = located
        spans.append({"node_id": node_id, "quote": quote})

    return spans


def build_claim(
    text: str,
    field: str,
    chunks: list[dict[str, Any]],
    *,
    generator_version: str = "math5a-grounded-base/2.0.0",
) -> dict[str, Any]:
    """One claim, honest about what stands behind it."""
    claim_kind = FIELD_CLAIM_KINDS.get(field)

    if claim_kind is None:
        raise ValueError(f"no canonical claim kind declared for field {field!r}")

    if claim_kind in GENERATED_CLAIM_KINDS:
        return {
            "text": text,
            "claim_kind": claim_kind,
            "origin": "pedagogical_generation",
            "source_chunk_ids": [],
            "grounded_in_source_chunk_ids": unique_preserve_order(
                [str(chunk.get("node_id") or "") for chunk in chunks]
            ),
            "generation_reason": f"Written for the learner from this chapter's pages ({field})",
            "generator_version": generator_version,
            "evidence_spans": [],
            "reason": None,
        }

    spans = cover_with_spans(text, chunks)

    if spans is None:
        return {
            "text": None,
            "claim_kind": claim_kind,
            "origin": "insufficient_source_evidence",
            "source_chunk_ids": [],
            "grounded_in_source_chunk_ids": [],
            "evidence_spans": [],
            "reason": "no span in the parsed source covers the whole claim",
        }

    return {
        "text": text,
        "claim_kind": claim_kind,
        "origin": "source_grounded",
        "source_chunk_ids": unique_preserve_order([span["node_id"] for span in spans]),
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": spans,
        "reason": None,
    }


def clean_chunks_from_pages(pages: list[dict[str, Any]], slug: str, chapter_number: int) -> list[dict[str, Any]]:
    """A clean-chunks artifact derived deterministically from the parsed pages.

    One chunk per page, ids from the page number, so regenerating the same
    source produces the same ids and every claim's references stay valid.

    The text is the SOURCE's, unchanged. Normalising here would make the
    artifact a lowercased paraphrase of the book, and every evidence span would
    quote something the page does not say.
    """
    return [
        {
            "node_id": f"{slug}:p{page['page']}",
            "source_pdf": page.get("source_pdf", slug),
            "chapter_number": chapter_number,
            "text": page.get("markdown") or page.get("text") or "",
        }
        for page in pages
    ]
