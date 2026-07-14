"""Tests for what the grounding judge is allowed to judge, and for v2 extraction.

Two defects, found by semantically auditing a v2 PTE chapter:

- The extractor read v2 grounded content objects with the v1 plain-string reader,
  which returns None for a dict. Key terms, core lessons, worked examples and
  misconceptions were therefore silently dropped, so most of a chapter was never
  audited at all (9 claims extracted from a 37-claim chapter).

- The judge then graded the survivors for source support without knowing their
  origin, so deliberately invented pedagogy ("I can chunk spoken questions...")
  was marked UNSUPPORTED and failed a chapter whose every genuine source claim
  was sound.
"""

import audit_book_claim_support as audit
import extract_book_learning_claims as extract


def grounded(text, origin, kind, ids=None):
    return {
        "text": text,
        "claim_kind": kind,
        "origin": origin,
        "source_chunk_ids": ids or [],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": [],
        "reason": None,
    }


# --------------------------------------------------------------------------- #
# Extractor: v2 grounded objects must not be dropped
# --------------------------------------------------------------------------- #

def test_unwrap_reads_a_v2_grounded_object():
    text, origin, kind, ids = extract.unwrap_grounded(
        grounded("A brief spoken answer.", "source_grounded", "definition", ["c1"])
    )

    assert text == "A brief spoken answer."
    assert origin == "source_grounded"
    assert kind == "definition"
    assert ids == ["c1"]


def test_unwrap_still_reads_a_v1_plain_string():
    text, origin, kind, ids = extract.unwrap_grounded("A v1 string field.")

    assert text == "A v1 string field."
    assert origin is None and kind is None and ids is None


def test_unwrap_ignores_a_dict_that_is_not_a_grounded_object():
    text, origin, _kind, _ids = extract.unwrap_grounded({"term": "not a claim"})

    assert text is None
    assert origin is None


def test_insufficient_evidence_object_yields_no_text():
    # text is null by construction, so there is nothing to judge.
    text, origin, _kind, _ids = extract.unwrap_grounded(
        grounded(None, "insufficient_source_evidence", "task_format")
    )

    assert text is None
    assert origin == "insufficient_source_evidence"


# --------------------------------------------------------------------------- #
# Judge scope: generated pedagogy is not a claim about the source
# --------------------------------------------------------------------------- #

def claim(claim_id, grounded_origin):
    return {"claim_id": claim_id, "claim_text": "x", "grounded_origin": grounded_origin}


def test_pedagogical_generation_is_not_a_source_claim():
    assert not audit.is_source_claim(claim("c1", "pedagogical_generation"))


def test_source_grounded_is_a_source_claim():
    assert audit.is_source_claim(claim("c1", "source_grounded"))


def test_v1_claims_without_origin_are_still_judged():
    # Preserves v1 behaviour: no origin recorded means judge it.
    assert audit.is_source_claim({"claim_id": "c1", "claim_text": "x"})


def test_whole_book_sweep_skips_generated_claims():
    claims = [
        claim("obj.0", "source_grounded"),
        claim("checklist.0", "pedagogical_generation"),
        claim("checklist.1", "pedagogical_generation"),
        claim("lesson.0", "source_grounded"),
    ]
    selected, mode, requested = audit.select_claims(claims, None)

    assert mode == "all"
    assert requested == []
    assert [c["claim_id"] for c in selected] == ["obj.0", "lesson.0"]


def test_explicitly_requested_generated_claim_is_still_judged():
    # An explicit --claim-id is an instruction, not a sweep; honour it.
    claims = [claim("checklist.0", "pedagogical_generation")]
    selected, mode, _requested = audit.select_claims(claims, ["checklist.0"])

    assert mode == "claim_ids"
    assert [c["claim_id"] for c in selected] == ["checklist.0"]


def test_partition_reports_what_was_exempted():
    claims = [
        claim("a", "source_grounded"),
        claim("b", "pedagogical_generation"),
    ]
    judgeable, exempt = audit.partition_source_claims(claims)

    assert [c["claim_id"] for c in judgeable] == ["a"]
    assert [c["claim_id"] for c in exempt] == ["b"]


# --------------------------------------------------------------------------- #
# The audit must report the judge that actually ran
# --------------------------------------------------------------------------- #

def test_audit_provenance_names_the_real_judge():
    import argparse

    codex = argparse.Namespace(
        backend="codex-cli", model="mistral-x", codex_model="gpt-5.5", claude_model="sonnet"
    )
    nvidia = argparse.Namespace(
        backend="nvidia", model="mistral-x", codex_model="gpt-5.5", claude_model="sonnet"
    )

    assert audit.audit_judge_model_name(codex) == "gpt-5.5"
    assert audit.audit_judge_model_name(nvidia) == "mistral-x"
