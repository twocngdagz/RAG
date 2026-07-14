import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from book_learning_materials_contract import (
    BOOK_LEARNING_MATERIALS_SCHEMA_VERSION,
    ContractValidator,
    atomic_write_json,
    atomic_write_text,
    format_text_report,
    load_clean_chunks as load_contract_clean_chunks,
    normalize_text,
)


BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION = BOOK_LEARNING_MATERIALS_SCHEMA_VERSION
BOOK_LEARNING_MATERIALS_V2_CHECKPOINT_SCHEMA_VERSION = (
    "book_learning_materials_v2_checkpoint.v1"
)
BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION = (
    "book_learning_materials_v2_chapter.v2"
)
V2_SELECTION_MODE_CHAPTERS = "chapters"

HIGH_RISK_CLAIM_KINDS = {
    "official_rule",
    "task_format",
    "pronunciation_rule",
    "grammar_rule",
}

# Claim kinds the model is asked to invent, so they carry no evidence spans.
#
# misconception_statement belongs here even though it sounds factual. A
# misconception is a false belief, named so the paired correction can refute it:
# the source asserts the truth, never the error. Requiring it to be
# source_grounded forced the model to attach evidence that supports the
# *correction*, and the grounding judge then read the misconception as
# contradicting its own evidence -- "learners need to write their answers" was
# reported as CONTRADICTED for faithfully stating a belief the source refutes.
# The correction stays strictly source_grounded; only the error being named is
# generated. A source that explicitly names a misconception may still cite it as
# source_grounded.
PEDAGOGICAL_GENERATION_CLAIM_KINDS = {
    "pedagogical_example",
    "practice_question",
    "practice_answer",
    "learner_instruction",
    "self_assessment",
    "study_plan",
    "misconception_statement",
}

GROUNDED_CONTENT_SCHEMA = {
    "text": "string or null",
    "claim_kind": "source_summary",
    "origin": "source_grounded",
    "source_chunk_ids": ["source_chunk_id"],
    "grounded_in_source_chunk_ids": [],
    "evidence_spans": [{"node_id": "source_chunk_id", "quote": "exact source quote"}],
    "reason": None,
}

SUBSTANTIVE_MINIMUMS = {
    "learning_objectives": (3, "TOO_FEW_LEARNING_OBJECTIVES"),
    "key_terms": (3, "TOO_FEW_KEY_TERMS"),
    "core_lessons": (4, "TOO_FEW_CORE_LESSONS"),
    "worked_examples": (2, "TOO_FEW_WORKED_EXAMPLES"),
    "practice_questions": (3, "TOO_FEW_PRACTICE_QUESTIONS"),
    "review_checklist": (4, "TOO_FEW_REVIEW_CHECKLIST_ITEMS"),
}

GENERIC_PLACEHOLDER_TEXTS = {
    normalize_text("Review the cited source excerpt.").lower(),
    normalize_text("The source excerpt provides the local evidence.").lower(),
    normalize_text("Study the source material.").lower(),
    normalize_text("Read the source and answer the question.").lower(),
    normalize_text("This lesson is based on the source excerpt.").lower(),
}


