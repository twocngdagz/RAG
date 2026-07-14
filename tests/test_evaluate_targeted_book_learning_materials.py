import argparse
import json
import os
import re
import tempfile
import time
from pathlib import Path

import pytest

import evaluate_targeted_book_learning_materials as eval34


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def quote_for(chapter_number: int, index: int) -> str:
    if index == 1:
        aliases = {
            2: "wanted regular past tense ed ending pronunciation evidence has enough words.",
            11: "spelling zero score write from dictation evidence has enough words.",
            15: "highlight correct summary task evidence has enough words.",
            16: "essay timing minutes time limit evidence has enough words.",
        }
        if chapter_number in aliases:
            return aliases[chapter_number]
    labels = ["alpha", "beta", "gamma", "delta"]
    return f"chapter {chapter_number} {labels[index - 1]} concept evidence has enough words."


def probe_concept_title(chapter_number: int) -> str:
    return {
        2: "Wanted -ed ending pronunciation",
        11: "Spelling zero score",
        15: "Highlight Correct Summary",
        16: "Essay timing",
    }.get(chapter_number, "Concept 1")


def clean_chunk(chapter_number: int) -> dict:
    quotes = [quote_for(chapter_number, index) for index in range(1, 5)]
    exact = f"Exact copied learner phrase for chapter {chapter_number}."
    return {
        "id": f"pte_chunk_{chapter_number:03d}",
        "source_pdf": "input/pdfs/pte.pdf",
        "source_type": "pdf",
        "book_id": "pte",
        "book_title": "PTE",
        "chapter": f"LESSON {chapter_number}",
        "chapter_number": chapter_number,
        "section": f"Lesson {chapter_number}",
        "topic": f"Lesson {chapter_number}",
        "content_type": "unknown",
        "page_start": chapter_number,
        "page_end": chapter_number,
        "is_front_matter": False,
        "text": " ".join(quotes + [exact, "Extra source context for learners."]),
        "metadata": {},
    }


def grounded(
    *,
    text,
    claim_kind: str,
    origin: str,
    source_id: str,
    reason: str | None = None,
    evidence_quote: str | None = None,
) -> dict:
    source_ids = [source_id] if origin == "source_grounded" else []
    spans = []
    if evidence_quote:
        spans = [{"node_id": source_id, "quote": evidence_quote}]
    return {
        "text": text,
        "claim_kind": claim_kind,
        "origin": origin,
        "source_chunk_ids": source_ids,
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": spans,
        "reason": reason,
    }


def v2_chapter(chapter_number: int) -> dict:
    source_id = f"pte_chunk_{chapter_number:03d}"
    return {
        "chapter_number": chapter_number,
        "chapter_title": f"LESSON {chapter_number}",
        "source_chunk_ids": [source_id],
        "estimated_study_time": grounded(
            text=f"Study chapter {chapter_number} for a generated practice session.",
            claim_kind="study_plan",
            origin="pedagogical_generation",
            source_id=source_id,
        ),
        "chapter_summary": grounded(
            text=f"Exact copied learner phrase for chapter {chapter_number}.",
            claim_kind="source_summary",
            origin="source_grounded",
            source_id=source_id,
        ),
        "learning_objectives": [
            grounded(
                text=f"Paraphrased objective for chapter {chapter_number}.",
                claim_kind="learning_objective",
                origin="source_grounded",
                source_id=source_id,
            )
        ],
        "key_terms": [
            {
                "term": "Damaged source item",
                "meaning": grounded(
                    text=None,
                    claim_kind="definition",
                    origin="insufficient_source_evidence",
                    source_id=source_id,
                    reason="The source notation is damaged.",
                ),
            }
        ],
        "core_lessons": [
            {
                "title": "Task format",
                "explanation": grounded(
                    text=f"Task format statement for chapter {chapter_number}.",
                    claim_kind="task_format",
                    origin="source_grounded",
                    source_id=source_id,
                    evidence_quote=quote_for(chapter_number, 1),
                ),
            }
        ],
        "worked_examples": [
            {
                "title": "Generated example",
                "example": grounded(
                    text=f"Generated example for chapter {chapter_number}.",
                    claim_kind="pedagogical_example",
                    origin="pedagogical_generation",
                    source_id=source_id,
                ),
                "explanation": grounded(
                    text=f"Supported explanation for chapter {chapter_number}.",
                    claim_kind="strategy",
                    origin="source_grounded",
                    source_id=source_id,
                ),
            }
        ],
        "common_misconceptions": [
            {
                "misconception": grounded(
                    text=f"Generated misconception for chapter {chapter_number}.",
                    claim_kind="misconception_statement",
                    origin="pedagogical_generation",
                    source_id=source_id,
                ),
                "correction": grounded(
                    text=None,
                    claim_kind="misconception_correction",
                    origin="insufficient_source_evidence",
                    source_id=source_id,
                    reason="The source does not clearly support a correction.",
                ),
            }
        ],
        "practice_questions": [
            {
                "question": grounded(
                    text=f"Generated practice question for chapter {chapter_number}.",
                    claim_kind="practice_question",
                    origin="pedagogical_generation",
                    source_id=source_id,
                ),
                "answer": grounded(
                    text=f"Source-grounded answer for chapter {chapter_number}.",
                    claim_kind="practice_answer",
                    origin="source_grounded",
                    source_id=source_id,
                ),
            }
        ],
        "review_checklist": [
            grounded(
                text=f"Generated checklist item for chapter {chapter_number}.",
                claim_kind="self_assessment",
                origin="pedagogical_generation",
                source_id=source_id,
            )
        ],
    }


def v1_claim(claim_id: str, chapter_number: int, status: str = "SUPPORTED") -> dict:
    return {
        "claim_id": claim_id,
        "json_path": f"$.claims.{claim_id}",
        "chapter_number": chapter_number,
        "claim_type": "core_lesson_explanation",
        "claim_text": f"Generated v1 claim {claim_id}.",
        "source_chunk_ids": [f"pte_chunk_{chapter_number:03d}"],
        "support_status": status,
        "claim_nature": "task_format",
        "severity": "HIGH" if status != "SUPPORTED" else "LOW",
        "confidence": "HIGH",
        "rationale": "Existing Step 34B judgment.",
        "supported_elements": [],
        "unsupported_elements": [],
        "contradicted_elements": [],
        "evidence_chunk_ids_used": [f"pte_chunk_{chapter_number:03d}"],
        "recommended_action": "keep",
    }


