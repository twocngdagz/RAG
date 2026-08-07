"""Emit one chapter as a v2 lesson package, or refuse and say why.

The exporter TRANSFORMS a declared mapping. It does not decide what a claim
teaches or assesses — the manifest says that, because the chapter cannot. What
this module does is follow the mapping into the material, publish the whole
teaching document as ordered blocks, add each concept's class lesson to them
where the transform stage has written one, fill each concept's question bank,
draw the declared diagrams from the numbers the material already carries, seal
the assets in, translate each claim's provenance into the record Ela validates,
and hash the result.

Class lessons ADD. A chapter that has been through B20.1's transform stage
carries, per concept, the thing a teacher stands up and delivers — the goal, the
techniques, the examples worked in front of the class — and those become blocks
belonging to that concept. The enrichment's own material stays exactly where it
was. A chapter that has never been through the transform stage has no class
lessons, and exports from its enrichment as it always did.

It exports from APPROVED mappings only. Drafts exist now — a generator proposes
what a chapter's concepts might be — and a proposal that reached a learner would
be indistinguishable from teaching somebody wrote. So a mapping that does not
say `"approved": true` is refused before anything else happens.

Every refusal names a path. "The chapter cannot be exported" is not actionable;
"resources.0.elements.2 -> review_checklist.9 does not resolve" tells whoever
fixes it exactly which line of the mapping is wrong.

A re-export COMPARES itself to the package already on disk and prints what it
added and what it dropped. Enrichment adds; a removal is an edit, and an edit is
named by whoever makes it (`--edit "why"`), never shipped as an enrichment.

    python export_lesson_package.py --slug math5a --chapter 3 \\
        --book output/math5a.chapter03.book_learning_materials.json \\
        --clean-chunks output/math5a.chapter03.clean_chunks.json \\
        --manifest manifests/math5a.chapter03.export_manifest.json \\
        --out output/math5a.chapter03.package.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import class_lesson_contract
import class_lesson_store
import domain_packs
import enrichment_comparison
import exercise_bank
import lesson_assets
import lesson_diagrams
import lesson_export_manifest as manifest_module
import lesson_package
import lesson_provenance
import math_practice_items
import teaching_document as teaching_document_module
from book_learning_materials_contract import (
    BookLearningMaterialsContractError,
    atomic_write_json,
    validate_book_contract,
)

# RAG claim kinds that describe teaching a learner reads. Anything outside this
# is metadata about the chapter, not content within it.
BLOCK_TEXT_FIELDS = ("text", "value", "meaning", "explanation", "example", "question", "answer")


class ExportRefused(Exception):
    """The chapter cannot be exported, and why."""


def export_chapter(
    slug: str,
    chapter_number: int,
    materials: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    *,
    teaching_document: dict[str, Any] | None = None,
    practice_items: list[dict[str, Any]] | None = None,
    class_lessons: dict[str, Any] | None = None,
    class_lessons_file: str | Path | None = None,
    asset_base: Path | None = None,
) -> dict[str, Any]:
    """One chapter, one package.

    A chapter is one lesson. Splitting it would need a rule for where a lesson
    ends that nobody has written down, and merging chapters would put a learner
    in front of material the book kept apart.

    `manifest`, `teaching_document`, `practice_items` and `class_lessons` may be
    supplied directly; otherwise they are read from the paths the pack declares.
    Supplying the manifest is still supplying a DECLARED mapping — the exporter
    does not gain the ability to invent one.

    A chapter nobody has run the transform stage for has no class lessons, and
    that is SILENCE rather than a gap: it exports from its enrichment exactly as
    it did before class lessons existed.
    """
    pack = domain_packs.get(slug)
    _assert_pack_matches_source(pack, materials)

    if manifest is None:
        manifest = manifest_module.load(slug, chapter_number)
    else:
        # Supplying the mapping in memory skips reading it off disk; it does not
        # skip the person who has to approve it. Otherwise the one caller that
        # passes a manifest directly would be the way an unread draft ships.
        manifest_module.assert_approved(manifest, "the supplied mapping")

        problems = manifest_module.validate(manifest)

        if problems:
            raise manifest_module.ManifestInvalid(
                "the supplied mapping cannot be exported from:\n  " + "\n  ".join(problems)
            )

    chapter = _chapter(materials, chapter_number)

    if teaching_document is None:
        teaching_document = _read_json(pack.enrich_path(chapter_number), "the teaching document")

    if practice_items is None:
        practice_items = _read_json(math_practice_items.OUTPUT_FILE, "the practice item bank")

    if class_lessons is None:
        class_lessons = _read_class_lessons(slug, chapter_number, class_lessons_file)

    source_resource_id = _source_resource_id(materials, slug)
    content_revision = _content_revision(materials, chapter_number)
    lesson_stable_key = manifest["lesson"]["stable_key"]

    lesson = {
        **manifest["lesson"],
        "provenance": _lesson_provenance(manifest),
    }

    chapter_chunk_ids = [str(chunk) for chunk in chapter.get("source_chunk_ids") or []]

    try:
        published_document = teaching_document_module.build(
            teaching_document,
            slug=slug,
            chapter_number=chapter_number,
            grounded_in_source_chunk_ids=chapter_chunk_ids,
            generator_version=str(manifest["teaching_document"]["generator_version"]).strip(),
        )
    except teaching_document_module.TeachingDocumentRefused as error:
        raise ExportRefused(f"teaching_document -> {error}") from error

    # Added to the enrichment's blocks, never in place of them, and added BEFORE
    # the diagrams are drawn so a picture may be placed after a class lesson's
    # worked example exactly as it may after the chapter's own.
    try:
        published_document = teaching_document_module.with_class_lessons(
            published_document,
            _class_lessons(
                class_lessons,
                slug=slug,
                chapter_number=chapter_number,
                manifest=manifest,
                lesson_stable_key=lesson_stable_key,
                grounded_in_source_chunk_ids=chapter_chunk_ids,
            ),
        )
    except teaching_document_module.TeachingDocumentRefused as error:
        raise ExportRefused(f"teaching_document -> {error}") from error

    concepts = [
        _concept(
            declared,
            chapter_number=chapter_number,
            lesson_stable_key=lesson_stable_key,
            items=practice_items,
            manifest=manifest,
            pack=pack,
            path=f"concepts.{index}",
        )
        for index, declared in enumerate(manifest.get("concepts") or [])
    ]

    # Concepts belong to a framework. Ela's column is required and it will not
    # guess one, because filing a book's concepts under a framework nobody chose
    # is worse than refusing the package.
    competency_framework = manifest["competency_framework"]

    resources = [
        _resource(
            resource,
            chapter,
            pack,
            source_resource_id,
            lesson_stable_key,
            f"resources.{index}",
        )
        for index, resource in enumerate(manifest.get("resources") or [])
    ]

    # Drawn before the assets are sealed, because a computed diagram IS an
    # asset: it goes through the same gate as a photograph an author uploaded,
    # and a second way into the asset channel would be a second answer to what
    # an asset is.
    try:
        drawn = [
            _diagram(
                declared,
                blocks=published_document["blocks"],
                items=practice_items,
                lesson_stable_key=lesson_stable_key,
                exercise_keys={
                    str(exercise.get("stable_key") or "")
                    for concept in concepts
                    for exercise in concept.get("exercises") or []
                },
                path=f"diagrams.{index}",
            )
            for index, declared in enumerate(manifest.get("diagrams") or [])
        ]
    except lesson_diagrams.DiagramRefused as error:
        raise ExportRefused(str(error)) from error

    base_dir = asset_base or Path(".")

    try:
        assets = [
            lesson_assets.build(asset, base_dir=base_dir, path=f"assets.{index}")
            for index, asset in enumerate(manifest.get("assets") or [])
        ] + [
            lesson_assets.build(diagram["asset"], base_dir=base_dir, path=f"diagrams.{index}")
            for index, diagram in enumerate(drawn)
        ]
    except lesson_assets.AssetRefused as error:
        raise ExportRefused(str(error)) from error

    try:
        published_document = teaching_document_module.with_illustrations(
            published_document, [_illustration(diagram) for diagram in drawn]
        )
    except teaching_document_module.TeachingDocumentRefused as error:
        raise ExportRefused(f"teaching_document -> {error}") from error

    package = lesson_package.build_package(
        competency_framework=competency_framework,
        objective_associations=manifest.get("objective_associations") or [],
        pack=pack,
        content_revision=content_revision,
        lesson=lesson,
        teaching_document=published_document,
        concepts=concepts,
        resources=resources,
        assets=assets,
    )

    problems = lesson_package.structural_problems(package)

    if problems:
        raise ExportRefused(
            f"{slug} chapter {chapter_number} assembled into an unusable package:\n  "
            + "\n  ".join(problems)
        )

    return package


def _concept(
    declared: dict[str, Any],
    *,
    chapter_number: int,
    lesson_stable_key: str,
    items: list[dict[str, Any]],
    manifest: dict[str, Any],
    pack,
    path: str,
) -> dict[str, Any]:
    """One concept: the objective, the card, and the bank behind it.

    The statement is written once, in the manifest, and appears once here. The
    card in a learner's schedule, the "what you'll be able to do" line, and the
    mastery tick are the same entity — so there is nothing to keep in step.
    """
    try:
        exercises = exercise_bank.build(
            concept=declared,
            chapter_number=chapter_number,
            lesson_stable_key=lesson_stable_key,
            items=items,
            pack=pack,
            path=path,
        )
    except exercise_bank.BankRefused as error:
        raise ExportRefused(str(error)) from error

    return {
        "stable_key": declared["stable_key"],
        "statement": declared["statement"],
        "objective_type": declared["objective_type"],
        # Whether a learner is MEASURED against this concept, not merely taught
        # it. The importer refuses to publish an assessed objective nothing can
        # produce evidence for, and without this field that check governs
        # nothing: every concept looks unassessed.
        "assessed": bool(declared.get("assessed", False)),
        # A concept's statement is written in the manifest, by a person, so it is
        # manually authored — and it says so only because that is verifiably how
        # it got there, not because RAG has nothing better.
        "provenance": {
            "origin": lesson_provenance.MANUALLY_AUTHORED,
            "author_reference": _author_reference(manifest, path),
        },
        "exercises": exercises,
    }


def _read_class_lessons(
    slug: str, chapter_number: int, path: str | Path | None
) -> dict[str, Any] | None:
    """The chapter's class lessons, or None because it has none.

    Absence at the DEFAULT path is silence: most chapters have not been through
    the transform stage yet, and one that has not still exports from its
    enrichment. A path NAMED by the caller is a different thing — asking for a
    file that is not there is a mistake worth hearing about, not a chapter
    exporting quietly without the teaching somebody meant to include.
    """
    if path is not None:
        return _read_json(path, "the chapter's class lessons")

    default = class_lesson_store.store_path(slug, chapter_number)

    return _read_json(default, "the chapter's class lessons") if default.exists() else None


def _class_lessons(
    store: dict[str, Any] | None,
    *,
    slug: str,
    chapter_number: int,
    manifest: dict[str, Any],
    lesson_stable_key: str,
    grounded_in_source_chunk_ids: list[str],
) -> list[dict[str, Any]]:
    """This chapter's class lessons, held to the contract and to the mapping.

    THE CONTRACT IS CHECKED AGAIN HERE, and deliberately. It governs three
    stages — it briefs the generator, it is what the runner accepted a reply
    under, and it is what the export publishes — and a file on disk can be edited
    between the second and the third. Re-checking costs nothing and is the only
    thing standing between a hand-edited store and a package.

    THE STATEMENT IS CHECKED TOO, because the contract checks a lesson against the
    concept it claims to be for. A statement that moved in the mapping after the
    lesson was generated means the lesson teaches something the card no longer
    says, and the honest answer is to run that concept again rather than to ship
    the mismatch.

    A concept with no class lesson is silence: this chapter has not been run for
    it yet, and the enrichment still teaches. A class lesson for a concept the
    mapping does not declare is not silence — it is teaching about to be dropped
    without a word, so it is refused.
    """
    if not store:
        return []

    try:
        class_lesson_store.assert_holds(
            store, slug=slug, chapter=chapter_number, source="the chapter's class lessons"
        )
    except class_lesson_store.ClassLessonsRefused as error:
        raise ExportRefused(f"class_lessons -> {error}") from error

    lessons = class_lesson_store.lessons(store)

    if not lessons:
        return []

    generator_version = str(
        (manifest.get("class_lessons") or {}).get("generator_version") or ""
    ).strip()

    if not generator_version:
        raise ExportRefused(
            "class_lessons -> this chapter has class lessons, but the mapping does not say which "
            "generator produced them; naming one RAG cannot verify would be inventing a fact "
            "about authorship, exactly as teaching_document.generator_version would be"
        )

    declared = {
        str((concept or {}).get("stable_key") or "").strip(): concept
        for concept in manifest.get("concepts") or []
    }
    orphans = sorted(set(lessons) - set(declared))

    if orphans:
        raise ExportRefused(
            f"class_lessons -> there is teaching for {', '.join(orphans)}, which this mapping does "
            f"not declare as a concept of {lesson_stable_key}. Exporting without it would drop a "
            f"class lesson somebody generated and say nothing"
        )

    built: list[dict[str, Any]] = []

    for key, concept in declared.items():
        lesson = lessons.get(key)

        if lesson is None:
            continue

        try:
            checked = class_lesson_contract.validate(
                lesson,
                concept_key=key,
                concept_statement=str((concept or {}).get("statement") or ""),
            )
        except class_lesson_contract.ClassLessonRefused as error:
            raise ExportRefused(f"class_lessons.{key} -> {error}") from error

        built.append(
            {
                "concept_stable_key": key,
                "class_lesson": checked,
                "provenance": {
                    "origin": lesson_provenance.PEDAGOGICAL_GENERATION,
                    # A class lesson is a transform of the chapter's enriched
                    # material, so it rests on what that material rests on. Naming
                    # nothing would understate it; naming anything else would
                    # claim the generator read something it never saw.
                    "grounded_in_source_chunk_ids": sorted(set(grounded_in_source_chunk_ids)),
                    "generation_reason": (
                        f"Class lesson for {key}, written from this chapter's enriched material "
                        f"under {class_lesson_contract.SCHEMA_VERSION}"
                    ),
                    "generator_version": generator_version,
                },
            }
        )

    return built


def _diagram(
    declared: dict[str, Any],
    *,
    blocks: list[dict[str, Any]],
    items: list[dict[str, Any]],
    lesson_stable_key: str,
    exercise_keys: set[str],
    path: str,
) -> dict[str, Any]:
    """One computed diagram: the numbers it reads, and the picture it becomes.

    The manifest says WHICH drawing and WHERE the numbers live; it never says
    what the numbers are. Restating them here would let a picture and the
    example beside it drift apart, and a maths picture that disagrees with its
    question teaches the wrong thing.
    """
    reference = str(declared.get("numbers_from") or "").strip()
    source_text, grounded_in_source_chunk_ids = _diagram_numbers(
        reference,
        blocks=blocks,
        items=items,
        lesson_stable_key=lesson_stable_key,
        exercise_keys=exercise_keys,
        path=path,
    )

    return {
        "asset": lesson_diagrams.build(
            declared,
            source_text=source_text,
            source_reference=reference,
            grounded_in_source_chunk_ids=grounded_in_source_chunk_ids,
            path=path,
        ),
        "appears_after": str(declared.get("appears_after") or "").strip(),
    }


def _diagram_numbers(
    reference: str,
    *,
    blocks: list[dict[str, Any]],
    items: list[dict[str, Any]],
    lesson_stable_key: str,
    exercise_keys: set[str],
    path: str,
) -> tuple[str, list[str]]:
    """The text a diagram reads its numbers from, and what that text rests on."""
    if reference.startswith("worked_examples."):
        block = next((block for block in blocks if block.get("key") == reference), None)

        if block is None:
            raise lesson_diagrams.DiagramRefused(
                f"{path}.numbers_from names {reference!r}, which this teaching document does not contain"
            )

        question = str((block.get("content") or {}).get("input") or "").strip()

        if not question:
            raise lesson_diagrams.DiagramRefused(
                f"{path}.numbers_from names {reference!r}, which poses no question to draw from"
            )

        # A diagram drawn from a worked example rests on whatever that example
        # rests on. It is the same teaching, in a second form.
        return question, _block_chunks(block)

    item_id = reference[len("exercises."):]
    item = next((item for item in items if str(item.get("id") or "") == item_id), None)

    if item is None:
        raise lesson_diagrams.DiagramRefused(
            f"{path}.numbers_from names exercise {item_id!r}, which the item bank does not have"
        )

    if f"{lesson_stable_key}:{item_id}" not in exercise_keys:
        raise lesson_diagrams.DiagramRefused(
            f"{path}.numbers_from names exercise {item_id!r}, which no concept in this lesson asks; "
            f"a picture of a question the lesson never puts is met by nobody"
        )

    question = str(item.get("prompt") or "").strip()

    if not question:
        raise lesson_diagrams.DiagramRefused(
            f"{path}.numbers_from names exercise {item_id!r}, which has no question to draw from"
        )

    # Deliberately empty, and honest: these numbers came from a parametric
    # generator and rest on no passage of the book, exactly as the exercise
    # itself does.
    return question, []


def _illustration(diagram: dict[str, Any]) -> dict[str, Any]:
    """The block a learner meets the picture in, carrying what it says about itself."""
    asset = diagram["asset"]

    return {
        "key": f"illustration.{asset['stable_key']}",
        "appears_after": diagram["appears_after"],
        "content": {
            "caption": asset["caption"],
            "alt_text": asset["alt_text"],
            "asset_stable_key": asset["stable_key"],
        },
        "provenance": asset["provenance"],
    }


def _block(reference: str, chapter: dict[str, Any], source_resource_id: str, path: str) -> dict[str, Any]:
    try:
        claim = manifest_module.resolve_element(chapter, reference)
    except manifest_module.ManifestInvalid as error:
        raise ExportRefused(f"{path} -> {error}") from error

    if not isinstance(claim, dict):
        raise ExportRefused(f"{path} -> {reference!r} is not a claim with provenance")

    text = next(
        (str(claim[field]).strip() for field in BLOCK_TEXT_FIELDS if str(claim.get(field) or "").strip()),
        "",
    )

    if not text:
        raise ExportRefused(f"{path} -> {reference!r} has no text a learner could read")

    try:
        provenance = lesson_provenance.translate(
            claim,
            source_path=f"{path} -> {reference}",
            source_resource_id=source_resource_id,
        )
    except lesson_provenance.UnsupportedProvenance as error:
        raise ExportRefused(str(error)) from error

    return {
        "type": "text",
        "version": 1,
        "content": {"key": reference.replace(".", "_"), "text": text},
        "provenance": provenance,
    }


def _block_chunks(block: dict[str, Any]) -> list[str]:
    provenance = block.get("provenance") or {}

    return list(
        provenance.get("source_chunk_ids") or provenance.get("grounded_in_source_chunk_ids") or []
    )


def _resource(
    declared: dict[str, Any],
    chapter: dict[str, Any],
    pack,
    source_resource_id: str,
    lesson_stable_key: str,
    path: str,
) -> dict[str, Any]:
    blocks = [
        _block(reference, chapter, source_resource_id, f"{path}.elements.{index}")
        for index, reference in enumerate(declared["elements"])
    ]

    links = declared.get("links") or []

    if not links:
        raise ExportRefused(f"{path}.links is empty; a resource nothing links to reaches no learner")

    for index, link in enumerate(links):
        if link.get("scope") == "lesson" and link.get("lesson_stable_key") != lesson_stable_key:
            raise ExportRefused(
                f"{path}.links.{index} is lesson-scoped but names "
                f"{link.get('lesson_stable_key')!r} rather than {lesson_stable_key!r}"
            )

    return {
        "stable_key": declared["stable_key"],
        "definition": {
            "contract": "learning.resource.v1",
            "resource_type": declared.get("resource_type", "alternative_explanation"),
            "resource_type_version": 1,
            "title": declared.get("title", ""),
            # Ela's resource contract requires both. Omitting them produced a
            # resource that passed this repository's structural check and would
            # have been refused at import.
            "domain": declared.get("domain", pack.slug),
            "definition": {"blocks": blocks},
            "provenance": {
                "origin": lesson_provenance.PEDAGOGICAL_GENERATION,
                "grounded_in_source_chunk_ids": sorted(
                    {chunk for block in blocks for chunk in _block_chunks(block)}
                ),
                "generation_reason": declared.get(
                    "assembly_reason", "Assembled from declared chapter elements"
                ),
                "generator_version": f"{lesson_package.PRODUCER_VERSION} pack:{pack.version}",
            },
        },
        "links": links,
    }


def _lesson_provenance(manifest: dict[str, Any]) -> dict[str, Any]:
    """Where the LESSON came from, which is not where any one claim came from.

    This used to translate `chapter_summary`'s provenance, which coupled the
    lesson's identity to whether one sentence happened to be quotable from the
    source. On a workbook it never is -- Singapore Math 5A demonstrates rather
    than explains -- so no math5a chapter could be exported at all, however
    publishable its actual content was.

    A lesson's stable key, title and domain are written in the manifest, by a
    person, exactly as concept statements are. So it carries the same origin
    they do, and for the same verifiable reason: that is how it got there.

    The claims inside the lesson keep their own provenance. Nothing here weakens
    what any individual element says about its evidence.
    """
    return {
        "origin": lesson_provenance.MANUALLY_AUTHORED,
        "author_reference": _author_reference(manifest, "lesson"),
    }


def _author_reference(manifest: dict[str, Any], path: str) -> str:
    """Who wrote the mapping.

    Required, and never inferred. `manually_authored` is a claim that a person
    wrote something; emitting it because RAG happens to have no better origin
    would turn "we do not know" into "a person did this".
    """
    reference = str(manifest.get("authored_by") or "").strip()

    if not reference:
        raise ExportRefused(
            f"{path} would be manually_authored, but the manifest does not say who wrote it"
        )

    return reference


def _assert_pack_matches_source(pack, materials: dict[str, Any]) -> None:
    """The pack and the book must be the same book.

    Exporting a `sample-v2` book under the `math5a` pack produces a package
    whose pack rules and source resource describe different material — and the
    resource id every block carries would name a book the pack has never seen.
    """
    book_slug = str((materials.get("book") or {}).get("slug") or "").strip()

    if book_slug and book_slug != pack.slug:
        raise ExportRefused(
            f"the source book is {book_slug!r} but the pack is {pack.slug!r}; "
            f"a package cannot describe one book under another's rules"
        )


def _chapter(materials: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    chapters = (materials.get("learning_materials") or materials).get("chapters") or []

    for chapter in chapters:
        if chapter.get("chapter_number") == chapter_number:
            return chapter

    raise ExportRefused(f"the material has no chapter {chapter_number}")


def _read_json(path: str | Path, what: str) -> Any:
    location = Path(path)

    if not location.exists():
        raise ExportRefused(f"{what} is not at {location}; nothing was exported")

    try:
        return json.loads(location.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ExportRefused(f"{what} at {location} is not readable JSON: {error}") from error


def _source_resource_id(materials: dict[str, Any], slug: str) -> str:
    book = materials.get("book") or {}

    return str(book.get("slug") or slug) + ":book"


def _content_revision(materials: dict[str, Any], chapter_number: int) -> str:
    """A revision that identifies THIS content, or a refusal.

    Emitting `chapter03@unknown` looks like a revision and identifies nothing:
    two different generations of a chapter would carry the same string, and an
    importer deciding whether it already has this material would be comparing
    labels that never change. Where the generator recorded a run, that is used;
    otherwise the revision is derived from the chapter's own canonical content,
    which at least moves when the content does.
    """
    generation = materials.get("generation") or {}
    recorded = str(generation.get("run_id") or generation.get("generated_at") or "").strip()

    if recorded:
        return f"chapter{chapter_number:02d}@{recorded}"

    chapter = _chapter(materials, chapter_number)
    canonical = json.dumps(chapter, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    return f"chapter{chapter_number:02d}@sha256:{digest}"


def emit_package_file(
    *,
    slug: str,
    chapter_number: int,
    book_file: str | Path,
    clean_chunks_file: str | Path,
    manifest_file: str | Path,
    output_file: str | Path,
    enrichment_file: str | Path | None = None,
    practice_items_file: str | Path | None = None,
    class_lessons_file: str | Path | None = None,
    compare_with: str | Path | None = None,
    edit_reason: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Check approval, validate the source, assemble, compare, and write — in that order.

    Approval is checked FIRST, before anything is read or audited. An unapproved
    mapping cannot be published however sound the material behind it is, so
    spending the audit on one only buys a refusal that names the wrong problem:
    whoever pointed the exporter at a draft needs to be told it is a draft, not
    handed a report about claim grounding.

    The source contract runs next and must pass. A book that fails it has
    something wrong with its claims or their grounding, and exporting anyway
    would launder that into a package Ela then imports as though it were sound —
    the one place the problem stops being visible.

    The comparison runs BEFORE the write, so a re-export that dropped content
    leaves the previous package where it was. Discovering the loss after
    overwriting the only copy of what was lost is not a check.

    Nothing is written unless everything succeeds. A partial package on disk is
    worse than none: it looks like an artefact, and an importer has no way to
    tell it from a complete one.
    """
    manifest = _read_json(manifest_file, "the declared mapping")
    manifest_module.assert_approved(manifest, str(manifest_file))

    audit = validate_book_contract(book_file=book_file, clean_chunks_file=clean_chunks_file)

    if audit.get("status") != "PASS":
        summary = audit.get("summary") or {}
        raise ExportRefused(
            f"{book_file} does not pass the source contract "
            f"({summary.get('error_count', 'unknown')} errors); no package was written"
        )

    problems = manifest_module.validate(manifest)

    if problems:
        raise manifest_module.ManifestInvalid(
            f"{manifest_file} cannot be exported from:\n  " + "\n  ".join(problems)
        )

    materials = json.loads(Path(book_file).read_text(encoding="utf-8"))
    pack = domain_packs.get(slug)

    package = export_chapter(
        slug,
        chapter_number,
        materials,
        manifest=manifest,
        teaching_document=_read_json(
            enrichment_file or pack.enrich_path(chapter_number), "the teaching document"
        ),
        practice_items=_read_json(
            practice_items_file or math_practice_items.OUTPUT_FILE, "the practice item bank"
        ),
        class_lessons_file=class_lessons_file,
        # Asset files are named relative to the manifest that declares them, so
        # a mapping stays movable: the pictures travel with the mapping.
        asset_base=Path(manifest_file).resolve().parent,
    )

    report = _compare_with_previous(
        package,
        previous_file=Path(compare_with) if compare_with else Path(output_file),
        required=compare_with is not None,
        edit_reason=edit_reason,
    )

    # Reused rather than reinvented: a second writer is a second answer to what
    # "written" means, and they drift.
    atomic_write_json(Path(output_file), package)

    return package, report


