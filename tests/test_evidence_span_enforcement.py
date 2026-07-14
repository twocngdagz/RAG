"""Tests for evidence-span parsing and source_grounded enforcement.

Covers two defects found by comparing model backends on PTE chapter 1:

- Quote-key mismatch: gpt-5.5 emits evidence spans as
  {"node_id": ..., "text": ...} while the schema asks for "quote". The parser
  only read "quote"/"span", so valid, exact source quotes were silently dropped,
  which nulled every high-risk claim that depended on them.

- Audit hole M-8: only HIGH_RISK_CLAIM_KINDS required an evidence span, so any
  other claim could be labelled "source_grounded" on a bare chunk citation that
  was never matched against the source text. A citation is not evidence.
"""

import pytest

import book_learning_materials_v2_generation as v2


SOURCE_TEXT = "Time allocated: 2 hours. Candidates provide a brief and accurate response."
LOOKUP = {"c1": {"text": SOURCE_TEXT}}
ALLOWED = {"c1"}

EXACT_QUOTE = "provide a brief and accurate response"


def grounded(**overrides):
    base = {
        "text": "Candidates must answer briefly.",
        "claim_kind": "definition",  # deliberately NOT high-risk
        "origin": "source_grounded",
        "source_chunk_ids": ["c1"],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": [],
        "reason": None,
    }
    base.update(overrides)
    return base


def normalize(obj):
    return v2.normalize_grounded_content_object(
        obj, allowed_ids=ALLOWED, clean_chunks_lookup=LOOKUP
    )


# --------------------------------------------------------------------------- #
# Quote-key aliases (the gpt-5.5 failure)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("quote_key", ["quote", "span", "text", "excerpt"])
def test_evidence_span_quote_key_aliases_are_accepted(quote_key):
    obj = grounded(evidence_spans=[{"node_id": "c1", quote_key: EXACT_QUOTE}])
    result = normalize(obj)

    assert result["origin"] == "source_grounded"
    assert result["text"] == "Candidates must answer briefly."
    # Whatever key the model used, the span is stored under the canonical "quote".
    assert result["evidence_spans"] == [{"node_id": "c1", "quote": EXACT_QUOTE}]


def test_high_risk_claim_survives_when_span_uses_text_key():
    # This is the exact shape that nulled the four PTE core lessons.
    obj = grounded(
        claim_kind="task_format",  # high-risk
        evidence_spans=[{"node_id": "c1", "text": EXACT_QUOTE}],
    )
    result = normalize(obj)

    assert result["origin"] == "source_grounded"
    assert result["text"] is not None
    assert result["evidence_spans"][0]["quote"] == EXACT_QUOTE


# --------------------------------------------------------------------------- #
# Alias tolerance must not become a forgery hole
# --------------------------------------------------------------------------- #

def test_span_not_present_in_source_is_still_rejected():
    obj = grounded(
        evidence_spans=[{"node_id": "c1", "text": "a phrase that is absent from the source"}]
    )
    result = normalize(obj)

    assert result["origin"] == "insufficient_source_evidence"
    assert result["text"] is None


def test_span_citing_a_disallowed_chunk_is_rejected():
    obj = grounded(evidence_spans=[{"node_id": "not_allowed", "quote": EXACT_QUOTE}])
    result = normalize(obj)

    assert result["origin"] == "insufficient_source_evidence"
    assert result["text"] is None


# --------------------------------------------------------------------------- #
# M-8: a citation alone is not evidence, for ANY claim kind
# --------------------------------------------------------------------------- #

def test_non_high_risk_source_grounded_without_span_is_downgraded():
    result = normalize(grounded(evidence_spans=[]))

    assert result["origin"] == "insufficient_source_evidence"
    assert result["text"] is None
    assert result["evidence_spans"] == []
    assert "evidence span" in (result["reason"] or "")


def test_high_risk_source_grounded_without_span_is_downgraded():
    result = normalize(grounded(claim_kind="official_rule", evidence_spans=[]))

    assert result["origin"] == "insufficient_source_evidence"
    assert result["text"] is None
    assert "high-risk" in (result["reason"] or "")


def test_source_grounded_with_verified_span_is_kept():
    result = normalize(
        grounded(evidence_spans=[{"node_id": "c1", "quote": EXACT_QUOTE}])
    )

    assert result["origin"] == "source_grounded"
    assert result["text"] is not None
    assert len(result["evidence_spans"]) == 1


# --------------------------------------------------------------------------- #
# The prompt must name the required key, so models do not have to guess it.
# --------------------------------------------------------------------------- #

def test_schema_rules_state_the_required_quote_key():
    rules = v2.v2_schema_rules_text()

    assert '"quote"' in rules
    assert "EVERY source_grounded field" in rules
