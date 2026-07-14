import argparse
import json
from pathlib import Path

import pytest

import audit_book_claim_support as audit


def claim(
    claim_id: str,
    *,
    chapter_number: int | None,
    source_chunk_ids: list[str],
    claim_type: str = "key_term_definition",
    claim_text: str | None = None,
    citation_origin: str = "local",
) -> dict:
    return {
        "claim_id": claim_id,
        "json_path": f"$.claims.{claim_id}",
        "scope": "chapter" if chapter_number is not None else "book",
        "chapter_number": chapter_number,
        "chapter_title": f"LESSON {chapter_number}" if chapter_number else None,
        "claim_type": claim_type,
        "claim_text": claim_text or f"Claim text for {claim_id}.",
        "context": {"title": "Context title"},
        "citation_origin": citation_origin,
        "source_chunk_ids": source_chunk_ids,
        "evidence_status": "RESOLVED" if source_chunk_ids else "NO_CITATION",
    }


def evidence(node_id: str, *, text: str | None = None, chapter_number: int | None = 1) -> dict:
    return {
        "node_id": node_id,
        "source_pdf": "input/pdfs/pte.pdf",
        "chapter_number": chapter_number,
        "chapter": f"LESSON {chapter_number}" if chapter_number else None,
        "section": "Section",
        "topic": "Topic",
        "page_start": chapter_number or 1,
        "page_end": chapter_number or 1,
        "text": text or f"FULL authoritative evidence text for {node_id}.",
    }


def artifact() -> dict:
    claims = [
        claim(
            "book.book_overview",
            chapter_number=None,
            source_chunk_ids=[],
            claim_type="book_overview",
            citation_origin="none",
            claim_text="A generated overview for learners.",
        ),
        claim(
            "chapter_01.key_terms.0.meaning",
            chapter_number=1,
            source_chunk_ids=["e1"],
            claim_type="key_term_definition",
            claim_text="A supported definition.",
        ),
        claim(
            "chapter_01.core_lessons.0.explanation",
            chapter_number=1,
            source_chunk_ids=["e1", "e2"],
            claim_type="core_lesson_explanation",
            claim_text="A multi-part lesson explanation.",
        ),
        claim(
            "chapter_02.worked_examples.2.explanation",
            chapter_number=2,
            source_chunk_ids=["e3"],
            claim_type="worked_example_explanation",
            claim_text="A pronunciation rule about wanted.",
        ),
    ]
    evidence_chunks = [
        evidence("e1", chapter_number=1, text="FULL TEXT E1 supports a definition."),
        evidence("e2", chapter_number=1, text="FULL TEXT E2 supports a lesson."),
        evidence("e3", chapter_number=2, text="FULL TEXT E3 has damaged phonetic notation �."),
    ]
    return {
        "schema_version": "book_claim_evidence.v1",
        "status": "PASS",
        "input": {
            "book_file": "output/pte.book_learning_materials.generated.json",
            "clean_chunks_file": "extracted/pte.section_clean_chunks.json",
            "source_pdf": "input/pdfs/pte.pdf",
            "book_slug": "pte",
            "pipeline_version": "book_learning_materials.v1",
        },
        "summary": {
            "claim_count": len(claims),
            "unique_evidence_chunk_count": len(evidence_chunks),
        },
        "claims": claims,
        "evidence_chunks": evidence_chunks,
        "errors": [],
        "warnings": [],
    }


def write_artifact(path: Path, data: dict | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data or artifact(), indent=2), encoding="utf-8")
    return path


