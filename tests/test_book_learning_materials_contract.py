import copy
import json
from pathlib import Path

import pytest

import validate_book_learning_materials_contract as cli
from book_learning_materials_contract import (
    BOOK_LEARNING_MATERIALS_CONTRACT_AUDIT_VERSION,
    BOOK_LEARNING_MATERIALS_SCHEMA_VERSION,
    validate_book_contract,
)


FIXTURE_BOOK = Path("tests/fixtures/book_learning_materials_v2.valid.json")
FIXTURE_CHUNKS = Path("tests/fixtures/book_learning_materials_v2.clean_chunks.json")


def load_valid_book() -> dict:
    return json.loads(FIXTURE_BOOK.read_text(encoding="utf-8"))


def load_valid_chunks() -> list[dict]:
    return json.loads(FIXTURE_CHUNKS.read_text(encoding="utf-8"))


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def validate_data(tmp_path: Path, book: dict | None = None, chunks: list[dict] | None = None):
    book_path = write_json(tmp_path / "book.json", book if book is not None else load_valid_book())
    chunks_path = write_json(
        tmp_path / "clean_chunks.json",
        chunks if chunks is not None else load_valid_chunks(),
    )
    return validate_book_contract(book_file=book_path, clean_chunks_file=chunks_path)


def error_codes(audit: dict) -> set[str]:
    return {error["code"] for error in audit["errors"]}


def first_chapter(book: dict) -> dict:
    return book["learning_materials"]["chapters"][0]


def task_format_object(book: dict) -> dict:
    return first_chapter(book)["core_lessons"][0]["explanation"]


def test_accepts_valid_v2_artifact_and_counts_contract_features(tmp_path):
    audit = validate_data(tmp_path)

    assert audit["schema_version"] == BOOK_LEARNING_MATERIALS_CONTRACT_AUDIT_VERSION
    assert audit["status"] == "PASS"
    summary = audit["summary"]
    assert summary["grounded_content_count"] == 21
    assert summary["source_grounded_count"] == 11
    assert summary["pedagogical_generation_count"] == 9
    assert summary["insufficient_source_evidence_count"] == 1
    assert summary["high_risk_claim_count"] == 1
    assert summary["high_risk_verified_span_count"] == 1
    assert summary["verified_evidence_span_count"] == 1
    assert summary["unique_referenced_source_chunk_count"] == 2
    assert summary["invalid_claim_count"] == 0
    assert summary["claims_by_kind"]["task_format"] == 1
    assert summary["claims_by_origin"]["pedagogical_generation"] == 9


def test_wrong_typed_learning_materials_fails_instead_of_skipping_validation(tmp_path):
    # Audit finding H-3: content validation ran only when learning_materials was a
    # dict, so a string (or any non-object) skipped every content check and the
    # book still returned PASS. The contract is the grounding gate; a shape it
    # cannot validate must FAIL.
    for bad_value in ["a string, not an object", [], 42, None]:
        book = load_valid_book()
        book["learning_materials"] = bad_value
        audit = validate_data(tmp_path, book=book)
        assert audit["status"] == "FAIL", f"passed with learning_materials={bad_value!r}"
        assert "INVALID_TOP_LEVEL_SHAPE" in error_codes(audit)


def test_wrong_typed_top_level_fields_are_all_rejected(tmp_path):
    for key, bad_value in [
        ("book", "str"),
        ("generation", []),
        ("source_chunks", {}),
        ("audit", "str"),
    ]:
        book = load_valid_book()
        book[key] = bad_value
        audit = validate_data(tmp_path, book=book)
        assert audit["status"] == "FAIL", f"{key}={bad_value!r} passed"
        assert any(
            e["json_path"] == f"$.{key}" and e["code"] == "INVALID_TOP_LEVEL_SHAPE"
            for e in audit["errors"]
        ), f"no top-level type error for {key}"


def test_rejects_schema_and_pipeline_version_problems(tmp_path):
    book = load_valid_book()
    book["schema_version"] = "book_learning_materials.v1"
    audit = validate_data(tmp_path, book=book)
    assert "UNSUPPORTED_SCHEMA_VERSION" in error_codes(audit)

    book = load_valid_book()
    book.pop("schema_version")
    audit = validate_data(tmp_path, book=book)
    assert "UNSUPPORTED_SCHEMA_VERSION" in error_codes(audit)

    book = load_valid_book()
    book["generation"]["pipeline_version"] = "book_learning_materials.v1"
    audit = validate_data(tmp_path, book=book)
    assert "PIPELINE_VERSION_MISMATCH" in error_codes(audit)

    book = load_valid_book()
    book.pop("learning_materials")
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_TOP_LEVEL_SHAPE" in error_codes(audit)