def fixture_files(tmp_path: Path):
    selected = eval34.SELECTED_CHAPTER_NUMBERS
    v1_book = {
        "book": {"source_pdf": "input/pdfs/pte.pdf"},
        "learning_materials": {
            "chapters": [
                {"chapter_number": number, "chapter_title": f"LESSON {number}"}
                for number in selected
            ]
        },
    }
    known_by_chapter = {
        probe["chapter_number"]: probe["v1_claim_id"]
        for probe in eval34.KNOWN_PATTERN_PROBES
    }
    results = []
    for number in selected:
        results.append(v1_claim(known_by_chapter[number], number, "UNSUPPORTED"))
        results.append(v1_claim(f"chapter_{number:02d}.chapter_summary", number, "SUPPORTED"))
    v1_audit = {
        "schema_version": eval34.V1_AUDIT_SCHEMA_VERSION,
        "run_status": "COMPLETE",
        "audit_verdict": "FAIL",
        "summary": {"claim_count": len(results)},
        "results": results,
        "priority_findings": [],
        "warnings": [],
        "errors": [],
    }
    v2_book = {
        "schema_version": eval34.V2_BOOK_SCHEMA_VERSION,
        "book": {
            "slug": "pte",
            "title": "PTE",
            "source_pdf": "input/pdfs/pte.pdf",
        },
        "generation": {
            "pipeline_version": eval34.V2_BOOK_SCHEMA_VERSION,
            "selection_mode": "chapters",
            "selected_chapter_numbers": selected,
            "book_synthesis_performed": False,
        },
        "learning_materials": {"chapters": [v2_chapter(number) for number in selected]},
        "source_chunks": [],
        "audit": {},
    }
    v2_contract = {
        "schema_version": eval34.V2_CONTRACT_AUDIT_SCHEMA_VERSION,
        "status": "PASS",
        "summary": {
            "grounded_content_count": 48,
            "source_grounded_count": 20,
            "pedagogical_generation_count": 20,
            "insufficient_source_evidence_count": 8,
            "invalid_claim_count": 0,
        },
        "errors": [],
        "warnings": [],
    }
    chunks = [clean_chunk(number) for number in selected]
    paths = {
        "v1_book": tmp_path / "output/v1.json",
        "v1_audit": tmp_path / "output/v1.audit.json",
        "v2_book": tmp_path / "output/v2.json",
        "v2_contract": tmp_path / "output/v2.contract.json",
        "chunks": tmp_path / "extracted/chunks.json",
        "output": tmp_path / "output/evaluation.json",
        "report": tmp_path / "output/evaluation.txt",
        "checkpoint": tmp_path / "output/evaluation.checkpoint.json",
    }
    write_json(paths["v1_book"], v1_book)
    write_json(paths["v1_audit"], v1_audit)
    write_json(paths["v2_book"], v2_book)
    write_json(paths["v2_contract"], v2_contract)
    write_json(paths["chunks"], chunks)
    return paths


