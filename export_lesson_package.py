"""Emit one chapter as a lesson package, or refuse and say why.

The exporter TRANSFORMS a declared mapping. It does not decide what a claim
teaches or assesses — the manifest says that, because the chapter cannot. What
this module does is follow the mapping into the material, translate each claim's
provenance into the record Ela validates, assemble complete
`learning.activity.v1` definitions, and hash the result.

Every refusal names a path. "The chapter cannot be exported" is not actionable;
"activities.1.elements.0 -> core_lessons.9.explanation does not resolve" tells
whoever fixes it exactly which line of the mapping is wrong.

    python export_lesson_package.py --slug math5a --chapter 3 \\
        --book output/math5a.chapter03.book_learning_materials.json \\
        --clean-chunks output/math5a.clean_chunks.json \\
        --manifest output/math5a.chapter03.export_manifest.json \\
        --out output/math5a.chapter03.package.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import domain_packs
import lesson_export_manifest as manifest_module
import lesson_package
import lesson_provenance
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
) -> dict[str, Any]:
    """One chapter, one package.

    A chapter is one lesson. Splitting it would need a rule for where a lesson
    ends that nobody has written down, and merging chapters would put a learner
    in front of material the book kept apart.

    `manifest` may be supplied directly; otherwise it is read from beside the
    material. Supplying it is still supplying a DECLARED mapping — the exporter
    does not gain the ability to invent one.
    """
    pack = domain_packs.get(slug)

    if manifest is None:
        manifest = manifest_module.load(slug, chapter_number)
    else:
        problems = manifest_module.validate(manifest)

        if problems:
            raise manifest_module.ManifestInvalid(
                "the supplied mapping cannot be exported from:\n  " + "\n  ".join(problems)
            )
    chapter = _chapter(materials, chapter_number)

    source_resource_id = _source_resource_id(materials, slug)
    content_revision = _content_revision(materials, chapter_number)

    lesson = {
        **manifest["lesson"],
        "provenance": _lesson_provenance(chapter, source_resource_id),
    }

    objectives = [
        {
            "stable_key": objective["stable_key"],
            "statement": objective["statement"],
            "objective_type": objective["objective_type"],
            # An objective statement is written in the manifest, by a person, so
            # it is manually authored — and it says so only because that is
            # verifiably how it got there, not because RAG has nothing better.
            "provenance": {
                "origin": lesson_provenance.MANUALLY_AUTHORED,
                "author_reference": _author_reference(manifest, f"objectives.{index}"),
            },
        }
        for index, objective in enumerate(manifest.get("objectives") or [])
    ]

    resources = [
        _resource(resource, chapter, source_resource_id, f"resources.{index}")
        for index, resource in enumerate(manifest.get("resources") or [])
    ]

    activities = [
        _activity(activity, chapter, pack, source_resource_id, f"activities.{index}")
        for index, activity in enumerate(manifest.get("activities") or [])
    ]

    package = lesson_package.build_package(
        pack=pack,
        content_revision=content_revision,
        lesson=lesson,
        objectives=objectives,
        activities=activities,
        resources=resources,
    )

    problems = lesson_package.structural_problems(package)

    if problems:
        raise ExportRefused(
            f"{slug} chapter {chapter_number} assembled into an unusable package:\n  "
            + "\n  ".join(problems)
        )

    return package


def _activity(
    declared: dict[str, Any],
    chapter: dict[str, Any],
    pack,
    source_resource_id: str,
    path: str,
) -> dict[str, Any]:
    blocks = [
        _block(reference, chapter, source_resource_id, f"{path}.elements.{index}")
        for index, reference in enumerate(declared["elements"])
    ]

    definition = {
        "contract": lesson_package.ACTIVITY_CONTRACT,
        "type": declared["type"],
        "type_version": declared.get("type_version", 1),
        "domain": declared.get("domain", pack.slug),
        "evidence_mode": declared["evidence_mode"],
        "answer_visibility": declared.get("answer_visibility", "after_submission"),
        "presentation": {"blocks": blocks},
        "response": declared["response"],
        "evaluation": declared["evaluation"],
        "scheduling": declared["scheduling"],
        # The activity as a whole is assembled here from declared parts. Its
        # blocks each carry their own origin, which is where the real evidence
        # about the content lives.
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
    }

    if declared.get("guidance"):
        definition["presentation"]["guidance"] = declared["guidance"]

    return {
        "stable_key": declared["stable_key"],
        "objective_alignments": declared["objective_alignments"],
        "resource_links": declared.get("resource_links", []),
        "definition": definition,
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
    source_resource_id: str,
    path: str,
) -> dict[str, Any]:
    blocks = [
        _block(reference, chapter, source_resource_id, f"{path}.elements.{index}")
        for index, reference in enumerate(declared["elements"])
    ]

    return {
        "stable_key": declared["stable_key"],
        "definition": {
            "contract": "learning.resource.v1",
            "resource_type": declared.get("resource_type", "alternative_explanation"),
            "resource_type_version": 1,
            "title": declared.get("title", ""),
            "definition": {"blocks": blocks},
        },
        "links": declared.get("links", []),
    }


def _lesson_provenance(chapter: dict[str, Any], source_resource_id: str) -> dict[str, Any]:
    summary = chapter.get("chapter_summary")

    if isinstance(summary, dict):
        try:
            return lesson_provenance.translate(
                summary,
                source_path="chapter_summary",
                source_resource_id=source_resource_id,
            )
        except lesson_provenance.UnsupportedProvenance as error:
            raise ExportRefused(str(error)) from error

    raise ExportRefused("chapter_summary carries no provenance, so the lesson cannot say where it came from")


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


def _chapter(materials: dict[str, Any], chapter_number: int) -> dict[str, Any]:
    chapters = (materials.get("learning_materials") or materials).get("chapters") or []

    for chapter in chapters:
        if chapter.get("chapter_number") == chapter_number:
            return chapter

    raise ExportRefused(f"the material has no chapter {chapter_number}")


def _source_resource_id(materials: dict[str, Any], slug: str) -> str:
    book = materials.get("book") or {}

    return str(book.get("slug") or slug) + ":book"


def _content_revision(materials: dict[str, Any], chapter_number: int) -> str:
    generation = materials.get("generation") or {}
    revision = generation.get("run_id") or generation.get("generated_at") or "unknown"

    return f"chapter{chapter_number:02d}@{revision}"


def emit_package_file(
    *,
    slug: str,
    chapter_number: int,
    book_file: str | Path,
    clean_chunks_file: str | Path,
    manifest_file: str | Path,
    output_file: str | Path,
) -> dict[str, Any]:
    """Validate the source, assemble the package, and write it — in that order.

    The source contract runs FIRST and must pass. A book that fails it has
    something wrong with its claims or their grounding, and exporting anyway
    would launder that into a package Ela then imports as though it were sound —
    the one place the problem stops being visible.

    Nothing is written unless everything succeeds. A partial package on disk is
    worse than none: it looks like an artefact, and B11.1 has no way to tell it
    from a complete one.
    """
    audit = validate_book_contract(book_file=book_file, clean_chunks_file=clean_chunks_file)

    if audit.get("status") != "PASS":
        summary = audit.get("summary") or {}
        raise ExportRefused(
            f"{book_file} does not pass the source contract "
            f"({summary.get('error_count', 'unknown')} errors); no package was written"
        )

    manifest = json.loads(Path(manifest_file).read_text(encoding="utf-8"))
    problems = manifest_module.validate(manifest)

    if problems:
        raise manifest_module.ManifestInvalid(
            f"{manifest_file} cannot be exported from:\n  " + "\n  ".join(problems)
        )

    materials = json.loads(Path(book_file).read_text(encoding="utf-8"))
    package = export_chapter(slug, chapter_number, materials, manifest=manifest)

    # Reused rather than reinvented: a second writer is a second answer to what
    # "written" means, and they drift.
    atomic_write_json(Path(output_file), package)

    return package


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Emit one chapter as a lesson package.")
    parser.add_argument("--slug", required=True, help="domain pack slug, e.g. math5a")
    parser.add_argument("--chapter", required=True, type=int)
    parser.add_argument("--book", required=True, help="generated book learning materials JSON")
    parser.add_argument("--clean-chunks", required=True, help="clean chunks the book is grounded in")
    parser.add_argument("--manifest", required=True, help="the declared export mapping")
    parser.add_argument("--out", required=True, help="where to write the package")

    args = parser.parse_args(argv)

    try:
        package = emit_package_file(
            slug=args.slug,
            chapter_number=args.chapter,
            book_file=args.book,
            clean_chunks_file=args.clean_chunks,
            manifest_file=args.manifest,
            output_file=args.out,
        )
    except (
        ExportRefused,
        manifest_module.ManifestMissing,
        manifest_module.ManifestInvalid,
        BookLearningMaterialsContractError,
    ) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1

    print(f"wrote {args.out} ({package['content_hash'][:12]})")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
