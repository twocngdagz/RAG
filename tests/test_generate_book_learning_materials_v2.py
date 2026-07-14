import argparse
import json
import sys
from pathlib import Path

import pytest

import book_learning_materials_v2_generation as v2
import generate_book_learning_materials as book


def make_args(**overrides):
    defaults = {
        "pdf_path": "input/pdfs/pte.pdf",
        "schema_version": "book_learning_materials.v2",
        "chapter_number": [2],
        "chapter_packages_output": "output/pte.v2.targeted.chapter_packages.generated.json",
        "output": "output/pte.v2.targeted.book_learning_materials.generated.json",
        "report": None,
        "overwrite": False,
        "rebuild_artifacts": False,
        "skip_prepare": True,
        "overwrite_index": False,
        "max_chapters": None,
        "chapter_context_chars": 16000,
        "book_synthesis_context_chars": 20000,
        "nvidia_model": "test-model",
        "dry_run": False,
        "prepare_only": False,
        "continue_on_chapter_error": False,
        "resume_chapter_packages": None,
        "resume_missing_chapters": False,
        "model_timeout_seconds": 180,
        "model_max_retries": 0,
        "model_retry_backoff_seconds": 0,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def write_fake_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n% fake test pdf\n")


def clean_chunk(
    node_id: str,
    *,
    chapter_number: int,
    section: str,
    text: str,
) -> dict:
    return {
        "id": node_id,
        "source_pdf": "input/pdfs/pte.pdf",
        "source_type": "pdf",
        "book_id": "pte",
        "book_title": "PTE Sample",
        "chapter": f"LESSON {chapter_number}",
        "chapter_number": chapter_number,
        "section": section,
        "section_page_start": chapter_number,
        "section_source": "toc",
        "section_confidence": "high",
        "section_level": 1,
        "topic": section,
        "content_type": "unknown",
        "page_start": chapter_number,
        "page_end": chapter_number,
        "is_front_matter": False,
        "text": text,
        "metadata": {},
    }


def write_clean_chunks(chunks: list[dict]) -> None:
    path = Path("extracted/pte.section_clean_chunks.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")


def grounded(
    *,
    text: str | None,
    claim_kind: str,
    origin: str,
    source_ids: list[str] | None = None,
    grounded_ids: list[str] | None = None,
    evidence_spans: list[dict] | None = None,
    reason: str | None = None,
) -> dict:
    return {
        "text": text,
        "claim_kind": claim_kind,
        "origin": origin,
        "source_chunk_ids": source_ids or [],
        "grounded_in_source_chunk_ids": grounded_ids or [],
        "evidence_spans": evidence_spans or [],
        "reason": reason,
    }


def valid_v2_chapter(chapter_number: int, node_id: str | list[str]) -> dict:
    node_ids = [node_id] if isinstance(node_id, str) else node_id
    first_node_id = node_ids[0]

    def node(index: int) -> str:
        return node_ids[index % len(node_ids)]

    exact_quote = "test takers hear a short question and give a brief spoken answer"

    def source_grounded(text: str, claim_kind: str, index: int, *, evidence: bool = False) -> dict:
        selected = node(index)
        spans = [{"node_id": selected, "quote": exact_quote}] if evidence else []
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
            text="The lesson explains short spoken answers and evidence checking.",
            claim_kind="source_summary",
            index=0,
        ),
        "learning_objectives": [
            source_grounded(
                text="Identify what the short-answer task asks learners to do.",
                claim_kind="learning_objective",
                index=0,
            ),
            source_grounded(
                text="Explain why a brief spoken answer is expected.",
                claim_kind="learning_objective",
                index=1,
            ),
            source_grounded(
                text="Use local evidence to check whether an answer matches the task.",
                claim_kind="learning_objective",
                index=2,
            ),
        ],
        "key_terms": [
            {
                "term": "Short answer",
                "meaning": source_grounded(
                    text="A short answer is a brief spoken response.",
                    claim_kind="definition",
                    index=0,
                ),
            },
            {
                "term": "Spoken response",
                "meaning": source_grounded(
                    text="A spoken response is an answer given aloud.",
                    claim_kind="definition",
                    index=1,
                ),
            },
            {
                "term": "Evidence check",
                "meaning": source_grounded(
                    text="An evidence check compares the learner answer with local source details.",
                    claim_kind="definition",
                    index=2,
                ),
            },
        ],
        "core_lessons": [
            {
                "title": "Task format",
                "explanation": source_grounded(
                    text="Test takers hear a short question and give a brief spoken answer.",
                    claim_kind="task_format",
                    index=0,
                    evidence=True,
                ),
            },
            {
                "title": "Answer length",
                "explanation": source_grounded(
                    text="The answer should be concise because the source describes a brief response.",
                    claim_kind="factual_explanation",
                    index=1,
                ),
            },
            {
                "title": "Listening focus",
                "explanation": source_grounded(
                    text="Learners need to listen for the main point of the short question.",
                    claim_kind="strategy",
                    index=2,
                ),
            },
            {
                "title": "Checking evidence",
                "explanation": source_grounded(
                    text="The source details help learners decide whether their answer fits the task.",
                    claim_kind="strategy",
                    index=3,
                ),
            },
        ],
        "worked_examples": [
            {
                "title": "Generated example",
                "example": grounded(
                    text="Question: What do people use to tell time? Answer: a clock.",
                    claim_kind="pedagogical_example",
                    origin="pedagogical_generation",
                ),
                "explanation": grounded(
                    text="A concise answer is useful because the source describes a brief spoken answer.",
                    claim_kind="strategy",
                    origin="source_grounded",
                    source_ids=[node(0)],
                ),
            },
            {
                "title": "Generated evidence check",
                "example": grounded(
                    text="Question: What do people drink from? Answer: a cup.",
                    claim_kind="pedagogical_example",
                    origin="pedagogical_generation",
                ),
                "explanation": source_grounded(
                    text="The generated answer is short, matching the source description of a brief spoken answer.",
                    claim_kind="strategy",
                    index=1,
                ),
            },
        ],
        "common_misconceptions": [
            {
                "misconception": source_grounded(
                    text="Learners may think they should give a long answer.",
                    claim_kind="misconception_statement",
                    index=0,
                ),
                "correction": source_grounded(
                    text="The source describes the answer as brief and spoken.",
                    claim_kind="misconception_correction",
                    index=0,
                ),
            }
        ],
        "practice_questions": [
            {
                "question": grounded(
                    text="What is the main action in this task?",
                    claim_kind="practice_question",
                    origin="pedagogical_generation",
                ),
                "answer": grounded(
                    text="The learner hears a short question and gives a brief spoken answer.",
                    claim_kind="practice_answer",
                    origin="source_grounded",
                    source_ids=[node(0)],
                ),
            },
            {
                "question": grounded(
                    text="Write one brief answer to a simple spoken question.",
                    claim_kind="practice_question",
                    origin="pedagogical_generation",
                ),
                "answer": grounded(
                    text="A brief spoken answer should be short and direct.",
                    claim_kind="practice_answer",
                    origin="pedagogical_generation",
                ),
            },
            {
                "question": grounded(
                    text="Which source detail tells you the answer should not be long?",
                    claim_kind="practice_question",
                    origin="pedagogical_generation",
                ),
                "answer": source_grounded(
                    text="The source describes the response as brief.",
                    claim_kind="practice_answer",
                    index=1,
                ),
            },
        ],
        "review_checklist": [
            grounded(
                text="I can identify the evidence for the task format.",
                claim_kind="self_assessment",
                origin="pedagogical_generation",
            ),
            grounded(
                text="I can explain why the answer should be brief.",
                claim_kind="self_assessment",
                origin="pedagogical_generation",
            ),
            grounded(
                text="I can create a short practice answer.",
                claim_kind="self_assessment",
                origin="pedagogical_generation",
            ),
            grounded(
                text="I can check my answer against local evidence.",
                claim_kind="self_assessment",
                origin="pedagogical_generation",
            ),
        ],
    }