def args_for(paths: dict[str, Path], **overrides) -> argparse.Namespace:
    values = {
        "v1_book_file": str(paths["v1_book"]),
        "v1_audit_file": str(paths["v1_audit"]),
        "v2_book_file": str(paths["v2_book"]),
        "v2_contract_audit_file": str(paths["v2_contract"]),
        "clean_chunks_file": str(paths["chunks"]),
        "output": str(paths["output"]),
        "report": str(paths["report"]),
        "checkpoint": str(paths["checkpoint"]),
        "model": "test-model",
        "model_timeout_seconds": 5,
        "model_max_retries": 0,
        "model_retry_backoff_seconds": 0,
        "max_new_evaluation_chapters": None,
        "evaluation_chapter_number": None,
        "reevaluate_selected_chapter": False,
        "resume": False,
        "overwrite": False,
        "dry_run": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def source_concepts(chapter_number: int) -> dict:
    return {
        "chapter_number": chapter_number,
        "concepts": [
            {
                "concept_id": f"chapter_{chapter_number:02d}.concept_{index:02d}",
                "title": probe_concept_title(chapter_number) if index == 1 else f"Concept {index}",
                "importance": "HIGH" if index <= 2 else ("MEDIUM" if index == 3 else "LOW"),
                "concept_type": "task_format" if index == 1 else "source_topic",
                "source_condition": "DAMAGED" if index == 2 else "CLEAR",
                "description": f"Concept {index} description.",
                "source_chunk_ids": [f"pte_chunk_{chapter_number:03d}"],
                "evidence_spans": [
                    {
                        "node_id": f"pte_chunk_{chapter_number:03d}",
                        "quote": quote_for(chapter_number, index),
                    }
                ],
            }
            for index in range(1, 5)
        ],
    }


def evaluation_response(chapter_number: int, records: list[dict], v1_status: str) -> dict:
    record_results = []
    source_grounded_records = [record for record in records if record["origin"] == "source_grounded"]
    insufficient_records = [
        record for record in records if record["origin"] == "insufficient_source_evidence"
    ]
    for record in records:
        if record["origin"] == "source_grounded":
            record_results.append(
                {
                    "record_id": record["record_id"],
                    "semantic_support_status": "SUPPORTED",
                    "pedagogical_quality_status": "NOT_APPLICABLE",
                    "abstention_status": "NOT_APPLICABLE",
                    "severity": "LOW",
                    "confidence": "HIGH",
                    "rationale": "Supported by the cited source.",
                    "supported_elements": ["supported"],
                    "unsupported_elements": [],
                    "contradicted_elements": [],
                    "evidence_chunk_ids_used": record["source_chunk_ids"][:1],
                    "concept_ids": [f"chapter_{chapter_number:02d}.concept_01"],
                }
            )
        elif record["origin"] == "pedagogical_generation":
            record_results.append(
                {
                    "record_id": record["record_id"],
                    "semantic_support_status": "NOT_APPLICABLE",
                    "pedagogical_quality_status": "USABLE",
                    "abstention_status": "NOT_APPLICABLE",
                    "severity": "LOW",
                    "confidence": "HIGH",
                    "rationale": "The activity is self-contained.",
                    "supported_elements": [],
                    "unsupported_elements": [],
                    "contradicted_elements": [],
                    "evidence_chunk_ids_used": [],
                    "concept_ids": [f"chapter_{chapter_number:02d}.concept_01"],
                }
            )
        else:
            record_results.append(
                {
                    "record_id": record["record_id"],
                    "semantic_support_status": "NOT_APPLICABLE",
                    "pedagogical_quality_status": "NOT_APPLICABLE",
                    "abstention_status": "JUSTIFIED",
                    "severity": "LOW",
                    "confidence": "HIGH",
                    "rationale": "The source is insufficient for the withheld field.",
                    "supported_elements": [],
                    "unsupported_elements": [],
                    "contradicted_elements": [],
                    "evidence_chunk_ids_used": [f"pte_chunk_{chapter_number:03d}"],
                    "concept_ids": [f"chapter_{chapter_number:02d}.concept_02"],
                }
            )
    coverage = [
        {
            "concept_id": f"chapter_{chapter_number:02d}.concept_01",
            "importance": "HIGH",
            "source_condition": "CLEAR",
            "v1_coverage_status": "COVERED_UNSAFELY",
            "v1_claim_ids": [
                next(
                    probe["v1_claim_id"]
                    for probe in eval34.KNOWN_PATTERN_PROBES
                    if probe["chapter_number"] == chapter_number
                )
            ],
            "v2_coverage_status": "COVERED_SAFELY",
            "v2_record_ids": [source_grounded_records[0]["record_id"]],
            "rationale": "V2 covers the concept safely.",
        },
        {
            "concept_id": f"chapter_{chapter_number:02d}.concept_02",
            "importance": "HIGH",
            "source_condition": "DAMAGED",
            "v1_coverage_status": "COVERED_UNSAFELY",
            "v1_claim_ids": [],
            "v2_coverage_status": "SAFELY_WITHHELD",
            "v2_record_ids": [insufficient_records[0]["record_id"]],
            "rationale": "The damaged concept is explicitly withheld.",
        },
        {
            "concept_id": f"chapter_{chapter_number:02d}.concept_03",
            "importance": "MEDIUM",
            "source_condition": "CLEAR",
            "v1_coverage_status": "OMITTED",
            "v1_claim_ids": [],
            "v2_coverage_status": "PARTIALLY_COVERED",
            "v2_record_ids": [source_grounded_records[0]["record_id"]],
            "rationale": "Only part of the concept is covered.",
        },
        {
            "concept_id": f"chapter_{chapter_number:02d}.concept_04",
            "importance": "LOW",
            "source_condition": "CLEAR",
            "v1_coverage_status": "OMITTED",
            "v1_claim_ids": [],
            "v2_coverage_status": "SILENTLY_OMITTED",
            "v2_record_ids": [],
            "rationale": "A low-importance concept is omitted.",
        },
    ]
    probe = next(
        item for item in eval34.KNOWN_PATTERN_PROBES if item["chapter_number"] == chapter_number
    )
    return {
        "chapter_number": chapter_number,
        "v2_record_evaluations": record_results,
        "concept_coverage": coverage,
        "known_pattern_traces": [
            {
                "probe_id": probe["probe_id"],
                "chapter_number": chapter_number,
                "source_condition": "CLEAR",
                "matching_concept_ids": [f"chapter_{chapter_number:02d}.concept_01"],
                "v1_claim_id": probe["v1_claim_id"],
                "v1_support_status": v1_status,
                "v2_status": "COVERED_SAFELY",
                "v2_record_ids": [source_grounded_records[0]["record_id"]],
                "conclusion": "The known pattern is safely represented.",
            }
        ],
    }


def fake_complete_factory(bundle: eval34.InputBundle, *, malformed_first: bool = False):
    state_path = Path(tempfile.mkdtemp(prefix="eval34_fake_complete_")) / "state.json"
    write_json(state_path, {"count": 0, "malformed_sent": False})
    v1_status_by_chapter = {
        number: bundle.v1_results_by_chapter[number][0]["support_status"]
        for number in bundle.selected_chapter_numbers
    }

    def complete(prompt: str) -> str:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["count"] += 1
        if malformed_first and not state["malformed_sent"]:
            state["malformed_sent"] = True
            write_json(state_path, state)
            return "{not json"
        write_json(state_path, state)
        match = re.search(r"Chapter number: (\d+)", prompt)
        assert match, prompt[:300]
        chapter_number = int(match.group(1))
        if eval34.TARGETED_SOURCE_CONCEPT_PROMPT_VERSION in prompt:
            assert "Generated v1 claim" not in prompt
            assert "Task format statement" not in prompt
            return json.dumps(source_concepts(chapter_number))
        if eval34.TARGETED_V2_COMPARISON_PROMPT_VERSION in prompt:
            assert "pte_chunk_001" not in prompt
            return json.dumps(
                evaluation_response(
                    chapter_number,
                    bundle.v2_records_by_chapter[chapter_number],
                    v1_status_by_chapter[chapter_number],
                )
            )
        if "Repair this malformed JSON response" in prompt:
            return json.dumps(source_concepts(chapter_number))
        raise AssertionError(prompt[:500])

    complete.call_count = lambda: json.loads(state_path.read_text(encoding="utf-8"))["count"]
    return complete


def load_bundle(
    paths: dict[str, Path],
    *,
    selected_chapter_numbers: list[int] | None = None,
) -> eval34.InputBundle:
    return eval34.load_and_validate_inputs(
        v1_book_file=paths["v1_book"],
        v1_audit_file=paths["v1_audit"],
        v2_book_file=paths["v2_book"],
        v2_contract_audit_file=paths["v2_contract"],
        clean_chunks_file=paths["chunks"],
        selected_chapter_numbers=selected_chapter_numbers,
        expected_v1_result_count=None,
    )


def pad_v1_audit_to_live_result_count(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data["results"]
    for index in range(len(results), eval34.EXPECTED_LIVE_V1_RESULT_COUNT):
        results.append(v1_claim(f"padding_claim_{index:03d}", 99, "SUPPORTED"))
    data["summary"]["claim_count"] = len(results)
    write_json(path, data)


def write_checkpoint_with_completed_concepts(
    paths: dict[str, Path],
    bundle: eval34.InputBundle,
    *,
    completed_evaluations: list[int] | None = None,
) -> None:
    checkpoint = eval34.initial_checkpoint(bundle=bundle, model="test-model")
    checkpoint["completed_source_concept_chapters"] = eval34.SELECTED_CHAPTER_NUMBERS[:]
    checkpoint["source_concepts_by_chapter"] = {
        str(number): source_concepts(number)
        for number in eval34.SELECTED_CHAPTER_NUMBERS
    }
    checkpoint["completed_evaluation_chapters"] = completed_evaluations or []
    checkpoint["evaluations_by_chapter"] = {
        str(number): evaluation_response(
            number,
            bundle.v2_records_by_chapter[number],
            bundle.v1_results_by_chapter[number][0]["support_status"],
        )
        for number in (completed_evaluations or [])
    }
    write_json(paths["checkpoint"], checkpoint)


def evaluation_only_complete(bundle: eval34.InputBundle, call_log_path: Path):
    def complete(prompt: str) -> str:
        assert eval34.TARGETED_SOURCE_CONCEPT_PROMPT_VERSION not in prompt
        assert eval34.TARGETED_V2_COMPARISON_PROMPT_VERSION in prompt
        match = re.search(r"Chapter number: (\d+)", prompt)
        assert match, prompt[:300]
        chapter_number = int(match.group(1))
        with call_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{chapter_number}\n")
        return json.dumps(
            evaluation_response(
                chapter_number,
                bundle.v2_records_by_chapter[chapter_number],
                bundle.v1_results_by_chapter[chapter_number][0]["support_status"],
            )
        )

    return complete


def read_call_log(path: Path) -> list[int]:
    if not path.exists():
        return []
    return [
        int(line.strip())
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def hanging_complete_with_pid(pid_path: Path, sleep_seconds: float = 60):
    def complete(_prompt: str) -> str:
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(sleep_seconds)
        return "{}"

    return complete


def wait_for_pid_file(path: Path) -> int:
    deadline = time.time() + 5
    while time.time() < deadline:
        if path.exists():
            return int(path.read_text(encoding="utf-8"))
        time.sleep(0.05)
    raise AssertionError(f"PID file was not written: {path}")


def assert_process_gone(pid: int) -> None:
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    raise AssertionError(f"Worker process still exists: {pid}")


def test_loads_inputs_filters_v1_and_extracts_48_v2_records(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)

    assert bundle.selected_chapter_numbers == [2, 11, 15, 16]
    assert sum(len(bundle.v1_results_by_chapter[n]) for n in eval34.SELECTED_CHAPTER_NUMBERS) == 8
    assert len(bundle.v2_records) == 48
    assert bundle.v2_records[0]["record_id"] == "chapter_02.estimated_study_time"
    assert bundle.v2_records[0]["json_path"] == "$.learning_materials.chapters[0].estimated_study_time"
    assert bundle.v2_records[1]["text_derivation"] == "exact_source_text"
    assert bundle.v2_records[2]["text_derivation"] == "source_paraphrase"
    assert "text_preview" not in json.dumps(bundle.v2_records)


def test_loads_inputs_with_exact_chapter_scope_filters_v1_and_v2(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths, selected_chapter_numbers=[15])

    assert bundle.selected_chapter_numbers == [15]
    assert list(bundle.v1_results_by_chapter) == [15]
    assert len(bundle.v1_results) == 2
    assert [result["chapter_number"] for result in bundle.v1_results] == [15, 15]
    assert list(bundle.v2_records_by_chapter) == [15]
    assert len(bundle.v2_records) == 12
    assert {record["chapter_number"] for record in bundle.v2_records} == {15}


def test_max_new_evaluation_chapters_cli_parsing():
    args = eval34.parse_args(
        [
            "--v1-book-file",
            "v1.json",
            "--v1-audit-file",
            "v1.audit.json",
            "--v2-book-file",
            "v2.json",
            "--v2-contract-audit-file",
            "v2.contract.json",
            "--clean-chunks-file",
            "chunks.json",
            "--output",
            "out.json",
            "--max-new-evaluation-chapters",
            "1",
        ]
    )
    assert args.max_new_evaluation_chapters == 1

    for value in ["0", "-1"]:
        with pytest.raises(SystemExit):
            eval34.parse_args(
                [
                    "--v1-book-file",
                    "v1.json",
                    "--v1-audit-file",
                    "v1.audit.json",
                    "--v2-book-file",
                    "v2.json",
                    "--v2-contract-audit-file",
                    "v2.contract.json",
                    "--clean-chunks-file",
                    "chunks.json",
                    "--output",
                    "out.json",
                    "--max-new-evaluation-chapters",
                    value,
                ]
            )


def test_evaluation_chapter_number_cli_parsing():
    args = eval34.parse_args(
        [
            "--v1-book-file",
            "v1.json",
            "--v1-audit-file",
            "v1.audit.json",
            "--v2-book-file",
            "v2.json",
            "--v2-contract-audit-file",
            "v2.contract.json",
            "--clean-chunks-file",
            "chunks.json",
            "--output",
            "out.json",
            "--evaluation-chapter-number",
            "2",
        ]
    )
    assert args.evaluation_chapter_number == 2

    for value in ["0", "-1"]:
        with pytest.raises(SystemExit):
            eval34.parse_args(
                [
                    "--v1-book-file",
                    "v1.json",
                    "--v1-audit-file",
                    "v1.audit.json",
                    "--v2-book-file",
                    "v2.json",
                    "--v2-contract-audit-file",
                    "v2.contract.json",
                    "--clean-chunks-file",
                    "chunks.json",
                    "--output",
                    "out.json",
                    "--evaluation-chapter-number",
                    value,
                ]
            )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["v1_audit"].update(run_status="IN_PROGRESS"), "run_status"),
        (lambda data: data["v2_contract"].update(status="FAIL"), "status"),
        (
            lambda data: data["v2_book"]["generation"].update(selected_chapter_numbers=[2, 11]),
            "selected_chapter_numbers",
        ),
        (
            lambda data: data["v2_book"]["learning_materials"].update(
                chapters=list(reversed(data["v2_book"]["learning_materials"]["chapters"]))
            ),
            "V2 chapters",
        ),
        (lambda data: data["chunks"].append(dict(data["chunks"][0])), "Duplicate clean chunk ID"),
    ],
)
def test_input_validation_rejects_bad_artifacts(tmp_path, mutate, message):
    paths = fixture_files(tmp_path)
    data = {
        "v1_audit": json.loads(paths["v1_audit"].read_text()),
        "v2_contract": json.loads(paths["v2_contract"].read_text()),
        "v2_book": json.loads(paths["v2_book"].read_text()),
        "chunks": json.loads(paths["chunks"].read_text()),
    }
    mutate(data)
    write_json(paths["v1_audit"], data["v1_audit"])
    write_json(paths["v2_contract"], data["v2_contract"])
    write_json(paths["v2_book"], data["v2_book"])
    write_json(paths["chunks"], data["chunks"])

    with pytest.raises(eval34.TargetedEvaluationError, match=message):
        load_bundle(paths)