class V2GenerationError(RuntimeError):
    pass


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def text_preview(text: str, max_chars: int = 300) -> str:
    normalized = normalize_whitespace(text)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def chunk_node_id(chunk: dict[str, Any]) -> str:
    for key in ("node_id", "id", "chunk_id"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def unique_preserve_order(values: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    output: list[Any] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def clean_chunks_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def derive_contract_audit_paths(output_json: Path) -> tuple[Path, Path]:
    name = output_json.name
    if name.endswith(".generated.json"):
        prefix = name[: -len(".generated.json")]
    elif name.endswith(".json"):
        prefix = name[: -len(".json")]
    else:
        prefix = output_json.stem
    return (
        output_json.with_name(f"{prefix}.contract.audit.json"),
        output_json.with_name(f"{prefix}.contract.audit.txt"),
    )


def derive_invalid_candidate_dir(output_json: Path) -> Path:
    name = output_json.name
    for suffix in (
        ".book_learning_materials.generated.json",
        ".generated.json",
        ".json",
    ):
        if name.endswith(suffix):
            return output_json.with_name(f"{name[: -len(suffix)]}.invalid")
    return output_json.with_name(f"{output_json.stem}.invalid")


def select_chapters_by_number(
    chapters: list[dict[str, Any]],
    requested_numbers: list[int],
) -> list[dict[str, Any]]:
    if not requested_numbers:
        raise V2GenerationError(
            "Full-book v2 generation is deferred to Step 34C.4. "
            "Provide one or more --chapter-number values."
        )
    duplicates = sorted(
        number for number, count in Counter(requested_numbers).items() if count > 1
    )
    if duplicates:
        raise V2GenerationError(
            "Duplicate --chapter-number values are not allowed: "
            + ", ".join(str(number) for number in duplicates)
        )
    invalid = [number for number in requested_numbers if number <= 0]
    if invalid:
        raise V2GenerationError(
            "--chapter-number values must be positive integers: "
            + ", ".join(str(number) for number in invalid)
        )

    requested = set(requested_numbers)
    available = {int(chapter["chapter_number"]) for chapter in chapters}
    unknown = [number for number in requested_numbers if number not in available]
    if unknown:
        raise V2GenerationError(
            "Unknown selected chapter number(s): "
            + ", ".join(str(number) for number in unknown)
            + f". Available chapters: {', '.join(str(number) for number in sorted(available))}"
        )
    return [
        chapter
        for chapter in chapters
        if int(chapter["chapter_number"]) in requested
    ]


def source_chunk_record(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": chunk_node_id(chunk),
        "source_pdf": chunk.get("source_pdf"),
        "chapter": chunk.get("chapter"),
        "chapter_number": chunk.get("chapter_number"),
        "section": chunk.get("section"),
        "topic": chunk.get("topic"),
        "content_type": chunk.get("content_type"),
        "page_start": chunk.get("page_start"),
        "page_end": chunk.get("page_end"),
        "is_front_matter": chunk.get("is_front_matter"),
        "text_preview": text_preview(str(chunk.get("text") or "")),
    }


def dedupe_source_chunk_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for record in records:
        node_id = str(record.get("node_id") or "").strip()
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        output.append(record)
    return output


def dedupe_chunks_by_node_id(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for chunk in chunks:
        node_id = chunk_node_id(chunk)
        if not node_id or node_id in seen:
            continue
        seen.add(node_id)
        output.append(chunk)
    return output


def chapter_context_blocks(
    chapter: dict[str, Any],
    *,
    max_chunks: int | None = None,
    max_chars_per_chunk: int | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    available_chunks = [
        chunk
        for chunk in chapter.get("chunks", [])
        if chunk_node_id(chunk) and str(chunk.get("text") or "").strip()
    ]
    if not available_chunks:
        raise V2GenerationError(
            f"No usable clean chunks for chapter {chapter.get('chapter_number')}."
        )

    chunks = dedupe_chunks_by_node_id(available_chunks)
    if max_chunks is not None:
        chunks = chunks[:max_chunks]

    blocks: list[dict[str, Any]] = []
    for chunk in chunks:
        text = str(chunk.get("text") or "")
        if max_chars_per_chunk is not None and len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk].rstrip()
        blocks.append(
            {
                "source_chunk_id": chunk_node_id(chunk),
                "chapter": chunk.get("chapter"),
                "chapter_number": chunk.get("chapter_number"),
                "section": chunk.get("section"),
                "topic": chunk.get("topic"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "text": text,
            }
        )
    allowed_ids = [block["source_chunk_id"] for block in blocks]
    return json.dumps(blocks, indent=2, ensure_ascii=False), chunks, allowed_ids


def v2_schema_rules_text() -> str:
    return f"""
Grounded object: exactly seven keys: text, claim_kind, origin, source_chunk_ids, grounded_in_source_chunk_ids, evidence_spans, reason.
Origins:
- source_grounded: non-empty text, local source_chunk_ids, grounded_in_source_chunk_ids [], reason null.
- pedagogical_generation: non-empty text, source_chunk_ids [], evidence_spans [], reason null. Use only for study_plan, pedagogical_example, practice_question, practice_answer, self_assessment, learner_instruction, misconception_statement.

common_misconceptions.misconception states the FALSE belief, so that .correction can refute it. The
source asserts the truth, never the error, so the misconception is normally pedagogical_generation:
a plausible wrong belief you are naming in order to correct it. Do not attach evidence to it and do
not soften it into a true statement. Use source_grounded for it ONLY if the source explicitly names
the misconception itself. The paired .correction is always source_grounded and must be fully covered
by its evidence spans -- the correction is what the learner is meant to believe.
- insufficient_source_evidence: text null, all source arrays/spans [], non-empty reason.
Evidence spans: exact 4-80 word quotes copied from source; span node_id must be in source_chunk_ids.
Each evidence span is an object with EXACTLY these two keys: {{"node_id": "...", "quote": "..."}}.
The quote key MUST be named "quote" (not "text", "span", or "excerpt"), and its value must be
copied character-for-character from the source chunk named by node_id. Do not paraphrase it.
EVERY source_grounded field, not only high-risk ones, must carry at least one such evidence span.
A source_chunk_ids citation alone is NOT evidence: a source_grounded field with no valid exact
quote is rejected and downgraded to insufficient_source_evidence, losing its text.

EVIDENCE MUST COVER THE WHOLE TEXT, not just part of it. One quote does not license a text that
asserts several things. Before writing a source_grounded text, decide what it asserts, then supply
an evidence span for EVERY assertion in it. If a text makes three claims, quote all three.
Do not bundle an unquotable claim into a sentence beside a quotable one -- that is the most common
way grounded text goes wrong. Concretely:
- Only assert what you can quote. If the source shows the rule but never says learners confuse or
  struggle with it, do not write that they do.
- If the source supports part of what you want to say, narrow the text to that part rather than
  keeping the wider statement.
- If a sentence needs support the source does not give, delete the sentence. Do not soften it,
  generalize it, or infer it.
A source_grounded text asserting more than its spans support is a grounding failure even when every
individual quote is exact, and it is reported as PARTIALLY_SUPPORTED against you.
No citation inheritance: every source_grounded field has local source_chunk_ids.
High-risk kinds: official_rule, task_format, pronunciation_rule, grammar_rule. They must be source_grounded with evidence_spans or insufficient_source_evidence, never pedagogical_generation.
Damaged pronunciation notation -> insufficient_source_evidence. Task modality must be explicit in source. Zero-score/scoring/timing rules -> official_rule only when explicit; otherwise insufficient_source_evidence. Generated study-time estimates -> study_plan + pedagogical_generation.
Return this complete chapter shape with substantive arrays:
chapter_number, chapter_title, source_chunk_ids, estimated_study_time, chapter_summary, learning_objectives, key_terms, core_lessons, worked_examples, common_misconceptions, practice_questions, review_checklist.
Use grounded object claim kinds exactly as field names imply: chapter_summary source_summary; learning_objectives learning_objective; key_terms.meaning definition; core_lessons.explanation source_summary/task_format/official_rule/strategy/factual_explanation/pronunciation_rule/grammar_rule; worked_examples.example pedagogical_example; worked_examples.explanation strategy/factual_explanation/official_rule/task_format; common_misconceptions.misconception misconception_statement; common_misconceptions.correction misconception_correction; practice question/answer practice_question/practice_answer; review_checklist self_assessment.
""".strip()


def build_v2_chapter_prompt(
    *,
    chapter: dict[str, Any],
    context_json: str,
    allowed_ids: list[str],
    model: str,
) -> str:
    return f"""
You are generating the complete learner-facing chapter object for `book_learning_materials.v2`.
This is not a signal response, outline, summary-only response, or compact planning response.

Return valid JSON only. No Markdown. No code fences. No comments outside JSON.
Use only the supplied chapter source chunks. Do not use outside PTE knowledge, web knowledge, or other chapters.

Prompt version: {BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION}
Model: {model}
Chapter number: {chapter["chapter_number"]}
Detected chapter label: {chapter["chapter"]}
Allowed source chunk IDs: {allowed_ids}

{v2_schema_rules_text()}

Generate one complete, substantive chapter package for this chapter only.
The JSON response itself must contain the full chapter object with:
chapter_number, chapter_title, source_chunk_ids, estimated_study_time, chapter_summary, learning_objectives, key_terms, core_lessons, worked_examples, common_misconceptions, practice_questions, review_checklist.

Minimum learner-usefulness counts:
- learning_objectives: at least 3
- key_terms: at least 3
- core_lessons: at least 4
- worked_examples: at least 2
- practice_questions: at least 3
- review_checklist: at least 4
- common_misconceptions: include one or more when safely supported; use insufficient_source_evidence when the source does not safely provide a misconception or correction.

Use multiple distinct source chunks. Source-grounded fields should collectively cite at least four distinct source chunk IDs when four or more are available, otherwise cite every available source chunk ID somewhere in source_grounded objects.
Do not use generic source-reference filler as a complete field, such as "Review the cited source excerpt", "The source excerpt provides the local evidence", "Study the source material", "Read the source and answer the question", or "This lesson is based on the source excerpt".
Make examples, questions, answers, checklist items, and learner instructions useful and self-contained.
Prefer `source_grounded` when the local source explicitly supports the field.
Use `pedagogical_generation` for created examples, learner practice prompts, review checklist items, and estimated study time.
Use `insufficient_source_evidence` when the source does not safely support a factual, official, task-format, scoring, grammar, or pronunciation claim.
Do not infer missing IPA, scoring, timing, task modality, or grammar details. If the source is unclear or damaged, use insufficient_source_evidence.

Complete clean source chunks for this chapter:
{context_json}
""".strip()


def build_v2_repair_prompt(
    *,
    chapter: dict[str, Any],
    context_json: str,
    allowed_ids: list[str],
    raw_response: str | None = None,
    invalid_candidate: dict[str, Any] | None,
    contract_errors: list[dict[str, Any]],
    model: str,
) -> str:
    error_summary = [
        {
            "code": error.get("code"),
            "json_path": error.get("json_path"),
            "message": error.get("message"),
        }
        for error in contract_errors
    ]
    candidate_text = (
        json.dumps(invalid_candidate, indent=2, ensure_ascii=False)
        if invalid_candidate is not None
        else "null"
    )
    raw_text = raw_response if raw_response is not None else ""
    return f"""
Repair the complete chapter package below so it passes the deterministic `book_learning_materials.v2` contract and the substantive chapter validation.

Return valid JSON only. No Markdown. No code fences. No comments outside JSON.
Return a complete replacement chapter object, not a patch, signal, outline, or compact response.
Do not introduce new source evidence. Use only the same supplied source chunks and allowed source IDs.

Prompt version: {BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION}
Model: {model}
Chapter number: {chapter["chapter_number"]}
Detected chapter label: {chapter["chapter"]}
Allowed source chunk IDs: {allowed_ids}

Validation errors to fix:
{json.dumps(error_summary, indent=2, ensure_ascii=False)}

{v2_schema_rules_text()}

Invalid candidate:
{candidate_text}

Original raw model response, if the candidate was not parseable:
{raw_text}

Same selected source excerpts:
{context_json}
""".strip()


def extract_chapter_candidate(parsed: dict[str, Any]) -> dict[str, Any]:
    for key in ("chapter_package", "chapter"):
        value = parsed.get(key)
        if isinstance(value, dict):
            return value
    return parsed


def normalize_evidence_spans(
    spans: Any,
    *,
    source_ids: list[str],
    clean_chunks_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    if not isinstance(spans, list):
        return []
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for span in spans:
        if not isinstance(span, dict):
            continue
        node_id = span.get("node_id", span.get("chunk_id", span.get("id")))
        # Models reliably emit the span object but disagree on the quote key:
        # gpt-5.5 uses "text", others "quote"/"span"/"excerpt". Dropping the
        # unrecognized ones silently discarded valid, exact source quotes and
        # nulled the claims that depended on them. Accepting the aliases is safe
        # because the exact-substring check below still gates acceptance, so a
        # non-quote (e.g. the claim text) can never pass.
        quote = None
        for key in ("quote", "span", "text", "excerpt"):
            candidate = span.get(key)
            if isinstance(candidate, str) and candidate.strip():
                quote = candidate
                break
        if not isinstance(node_id, str) or not node_id.strip():
            continue
        if not isinstance(quote, str) or not quote.strip():
            continue
        node_id = node_id.strip()
        if node_id not in source_ids:
            continue
        normalized_quote = normalize_text(quote)
        words = normalized_quote.split()
        if len(words) < 4 or len(words) > 80:
            continue
        chunk = clean_chunks_lookup.get(node_id)
        if not chunk or normalized_quote not in normalize_text(str(chunk.get("text") or "")):
            continue
        key = (node_id, normalized_quote)
        if key in seen:
            continue
        seen.add(key)
        output.append({"node_id": node_id, "quote": quote})
    return output


def normalize_grounded_content_object(
    value: dict[str, Any],
    *,
    allowed_ids: set[str],
    clean_chunks_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    normalized = {
        "text": value.get("text"),
        "claim_kind": value.get("claim_kind"),
        "origin": value.get("origin"),
        "source_chunk_ids": [],
        "grounded_in_source_chunk_ids": [],
        "evidence_spans": [],
        "reason": value.get("reason"),
    }
    claim_kind = normalized["claim_kind"]
    origin = normalized["origin"]
    source_ids = [
        str(node_id).strip()
        for node_id in value.get("source_chunk_ids", [])
        if str(node_id).strip() in allowed_ids
    ]
    source_ids = unique_preserve_order(source_ids)
    grounded_ids = [
        str(node_id).strip()
        for node_id in value.get("grounded_in_source_chunk_ids", [])
        if str(node_id).strip() in allowed_ids
    ]
    grounded_ids = unique_preserve_order(grounded_ids)
    spans = normalize_evidence_spans(
        value.get("evidence_spans"),
        source_ids=source_ids,
        clean_chunks_lookup=clean_chunks_lookup,
    )

    if origin == "source_grounded":
        normalized["source_chunk_ids"] = source_ids
        normalized["grounded_in_source_chunk_ids"] = []
        normalized["evidence_spans"] = spans
        normalized["reason"] = None
        if not source_ids:
            normalized.update(
                {
                    "text": None,
                    "origin": "insufficient_source_evidence",
                    "source_chunk_ids": [],
                    "grounded_in_source_chunk_ids": [],
                    "evidence_spans": [],
                    "reason": "The model did not provide a valid local source citation for this field.",
                }
            )
        elif not spans:
            # Every source_grounded claim must carry at least one verified exact
            # quote. Previously only HIGH_RISK_CLAIM_KINDS were checked, so any
            # other claim could be labelled "source_grounded" on the strength of a
            # bare chunk citation that was never matched against the source text.
            # A citation is not evidence; without a verified span the claim is not
            # grounded, so it is downgraded rather than carrying a false label.
            high_risk = claim_kind in HIGH_RISK_CLAIM_KINDS
            normalized.update(
                {
                    "text": None,
                    "origin": "insufficient_source_evidence",
                    "source_chunk_ids": [],
                    "grounded_in_source_chunk_ids": [],
                    "evidence_spans": [],
                    "reason": (
                        "The model did not provide a valid exact evidence span "
                        + (
                            "for this high-risk claim."
                            if high_risk
                            else "for this source_grounded claim."
                        )
                    ),
                }
            )
    elif origin == "pedagogical_generation":
        normalized["source_chunk_ids"] = []
        normalized["grounded_in_source_chunk_ids"] = grounded_ids
        normalized["evidence_spans"] = []
        normalized["reason"] = None
        if claim_kind not in PEDAGOGICAL_GENERATION_CLAIM_KINDS:
            normalized.update(
                {
                    "text": None,
                    "origin": "insufficient_source_evidence",
                    "grounded_in_source_chunk_ids": [],
                    "reason": (
                        "The model used pedagogical_generation for a claim kind "
                        "that requires source evidence."
                    ),
                }
            )
    elif origin == "insufficient_source_evidence":
        normalized["text"] = None
        normalized["source_chunk_ids"] = []
        normalized["grounded_in_source_chunk_ids"] = []
        normalized["evidence_spans"] = []
        if not isinstance(normalized["reason"], str) or not normalized["reason"].strip():
            normalized["reason"] = "The local source evidence was insufficient for this field."
    return normalized


def normalize_v2_candidate_for_contract(
    candidate: dict[str, Any],
    *,
    allowed_ids: list[str],
    clean_chunks_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    allowed = set(allowed_ids)
    required_fields = {
        "text",
        "claim_kind",
        "origin",
        "source_chunk_ids",
        "grounded_in_source_chunk_ids",
        "evidence_spans",
        "reason",
    }

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            if required_fields.intersection(value.keys()) and {
                "claim_kind",
                "origin",
            }.issubset(value.keys()):
                return normalize_grounded_content_object(
                    value,
                    allowed_ids=allowed,
                    clean_chunks_lookup=clean_chunks_lookup,
                )
            return {key: walk(child) for key, child in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        return value

    normalized = walk(candidate)
    if not isinstance(normalized, dict):
        return candidate
    if not isinstance(normalized.get("estimated_study_time"), dict):
        normalized["estimated_study_time"] = {
            "text": str(normalized.get("estimated_study_time") or "Use a short generated study session."),
            "claim_kind": "study_plan",
            "origin": "pedagogical_generation",
            "source_chunk_ids": [],
            "grounded_in_source_chunk_ids": [],
            "evidence_spans": [],
            "reason": None,
        }
    for field, fallback_title in [
        ("core_lessons", "Core lesson"),
        ("worked_examples", "Worked example"),
    ]:
        items = normalized.get(field)
        if isinstance(items, list):
            for index, item in enumerate(items, start=1):
                if isinstance(item, dict) and not str(item.get("title") or "").strip():
                    item["title"] = f"{fallback_title} {index}"
    practice_items = normalized.get("practice_questions")
    if isinstance(practice_items, list):
        for item in practice_items:
            if not isinstance(item, dict):
                continue
            question_value = item.get("question")
            if isinstance(question_value, dict) and not {
                "claim_kind",
                "origin",
            }.issubset(question_value.keys()):
                question_value = question_value.get("text")
            if isinstance(question_value, str):
                item["question"] = {
                    "text": question_value,
                    "claim_kind": "practice_question",
                    "origin": "pedagogical_generation",
                    "source_chunk_ids": [],
                    "grounded_in_source_chunk_ids": [],
                    "evidence_spans": [],
                    "reason": None,
                }
            answer_value = item.get("answer")
            if isinstance(answer_value, dict) and not {
                "claim_kind",
                "origin",
            }.issubset(answer_value.keys()):
                answer_value = answer_value.get("text")
            if isinstance(answer_value, str):
                item["answer"] = {
                    "text": answer_value,
                    "claim_kind": "practice_answer",
                    "origin": "pedagogical_generation",
                    "source_chunk_ids": [],
                    "grounded_in_source_chunk_ids": [],
                    "evidence_spans": [],
                    "reason": None,
                }
    checklist_items = normalized.get("review_checklist")
    if isinstance(checklist_items, list):
        normalized["review_checklist"] = [
            {
                "text": item,
                "claim_kind": "self_assessment",
                "origin": "pedagogical_generation",
                "source_chunk_ids": [],
                "grounded_in_source_chunk_ids": [],
                "evidence_spans": [],
                "reason": None,
            }
            if isinstance(item, str)
            else item
            for item in checklist_items
        ]
    if isinstance(normalized.get("source_chunk_ids"), list):
        normalized["source_chunk_ids"] = [
            str(node_id).strip()
            for node_id in normalized["source_chunk_ids"]
            if str(node_id).strip() in allowed
        ]
        normalized["source_chunk_ids"] = unique_preserve_order(
            normalized["source_chunk_ids"]
        )
    return normalized


def is_grounded_content_object(value: Any) -> bool:
    return isinstance(value, dict) and {"text", "claim_kind", "origin"}.issubset(value)


def iter_grounded_content(value: Any, path: str):
    if is_grounded_content_object(value):
        yield path, value
        return
    if isinstance(value, dict):
        for key, child in value.items():
            yield from iter_grounded_content(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_grounded_content(child, f"{path}[{index}]")


def substantive_error(code: str, json_path: str, message: str) -> dict[str, str]:
    return {"code": code, "json_path": json_path, "message": message}


def validate_substantive_v2_chapter(
    *,
    candidate: dict[str, Any],
    allowed_ids: list[str],
) -> list[dict[str, str]]:
    chapter_path = "$.learning_materials.chapters[0]"
    errors: list[dict[str, str]] = []
    for field, (minimum, code) in SUBSTANTIVE_MINIMUMS.items():
        value = candidate.get(field)
        count = len(value) if isinstance(value, list) else 0
        if count < minimum:
            errors.append(
                substantive_error(
                    code,
                    f"{chapter_path}.{field}",
                    f"{field} must contain at least {minimum} item(s); got {count}.",
                )
            )

    used_source_ids: set[str] = set()
    allowed_set = set(allowed_ids)
    for path, grounded_object in iter_grounded_content(candidate, chapter_path):
        text = grounded_object.get("text")
        if isinstance(text, str) and normalize_text(text).lower() in GENERIC_PLACEHOLDER_TEXTS:
            errors.append(
                substantive_error(
                    "GENERIC_PLACEHOLDER_TEXT",
                    f"{path}.text",
                    "Learner-facing text is generic source-reference filler.",
                )
            )
        if grounded_object.get("origin") == "source_grounded":
            for node_id in grounded_object.get("source_chunk_ids") or []:
                if isinstance(node_id, str) and node_id in allowed_set:
                    used_source_ids.add(node_id)

    required_count = min(4, len(allowed_ids))
    if required_count:
        if len(allowed_ids) < 4:
            missing = [node_id for node_id in allowed_ids if node_id not in used_source_ids]
            if missing:
                errors.append(
                    substantive_error(
                        "INSUFFICIENT_SOURCE_CHUNK_COVERAGE",
                        f"{chapter_path}",
                        "source_grounded objects must cite every available source chunk ID; "
                        f"missing: {', '.join(missing)}.",
                    )
                )
        elif len(used_source_ids) < required_count:
            errors.append(
                substantive_error(
                    "INSUFFICIENT_SOURCE_CHUNK_COVERAGE",
                    f"{chapter_path}",
                    "source_grounded objects must cite at least four distinct chapter source IDs; "
                    f"got {len(used_source_ids)}.",
                )
            )
    return errors


def merge_substantive_errors(
    audit: dict[str, Any],
    substantive_errors: list[dict[str, str]],
) -> dict[str, Any]:
    if not substantive_errors:
        return audit
    merged = dict(audit)
    errors = list(merged.get("errors") or []) + substantive_errors
    merged["errors"] = errors
    merged["status"] = "FAIL"
    summary = dict(merged.get("summary") or {})
    errors_by_code = dict(summary.get("errors_by_code") or {})
    for error in substantive_errors:
        code = error["code"]
        errors_by_code[code] = errors_by_code.get(code, 0) + 1
    summary["errors_by_code"] = errors_by_code
    summary["invalid_claim_count"] = int(summary.get("invalid_claim_count") or 0) + len(
        substantive_errors
    )
    merged["summary"] = summary
    return merged


def build_v2_book(
    *,
    slug: str,
    title: str,
    source_pdf: str,
    model: str,
    selected_chapter_numbers: list[int],
    clean_chunks_path: Path,
    chapter_packages: list[dict[str, Any]],
    source_chunks: list[dict[str, Any]],
    audit_status: str = "PENDING",
    generated_at: str | None = None,
    backend: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION,
        "book": {
            "slug": slug,
            "title": title,
            "source_pdf": source_pdf,
        },
        "generation": {
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "pipeline_version": BOOK_LEARNING_MATERIALS_V2_SCHEMA_VERSION,
            "prompt_version": BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION,
            # Which backend produced this, alongside the model it ran. Stored
            # material is reused, so its origin has to be recorded truthfully.
            "backend": backend,
            "model": model,
            "selection_mode": V2_SELECTION_MODE_CHAPTERS,
            "selected_chapter_numbers": selected_chapter_numbers,
            "book_synthesis_performed": False,
            "clean_chunks_path": str(clean_chunks_path),
        },
        "learning_materials": {
            "chapters": chapter_packages,
        },
        "source_chunks": dedupe_source_chunk_records(source_chunks),
        "audit": {
            "status": audit_status,
            "contract_status": audit_status,
        },
    }


def validate_v2_book_dict(
    *,
    book: dict[str, Any],
    clean_chunks_lookup: dict[str, dict[str, Any]],
    clean_chunks_path: Path,
    book_file: Path,
    initial_errors: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    validator = ContractValidator(
        book=book,
        clean_chunks=clean_chunks_lookup,
        book_file=book_file,
        clean_chunks_file=clean_chunks_path,
        initial_errors=initial_errors,
    )
    return validator.validate()


def load_contract_clean_chunk_lookup(
    clean_chunks_path: Path,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    return load_contract_clean_chunks(clean_chunks_path)


def contract_error_message(chapter_number: int, audit: dict[str, Any]) -> str:
    errors = audit.get("errors") or []
    lines = [
        f"Chapter {chapter_number} failed v2 contract validation with {len(errors)} error(s)."
    ]
    for error in errors[:12]:
        lines.append(
            f"- {error.get('code')} | {error.get('json_path')} | {error.get('message')}"
        )
    if len(errors) > 12:
        lines.append(f"- ... {len(errors) - 12} more")
    return "\n".join(lines)


def save_failed_candidate_artifacts(
    *,
    invalid_dir: Path,
    chapter_number: int,
    stage: str,
    raw_response: str | None,
    parsed_candidate: dict[str, Any] | None,
    contract_errors: list[dict[str, Any]] | None,
) -> None:
    invalid_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"chapter_{chapter_number:02d}.{stage}"
    if raw_response is not None:
        atomic_write_text(invalid_dir / f"{prefix}.raw.txt", raw_response)
    if parsed_candidate is not None:
        atomic_write_json(invalid_dir / f"{prefix}.parsed.json", parsed_candidate)
    if contract_errors is not None:
        atomic_write_json(
            invalid_dir / f"{prefix}.contract_errors.json",
            contract_errors,
        )


def build_v2_checkpoint(
    *,
    status: str,
    source_pdf: str,
    clean_chunks_path: Path,
    clean_chunks_hash: str,
    model: str,
    selected_chapter_numbers: list[int],
    chapter_packages: list[dict[str, Any]],
    failed_chapters: list[dict[str, Any]],
    model_call_count: int,
    repair_call_count: int,
) -> dict[str, Any]:
    completed_numbers = [
        int(package["chapter_number"])
        for package in chapter_packages
        if isinstance(package, dict) and package.get("chapter_number") is not None
    ]
    return {
        "schema_version": BOOK_LEARNING_MATERIALS_V2_CHECKPOINT_SCHEMA_VERSION,
        "status": status,
        "source_pdf": source_pdf,
        "clean_chunks_path": str(clean_chunks_path),
        "clean_chunks_sha256": clean_chunks_hash,
        "prompt_version": BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION,
        "model": model,
        "selection_mode": V2_SELECTION_MODE_CHAPTERS,
        "selected_chapter_numbers": selected_chapter_numbers,
        "selected_chapter_count": len(selected_chapter_numbers),
        "completed_chapter_numbers": completed_numbers,
        "completed_chapter_count": len(completed_numbers),
        "chapter_packages": chapter_packages,
        "failed_chapters": failed_chapters,
        "model_call_count": model_call_count,
        "repair_call_count": repair_call_count,
    }


def write_v2_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    atomic_write_json(path, checkpoint)


def load_v2_checkpoint(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise V2GenerationError(f"V2 checkpoint does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise V2GenerationError(f"V2 checkpoint is not valid JSON: {path}: {error}") from error
    if not isinstance(data, dict):
        raise V2GenerationError(f"V2 checkpoint must be a JSON object: {path}")
    return data


def validate_resume_checkpoint(
    *,
    checkpoint: dict[str, Any],
    source_pdf: str,
    clean_chunks_path: Path,
    clean_chunks_hash: str,
    model: str,
    selected_chapter_numbers: list[int],
) -> None:
    expected = {
        "schema_version": BOOK_LEARNING_MATERIALS_V2_CHECKPOINT_SCHEMA_VERSION,
        "source_pdf": source_pdf,
        "clean_chunks_path": str(clean_chunks_path),
        "clean_chunks_sha256": clean_chunks_hash,
        "prompt_version": BOOK_LEARNING_MATERIALS_V2_CHAPTER_PROMPT_VERSION,
        "model": model,
        "selection_mode": V2_SELECTION_MODE_CHAPTERS,
        "selected_chapter_numbers": selected_chapter_numbers,
    }
    for key, expected_value in expected.items():
        actual = checkpoint.get(key)
        if actual != expected_value:
            raise V2GenerationError(
                f"Incompatible v2 checkpoint field {key}: expected {expected_value!r}, got {actual!r}."
            )

    packages = checkpoint.get("chapter_packages")
    if not isinstance(packages, list):
        raise V2GenerationError("Incompatible v2 checkpoint: chapter_packages must be an array.")
    completed = checkpoint.get("completed_chapter_numbers")
    if completed is None:
        completed = [
            package.get("chapter_number")
            for package in packages
            if isinstance(package, dict)
        ]
    if not isinstance(completed, list):
        raise V2GenerationError(
            "Incompatible v2 checkpoint: completed_chapter_numbers must be an array."
        )
    selected_set = set(selected_chapter_numbers)
    if any(number not in selected_set for number in completed):
        raise V2GenerationError(
            "Incompatible v2 checkpoint: completed chapters are outside the selected chapter set."
        )
    selected_positions = {number: index for index, number in enumerate(selected_chapter_numbers)}
    if completed != sorted(completed, key=lambda number: selected_positions[number]):
        raise V2GenerationError(
            "Incompatible v2 checkpoint: completed chapter order does not match selected chapter order."
        )


def format_v2_contract_report(audit: dict[str, Any], output_path: Path) -> str:
    return format_text_report(audit, output_path)


def summarize_selected_chapters(selected_chapters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "chapter_number": int(chapter["chapter_number"]),
            "chapter": chapter.get("chapter"),
            "source_chunk_count": len(chapter.get("chunks") or []),
        }
        for chapter in selected_chapters
    ]
