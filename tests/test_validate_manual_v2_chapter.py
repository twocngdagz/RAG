import copy
import json
import sys
from pathlib import Path

import pytest

import validate_manual_v2_chapter as manual


EXACT_QUOTE = "test takers hear a short question and give a brief spoken answer"


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def grounded(
    *,
    text: str | None,
    claim_kind: str,
    origin: str,
    source_ids: list[str] | None = None,
    evidence_spans: list[dict] | None = None,
    reason: str | None = None,
) -> dict:
    return {
        "text": text,
        "claim_kind": claim_kind,
        "origin": origin,
        "source_chunk_ids": source_ids or [],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": evidence_spans or [],
        "reason": reason,
    }


def valid_chapter(chapter_number: int, node_ids: list[str]) -> dict:
    def node(index: int) -> str:
        return node_ids[index % len(node_ids)]

    def source_grounded(
        text: str,
        claim_kind: str,
        index: int,
        *,
        evidence: bool = False,
    ) -> dict:
        selected = node(index)
        spans = [{"node_id": selected, "quote": EXACT_QUOTE}] if evidence else []
        return grounded(
            text=text,
            claim_kind=claim_kind,
            origin="source_grounded",
            source_ids=[selected],
            evidence_spans=spans,
        )

    return {
        "chapter_number": chapter_number,
        "chapter_title": f"Lesson {chapter_number}",
        "source_chunk_ids": node_ids,
        "estimated_study_time": grounded(
            text="Spend about 20 minutes on this generated study plan.",
            claim_kind="study_plan",
            origin="pedagogical_generation",
        ),
        "chapter_summary": source_grounded(
            "This lesson explains short spoken answers and evidence checking.",
            "source_summary",
            0,
        ),
        "learning_objectives": [
            source_grounded("Identify the short-answer task.", "learning_objective", 0),
            source_grounded("Explain why a brief answer is expected.", "learning_objective", 1),
            source_grounded("Check answers against local evidence.", "learning_objective", 2),
        ],
        "key_terms": [
            {"term": "Short answer", "meaning": source_grounded("A short answer is brief.", "definition", 0)},
            {"term": "Spoken response", "meaning": source_grounded("A spoken response is given aloud.", "definition", 1)},
            {"term": "Evidence check", "meaning": source_grounded("An evidence check uses source details.", "definition", 2)},
        ],
        "core_lessons": [
            {
                "title": "Task format",
                "explanation": source_grounded(
                    "Test takers hear a short question and give a brief spoken answer.",
                    "task_format",
                    0,
                    evidence=True,
                ),
            },
            {"title": "Answer length", "explanation": source_grounded("The answer should be concise.", "factual_explanation", 1)},
            {"title": "Listening focus", "explanation": source_grounded("Learners listen for the main point.", "strategy", 2)},
            {"title": "Evidence checking", "explanation": source_grounded("Source details help check the answer.", "strategy", 3)},
        ],
        "worked_examples": [
            {
                "title": "Generated example",
                "example": grounded(
                    text="Question: What do people use to tell time? Answer: a clock.",
                    claim_kind="pedagogical_example",
                    origin="pedagogical_generation",
                ),
                "explanation": source_grounded("A concise answer matches the task.", "strategy", 0),
            },
            {
                "title": "Generated check",
                "example": grounded(
                    text="Question: What do people drink from? Answer: a cup.",
                    claim_kind="pedagogical_example",
                    origin="pedagogical_generation",
                ),
                "explanation": source_grounded("The generated answer is short.", "strategy", 1),
            },
        ],
        "common_misconceptions": [
            {
                "misconception": source_grounded("Learners may think long answers are needed.", "misconception_statement", 2),
                "correction": source_grounded("The source describes a brief spoken answer.", "misconception_correction", 3),
            }
        ],
        "practice_questions": [
            {
                "question": grounded(text="What is the main action?", claim_kind="practice_question", origin="pedagogical_generation"),
                "answer": source_grounded("The learner gives a brief spoken answer.", "practice_answer", 0),
            },
            {
                "question": grounded(text="Give one short answer.", claim_kind="practice_question", origin="pedagogical_generation"),
                "answer": grounded(text="A short direct answer is acceptable.", claim_kind="practice_answer", origin="pedagogical_generation"),
            },
            {
                "question": grounded(text="Which detail shows the answer is brief?", claim_kind="practice_question", origin="pedagogical_generation"),
                "answer": source_grounded("The source describes the response as brief.", "practice_answer", 1),
            },
        ],
        "review_checklist": [
            grounded(text="I can identify task-format evidence.", claim_kind="self_assessment", origin="pedagogical_generation"),
            grounded(text="I can explain why answers should be brief.", claim_kind="self_assessment", origin="pedagogical_generation"),
            grounded(text="I can create a short practice answer.", claim_kind="self_assessment", origin="pedagogical_generation"),
            grounded(text="I can check my answer against evidence.", claim_kind="self_assessment", origin="pedagogical_generation"),
        ],
    }


