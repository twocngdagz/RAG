import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

import generate_book_learning_materials as book


def make_args(**overrides):
    defaults = {
        "pdf_path": "input/pdfs/pte.pdf",
        "output": None,
        "report": None,
        "overwrite": False,
        "rebuild_artifacts": False,
        "skip_prepare": False,
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
        "model_max_retries": 2,
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
    text: str = "This is cleaned chapter content for learning.",
) -> dict:
    return {
        "id": node_id,
        "source_pdf": "input/pdfs/pte.pdf",
        "source_type": "pdf",
        "book_id": "pte",
        "book_title": "PTE Sample",
        "chapter": f"CHAPTER {chapter_number}",
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


def chapter_response(node_id: str = "pte_chunk_001") -> str:
    return json.dumps(
        {
            "chapter_title": "Chapter One",
            "estimated_study_time_minutes": 30,
            "chapter_summary": "A short chapter summary.",
            "learning_objectives": ["Understand the main idea."],
            "key_terms": [
                {
                    "term": "Main idea",
                    "meaning": "The central concept.",
                    "source_chunk_ids": [node_id],
                }
            ],
            "core_lessons": [
                {
                    "title": "Core lesson",
                    "explanation": "A grounded explanation.",
                    "source_chunk_ids": [node_id],
                }
            ],
            "worked_examples": [
                {
                    "title": "Example",
                    "example": "A small example.",
                    "explanation": "The explanation.",
                    "source_chunk_ids": [node_id],
                }
            ],
            "common_misconceptions": [
                {
                    "misconception": "A misconception.",
                    "correction": "A correction.",
                    "source_chunk_ids": [node_id],
                }
            ],
            "practice_questions": [
                {
                    "question": "A question?",
                    "answer": "An answer.",
                    "source_chunk_ids": [node_id],
                }
            ],
            "review_checklist": ["Review the main idea."],
            "source_chunk_ids": [node_id],
        }
    )


def synthesis_response(node_id: str = "pte_chunk_001") -> str:
    return json.dumps(
        {
            "book_overview": "A compact overview.",
            "who_this_is_for": ["Learners"],
            "how_to_use_this_book": ["Study one chapter at a time."],
            "study_plan": [
                {
                    "week": 1,
                    "focus": "Chapter 1",
                    "chapters": [1],
                    "activities": ["Read and review."],
                }
            ],
            "global_key_terms": [
                {
                    "term": "Main idea",
                    "meaning": "The central concept.",
                    "chapter_numbers": [1],
                    "source_chunk_ids": [node_id],
                }
            ],
            "final_review": {
                "summary": "Review the book.",
                "questions": ["What did you learn?"],
            },
        }
    )


def write_fake_clean_chunks(chunks: list[dict]) -> None:
    clean_path = Path("extracted/pte.section_clean_chunks.json")
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.write_text(json.dumps(chunks), encoding="utf-8")


def write_resume_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_chunk = book.source_chunk_record(
        clean_chunk("pte_chunk_001", chapter_number=1, section="First")
    )
    package = book.validate_chapter_package(
        json.loads(chapter_response("pte_chunk_001")),
        chapter_number=1,
        chapter_label="CHAPTER 1",
        allowed_ids=["pte_chunk_001"],
    )
    path.write_text(
        json.dumps(
            {
                "book": {
                    "slug": "pte",
                    "source_pdf": "input/pdfs/pte.pdf",
                    "title": "PTE Sample",
                    "detected_chapter_count": 1,
                    "detected_section_count": 1,
                },
                "generation": {
                    "generated_at": "2026-01-01T00:00:00+00:00",
                    "model": "test-model",
                    "pipeline_version": "book_learning_materials.v1",
                    "clean_index_id": "section_clean_pdf_pte",
                    "clean_storage_dir": "storage/section_clean_pdf_pte",
                    "clean_chunks_path": "extracted/pte.section_clean_chunks.json",
                    "structure_resolution_path": "extracted/pte.structure_resolution.json",
                    "chapter_context_chars": 16000,
                    "book_synthesis_context_chars": 20000,
                },
                "chapter_packages": [package],
                "source_chunks": [source_chunk],
            }
        ),
        encoding="utf-8",
    )


def test_slug_and_path_derivation_from_pdf_path():
    args = make_args(pdf_path="input/pdfs/pte.pdf")
    plan = book.build_plan(args)

    assert plan["slug"] == "pte"
    assert plan["paths"]["raw_chunks"] == "extracted/pte.chunks.json"
    assert plan["paths"]["clean_chunks"] == "extracted/pte.section_clean_chunks.json"
    assert plan["clean_index_id"] == "section_clean_pdf_pte"
    assert str(plan["clean_storage_dir"]) == "storage/section_clean_pdf_pte"
    assert str(plan["output_json"]) == "output/pte.book_learning_materials.generated.json"


def test_model_timeout_options_are_parsed(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_book_learning_materials.py",
            "input/pdfs/pte.pdf",
            "--model-timeout-seconds",
            "12",
            "--model-max-retries",
            "3",
            "--model-retry-backoff-seconds",
            "0.5",
        ],
    )

    args = book.parse_args()

    assert args.model_timeout_seconds == 12
    assert args.model_max_retries == 3
    assert args.model_retry_backoff_seconds == 0.5