def source_text(label: str) -> str:
    return (
        f"{label}. This source says that test takers hear a short question and "
        "give a brief spoken answer. Learners review the main idea and check "
        "their answer against evidence."
    )


def setup_three_chapters(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_clean_chunks(
        [
            clean_chunk(
                "pte_chunk_001",
                chapter_number=1,
                section="Unselected",
                text=source_text("UNSELECTED CHAPTER TEXT"),
            ),
            clean_chunk(
                "pte_chunk_002",
                chapter_number=2,
                section="Selected Two",
                text=source_text("SELECTED TWO TEXT"),
            ),
            clean_chunk(
                "pte_chunk_003",
                chapter_number=3,
                section="Selected Three",
                text=source_text("SELECTED THREE TEXT"),
            ),
        ]
    )


def response_for_prompt(prompt: str) -> str:
    if "Chapter number: 2" in prompt:
        return json.dumps(valid_v2_chapter(2, "pte_chunk_002"))
    if "Chapter number: 3" in prompt:
        return json.dumps(valid_v2_chapter(3, "pte_chunk_003"))
    raise AssertionError(f"Unexpected model prompt:\n{prompt[:500]}")


def prompt_chapter_with_chunks() -> dict:
    return {
        "chapter_number": 2,
        "chapter": "LESSON 2",
        "chunks": [
            clean_chunk(
                f"pte_chunk_00{index}",
                chapter_number=2,
                section=f"Section {index}",
                text=f"FULL CHUNK {index} TEXT test takers hear a short question and give a brief spoken answer.",
            )
            for index in range(1, 5)
        ],
    }


def test_parse_args_accepts_schema_versions_and_repeatable_chapters(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_book_learning_materials.py",
            "input/pdfs/pte.pdf",
            "--schema-version",
            "book_learning_materials.v2",
            "--chapter-number",
            "2",
            "--chapter-number",
            "11",
            "--chapter-packages-output",
            "output/checkpoint.json",
        ],
    )
    args = book.parse_args()

    assert args.schema_version == "book_learning_materials.v2"
    assert args.chapter_number == [2, 11]
    assert args.chapter_packages_output == "output/checkpoint.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_book_learning_materials.py", "input/pdfs/pte.pdf"],
    )
    assert book.parse_args().schema_version == "book_learning_materials.v1"


