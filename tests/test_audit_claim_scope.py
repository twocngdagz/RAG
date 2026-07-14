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
# Every extracted v2 claim must carry its origin. Threading it through most call
# sites but not all is silent: the missed fields simply get judged as source
# claims again, which is the bug this whole file exists to prevent.
# --------------------------------------------------------------------------- #

def v2_chapter():
    return {
        "chapter_number": 1,
        "chapter_title": "LESSON 1",
        "source_chunk_ids": ["c1"],
        "chapter_summary": grounded("Summary.", "source_grounded", "source_summary", ["c1"]),
        "learning_objectives": [
            grounded("Objective.", "source_grounded", "learning_objective", ["c1"])
        ],
        "key_terms": [
            {"term": "T", "meaning": grounded("Meaning.", "source_grounded", "definition", ["c1"])}
        ],
        "core_lessons": [
            {
                "title": "L",
                "explanation": grounded("Explain.", "source_grounded", "task_format", ["c1"]),
            }
        ],
        "worked_examples": [
            {
                "title": "W",
                "example": grounded("Example.", "pedagogical_generation", "pedagogical_example"),
                "explanation": grounded("Why.", "source_grounded", "strategy", ["c1"]),
            }
        ],
        "common_misconceptions": [
            {
                "misconception": grounded("Myth.", "source_grounded", "misconception_statement", ["c1"]),
                "correction": grounded("Fix.", "source_grounded", "misconception_correction", ["c1"]),
            }
        ],
        "practice_questions": [
            {
                "question": grounded("Q?", "pedagogical_generation", "practice_question"),
                "answer": grounded("A.", "pedagogical_generation", "practice_answer"),
            }
        ],
        "review_checklist": [
            grounded("I can do it.", "pedagogical_generation", "self_assessment")
        ],
    }


def v2_book():
    return {
        "book": {"slug": "pte", "source_pdf": "input/pdfs/pte.pdf"},
        "generation": {"pipeline_version": "book_learning_materials.v2"},
        "learning_materials": {"chapters": [v2_chapter()]},
    }


def test_every_v2_claim_carries_its_origin():
    claims = extract.extract_claims(v2_book())

    missing = [c["claim_id"] for c in claims if c.get("grounded_origin") is None]
    assert not missing, f"claims extracted without an origin (they will be judged as source claims): {missing}"


def test_generated_fields_are_exempted_end_to_end():
    claims = extract.extract_claims(v2_book())
    _judgeable, exempt = audit.partition_source_claims(claims)

    exempt_types = sorted(c["claim_type"] for c in exempt)
    # The invented ones: a practice answer, a worked example, a self-assessment.
    assert "practice_answer" in exempt_types
    assert "review_checklist_item" in exempt_types
    assert "worked_example_content" in exempt_types


def test_source_grounded_fields_are_still_judged_end_to_end():
    claims = extract.extract_claims(v2_book())
    judgeable, _exempt = audit.partition_source_claims(claims)

    judged_types = sorted(c["claim_type"] for c in judgeable)
    for expected in (
        "chapter_summary",
        "core_lesson_explanation",
        "key_term_definition",
        "learning_objective",
        "misconception_correction",
        "misconception_statement",
        "worked_example_explanation",
    ):
        assert expected in judged_types


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