def test_model_retries_stop_after_configured_limit():
    calls = []

    def fail(_prompt):
        calls.append("call")
        raise TimeoutError("slow")

    with pytest.raises(book.ModelCallError, match="failed after 3 attempt"):
        book.complete_model_with_retries(
            prompt="hello",
            args=make_args(model_max_retries=2, model_retry_backoff_seconds=0),
            label="test",
            complete_fn=fail,
        )

    assert len(calls) == 3


def test_dry_run_does_not_call_subprocess_or_nvidia(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))

    def fail_subprocess(*_args, **_kwargs):
        raise AssertionError("subprocess should not be called")

    def fail_complete(_prompt):
        raise AssertionError("NVIDIA should not be called")

    result = book.generate_book_learning_materials(
        make_args(dry_run=True),
        complete_fn=fail_complete,
        run_subprocess=fail_subprocess,
    )

    assert result is None


def test_prepare_only_does_not_call_nvidia(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    commands = []

    def fake_subprocess(command, check=False):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    def fail_complete(_prompt):
        raise AssertionError("NVIDIA should not be called")

    result = book.generate_book_learning_materials(
        make_args(prepare_only=True),
        complete_fn=fail_complete,
        run_subprocess=fake_subprocess,
    )

    assert result is None
    assert commands
    assert any("prepare_clean_section_index.py" in command for command in commands)


def test_output_overwrite_protection(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    output = Path("output/existing.json")
    output.parent.mkdir(parents=True)
    output.write_text("already here", encoding="utf-8")

    with pytest.raises(book.BookLearningMaterialsError, match="Output file already exists"):
        book.generate_book_learning_materials(
            make_args(output=str(output)),
            complete_fn=lambda _prompt: pytest.fail("NVIDIA should not be called"),
            run_subprocess=lambda *_args, **_kwargs: pytest.fail("subprocess should not be called"),
        )


def test_validation_catches_invalid_source_references():
    package = json.loads(chapter_response("unknown_chunk"))

    with pytest.raises(book.BookLearningMaterialsError, match="unknown source chunk IDs"):
        book.validate_chapter_package(
            package,
            chapter_number=1,
            chapter_label="CHAPTER 1",
            allowed_ids=["pte_chunk_001"],
        )


def test_chapter_grouping_from_fake_clean_chunks():
    chunks = [
        clean_chunk("pte_chunk_002", chapter_number=2, section="Second"),
        {**clean_chunk("pte_chunk_000", chapter_number=0, section="Front"), "is_front_matter": True},
        clean_chunk("pte_chunk_001", chapter_number=1, section="First"),
    ]

    grouped = book.group_chunks_by_chapter(chunks)

    assert [chapter["chapter_number"] for chapter in grouped] == [1, 2]
    assert grouped[0]["chunks"][0]["id"] == "pte_chunk_001"


def test_max_chapters_limits_generated_chapters_and_writes_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    clean_path = Path("extracted/pte.section_clean_chunks.json")
    clean_path.parent.mkdir(parents=True)
    clean_path.write_text(
        json.dumps(
            [
                clean_chunk("pte_chunk_001", chapter_number=1, section="First"),
                clean_chunk("pte_chunk_002", chapter_number=2, section="Second"),
            ]
        ),
        encoding="utf-8",
    )
    responses = [chapter_response("pte_chunk_001"), synthesis_response("pte_chunk_001")]

    result = book.generate_book_learning_materials(
        make_args(
            skip_prepare=True,
            overwrite=True,
            max_chapters=1,
            output="output/book.json",
        ),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    output_data = json.loads(Path("output/book.json").read_text(encoding="utf-8"))
    assert result is not None
    assert len(output_data["learning_materials"]["chapters"]) == 1
    assert output_data["audit"]["status"] == "PASS_WITH_WARNINGS"
    assert output_data["audit"]["partial_generation"] is True
    assert output_data["audit"]["invalid_source_reference_count"] == 0
    assert output_data["source_chunks"][0]["node_id"] == "pte_chunk_001"
    assert Path("output/book.txt").exists()


def test_checkpoint_is_written_after_each_successful_chapter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks(
        [
            clean_chunk("pte_chunk_001", chapter_number=1, section="First"),
            clean_chunk("pte_chunk_002", chapter_number=2, section="Second"),
        ]
    )
    original_writer = book.write_chapter_checkpoint
    checkpoint_counts = []

    def spy_writer(**kwargs):
        checkpoint_counts.append(
            (
                kwargs["status"],
                len(kwargs["chapter_packages"]),
                kwargs["chapter_packages"][-1]["chapter_number"]
                if kwargs["chapter_packages"]
                else None,
            )
        )
        original_writer(**kwargs)

    monkeypatch.setattr(book, "write_chapter_checkpoint", spy_writer)
    responses = [
        chapter_response("pte_chunk_001"),
        chapter_response("pte_chunk_002"),
        synthesis_response("pte_chunk_001"),
    ]

    book.generate_book_learning_materials(
        make_args(skip_prepare=True, overwrite=True),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    assert checkpoint_counts[:2] == [("IN_PROGRESS", 1, 1), ("IN_PROGRESS", 2, 2)]
    assert checkpoint_counts[-1] == ("COMPLETE", 2, 2)
    checkpoint = json.loads(
        Path("output/pte.chapter_packages.generated.json").read_text(encoding="utf-8")
    )["checkpoint"]
    assert checkpoint["status"] == "COMPLETE"
    assert checkpoint["generated_chapter_count"] == 2


def test_timeout_failure_writes_checkpoint_before_exiting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])

    with pytest.raises(book.BookLearningMaterialsError, match="Checkpoint saved"):
        book.generate_book_learning_materials(
            make_args(
                skip_prepare=True,
                overwrite=True,
                model_max_retries=1,
                model_retry_backoff_seconds=0,
            ),
            complete_fn=lambda _prompt: (_ for _ in ()).throw(TimeoutError("slow")),
        )

    data = json.loads(
        Path("output/pte.chapter_packages.generated.json").read_text(encoding="utf-8")
    )
    assert data["checkpoint"]["status"] == "IN_PROGRESS"
    assert data["checkpoint"]["generated_chapter_count"] == 0
    assert data["checkpoint"]["errors"][0]["reason"] == "model_call_timeout"


def test_final_merge_includes_source_chunks_and_pass_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    responses = [chapter_response("pte_chunk_001"), synthesis_response("pte_chunk_001")]

    result = book.generate_book_learning_materials(
        make_args(skip_prepare=True, overwrite=True),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    assert result is not None
    assert result["book"]["slug"] == "pte"
    assert result["book"]["title"] == "PTE Sample"
    assert result["source_chunks"]
    assert result["audit"]["status"] == "PASS"
    assert result["audit"]["failures"] == []


def test_chapter_packages_are_saved_before_book_synthesis_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    responses = [
        chapter_response("pte_chunk_001"),
        synthesis_response("unknown_chunk"),
    ]

    with pytest.raises(book.BookLearningMaterialsError, match="unknown source chunk IDs"):
        book.generate_book_learning_materials(
            make_args(skip_prepare=True, overwrite=True),
            complete_fn=lambda _prompt: responses.pop(0),
        )

    saved = Path("output/pte.chapter_packages.generated.json")
    assert saved.exists()
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["chapter_packages"][0]["chapter_title"] == "Chapter One"
    assert data["source_chunks"][0]["node_id"] == "pte_chunk_001"


def test_resume_from_chapter_packages_skips_chapter_generation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    resume_path = Path("output/pte.chapter_packages.generated.json")
    write_resume_file(resume_path)
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        assert "You are creating student-friendly learning materials from one book chapter" not in prompt
        return synthesis_response("pte_chunk_001")

    result = book.generate_book_learning_materials(
        make_args(
            resume_chapter_packages=str(resume_path),
            output="output/final.json",
            overwrite=True,
        ),
        complete_fn=complete,
        run_subprocess=lambda *_args, **_kwargs: pytest.fail("preparation should be skipped"),
    )

    assert result is not None
    assert len(prompts) == 1
    assert result["generation"]["resumed_from_chapter_packages"] == str(resume_path)
    assert result["audit"]["invalid_source_reference_count"] == 0


def test_partial_checkpoint_can_be_loaded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = Path("output/pte.chapter_packages.generated.json")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "book": {"slug": "pte", "detected_chapter_count": 2},
                "generation": {"model": "test-model"},
                "chapter_packages": [],
                "source_chunks": [],
                "checkpoint": {
                    "status": "IN_PROGRESS",
                    "generated_chapter_count": 0,
                    "target_chapter_count": 2,
                    "last_completed_chapter_number": None,
                    "errors": [{"chapter_number": 1, "reason": "model_call_timeout"}],
                },
            }
        ),
        encoding="utf-8",
    )

    data = book.load_chapter_packages_file(path)

    assert data["checkpoint"]["status"] == "IN_PROGRESS"
    assert data["chapter_packages"] == []