def test_unknown_schema_version_is_rejected(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_book_learning_materials.py",
            "input/pdfs/pte.pdf",
            "--schema-version",
            "book_learning_materials.v9",
        ],
    )
    with pytest.raises(SystemExit):
        book.parse_args()


def test_v2_requires_selection_and_v1_does_not(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))

    with pytest.raises(book.BookLearningMaterialsError, match="Full-book v2 generation"):
        book.generate_book_learning_materials(
            make_args(chapter_number=[], dry_run=True),
            complete_fn=lambda _prompt: pytest.fail("model should not be called"),
        )

    result = book.generate_book_learning_materials(
        argparse.Namespace(
            **{
                **make_args().__dict__,
                "schema_version": "book_learning_materials.v1",
                "chapter_number": [],
                "dry_run": True,
            }
        ),
        complete_fn=lambda _prompt: pytest.fail("model should not be called"),
    )
    assert result is None


def test_duplicate_and_unknown_chapter_numbers_are_rejected(tmp_path, monkeypatch):
    setup_three_chapters(tmp_path, monkeypatch)

    with pytest.raises(book.BookLearningMaterialsError, match="Duplicate"):
        book.generate_book_learning_materials(
            make_args(chapter_number=[2, 2], dry_run=True),
            complete_fn=lambda _prompt: pytest.fail("model should not be called"),
        )

    with pytest.raises(book.BookLearningMaterialsError, match="Unknown selected chapter"):
        book.generate_book_learning_materials(
            make_args(chapter_number=[99], dry_run=True),
            complete_fn=lambda _prompt: pytest.fail("model should not be called"),
        )