def make_args(tmp_path: Path, **overrides) -> argparse.Namespace:
    defaults = {
        "input": str(tmp_path / "claim_evidence.json"),
        "output": str(tmp_path / "audit.json"),
        "report": str(tmp_path / "audit.txt"),
        "checkpoint": str(tmp_path / "audit.checkpoint.json"),
        "model": "test-model",
        "batch_size": 2,
        "model_timeout_seconds": 30,
        "model_max_retries": 0,
        "model_retry_backoff_seconds": 0,
        "claim_id": [],
        "resume": False,
        "overwrite": False,
        "dry_run": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def result_for_claim_id(claim_id: str) -> dict:
    if claim_id == "book.book_overview":
        return {
            "claim_id": claim_id,
            "support_status": "NOT_A_FACTUAL_CLAIM",
            "claim_nature": "study_plan",
            "severity": "LOW",
            "confidence": "HIGH",
            "rationale": "This is generated learner guidance rather than a source fact.",
            "supported_elements": [],
            "unsupported_elements": [],
            "contradicted_elements": [],
            "evidence_chunk_ids_used": [],
        }
    if claim_id == "chapter_02.worked_examples.2.explanation":
        return {
            "claim_id": claim_id,
            "support_status": "SOURCE_DAMAGED",
            "claim_nature": "factual_explanation",
            "severity": "LOW",
            "confidence": "LOW",
            "rationale": "The cited phonetic evidence is damaged.",
            "supported_elements": [],
            "unsupported_elements": [],
            "contradicted_elements": [],
            "evidence_chunk_ids_used": ["e3"],
        }
    return {
        "claim_id": claim_id,
        "support_status": "SUPPORTED",
        "claim_nature": "definition",
        "severity": "MEDIUM",
        "confidence": "HIGH",
        "rationale": "The evidence directly supports the claim.",
        "supported_elements": ["The definition is present."],
        "unsupported_elements": [],
        "contradicted_elements": [],
        "evidence_chunk_ids_used": ["e1"] if claim_id.endswith("meaning") else ["e1", "e2"],
    }


def claims_from_prompt(prompt: str) -> list[dict]:
    marker = "Claims to audit:\n"
    evidence_marker = "\n\nClaims to audit:\n"
    text = prompt.split(marker, 1)[1]
    return json.loads(text)


def fake_complete(prompt: str) -> str:
    return json.dumps({"results": [result_for_claim_id(item["claim_id"]) for item in claims_from_prompt(prompt)]})


def test_loads_valid_artifact_and_rejects_malformed_inputs(tmp_path):
    valid = artifact()
    assert audit.validate_claim_evidence_artifact(valid)["status"] == "PASS"

    bad = artifact()
    bad["schema_version"] = "wrong"
    with pytest.raises(audit.BookClaimSupportAuditError, match="Unsupported schema"):
        audit.validate_claim_evidence_artifact(bad)

    bad = artifact()
    bad["status"] = "FAIL"
    with pytest.raises(audit.BookClaimSupportAuditError, match="status must be PASS"):
        audit.validate_claim_evidence_artifact(bad)

    bad = artifact()
    bad["claims"].append(dict(bad["claims"][0]))
    with pytest.raises(audit.BookClaimSupportAuditError, match="Duplicate claim ID"):
        audit.validate_claim_evidence_artifact(bad)

    bad = artifact()
    bad["evidence_chunks"].append(dict(bad["evidence_chunks"][0]))
    with pytest.raises(audit.BookClaimSupportAuditError, match="Duplicate evidence ID"):
        audit.validate_claim_evidence_artifact(bad)

    bad = artifact()
    bad["claims"][1]["source_chunk_ids"] = ["missing"]
    with pytest.raises(audit.BookClaimSupportAuditError, match="missing evidence"):
        audit.validate_claim_evidence_artifact(bad)

    bad = artifact()
    bad["evidence_chunks"][0]["text"] = ""
    with pytest.raises(audit.BookClaimSupportAuditError, match="empty text"):
        audit.validate_claim_evidence_artifact(bad)

    bad = artifact()
    bad["evidence_chunks"][0]["text_preview"] = "preview"
    with pytest.raises(audit.BookClaimSupportAuditError, match="text_preview"):
        audit.validate_claim_evidence_artifact(bad)


def test_claim_selection_preserves_original_order_and_rejects_bad_ids():
    data = artifact()
    selected, mode, requested = audit.select_claims(
        data["claims"],
        [
            "chapter_02.worked_examples.2.explanation",
            "chapter_01.key_terms.0.meaning",
        ],
    )

    assert mode == "claim_ids"
    assert requested == [
        "chapter_02.worked_examples.2.explanation",
        "chapter_01.key_terms.0.meaning",
    ]
    assert [item["claim_id"] for item in selected] == [
        "chapter_01.key_terms.0.meaning",
        "chapter_02.worked_examples.2.explanation",
    ]

    selected_all, mode_all, requested_all = audit.select_claims(data["claims"], [])
    assert mode_all == "all"
    assert requested_all == []
    assert selected_all == data["claims"]

    with pytest.raises(audit.BookClaimSupportAuditError, match="Unknown"):
        audit.select_claims(data["claims"], ["missing"])
    with pytest.raises(audit.BookClaimSupportAuditError, match="Duplicate requested"):
        audit.select_claims(data["claims"], ["book.book_overview", "book.book_overview"])


def test_batching_groups_only_identical_chapter_and_ordered_evidence():
    data = artifact()
    batches = audit.build_batches(data["claims"], batch_size=2)

    keys = [(batch.chapter_number, batch.source_chunk_ids) for batch in batches]
    assert keys == [
        (None, ()),
        (1, ("e1",)),
        (1, ("e1", "e2")),
        (2, ("e3",)),
    ]

    changed = artifact()
    changed["claims"][2]["source_chunk_ids"] = ["e2", "e1"]
    batches = audit.build_batches(changed["claims"], batch_size=10)
    assert (1, ("e2", "e1")) in [
        (batch.chapter_number, batch.source_chunk_ids) for batch in batches
    ]


def test_prompt_uses_full_exact_evidence_and_no_unrelated_evidence():
    data = artifact()
    evidence_by_id = audit.evidence_lookup(data)
    batch = audit.PlannedBatch(
        batch_id="batch_0001",
        chapter_number=1,
        source_chunk_ids=("e1",),
        claims=[data["claims"][1]],
    )

    prompt = audit.build_judge_prompt(batch=batch, evidence_by_id=evidence_by_id)

    assert "Use only the supplied evidence" in prompt
    assert "FULL TEXT E1 supports a definition." in prompt
    assert "FULL TEXT E2 supports a lesson." not in prompt
    assert "FULL TEXT E3 has damaged" not in prompt

    uncited = audit.PlannedBatch(
        batch_id="batch_0002",
        chapter_number=None,
        source_chunk_ids=(),
        claims=[data["claims"][0]],
    )
    prompt = audit.build_judge_prompt(batch=uncited, evidence_by_id=evidence_by_id)
    assert '"node_id"' not in prompt.split("Evidence chunks", 1)[1].split("Claims to audit", 1)[0]


def test_model_result_validation_success_and_severity_floor():
    data = artifact()
    batch_claims = [data["claims"][3]]
    model_result = [result_for_claim_id("chapter_02.worked_examples.2.explanation")]

    [result] = audit.validate_model_batch_results(
        batch_claims=batch_claims,
        raw_results=model_result,
    )

    assert result["support_status"] == "SOURCE_DAMAGED"
    assert result["model_severity"] == "LOW"
    assert result["severity"] == "HIGH"
    assert result["severity_floor_applied"] is True
    assert result["recommended_action"] == "inspect_source_and_regenerate"


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("support_status", "BAD", "support_status"),
        ("claim_nature", "BAD", "claim_nature"),
        ("severity", "BAD", "severity"),
        ("confidence", "BAD", "confidence"),
    ],
)
def test_model_result_validation_rejects_invalid_enums(field, value, match):
    data = artifact()
    model_result = result_for_claim_id("chapter_01.key_terms.0.meaning")
    model_result[field] = value

    with pytest.raises(audit.ModelJSONError, match=match):
        audit.validate_model_batch_results(
            batch_claims=[data["claims"][1]],
            raw_results=[model_result],
        )