def test_rejects_missing_grounded_fields_unknown_origin_and_unknown_kind(tmp_path):
    book = load_valid_book()
    book["learning_materials"]["book_overview"].pop("origin")
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_GROUNDED_CONTENT_SHAPE" in error_codes(audit)

    book = load_valid_book()
    book["learning_materials"]["book_overview"]["origin"] = "model_guess"
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_ORIGIN" in error_codes(audit)

    book = load_valid_book()
    book["learning_materials"]["book_overview"]["claim_kind"] = "made_up"
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_CLAIM_KIND" in error_codes(audit)


def test_origin_field_combinations_are_enforced(tmp_path):
    book = load_valid_book()
    book["learning_materials"]["book_overview"]["source_chunk_ids"] = []
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_ORIGIN_FIELD_COMBINATION" in error_codes(audit)

    book = load_valid_book()
    generated = first_chapter(book)["worked_examples"][0]["example"]
    generated["source_chunk_ids"] = ["sample_chunk_001"]
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_ORIGIN_FIELD_COMBINATION" in error_codes(audit)

    book = load_valid_book()
    generated = first_chapter(book)["worked_examples"][0]["example"]
    generated["evidence_spans"] = [
        {
            "node_id": "sample_chunk_001",
            "quote": "test takers hear a short question",
        }
    ]
    audit = validate_data(tmp_path, book=book)
    assert "INVALID_ORIGIN_FIELD_COMBINATION" in error_codes(audit)

    book = load_valid_book()
    insufficient = first_chapter(book)["learning_objectives"][0]
    insufficient["text"] = "Unknown"
    insufficient["reason"] = None
    audit = validate_data(tmp_path, book=book)
    codes = error_codes(audit)
    assert "INVALID_ORIGIN_FIELD_COMBINATION" in codes
    assert "MISSING_INSUFFICIENT_EVIDENCE_REASON" in codes


def test_pedagogical_generation_is_restricted_for_factual_and_high_risk_kinds(tmp_path):
    book = load_valid_book()
    overview = book["learning_materials"]["book_overview"]
    overview["origin"] = "pedagogical_generation"
    overview["source_chunk_ids"] = []
    audit = validate_data(tmp_path, book=book)
    assert "PEDAGOGICAL_ORIGIN_NOT_ALLOWED" in error_codes(audit)

    for high_risk_kind in [
        "official_rule",
        "task_format",
        "pronunciation_rule",
        "grammar_rule",
    ]:
        book = load_valid_book()
        item = task_format_object(book)
        item["claim_kind"] = high_risk_kind
        item["origin"] = "pedagogical_generation"
        item["source_chunk_ids"] = []
        item["evidence_spans"] = []
        audit = validate_data(tmp_path, book=book)
        assert "HIGH_RISK_PEDAGOGICAL_GENERATION_FORBIDDEN" in error_codes(audit)

    book = load_valid_book()
    correction = first_chapter(book)["common_misconceptions"][0]["correction"]
    correction["origin"] = "pedagogical_generation"
    correction["source_chunk_ids"] = []
    audit = validate_data(tmp_path, book=book)
    assert "PEDAGOGICAL_ORIGIN_NOT_ALLOWED" in error_codes(audit)


def test_high_risk_source_grounded_claim_requires_verified_span(tmp_path):
    book = load_valid_book()
    task_format_object(book)["evidence_spans"] = []
    audit = validate_data(tmp_path, book=book)
    assert "HIGH_RISK_EVIDENCE_SPAN_REQUIRED" in error_codes(audit)

    book = load_valid_book()
    task_format_object(book)["evidence_spans"][0]["node_id"] = "sample_chunk_002"
    audit = validate_data(tmp_path, book=book)
    assert "EVIDENCE_SPAN_NODE_NOT_CITED" in error_codes(audit)

    book = load_valid_book()
    task_format_object(book)["evidence_spans"][0]["quote"] = "this quote is absent from source text"
    audit = validate_data(tmp_path, book=book)
    assert "EVIDENCE_SPAN_QUOTE_NOT_FOUND" in error_codes(audit)


