import json
from pathlib import Path

import pytest

import extract_book_learning_claims as claims


def clean_chunk(
    node_id: str,
    *,
    chapter_number: int | None = 1,
    source_pdf: str = "input/pdfs/pte.pdf",
    text: str = "FULL CLEAN SOURCE TEXT",
) -> dict:
    return {
        "id": node_id,
        "source_pdf": source_pdf,
        "source_type": "pdf",
        "book_id": "pte",
        "book_title": "PTE Sample",
        "chapter": f"LESSON {chapter_number}" if chapter_number else None,
        "chapter_number": chapter_number,
        "section": f"LESSON {chapter_number}" if chapter_number else None,
        "topic": f"LESSON {chapter_number}" if chapter_number else None,
        "content_type": "unknown",
        "page_start": chapter_number or 1,
        "page_end": chapter_number or 1,
        "is_front_matter": chapter_number is None,
        "text": text,
        "metadata": {"page_label": str(chapter_number or 1)},
    }


def chapter_package() -> dict:
    return {
        "chapter_number": 1,
        "chapter_title": "LESSON 1: Foundations",
        "estimated_study_time_minutes": 45,
        "chapter_summary": "Exact chapter summary.",
        "learning_objectives": ["Exact learning objective."],
        "key_terms": [
            {
                "term": "Answer short question",
                "meaning": "Exact key term meaning.",
                "source_chunk_ids": ["pte_chunk_002"],
            }
        ],
        "core_lessons": [
            {
                "title": "Core title",
                "explanation": "Exact core lesson explanation.",
                "source_chunk_ids": ["pte_chunk_002"],
            }
        ],
        "worked_examples": [
            {
                "title": "Worked title",
                "example": "Exact worked example.",
                "explanation": "Exact worked explanation.",
                "source_chunk_ids": ["pte_chunk_002"],
            }
        ],
        "common_misconceptions": [
            {
                "misconception": "Exact misconception.",
                "correction": "Exact correction.",
                "source_chunk_ids": ["pte_chunk_002"],
            }
        ],
        "practice_questions": [
            {
                "question": "Exact question?",
                "answer": "Exact practice answer.",
                "source_chunk_ids": ["pte_chunk_002"],
            }
        ],
        "review_checklist": ["Exact review checklist item."],
        "source_chunk_ids": ["pte_chunk_001"],
    }


def final_book(clean_chunks_path: str = "extracted/pte.section_clean_chunks.json") -> dict:
    return {
        "book": {
            "slug": "pte",
            "source_pdf": "input/pdfs/pte.pdf",
            "title": "PTE Sample",
        },
        "generation": {
            "pipeline_version": "book_learning_materials.v1",
            "clean_chunks_path": clean_chunks_path,
        },
        "learning_materials": {
            "book_overview": "Exact book overview.",
            "who_this_is_for": ["Exact audience item."],
            "how_to_use_this_book": ["Exact usage instruction."],
            "study_plan": [
                {
                    "week": 1,
                    "focus": "Exact study focus.",
                    "chapters": [1],
                    "activities": ["Exact study activity."],
                }
            ],
            "global_key_terms": [
                {
                    "term": "Global term",
                    "meaning": "Exact global key term meaning.",
                    "chapter_numbers": [1],
                    "source_chunk_ids": ["pte_chunk_002"],
                }
            ],
            "final_review": {
                "summary": "Exact final review summary.",
                "questions": ["Exact final review question?"],
            },
            "chapters": [chapter_package()],
        },
        "source_chunks": [
            {
                "node_id": "pte_chunk_002",
                "text_preview": "THIS PREVIEW MUST NOT BE USED",
            }
        ],
        "audit": {"status": "PASS"},
    }


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def write_fixture_files(tmp_path: Path, book: dict | None = None, chunks: list[dict] | None = None):
    book_path = tmp_path / "book.json"
    clean_path = tmp_path / "clean.json"
    write_json(book_path, book or final_book(str(clean_path)))
    write_json(
        clean_path,
        chunks
        or [
            clean_chunk("pte_chunk_001", text="FULL CLEAN TEXT FOR CHAPTER."),
            clean_chunk("pte_chunk_002", text="FULL CLEAN TEXT FOR LOCAL CLAIMS."),
        ],
    )
    return book_path, clean_path


