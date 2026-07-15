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
import re
import sys
from pathlib import Path
from typing import Any

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

    return "\n".join(out)


# --------------------------------------------------------------------------- #
# 2. Pull the JSON back out of the scraped reply.
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


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


def validate_enrichment(document: dict[str, Any], chapter_number: int) -> None:
    """Fail loudly before writing/storing if the reply is off-contract."""
    meta = store.extract_enrichment_metadata(document)  # checks schema + source_label
    if meta["book_slug"] != BOOK_SLUG or meta["chapter_number"] != chapter_number:
        raise ValueError(
            f"Enrichment identifies as {meta['source_label']!r} but we asked for "
            f"{BOOK_SLUG}:ch{chapter_number:02d}. Refusing to store a mismatch."
        )


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


def cmd_run(args) -> int:
    stored: list[Path] = []
    # headless is fine for send once you've logged in via the driver's `login`.
    with ChatGPTDriver(args.profile_dir, headless=args.headless) as d:
        for n in args.chapters:
            print(f"\n=== Lesson {n} ===")
            payload = build_payload(n)
            print(f"  payload: {len(payload)} chars -> sending to project (fresh chat)")
            # Navigating to the project URL each time yields a fresh, prompt-primed chat.
            reply = d.send_and_wait(args.project_url, payload, timeout_s=args.timeout)
            raw = scrape_reply_json(d.page) or reply
            try:
                document = extract_json_object(raw)
                validate_enrichment(document, n)
            except (ValueError, json.JSONDecodeError, store.StoreError) as exc:
                debug = Path(f"output/_lesson{n:02d}.reply.txt")
                debug.write_text(raw or "", encoding="utf-8")
                print(f"  ! chapter {n} failed: {exc}\n    raw reply saved to {debug}", file=sys.stderr)
                if args.stop_on_error:
                    return 1
                continue
            path = write_enrichment_file(document, n)
            print(f"  wrote {path}  (task_type={document.get('task_type')})")
            stored.append(path)

    if stored:
        print("\nLoading into DB…")
        load_into_db(stored, db_url=args.db_url)
        print(f"\nDone: {len(stored)}/{len(args.chapters)} lesson(s) enriched and stored.")
    return 0 if len(stored) == len(args.chapters) else 1


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
    sr.add_argument("--timeout", type=int, default=300)
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