def test_source_concept_prompt_and_validation_rules(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    prompt = eval34.build_source_concept_prompt(
        chapter_number=2,
        chapter_title="LESSON 2",
        chapter_chunks=bundle.chunks_by_chapter[2],
    )
    assert "Generated v1 claim" not in prompt
    assert "Task format statement" not in prompt
    assert "pte_chunk_002" in prompt

    valid = eval34.validate_source_concept_inventory(
        source_concepts(2),
        chapter_number=2,
        chapter_chunks=bundle.chunks_by_chapter[2],
        clean_chunks_by_id=bundle.clean_chunks_by_id,
    )
    assert len(valid["concepts"]) == 4

    bad_source = source_concepts(2)
    bad_source["concepts"][0]["source_chunk_ids"] = ["invented"]
    with pytest.raises(eval34.ModelJSONError, match="outside the chapter"):
        eval34.validate_source_concept_inventory(
            bad_source,
            chapter_number=2,
            chapter_chunks=bundle.chunks_by_chapter[2],
            clean_chunks_by_id=bundle.clean_chunks_by_id,
        )

    bad_duplicate = source_concepts(2)
    bad_duplicate["concepts"][1]["concept_id"] = bad_duplicate["concepts"][0]["concept_id"]
    with pytest.raises(eval34.ModelJSONError, match="Expected concept_id"):
        eval34.validate_source_concept_inventory(
            bad_duplicate,
            chapter_number=2,
            chapter_chunks=bundle.chunks_by_chapter[2],
            clean_chunks_by_id=bundle.clean_chunks_by_id,
        )


def test_chapter_evaluation_validation_enforces_ids_and_status_combinations(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    concepts = source_concepts(2)
    valid = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")
    normalized = eval34.validate_chapter_evaluation(
        valid,
        chapter_number=2,
        concepts=concepts,
        v1_results=bundle.v1_results_by_chapter[2],
        v2_records=bundle.v2_records_by_chapter[2],
        chapter_chunks=bundle.chunks_by_chapter[2],
    )
    assert len(normalized["v2_record_evaluations"]) == 12
    assert len(normalized["concept_coverage"]) == 4
    assert normalized["known_pattern_traces"][0]["probe_id"] == "wanted_pronunciation"

    missing = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")
    missing["v2_record_evaluations"].pop()
    with pytest.raises(eval34.ModelJSONError, match="Missing"):
        eval34.validate_chapter_evaluation(
            missing,
            chapter_number=2,
            concepts=concepts,
            v1_results=bundle.v1_results_by_chapter[2],
            v2_records=bundle.v2_records_by_chapter[2],
            chapter_chunks=bundle.chunks_by_chapter[2],
        )

    bad_combo = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")
    bad_combo["v2_record_evaluations"][0]["semantic_support_status"] = "SUPPORTED"
    with pytest.raises(eval34.ModelJSONError, match="pedagogical status combination"):
        eval34.validate_chapter_evaluation(
            bad_combo,
            chapter_number=2,
            concepts=concepts,
            v1_results=bundle.v1_results_by_chapter[2],
            v2_records=bundle.v2_records_by_chapter[2],
            chapter_chunks=bundle.chunks_by_chapter[2],
        )

    bad_evidence = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")
    bad_evidence["v2_record_evaluations"][1]["evidence_chunk_ids_used"] = ["invented"]
    with pytest.raises(eval34.ModelJSONError, match="invented"):
        eval34.validate_chapter_evaluation(
            bad_evidence,
            chapter_number=2,
            concepts=concepts,
            v1_results=bundle.v1_results_by_chapter[2],
            v2_records=bundle.v2_records_by_chapter[2],
            chapter_chunks=bundle.chunks_by_chapter[2],
        )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("PARTIALLY_SUPPORTED", "PARTIALLY_COVERED"),
        ("UNSUPPORTED", "COVERED_UNSAFELY"),
        ("CONTRADICTED", "COVERED_UNSAFELY"),
        ("SOURCE_DAMAGED", "COVERED_UNSAFELY"),
        ("SUPPORTED", "COVERED_SAFELY"),
    ],
)
def test_v1_concept_coverage_is_calculated_from_step34b_status(tmp_path, status, expected):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    concepts = source_concepts(2)
    response = evaluation_response(2, bundle.v2_records_by_chapter[2], status)
    response["concept_coverage"][0]["v1_coverage_status"] = "COVERED_SAFELY"
    v1_results = json.loads(json.dumps(bundle.v1_results_by_chapter[2]))
    v1_results[0]["support_status"] = status

    normalized = eval34.validate_chapter_evaluation(
        response,
        chapter_number=2,
        concepts=concepts,
        v1_results=v1_results,
        v2_records=bundle.v2_records_by_chapter[2],
        chapter_chunks=bundle.chunks_by_chapter[2],
    )

    coverage = normalized["concept_coverage"][0]
    assert coverage["v1_coverage_status"] == expected
    assert coverage["v1_claim_statuses"] == {v1_results[0]["claim_id"]: status}