def clean_chunk(node_id: str, chapter_number: int) -> dict:
    return {
        "id": node_id,
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
        "text": f"{node_id}: {EXACT_QUOTE}. Learners use local source evidence.",
        "metadata": {},
    }


def base_book(clean_path: Path, chapters: list[dict]) -> dict:
    return {
        "schema_version": "book_learning_materials.v2",
        "book": {"slug": "pte", "title": "PTE", "source_pdf": "input/pdfs/pte.pdf"},
        "generation": {
            "pipeline_version": "book_learning_materials.v2",
            "clean_chunks_path": str(clean_path),
        },
        "learning_materials": {"chapters": chapters},
        "source_chunks": [],
        "audit": {"status": "PASS", "contract_status": "PASS"},
    }


def fixture_files(
    tmp_path: Path,
    manual_chapter: dict | None = None,
    base: dict | None = None,
    clean_chunks: list[dict] | None = None,
):
    clean_path = tmp_path / "clean_chunks.json"
    chapter14_ids = [f"pte_chunk_14{i}" for i in range(1, 5)]
    chapter15_ids = [f"pte_chunk_15{i}" for i in range(1, 5)]
    chunks = clean_chunks or (
        [clean_chunk(node_id, 14) for node_id in chapter14_ids]
        + [clean_chunk(node_id, 15) for node_id in chapter15_ids]
    )
    write_json(clean_path, chunks)

    manual_chapter = manual_chapter or valid_chapter(15, chapter15_ids)
    base = base or base_book(
        clean_path,
        [
            valid_chapter(14, chapter14_ids),
            valid_chapter(15, chapter15_ids),
        ],
    )

    chapter_path = tmp_path / "manual_chapter.json"
    base_path = tmp_path / "base_book.json"
    write_json(chapter_path, manual_chapter)
    write_json(base_path, base)
    return chapter_path, base_path


def args_for(tmp_path: Path, chapter_path: Path, base_path: Path):
    return [
        "--chapter-file",
        str(chapter_path),
        "--base-book-file",
        str(base_path),
        "--chapter-number",
        "15",
        "--assembled-book-output",
        str(tmp_path / "assembled.json"),
        "--contract-audit-output",
        str(tmp_path / "contract.json"),
        "--contract-report-output",
        str(tmp_path / "contract.txt"),
        "--substantive-audit-output",
        str(tmp_path / "substantive.json"),
    ]


def parsed_args(tmp_path: Path, chapter_path: Path, base_path: Path):
    return manual.parse_args(args_for(tmp_path, chapter_path, base_path))


def run_adapter(
    tmp_path: Path,
    chapter: dict | None = None,
    base: dict | None = None,
    clean_chunks: list[dict] | None = None,
):
    chapter_path, base_path = fixture_files(tmp_path, chapter, base, clean_chunks)
    args = parsed_args(tmp_path, chapter_path, base_path)
    return manual.validate_manual_v2_chapter(args), args