def test_v2_complete_chapter_prompt_requests_substantive_chapter_object():
    chapter = prompt_chapter_with_chunks()
    context_json, _chunks, allowed_ids = v2.chapter_context_blocks(chapter)

    prompt = v2.build_v2_chapter_prompt(
        chapter=chapter,
        context_json=context_json,
        allowed_ids=allowed_ids,
        model="test-model",
    )

    assert "complete learner-facing chapter object" in prompt
    assert "This is not a signal response" in prompt
    assert "chapter_number, chapter_title, source_chunk_ids" in prompt
    assert "at least 3" in prompt
    assert "at least 4" in prompt
    assert "generic source-reference filler" in prompt
    assert "High-risk kinds" in prompt
    assert "Do not infer missing IPA, scoring, timing, task modality, or grammar details" in prompt
    assert '"source_chunk_id": "pte_chunk_001"' in prompt
    assert '"source_chunk_id": "pte_chunk_004"' in prompt
    assert "FULL CHUNK 1 TEXT" in prompt
    assert "FULL CHUNK 4 TEXT" in prompt


def test_v2_prompt_version_is_v2():
    assert v2.BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION == (
        "book_learning_materials_v2_chapter.v2"
    )


def substantive_codes(chapter: dict, allowed_ids: list[str]) -> list[str]:
    return [
        error["code"]
        for error in v2.validate_substantive_v2_chapter(
            candidate=chapter,
            allowed_ids=allowed_ids,
        )
    ]


