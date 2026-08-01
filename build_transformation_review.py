"""Prepare the transformation review for one chapter, and report what it costs.

Emits a manifest with every candidate transformation pinned -- claim path, the
exact wording's hash, the source revision, the chunks it must be judged against
-- and NO verdicts. A reviewer fills those in. Nothing here decides whether a
rewording is faithful; that is the one judgement this whole mechanism exists to
route to a person.

Run before review to produce the worksheet, and again after the source changes
to see which approvals the change invalidated.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import build_math_grounded_base as builder
import math_claim_grounding as grounding
import transformation_review

ROOT = Path(__file__).resolve().parent


def candidates(
    chapter_number: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Claims needing review, claims that are generated, and the chapter's chunks.

    A candidate is a claim whose kind could be grounded but whose words are not
    in the source. Generated kinds are never candidates -- a practice question
    the model wrote is not a transformation of anything, and putting it in front
    of a reviewer would invite an approval that means nothing.
    """
    pages = builder.load_pages()
    chapter = next(
        c for c in builder.chapters(pages) if c["chapter_number"] == chapter_number
    )
    chapter_pages = [
        page for page in pages if chapter["first_page"] <= page["page"] <= chapter["last_page"]
    ]
    chunks = grounding.clean_chunks_from_pages(chapter_pages, builder.SLUG, chapter_number)

    source = Path(f"output/{builder.SLUG}.chapter{chapter_number:02d}.book_learning_materials.json")
    materials = json.loads(source.read_text(encoding="utf-8"))
    chapter_doc = materials["learning_materials"]["chapters"][0]

    needs_review: list[dict[str, Any]] = []
    generated: list[dict[str, Any]] = []

    for claim_path, field, text in _claims(chapter_doc, chapter_number):
        claim = grounding.build_claim(text, field, chunks)
        record = {"claim_path": claim_path, "field": field, "text": text}

        if claim["origin"] == "pedagogical_generation":
            generated.append(record)
        elif claim["origin"] == "insufficient_source_evidence":
            needs_review.append(record)

    return needs_review, generated, chunks


def _claims(chapter: dict[str, Any], number: int) -> list[tuple[str, str, str]]:
    """Every claim in the chapter as (path, field, text), in document order.

    Paths are positional and dotted, matching the export manifest's addressing,
    so an approval and an export mapping name the same claim the same way.
    """
    prefix = f"chapter{number:02d}"
    out: list[tuple[str, str, str]] = [
        (f"{prefix}.estimated_study_time", "estimated_study_time", chapter["estimated_study_time"]["text"]),
        (f"{prefix}.chapter_summary", "chapter_summary", chapter["chapter_summary"]["text"]),
    ]

    for index, objective in enumerate(chapter["learning_objectives"]):
        out.append((f"{prefix}.learning_objectives.{index}", "learning_objectives", objective["text"]))

    for index, term in enumerate(chapter["key_terms"]):
        out.append((f"{prefix}.key_terms.{index}.meaning", "key_terms", term["meaning"]["text"]))

    for index, lesson in enumerate(chapter["core_lessons"]):
        out.append((f"{prefix}.core_lessons.{index}.explanation", "core_lessons", lesson["explanation"]["text"]))

    for index, example in enumerate(chapter["worked_examples"]):
        out.append((f"{prefix}.worked_examples.{index}.example", "worked_example", example["example"]["text"]))
        out.append((f"{prefix}.worked_examples.{index}.explanation", "worked_example_explanation", example["explanation"]["text"]))

    for index, item in enumerate(chapter["common_misconceptions"]):
        out.append((f"{prefix}.common_misconceptions.{index}.misconception", "misconception", item["misconception"]["text"]))
        out.append((f"{prefix}.common_misconceptions.{index}.correction", "correction", item["correction"]["text"]))

    for index, question in enumerate(chapter["practice_questions"]):
        out.append((f"{prefix}.practice_questions.{index}.question", "practice_question", question["question"]["text"]))
        out.append((f"{prefix}.practice_questions.{index}.answer", "practice_answer", question["answer"]["text"]))

    for index, entry in enumerate(chapter["review_checklist"]):
        out.append((f"{prefix}.review_checklist.{index}", "review_checklist", entry["text"]))

    return out


def worksheet(chapter_number: int) -> dict[str, Any]:
    """The manifest a reviewer completes, with verdicts left empty."""
    needs_review, generated, chunks = candidates(chapter_number)
    revision = transformation_review.source_revision(chunks)

    return {
        "schema_version": transformation_review.REVIEW_SCHEMA_VERSION,
        "chapter_number": chapter_number,
        "source_content_revision": revision,
        "generated_claim_count": len(generated),
        "approvals": [
            {
                "claim_path": candidate["claim_path"],
                "claim_hash": transformation_review.claim_hash(candidate["text"]),
                "source_content_revision": revision,
                # Left for the reviewer: which pages they actually judged it
                # against. Prefilling every chunk in the chapter would record a
                # reading nobody did.
                "source_chunk_ids": [],
                "transformation_type": None,
                "reviewer": None,
                "verdict": None,
                "_claim_text": candidate["text"],
            }
            for candidate in needs_review
        ],
    }


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--out", help="where to write the worksheet")
    args = parser.parse_args(argv)

    sheet = worksheet(args.chapter)
    needs = len(sheet["approvals"])

    print(f"chapter {args.chapter}: {needs} transformations need review, "
          f"{sheet['generated_claim_count']} claims are generated")
    print(f"source revision: {sheet['source_content_revision']}")

    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(sheet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {target}")

    return 0


if __name__ == "__main__":
    sys.exit(_main())