def test_model_result_validation_rejects_missing_extra_duplicate_and_bad_evidence_ids():
    data = artifact()
    good = result_for_claim_id("chapter_01.key_terms.0.meaning")

    with pytest.raises(audit.ModelJSONError, match="missing"):
        audit.validate_model_batch_results(batch_claims=[data["claims"][1]], raw_results=[])

    extra = dict(good, claim_id="extra")
    with pytest.raises(audit.ModelJSONError, match="extra"):
        audit.validate_model_batch_results(batch_claims=[data["claims"][1]], raw_results=[extra])

    with pytest.raises(audit.ModelJSONError, match="Duplicate"):
        audit.validate_model_batch_results(
            batch_claims=[data["claims"][1]],
            raw_results=[good, good],
        )

    bad_evidence = dict(good, evidence_chunk_ids_used=["e2"])
    with pytest.raises(audit.ModelJSONError, match="outside"):
        audit.validate_model_batch_results(
            batch_claims=[data["claims"][1]],
            raw_results=[bad_evidence],
        )


def test_run_audit_writes_checkpoint_output_report_and_summary_counts(tmp_path):
    input_path = write_artifact(tmp_path / "claim_evidence.json")
    args = make_args(tmp_path)

    result = audit.run_audit(args, complete_fn=fake_complete)

    assert result is not None
    assert Path(args.output).exists()
    assert Path(args.report).exists()
    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    assert checkpoint["status"] == "COMPLETE"
    assert checkpoint["completed_claim_count"] == 4
    assert result["input"]["input_claim_count"] == 4
    assert result["input"]["selected_claim_count"] == 4
    assert result["input"]["selection_mode"] == "all"
    assert [item["claim_id"] for item in result["results"]] == [
        item["claim_id"] for item in artifact()["claims"]
    ]
    assert result["summary"]["claim_count"] == 4
    assert result["summary"]["supported_count"] == 2
    assert result["summary"]["source_damaged_count"] == 1
    assert result["summary"]["not_factual_count"] == 1
    assert result["summary"]["results_by_claim_type"]["key_term_definition"] == 1
    assert result["summary"]["results_by_claim_nature"]["definition"] == 2
    assert result["summary"]["results_by_chapter"]["2"]["high_severity_finding_count"] == 1
    assert result["priority_findings"][0]["claim_id"] == (
        "chapter_02.worked_examples.2.explanation"
    )
    assert result["audit_verdict"] == "FAIL"