def claims_by_id(result: dict) -> dict[str, dict]:
    return {claim["claim_id"]: claim for claim in result["claims"]}


def test_extracts_supported_final_book_shape_and_known_claim_types(tmp_path):
    book_path, clean_path = write_fixture_files(tmp_path)

    result = claims.extract_book_claim_evidence(
        book_file=book_path,
        clean_chunks_file=clean_path,
    )

    assert result["schema_version"] == "book_claim_evidence.v1"
    assert result["status"] == "PASS"
    assert result["input"]["pipeline_version"] == "book_learning_materials.v1"

    by_id = claims_by_id(result)
    claim_ids = [claim["claim_id"] for claim in result["claims"]]
    assert len(claim_ids) == len(set(claim_ids))
    assert by_id["book.book_overview"]["claim_text"] == "Exact book overview."
    assert (
        by_id["chapter_01.chapter_summary"]["json_path"]
        == "$.learning_materials.chapters[0].chapter_summary"
    )
    assert by_id["chapter_01.chapter_summary"]["citation_origin"] == (
        "inherited_chapter"
    )
    assert by_id["chapter_01.learning_objectives.0"]["citation_origin"] == (
        "inherited_chapter"
    )
    assert by_id["chapter_01.review_checklist.0"]["citation_origin"] == (
        "inherited_chapter"
    )
    assert by_id["chapter_01.estimated_study_time_minutes"] == {
        "claim_id": "chapter_01.estimated_study_time_minutes",
        "json_path": "$.learning_materials.chapters[0].estimated_study_time_minutes",
        "scope": "chapter",
        "chapter_number": 1,
        "chapter_title": "LESSON 1: Foundations",
        "claim_type": "estimated_study_time",
        "claim_text": "Estimated study time: 45 minutes.",
        "context": {},
        "citation_origin": "none",
        "source_chunk_ids": [],
        "evidence_status": "NO_CITATION",
    }
    assert by_id["chapter_01.key_terms.0.meaning"]["context"] == {
        "term": "Answer short question"
    }
    assert by_id["chapter_01.core_lessons.0.explanation"]["context"] == {
        "title": "Core title"
    }
    assert by_id["chapter_01.worked_examples.0.example"]["claim_type"] == (
        "worked_example_content"
    )
    assert by_id["chapter_01.worked_examples.0.explanation"]["claim_type"] == (
        "worked_example_explanation"
    )
    assert by_id["chapter_01.common_misconceptions.0.misconception"][
        "claim_type"
    ] == "misconception_statement"
    assert by_id["chapter_01.common_misconceptions.0.correction"][
        "claim_type"
    ] == "misconception_correction"
    assert by_id["chapter_01.practice_questions.0.answer"]["context"] == {
        "question": "Exact question?"
    }

    claim_types = result["summary"]["claims_by_type"]
    for claim_type in [
        "audience_item",
        "book_overview",
        "chapter_summary",
        "core_lesson_explanation",
        "estimated_study_time",
        "final_review_question",
        "final_review_summary",
        "global_key_term_definition",
        "key_term_definition",
        "learning_objective",
        "misconception_correction",
        "misconception_statement",
        "practice_answer",
        "review_checklist_item",
        "study_plan_activity",
        "study_plan_focus",
        "usage_instruction",
        "worked_example_content",
        "worked_example_explanation",
    ]:
        assert claim_types[claim_type] >= 1

    assert result["summary"]["claim_count"] == len(result["claims"]) == 19
    assert result["summary"]["book_claim_count"] == 8
    assert result["summary"]["chapter_claim_count"] == 11
    assert result["summary"]["locally_cited_claim_count"] == 8
    assert result["summary"]["inherited_citation_claim_count"] == 3
    assert result["summary"]["uncited_claim_count"] == 8


