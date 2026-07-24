"""Turn the parsed Singapore Math 5A book into per-chapter grounded bases.

The enrichment pipeline consumes one `book_learning_materials` file per chapter.
This builds them for the maths book, which needs two things the PTE pipeline got
elsewhere: chapter boundaries, and source-faithful teaching content.

Chapter boundaries are taken from the BOOK'S OWN table of contents, not guessed.
The TOC lists printed page numbers, which differ from PDF page numbers by a fixed
offset; the offset is derived by matching a TOC entry against the page where that
heading actually appears, so a differently-scanned copy still lines up.

Content is EXTRACTED, not invented. The model is given one chapter's real text and
asked to pull out what is already there — objectives, terms, the methods taught,
the worked examples. Every chapter's verbatim source pages are carried in
`source_chunks`, so the enrichment layer downstream is always traceable back.

Two deterministic checks run before anything is written, because a maths base is
worth nothing if its sums are wrong:
  - every calculation in the extracted base must be arithmetically true
  - the base must actually contain content (no empty chapters)

Usage:
  python build_math_grounded_base.py --dry-run      # just show the chapter split
  python build_math_grounded_base.py                # build every chapter
  python build_math_grounded_base.py --chapters 3   # one chapter
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import httpx

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import domain_packs
import math_evaluators

ROOT = Path(__file__).resolve().parent
PARSED = ROOT / "output/singapore-math-5a.parsed.json"
SOURCE_PDF = "Singapore Math 5A Textbook"
OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"
SLUG = "math5a"


# --------------------------------------------------------------------------- #
# Chapter boundaries, from the book's own contents page
# --------------------------------------------------------------------------- #

# "Chapter 4 icon **Area of Triangle**" / "3 **Fractions**"
_TOC_CHAPTER = re.compile(r"^(?:Chapter\s+)?(\d+)\s*(?:icon\s*)?\*\*(.+?)\*\*", re.M)
# "**REVIEW A** 61"  — reviews are chapters too, they just aren't numbered
_TOC_REVIEW = re.compile(r"^\*\*(REVIEW [A-Z])\*\*\s*(\d+)", re.M)
# "1 Place Values 6" — a section entry, used to find where a chapter starts
_TOC_SECTION = re.compile(r"^(\d+)\s+([A-Z][^*\n]+?)\s+(\d+)\s*$", re.M)


def load_pages() -> list[dict[str, Any]]:
    return json.loads(PARSED.read_text(encoding="utf-8"))


def _page_offset(pages: list[dict[str, Any]], toc: str) -> int:
    """Printed page number minus PDF page number, derived by matching a heading.

    The TOC says "1 Place Values 6"; that heading really sits on PDF page 4, so
    the offset is 2. Derived rather than hardcoded so a different scan still works.
    """
    for num, title, printed in _TOC_SECTION.findall(toc):
        needle = title.strip().lower()
        for p in pages:
            for line in p["markdown"].split("\n"):
                line = line.strip()
                if line.startswith("#") and needle in line.lower():
                    return int(printed) - p["page"]
    raise RuntimeError("could not derive the page offset from the contents page")


def chapters(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every chapter with its PDF page range, in reading order."""
    toc = "\n".join(p["markdown"] for p in pages[:4])
    offset = _page_offset(pages, toc)

    marks: list[tuple[int, str]] = []   # (printed start page, title)
    for num, title in _TOC_CHAPTER.findall(toc):
        # a chapter starts at its first section's printed page
        after = toc.split(f"**{title}**", 1)[1]
        first = _TOC_SECTION.search(after)
        if first:
            marks.append((int(first.group(3)), f"{num} {title.strip()}"))
    for title, printed in _TOC_REVIEW.findall(toc):
        marks.append((int(printed), title))

    marks.sort()
    out = []
    for i, (printed, title) in enumerate(marks):
        start = printed - offset
        end = (marks[i + 1][0] - offset - 1) if i + 1 < len(marks) else len(pages)
        out.append({
            "chapter_number": i + 1,
            "chapter_title": title,
            "first_page": start,
            "last_page": end,
            "pages": end - start + 1,
        })
    return out


def chapter_text(pages: list[dict[str, Any]], ch: dict[str, Any]) -> str:
    return "\n\n".join(
        p["markdown"] for p in pages
        if ch["first_page"] <= p["page"] <= ch["last_page"]
    )


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #

