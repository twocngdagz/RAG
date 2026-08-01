"""Claims the producer builds must satisfy the real source contract.

Checked THROUGH `validate_book_contract`, not by reading the dictionaries back.
The previous builder produced claims that looked right field by field and were
rejected wholesale — inspecting its output would have agreed with it.

    python test_math_claim_grounding.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import math_claim_grounding as grounding
from book_learning_materials_contract import validate_book_contract
from book_learning_materials_v2_generation import PEDAGOGICAL_GENERATION_CLAIM_KINDS

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


PAGE_TEXT = (
    "Four quarters make one whole. Eleven quarters group into two wholes and three quarters. "
    "A fraction shows a division of a whole into equal parts."
)
CHUNKS = [{"node_id": "math5a:p31", "source_pdf": "Math 5A", "chapter_number": 3, "text": PAGE_TEXT}]

SENTENCE = "Four quarters make one whole."
LONGER = "Eleven quarters group into two wholes and three quarters."
UNFOUNDED = "Every fraction is secretly a decimal that hides its own denominator."


def contract_status(claims: dict) -> dict:
    """Run one built chapter through the real contract."""
    book = {
        "schema_version": "book_learning_materials.v2",
        "book": {"slug": "math5a", "title": "Math 5A", "source_pdf": "Math 5A"},
        "generation": {"pipeline_version": "book_learning_materials.v2", "run_id": "test"},
        "audit": {"status": "PASS"},
        "source_chunks": [{"node_id": c["node_id"], "text": c["text"]} for c in CHUNKS],
        "learning_materials": {"global_key_terms": [], "chapters": [claims]},
    }

    workspace = Path(tempfile.mkdtemp())
    book_file = workspace / "book.json"
    chunks_file = workspace / "chunks.json"
    book_file.write_text(json.dumps(book))
    chunks_file.write_text(json.dumps(CHUNKS))

    return validate_book_contract(book_file=book_file, clean_chunks_file=chunks_file)


print("the origin comes from the KIND first")

for field, expected in [
    ("estimated_study_time", "pedagogical_generation"),
    ("practice_question", "pedagogical_generation"),
    ("practice_answer", "pedagogical_generation"),
    ("review_checklist", "pedagogical_generation"),
    ("misconception", "pedagogical_generation"),
    ("worked_examples", "pedagogical_generation"),
]:
    # The text is lifted verbatim from the page, so a text-matching rule would
    # call every one of these grounded. None of them is the book's claim.
    claim = grounding.build_claim(f"{SENTENCE} {LONGER}", field, CHUNKS)
    check(f"{field} is {expected} even when the source says the same words", claim["origin"] == expected, claim["origin"])
    check(f"{field} cites no direct source chunks", claim["source_chunk_ids"] == [], str(claim["source_chunk_ids"]))
    check(f"{field} carries no evidence spans", claim["evidence_spans"] == [], str(claim["evidence_spans"]))

check(
    "the generated-kind list mirrors the v2 rules",
    grounding.GENERATED_CLAIM_KINDS == PEDAGOGICAL_GENERATION_CLAIM_KINDS,
    str(grounding.GENERATED_CLAIM_KINDS ^ PEDAGOGICAL_GENERATION_CLAIM_KINDS),
)


print("\ngrounding requires the WHOLE claim, not its opening")

covered = grounding.build_claim(f"{SENTENCE} {LONGER}", "core_lessons", CHUNKS)
check("a fully covered claim is grounded", covered["origin"] == "source_grounded", covered["origin"])
check("every sentence produced a span", len(covered["evidence_spans"]) == 2, str(len(covered["evidence_spans"])))
check("spans quote the source", all(s["quote"] for s in covered["evidence_spans"]))
check("the generated list stays empty", covered["grounded_in_source_chunk_ids"] == [])

partial = grounding.build_claim(f"{SENTENCE} {UNFOUNDED}", "core_lessons", CHUNKS)
check(
    "a claim whose opening matches but whose assertion does not is refused",
    partial["origin"] == "insufficient_source_evidence",
    partial["origin"],
)
check("its text is null, not the unsupported wording", partial["text"] is None, str(partial["text"]))


print("\nclean chunks preserve the source")

pages = [{"page": 31, "markdown": PAGE_TEXT, "source_pdf": "Math 5A"}]
chunks = grounding.clean_chunks_from_pages(pages, "math5a", 3)

check("the text is unchanged", chunks[0]["text"] == PAGE_TEXT, chunks[0]["text"][:60])
check("it is not lowercased", chunks[0]["text"] != PAGE_TEXT.lower())
check("ids are derived from the page", chunks[0]["node_id"] == "math5a:p31", chunks[0]["node_id"])
check(
    "the same pages give the same chunks",
    grounding.clean_chunks_from_pages(pages, "math5a", 3) == chunks,
)


print("\nthe built chapter satisfies the real contract")

chapter = {
    "chapter_number": 3,
    "chapter_title": "Fractions",
    "source_chunk_ids": ["math5a:p31"],
    "estimated_study_time": grounding.build_claim("Two hours of study for this chapter.", "estimated_study_time", CHUNKS),
    "chapter_summary": grounding.build_claim(f"{SENTENCE} {LONGER}", "chapter_summary", CHUNKS),
    "learning_objectives": [grounding.build_claim(LONGER, "learning_objectives", CHUNKS)],
    "key_terms": [{"term": "quarter", "meaning": grounding.build_claim(SENTENCE, "key_terms", CHUNKS)}],
    "core_lessons": [{"title": "Fractions", "explanation": grounding.build_claim(LONGER, "core_lessons", CHUNKS)}],
    "worked_examples": [{"title": "Example", "example": grounding.build_claim(SENTENCE, "worked_examples", CHUNKS),
                          "explanation": grounding.build_claim(LONGER, "core_lessons", CHUNKS)}],
    "common_misconceptions": [{"misconception": grounding.build_claim(SENTENCE, "misconception", CHUNKS),
                               "correction": grounding.build_claim(LONGER, "correction", CHUNKS)}],
    "practice_questions": [{"question": grounding.build_claim(SENTENCE, "practice_question", CHUNKS),
                            "answer": grounding.build_claim(LONGER, "practice_answer", CHUNKS)}],
    "review_checklist": [grounding.build_claim(SENTENCE, "review_checklist", CHUNKS)],
}

audit = contract_status(chapter)
errors = audit.get("errors") or []

check("no unknown claim kind", not any(e.get("code") == "INVALID_CLAIM_KIND" for e in errors), str(errors[:2]))
check(
    "no contradictory origin fields",
    not any(e.get("code") == "INVALID_ORIGIN_FIELD_COMBINATION" for e in errors),
    str([e for e in errors if e.get("code") == "INVALID_ORIGIN_FIELD_COMBINATION"][:1]),
)
check("no missing pipeline version", not any(e.get("code") == "PIPELINE_VERSION_MISMATCH" for e in errors), str(errors[:1]))

for error in errors[:5]:
    print(f"      contract said: {error.get('code')} {str(error.get('message'))[:70]}")


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "claims are grounded honestly, or not at all")
raise SystemExit(1 if fails else 0)
