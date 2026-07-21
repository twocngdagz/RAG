"""Audit the exam facts asserted in the enrichment (teaching) layer.

The grounded base has an extract -> resolve -> semantic-audit chain proving every
claim traces to the book. The enrichment layer had no equivalent: its value comes
precisely from facts added BEYOND the book (timings, word counts, question
counts, scoring traits), and nothing verified them. Two hallucinations have
already been caught by hand.

This closes that gap using the same shape, with Pearson's official Score Guide as
the evidence:

  extract claims (code)  ->  gather the guide text for that task type (code)
  ->  semantic judge with the guide excerpt as the ONLY evidence (model)
  ->  report SUPPORTED / CONTRADICTED / NOT_IN_GUIDE

A CONTRADICTED verdict is a real defect. NOT_IN_GUIDE is not an error — the guide
does not state every timing — but it marks a claim as unverified, which is itself
worth knowing.

Usage:
  export OLLAMA_API_KEY=...                       # or .env
  python audit_enrichment_facts.py --guide /path/to/PTE-Score-Guide.pdf
  python audit_enrichment_facts.py --chapters 7 6 9      # subset
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

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"
DEFAULT_GUIDE = str(Path.home() / "Downloads" / "PTE-Academic-Test-Taker-Score-Guide.pdf")
REPORT_FILE = "output/enrichment_fact_audit.json"

# Our task_type -> the question-type names as they appear in the Score Guide.
TASK_ALIASES: dict[str, list[str]] = {
    "answer_short_question": ["Answer Short Question"],
    "read_aloud_repeat_sentence": ["Read Aloud", "Repeat Sentence"],
    "reading_fill_in_the_blanks": ["Fill in the Blanks", "Reading:"],
    "reading_multiple_choice": ["Multiple Choice, Single Answer", "Multiple Choice, Multiple Answers"],
    "select_missing_word_and_highlight_incorrect_words": [
        "Select Missing Word",
        "Highlight Incorrect Words",
    ],
    "summarize_written_text": ["Summarize Written Text"],
    "write_essay": ["Write Essay"],
    "describe_image": ["Describe Image"],
    "re_order_paragraphs": ["Reorder Paragraph"],
    "listening_fill_in_the_blanks_and_write_from_dictation": [
        "Write from Dictation",
        "Fill in the Blanks",
    ],
    "listening_multiple_choice": ["Multiple Choice, Single Answer", "Multiple Choice, Multiple Answers"],
    "retell_lecture": ["Retell Lecture", "Re-tell Lecture"],
    "summarize_spoken_text_and_highlight_correct_summary": [
        "Summarize Spoken Text",
        "Highlight Correct Summary",
    ],
    "summarize_group_discussion": ["Summarize Group Discussion"],
    "respond_to_a_situation": ["Respond to a Situation"],
}

NUM_RE = re.compile(r"\d")


# --------------------------------------------------------------------------- #
# Evidence: the official guide, indexed by question type
# --------------------------------------------------------------------------- #

def load_guide_pages(path: str) -> list[str]:
    from pypdf import PdfReader

    return [(p.extract_text() or "") for p in PdfReader(path).pages]


def _flat(s: str) -> str:
    """Collapse whitespace for matching: the PDF wraps question-type names across
    lines ("Summarize \\nWritten Text"), so naive substring matching silently
    misses the very pages that hold the rubric."""
    return re.sub(r"\s+", " ", s).lower()


# p.15 lists every question type in one human-review note. It matches every task
# and carries trait names belonging to *other* tasks, so it is useful context for
# the judge but must never be read as this task's rubric.
GENERIC_MENTION_PAGE = 15


def guide_text_for(task_type: str, pages: list[str], max_chars: int = 24000,
                   *, rubric_only: bool = False) -> tuple[str, list[int]]:
    """The guide pages that mention this question type, plus their page numbers so
    the report can cite them. Falls back to the scoring-overview pages."""
    names = TASK_ALIASES.get(task_type, [])
    hits = [
        (i + 1, t)
        for i, t in enumerate(pages)
        if names and any(_flat(n) in _flat(t) for n in names)
    ]
    matched = bool(hits)
    # Page 15 only *mentions* question types (the human-review note); real rubric
    # pages matter more, so order them first — truncation must never drop the
    # rubric and leave the mention, which produced a false contradiction.
    hits.sort(key=lambda h: (h[0] == GENERIC_MENTION_PAGE, h[0]))
    if rubric_only:
        hits = [h for h in hits if h[0] != GENERIC_MENTION_PAGE]
    if not hits:
        hits = [(i + 1, t) for i, t in enumerate(pages) if "scoring" in _flat(t)][:4]
    text = "\n\n".join(t for _, t in hits)
    return text[:max_chars], [n for n, _ in hits], matched


# --------------------------------------------------------------------------- #
# Deterministic check: official trait vocabulary
# --------------------------------------------------------------------------- #

# Pearson's own trait names. A lesson is free to describe scoring in its own
# teaching words ("Main-idea coverage"), and those are not checkable here. But
# when a lesson uses one of Pearson's ACTUAL trait names, that name has to belong
# to the task — claiming a writing task is scored on Oral Fluency is a defect.
#
# This is deterministic on purpose. The model judge would not treat the guide's
# "Traits scored" list as closed no matter how the prompt was worded, and tuning
# the prompt to force it swung the whole audit between "flags everything" and
# "flags nothing". Mechanical checks belong in code.
OFFICIAL_TRAITS = (
    "content", "form", "grammar", "vocabulary", "spelling",
    "oral fluency", "pronunciation", "appropriacy",
    "development, structure and coherence", "general linguistic range",
    "vocabulary range", "linguistic range",
)

_TRAIT_HEADING_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in OFFICIAL_TRAITS) + r")\s*:", re.IGNORECASE
)


def guide_traits(evidence: str) -> set[str]:
    """Official trait names the guide heads a scoring band with, e.g. 'Form:'."""
    flat = re.sub(r"\s+", " ", evidence)
    return {m.group(1).lower() for m in _TRAIT_HEADING_RE.finditer(flat)}


def check_trait_vocabulary(doc: dict[str, Any], evidence: str) -> list[dict[str, str]]:
    """Lesson scoring factors that borrow an official trait name the guide does
    not list for this task. Teaching-level paraphrases are ignored."""
    listed = guide_traits(evidence)
    if not listed:
        return []
    defects = []
    for s in (doc.get("overview") or {}).get("scoring_factors") or []:
        if not isinstance(s, dict) or not s.get("name"):
            continue
        name = str(s["name"]).strip().lower()
        if name in OFFICIAL_TRAITS and name not in listed:
            defects.append({
                "factor": str(s["name"]),
                "reason": (
                    f"'{s['name']}' is an official PTE trait name, but the guide's "
                    f"traits for this task are: {', '.join(sorted(listed))}."
                ),
            })
    return defects


# --------------------------------------------------------------------------- #
# Deterministic check: the word range that gates Form
# --------------------------------------------------------------------------- #

# Guide wordings: "2 Length is between 200 and 300 words" / "2 Contains 50-70 words".
_FORM_BAND_RE = re.compile(r"Form:\s*2\s*(.{0,80}?)(?=\s+1\s)", re.IGNORECASE)
# Lessons write ranges several ways: "50-70 words", "between 200 and 300 words",
# "200 to 300 words", "the required 200-to-300-word range". Missing the last form
# made this check report a lesson that stated the range perfectly well.
_RANGE_RE = re.compile(
    r"(\d{1,4})\s*(?:[-–]\s*to\s*[-–]?|[-–]|to|and)\s*(\d{1,4})[-\s]*words?",
    re.IGNORECASE,
)


def guide_word_range(rubric_evidence: str) -> tuple[int, int] | None:
    """The word range that earns full Form credit, if the task has one."""
    flat = re.sub(r"\s+", " ", rubric_evidence)
    band = _FORM_BAND_RE.search(flat)
    if not band:
        return None
    m = _RANGE_RE.search(band.group(1))
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_word_range(doc: dict[str, Any], rubric_evidence: str) -> list[dict[str, str]]:
    """Where the guide gates Form on a word range, the lesson has to state that
    range. Lesson 15 shipped telling learners to 'verify word-count compliance'
    without ever saying what the count was — a missing number, which no
    compare-the-numbers check would ever have caught."""
    rng = guide_word_range(rubric_evidence)
    if not rng:
        return []
    ov = doc.get("overview") or {}
    hay = " ".join(
        [str(f.get("value", "")) for f in ov.get("format_facts") or [] if isinstance(f, dict)]
        + [str(r) for r in ov.get("critical_rules") or []]
    )
    if any((int(a), int(b)) == rng for a, b in _RANGE_RE.findall(hay)):
        return []
    return [{
        "range": f"{rng[0]}-{rng[1]}",
        "reason": (
            f"The guide gives full Form credit for {rng[0]}-{rng[1]} words, and Form "
            f"gates the whole response. The lesson never states this range."
        ),
    }]


# --------------------------------------------------------------------------- #
# Claims: what the enrichment asserts about the exam
# --------------------------------------------------------------------------- #

def extract_claims(doc: dict[str, Any]) -> list[dict[str, str]]:
    """The checkable, high-risk assertions: format facts, the scoring traits it
    names, and any critical rule stating a number."""
    claims: list[dict[str, str]] = []
    ov = doc.get("overview") or {}
    for f in ov.get("format_facts") or []:
        if isinstance(f, dict) and f.get("label"):
            claims.append({
                "kind": "format_fact",
                "text": f"{f.get('label')}: {f.get('value')}",
            })
    # scoring_factors are teaching-level descriptions of what the scoring cares
    # about — NOT a claim to reproduce Pearson's official trait names. Rolling
    # them into "this task is scored on these traits: ..." invented a stronger
    # claim than the lesson makes, and every combined lesson (one chapter, two
    # question types) failed it. Judge each factor on its own, as asserted.
    for s in ov.get("scoring_factors") or []:
        if isinstance(s, dict) and s.get("name"):
            claims.append({
                "kind": "scoring_factor",
                "text": (
                    f"Scoring for this task takes into account "
                    f"{s.get('name')}: {s.get('what_it_measures')}"
                ),
            })
    for r in ov.get("critical_rules") or []:
        if isinstance(r, str) and NUM_RE.search(r):
            claims.append({"kind": "critical_rule", "text": r})
    return claims


# --------------------------------------------------------------------------- #
# Judge
# --------------------------------------------------------------------------- #

SYSTEM = """You verify claims made by PTE Academic study material against the
official Pearson Score Guide.