def rewrite_source_grounded_ids(chapter: dict, node_id: str) -> dict:
    rewritten = copy.deepcopy(chapter)
    for _path, grounded_object in manual.iter_grounded_content(
        rewritten, "$.learning_materials.chapters[0]"
    ):
        if grounded_object.get("origin") == "source_grounded":
            grounded_object["source_chunk_ids"] = [node_id]
            for span in grounded_object.get("evidence_spans") or []:
                span["node_id"] = node_id
    return rewritten


def test_valid_standalone_chapter_passes_both_validators(tmp_path):
    result, _args = run_adapter(tmp_path)

    assert result["contract_audit"]["status"] == "PASS"
    assert result["substantive_audit"]["status"] == "PASS"


def test_unreferenced_empty_chunk_does_not_fail(tmp_path):
    extra = clean_chunk("pte_chunk_249", 99)
    extra["text"] = ""
    chunks = (
        [clean_chunk(f"pte_chunk_14{i}", 14) for i in range(1, 5)]
        + [clean_chunk(f"pte_chunk_15{i}", 15) for i in range(1, 5)]
        + [extra]
    )

    result, _args = run_adapter(tmp_path, clean_chunks=chunks)

    assert result["contract_audit"]["status"] == "PASS"
    assert result["substantive_audit"]["status"] == "PASS"
    assert {
        "code": "UNREFERENCED_EMPTY_CLEAN_CHUNK_IGNORED",
        "source_chunk_id": "pte_chunk_249",
        "json_path": "$[8]",
    } in result["substantive_audit"]["warnings"]


def test_referenced_empty_chunk_fails(tmp_path):
    chunks = [clean_chunk(f"pte_chunk_14{i}", 14) for i in range(1, 5)] + [
        clean_chunk(f"pte_chunk_15{i}", 15) for i in range(1, 5)
    ]
    chunks[4]["text"] = ""

    result, _args = run_adapter(tmp_path, clean_chunks=chunks)

    assert result["contract_audit"]["status"] == "FAIL"
    assert any(
        error["code"] == "EMPTY_CLEAN_CHUNK_TEXT"
        and "pte_chunk_151" in error["message"]
        for error in result["contract_audit"]["errors"]
    )


def test_missing_referenced_chunk_fails(tmp_path):
    chunks = [clean_chunk(f"pte_chunk_14{i}", 14) for i in range(1, 5)] + [
        clean_chunk(f"pte_chunk_15{i}", 15) for i in range(2, 5)
    ]

    result, _args = run_adapter(tmp_path, clean_chunks=chunks)

    assert result["contract_audit"]["status"] == "FAIL"
    assert any(
        error["code"] == "SOURCE_CHUNK_ID_NOT_FOUND"
        and "pte_chunk_151" in error["message"]
        for error in result["contract_audit"]["errors"]
    )


def test_valid_referenced_chunks_pass_with_filtered_inventory(tmp_path):
    result, _args = run_adapter(tmp_path)

    assert result["contract_audit"]["status"] == "PASS"
    assert result["contract_audit"]["summary"]["invalid_claim_count"] == 0


def test_chapter_number_mismatch_fails(tmp_path):
    chapter = valid_chapter(14, [f"pte_chunk_15{i}" for i in range(1, 5)])
    chapter_path, base_path = fixture_files(tmp_path, chapter)

    with pytest.raises(manual.ManualV2ChapterValidationError, match="chapter_number mismatch"):
        manual.validate_manual_v2_chapter(parsed_args(tmp_path, chapter_path, base_path))


def test_missing_chapter_in_base_book_fails_clearly(tmp_path):
    clean_path = tmp_path / "clean_chunks.json"
    base = base_book(clean_path, [valid_chapter(14, [f"pte_chunk_14{i}" for i in range(1, 5)])])
    chapter_path, base_path = fixture_files(tmp_path, base=base)

    with pytest.raises(manual.ManualV2ChapterValidationError, match="Chapter 15 was not found"):
        manual.validate_manual_v2_chapter(parsed_args(tmp_path, chapter_path, base_path))


def test_invalid_contract_structure_fails(tmp_path):
    chapter = valid_chapter(15, [f"pte_chunk_15{i}" for i in range(1, 5)])
    chapter["chapter_summary"] = "not grounded content"

    result, _args = run_adapter(tmp_path, chapter)

    assert result["contract_audit"]["status"] == "FAIL"