def test_audit_verdicts_pass_warning_and_fail():
    supported = [dict(result_for_claim_id("chapter_01.key_terms.0.meaning"))]
    supported[0]["severity_floor_applied"] = False
    supported[0]["source_chunk_ids"] = ["e1"]
    supported[0]["claim_type"] = "key_term_definition"
    supported[0]["chapter_number"] = 1
    summary = audit.build_summary(supported)
    assert audit.audit_verdict(summary) == "PASS"

    warning = [dict(supported[0], support_status="UNSUPPORTED", severity="LOW")]
    summary = audit.build_summary(warning)
    assert audit.audit_verdict(summary) == "PASS_WITH_WARNINGS"

    failure = [dict(supported[0], support_status="UNSUPPORTED", severity="HIGH")]
    summary = audit.build_summary(failure)
    assert audit.audit_verdict(summary) == "FAIL"


def test_checkpoint_resume_processes_only_missing_claims(tmp_path):
    write_artifact(tmp_path / "claim_evidence.json")
    calls: list[list[str]] = []

    def fail_second_batch(prompt: str) -> str:
        ids = [item["claim_id"] for item in claims_from_prompt(prompt)]
        calls.append(ids)
        if len(calls) == 2:
            raise RuntimeError("interrupted")
        return json.dumps({"results": [result_for_claim_id(claim_id) for claim_id in ids]})

    args = make_args(tmp_path, batch_size=1)
    with pytest.raises(audit.BookClaimSupportAuditError, match="Resume with"):
        audit.run_audit(args, complete_fn=fail_second_batch)

    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    assert checkpoint["completed_claim_count"] == 1
    assert checkpoint["completed_claim_ids"] == ["book.book_overview"]

    resumed_calls: list[list[str]] = []

    def resume_complete(prompt: str) -> str:
        ids = [item["claim_id"] for item in claims_from_prompt(prompt)]
        resumed_calls.append(ids)
        return json.dumps({"results": [result_for_claim_id(claim_id) for claim_id in ids]})

    resume_args = make_args(tmp_path, batch_size=1, resume=True)
    result = audit.run_audit(resume_args, complete_fn=resume_complete)

    assert result is not None
    assert ["book.book_overview"] not in resumed_calls
    assert len(result["results"]) == 4


def test_resume_rejects_incompatible_checkpoint(tmp_path):
    write_artifact(tmp_path / "claim_evidence.json")
    args = make_args(tmp_path, batch_size=1)
    audit.run_audit(args, complete_fn=fake_complete)
    checkpoint_path = Path(args.checkpoint)
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    for field, value, match in [
        ("input_sha256", "bad", "SHA"),
        ("prompt_version", "bad", "prompt"),
        ("model", "other", "model"),
        ("batch_size", 99, "batch size"),
        ("selected_claim_ids", ["only"], "selected"),
    ]:
        changed = dict(checkpoint)
        changed[field] = value
        with pytest.raises(audit.BookClaimSupportAuditError, match=match):
            audit.validate_resume_checkpoint(
                checkpoint=changed,
                input_file=Path(args.input),
                input_sha256=checkpoint["input_sha256"],
                model=args.model,
                batch_size=args.batch_size,
                selected_claim_ids=checkpoint["selected_claim_ids"],
            )