def test_resume_missing_chapters_generates_only_missing_chapters(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks(
        [
            clean_chunk("pte_chunk_001", chapter_number=1, section="First"),
            clean_chunk("pte_chunk_002", chapter_number=2, section="Second"),
        ]
    )
    resume_path = Path("output/pte.chapter_packages.generated.json")
    write_resume_file(resume_path)
    prompts = []

    def complete(prompt):
        prompts.append(prompt)
        if "You are creating student-friendly learning materials" in prompt:
            assert "Chapter number: 1" not in prompt
            assert "Chapter number: 2" in prompt
            return chapter_response("pte_chunk_002")
        return synthesis_response("pte_chunk_001")

    result = book.generate_book_learning_materials(
        make_args(
            skip_prepare=True,
            overwrite=True,
            resume_chapter_packages=str(resume_path),
            resume_missing_chapters=True,
        ),
        complete_fn=complete,
    )

    chapter_prompts = [
        prompt
        for prompt in prompts
        if "You are creating student-friendly learning materials" in prompt
    ]
    assert len(chapter_prompts) == 1
    assert [chapter["chapter_number"] for chapter in result["learning_materials"]["chapters"]] == [1, 2]
    checkpoint = json.loads(resume_path.read_text(encoding="utf-8"))["checkpoint"]
    assert checkpoint["status"] == "COMPLETE"
    assert checkpoint["generated_chapter_count"] == 2


def test_malformed_book_synthesis_saves_raw_response_and_repairs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    malformed = '{"book_overview": "unterminated'
    responses = [
        chapter_response("pte_chunk_001"),
        malformed,
        synthesis_response("pte_chunk_001"),
    ]

    result = book.generate_book_learning_materials(
        make_args(skip_prepare=True, overwrite=True),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    raw_path = Path("output/pte.book_synthesis.raw_response.txt")
    assert raw_path.exists()
    assert raw_path.read_text(encoding="utf-8") == malformed
    assert "book_synthesis_model_json_repaired" in result["audit"]["warnings"]
    assert result["audit"]["invalid_source_reference_count"] == 0


def test_continue_on_chapter_error_records_error_and_continues(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks(
        [
            clean_chunk("pte_chunk_001", chapter_number=1, section="First"),
            clean_chunk("pte_chunk_002", chapter_number=2, section="Second"),
        ]
    )
    calls = {"chapter": 0}

    def complete(prompt):
        if "You are creating student-friendly learning materials" in prompt:
            calls["chapter"] += 1
            if calls["chapter"] == 1:
                raise TimeoutError("slow")
            return chapter_response("pte_chunk_002")
        return synthesis_response("pte_chunk_002")

    result = book.generate_book_learning_materials(
        make_args(
            skip_prepare=True,
            overwrite=True,
            continue_on_chapter_error=True,
            model_max_retries=0,
        ),
        complete_fn=complete,
    )

    checkpoint = json.loads(
        Path("output/pte.chapter_packages.generated.json").read_text(encoding="utf-8")
    )["checkpoint"]
    assert checkpoint["errors"][0]["reason"] == "model_call_timeout"
    assert "chapter_generation_errors_present" in result["audit"]["warnings"]
    assert len(result["learning_materials"]["chapters"]) == 2


def test_invalid_chapter_json_saves_raw_response(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    malformed = '{"chapter_title": "broken'
    responses = [
        malformed,
        chapter_response("pte_chunk_001"),
        synthesis_response("pte_chunk_001"),
    ]

    result = book.generate_book_learning_materials(
        make_args(
            skip_prepare=True,
            overwrite=True,
            model_max_retries=1,
            model_retry_backoff_seconds=0,
        ),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    raw_path = Path("output/pte.chapter_1.raw_response.txt")
    assert raw_path.exists()
    assert raw_path.read_text(encoding="utf-8") == malformed
    assert result["audit"]["invalid_source_reference_count"] == 0


def test_repair_failure_triggers_deterministic_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    malformed = '{"book_overview": "unterminated'
    responses = [chapter_response("pte_chunk_001"), malformed, malformed]

    result = book.generate_book_learning_materials(
        make_args(skip_prepare=True, overwrite=True),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    assert result["audit"]["status"] == "PASS_WITH_WARNINGS"
    assert (
        "book_synthesis_model_failed_used_deterministic_fallback"
        in result["audit"]["warnings"]
    )
    assert result["learning_materials"]["book_overview"].startswith(
        "These learning materials cover the main lessons detected"
    )
    assert result["audit"]["invalid_source_reference_count"] == 0


def test_deterministic_fallback_produces_valid_final_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    malformed = '{"book_overview": "unterminated'
    responses = [chapter_response("pte_chunk_001"), malformed, malformed]

    book.generate_book_learning_materials(
        make_args(skip_prepare=True, overwrite=True),
        complete_fn=lambda _prompt: responses.pop(0),
    )

    data = json.loads(
        Path("output/pte.book_learning_materials.generated.json").read_text(
            encoding="utf-8"
        )
    )
    assert data["learning_materials"]["study_plan"]
    assert data["learning_materials"]["global_key_terms"]
    assert data["learning_materials"]["final_review"]["questions"]
    assert data["audit"]["invalid_source_reference_count"] == 0


def test_invalid_book_synthesis_source_references_are_caught(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    write_fake_clean_chunks([clean_chunk("pte_chunk_001", chapter_number=1, section="First")])
    responses = [
        chapter_response("pte_chunk_001"),
        synthesis_response("unknown_chunk"),
    ]

    with pytest.raises(book.BookLearningMaterialsError, match="unknown source chunk IDs"):
        book.generate_book_learning_materials(
            make_args(skip_prepare=True, overwrite=True),
            complete_fn=lambda _prompt: responses.pop(0),
        )


def test_missing_input_pdf_returns_clear_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(book.BookLearningMaterialsError, match="Input PDF does not exist"):
        book.generate_book_learning_materials(make_args())


def test_main_returns_nonzero_for_existing_output_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_fake_pdf(Path("input/pdfs/pte.pdf"))
    output = Path("output/pte.book_learning_materials.generated.json")
    output.parent.mkdir(parents=True)
    output.write_text("already here", encoding="utf-8")
    monkeypatch.setattr(
        book,
        "parse_args",
        lambda: make_args(output=str(output)),
    )

    with pytest.raises(SystemExit) as error:
        book.main()

    assert error.value.code == 1