def test_no_mapped_v1_claims_maps_to_omitted(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    response = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")
    response["concept_coverage"][0]["v1_claim_ids"] = []
    response["concept_coverage"][0]["v1_coverage_status"] = "COVERED_SAFELY"

    normalized = eval34.validate_chapter_evaluation(
        response,
        chapter_number=2,
        concepts=source_concepts(2),
        v1_results=bundle.v1_results_by_chapter[2],
        v2_records=bundle.v2_records_by_chapter[2],
        chapter_chunks=bundle.chunks_by_chapter[2],
    )

    assert normalized["concept_coverage"][0]["v1_coverage_status"] == "OMITTED"


def test_not_a_factual_only_v1_mapping_is_rejected(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    response = evaluation_response(2, bundle.v2_records_by_chapter[2], "NOT_A_FACTUAL_CLAIM")
    v1_results = json.loads(json.dumps(bundle.v1_results_by_chapter[2]))
    v1_results[0]["support_status"] = "NOT_A_FACTUAL_CLAIM"

    with pytest.raises(eval34.ModelJSONError, match="NOT_A_FACTUAL_CLAIM"):
        eval34.validate_chapter_evaluation(
            response,
            chapter_number=2,
            concepts=source_concepts(2),
            v1_results=v1_results,
            v2_records=bundle.v2_records_by_chapter[2],
            chapter_chunks=bundle.chunks_by_chapter[2],
        )


def test_wanted_probe_rejects_word_boundary_only_concept(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    concepts = source_concepts(2)
    concepts["concepts"][0]["title"] = "Consonants at word boundaries"
    concepts["concepts"][0]["description"] = "A pronunciation detail about consonants at word boundaries."
    concepts["concepts"][0]["evidence_spans"][0]["quote"] = quote_for(2, 3)
    response = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")

    normalized = eval34.validate_chapter_evaluation(
        response,
        chapter_number=2,
        concepts=concepts,
        v1_results=bundle.v1_results_by_chapter[2],
        v2_records=bundle.v2_records_by_chapter[2],
        chapter_chunks=bundle.chunks_by_chapter[2],
    )

    trace = normalized["known_pattern_traces"][0]
    assert trace["matching_concept_ids"] == []
    assert trace["warnings"][0]["code"] == "KNOWN_PATTERN_CONCEPT_MISMATCH"


def test_wanted_probe_accepts_ed_ending_concept(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    response = evaluation_response(2, bundle.v2_records_by_chapter[2], "UNSUPPORTED")

    normalized = eval34.validate_chapter_evaluation(
        response,
        chapter_number=2,
        concepts=source_concepts(2),
        v1_results=bundle.v1_results_by_chapter[2],
        v2_records=bundle.v2_records_by_chapter[2],
        chapter_chunks=bundle.chunks_by_chapter[2],
    )

    assert normalized["known_pattern_traces"][0]["matching_concept_ids"] == ["chapter_02.concept_01"]


def test_highlight_correct_summary_requires_summary_terminology(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    concepts = source_concepts(15)
    concepts["concepts"][0]["title"] = "Highlight the correct answer"
    concepts["concepts"][0]["description"] = "A concept about choosing an answer."
    concepts["concepts"][0]["evidence_spans"][0]["quote"] = quote_for(15, 3)
    response = evaluation_response(15, bundle.v2_records_by_chapter[15], "UNSUPPORTED")

    normalized = eval34.validate_chapter_evaluation(
        response,
        chapter_number=15,
        concepts=concepts,
        v1_results=bundle.v1_results_by_chapter[15],
        v2_records=bundle.v2_records_by_chapter[15],
        chapter_chunks=bundle.chunks_by_chapter[15],
    )

    assert normalized["known_pattern_traces"][0]["matching_concept_ids"] == []


def test_essay_timing_requires_essay_and_timing_terminology(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    concepts = source_concepts(16)
    concepts["concepts"][0]["title"] = "Essay structure"
    concepts["concepts"][0]["description"] = "A concept about essay paragraph structure."
    concepts["concepts"][0]["evidence_spans"][0]["quote"] = quote_for(16, 3)
    response = evaluation_response(16, bundle.v2_records_by_chapter[16], "UNSUPPORTED")

    normalized = eval34.validate_chapter_evaluation(
        response,
        chapter_number=16,
        concepts=concepts,
        v1_results=bundle.v1_results_by_chapter[16],
        v2_records=bundle.v2_records_by_chapter[16],
        chapter_chunks=bundle.chunks_by_chapter[16],
    )

    assert normalized["known_pattern_traces"][0]["matching_concept_ids"] == []


def test_empty_slash_pronunciation_notation_forces_damaged():
    quote = "wanted pronunciation / / evidence has enough words."
    chunk = clean_chunk(2)
    chunk["text"] += f" {quote}"
    concepts = source_concepts(2)
    concepts["concepts"][0]["source_condition"] = "CLEAR"
    concepts["concepts"][0]["evidence_spans"][0]["quote"] = quote

    normalized = eval34.validate_source_concept_inventory(
        concepts,
        chapter_number=2,
        chapter_chunks=[chunk],
        clean_chunks_by_id={chunk["id"]: chunk},
    )

    concept = normalized["concepts"][0]
    assert concept["source_condition"] == "DAMAGED"
    assert concept["warnings"][0]["code"] == "PRONUNCIATION_SOURCE_DAMAGED"


def test_unrelated_slash_notation_does_not_damage_non_pronunciation_concept():
    quote = "general slash / / evidence has enough words."
    chunk = clean_chunk(2)
    chunk["text"] += f" {quote}"
    concepts = source_concepts(2)
    concepts["concepts"][0]["title"] = "General source formatting"
    concepts["concepts"][0]["description"] = "A concept about generic formatting."
    concepts["concepts"][0]["source_condition"] = "CLEAR"
    concepts["concepts"][0]["evidence_spans"][0]["quote"] = quote

    normalized = eval34.validate_source_concept_inventory(
        concepts,
        chapter_number=2,
        chapter_chunks=[chunk],
        clean_chunks_by_id={chunk["id"]: chunk},
    )

    assert normalized["concepts"][0]["source_condition"] == "CLEAR"
    assert normalized["concepts"][0]["warnings"] == []


def test_dry_run_writes_nothing_and_overwrite_protects_outputs(tmp_path, capsys):
    paths = fixture_files(tmp_path)
    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, dry_run=True),
        complete_fn=lambda _prompt: pytest.fail("dry run should not call model"),
        expected_v1_result_count=None,
    )
    assert result is None
    assert not paths["output"].exists()
    assert not paths["checkpoint"].exists()
    out = capsys.readouterr().out
    assert "V2 grounded-content records: 48" in out
    assert "Model calls made: 0" in out

    write_json(paths["output"], {"existing": True})
    with pytest.raises(eval34.TargetedEvaluationError, match="already exists"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(paths),
            complete_fn=lambda _prompt: pytest.fail("should not call model"),
            expected_v1_result_count=None,
        )
    assert json.loads(paths["output"].read_text()) == {"existing": True}


def test_dry_run_with_exact_chapter_selects_only_that_chapter(tmp_path, capsys):
    paths = fixture_files(tmp_path)
    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, dry_run=True, evaluation_chapter_number=15),
        complete_fn=lambda _prompt: pytest.fail("dry run should not call model"),
        expected_v1_result_count=None,
    )

    assert result is None
    assert not paths["output"].exists()
    assert not paths["checkpoint"].exists()
    out = capsys.readouterr().out
    assert "Selected chapters: 15" in out
    assert "V1 filtered claims: 2" in out
    assert "V2 grounded-content records: 12" in out
    assert "Planned source-concept calls: 1" in out
    assert "Planned chapter-evaluation calls: 1" in out
    assert "Planned normal model calls: 2" in out
    assert "Model calls made: 0" in out


def test_fresh_exact_chapter_run_creates_only_requested_checkpoint_scope(tmp_path):
    paths = fixture_files(tmp_path)
    call_log_path = tmp_path / "calls.txt"

    def complete(prompt: str) -> str:
        match = re.search(r"Chapter number: (\d+)", prompt)
        assert match, prompt[:300]
        chapter_number = int(match.group(1))
        with call_log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{chapter_number}\n")
        if eval34.TARGETED_SOURCE_CONCEPT_PROMPT_VERSION in prompt:
            return json.dumps(source_concepts(chapter_number))
        if eval34.TARGETED_V2_COMPARISON_PROMPT_VERSION in prompt:
            bundle = load_bundle(paths, selected_chapter_numbers=[15])
            return json.dumps(
                evaluation_response(
                    chapter_number,
                    bundle.v2_records_by_chapter[chapter_number],
                    bundle.v1_results_by_chapter[chapter_number][0]["support_status"],
                )
            )
        raise AssertionError(prompt[:500])

    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, overwrite=True, evaluation_chapter_number=15),
        complete_fn=complete,
        expected_v1_result_count=None,
    )

    assert result is not None
    assert read_call_log(call_log_path) == [15, 15]
    assert result["input"]["selected_chapter_numbers"] == [15]
    assert result["summary"]["v1_claim_count"] == 2
    assert result["summary"]["v2_record_count"] == 12
    assert [chapter["chapter_number"] for chapter in result["chapters"]] == [15]
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["selected_chapter_numbers"] == [15]
    assert checkpoint["planned_source_concept_calls"] == 1
    assert checkpoint["planned_chapter_evaluation_calls"] == 1
    assert checkpoint["completed_source_concept_chapters"] == [15]
    assert checkpoint["completed_evaluation_chapters"] == [15]
    assert set(checkpoint["source_concepts_by_chapter"]) == {"15"}
    assert set(checkpoint["evaluations_by_chapter"]) == {"15"}