def test_repair_is_attempted_for_malformed_and_schema_invalid_json(tmp_path):
    write_artifact(tmp_path / "claim_evidence.json")
    repair_calls: list[str] = []

    def bad_complete(_prompt: str) -> str:
        return "{not json"

    def repair_complete(prompt: str) -> str:
        repair_calls.append(prompt)
        return json.dumps({"results": [result_for_claim_id("chapter_01.key_terms.0.meaning")]})

    args = make_args(
        tmp_path,
        claim_id=["chapter_01.key_terms.0.meaning"],
        output=str(tmp_path / "malformed.audit.json"),
        report=str(tmp_path / "malformed.audit.txt"),
        checkpoint=str(tmp_path / "malformed.checkpoint.json"),
    )
    result = audit.run_audit(args, complete_fn=bad_complete, repair_complete_fn=repair_complete)

    assert result is not None
    assert repair_calls
    assert result["generation"]["repair_call_count"] == 1
    assert (tmp_path / "malformed.raw" / "batch_0001.invalid.raw_response.txt").exists()

    def schema_invalid(_prompt: str) -> str:
        return json.dumps({"results": [dict(result_for_claim_id("chapter_01.key_terms.0.meaning"), support_status="BAD")]})

    args = make_args(
        tmp_path,
        claim_id=["chapter_01.key_terms.0.meaning"],
        output=str(tmp_path / "schema.audit.json"),
        report=str(tmp_path / "schema.audit.txt"),
        checkpoint=str(tmp_path / "schema.checkpoint.json"),
    )
    result = audit.run_audit(args, complete_fn=schema_invalid, repair_complete_fn=repair_complete)
    assert result is not None
    assert result["generation"]["repair_call_count"] == 1


def test_repair_failure_preserves_checkpoint_and_fails_clearly(tmp_path):
    write_artifact(tmp_path / "claim_evidence.json")

    args = make_args(
        tmp_path,
        claim_id=["chapter_01.key_terms.0.meaning"],
        output=str(tmp_path / "repair_fail.audit.json"),
        report=str(tmp_path / "repair_fail.audit.txt"),
        checkpoint=str(tmp_path / "repair_fail.checkpoint.json"),
    )

    with pytest.raises(audit.BookClaimSupportAuditError, match="repair failed"):
        audit.run_audit(
            args,
            complete_fn=lambda _prompt: "{bad",
            repair_complete_fn=lambda _prompt: "{still bad",
        )

    checkpoint = json.loads(Path(args.checkpoint).read_text(encoding="utf-8"))
    assert checkpoint["completed_claim_count"] == 0
    assert checkpoint["errors"]
    assert (tmp_path / "repair_fail.raw" / "batch_0001.invalid.raw_response.txt").exists()
    assert (
        tmp_path / "repair_fail.raw" / "batch_0001.repair_invalid.raw_response.txt"
    ).exists()


def test_existing_outputs_are_protected_and_overwrite_resets(tmp_path):
    write_artifact(tmp_path / "claim_evidence.json")
    args = make_args(tmp_path)
    Path(args.output).write_text("original", encoding="utf-8")

    with pytest.raises(audit.BookClaimSupportAuditError, match="already exists"):
        audit.run_audit(args, complete_fn=fake_complete)

    assert Path(args.output).read_text(encoding="utf-8") == "original"

    overwrite_args = make_args(tmp_path, overwrite=True)
    result = audit.run_audit(overwrite_args, complete_fn=fake_complete)

    assert result is not None
    assert json.loads(Path(args.output).read_text(encoding="utf-8"))["run_status"] == "COMPLETE"


def test_dry_run_writes_nothing_and_makes_zero_model_calls(tmp_path, capsys):
    write_artifact(tmp_path / "claim_evidence.json")
    calls = []

    def should_not_call(_prompt: str) -> str:
        calls.append("called")
        raise AssertionError("model should not be called")

    args = make_args(tmp_path, dry_run=True)
    result = audit.run_audit(args, complete_fn=should_not_call)

    assert result is None
    assert calls == []
    assert not Path(args.output).exists()
    assert not Path(args.checkpoint).exists()
    captured = capsys.readouterr().out
    assert "Selected claims: 4" in captured
    assert "Model calls made: 0" in captured


def test_cli_subset_run_records_selection_metadata(tmp_path):
    write_artifact(tmp_path / "claim_evidence.json")
    args = make_args(
        tmp_path,
        claim_id=[
            "chapter_02.worked_examples.2.explanation",
            "chapter_01.key_terms.0.meaning",
        ],
    )

    result = audit.run_audit(args, complete_fn=fake_complete)

    assert result is not None
    assert result["input"]["selection_mode"] == "claim_ids"
    assert result["input"]["selected_claim_ids"] == [
        "chapter_02.worked_examples.2.explanation",
        "chapter_01.key_terms.0.meaning",
    ]
    assert [item["claim_id"] for item in result["results"]] == [
        "chapter_01.key_terms.0.meaning",
        "chapter_02.worked_examples.2.explanation",
    ]