def test_substantive_minimum_failure_fails(tmp_path):
    chapter = valid_chapter(15, [f"pte_chunk_15{i}" for i in range(1, 5)])
    chapter["learning_objectives"] = chapter["learning_objectives"][:1]

    result, _args = run_adapter(tmp_path, chapter)

    assert result["substantive_audit"]["status"] == "FAIL"
    assert any(error["code"] == "TOO_FEW_LEARNING_OBJECTIVES" for error in result["substantive_audit"]["errors"])


def test_generic_placeholder_failure_fails(tmp_path):
    chapter = valid_chapter(15, [f"pte_chunk_15{i}" for i in range(1, 5)])
    chapter["chapter_summary"]["text"] = "Review the cited source excerpt."

    result, _args = run_adapter(tmp_path, chapter)

    assert result["substantive_audit"]["status"] == "FAIL"
    assert any(error["code"] == "GENERIC_PLACEHOLDER_TEXT" for error in result["substantive_audit"]["errors"])


def test_insufficient_source_use_floor_fails(tmp_path):
    node_ids = [f"pte_chunk_15{i}" for i in range(1, 5)]
    chapter = rewrite_source_grounded_ids(valid_chapter(15, node_ids), node_ids[0])

    result, _args = run_adapter(tmp_path, chapter)

    assert result["substantive_audit"]["status"] == "FAIL"
    assert any(error["code"] == "INSUFFICIENT_SOURCE_CHUNK_COVERAGE" for error in result["substantive_audit"]["errors"])


def test_valid_source_use_floor_passes(tmp_path):
    result, _args = run_adapter(tmp_path)

    assert result["substantive_audit"]["distinct_source_grounded_chunk_count"] == 4
    assert result["substantive_audit"]["status"] == "PASS"


def test_chapter_15_is_replaced(tmp_path):
    chapter = valid_chapter(15, [f"pte_chunk_15{i}" for i in range(1, 5)])
    chapter["chapter_title"] = "Manual Lesson 15"

    result, _args = run_adapter(tmp_path, chapter)

    chapters = result["assembled_book"]["learning_materials"]["chapters"]
    assert chapters[1]["chapter_title"] == "Manual Lesson 15"


def test_other_chapters_are_preserved_as_json_values(tmp_path):
    result, args = run_adapter(tmp_path)
    base = json.loads(Path(args.base_book_file).read_text(encoding="utf-8"))

    assert result["assembled_book"]["learning_materials"]["chapters"][0] == base["learning_materials"]["chapters"][0]


def test_contract_audit_json_is_written(tmp_path):
    _result, args = run_adapter(tmp_path)

    assert Path(args.contract_audit_output).exists()


def test_contract_report_text_is_written(tmp_path):
    _result, args = run_adapter(tmp_path)

    assert Path(args.contract_report_output).read_text(encoding="utf-8").startswith(
        "BOOK LEARNING MATERIALS CONTRACT AUDIT"
    )


def test_substantive_audit_json_is_written(tmp_path):
    _result, args = run_adapter(tmp_path)

    data = json.loads(Path(args.substantive_audit_output).read_text(encoding="utf-8"))
    assert data["status"] == "PASS"


def test_cli_exits_zero_when_both_validators_pass(tmp_path):
    chapter_path, base_path = fixture_files(tmp_path)

    assert manual.main(args_for(tmp_path, chapter_path, base_path)) == 0


def test_cli_exits_nonzero_when_either_validator_fails(tmp_path):
    chapter = valid_chapter(15, [f"pte_chunk_15{i}" for i in range(1, 5)])
    chapter["learning_objectives"] = []
    chapter_path, base_path = fixture_files(tmp_path, chapter)

    assert manual.main(args_for(tmp_path, chapter_path, base_path)) == 1


def test_no_model_call_occurs(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "openai", None)
    chapter_path, base_path = fixture_files(tmp_path)

    assert manual.main(args_for(tmp_path, chapter_path, base_path)) == 0