def test_evidence_span_length_duplicate_and_exact_matching_rules(tmp_path):
    book = load_valid_book()
    task_format_object(book)["evidence_spans"][0]["quote"] = "short quote"
    audit = validate_data(tmp_path, book=book)
    assert "EVIDENCE_SPAN_QUOTE_TOO_SHORT" in error_codes(audit)

    book = load_valid_book()
    long_quote = " ".join(f"word{i}" for i in range(81))
    task_format_object(book)["evidence_spans"][0]["quote"] = long_quote
    audit = validate_data(tmp_path, book=book)
    assert "EVIDENCE_SPAN_QUOTE_TOO_LONG" in error_codes(audit)

    book = load_valid_book()
    span = copy.deepcopy(task_format_object(book)["evidence_spans"][0])
    task_format_object(book)["evidence_spans"].append(span)
    audit = validate_data(tmp_path, book=book)
    assert "DUPLICATE_EVIDENCE_SPAN" in error_codes(audit)

    book = load_valid_book()
    task_format_object(book)["evidence_spans"][0]["quote"] = (
        "test takers hear a short question and give a brief written answer"
    )
    audit = validate_data(tmp_path, book=book)
    assert "EVIDENCE_SPAN_QUOTE_NOT_FOUND" in error_codes(audit)


def test_unicode_nfkc_and_whitespace_are_normalized_but_not_fuzzy_matched(tmp_path):
    book = load_valid_book()
    chunks = load_valid_chunks()
    chunks[0]["text"] = "Ａ quick    normalized quote appears here for validation."
    item = task_format_object(book)
    item["text"] = "A normalized quote is present."
    item["evidence_spans"][0]["quote"] = "A quick normalized quote appears"
    audit = validate_data(tmp_path, book=book, chunks=chunks)
    assert audit["status"] == "PASS"

    item["evidence_spans"][0]["quote"] = "A quick normalized quote appears!"
    audit = validate_data(tmp_path, book=book, chunks=chunks)
    assert "EVIDENCE_SPAN_QUOTE_NOT_FOUND" in error_codes(audit)


def test_clean_chunk_validation_and_preview_is_not_authoritative(tmp_path):
    chunks = load_valid_chunks()
    chunks.append(copy.deepcopy(chunks[0]))
    audit = validate_data(tmp_path, chunks=chunks)
    assert "DUPLICATE_CLEAN_CHUNK_ID" in error_codes(audit)

    chunks = load_valid_chunks()
    chunks[0]["text"] = ""
    audit = validate_data(tmp_path, chunks=chunks)
    assert "EMPTY_CLEAN_CHUNK_TEXT" in error_codes(audit)

    book = load_valid_book()
    chunks = load_valid_chunks()
    chunks[0]["text_preview"] = task_format_object(book)["evidence_spans"][0]["quote"]
    chunks[0]["text"] = "The authoritative full text does not contain the selected words."
    audit = validate_data(tmp_path, book=book, chunks=chunks)
    assert "EVIDENCE_SPAN_QUOTE_NOT_FOUND" in error_codes(audit)


def test_source_id_duplicates_missing_ids_and_grounded_in_duplicates(tmp_path):
    book = load_valid_book()
    overview = book["learning_materials"]["book_overview"]
    overview["source_chunk_ids"] = ["sample_chunk_001", "sample_chunk_001"]
    audit = validate_data(tmp_path, book=book)
    assert "DUPLICATE_SOURCE_CHUNK_ID" in error_codes(audit)

    book = load_valid_book()
    overview = book["learning_materials"]["book_overview"]
    overview["source_chunk_ids"] = ["missing_chunk"]
    audit = validate_data(tmp_path, book=book)
    assert "SOURCE_CHUNK_ID_NOT_FOUND" in error_codes(audit)

    book = load_valid_book()
    generated = first_chapter(book)["worked_examples"][0]["example"]
    generated["grounded_in_source_chunk_ids"] = [
        "sample_chunk_001",
        "sample_chunk_001",
    ]
    audit = validate_data(tmp_path, book=book)
    assert "DUPLICATE_SOURCE_CHUNK_ID" in error_codes(audit)


