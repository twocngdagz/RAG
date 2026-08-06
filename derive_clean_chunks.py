"""The clean-chunks file the source contract reads, derived from the book itself.

Every generated chapter carries the passages it was written from, whole, under
`source_chunks`. The contract validator reads the same passages from a separate
clean-chunks file, so that a claim saying "this came from math5a:p31" can be
checked against what math5a:p31 actually says. Chapter 3 had such a file because
the PDF run that produced it happened to write one; the other eight chapters
never got one, and without it nothing about them can be validated or exported.

Re-parsing the PDF to fill that gap would be the wrong repair twice over. It
needs a PDF this repository does not track, and a second parse is a second
opinion about what the book says — one that can disagree with the passages the
chapter was actually written from. The chapter already carries them. So this
module TRANSFORMS what is there rather than fetching it again: one clean chunk
per source chunk, with the book and chapter it belongs to attached, in the order
the chapter lists them. Same input, same output, every time.

The two fields it adds are the two the validator checks a chunk against — which
book it came from and which chapter it belongs to. They are read from the
material's own `book.source_pdf` and the chapter's own number, never defaulted:
a chunks file missing them is not a smaller file, it is one whose consistency
checks silently pass on anything.

    python derive_clean_chunks.py --slug math5a --chapter 3
    python derive_clean_chunks.py --slug math5a --all
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import domain_packs
from book_learning_materials_contract import atomic_write_json, chunk_node_id

# Beside the material it is derived from, under the name the exporter's
# --clean-chunks argument is already pointed at for chapter 3.
CLEAN_CHUNKS_FILE = "output/{slug}.chapter{n:02d}.clean_chunks.json"


class CleanChunksRefused(Exception):
    """The chunks cannot be derived from this material, and why."""


def clean_chunks_path(slug: str, chapter: int) -> Path:
    return Path(CLEAN_CHUNKS_FILE.format(slug=slug, n=chapter))


def derive(materials: dict[str, Any], *, chapter_number: int | None = None) -> list[dict[str, Any]]:
    """One clean chunk per source chunk the material carries, or a refusal."""
    source_pdf = str((materials.get("book") or {}).get("source_pdf") or "").strip()

    if not source_pdf:
        raise CleanChunksRefused(
            "book.source_pdf is missing, so a chunk cannot say which book it came from; "
            "the validator's check that a chapter cites its own book would pass on anything"
        )

    number = _chapter_number(materials, chapter_number)
    chunks = materials.get("source_chunks")

    if not isinstance(chunks, list) or not chunks:
        raise CleanChunksRefused(
            "source_chunks is empty; the chapter does not carry the passages it was "
            "written from, and they cannot be recovered from anything else here"
        )

    derived: list[dict[str, Any]] = []
    seen: set[str] = set()

    for index, chunk in enumerate(chunks):
        path = f"source_chunks.{index}"

        if not isinstance(chunk, dict):
            raise CleanChunksRefused(f"{path} is not a chunk with an id and text")

        node_id = chunk_node_id(chunk)

        if not node_id:
            raise CleanChunksRefused(f"{path} has no node id, so nothing can cite it")

        if node_id in seen:
            raise CleanChunksRefused(
                f"{path} repeats node id {node_id!r}; two passages under one id means a "
                f"citation of it names both and proves neither"
            )

        text = str(chunk.get("text") or "")

        if not text.strip():
            raise CleanChunksRefused(
                f"{path} ({node_id}) has no text; a claim grounded in it could never be checked"
            )

        seen.add(node_id)
        # Field order is fixed, so re-deriving a chapter that already has a
        # chunks file rewrites the same bytes rather than a reshuffled equal.
        derived.append(
            {
                "node_id": node_id,
                "source_pdf": source_pdf,
                "chapter_number": number,
                "text": text,
            }
        )

    return derived


def _chapter_number(materials: dict[str, Any], chapter_number: int | None) -> int:
    """Which chapter these passages belong to, said by the material rather than assumed."""
    chapters = (materials.get("learning_materials") or materials).get("chapters") or []
    numbers = [chapter.get("chapter_number") for chapter in chapters if isinstance(chapter, dict)]
    numbers = [number for number in numbers if isinstance(number, int)]

    if chapter_number is not None:
        if chapter_number not in numbers:
            raise CleanChunksRefused(
                f"the material has no chapter {chapter_number}; it carries "
                f"{', '.join(str(number) for number in numbers) or 'no chapters'}"
            )

        return chapter_number

    if not numbers:
        raise CleanChunksRefused("the material names no chapter, so a chunk cannot say which it belongs to")

    if len(set(numbers)) > 1:
        raise CleanChunksRefused(
            f"the material carries chapters {', '.join(str(number) for number in sorted(set(numbers)))} "
            f"and its source_chunks are one undivided list; which chunk belongs to which chapter "
            f"is not written down and this module may not guess. Name one with --chapter."
        )

    return numbers[0]


def emit_clean_chunks_file(
    *,
    slug: str,
    chapter_number: int,
    book_file: str | Path,
    output_file: str | Path,
) -> list[dict[str, Any]]:
    """Derive one chapter's chunks and write them, or write nothing."""
    location = Path(book_file)

    if not location.exists():
        raise CleanChunksRefused(f"the learning materials are not at {location}; nothing was derived")

    try:
        materials = json.loads(location.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CleanChunksRefused(f"{location} is not readable JSON: {error}") from error

    book_slug = str((materials.get("book") or {}).get("slug") or "").strip()

    if book_slug and book_slug != slug:
        raise CleanChunksRefused(
            f"{location} is book {book_slug!r} but the chunks were asked for under {slug!r}"
        )

    chunks = derive(materials, chapter_number=chapter_number)
    atomic_write_json(Path(output_file), chunks)

    return chunks


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Derive a chapter's clean-chunks file from its own learning materials."
    )
    parser.add_argument("--slug", required=True, help="domain pack slug, e.g. math5a")
    parser.add_argument("--chapter", type=int, help="chapter number; omit with --all")
    parser.add_argument("--all", action="store_true", help="every chapter the pack has materials for")
    parser.add_argument("--book", help="the learning materials to read (default: the path the pack declares)")
    parser.add_argument("--out", help="where to write the chunks (default: beside the materials)")

    args = parser.parse_args(argv)

    if args.all == (args.chapter is not None):
        print("refused: name exactly one of --chapter N or --all", file=sys.stderr)
        return 2

    if args.all and (args.book or args.out):
        print("refused: --book and --out name one file, so they cannot be used with --all", file=sys.stderr)
        return 2

    pack = domain_packs.get(args.slug)
    chapters = domain_packs.chapters_with_materials(pack) if args.all else [args.chapter]

    if not chapters:
        print(f"refused: no {args.slug} learning materials found at {pack.base_file}", file=sys.stderr)
        return 1

    for chapter in chapters:
        book_file = args.book or pack.base_path(chapter)
        output_file = args.out or clean_chunks_path(args.slug, chapter)

        try:
            chunks = emit_clean_chunks_file(
                slug=args.slug,
                chapter_number=chapter,
                book_file=book_file,
                output_file=output_file,
            )
        except CleanChunksRefused as error:
            print(f"refused: chapter {chapter}: {error}", file=sys.stderr)
            return 1

        print(f"wrote {output_file} ({len(chunks)} chunks from {book_file})")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
