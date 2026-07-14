import argparse
import json
import os
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "book_claim_evidence.v1"


class BookClaimExtractionError(Exception):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract deterministic whole-book learning-material claims and "
            "resolve their full clean source evidence."
        )
    )
    parser.add_argument("--book-file", required=True)
    parser.add_argument("--clean-chunks-file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def load_json_file(path: Path, label: str) -> Any:
    if not path.exists():
        raise BookClaimExtractionError(f"{label} does not exist: {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BookClaimExtractionError(
            f"{label} is not valid JSON: {path}\nError: {error}"
        ) from error


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BookClaimExtractionError(f"{label} must be a JSON object.")
    return value


def clean_chunk_node_id(chunk: dict[str, Any]) -> str:
    for key in ("node_id", "chunk_id", "id"):
        value = chunk.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise BookClaimExtractionError(
        "Clean chunks JSON contains a chunk without a non-empty ID."
    )


def load_clean_chunk_lookup(path: Path) -> dict[str, dict[str, Any]]:
    artifact = load_json_file(path, "Clean chunks file")

    if isinstance(artifact, dict):
        chunks = artifact.get("chunks") or artifact.get("nodes") or artifact.get("items")
    else:
        chunks = artifact

    if not isinstance(chunks, list) or not chunks:
        raise BookClaimExtractionError(
            "Clean chunks JSON must contain a non-empty chunk collection."
        )

    lookup: OrderedDict[str, dict[str, Any]] = OrderedDict()
    duplicate_ids: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise BookClaimExtractionError(
                "Clean chunks JSON must contain only chunk objects."
            )

        node_id = clean_chunk_node_id(chunk)
        if node_id in lookup:
            duplicate_ids.append(node_id)
            continue
        lookup[node_id] = chunk

    if duplicate_ids:
        raise BookClaimExtractionError(
            "Clean chunks JSON contains duplicate chunk IDs: "
            + ", ".join(sorted(set(duplicate_ids)))
        )

    return dict(lookup)


def validate_book_shape(book: dict[str, Any]) -> None:
    if not isinstance(book.get("book"), dict):
        raise BookClaimExtractionError("Unsupported book JSON: missing book object.")

    if not isinstance(book.get("generation"), dict):
        raise BookClaimExtractionError(
            "Unsupported book JSON: missing generation object."
        )

    learning_materials = book.get("learning_materials")
    has_learning_materials = isinstance(learning_materials, dict)
    has_top_level_packages = isinstance(book.get("chapter_packages"), list)
    if not has_learning_materials and not has_top_level_packages:
        raise BookClaimExtractionError(
            "Unsupported book JSON: expected learning_materials or chapter_packages."
        )


def resolve_clean_chunks_path(
    *,
    book: dict[str, Any],
    explicit_clean_chunks_file: str | None,
) -> Path:
    if explicit_clean_chunks_file:
        return Path(explicit_clean_chunks_file)

    generation = require_object(book.get("generation"), "generation")
    value = generation.get("clean_chunks_path")
    if not isinstance(value, str) or not value.strip():
        raise BookClaimExtractionError(
            "Missing generation.clean_chunks_path; pass --clean-chunks-file."
        )

    return Path(value)


def source_pdf_from_book(book: dict[str, Any]) -> str | None:
    metadata = book.get("book")
    if isinstance(metadata, dict):
        value = metadata.get("source_pdf")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def book_slug_from_book(book: dict[str, Any], source_pdf: str | None) -> str | None:
    metadata = book.get("book")
    if isinstance(metadata, dict):
        value = metadata.get("slug") or metadata.get("book_id")
        if isinstance(value, str) and value.strip():
            return value.strip()

    if source_pdf:
        return Path(source_pdf).stem

    return None


def chapter_packages_with_path(
    book: dict[str, Any]
) -> tuple[list[dict[str, Any]], str]:
    learning_materials = book.get("learning_materials")
    if isinstance(learning_materials, dict):
        chapters = learning_materials.get("chapters")
        if isinstance(chapters, list):
            return [require_object(item, "chapter package") for item in chapters], (
                "$.learning_materials.chapters"
            )

        chapter_packages = learning_materials.get("chapter_packages")
        if isinstance(chapter_packages, list):
            return [
                require_object(item, "chapter package") for item in chapter_packages
            ], "$.learning_materials.chapter_packages"

    chapter_packages = book.get("chapter_packages")
    if isinstance(chapter_packages, list):
        return [require_object(item, "chapter package") for item in chapter_packages], (
            "$.chapter_packages"
        )

    return [], "$.learning_materials.chapters"


def as_nonempty_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


GROUNDED_ORIGINS = {
    "source_grounded",
    "pedagogical_generation",
    "insufficient_source_evidence",
}


def unwrap_grounded(value: Any) -> tuple[str | None, str | None, str | None, Any]:
    """Read a field that may be a v1 plain string or a v2 grounded content object.

    v2 stores {text, claim_kind, origin, source_chunk_ids, evidence_spans, reason}
    where v1 stored a bare string. The v1 string reader returns None for a dict, so
    every v2 grounded object was silently dropped and most of a v2 chapter -- key
    terms, core lessons, worked examples, misconceptions -- was never extracted and
    therefore never semantically audited.

    Returns (text, origin, claim_kind, local_source_ids). origin/claim_kind are None
    for v1 strings, and local_source_ids is None when the caller should fall back to
    the enclosing container's citation.
    """
    if isinstance(value, dict) and value.get("origin") in GROUNDED_ORIGINS:
        return (
            as_nonempty_string(value.get("text")),
            value.get("origin"),
            value.get("claim_kind"),
            value.get("source_chunk_ids"),
        )
    return as_nonempty_string(value), None, None, None


def normalize_source_ids(source_ids: Any, *, claim_id: str) -> list[str]:
    if source_ids is None:
        return []

    if not isinstance(source_ids, list):
        raise BookClaimExtractionError(
            f"{claim_id} source_chunk_ids must be a list."
        )

    normalized: list[str] = []
    for value in source_ids:
        if not isinstance(value, str) or not value.strip():
            raise BookClaimExtractionError(
                f"{claim_id} contains a non-string or empty source chunk ID."
            )
        normalized.append(value.strip())

    duplicates = [item for item, count in Counter(normalized).items() if count > 1]
    if duplicates:
        raise BookClaimExtractionError(
            f"{claim_id} contains duplicate source chunk IDs: "
            + ", ".join(duplicates)
        )

    return normalized


def local_source_ids(container: Any) -> Any:
    if isinstance(container, dict) and "source_chunk_ids" in container:
        return container.get("source_chunk_ids")
    return None


def inherited_source_ids(chapter: dict[str, Any]) -> Any:
    return chapter.get("source_chunk_ids") if "source_chunk_ids" in chapter else None


def citation_origin_for_ids(
    *,
    local_ids: Any = None,
    inherited_ids: Any = None,
    allow_inherited: bool = False,
) -> tuple[str, Any]:
    if local_ids is not None:
        return "local", local_ids

    if allow_inherited and inherited_ids is not None:
        return "inherited_chapter", inherited_ids

    return "none", []


def chapter_claim_id(
    chapter: dict[str, Any], chapter_index: int, suffix: str
) -> str:
    number = chapter.get("chapter_number")
    try:
        numeric = int(number)
    except (TypeError, ValueError):
        numeric = chapter_index + 1
    return f"chapter_{numeric:02d}.{suffix}"


def chapter_number_value(chapter: dict[str, Any]) -> int | None:
    value = chapter.get("chapter_number")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def path_for_chapter(chapters_path: str, chapter_index: int, suffix: str) -> str:
    return f"{chapters_path}[{chapter_index}].{suffix}"


def list_item_text_and_container(item: Any, text_keys: tuple[str, ...]) -> tuple[str | None, Any]:
    if isinstance(item, str):
        return as_nonempty_string(item), None

    if isinstance(item, dict):
        for key in text_keys:
            text = as_nonempty_string(item.get(key))
            if text is not None:
                return text, item

    return None, item


def extract_claims(book: dict[str, Any]) -> list[dict[str, Any]]:
    validate_book_shape(book)

    claims: list[dict[str, Any]] = []
    seen_claim_ids: set[str] = set()

    def add_claim(
        *,
        claim_id: str,
        json_path: str,
        scope: str,
        chapter_number: int | None,
        chapter_title: str | None,
        claim_type: str,
        claim_text: str | None,
        context: dict[str, Any] | None = None,
        citation_origin: str,
        source_ids: Any,
        grounded_origin: str | None = None,
        claim_kind: str | None = None,
    ) -> None:
        if claim_text is None or not isinstance(claim_text, str) or not claim_text.strip():
            return

        if claim_id in seen_claim_ids:
            raise BookClaimExtractionError(f"Duplicate generated claim ID: {claim_id}")
        seen_claim_ids.add(claim_id)

        normalized_ids = normalize_source_ids(source_ids, claim_id=claim_id)
        if not normalized_ids:
            citation_origin = "none"

        if citation_origin not in {"local", "inherited_chapter", "none"}:
            raise BookClaimExtractionError(
                f"{claim_id} has invalid citation_origin: {citation_origin}"
            )

        claims.append(
            {
                "claim_id": claim_id,
                "json_path": json_path,
                "scope": scope,
                "chapter_number": chapter_number,
                "chapter_title": chapter_title,
                "claim_type": claim_type,
                "claim_text": claim_text,
                "context": context or {},
                "citation_origin": citation_origin,
                "source_chunk_ids": normalized_ids,
                "evidence_status": "RESOLVED" if normalized_ids else "NO_CITATION",
                # v2 grounding metadata. Without these the judge cannot tell a
                # claim about the source from deliberately generated pedagogy, and
                # marks invented practice content "unsupported by the source".
                "grounded_origin": grounded_origin,
                "claim_kind": claim_kind,
            }
        )

    learning_materials = book.get("learning_materials")
    if isinstance(learning_materials, dict):
        extract_book_level_claims(learning_materials, add_claim)

    chapters, chapters_path = chapter_packages_with_path(book)
    for chapter_index, chapter in enumerate(chapters):
        extract_chapter_claims(
            chapter=chapter,
            chapter_index=chapter_index,
            chapters_path=chapters_path,
            add_claim=add_claim,
        )

    return claims


def extract_book_level_claims(learning_materials: dict[str, Any], add_claim) -> None:
    def book_claim(
        *,
        claim_id: str,
        json_path: str,
        claim_type: str,
        claim_text: str | None,
        context: dict[str, Any] | None = None,
        container: Any = None,
    ) -> None:
        origin, ids = citation_origin_for_ids(local_ids=local_source_ids(container))
        add_claim(
            claim_id=claim_id,
            json_path=json_path,
            scope="book",
            chapter_number=None,
            chapter_title=None,
            claim_type=claim_type,
            claim_text=claim_text,
            context=context,
            citation_origin=origin,
            source_ids=ids,
        )

    for field, claim_type in [
        ("book_overview", "book_overview"),
        ("summary", "book_summary"),
        ("overview", "book_overview"),
    ]:
        if field in learning_materials:
            book_claim(
                claim_id=f"book.{field}",
                json_path=f"$.learning_materials.{field}",
                claim_type=claim_type,
                claim_text=as_nonempty_string(learning_materials.get(field)),
                container=learning_materials,
            )

    for index, item in enumerate(learning_materials.get("who_this_is_for") or []):
        text, container = list_item_text_and_container(item, ("text", "description"))
        book_claim(
            claim_id=f"book.who_this_is_for.{index}",
            json_path=f"$.learning_materials.who_this_is_for[{index}]",
            claim_type="audience_item",
            claim_text=text,
            container=container,
        )

    for index, item in enumerate(learning_materials.get("how_to_use_this_book") or []):
        text, container = list_item_text_and_container(item, ("text", "instruction"))
        book_claim(
            claim_id=f"book.how_to_use_this_book.{index}",
            json_path=f"$.learning_materials.how_to_use_this_book[{index}]",
            claim_type="usage_instruction",
            claim_text=text,
            container=container,
        )

    for index, item in enumerate(learning_materials.get("study_plan") or []):
        if not isinstance(item, dict):
            continue
        week = item.get("week")
        focus = as_nonempty_string(item.get("focus"))
        context = {
            key: value
            for key, value in {
                "week": week,
                "chapters": item.get("chapters"),
            }.items()
            if value is not None
        }
        book_claim(
            claim_id=f"book.study_plan.{index}.focus",
            json_path=f"$.learning_materials.study_plan[{index}].focus",
            claim_type="study_plan_focus",
            claim_text=focus,
            context=context,
            container=item,
        )
        for activity_index, activity in enumerate(item.get("activities") or []):
            text, container = list_item_text_and_container(
                activity, ("text", "activity", "description")
            )
            activity_context = {
                key: value
                for key, value in {
                    "week": week,
                    "focus": focus,
                    "chapters": item.get("chapters"),
                }.items()
                if value is not None
            }
            book_claim(
                claim_id=f"book.study_plan.{index}.activities.{activity_index}",
                json_path=(
                    "$.learning_materials.study_plan"
                    f"[{index}].activities[{activity_index}]"
                ),
                claim_type="study_plan_activity",
                claim_text=text,
                context=activity_context,
                container=container or item,
            )

    for index, item in enumerate(learning_materials.get("global_key_terms") or []):
        if not isinstance(item, dict):
            continue
        book_claim(
            claim_id=f"book.global_key_terms.{index}.meaning",
            json_path=f"$.learning_materials.global_key_terms[{index}].meaning",
            claim_type="global_key_term_definition",
            claim_text=as_nonempty_string(item.get("meaning")),
            context={
                key: value
                for key, value in {
                    "term": item.get("term"),
                    "chapter_numbers": item.get("chapter_numbers"),
                }.items()
                if value is not None
            },
            container=item,
        )

    final_review = learning_materials.get("final_review")
    if isinstance(final_review, dict):
        book_claim(
            claim_id="book.final_review.summary",
            json_path="$.learning_materials.final_review.summary",
            claim_type="final_review_summary",
            claim_text=as_nonempty_string(final_review.get("summary")),
            container=final_review,
        )
        for index, question in enumerate(final_review.get("questions") or []):
            text, container = list_item_text_and_container(question, ("text", "question"))
            book_claim(
                claim_id=f"book.final_review.questions.{index}",
                json_path=f"$.learning_materials.final_review.questions[{index}]",
                claim_type="final_review_question",
                claim_text=text,
                container=container or final_review,
            )


def extract_chapter_claims(
    *,
    chapter: dict[str, Any],
    chapter_index: int,
    chapters_path: str,
    add_claim,
) -> None:
    chapter_number = chapter_number_value(chapter)
    chapter_title = (
        str(chapter.get("chapter_title")).strip()
        if chapter.get("chapter_title") is not None
        else None
    )
    inherited_ids = inherited_source_ids(chapter)

    summary_text, summary_origin, summary_kind, summary_ids = unwrap_grounded(
        chapter.get("chapter_summary")
    )
    origin, ids = citation_origin_for_ids(
        local_ids=summary_ids,
        inherited_ids=inherited_ids,
        allow_inherited=True,
    )
    add_claim(
        claim_id=chapter_claim_id(chapter, chapter_index, "chapter_summary"),
        json_path=path_for_chapter(chapters_path, chapter_index, "chapter_summary"),
        scope="chapter",
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        claim_type="chapter_summary",
        claim_text=summary_text,
        citation_origin=origin,
        source_ids=ids,
        grounded_origin=summary_origin,
        claim_kind=summary_kind,
    )

    for index, item in enumerate(chapter.get("learning_objectives") or []):
        text, container = list_item_text_and_container(
            item, ("text", "objective", "description")
        )
        _t, g_origin, g_kind, g_ids = unwrap_grounded(item)
        origin, ids = citation_origin_for_ids(
            local_ids=g_ids if g_ids is not None else local_source_ids(container),
            inherited_ids=inherited_ids,
            allow_inherited=True,
        )
        add_claim(
            claim_id=chapter_claim_id(chapter, chapter_index, f"learning_objectives.{index}"),
            json_path=path_for_chapter(
                chapters_path, chapter_index, f"learning_objectives[{index}]"
            ),
            scope="chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            claim_type="learning_objective",
            claim_text=text,
            citation_origin=origin,
            source_ids=ids,
            grounded_origin=g_origin,
            claim_kind=g_kind,
        )

    for index, item in enumerate(chapter.get("key_terms") or []):
        if not isinstance(item, dict):
            continue
        m_text, m_origin, m_kind, m_ids = unwrap_grounded(item.get("meaning"))
        origin, ids = citation_origin_for_ids(
            local_ids=m_ids if m_ids is not None else local_source_ids(item)
        )
        add_claim(
            claim_id=chapter_claim_id(chapter, chapter_index, f"key_terms.{index}.meaning"),
            json_path=path_for_chapter(
                chapters_path, chapter_index, f"key_terms[{index}].meaning"
            ),
            scope="chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            claim_type="key_term_definition",
            claim_text=m_text,
            context={"term": item.get("term")} if item.get("term") is not None else {},
            citation_origin=origin,
            source_ids=ids,
            grounded_origin=m_origin,
            claim_kind=m_kind,
        )

    for index, item in enumerate(chapter.get("core_lessons") or []):
        if not isinstance(item, dict):
            continue
        e_text, e_origin, e_kind, e_ids = unwrap_grounded(item.get("explanation"))
        origin, ids = citation_origin_for_ids(
            local_ids=e_ids if e_ids is not None else local_source_ids(item)
        )
        add_claim(
            claim_id=chapter_claim_id(
                chapter, chapter_index, f"core_lessons.{index}.explanation"
            ),
            json_path=path_for_chapter(
                chapters_path, chapter_index, f"core_lessons[{index}].explanation"
            ),
            scope="chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            claim_type="core_lesson_explanation",
            claim_text=e_text,
            context={"title": item.get("title")} if item.get("title") is not None else {},
            citation_origin=origin,
            source_ids=ids,
            grounded_origin=e_origin,
            claim_kind=e_kind,
        )

    for index, item in enumerate(chapter.get("worked_examples") or []):
        if not isinstance(item, dict):
            continue
        context = {"title": item.get("title")} if item.get("title") is not None else {}
        for field, claim_type in [
            ("example", "worked_example_content"),
            ("explanation", "worked_example_explanation"),
        ]:
            f_text, f_origin, f_kind, f_ids = unwrap_grounded(item.get(field))
            origin, ids = citation_origin_for_ids(
                local_ids=f_ids if f_ids is not None else local_source_ids(item)
            )
            add_claim(
                claim_id=chapter_claim_id(
                    chapter, chapter_index, f"worked_examples.{index}.{field}"
                ),
                json_path=path_for_chapter(
                    chapters_path, chapter_index, f"worked_examples[{index}].{field}"
                ),
                scope="chapter",
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                claim_type=claim_type,
                claim_text=f_text,
                context=context,
                citation_origin=origin,
                source_ids=ids,
                grounded_origin=f_origin,
                claim_kind=f_kind,
            )

    for index, item in enumerate(chapter.get("common_misconceptions") or []):
        if not isinstance(item, dict):
            continue
        for field, claim_type in [
            ("misconception", "misconception_statement"),
            ("correction", "misconception_correction"),
        ]:
            f_text, f_origin, f_kind, f_ids = unwrap_grounded(item.get(field))
            origin, ids = citation_origin_for_ids(
                local_ids=f_ids if f_ids is not None else local_source_ids(item)
            )
            add_claim(
                claim_id=chapter_claim_id(
                    chapter, chapter_index, f"common_misconceptions.{index}.{field}"
                ),
                json_path=path_for_chapter(
                    chapters_path,
                    chapter_index,
                    f"common_misconceptions[{index}].{field}",
                ),
                scope="chapter",
                chapter_number=chapter_number,
                chapter_title=chapter_title,
                claim_type=claim_type,
                claim_text=f_text,
                citation_origin=origin,
                source_ids=ids,
                grounded_origin=f_origin,
                claim_kind=f_kind,
            )

    for index, item in enumerate(chapter.get("practice_questions") or []):
        if not isinstance(item, dict):
            continue
        a_text, a_origin, a_kind, a_ids = unwrap_grounded(item.get("answer"))
        origin, ids = citation_origin_for_ids(
            local_ids=a_ids if a_ids is not None else local_source_ids(item)
        )
        add_claim(
            claim_id=chapter_claim_id(
                chapter, chapter_index, f"practice_questions.{index}.answer"
            ),
            json_path=path_for_chapter(
                chapters_path, chapter_index, f"practice_questions[{index}].answer"
            ),
            scope="chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            claim_type="practice_answer",
            claim_text=a_text,
            context={
                "question": item.get("question")
            }
            if item.get("question") is not None
            else {},
            citation_origin=origin,
            source_ids=ids,
        )

    for index, item in enumerate(chapter.get("review_checklist") or []):
        text, container = list_item_text_and_container(item, ("text", "item"))
        _t, c_origin, c_kind, c_ids = unwrap_grounded(item)
        origin, ids = citation_origin_for_ids(
            local_ids=c_ids if c_ids is not None else local_source_ids(container),
            inherited_ids=inherited_ids,
            allow_inherited=True,
        )
        add_claim(
            claim_id=chapter_claim_id(chapter, chapter_index, f"review_checklist.{index}"),
            json_path=path_for_chapter(
                chapters_path, chapter_index, f"review_checklist[{index}]"
            ),
            scope="chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            claim_type="review_checklist_item",
            claim_text=text,
            citation_origin=origin,
            source_ids=ids,
        )

    if "estimated_study_time_minutes" in chapter:
        value = chapter.get("estimated_study_time_minutes")
        if isinstance(value, int | float) and not isinstance(value, bool):
            text = f"Estimated study time: {value:g} minutes."
        elif isinstance(value, str) and value.strip():
            text = f"Estimated study time: {value.strip()} minutes."
        else:
            text = None

        add_claim(
            claim_id=chapter_claim_id(
                chapter, chapter_index, "estimated_study_time_minutes"
            ),
            json_path=path_for_chapter(
                chapters_path, chapter_index, "estimated_study_time_minutes"
            ),
            scope="chapter",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            claim_type="estimated_study_time",
            claim_text=text,
            citation_origin="none",
            source_ids=[],
        )


def evidence_record(node_id: str, chunk: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "source_pdf",
        "source_type",
        "book_id",
        "book_title",
        "chapter_number",
        "chapter",
        "section",
        "section_page_start",
        "section_source",
        "section_confidence",
        "section_level",
        "topic",
        "content_type",
        "page_start",
        "page_end",
        "is_front_matter",
        "metadata",
    ]
    record = {"node_id": node_id}
    for key in keys:
        if key in chunk:
            record[key] = chunk.get(key)
    record["text"] = chunk.get("text")
    return record


def resolve_evidence(
    *,
    claims: list[dict[str, Any]],
    clean_lookup: dict[str, dict[str, Any]],
    expected_source_pdf: str | None,
) -> list[dict[str, Any]]:
    evidence: OrderedDict[str, dict[str, Any]] = OrderedDict()
    errors: list[str] = []

    for claim in claims:
        for node_id in claim["source_chunk_ids"]:
            chunk = clean_lookup.get(node_id)
            if chunk is None:
                errors.append(
                    f"{claim['claim_id']} references unresolved source ID: {node_id}"
                )
                continue

            text = chunk.get("text")
            if not isinstance(text, str) or not text.strip():
                errors.append(
                    f"{claim['claim_id']} references empty evidence text: {node_id}"
                )

            chunk_source_pdf = chunk.get("source_pdf")
            if (
                expected_source_pdf
                and isinstance(chunk_source_pdf, str)
                and chunk_source_pdf.strip()
                and chunk_source_pdf.strip() != expected_source_pdf
            ):
                errors.append(
                    f"{claim['claim_id']} source PDF mismatch for {node_id}: "
                    f"{chunk_source_pdf} != {expected_source_pdf}"
                )

            claim_chapter = claim.get("chapter_number")
            chunk_chapter = chunk.get("chapter_number")
            if (
                claim.get("scope") == "chapter"
                and claim_chapter is not None
                and chunk_chapter is not None
            ):
                try:
                    chunk_chapter_int = int(chunk_chapter)
                except (TypeError, ValueError):
                    chunk_chapter_int = None
                if chunk_chapter_int is not None and int(claim_chapter) != chunk_chapter_int:
                    errors.append(
                        f"{claim['claim_id']} chapter mismatch for {node_id}: "
                        f"{chunk_chapter} != {claim_chapter}"
                    )

            if node_id not in evidence:
                evidence[node_id] = evidence_record(node_id, chunk)

    if errors:
        raise BookClaimExtractionError("\n".join(errors))

    return list(evidence.values())


def build_summary(claims: list[dict[str, Any]], evidence_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    claims_by_type = Counter(claim["claim_type"] for claim in claims)
    return {
        "claim_count": len(claims),
        "book_claim_count": sum(1 for claim in claims if claim["scope"] == "book"),
        "chapter_claim_count": sum(
            1 for claim in claims if claim["scope"] == "chapter"
        ),
        "locally_cited_claim_count": sum(
            1 for claim in claims if claim["citation_origin"] == "local"
        ),
        "inherited_citation_claim_count": sum(
            1 for claim in claims if claim["citation_origin"] == "inherited_chapter"
        ),
        "uncited_claim_count": sum(
            1 for claim in claims if claim["citation_origin"] == "none"
        ),
        "unique_evidence_chunk_count": len(evidence_chunks),
        "unresolved_source_id_count": 0,
        "duplicate_clean_chunk_id_count": 0,
        "empty_evidence_text_count": 0,
        "document_mismatch_count": 0,
        "chapter_mismatch_count": 0,
        "claims_by_type": dict(sorted(claims_by_type.items())),
    }


def extract_book_claim_evidence(
    *,
    book_file: str | Path,
    clean_chunks_file: str | Path | None = None,
) -> dict[str, Any]:
    book_path = Path(book_file)
    book = require_object(load_json_file(book_path, "Book file"), "Book file")
    validate_book_shape(book)

    clean_path = (
        Path(clean_chunks_file)
        if clean_chunks_file is not None
        else resolve_clean_chunks_path(
            book=book,
            explicit_clean_chunks_file=None,
        )
    )
    clean_lookup = load_clean_chunk_lookup(clean_path)

    claims = extract_claims(book)
    source_pdf = source_pdf_from_book(book)
    evidence_chunks = resolve_evidence(
        claims=claims,
        clean_lookup=clean_lookup,
        expected_source_pdf=source_pdf,
    )

    generation = require_object(book.get("generation"), "generation")
    output = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "input": {
            "book_file": str(book_path),
            "clean_chunks_file": str(clean_path),
            "source_pdf": source_pdf,
            "book_slug": book_slug_from_book(book, source_pdf),
            "pipeline_version": generation.get("pipeline_version"),
        },
        "summary": build_summary(claims, evidence_chunks),
        "claims": claims,
        "evidence_chunks": evidence_chunks,
        "errors": [],
        "warnings": [],
    }
    return output


def format_report(result: dict[str, Any], output_path: Path) -> str:
    summary = result["summary"]
    input_info = result["input"]
    lines = [
        "BOOK CLAIM EVIDENCE REPORT",
        f"Book file: {input_info.get('book_file')}",
        f"Clean chunks file: {input_info.get('clean_chunks_file')}",
        f"Source PDF: {input_info.get('source_pdf')}",
        f"Book slug: {input_info.get('book_slug')}",
        f"Status: {result.get('status')}",
        "",
        "CLAIM SUMMARY",
        f"Total claims: {summary['claim_count']}",
        f"Book-level claims: {summary['book_claim_count']}",
        f"Chapter-level claims: {summary['chapter_claim_count']}",
        f"Locally cited claims: {summary['locally_cited_claim_count']}",
        f"Inherited-citation claims: {summary['inherited_citation_claim_count']}",
        f"Uncited claims: {summary['uncited_claim_count']}",
        f"Unique full evidence chunks: {summary['unique_evidence_chunk_count']}",
        "",
        "CLAIMS BY TYPE",
    ]
    for claim_type, count in summary["claims_by_type"].items():
        lines.append(f"{claim_type}: {count}")
    lines.extend(
        [
            "",
            "VALIDATION",
            f"Unresolved source IDs: {summary['unresolved_source_id_count']}",
            f"Duplicate clean chunk IDs: {summary['duplicate_clean_chunk_id_count']}",
            f"Empty evidence texts: {summary['empty_evidence_text_count']}",
            f"Document mismatches: {summary['document_mismatch_count']}",
            f"Chapter mismatches: {summary['chapter_mismatch_count']}",
            "",
            "OUTPUT",
            f"JSON file: {output_path}",
            "",
        ]
    )
    return "\n".join(lines)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def ensure_can_write(paths: list[Path], overwrite: bool) -> None:
    if overwrite:
        return
    existing = [path for path in paths if path.exists()]
    if existing:
        raise BookClaimExtractionError(
            "Output already exists. Use --overwrite to replace: "
            + ", ".join(str(path) for path in existing)
        )


def run_cli(args: argparse.Namespace) -> int:
    book_path = Path(args.book_file)
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else None

    if not args.dry_run:
        ensure_can_write(
            [path for path in [output_path, report_path] if path is not None],
            args.overwrite,
        )

    book = require_object(load_json_file(book_path, "Book file"), "Book file")
    validate_book_shape(book)
    clean_path = resolve_clean_chunks_path(
        book=book,
        explicit_clean_chunks_file=args.clean_chunks_file,
    )
    clean_lookup = load_clean_chunk_lookup(clean_path)

    if args.dry_run:
        chapters, _chapters_path = chapter_packages_with_path(book)
        print(f"Book loaded: {book_path}")
        print(f"Resolved clean chunks: {clean_path}")
        print(f"Clean chunks loaded: {clean_path}")
        print(f"Chapter packages found: {len(chapters)}")
        print(f"Output would be written: {output_path}")
        if report_path is not None:
            print(f"Report would be written: {report_path}")
        print("No output files written.")
        print("No model calls.")
        return 0

    claims = extract_claims(book)
    source_pdf = source_pdf_from_book(book)
    evidence_chunks = resolve_evidence(
        claims=claims,
        clean_lookup=clean_lookup,
        expected_source_pdf=source_pdf,
    )
    generation = require_object(book.get("generation"), "generation")
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "input": {
            "book_file": str(book_path),
            "clean_chunks_file": str(clean_path),
            "source_pdf": source_pdf,
            "book_slug": book_slug_from_book(book, source_pdf),
            "pipeline_version": generation.get("pipeline_version"),
        },
        "summary": build_summary(claims, evidence_chunks),
        "claims": claims,
        "evidence_chunks": evidence_chunks,
        "errors": [],
        "warnings": [],
    }

    chapters, _chapters_path = chapter_packages_with_path(book)
    formatted = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    atomic_write_text(output_path, formatted)

    if report_path is not None:
        atomic_write_text(report_path, format_report(result, output_path))

    summary = result["summary"]
    print(f"Book loaded: {book_path}")
    print(f"Clean chunks loaded: {clean_path}")
    print(f"Chapter packages found: {len(chapters)}")
    print(f"Claims extracted: {summary['claim_count']}")
    print(f"Locally cited claims: {summary['locally_cited_claim_count']}")
    print(f"Inherited-citation claims: {summary['inherited_citation_claim_count']}")
    print(f"Uncited claims: {summary['uncited_claim_count']}")
    print(f"Unique full evidence chunks: {summary['unique_evidence_chunk_count']}")
    print("Evidence validation: PASS")
    print(f"Output written: {output_path}")
    if report_path is not None:
        print(f"Report written: {report_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_cli(args)
    except BookClaimExtractionError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