def test_chapter_and_source_document_consistency(tmp_path):
    book = load_valid_book()
    chunks = load_valid_chunks()
    chunks[0]["chapter_number"] = 2
    audit = validate_data(tmp_path, book=book, chunks=chunks)
    assert "CHAPTER_MISMATCH" in error_codes(audit)

    chunks = load_valid_chunks()
    chunks[0]["source_pdf"] = "input/pdfs/other.pdf"
    audit = validate_data(tmp_path, book=book, chunks=chunks)
    assert "SOURCE_DOCUMENT_MISMATCH" in error_codes(audit)


def test_no_inherited_citation_is_supported(tmp_path):
    book = load_valid_book()
    summary = first_chapter(book)["chapter_summary"]
    summary["source_chunk_ids"] = []
    audit = validate_data(tmp_path, book=book)

    assert "INVALID_ORIGIN_FIELD_COMBINATION" in error_codes(audit)
    assert "INHERITED_CITATION_NOT_SUPPORTED" in error_codes(audit)
    assert any(
        error["json_path"]
        == "$.learning_materials.chapters[0].chapter_summary.source_chunk_ids"
        for error in audit["errors"]
    )


def test_generated_study_plan_and_example_with_grounded_ids_are_accepted(tmp_path):
    audit = validate_data(tmp_path)
    assert audit["status"] == "PASS"
    assert audit["summary"]["claims_by_kind"]["study_plan"] >= 2
    assert audit["summary"]["claims_by_kind"]["pedagogical_example"] == 1


def test_error_ordering_and_exact_json_paths_are_deterministic(tmp_path):
    book = load_valid_book()
    task_format_object(book)["origin"] = "pedagogical_generation"
    task_format_object(book)["source_chunk_ids"] = []
    task_format_object(book)["evidence_spans"] = []

    audit1 = validate_data(tmp_path, book=book)
    audit2 = validate_data(tmp_path, book=book)

    assert audit1["errors"] == audit2["errors"]
    assert any(
        error["json_path"]
        == "$.learning_materials.chapters[0].core_lessons[0].explanation"
        for error in audit1["errors"]
    )


def test_cli_writes_valid_json_and_text_report(tmp_path):
    output = tmp_path / "audit.json"
    report = tmp_path / "audit.txt"
    exit_code = cli.main(
        [
            "--book-file",
            str(FIXTURE_BOOK),
            "--clean-chunks-file",
            str(FIXTURE_CHUNKS),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )

    assert exit_code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert "BOOK LEARNING MATERIALS CONTRACT AUDIT" in report.read_text(
        encoding="utf-8"
    )


def test_cli_protects_overwrite_and_explicit_overwrite_replaces(tmp_path):
    output = tmp_path / "audit.json"
    report = tmp_path / "audit.txt"
    output.write_text("original", encoding="utf-8")

    exit_code = cli.main(
        [
            "--book-file",
            str(FIXTURE_BOOK),
            "--clean-chunks-file",
            str(FIXTURE_CHUNKS),
            "--output",
            str(output),
            "--report",
            str(report),
        ]
    )
    assert exit_code == 1
    assert output.read_text(encoding="utf-8") == "original"

    exit_code = cli.main(
        [
            "--book-file",
            str(FIXTURE_BOOK),
            "--clean-chunks-file",
            str(FIXTURE_CHUNKS),
            "--output",
            str(output),
            "--report",
            str(report),
            "--overwrite",
        ]
    )
    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"


def test_dry_run_writes_nothing_and_returns_status(tmp_path):
    output = tmp_path / "audit.json"
    report = tmp_path / "audit.txt"
    exit_code = cli.main(
        [
            "--book-file",
            str(FIXTURE_BOOK),
            "--clean-chunks-file",
            str(FIXTURE_CHUNKS),
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


def test_cli_returns_nonzero_and_writes_failure_audit_for_invalid_contract(tmp_path):
    book = load_valid_book()
    book["schema_version"] = "book_learning_materials.v1"
    book_path = write_json(tmp_path / "bad_book.json", book)
    chunks_path = write_json(tmp_path / "chunks.json", load_valid_chunks())
    output = tmp_path / "audit.json"

    exit_code = cli.main(
        [
            "--book-file",
            str(book_path),
            "--clean-chunks-file",
            str(chunks_path),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["status"] == "FAIL"
    assert "UNSUPPORTED_SCHEMA_VERSION" in error_codes(data)