def test_preserves_source_id_order_within_claims(tmp_path):
    data = final_book()
    data["learning_materials"]["global_key_terms"][0]["source_chunk_ids"] = [
        "pte_chunk_002",
        "pte_chunk_001",
    ]
    book_path, clean_path = write_fixture_files(tmp_path, book=data)

    result = claims.extract_book_claim_evidence(
        book_file=book_path,
        clean_chunks_file=clean_path,
    )

    by_id = claims_by_id(result)
    assert by_id["book.global_key_terms.0.meaning"]["source_chunk_ids"] == [
        "pte_chunk_002",
        "pte_chunk_001",
    ]


def test_resolves_full_evidence_once_and_never_uses_text_preview(tmp_path):
    book_path, clean_path = write_fixture_files(tmp_path)

    result = claims.extract_book_claim_evidence(
        book_file=book_path,
        clean_chunks_file=clean_path,
    )

    evidence_by_id = {chunk["node_id"]: chunk for chunk in result["evidence_chunks"]}
    assert set(evidence_by_id) == {"pte_chunk_001", "pte_chunk_002"}
    assert evidence_by_id["pte_chunk_002"]["text"] == "FULL CLEAN TEXT FOR LOCAL CLAIMS."
    assert "text_preview" not in evidence_by_id["pte_chunk_002"]
    assert result["summary"]["unique_evidence_chunk_count"] == 2


def test_supports_learning_materials_chapter_packages_location(tmp_path):
    data = final_book()
    chapters = data["learning_materials"].pop("chapters")
    data["learning_materials"]["chapter_packages"] = chapters
    book_path, clean_path = write_fixture_files(tmp_path, book=data)

    result = claims.extract_book_claim_evidence(
        book_file=book_path,
        clean_chunks_file=clean_path,
    )

    by_id = claims_by_id(result)
    assert by_id["chapter_01.chapter_summary"]["json_path"] == (
        "$.learning_materials.chapter_packages[0].chapter_summary"
    )


def test_supports_top_level_checkpoint_chapter_packages_location(tmp_path):
    data = final_book()
    chapters = data["learning_materials"].pop("chapters")
    data.pop("learning_materials")
    data["chapter_packages"] = chapters
    book_path, clean_path = write_fixture_files(tmp_path, book=data)

    result = claims.extract_book_claim_evidence(
        book_file=book_path,
        clean_chunks_file=clean_path,
    )

    by_id = claims_by_id(result)
    assert by_id["chapter_01.chapter_summary"]["json_path"] == (
        "$.chapter_packages[0].chapter_summary"
    )


