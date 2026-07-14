import json
import sys
from pathlib import Path

import pytest

import ask_section_pdf_lesson as qa
import retrieve_section_pdf_context as retrieval


LESSON_TEXT = "Complete lesson chunk text about memory. " * 20
FALLBACK_TEXT = "Complete fallback chunk text about tools and agents. " * 20
INSUFFICIENT_ANSWER = (
    "The lesson materials do not provide enough information to answer that question."
)
COMBINED_INSUFFICIENT_ANSWER = (
    "The lesson materials and additional chapter context do not provide enough "
    "information to answer that question."
)


@pytest.fixture(autouse=True)
def isolate_project_root(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def lesson_source_chunk(node_id: str = "lesson_1") -> dict:
    return {
        "node_id": node_id,
        "source_pdf": "input/pdfs/sample.pdf",
        "chapter_number": 6,
        "section": "Memory",
        "page_start": 300,
        "page_end": 300,
        "text_preview": "truncated lesson preview...",
    }


def clean_chunk(node_id: str, text: str = LESSON_TEXT) -> dict:
    return {
        "id": node_id,
        "source_pdf": "input/pdfs/sample.pdf",
        "chapter_number": 6,
        "section": "Memory",
        "topic": "Memory",
        "page_start": 300,
        "page_end": 300,
        "text": text,
        "metadata": {},
    }


def make_lesson_file(tmp_path: Path, source_chunks: list[dict] | None = None) -> Path:
    if source_chunks is None:
        source_chunks = [lesson_source_chunk("lesson_1"), lesson_source_chunk("lesson_2")]

    lesson = {
        "title": "Memory Lesson",
        "introduction": "This lesson explains AI memory.",
        "key_ideas": [
            {
                "idea": "Memory helps AI systems retain information.",
                "source_chunk_ids": ["lesson_1"],
            }
        ],
        "explanation": "Short-term memory is current context.",
        "summary": "Memory supports recall.",
        "source_chunks": source_chunks,
    }
    path = tmp_path / "lesson.json"
    path.write_text(json.dumps(lesson, indent=2) + "\n", encoding="utf-8")

    clean_path = Path("extracted/sample.section_clean_chunks.json")
    clean_path.parent.mkdir(parents=True, exist_ok=True)
    clean_path.write_text(
        json.dumps(
            [
                clean_chunk("lesson_1"),
                clean_chunk("lesson_2", "Second complete lesson chunk text. " * 20),
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def response(
    *,
    answer: str = "Memory is supported by context and external information.",
    source_chunk_ids: list[str] | None = None,
    confidence: str = "high",
) -> dict:
    return {
        "answer": answer,
        "source_chunk_ids": ["lesson_1"] if source_chunk_ids is None else source_chunk_ids,
        "confidence": confidence,
        "follow_up_questions": [
            "How does memory help an AI system?",
            "What is short-term memory?",
        ],
    }


def insufficient_response() -> dict:
    return response(
        answer=INSUFFICIENT_ANSWER,
        source_chunk_ids=[],
        confidence="low",
    )


def combined_insufficient_response() -> dict:
    return response(
        answer=COMBINED_INSUFFICIENT_ANSWER,
        source_chunk_ids=[],
        confidence="low",
    )


class FakeCompleter:
    def __init__(self, payloads: list[dict]):
        self.payloads = payloads
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.payloads:
            raise AssertionError("Unexpected completion call")
        return json.dumps(self.payloads.pop(0))


class FakeFallback:
    def __init__(self, result: dict | None = None):
        self.result = result if result is not None else fallback_result()
        self.calls: list[dict] = []

    def __call__(self, lesson: dict, question: str, *, clean_chunks_file=None) -> dict:
        self.calls.append(
            {
                "lesson": lesson,
                "question": question,
                "clean_chunks_file": clean_chunks_file,
            }
        )
        return self.result


def fallback_chunk(node_id: str = "fallback_1", text: str = FALLBACK_TEXT) -> dict:
    return {
        "node_id": node_id,
        "score": 0.8,
        "source_pdf": "input/pdfs/sample.pdf",
        "chapter_number": 6,
        "section": "Tools",
        "page_start": 279,
        "page_end": 279,
        "text": text,
    }


def fallback_result(chunks: list[dict] | None = None) -> dict:
    if chunks is None:
        chunks = [fallback_chunk("fallback_1"), fallback_chunk("fallback_2")]
    return {
        "source_pdf": "input/pdfs/sample.pdf",
        "document_slug": "sample",
        "chapter_number": 6,
        "storage_dir": "storage/section_clean_pdf_sample",
        "index_id": "section_clean_pdf_sample",
        "clean_chunks_file": "extracted/sample.section_clean_chunks.json",
        "candidate_count": 10,
        "selected_count": len(chunks),
        "chunks": chunks,
    }


def test_allow_index_fallback_defaults_to_false(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ask_section_pdf_lesson.py", "--lesson-file", "x", "--question", "q"])
    args = qa.parse_args()
    assert args.allow_index_fallback is False


def test_cli_parser_enables_fallback_flag(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["ask_section_pdf_lesson.py", "--lesson-file", "x", "--question", "q", "--allow-index-fallback"],
    )
    args = qa.parse_args()
    assert args.allow_index_fallback is True


def test_fallback_disabled_preserves_existing_four_field_schema(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What is memory?",
        allow_index_fallback=False,
        complete_fn=FakeCompleter([response()]),
    )
    assert set(answer) == {"answer", "source_chunk_ids", "confidence", "follow_up_questions"}


def test_fallback_disabled_supported_answer_does_not_call_retrieval(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What is memory?",
        allow_index_fallback=False,
        complete_fn=FakeCompleter([response()]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls == []


def test_fallback_disabled_insufficient_answer_does_not_call_retrieval(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What tools can an AI agent use?",
        allow_index_fallback=False,
        complete_fn=FakeCompleter([insufficient_response()]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls == []
    assert "grounding" not in answer


def test_fallback_enabled_supported_stage1_does_not_call_retrieval(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What is memory?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([response()]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls == []


def test_fallback_enabled_supported_stage1_returns_fallback_attempted_false(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What is memory?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([response(source_chunk_ids=["lesson_1", "lesson_2"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["fallback_attempted"] is False
    assert answer["grounding"]["retrieved_source_chunk_ids"] == []


def test_fallback_enabled_supported_stage1_reports_lesson_provenance(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What is memory?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([response(source_chunk_ids=["lesson_2", "lesson_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["lesson_source_chunk_ids"] == ["lesson_2", "lesson_1"]


def test_valid_insufficient_stage1_triggers_retrieval_when_enabled(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "What tools can an AI agent use?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=fallback,
    )
    assert len(fallback.calls) == 1


def test_retrieval_receives_original_question_unchanged(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    question = "What tools can an AI agent use?"
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        question,
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls[0]["question"] == question


def test_retrieval_receives_same_lesson_dictionary(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    expected_lesson = qa.load_lesson(lesson_file)
    fallback = FakeFallback()
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls[0]["lesson"] == expected_lesson


def test_retrieval_receives_explicit_clean_chunks_override(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    override = Path("extracted/sample.section_clean_chunks.json")
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        clean_chunks_file=override,
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls[0]["clean_chunks_file"] == override


def test_no_valid_new_chunks_returns_stage1_insufficient_response(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response()]),
        fallback_retrieval_fn=FakeFallback(fallback_result(chunks=[])),
    )
    assert answer["answer"] == INSUFFICIENT_ANSWER
    assert answer["grounding"]["fallback_attempted"] is True
    assert answer["grounding"]["retrieved_source_chunk_ids"] == []


def test_no_valid_new_chunks_does_not_make_stage2_model_call(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    completer = FakeCompleter([insufficient_response()])
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=completer,
        fallback_retrieval_fn=FakeFallback(fallback_result(chunks=[])),
    )
    assert len(completer.prompts) == 1


def test_stage2_receives_original_lesson_evidence(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    completer = FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])])
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=completer,
        fallback_retrieval_fn=FakeFallback(),
    )
    assert LESSON_TEXT.strip() in completer.prompts[1]


def test_stage2_receives_fallback_evidence(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    completer = FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])])
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=completer,
        fallback_retrieval_fn=FakeFallback(),
    )
    assert FALLBACK_TEXT in completer.prompts[1]


def test_stage2_prompt_labels_lesson_evidence_origin(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    completer = FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])])
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=completer,
        fallback_retrieval_fn=FakeFallback(),
    )
    assert "EVIDENCE ORIGIN: lesson" in completer.prompts[1]
    assert "LESSON SOURCE CHUNK ID: lesson_1" in completer.prompts[1]


def test_stage2_prompt_labels_fallback_evidence_origin(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    completer = FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])])
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=completer,
        fallback_retrieval_fn=FakeFallback(),
    )
    assert "EVIDENCE ORIGIN: clean_index_fallback" in completer.prompts[1]
    assert "FALLBACK SOURCE CHUNK ID: fallback_1" in completer.prompts[1]


def test_stage2_uses_complete_fallback_text_not_preview(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback(
        fallback_result(
            chunks=[
                fallback_chunk("fallback_1", text="FULL FALLBACK TEXT " * 30)
                | {"text_preview": "truncated fallback preview..."}
            ]
        )
    )
    completer = FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])])
    qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=completer,
        fallback_retrieval_fn=fallback,
    )
    assert "FULL FALLBACK TEXT" in completer.prompts[1]
    assert "truncated fallback preview" not in completer.prompts[1]


def test_stage2_may_cite_lesson_chunks_only(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["lesson_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["lesson_source_chunk_ids"] == ["lesson_1"]
    assert answer["grounding"]["retrieved_source_chunk_ids"] == []


def test_stage2_may_cite_fallback_chunks_only(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["lesson_source_chunk_ids"] == []
    assert answer["grounding"]["retrieved_source_chunk_ids"] == ["fallback_1"]


def test_stage2_may_cite_both_origins(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["lesson_1", "fallback_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["lesson_source_chunk_ids"] == ["lesson_1"]
    assert answer["grounding"]["retrieved_source_chunk_ids"] == ["fallback_1"]


def test_invented_stage2_citation_is_rejected(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    with pytest.raises(qa.LessonQuestionError):
        qa.ask_lesson_question_with_optional_fallback(
            lesson_file,
            "Question?",
            allow_index_fallback=True,
            complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["invented"])]),
            fallback_retrieval_fn=FakeFallback(),
        )


def test_duplicate_stage2_citation_is_rejected(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    with pytest.raises(qa.LessonQuestionError):
        qa.ask_lesson_question_with_optional_fallback(
            lesson_file,
            "Question?",
            allow_index_fallback=True,
            complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1", "fallback_1"])]),
            fallback_retrieval_fn=FakeFallback(),
        )


def test_uncited_fallback_candidates_do_not_appear_in_grounding(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["retrieved_source_chunk_ids"] == ["fallback_1"]
    assert "fallback_2" not in answer["grounding"]["retrieved_source_chunk_ids"]


def test_citation_provenance_is_partitioned_correctly(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["lesson_1", "fallback_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert set(answer["grounding"]["lesson_source_chunk_ids"]) == {"lesson_1"}
    assert set(answer["grounding"]["retrieved_source_chunk_ids"]) == {"fallback_1"}
    assert not (
        set(answer["grounding"]["lesson_source_chunk_ids"])
        & set(answer["grounding"]["retrieved_source_chunk_ids"])
    )


def test_canonical_citation_order_groups_lesson_ids_before_fallback_ids(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_2", "lesson_1", "fallback_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["source_chunk_ids"] == ["lesson_1", "fallback_2", "fallback_1"]


def test_stage2_insufficient_response_has_empty_provenance(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), combined_insufficient_response()]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["source_chunk_ids"] == []
    assert answer["grounding"]["lesson_source_chunk_ids"] == []
    assert answer["grounding"]["retrieved_source_chunk_ids"] == []


def test_medium_confidence_supported_stage1_does_not_trigger_retrieval(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    fallback = FakeFallback()
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([response(confidence="medium")]),
        fallback_retrieval_fn=fallback,
    )
    assert fallback.calls == []
    assert answer["confidence"] == "medium"


def test_existing_output_file_prevents_stage1_generation(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    output = tmp_path / "answer.json"
    output.write_text("original", encoding="utf-8")
    completer = FakeCompleter([response()])
    with pytest.raises(qa.LessonQuestionError):
        qa.ask_lesson_question_with_optional_fallback_to_file(
            lesson_file,
            "Question?",
            output,
            allow_index_fallback=True,
            complete_fn=completer,
            fallback_retrieval_fn=FakeFallback(),
        )
    assert completer.prompts == []


def test_existing_output_file_prevents_fallback_retrieval(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    output = tmp_path / "answer.json"
    output.write_text("original", encoding="utf-8")
    fallback = FakeFallback()
    with pytest.raises(qa.LessonQuestionError):
        qa.ask_lesson_question_with_optional_fallback_to_file(
            lesson_file,
            "Question?",
            output,
            allow_index_fallback=True,
            complete_fn=FakeCompleter([insufficient_response()]),
            fallback_retrieval_fn=fallback,
        )
    assert fallback.calls == []


def test_overwrite_remains_supported(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    output = tmp_path / "answer.json"
    output.write_text("original", encoding="utf-8")
    qa.ask_lesson_question_with_optional_fallback_to_file(
        lesson_file,
        "Question?",
        output,
        overwrite=True,
        allow_index_fallback=False,
        complete_fn=FakeCompleter([response()]),
    )
    assert json.loads(output.read_text(encoding="utf-8"))["source_chunk_ids"] == ["lesson_1"]


def test_existing_step32_non_fallback_function_remains_unchanged(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question(
        lesson_file,
        "Question?",
        complete_fn=FakeCompleter([response()]),
    )
    assert set(answer) == {"answer", "source_chunk_ids", "confidence", "follow_up_questions"}


def test_existing_api_facing_function_still_returns_four_fields(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question(
        lesson_file,
        "Question?",
        complete_fn=FakeCompleter([response(source_chunk_ids=["lesson_2"])]),
    )
    assert "grounding" not in answer
    assert answer["source_chunk_ids"] == ["lesson_2"]


def test_existing_step33a_retrieval_functions_remain_importable():
    assert callable(retrieval.retrieve_lesson_fallback_context)
    assert callable(retrieval.retrieve_section_context_candidates)


def test_fallback_disabled_insufficient_output_has_four_fields(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    output = tmp_path / "answer.json"
    answer, _details = qa.ask_lesson_question_with_optional_fallback_to_file(
        lesson_file,
        "Question?",
        output,
        allow_index_fallback=False,
        complete_fn=FakeCompleter([insufficient_response()]),
        fallback_retrieval_fn=FakeFallback(),
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert set(payload) == {"answer", "source_chunk_ids", "confidence", "follow_up_questions"}
    assert payload == answer


def test_stage2_answer_does_not_include_uncited_lesson_ids(tmp_path: Path):
    lesson_file = make_lesson_file(tmp_path)
    answer = qa.ask_lesson_question_with_optional_fallback(
        lesson_file,
        "Question?",
        allow_index_fallback=True,
        complete_fn=FakeCompleter([insufficient_response(), response(source_chunk_ids=["fallback_1"])]),
        fallback_retrieval_fn=FakeFallback(),
    )
    assert answer["grounding"]["lesson_source_chunk_ids"] == []
    assert "lesson_2" not in answer["source_chunk_ids"]