SYSTEM = """You extract the teaching content that is ALREADY PRESENT in one chapter
of a Year 5 maths textbook. You are not writing new material and not teaching — a
later stage does that. You only pull out what the pages already contain.

Rules:
- Use only what is in the chapter text. Do not add methods, facts or examples the
  chapter does not contain.
- Every calculation you copy must be exactly right; it is checked automatically.
- Write EVERY calculation in LaTeX, inside dollar signs: $\\frac{3}{4}$, $11 \\div 4 = 2$,
  $2\\frac{3}{4}$. This is how the arithmetic gets checked; plain text like
  "11 / 4 = 2" cannot be verified and the chapter will be rejected.
- Plain words for a 10-year-old. Short sentences.
- If the chapter genuinely has nothing for a field, use an empty list.

STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block containing:
{"chapter_summary": "<2-3 sentences on what this chapter covers>",
 "estimated_study_time": "<e.g. '3 hours'>",
 "learning_objectives": ["<what a pupil should be able to do>"],
 "key_terms": [{"term": "<word>", "meaning": "<plain definition>"}],
 "core_lessons": [{"title": "<the method as the book names it>",
                   "explanation": "<how the book teaches it>"}],
 "worked_examples": [{"title": "<short>", "example": "<the problem and its working, from the book>",
                      "explanation": "<why each step happens>"}],
 "common_misconceptions": [{"misconception": "<a mistake this chapter warns about or invites>",
                            "correction": "<what is actually true>"}],
 "practice_questions": [{"question": "<a question from the chapter>", "answer": "<its answer>"}],
 "review_checklist": ["<'I can ...' statements>"]}

EXAMPLE of the notation required (shape only — copy the maths style, not this content).
Telling the model to use LaTeX was not enough on its own; this is what it must look like:

{"worked_examples": [
  {"title": "Change an improper fraction to a mixed number",
   "example": "$\\frac{11}{4} = 11 \\div 4 = 2\\frac{3}{4}$",
   "explanation": "Four goes into eleven twice, with 3 left over. The 3 left over stays over 4."},
  {"title": "Add fractions with different bottoms",
   "example": "$\\frac{1}{2} + \\frac{1}{4} = \\frac{2}{4} + \\frac{1}{4} = \\frac{3}{4}$",
   "explanation": "Change halves into quarters first, then add the top numbers."}],
 "practice_questions": [
  {"question": "Work out $\\frac{2}{3} \\times 6$.", "answer": "$\\frac{2}{3} \\times 6 = 4$"}]}

Every calculation sits inside $...$ so it can be checked. Never write "11 / 4 = 2" as
bare text.

DIVISION WITH A REMAINDER — write the remainder explicitly:
  RIGHT: $74 \\div 21 = 3 \\text{ r } 11$      (or "3 remainder 11")
  WRONG: $74 \\div 21 = 3$
The second is read as exact division and is false ($74 \\div 21$ is 3.52). Long
division is a whole topic in this book, so this matters: say the remainder."""

_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def extract(text: str, title: str, *, model: str) -> dict[str, Any]:
    key = os.environ.get("OLLAMA_API_KEY")
    if not key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    resp = httpx.post(
        OLLAMA_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "stream": False, "options": {"temperature": 0.2},
              "messages": [{"role": "system", "content": SYSTEM},
                           {"role": "user", "content": f"CHAPTER: {title}\n\n{text}"}]},
        timeout=600,
    )
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content", "")
    for cand in (raw, *(m.group(1) for m in _FENCE.finditer(raw))):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"no JSON in reply: {raw[:200]!r}")


# --------------------------------------------------------------------------- #
# Assemble + check
# --------------------------------------------------------------------------- #

_LIST_FIELDS = ("learning_objectives", "key_terms", "core_lessons", "worked_examples",
                "common_misconceptions", "practice_questions", "review_checklist")


def _grounded(text: str, pages: list[int]) -> dict[str, Any]:
    """A grounded leaf. Origin is source_grounded because the extractor was told to
    copy, and the pages it came from are recorded so the claim stays traceable."""
    return {
        "text": text,
        "claim_kind": "source_statement",
        "origin": "source_grounded",
        "source_chunk_ids": [f"{SLUG}:p{p}" for p in pages],
        "grounded_in_source_chunk_ids": [f"{SLUG}:p{p}" for p in pages],
        "evidence_spans": [],
        "reason": None,
    }


def build_document(ch: dict[str, Any], extracted: dict[str, Any],
                   pages: list[dict[str, Any]]) -> dict[str, Any]:
    page_ids = list(range(ch["first_page"], ch["last_page"] + 1))
    g = lambda t: _grounded(str(t), page_ids)

    chapter = {
        "chapter_number": ch["chapter_number"],
        "chapter_title": ch["chapter_title"],
        "estimated_study_time": g(extracted.get("estimated_study_time") or "2 hours"),
        "chapter_summary": g(extracted.get("chapter_summary") or ""),
        "learning_objectives": [g(o) for o in extracted.get("learning_objectives") or []],
        "key_terms": [{"term": k.get("term", ""), "meaning": g(k.get("meaning", ""))}
                      for k in extracted.get("key_terms") or []],
        "core_lessons": [{"title": c.get("title", ""), "explanation": g(c.get("explanation", ""))}
                         for c in extracted.get("core_lessons") or []],
        "worked_examples": [{"title": w.get("title", ""), "example": g(w.get("example", "")),
                             "explanation": g(w.get("explanation", ""))}
                            for w in extracted.get("worked_examples") or []],
        "common_misconceptions": [{"misconception": g(m.get("misconception", "")),
                                   "correction": g(m.get("correction", ""))}
                                  for m in extracted.get("common_misconceptions") or []],
        "practice_questions": [{"question": g(q.get("question", "")), "answer": g(q.get("answer", ""))}
                               for q in extracted.get("practice_questions") or []],
        "review_checklist": [g(r) for r in extracted.get("review_checklist") or []],
    }
    return {
        "schema_version": "book_learning_materials.v2",
        "book": {"slug": SLUG, "title": domain_packs.get(SLUG).title, "source_pdf": SOURCE_PDF},
        "generation": {"backend": "ollama", "model": DEFAULT_MODEL,
                       "note": "extracted from the LlamaParse output; teaching layer added downstream"},
        "learning_materials": {"chapters": [chapter]},
        "source_chunks": [
            {"node_id": f"{SLUG}:p{p['page']}", "text": p["markdown"]}
            for p in pages if ch["first_page"] <= p["page"] <= ch["last_page"]
        ],
        "audit": {"status": "extracted", "checks": []},
    }