def test_limited_run_reuses_source_concepts_and_evaluates_one_chapter(tmp_path, capsys):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle)
    call_log_path = tmp_path / "evaluation-calls.txt"

    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, resume=True, max_new_evaluation_chapters=1),
        complete_fn=evaluation_only_complete(bundle, call_log_path),
        expected_v1_result_count=None,
    )

    assert result is None
    assert read_call_log(call_log_path) == [2]
    assert not paths["output"].exists()
    assert not paths["report"].exists()
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["status"] == "IN_PROGRESS"
    assert checkpoint["completed_source_concept_chapters"] == [2, 11, 15, 16]
    assert checkpoint["completed_evaluation_chapters"] == [2]
    assert checkpoint["last_run"] == {
        "max_new_evaluation_chapters": 1,
        "newly_completed_evaluation_chapters": [2],
        "stopped_due_to_limit": True,
    }
    out = capsys.readouterr().out
    assert "Completed source-concept chapters reused: 2, 11, 15, 16" in out
    assert "New chapter-evaluation limit: 1" in out
    assert "Chapter evaluated this run: 2" in out
    assert "Remaining evaluation chapters: 11, 15, 16" in out
    assert "Final evaluation not written." in out


def test_limited_run_skips_completed_evaluations_and_preserves_order(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle, completed_evaluations=[2])
    call_log_path = tmp_path / "evaluation-calls.txt"

    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, resume=True, max_new_evaluation_chapters=1),
        complete_fn=evaluation_only_complete(bundle, call_log_path),
        expected_v1_result_count=None,
    )

    assert result is None
    assert read_call_log(call_log_path) == [11]
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_evaluation_chapters"] == [2, 11]
    assert checkpoint["last_run"]["newly_completed_evaluation_chapters"] == [11]


def test_unknown_evaluation_chapter_is_rejected(tmp_path):
    paths = fixture_files(tmp_path)
    with pytest.raises(eval34.TargetedEvaluationError, match="evaluation-chapter-number"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(paths, dry_run=True, evaluation_chapter_number=99),
            complete_fn=lambda _prompt: pytest.fail("unknown chapter should not call model"),
            expected_v1_result_count=None,
        )