def _compare_with_previous(
    package: dict[str, Any],
    *,
    previous_file: Path,
    required: bool,
    edit_reason: str | None,
) -> dict[str, Any] | None:
    """What this re-export added and dropped, or None if there is nothing to compare to."""
    if not previous_file.exists():
        if required:
            raise ExportRefused(f"there is no package at {previous_file} to compare against")

        return None

    previous = _read_json(previous_file, "the previous package")

    try:
        report = enrichment_comparison.compare(previous, package)
    except enrichment_comparison.PreviousPackageIncomparable as error:
        if required:
            raise ExportRefused(str(error)) from error

        # The v1 package sitting at the output path is the one this format break
        # replaces. Refusing to write over it would make the break unshippable;
        # pretending it was comparable would report the whole old lesson as
        # removed. So: say what happened, and carry on.
        print(f"not compared: {error}", file=sys.stderr)

        return None

    if not edit_reason:
        enrichment_comparison.assert_additive(report)

    return report


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Emit one chapter as a v2 lesson package.")
    parser.add_argument("--slug", required=True, help="domain pack slug, e.g. math5a")
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--book", required=True, help="generated book learning materials JSON")
    parser.add_argument("--clean-chunks", required=True, help="clean chunks the book is grounded in")
    parser.add_argument("--manifest", required=True, help="the declared export mapping")
    parser.add_argument("--out", required=True, help="where to write the package")
    parser.add_argument(
        "--enrichment",
        help="the Coach teaching document to publish (default: the path the pack declares)",
    )
    parser.add_argument(
        "--practice-items",
        help="the computed question bank concepts draw from (default: the generator's own output)",
    )
    parser.add_argument(
        "--class-lessons",
        help="the chapter's class lessons (default: the transform stage's own output, if it is "
             "there; a chapter with none exports from its enrichment)",
    )
    parser.add_argument(
        "--compare-with",
        help="a package to compare against instead of whatever is already at --out",
    )
    parser.add_argument(
        "--edit",
        help="declare this a named edit rather than an enrichment, so removals are allowed",
    )

    args = parser.parse_args(argv)

    try:
        package, report = emit_package_file(
            slug=args.slug,
            chapter_number=args.chapter,
            book_file=args.book,
            clean_chunks_file=args.clean_chunks,
            manifest_file=args.manifest,
            output_file=args.out,
            enrichment_file=args.enrichment,
            practice_items_file=args.practice_items,
            class_lessons_file=args.class_lessons,
            compare_with=args.compare_with,
            edit_reason=args.edit,
        )
    except (
        ExportRefused,
        manifest_module.ManifestMissing,
        manifest_module.ManifestInvalid,
        manifest_module.ManifestUnapproved,
        enrichment_comparison.EnrichmentRemovedContent,
        BookLearningMaterialsContractError,
    ) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1

    if report is not None:
        print(enrichment_comparison.summary(report) + (f" (edit: {args.edit})" if args.edit else ""))

    # Said out loud, because teaching being carried in silence is the failure this
    # channel exists to end: a chapter whose class lessons were ignored used to
    # export exactly like one that had none.
    carried = sorted(
        {
            str(block.get("concept_stable_key") or "")
            for block in package["teaching_document"]["blocks"]
            if block.get("concept_stable_key")
        }
    )

    if carried:
        print(f"class lessons carried for {len(carried)} concept(s): {', '.join(carried)}")

    print(f"wrote {args.out} ({package['content_hash'][:12]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