def test_valid_substantive_chapter_and_exact_minimum_counts_pass():
    chapter = valid_v2_chapter(2, ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"])

    assert substantive_codes(
        chapter,
        ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"],
    ) == []
    assert len(chapter["learning_objectives"]) == 3


@pytest.mark.parametrize(
    ("field", "limit", "code"),
    [
        ("learning_objectives", 2, "TOO_FEW_LEARNING_OBJECTIVES"),
        ("key_terms", 2, "TOO_FEW_KEY_TERMS"),
        ("core_lessons", 3, "TOO_FEW_CORE_LESSONS"),
        ("worked_examples", 1, "TOO_FEW_WORKED_EXAMPLES"),
        ("practice_questions", 2, "TOO_FEW_PRACTICE_QUESTIONS"),
        ("review_checklist", 3, "TOO_FEW_REVIEW_CHECKLIST_ITEMS"),
    ],
)
def test_substantive_minimums_are_enforced(field, limit, code):
    chapter = valid_v2_chapter(2, "pte_chunk_001")
    chapter[field] = chapter[field][:limit]

    assert code in substantive_codes(chapter, ["pte_chunk_001"])


def test_generic_placeholder_text_is_rejected_with_json_path():
    chapter = valid_v2_chapter(2, "pte_chunk_001")
    chapter["chapter_summary"]["text"] = "Review the cited source excerpt."

    errors = v2.validate_substantive_v2_chapter(
        candidate=chapter,
        allowed_ids=["pte_chunk_001"],
    )

    assert {
        "code": "GENERIC_PLACEHOLDER_TEXT",
        "json_path": "$.learning_materials.chapters[0].chapter_summary.text",
        "message": "Learner-facing text is generic source-reference filler.",
    } in errors


def test_substantive_sentence_containing_source_still_passes_placeholder_check():
    chapter = valid_v2_chapter(2, "pte_chunk_001")
    chapter["chapter_summary"]["text"] = (
        "The source explains that learners answer a short spoken question with a brief response."
    )

    codes = substantive_codes(chapter, ["pte_chunk_001"])

    assert "GENERIC_PLACEHOLDER_TEXT" not in codes


def test_source_use_floor_requires_four_distinct_source_grounded_ids_when_available():
    chapter = valid_v2_chapter(2, ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"])
    assert substantive_codes(
        chapter,
        ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"],
    ) == []

    weak = valid_v2_chapter(2, ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"])
    for _path, grounded_object in v2.iter_grounded_content(weak, "$.learning_materials.chapters[0]"):
        if grounded_object.get("origin") == "source_grounded":
            grounded_object["source_chunk_ids"] = ["pte_chunk_001"]
    assert "INSUFFICIENT_SOURCE_CHUNK_COVERAGE" in substantive_codes(
        weak,
        ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"],
    )


def test_source_use_floor_requires_all_available_ids_when_fewer_than_four():
    chapter = valid_v2_chapter(2, ["pte_chunk_001", "pte_chunk_002"])

    assert substantive_codes(chapter, ["pte_chunk_001", "pte_chunk_002"]) == []


def test_pedagogical_grounded_ids_do_not_count_for_source_use_floor():
    chapter = valid_v2_chapter(2, ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"])
    for _path, grounded_object in v2.iter_grounded_content(chapter, "$.learning_materials.chapters[0]"):
        if grounded_object.get("origin") == "source_grounded":
            grounded_object["source_chunk_ids"] = ["pte_chunk_001"]
        elif grounded_object.get("origin") == "pedagogical_generation":
            grounded_object["grounded_in_source_chunk_ids"] = [
                "pte_chunk_002",
                "pte_chunk_003",
                "pte_chunk_004",
            ]

    assert "INSUFFICIENT_SOURCE_CHUNK_COVERAGE" in substantive_codes(
        chapter,
        ["pte_chunk_001", "pte_chunk_002", "pte_chunk_003", "pte_chunk_004"],
    )


def test_v2_targeted_generation_selects_only_requested_chapters_and_skips_synthesis(
    tmp_path,
    monkeypatch,
):
    setup_three_chapters(tmp_path, monkeypatch)
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        assert "UNSELECTED CHAPTER TEXT" not in prompt
        assert "`source_grounded`" in prompt
        assert "`pedagogical_generation`" in prompt
        assert "`insufficient_source_evidence`" in prompt
        assert "High-risk kinds" in prompt
        assert "Damaged pronunciation notation" in prompt
        assert "Task modality" in prompt
        assert "Zero-score/scoring/timing" in prompt
        return response_for_prompt(prompt)

    result = book.generate_book_learning_materials(
        make_args(chapter_number=[3, 2], overwrite=True),
        complete_fn=complete,
    )

    assert result is not None
    assert len(prompts) == 2
    assert [chapter["chapter_number"] for chapter in result["learning_materials"]["chapters"]] == [2, 3]
    assert set(result["learning_materials"].keys()) == {"chapters"}
    assert result["schema_version"] == "book_learning_materials.v2"
    assert result["generation"]["pipeline_version"] == "book_learning_materials.v2"
    assert result["generation"]["prompt_version"] == "book_learning_materials_v2_chapter.v2"
    assert result["generation"]["book_synthesis_performed"] is False
    assert result["audit"]["contract_status"] == "PASS"
    assert Path("output/pte.v2.targeted.book_learning_materials.contract.audit.json").exists()
    checkpoint = json.loads(
        Path("output/pte.v2.targeted.chapter_packages.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["status"] == "COMPLETE"
    assert checkpoint["selected_chapter_numbers"] == [2, 3]
    assert checkpoint["completed_chapter_numbers"] == [2, 3]
    assert checkpoint["model_call_count"] == 2
    assert checkpoint["repair_call_count"] == 0


def test_invalid_chapter_is_not_checkpointed_until_repair_passes(tmp_path, monkeypatch):
    setup_three_chapters(tmp_path, monkeypatch)
    invalid = json.dumps(
        {
            "chapter_number": 2,
            "chapter_title": "Legacy",
            "source_chunk_ids": ["pte_chunk_002"],
            "chapter_summary": "legacy string should fail",
            "learning_objectives": ["legacy objective"],
            "key_terms": [],
            "core_lessons": [],
            "worked_examples": [],
            "common_misconceptions": [],
            "practice_questions": [],
            "review_checklist": [],
        }
    )
    calls = []

    def complete(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return invalid
        assert "Validation errors to fix" in prompt
        assert "INVALID_GROUNDED_CONTENT_SHAPE" in prompt
        assert "UNSELECTED CHAPTER TEXT" not in prompt
        return json.dumps(valid_v2_chapter(2, "pte_chunk_002"))

    result = book.generate_book_learning_materials(
        make_args(chapter_number=[2], overwrite=True),
        complete_fn=complete,
    )

    assert result is not None
    checkpoint = json.loads(
        Path("output/pte.v2.targeted.chapter_packages.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["completed_chapter_numbers"] == [2]
    assert checkpoint["model_call_count"] == 2
    assert checkpoint["repair_call_count"] == 1
    assert Path("output/pte.v2.targeted.invalid/chapter_02.initial.raw.txt").exists()
    assert Path("output/pte.v2.targeted.invalid/chapter_02.initial.contract_errors.json").exists()


def test_substantive_validation_failure_triggers_one_repair_with_errors(tmp_path, monkeypatch):
    setup_three_chapters(tmp_path, monkeypatch)
    invalid_chapter = valid_v2_chapter(2, "pte_chunk_002")
    invalid_chapter["learning_objectives"] = invalid_chapter["learning_objectives"][:2]
    calls = []

    def complete(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return json.dumps(invalid_chapter)
        assert "Validation errors to fix" in prompt
        assert "TOO_FEW_LEARNING_OBJECTIVES" in prompt
        assert "Invalid candidate" in prompt
        assert "Same selected source excerpts" in prompt
        return json.dumps(valid_v2_chapter(2, "pte_chunk_002"))

    result = book.generate_book_learning_materials(
        make_args(chapter_number=[2], overwrite=True),
        complete_fn=complete,
    )

    assert result is not None
    assert len(calls) == 2
    checkpoint = json.loads(
        Path("output/pte.v2.targeted.chapter_packages.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["completed_chapter_numbers"] == [2]
    assert checkpoint["model_call_count"] == 2
    assert checkpoint["repair_call_count"] == 1
    errors = json.loads(
        Path("output/pte.v2.targeted.invalid/chapter_02.initial.contract_errors.json").read_text(
            encoding="utf-8"
        )
    )
    assert any(error["code"] == "TOO_FEW_LEARNING_OBJECTIVES" for error in errors)


def test_failed_repair_preserves_completed_checkpoint_and_exits_nonzero(tmp_path, monkeypatch):
    setup_three_chapters(tmp_path, monkeypatch)
    invalid = json.dumps({"chapter_number": 3, "chapter_title": "Bad"})
    calls = []

    def complete(prompt):
        calls.append(prompt)
        if "Chapter number: 2" in prompt:
            return json.dumps(valid_v2_chapter(2, "pte_chunk_002"))
        return invalid

    with pytest.raises(book.BookLearningMaterialsError, match="Resume with"):
        book.generate_book_learning_materials(
            make_args(chapter_number=[2, 3], overwrite=True),
            complete_fn=complete,
        )

    checkpoint = json.loads(
        Path("output/pte.v2.targeted.chapter_packages.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["status"] == "IN_PROGRESS"
    assert checkpoint["completed_chapter_numbers"] == [2]
    assert checkpoint["failed_chapters"][0]["chapter_number"] == 3
    assert not Path("output/pte.v2.targeted.book_learning_materials.generated.json").exists()


def test_resume_skips_completed_and_rejects_incompatible_checkpoint(tmp_path, monkeypatch):
    setup_three_chapters(tmp_path, monkeypatch)
    book.generate_book_learning_materials(
        make_args(chapter_number=[2], overwrite=True),
        complete_fn=lambda prompt: json.dumps(valid_v2_chapter(2, "pte_chunk_002")),
    )
    checkpoint_path = Path("output/pte.v2.targeted.chapter_packages.generated.json")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["status"] = "IN_PROGRESS"
    checkpoint["selected_chapter_numbers"] = [2, 3]
    checkpoint["selected_chapter_count"] = 2
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")
    prompts = []

    result = book.generate_book_learning_materials(
        make_args(
            chapter_number=[2, 3],
            resume_chapter_packages=str(checkpoint_path),
            resume_missing_chapters=True,
            overwrite=True,
        ),
        complete_fn=lambda prompt: prompts.append(prompt) or response_for_prompt(prompt),
    )

    assert result is not None
    assert len(prompts) == 1
    assert "Chapter number: 3" in prompts[0]
    final_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert final_checkpoint["completed_chapter_numbers"] == [2, 3]

    final_checkpoint["prompt_version"] = "old"
    checkpoint_path.write_text(json.dumps(final_checkpoint, indent=2), encoding="utf-8")
    with pytest.raises(book.BookLearningMaterialsError, match="prompt_version"):
        book.generate_book_learning_materials(
            make_args(
                chapter_number=[2, 3],
                resume_chapter_packages=str(checkpoint_path),
                resume_missing_chapters=True,
                overwrite=True,
            ),
            complete_fn=lambda _prompt: pytest.fail("completed chapters should not call model"),
        )


def test_final_output_is_not_written_when_contract_validation_fails(
    tmp_path,
    monkeypatch,
):
    setup_three_chapters(tmp_path, monkeypatch)

    def fail_final_validation(**_kwargs):
        return {
            "status": "FAIL",
            "summary": {
                "grounded_content_count": 0,
                "source_grounded_count": 0,
                "pedagogical_generation_count": 0,
                "insufficient_source_evidence_count": 0,
                "high_risk_claim_count": 0,
                "high_risk_verified_span_count": 0,
                "verified_evidence_span_count": 0,
                "unique_referenced_source_chunk_count": 0,
                "invalid_claim_count": 1,
                "claims_by_kind": {},
                "claims_by_origin": {},
                "errors_by_code": {"FORCED": 1},
            },
            "errors": [{"code": "FORCED", "json_path": "$", "message": "forced"}],
            "warnings": [],
            "input": {},
        }

    calls = {"count": 0}
    original = v2.validate_v2_book_dict

    def validate_spy(**kwargs):
        calls["count"] += 1
        if calls["count"] > 1:
            return fail_final_validation(**kwargs)
        return original(**kwargs)

    monkeypatch.setattr(v2, "validate_v2_book_dict", validate_spy)
    with pytest.raises(book.BookLearningMaterialsError, match="Final targeted v2 book failed"):
        book.generate_book_learning_materials(
            make_args(chapter_number=[2], overwrite=True),
            complete_fn=lambda prompt: json.dumps(valid_v2_chapter(2, "pte_chunk_002")),
        )

    assert Path("output/pte.v2.targeted.book_learning_materials.contract.audit.json").exists()
    assert not Path("output/pte.v2.targeted.book_learning_materials.generated.json").exists()


def test_dry_run_and_overwrite_protection_write_no_files(tmp_path, monkeypatch):
    setup_three_chapters(tmp_path, monkeypatch)
    result = book.generate_book_learning_materials(
        make_args(chapter_number=[2], dry_run=True),
        complete_fn=lambda _prompt: pytest.fail("model should not be called"),
    )
    assert result is None
    assert not Path("output/pte.v2.targeted.chapter_packages.generated.json").exists()

    Path("output").mkdir(exist_ok=True)
    output = Path("output/pte.v2.targeted.book_learning_materials.generated.json")
    checkpoint = Path("output/pte.v2.targeted.chapter_packages.generated.json")
    audit = Path("output/pte.v2.targeted.book_learning_materials.contract.audit.json")
    report = Path("output/pte.v2.targeted.book_learning_materials.contract.audit.txt")
    for path in [output, checkpoint, audit, report]:
        path.write_text("existing", encoding="utf-8")

    with pytest.raises(book.BookLearningMaterialsError, match="already exists"):
        book.generate_book_learning_materials(
            make_args(chapter_number=[2], overwrite=False),
            complete_fn=lambda _prompt: pytest.fail("model should not be called"),
        )

    assert output.read_text(encoding="utf-8") == "existing"
    assert checkpoint.read_text(encoding="utf-8") == "existing"
    assert audit.read_text(encoding="utf-8") == "existing"
    assert report.read_text(encoding="utf-8") == "existing"