You are given an EXCERPT of the official guide and a list of CLAIMS. Judge each
claim using ONLY that excerpt. You have no other source and must not rely on prior
knowledge of PTE.

For each claim return one verdict:
- "SUPPORTED": the excerpt states this, or states something that clearly entails it.
- "CONTRADICTED": the excerpt states something incompatible with the claim.
- "NOT_IN_GUIDE": the excerpt does not address the claim either way.

Be strict about numbers: if the claim gives a figure (a count, a time, a word
range, a score range) and the excerpt gives a different figure for the same thing,
that is CONTRADICTED, not NOT_IN_GUIDE. If the excerpt simply does not mention the
figure, that is NOT_IN_GUIDE.

CONTRADICTED means incompatible, not merely different. Do NOT use it for a claim
that is a paraphrase, is worded differently, lists the same items in a different
order, or is narrower or broader than the excerpt while remaining consistent with
it. Those are SUPPORTED. Reserve CONTRADICTED for claims the excerpt rules out.

One lesson may cover more than one question type. A claim that plainly belongs to
a different question type than the one the excerpt describes is NOT_IN_GUIDE, not
CONTRADICTED.

Where the excerpt gives a COMPLETE enumeration — a "Traits scored" list, a table
of score bands — treat it as closed for that question type. A claim asserting a
trait or band outside that list is CONTRADICTED, not NOT_IN_GUIDE.