def test_exact_chapter_selection_stops_when_selected_chapter_complete(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle, completed_evaluations=[2])
    call_log_path = tmp_path / "evaluation-calls.txt"

    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, resume=True, evaluation_chapter_number=2),
        complete_fn=evaluation_only_complete(bundle, call_log_path),
        expected_v1_result_count=None,
    )

    assert result is None
    assert read_call_log(call_log_path) == []
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_evaluation_chapters"] == [2]
    assert not paths["output"].exists()
    assert not paths["report"].exists()


def test_exact_chapter_selection_runs_only_requested_incomplete_chapter(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle, completed_evaluations=[2])
    call_log_path = tmp_path / "evaluation-calls.txt"

    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, resume=True, evaluation_chapter_number=11),
        complete_fn=evaluation_only_complete(bundle, call_log_path),
        expected_v1_result_count=None,
    )

    assert result is None
    assert read_call_log(call_log_path) == [11]
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_evaluation_chapters"] == [2, 11]
    assert checkpoint["last_run"]["stopped_after_exact_chapter"] is True
    assert not paths["output"].exists()
    assert not paths["report"].exists()


def test_reevaluate_selected_chapter_requires_resume_and_chapter(tmp_path):
    paths = fixture_files(tmp_path)
    with pytest.raises(eval34.TargetedEvaluationError, match="requires --resume"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(
                paths,
                reevaluate_selected_chapter=True,
                evaluation_chapter_number=2,
            ),
            complete_fn=lambda _prompt: pytest.fail("invalid options should not call model"),
            expected_v1_result_count=None,
        )
    with pytest.raises(eval34.TargetedEvaluationError, match="requires --evaluation-chapter-number"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(paths, resume=True, reevaluate_selected_chapter=True),
            complete_fn=lambda _prompt: pytest.fail("invalid options should not call model"),
            expected_v1_result_count=None,
        )


def test_successful_reevaluation_replaces_only_selected_chapter(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle, completed_evaluations=[2, 11])
    checkpoint = json.loads(paths["checkpoint"].read_text())
    checkpoint["evaluations_by_chapter"]["2"]["v2_record_evaluations"][0]["rationale"] = "old chapter 2 result"
    old_chapter_11 = checkpoint["evaluations_by_chapter"]["11"]
    write_json(paths["checkpoint"], checkpoint)
    call_log_path = tmp_path / "evaluation-calls.txt"

    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(
            paths,
            resume=True,
            evaluation_chapter_number=2,
            reevaluate_selected_chapter=True,
        ),
        complete_fn=evaluation_only_complete(bundle, call_log_path),
        expected_v1_result_count=None,
    )

    assert result is None
    assert read_call_log(call_log_path) == [2]
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_source_concept_chapters"] == [2, 11, 15, 16]
    assert checkpoint["completed_evaluation_chapters"] == [2, 11]
    assert checkpoint["evaluations_by_chapter"]["2"]["v2_record_evaluations"][0]["rationale"] != "old chapter 2 result"
    assert checkpoint["evaluations_by_chapter"]["11"] == old_chapter_11


def test_failed_reevaluation_preserves_previous_valid_result(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle, completed_evaluations=[2])
    original = json.loads(paths["checkpoint"].read_text())["evaluations_by_chapter"]["2"]

    def invalid_complete(_prompt: str) -> str:
        return "{not json"

    with pytest.raises(eval34.ModelJSONError):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(
                paths,
                resume=True,
                evaluation_chapter_number=2,
                reevaluate_selected_chapter=True,
            ),
            complete_fn=invalid_complete,
            expected_v1_result_count=None,
        )

    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_evaluation_chapters"] == [2]
    assert checkpoint["evaluations_by_chapter"]["2"] == original
    assert checkpoint["errors"][-1]["error_type"] == "ModelJSONError"


def test_timeout_during_reevaluation_preserves_previous_valid_result(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle, completed_evaluations=[2])
    original = json.loads(paths["checkpoint"].read_text())["evaluations_by_chapter"]["2"]
    pid_path = tmp_path / "reeval-worker.pid"

    with pytest.raises(eval34.ModelCallTimeoutError):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(
                paths,
                resume=True,
                evaluation_chapter_number=2,
                reevaluate_selected_chapter=True,
                model_timeout_seconds=1,
                model_max_retries=0,
            ),
            complete_fn=hanging_complete_with_pid(pid_path),
            expected_v1_result_count=None,
        )

    assert_process_gone(wait_for_pid_file(pid_path))
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_evaluation_chapters"] == [2]
    assert checkpoint["evaluations_by_chapter"]["2"] == original
    assert checkpoint["errors"][-1]["error_type"] == "ModelCallTimeoutError"


def test_end_to_end_fake_model_checkpoint_resume_and_final_summary(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    complete = fake_complete_factory(bundle)
    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, overwrite=True),
        complete_fn=complete,
        expected_v1_result_count=None,
    )

    assert result is not None
    assert result["schema_version"] == eval34.EVALUATION_SCHEMA_VERSION
    assert result["run_status"] == "COMPLETE"
    assert result["summary"]["v2_record_count"] == 48
    assert result["summary"]["concept_count"] == 16
    assert result["summary"]["v1_high_severity_unsafe_count"] == 4
    assert result["generation"]["model_call_count"] == 8
    assert result["generation"]["repair_call_count"] == 0
    assert result["coverage_verdict"] == "PASS_WITH_WARNINGS"
    assert result["comparison_verdict"] == "IMPROVED_WITH_COVERAGE_WARNINGS"
    assert len(result["known_pattern_traces"]) == 4
    assert paths["output"].exists()
    assert paths["report"].exists()
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["status"] == "COMPLETE"
    assert checkpoint["completed_source_concept_chapters"] == [2, 11, 15, 16]
    assert checkpoint["completed_evaluation_chapters"] == [2, 11, 15, 16]

    resume_complete = fake_complete_factory(bundle)
    resumed = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, resume=True),
        complete_fn=resume_complete,
        expected_v1_result_count=None,
    )
    assert resumed is not None
    assert resume_complete.call_count() == 0


def test_repair_is_attempted_once_and_raw_response_is_saved(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    complete = fake_complete_factory(bundle, malformed_first=True)
    result = eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, overwrite=True),
        complete_fn=complete,
        expected_v1_result_count=None,
    )

    assert result is not None
    assert result["generation"]["repair_call_count"] == 1
    raw_dir = paths["output"].with_name("evaluation.raw")
    assert (raw_dir / "chapter_02.source_concepts.invalid.raw_response.txt").exists()


def test_hanging_normal_model_call_is_terminated(tmp_path):
    pid_path = tmp_path / "worker.pid"
    with pytest.raises(eval34.ModelCallTimeoutError, match="chapter_evaluation chapter 2"):
        eval34.complete_with_retries(
            "prompt",
            model="test-model",
            timeout_seconds=1,
            max_retries=0,
            retry_backoff_seconds=0,
            complete_fn=hanging_complete_with_pid(pid_path),
            stage_label="chapter_evaluation",
            chapter_number=2,
            call_kind="initial",
        )
    assert_process_gone(wait_for_pid_file(pid_path))


