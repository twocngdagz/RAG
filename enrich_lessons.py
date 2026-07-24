"""Turn a grounded lesson into a teaching-layer enrichment, end to end.

This orchestrates the loop we validated by hand for Lesson 1:

    grounded base JSON  ->  ChatGPT enrichment project  ->  teaching JSON
                        ->  output/pte.chapterNN.enrichment.json  ->  DB

The ChatGPT step is driven by ``ChatGPTDriver`` (Playwright on a dedicated,
persistent Chrome profile -- see ``chatgpt_browser_driver.py``). The project's
system prompt already knows what to do with a pasted lesson, so we only paste the
base payload and scrape the JSON it returns.

Point ``--project-url`` at the *project* URL (ends in ``/project``), not a single
chat: navigating there starts a fresh chat each time, so lessons never share
context. The scraped JSON is validated against the enrichment contract before it
is written or stored, so a malformed reply fails loudly instead of poisoning the DB.

Usage:
    # one-time: log into ChatGPT in the automation profile (headed)
    python chatgpt_browser_driver.py login

    # inspect the payload that would be pasted (no browser)
    python enrich_lessons.py payload 2

    # enrich one lesson (or several, sequentially) and load into the DB
    python enrich_lessons.py run --project-url "https://chatgpt.com/g/g-p-XXXX/project" 2

    # load an enrichment file that was produced/pasted by hand
    python enrich_lessons.py load 2
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PWError
from sqlalchemy.orm import Session

import book_learning_materials_store as store
from chatgpt_browser_driver import DEFAULT_PROFILE, ChatGPTDriver

BOOK_SLUG = "pte"
BASE_FILE = "output/pte.chapter{n:02d}.book_learning_materials.json"
ENRICH_FILE = "output/pte.chapter{n:02d}.enrichment.json"


# --------------------------------------------------------------------------- #
# 1. Build the grounded-base payload that gets pasted into the project.
# --------------------------------------------------------------------------- #

def _text(value: Any) -> str:
    """Read a grounded object's text, or a bare string, tolerating None."""
    if isinstance(value, dict):
        return (value.get("text") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def build_payload(chapter_number: int) -> str:
    """Render one chapter's grounded material as clean text for enrichment.

    Drops source_chunks and grounding bookkeeping -- the project only needs the
    teaching content, and the enrichment prompt synthesises the teaching layer.
    """
    path = Path(BASE_FILE.format(n=chapter_number))
    if not path.exists():
        raise FileNotFoundError(f"No grounded base for chapter {chapter_number}: {path}")
    ch = json.loads(path.read_text(encoding="utf-8"))["learning_materials"]["chapters"][0]

    out: list[str] = [
        "PTE LESSON (base learning material) — enrich this into the teaching-first version.",
        f"source_label: {BOOK_SLUG}:ch{chapter_number:02d}",
        f"chapter_number: {ch.get('chapter_number')}",
        f"lesson_title: {ch.get('chapter_title')}",
    ]
    est = _text(ch.get("estimated_study_time"))
    if est:
        out.append(f"estimated_study_time: {est}")
    if _text(ch.get("chapter_summary")):
        out.append(f"\nSUMMARY:\n{_text(ch.get('chapter_summary'))}")

    if ch.get("learning_objectives"):
        out.append("\nLEARNING OBJECTIVES:")
        out += [f"- {_text(o)}" for o in ch["learning_objectives"] if _text(o)]

    if ch.get("key_terms"):
        out.append("\nKEY TERMS:")
        out += [
            f"- {k['term']}: {_text(k.get('meaning'))}"
            for k in ch["key_terms"]
            if k.get("term") and _text(k.get("meaning"))
        ]

    if ch.get("core_lessons"):
        out.append("\nCORE LESSONS (the source teaching points):")
        for c in ch["core_lessons"]:
            exp = _text(c.get("explanation"))
            if exp:
                out.append(f"- {c['title']}: {exp}" if c.get("title") else f"- {exp}")

    if ch.get("worked_examples"):
        out.append("\nWORKED EXAMPLES (from source):")
        for w in ch["worked_examples"]:
            line = f"- {w.get('title')}: " if w.get("title") else "- "
            if _text(w.get("example")):
                line += f"Example: {_text(w.get('example'))} "
            if _text(w.get("explanation")):
                line += f"Explanation: {_text(w.get('explanation'))}"
            out.append(line.strip())

    if ch.get("common_misconceptions"):
        pairs = [
            m for m in ch["common_misconceptions"]
            if _text(m.get("misconception")) or _text(m.get("correction"))
        ]
        if pairs:
            out.append("\nCOMMON MISCONCEPTIONS / CORRECTIONS (from source):")
            for m in pairs:
                if _text(m.get("misconception")):
                    out.append(f"- Misconception: {_text(m.get('misconception'))}")
                if _text(m.get("correction")):
                    out.append(f"- Correction: {_text(m.get('correction'))}")

    if ch.get("practice_questions"):
        out.append("\nPRACTICE ITEMS (from source):")
        for p in ch["practice_questions"]:
            q = _text(p.get("question"))
            if q:
                a = _text(p.get("answer"))
                out.append(f"- Q: {q}" + (f"  A: {a}" if a else ""))

    if ch.get("review_checklist"):
        out.append("\nSELF-CHECK (from source):")
        out += [f"- {_text(r)}" for r in ch["review_checklist"] if _text(r)]

    # Reassert the output contract so a fresh project chat (no prior JSON turns in
    # its history) still returns machine-readable output instead of drifting to
    # prose/markdown tables.
    out.append(SCHEMA_CONTRACT)
    return "\n".join(out)


# The exact nested shape the frontend renders. The model reliably follows top-level
# keys but improvises inner field names unless they are spelled out, so pin every
# nested field explicitly (matches pte_lesson_enrichment.v1 / CoachView).
SCHEMA_CONTRACT = """
---
OUTPUT CONTRACT (follow EXACTLY). Reply with ONLY one fenced ```json code block:
a single valid pte_lesson_enrichment.v1 object. No prose, no markdown tables, and
no text before or after the code block. Use these keys and these nested field
names EXACTLY — do not rename, nest differently, or invent alternatives. Fill
every list with substantive content (aim for 4+ items each).

{
  "schema_version": "pte_lesson_enrichment.v1",
  "task_type": "<short string, e.g. 'summarize_written_text'>",
  "lesson_title": "<string>",
  "source_label": "<slug:chNN, exactly as given above>",
  "modality": "<reading|writing|speaking|listening|integrated>",
  "overview": {
    "what_it_is": "<string>",
    "format_facts": [{"label": "<string>", "value": "<string>"}],
    "scoring_factors": [{"name": "<string>", "what_it_measures": "<string>"}],
    "critical_rules": ["<string>"]
  },
  "learning_goals": ["<string>"],
  "core_method": {
    "name": "<string>",
    "summary": "<string>",
    "steps": [{"step": "<short name>", "detail": "<string>"}],
    "formula": "<string or null>"
  },
  "techniques": [{
    "name": "<string>", "purpose": "<string>",
    "how_to": ["<string>"],
    "example": "<string>", "why_it_matters": "<string>", "common_error": "<string>"
  }],
  "worked_examples": [{
    "title": "<string>", "input": "<string>", "decoding": "<string>",
    "plan": "<string>", "model_answer": "<string>",
    "annotations": [{"part": "<string>", "comment": "<string>"}]
  }],
  "useful_language": [{
    "category": "<string>",
    "items": [{"item": "<string>", "when_to_use": "<string>"}]
  }],
  "common_mistakes": [{"mistake": "<string>", "why_it_hurts": "<string>", "fix": "<string>"}],
  "practice_plan": {
    "time_budget": [{"phase": "<string>", "minutes": "<string>", "focus": "<string>"}],
    "drills": [{"name": "<string>", "instructions": "<string>"}],
    "routine": "<string>"
  },
  "mastery_checklist": ["<string>"],
  "strategy_notes": ["<string>"],
  "metadata": {
    "difficulty": "<string>", "estimated_study_time": "<string>",
    "tags": ["<string>"], "provenance_note": "<string>"
  }
}

Adapt content to this task type, but keep the shape identical. For non-speaking
tasks, model_answer may be a written sample or a worked selection; still provide
it as a string. useful_language must be a list of {category, items:[{item,
when_to_use}]} — for reading/selection tasks use signpost words, linkers, and
option-elimination phrases rather than leaving it empty.
"""


# --------------------------------------------------------------------------- #
# 2. Pull the JSON back out of the scraped reply.
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_CITATION_RE = re.compile(r"\s*:contentReference\[[^\]]*\]\{[^}]*\}")


def strip_citation_artifacts(obj: Any) -> Any:
    """Remove ChatGPT ``:contentReference[...]{...}`` citation markers that leak
    into string fields (e.g. provenance_note) and would render as garbage."""
    if isinstance(obj, str):
        return _CITATION_RE.sub("", obj).strip()
    if isinstance(obj, list):
        return [strip_citation_artifacts(x) for x in obj]
    if isinstance(obj, dict):
        return {k: strip_citation_artifacts(v) for k, v in obj.items()}
    return obj


def scrape_reply_json(page) -> str | None:
    """Read the last assistant message's code block straight from the DOM.

    More reliable than parsing rendered inner_text: the code element holds the
    raw JSON without ChatGPT's copy-button/label chrome.
    """
    js = """() => {
      const msgs = document.querySelectorAll("[data-message-author-role='assistant']");
      if (!msgs.length) return null;
      const last = msgs[msgs.length - 1];
      const code = last.querySelector('pre code');
      return code ? code.textContent : last.innerText;
    }"""
    return page.evaluate(js)


def extract_json_object(raw: str) -> dict[str, Any]:
    """Parse the enrichment object out of whatever text we scraped."""
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("Empty reply: nothing to parse.")

    # 1. straight parse (strict contract = the whole reply is the object).
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 2. a fenced ```json { ... } ``` block.
    m = _FENCE_RE.search(raw)
    if m:
        return json.loads(m.group(1))
    # 3. first balanced { ... } span.
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError(f"No JSON object found in reply ({len(raw)} chars).")


# The pte_lesson_enrichment.v1 shape the frontend CoachView renders. A fresh
# project chat sometimes improvises its own structure; anything missing these
# is off-schema and must be rejected before it reaches the DB/frontend.
REQUIRED_TOP_LEVEL_KEYS = {
    "task_type", "lesson_title", "modality", "overview", "learning_goals",
    "core_method", "techniques", "worked_examples", "useful_language",
    "common_mistakes", "practice_plan", "mastery_checklist", "strategy_notes",
    "metadata",
}
# The teaching sections that make a Coach page substantive. Others (useful_language,
# strategy_notes) are gracefully hidden by CoachView when empty, so they are
# optional — don't reject an otherwise-complete lesson over them.
REQUIRED_NONEMPTY_LISTS = (
    "learning_goals", "techniques", "worked_examples",
    "common_mistakes", "mastery_checklist",
)


def normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    """Coerce fields the model reports inconsistently but that need not fail a run.
    task_type comes back as a string, a list, null, or the schema name; the UI only
    displays it, so normalize to a non-empty string instead of rejecting the lesson."""
    tt = document.get("task_type")
    if isinstance(tt, list):
        document["task_type"] = " & ".join(str(x).strip() for x in tt if str(x).strip())
    elif not isinstance(tt, str) or not tt.strip():
        document["task_type"] = str(document.get("lesson_title") or "lesson_enrichment")
    return document


def validate_enrichment(document: dict[str, Any], chapter_number: int) -> None:
    """Fail loudly before writing/storing if the reply is off-contract."""
    meta = store.extract_enrichment_metadata(document)  # checks schema + source_label
    if meta["book_slug"] != BOOK_SLUG or meta["chapter_number"] != chapter_number:
        raise ValueError(
            f"Enrichment identifies as {meta['source_label']!r} but we asked for "
            f"{BOOK_SLUG}:ch{chapter_number:02d}. Refusing to store a mismatch."
        )
    missing = REQUIRED_TOP_LEVEL_KEYS - set(document)
    if missing:
        raise ValueError(
            f"Off-schema (not pte_lesson_enrichment.v1); missing keys: {sorted(missing)}. "
            f"The model likely invented its own structure."
        )
    if not isinstance(document.get("task_type"), str) or not document["task_type"].strip():
        raise ValueError("task_type must be a non-empty string.")
    for key in REQUIRED_NONEMPTY_LISTS:
        if not isinstance(document.get(key), list) or not document[key]:
            raise ValueError(f"'{key}' must be a non-empty list.")
    core = document.get("core_method")
    steps = core.get("steps") if isinstance(core, dict) else None
    if not isinstance(steps, list) or not all(isinstance(s, dict) and s.get("step") for s in steps):
        raise ValueError("core_method.steps must be a non-empty list of {step, detail} objects.")
    # Render-critical inner fields the frontend can't reconstruct from a wrong shape.
    for i, t in enumerate(document["techniques"]):
        if not isinstance(t, dict) or not isinstance(t.get("how_to"), list) or not t["how_to"]:
            raise ValueError(f"techniques[{i}].how_to must be a non-empty list (got wrong shape).")
    for i, w in enumerate(document["worked_examples"]):
        if not isinstance(w, dict) or not isinstance(w.get("model_answer"), str) or not w["model_answer"].strip():
            raise ValueError(f"worked_examples[{i}].model_answer must be a non-empty string.")


# --------------------------------------------------------------------------- #
# 3. Persist: file + DB.
# --------------------------------------------------------------------------- #

def write_enrichment_file(document: dict[str, Any], chapter_number: int) -> Path:
    path = Path(ENRICH_FILE.format(n=chapter_number))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_into_db(paths: list[Path], *, db_url: str) -> None:
    engine = store.create_db(db_url)
    with Session(engine) as session:
        for path in paths:
            rec = store.load_enrichment_file(session, path)
            print(f"  DB <- {path.name}  ({rec.id}, {rec.task_type})")
        session.commit()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def cmd_payload(args) -> int:
    for n in args.chapters:
        payload = build_payload(n)
        print(f"\n===== chapter {n} payload ({len(payload)} chars) =====\n")
        print(payload)
    return 0


def cmd_load(args) -> int:
    paths = []
    for n in args.chapters:
        p = Path(ENRICH_FILE.format(n=n))
        if not p.exists():
            print(f"! chapter {n}: {p} not found — skipping", file=sys.stderr)
            continue
        paths.append(p)
    if not paths:
        print("Nothing to load.", file=sys.stderr)
        return 1
    load_into_db(paths, db_url=args.db_url)
    return 0


def _pause_seconds(args) -> int:
    """How long to wait before the next request.

    Randomised inside [--cooldown, --cooldown-max] so the cadence isn't a fixed
    metronome. `max` is clamped up to the floor, so passing only --cooldown with a
    value above the default max still works instead of throwing.
    """
    lo = max(0, args.cooldown)
    if lo == 0:
        return 0  # 0 means disabled; don't let the max turn it back on
    hi = max(lo, getattr(args, "cooldown_max", lo))
    return random.randint(lo, hi)


def cmd_run(args) -> int:
    stored: list[int] = []
    failed: list[int] = []
    engine = store.create_db(args.db_url)
    # headless is fine for send once you've logged in via the driver's `login`.
    with ChatGPTDriver(args.profile_dir, headless=args.headless) as d:
        for i, n in enumerate(args.chapters):
            print(f"\n=== Lesson {n} ===")
            payload = build_payload(n)
            print(f"  payload: {len(payload)} chars -> sending to project (fresh chat)")
            raw = ""  # reset per-iteration so a failure never saves the prior reply
            document = None
            # Navigating to the project URL each time yields a fresh, prompt-primed chat.
            try:
                reply = d.send_and_wait(args.project_url, payload, timeout_s=args.timeout)
                raw = scrape_reply_json(d.page) or reply
                document = normalize_document(strip_citation_artifacts(extract_json_object(raw)))
                validate_enrichment(document, n)
            except (ValueError, json.JSONDecodeError, store.StoreError, RuntimeError, PWError) as exc:
                document = None
                debug = Path(f"output/_lesson{n:02d}.reply.txt")
                debug.write_text(raw or "", encoding="utf-8")
                print(f"  ! chapter {n} FAILED: {exc}\n    raw reply saved to {debug}", file=sys.stderr)
                failed.append(n)
                # A capped account can't produce anything — stop the batch instead
                # of burning more attempts, and say exactly what ChatGPT showed.
                notice = d.restriction_notice()
                if notice:
                    rest = args.chapters[i + 1:]
                    todo = failed + [m for m in rest if m not in failed]
                    print(
                        f"\n!! ChatGPT usage restriction detected: {notice!r}\n"
                        f"   Stopping the batch — the account is capped, retries would only add load.\n"
                        f"   Resume when the limit resets:  run … {' '.join(map(str, todo))}",
                        file=sys.stderr,
                    )
                    failed = todo
                    break
                if args.stop_on_error:
                    break

            if document is not None:
                # Persist immediately so a long run is never all-or-nothing.
                path = write_enrichment_file(document, n)
                with Session(engine) as s:
                    rec = store.load_enrichment_file(s, path)
                    s.commit()
                    rec_id = rec.id  # read inside the session; detaches on close
                print(f"  OK  wrote {path.name} + DB <- {rec_id} (task_type={document.get('task_type')})")
                stored.append(n)

            # Pace EVERY request, not just the ones that failed: each lesson is a
            # 30–60K-char generation, and it is cumulative volume that trips plan
            # limits. The run is unattended, so elapsed time costs nothing.
            if args.cooldown > 0 and i < len(args.chapters) - 1:
                delay = _pause_seconds(args)
                print(f"  waiting {delay // 60}m {delay % 60}s before the next lesson…")
                time.sleep(delay)

    print(f"\n{'='*48}\nDone: {len(stored)}/{len(args.chapters)} enriched and stored.")
    if stored:
        print(f"  stored: {stored}")
    if failed:
        print(f"  FAILED: {failed}  (re-run just these: run … {' '.join(map(str, failed))})")
    return 0 if not failed else 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enrich grounded lessons via a ChatGPT project.")
    p.add_argument("--db-url", default=store.DEFAULT_DB_URL)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("payload", help="Print the base payload (no browser).")
    sp.add_argument("chapters", type=int, nargs="+")
    sp.set_defaults(func=cmd_payload)

    sr = sub.add_parser("run", help="Drive ChatGPT, scrape, validate, store.")
    sr.add_argument("chapters", type=int, nargs="+")
    sr.add_argument("--project-url", required=True, help="ChatGPT project URL (ends /project).")
    sr.add_argument("--profile-dir", default=DEFAULT_PROFILE)
    sr.add_argument("--timeout", type=int, default=600)
    # Every request waits before the next one — not just after a failure. The run
    # is meant to go unattended overnight, where total elapsed time is free and
    # a steady human-paced cadence is the whole point. The wait is randomised
    # inside the window rather than a fixed number, so the gap between requests
    # isn't a metronome.
    sr.add_argument(
        "--cooldown", type=int, default=300,
        help="Minimum seconds to wait after every lesson before sending the next (0 disables).",
    )
    sr.add_argument(
        "--cooldown-max", type=int, default=600,
        help="Maximum seconds for that wait; the actual pause is random in "
             "[--cooldown, --cooldown-max]. Default 300-600s (5-10 min).",
    )
    sr.add_argument("--headless", action="store_true")
    sr.add_argument("--stop-on-error", action="store_true", help="Abort the batch on first failure.")
    sr.set_defaults(func=cmd_run)

    sl = sub.add_parser("load", help="Load existing enrichment files into the DB.")
    sl.add_argument("chapters", type=int, nargs="+")
    sl.set_defaults(func=cmd_load)

    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
