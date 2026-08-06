"""The clean-chunks file is derived from the book, not parsed again from the PDF.

The source contract checks a claim's citation against the passage it names, which
needs the passages in a file of their own. Chapter 3 had one because the PDF run
that produced it wrote one; the other eight chapters never did, and nothing about
them could be validated or exported.

The passages are not missing. Every chapter carries them, whole, under
`source_chunks` — so the repair is a transformation, not a second parse. The
property that makes it trustworthy is here: derived from chapter 3's own
material, the result is the file the PDF run wrote, byte for byte. A second
opinion about what the book says would not have matched.

    python test_clean_chunks_derivation.py
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import derive_clean_chunks
from book_learning_materials_contract import validate_book_contract

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


# Committed fixtures, not output/ — that directory is gitignored, so a test
# reading from it passes here and finds nothing on a clean checkout.
ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures" / "b11"
BOOK_FILE = FIXTURES / "math5a.chapter03.book_learning_materials.json"
CHUNKS_FILE = FIXTURES / "math5a.chapter03.clean_chunks.json"
SOURCE = json.loads(BOOK_FILE.read_text())


def without(**changes) -> dict:
    """The real material with one thing changed, so each refusal has one cause."""
    broken = copy.deepcopy(SOURCE)
    broken.update(changes)

    return broken


def refuses(materials: dict, label: str, fragment: str = "") -> None:
    try:
        derive_clean_chunks.derive(materials)
        check(label, False, "it derived")
    except derive_clean_chunks.CleanChunksRefused as error:
        check(label, fragment in str(error), str(error)[:140])


print("the derived file is the file the PDF run wrote")

derived = derive_clean_chunks.derive(SOURCE)

check("one clean chunk per source chunk", len(derived) == len(SOURCE["source_chunks"]), str(len(derived)))
check(
    "derived from the chapter's own passages, it is the existing file",
    derived == json.loads(CHUNKS_FILE.read_text()),
    "the derivation and the parsed file disagree about what the book says",
)
# Byte-for-byte, not merely equal as JSON: the file is read by a validator and
# committed beside the material, and a rewrite that reshuffled its keys on every
# run would show up as a change to content that did not change.
check(
    "and it is that file byte for byte",
    json.dumps(derived, indent=2, ensure_ascii=False) + "\n" == CHUNKS_FILE.read_text(),
    "same data, different bytes",
)
check(
    "same input, same output",
    derive_clean_chunks.derive(SOURCE) == derived,
    "two derivations from one material disagreed",
)

print("\nthe two fields it adds are the two a chunk is checked against")

check(
    "every chunk says which book it came from",
    {chunk["source_pdf"] for chunk in derived} == {SOURCE["book"]["source_pdf"]},
    str({chunk["source_pdf"] for chunk in derived}),
)
check(
    "every chunk says which chapter it belongs to",
    {chunk["chapter_number"] for chunk in derived} == {3},
    str({chunk["chapter_number"] for chunk in derived}),
)
check(
    "and the chapter it says is the one the material declares",
    derive_clean_chunks.derive(SOURCE, chapter_number=3) == derived,
    "naming the chapter explicitly changed the answer",
)

print("\nthe derived file is what the source contract reads")

with tempfile.TemporaryDirectory() as workspace:
    chunks_file = Path(workspace) / "derived.clean_chunks.json"
    derive_clean_chunks.emit_clean_chunks_file(
        slug="math5a",
        chapter_number=3,
        book_file=BOOK_FILE,
        output_file=chunks_file,
    )

    check(
        "the file written is the derivation, unreshaped",
        chunks_file.read_text() == CHUNKS_FILE.read_text(),
        "the writer changed what the deriver produced",
    )

    audit = validate_book_contract(book_file=BOOK_FILE, clean_chunks_file=chunks_file)
    check("chapter 3 passes the source contract against it", audit.get("status") == "PASS", str(audit.get("status")))

print("\nwhat it refuses, because the alternative is a check that passes on anything")

refuses(
    without(source_chunks=[]),
    "a chapter carrying no passages is refused",
    "source_chunks is empty",
)
refuses(
    without(book={**SOURCE["book"], "source_pdf": ""}),
    "material that does not name its book is refused",
    "book.source_pdf is missing",
)
refuses(
    without(source_chunks=[{"text": "a passage with no id"}]),
    "a passage nothing can cite is refused",
    "has no node id",
)
refuses(
    without(source_chunks=[dict(SOURCE["source_chunks"][0]), dict(SOURCE["source_chunks"][0])]),
    "two passages under one id are refused",
    "repeats node id",
)
refuses(
    without(source_chunks=[{"node_id": "math5a:p31", "text": "   "}]),
    "a passage with no text is refused",
    "has no text",
)

# Every chunk in one undivided list, and two chapters to divide it between. Which
# passage belongs to which is not written anywhere, so it is refused rather than
# split by a rule nobody wrote.
two_chapters = copy.deepcopy(SOURCE)
second = copy.deepcopy(two_chapters["learning_materials"]["chapters"][0])
second["chapter_number"] = 4
two_chapters["learning_materials"]["chapters"].append(second)

refuses(two_chapters, "a file carrying two chapters is refused", "is not written down")

check(
    "unless one of them is named",
    len(derive_clean_chunks.derive(two_chapters, chapter_number=4)) == len(derived),
    "naming a chapter did not resolve it",
)

try:
    derive_clean_chunks.derive(SOURCE, chapter_number=7)
    check("a chapter the material does not have is refused", False, "it derived")
except derive_clean_chunks.CleanChunksRefused as error:
    check("a chapter the material does not have is refused", "no chapter 7" in str(error), str(error)[:120])

print("\nthe command writes, or refuses and writes nothing")

with tempfile.TemporaryDirectory() as workspace:
    written = Path(workspace) / "chapter03.clean_chunks.json"
    run = subprocess.run(
        [sys.executable, str(ROOT / "derive_clean_chunks.py"),
         "--slug", "math5a", "--chapter", "3", "--book", str(BOOK_FILE), "--out", str(written)],
        capture_output=True, text=True, cwd=ROOT,
    )
    check("the command exits 0", run.returncode == 0, run.stderr[-200:])
    check("and writes the derivation", written.exists() and written.read_text() == CHUNKS_FILE.read_text(), run.stdout)

    nothing = Path(workspace) / "not-written.json"
    empty = Path(workspace) / "no-passages.json"
    empty.write_text(json.dumps(without(source_chunks=[])))
    refused = subprocess.run(
        [sys.executable, str(ROOT / "derive_clean_chunks.py"),
         "--slug", "math5a", "--chapter", "3", "--book", str(empty), "--out", str(nothing)],
        capture_output=True, text=True, cwd=ROOT,
    )
    check("a refusal exits 1", refused.returncode == 1, str(refused.returncode))
    check("and writes nothing", not nothing.exists(), "a file was written anyway")
    check("and says which chapter and why", "chapter 3" in refused.stderr and "source_chunks" in refused.stderr,
          refused.stderr[:160])


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the chunks are the book's own passages, not a second reading of the PDF")
raise SystemExit(1 if fails else 0)