Scoring tables are statements. If a claim restates what a band says, that is
SUPPORTED — do not downgrade it to NOT_IN_GUIDE merely because the claim is
phrased as advice ("must", "should", "keep it") while the excerpt is phrased as a
band ("2 Contains 50-70 words"). Judge the substance, not the wording.

Quote the exact words of the excerpt you relied on; leave the quote empty for
NOT_IN_GUIDE.

STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block containing
{"verdicts": [{"index": <int>, "verdict": "<SUPPORTED|CONTRADICTED|NOT_IN_GUIDE>",
"quote": "<exact words from the excerpt, or empty>", "note": "<short>"}]} —
exactly one verdict per claim index."""

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    text = (text or "").strip()
    for cand in (text, *(m.group(1) for m in _FENCE_RE.finditer(text))):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j > i:
        return json.loads(text[i : j + 1])
    raise ValueError("no JSON in reply")


def judge(claims: list[dict[str, str]], evidence: str, *, model: str, attempts: int = 2) -> list[dict[str, Any]]:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    listed = "\n".join(f"{i}. [{c['kind']}] {c['text']}" for i, c in enumerate(claims))
    user = f"OFFICIAL GUIDE EXCERPT:\n{evidence}\n\nCLAIMS:\n{listed}\n\nJudge every claim now."
    last: Exception | None = None
    for _ in range(attempts):
        try:
            resp = httpx.post(
                OLLAMA_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    # 0, not 0.1: at 0.1 the same planted claim flipped between
                    # CONTRADICTED and NOT_IN_GUIDE across runs, which makes
                    # any single clean report unreproducible.
                    "options": {"temperature": 0},
                },
                timeout=300.0,
            )
            resp.raise_for_status()
            data = extract_json(resp.json().get("message", {}).get("content", ""))
            verdicts = data.get("verdicts", []) if isinstance(data, dict) else data
            by_i = {v.get("index"): v for v in verdicts if isinstance(v, dict)}
            return [
                {
                    **c,
                    "verdict": (by_i.get(i, {}).get("verdict") or "NOT_IN_GUIDE").upper(),
                    "quote": by_i.get(i, {}).get("quote", ""),
                    "note": by_i.get(i, {}).get("note", ""),
                }
                for i, c in enumerate(claims)
            ]
        except Exception as exc:
            last = exc
    raise RuntimeError(f"judge failed after {attempts} attempts: {last}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    p = argparse.ArgumentParser(description="Audit enrichment exam facts against the official guide.")
    p.add_argument("--guide", default=DEFAULT_GUIDE)
    p.add_argument("--chapters", type=int, nargs="*")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default=REPORT_FILE)
    args = p.parse_args(argv)

    if not Path(args.guide).exists():
        print(f"Score Guide not found at {args.guide}", file=sys.stderr)
        return 2
    pages = load_guide_pages(args.guide)
    print(f"Loaded guide: {len(pages)} pages\n")

    chapters = args.chapters or [
        int(m.group(1))
        for m in sorted(
            (re.search(r"chapter(\d+)\.enrichment", str(p)) for p in Path("output").glob("pte.chapter*.enrichment.json")),
            key=lambda m: int(m.group(1)) if m else 0,
        )
        if m
    ]

    report, skipped = [], []
    totals = {"SUPPORTED": 0, "CONTRADICTED": 0, "NOT_IN_GUIDE": 0}
    for n in chapters:
        path = Path(f"output/pte.chapter{n:02d}.enrichment.json")
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        task = doc.get("task_type", "")
        claims = extract_claims(doc)
        if not claims:
            continue
        if task not in TASK_ALIASES:
            print(f"L{n:<2} {task[:34]:36} skipped — no matching question type in the guide")
            skipped.append({"chapter": n, "task_type": task, "reason": "no guide question type"})
            continue
        evidence, ev_pages, matched = guide_text_for(task, pages)
        if not matched:
            print(f"L{n:<2} {task[:34]:36} skipped — guide section not located")
            skipped.append({"chapter": n, "task_type": task, "reason": "guide section not located"})
            continue
        try:
            judged = judge(claims, evidence, model=args.model)
        except Exception as exc:
            print(f"L{n}: audit failed — {exc}", file=sys.stderr)
            continue
        # Trait names must come from this task's own rubric pages — p.15 names
        # traits belonging to other tasks and would mask a real mismatch.
        rubric_ev, _, _ = guide_text_for(task, pages, rubric_only=True)
        trait_defects = check_trait_vocabulary(doc, rubric_ev)
        trait_defects += check_word_range(doc, rubric_ev)
        counts = {k: sum(1 for j in judged if j["verdict"] == k) for k in totals}
        for k in totals:
            totals[k] += counts[k]
        print(
            f"L{n:<2} {task[:34]:36} "
            f"supported={counts['SUPPORTED']:<2} contradicted={counts['CONTRADICTED']:<2} "
            f"not-in-guide={counts['NOT_IN_GUIDE']:<2} (guide pp.{ev_pages})"
        )
        for j in judged:
            if j["verdict"] == "CONTRADICTED":
                print(f"     !! {j['text'][:88]}")
                print(f"        guide says: {j['quote'][:88]}")
        for d in trait_defects:
            print(f"     !! {d.get('factor') or ('missing word range ' + d.get('range',''))}")
            print(f"        {d['reason'][:96]}")
        report.append({"chapter": n, "task_type": task, "guide_pages": ev_pages,
                       "claims": judged, "counts": counts,
                       "trait_defects": trait_defects})

    print(f"\n{'='*60}\nTotals: {totals}")
    if skipped:
        print(f"Not auditable ({len(skipped)}): " + ", ".join(f"L{x['chapter']}" for x in skipped))
    contradicted = [
        (r["chapter"], c) for r in report for c in r["claims"] if c["verdict"] == "CONTRADICTED"
    ]
    trait_defects = [(r["chapter"], d) for r in report for d in r["trait_defects"]]
    if contradicted or trait_defects:
        total = len(contradicted) + len(trait_defects)
        print(f"\n{total} defect(s) to fix:")
        for n, c in contradicted:
            print(f"  L{n}: {c['text'][:90]}")
        for n, d in trait_defects:
            what = (f"wrong trait name '{d['factor']}'" if d.get("factor")
                    else f"never states the {d['range']} word range that gates Form")
            print(f"  L{n}: {what}")
    else:
        print("\nNo defects. (Only meaningful if test_audit_sensitivity.py passes.)")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps({"totals": totals,
                    "trait_defects": [{"chapter": n, **d} for n, d in trait_defects],
                    "lessons": report, "skipped": skipped}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nFull report -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