def test_hanging_repair_model_call_is_terminated(tmp_path):
    pid_path = tmp_path / "repair-worker.pid"
    invalid_sent_path = tmp_path / "initial-invalid-sent"

    def complete(_prompt: str) -> str:
        if not invalid_sent_path.exists():
            invalid_sent_path.write_text("1", encoding="utf-8")
            return "{not json"
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(60)
        return "{}"

    args = argparse.Namespace(
        model="test-model",
        model_timeout_seconds=1,
        model_max_retries=0,
        model_retry_backoff_seconds=0,
    )
    with pytest.raises(eval34.ModelCallTimeoutError, match="repair"):
        eval34.call_json_stage_with_repair(
            stage_id="chapter_02.evaluation",
            stage_label="chapter_evaluation",
            chapter_number=2,
            prompt="prompt",
            expected_ids=[],
            validate_fn=lambda parsed: {"parsed": parsed},
            args=args,
            raw_dir=tmp_path / "raw",
            stats=eval34.RuntimeStats(),
            complete_fn=complete,
        )
    assert_process_gone(wait_for_pid_file(pid_path))


def test_timeout_preserves_checkpoint_and_records_error(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle)
    pid_path = tmp_path / "eval-worker.pid"

    with pytest.raises(eval34.ModelCallTimeoutError):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(
                paths,
                resume=True,
                model_timeout_seconds=1,
                model_max_retries=0,
            ),
            complete_fn=hanging_complete_with_pid(pid_path),
            expected_v1_result_count=None,
        )

    assert_process_gone(wait_for_pid_file(pid_path))
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["status"] == "IN_PROGRESS"
    assert checkpoint["completed_source_concept_chapters"] == [2, 11, 15, 16]
    assert checkpoint["completed_evaluation_chapters"] == []
    assert checkpoint["errors"][-1]["error_type"] == "ModelCallTimeoutError"
    assert checkpoint["errors"][-1]["stage"] == "chapter_evaluation"
    assert checkpoint["errors"][-1]["chapter_number"] == 2
    assert not paths["output"].exists()
    assert not paths["report"].exists()


def test_cli_timeout_exits_nonzero_without_live_call(tmp_path, monkeypatch):
    paths = fixture_files(tmp_path)
    pad_v1_audit_to_live_result_count(paths["v1_audit"])
    bundle = load_bundle(paths)
    write_checkpoint_with_completed_concepts(paths, bundle)
    pid_path = tmp_path / "cli-worker.pid"

    def fake_default_complete(_prompt: str, *, model: str, timeout_seconds: int) -> str:
        pid_path.write_text(str(os.getpid()), encoding="utf-8")
        time.sleep(60)
        return "{}"

    monkeypatch.setattr(eval34, "default_complete", fake_default_complete)
    exit_code = eval34.main(
        [
            "--v1-book-file",
            str(paths["v1_book"]),
            "--v1-audit-file",
            str(paths["v1_audit"]),
            "--v2-book-file",
            str(paths["v2_book"]),
            "--v2-contract-audit-file",
            str(paths["v2_contract"]),
            "--clean-chunks-file",
            str(paths["chunks"]),
            "--output",
            str(paths["output"]),
            "--report",
            str(paths["report"]),
            "--checkpoint",
            str(paths["checkpoint"]),
            "--model",
            "test-model",
            "--model-timeout-seconds",
            "1",
            "--model-max-retries",
            "0",
            "--resume",
        ]
    )

    assert exit_code == 1
    assert_process_gone(wait_for_pid_file(pid_path))
    checkpoint = json.loads(paths["checkpoint"].read_text())
    assert checkpoint["completed_evaluation_chapters"] == []
    assert checkpoint["errors"][-1]["error_type"] == "ModelCallTimeoutError"


def test_resume_rejects_input_hash_prompt_and_model_mismatch(tmp_path):
    paths = fixture_files(tmp_path)
    bundle = load_bundle(paths)
    eval34.evaluate_targeted_book_learning_materials(
        args_for(paths, overwrite=True),
        complete_fn=fake_complete_factory(bundle),
        expected_v1_result_count=None,
    )

    checkpoint = json.loads(paths["checkpoint"].read_text())
    checkpoint["model"] = "other-model"
    write_json(paths["checkpoint"], checkpoint)
    with pytest.raises(eval34.TargetedEvaluationError, match="model changed"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(paths, resume=True),
            complete_fn=lambda _prompt: pytest.fail("should not call model"),
            expected_v1_result_count=None,
        )

    checkpoint["model"] = "test-model"
    checkpoint["source_concept_prompt_version"] = "old"
    write_json(paths["checkpoint"], checkpoint)
    with pytest.raises(eval34.TargetedEvaluationError, match="source prompt version"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(paths, resume=True),
            complete_fn=lambda _prompt: pytest.fail("should not call model"),
            expected_v1_result_count=None,
        )

    checkpoint["source_concept_prompt_version"] = eval34.TARGETED_SOURCE_CONCEPT_PROMPT_VERSION
    checkpoint["input_hashes"]["v1_book"] = "changed"
    write_json(paths["checkpoint"], checkpoint)
    with pytest.raises(eval34.TargetedEvaluationError, match="input hashes"):
        eval34.evaluate_targeted_book_learning_materials(
            args_for(paths, resume=True),
            complete_fn=lambda _prompt: pytest.fail("should not call model"),
            expected_v1_result_count=None,
        )


def test_verdict_helpers_cover_pass_warning_and_fail():
    base_summary = {
        "v2_high_severity_unsafe_count": 0,
        "pedagogical_misleading_count": 0,
        "high_importance_covered_unsafely_count": 0,
        "pedagogical_needs_revision_count": 0,
        "abstention_overcautious_count": 0,
        "abstention_misaligned_count": 0,
        "high_importance_silently_omitted_count": 0,
        "v2_partially_covered_count": 0,
        "medium_importance_silently_omitted_count": 0,
        "v2_safely_withheld_count": 0,
        "v1_high_severity_unsafe_count": 2,
    }
    safe_eval = {2: {"v2_record_evaluations": []}}
    assert eval34.safety_verdict(base_summary, safe_eval) == "PASS"
    assert eval34.coverage_verdict(base_summary) == "PASS"
    assert eval34.comparison_verdict(base_summary, "PASS", "PASS") == "IMPROVED"

    warning_summary = dict(base_summary, pedagogical_needs_revision_count=1, v2_safely_withheld_count=1)
    assert eval34.safety_verdict(warning_summary, safe_eval) == "PASS_WITH_WARNINGS"
    assert eval34.coverage_verdict(warning_summary) == "PASS_WITH_WARNINGS"
    assert (
        eval34.comparison_verdict(
            dict(warning_summary, v2_high_severity_unsafe_count=0),
            "PASS_WITH_WARNINGS",
            "PASS_WITH_WARNINGS",
        )
        == "IMPROVED_WITH_COVERAGE_WARNINGS"
    )

    fail_summary = dict(base_summary, v2_high_severity_unsafe_count=2)
    assert eval34.safety_verdict(fail_summary, safe_eval) == "FAIL"
    assert eval34.comparison_verdict(fail_summary, "FAIL", "PASS") == "NOT_IMPROVED"