def test_automatic_clean_path_and_explicit_override(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    auto_clean = Path("extracted/auto.json")
    override_clean = Path("extracted/override.json")
    book = final_book(str(auto_clean))
    write_json(Path("book.json"), book)
    write_json(auto_clean, [clean_chunk("pte_chunk_001"), clean_chunk("pte_chunk_002")])
    write_json(
        override_clean,
        [
            clean_chunk("pte_chunk_001", text="AUTO OVERRIDDEN ONE"),
            clean_chunk("pte_chunk_002", text="AUTO OVERRIDDEN TWO"),
        ],
    )

    auto_result = claims.extract_book_claim_evidence(book_file="book.json")
    override_result = claims.extract_book_claim_evidence(
        book_file="book.json",
        clean_chunks_file=override_clean,
    )

    assert auto_result["input"]["clean_chunks_file"] == str(auto_clean)
    assert override_result["input"]["clean_chunks_file"] == str(override_clean)
    evidence_by_id = {
        chunk["node_id"]: chunk for chunk in override_result["evidence_chunks"]
    }
    assert evidence_by_id["pte_chunk_001"]["text"] == "AUTO OVERRIDDEN ONE"


def test_rejects_duplicate_source_ids_inside_a_claim(tmp_path):
    data = final_book()
    data["learning_materials"]["chapters"][0]["core_lessons"][0][
        "source_chunk_ids"
    ] = ["pte_chunk_002", "pte_chunk_002"]
    book_path, clean_path = write_fixture_files(tmp_path, book=data)

    with pytest.raises(claims.BookClaimExtractionError, match="duplicate source"):
        claims.extract_book_claim_evidence(
            book_file=book_path,
            clean_chunks_file=clean_path,
        )


def test_rejects_duplicate_clean_chunk_ids(tmp_path):
    book_path, clean_path = write_fixture_files(
        tmp_path,
        chunks=[
            clean_chunk("pte_chunk_001"),
            clean_chunk("pte_chunk_001"),
            clean_chunk("pte_chunk_002"),
        ],
    )

    with pytest.raises(claims.BookClaimExtractionError, match="duplicate chunk IDs"):
        claims.extract_book_claim_evidence(
            book_file=book_path,
            clean_chunks_file=clean_path,
        )


def test_rejects_unresolved_cited_ids(tmp_path):
    book_path, clean_path = write_fixture_files(
        tmp_path,
        chunks=[clean_chunk("pte_chunk_001")],
    )

    with pytest.raises(claims.BookClaimExtractionError, match="unresolved source ID"):
        claims.extract_book_claim_evidence(
            book_file=book_path,
            clean_chunks_file=clean_path,
        )


def test_rejects_empty_evidence_text(tmp_path):
    book_path, clean_path = write_fixture_files(
        tmp_path,
        chunks=[
            clean_chunk("pte_chunk_001"),
            clean_chunk("pte_chunk_002", text="  "),
        ],
    )

    with pytest.raises(claims.BookClaimExtractionError, match="empty evidence text"):
        claims.extract_book_claim_evidence(
            book_file=book_path,
            clean_chunks_file=clean_path,
        )


def test_rejects_document_mismatch(tmp_path):
    book_path, clean_path = write_fixture_files(
        tmp_path,
        chunks=[
            clean_chunk("pte_chunk_001"),
            clean_chunk("pte_chunk_002", source_pdf="input/pdfs/other.pdf"),
        ],
    )

    with pytest.raises(claims.BookClaimExtractionError, match="source PDF mismatch"):
        claims.extract_book_claim_evidence(
            book_file=book_path,
            clean_chunks_file=clean_path,
        )


def test_rejects_chapter_mismatch_for_chapter_claims(tmp_path):
    book_path, clean_path = write_fixture_files(
        tmp_path,
        chunks=[
            clean_chunk("pte_chunk_001"),
            clean_chunk("pte_chunk_002", chapter_number=2),
        ],
    )

    with pytest.raises(claims.BookClaimExtractionError, match="chapter mismatch"):
        claims.extract_book_claim_evidence(
            book_file=book_path,
            clean_chunks_file=clean_path,
        )


def test_allows_uncited_claims(tmp_path):
    data = final_book()
    data["learning_materials"]["chapters"][0].pop("estimated_study_time_minutes")
    book_path, clean_path = write_fixture_files(tmp_path, book=data)

    result = claims.extract_book_claim_evidence(
        book_file=book_path,
        clean_chunks_file=clean_path,
    )

    uncited = [
        claim for claim in result["claims"] if claim["citation_origin"] == "none"
    ]
    assert uncited
    assert all(claim["evidence_status"] == "NO_CITATION" for claim in uncited)


def test_cli_dry_run_writes_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book_path, clean_path = write_fixture_files(tmp_path)
    output = tmp_path / "output.json"
    report = tmp_path / "report.txt"

    exit_code = claims.main(
        [
            "--book-file",
            str(book_path),
            "--clean-chunks-file",
            str(clean_path),
            "--output",
            str(output),
            "--report",
            str(report),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert not output.exists()
    assert not report.exists()


def test_cli_rejects_existing_output_without_overwrite_and_preserves_file(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    book_path, clean_path = write_fixture_files(tmp_path)
    output = tmp_path / "output.json"
    output.write_text("original", encoding="utf-8")

    exit_code = claims.main(
        [
            "--book-file",
            str(book_path),
            "--clean-chunks-file",
            str(clean_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert output.read_text(encoding="utf-8") == "original"


def test_cli_overwrite_replaces_output_and_writes_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    book_path, clean_path = write_fixture_files(tmp_path)
    output = tmp_path / "output.json"
    report = tmp_path / "report.txt"
    output.write_text("original", encoding="utf-8")

    exit_code = claims.main(
        [
            "--book-file",
            str(book_path),
            "--clean-chunks-file",
            str(clean_path),
            "--output",
            str(output),
            "--report",
            str(report),
            "--overwrite",
        ]
    )

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert "BOOK CLAIM EVIDENCE REPORT" in report.read_text(encoding="utf-8")