def check(doc: dict[str, Any], source_checkable: int = 0) -> list[str]:
    """Deterministic gates before writing. A maths base with wrong sums is worse
    than no base at all."""
    problems = []
    ch = doc["learning_materials"]["chapters"][0]
    filled = [f for f in _LIST_FIELDS if ch.get(f)]
    questions = len(ch.get("practice_questions") or [])
    # A REVIEW chapter is four pages of exercises: no methods, no key terms,
    # nothing to extract but the questions themselves. Demanding four filled
    # sections rejected two legitimate chapters, so a substantial question bank
    # counts as content in its own right.
    if len(filled) < 4 and questions < 10:
        problems.append(f"only {len(filled)} of {len(_LIST_FIELDS)} content sections filled "
                        f"and only {questions} practice questions")

    # An arithmetic check that found nothing has said NOTHING about this chapter,
    # and the first build passed exactly that way. But the demand has to be
    # RELATIVE TO THE SOURCE: measured across this book, five of nine chapters
    # contain no checkable arithmetic at all — the Reviews are fill-in-the-blank
    # exercises, Ratio and Angles are conceptual. Requiring it unconditionally
    # would block legitimate chapters forever. So only insist when the source
    # chapter actually had arithmetic to carry across.
    checkable = math_evaluators.checkable_chain_count(ch)
    if source_checkable >= 3 and checkable == 0:
        problems.append(
            f"the source chapter has {source_checkable} verifiable calculations but the "
            f"extraction carried none across — write maths in LaTeX $...$ so it can be checked")
    for f in math_evaluators.arithmetic_findings(ch):
        problems.append(f.summary)
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chapters", type=int, nargs="*")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="retries per chapter when a reply comes back truncated")
    ap.add_argument("--dry-run", action="store_true", help="show the chapter split only")
    args = ap.parse_args(argv)

    pages = load_pages()
    chs = chapters(pages)
    pack = domain_packs.get(SLUG)

    print(f"{len(chs)} chapters across {len(pages)} pages\n")
    for c in chs:
        print(f"  ch{c['chapter_number']:02d}  p{c['first_page']:>3}-{c['last_page']:<3} "
              f"({c['pages']:>2}p)  {c['chapter_title']}")
    if args.dry_run:
        return 0

    wanted = set(args.chapters or [c["chapter_number"] for c in chs])
    failed = []
    for c in chs:
        if c["chapter_number"] not in wanted:
            continue
        print(f"\n=== ch{c['chapter_number']:02d} {c['chapter_title']} ===")
        text = chapter_text(pages, c)
        print(f"  source: {len(text):,} chars")
        extracted = None
        for attempt in range(1, args.max_attempts + 1):
            try:
                extracted = extract(text, c["chapter_title"], model=args.model)
                break
            except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                # A reply can come back truncated mid-JSON; that is worth another
                # go rather than losing the chapter.
                print(f"  ! attempt {attempt}/{args.max_attempts} failed: "
                      f"{str(exc)[:110]}", file=sys.stderr)
        if extracted is None:
            failed.append(c["chapter_number"])
            continue
        doc = build_document(c, extracted, pages)
        src_checkable = sum(
            1 for chain in math_evaluators._chains_in(text)
            if math_evaluators.check_chain(chain)[1] != "nothing checkable"
        )
        problems = check(doc, src_checkable)
        if problems:
            print(f"  ! rejected: {'; '.join(problems[:3])}", file=sys.stderr)
            failed.append(c["chapter_number"])
            continue
        out = Path(pack.base_path(c["chapter_number"]))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        ch = doc["learning_materials"]["chapters"][0]
        print(f"  OK  {out.name}  "
              f"({len(ch['core_lessons'])} lessons, {len(ch['worked_examples'])} examples, "
              f"{len(ch['practice_questions'])} questions, "
              f"{math_evaluators.checkable_chain_count(ch)}/{src_checkable} equations verified)")

    if failed:
        print(f"\nFAILED: {failed}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
