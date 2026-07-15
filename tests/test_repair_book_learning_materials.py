"""Tests for the audit-feedback repair pass.

Chapters passed the contract but failed the semantic audit on one recurring
defect: a grounded text asserting more than its evidence spans cover. The repair
feeds each flagged claim back to the model to cite more or narrow, and normalizes
the result through the generator's own enforcement so an unfixable claim is
downgraded, never kept as an over-claim.
"""

import json

import pytest

import repair_book_learning_materials as repair


SOURCE = "The box contains six to eight words. The categories are words, noun forms and verb forms."
CLEAN_LOOKUP = {"c1": {"id": "c1", "text": SOURCE}}
COVERING_QUOTE = "The categories are words, noun forms and verb forms"


def book_with_overclaim():
    return {
        "learning_materials": {
            "chapters": [
                {
                    "chapter_number": 3,
                    "source_chunk_ids": ["c1"],
                    "worked_examples": [
                        {
                            "title": "W",
                            "explanation": {
                                "text": "Categories: words, noun forms, verb forms, synonyms, antonyms.",
                                "claim_kind": "strategy",
                                "origin": "source_grounded",
                                "source_chunk_ids": ["c1"],
                                "grounded_in_source_chunk_ids": [],
                                "evidence_spans": [{"node_id": "c1", "quote": "The categories are words"}],
                                "reason": None,
                            },
                        }
                    ],
                }
            ]
        }
    }


def audit_flagging(json_path, status="PARTIALLY_SUPPORTED"):
    return {
        "audit_verdict": "FAIL",
        "results": [
            {"claim_id": "x", "json_path": json_path, "support_status": status,
             "claim_text": "Categories..."}
        ],
    }


PATH = "$.learning_materials.chapters[0].worked_examples[0].explanation"


# --------------------------------------------------------------------------- #
# json_path navigation
# --------------------------------------------------------------------------- #

def test_parse_json_path_mixes_keys_and_indices():
    assert repair.parse_json_path(PATH) == [
        "learning_materials", "chapters", 0, "worked_examples", 0, "explanation"
    ]


def test_get_and_set_round_trip():
    book = book_with_overclaim()
    tokens = repair.parse_json_path(PATH)
    obj = repair.get_at(book, tokens)
    assert obj["claim_kind"] == "strategy"
    repair.set_at(book, tokens, {"replaced": True})
    assert book["learning_materials"]["chapters"][0]["worked_examples"][0]["explanation"] == {"replaced": True}


# --------------------------------------------------------------------------- #
# Finding selection
# --------------------------------------------------------------------------- #

def test_only_repairable_statuses_are_selected():
    audit = {"results": [
        {"json_path": "a", "support_status": "PARTIALLY_SUPPORTED"},
        {"json_path": "b", "support_status": "UNSUPPORTED"},
        {"json_path": "c", "support_status": "CONTRADICTED"},
        {"json_path": "d", "support_status": "SUPPORTED"},
        {"json_path": "e", "support_status": "SOURCE_DAMAGED"},
        {"json_path": "f", "support_status": "NOT_A_FACTUAL_CLAIM"},
    ]}
    paths = {f["json_path"] for f in repair.repairable_findings(audit)}
    assert paths == {"a", "b", "c"}


def test_source_damaged_is_reported_separately_not_repaired():
    audit = {"results": [{"json_path": "e", "support_status": "SOURCE_DAMAGED"}]}
    assert repair.repairable_findings(audit) == []
    assert [f["json_path"] for f in repair.unrepairable_findings(audit)] == ["e"]


# --------------------------------------------------------------------------- #
# Repair pass with a fake model
# --------------------------------------------------------------------------- #

def fake_model_returns(obj):
    return lambda _prompt: json.dumps(obj)


def test_repair_replaces_the_field_when_model_covers_the_claim():
    book = book_with_overclaim()
    fixed = {
        "text": "The categories are words, noun forms and verb forms.",
        "claim_kind": "strategy",
        "origin": "source_grounded",
        "source_chunk_ids": ["c1"],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": [{"node_id": "c1", "quote": COVERING_QUOTE}],
        "reason": None,
    }
    book, log = repair.repair_book(
        book, audit_flagging(PATH),
        clean_lookup=CLEAN_LOOKUP, complete_fn=fake_model_returns(fixed),
    )
    assert log[0]["outcome"] == "repaired"
    new = repair.get_at(book, repair.parse_json_path(PATH))
    assert new["evidence_spans"] == [{"node_id": "c1", "quote": COVERING_QUOTE}]


def test_uncoverable_repair_is_downgraded_not_kept_as_overclaim():
    # Model returns a claim whose "span" is not in the source: normalization must
    # downgrade it rather than leave an over-claim labelled source_grounded.
    book = book_with_overclaim()
    bogus = {
        "text": "An assertion the source does not support.",
        "claim_kind": "strategy",
        "origin": "source_grounded",
        "source_chunk_ids": ["c1"],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": [{"node_id": "c1", "quote": "a phrase absent from the source text"}],
        "reason": None,
    }
    book, log = repair.repair_book(
        book, audit_flagging(PATH),
        clean_lookup=CLEAN_LOOKUP, complete_fn=fake_model_returns(bogus),
    )
    assert log[0]["outcome"] == "downgraded"
    new = repair.get_at(book, repair.parse_json_path(PATH))
    assert new["origin"] == "insufficient_source_evidence"
    assert new["text"] is None


def test_unusable_model_output_keeps_the_original():
    book = book_with_overclaim()
    original = repair.get_at(book, repair.parse_json_path(PATH))
    book, log = repair.repair_book(
        book, audit_flagging(PATH),
        clean_lookup=CLEAN_LOOKUP, complete_fn=lambda _p: "not json at all",
    )
    assert log[0]["outcome"] == "unchanged"
    assert repair.get_at(book, repair.parse_json_path(PATH)) == original


def test_a_supported_book_has_nothing_to_repair():
    book = book_with_overclaim()
    calls = []
    book, log = repair.repair_book(
        book, {"results": [{"json_path": PATH, "support_status": "SUPPORTED"}]},
        clean_lookup=CLEAN_LOOKUP, complete_fn=lambda p: calls.append(p) or "{}",
    )
    assert log == []
    assert calls == []  # model is never called when nothing is flagged
