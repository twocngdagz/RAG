"""Generate PTE Reading Multiple-Choice practice items with a verified answer key.

Multiple choice only helps a learner if the key is right. A model asked to write
a question AND its answer will happily produce an item with two defensible
options, or mark the wrong one — and nothing about the JSON looks broken. So the
key is never trusted as written:

  model writes passage + question + options + key   (generation)
  -> contract-validate: shape, option count, key in range          (code)
  -> BLIND SOLVE: independent solvers see the passage, question and options
     but NOT the key, and answer it cold                           (model)
  -> keep the item only if every solver lands on the written key   (code)

A solver that disagrees means the item is ambiguous or the key is wrong; either
way the learner must never see it. Disagreement is the signal, so the solve is
run several times and unanimity is required.

Both PTE reading multiple-choice forms are produced:
  single   — one correct option, scored 1 or 0
  multiple — several correct, scored +1 per correct and -1 per wrong, floored at 0

Usage:
  export OLLAMA_API_KEY=...      # or .env
  python reading_mcq_items.py --count 8 --dry-run
  python reading_mcq_items.py --count 8
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"
OUTPUT_FILE = "output/reading_mcq_items.json"

# Independent blind solves per item, and how many must match the key.
SOLVER_RUNS = 3
SOLVER_AGREEMENT = 3          # unanimous — an item any solver misreads is ambiguous

OPTION_KEYS = ("A", "B", "C", "D", "E")
SINGLE_OPTIONS = 4
MULTI_OPTIONS = 5
SKILLS = ("main idea", "detail", "inference", "author's purpose", "tone")


# --------------------------------------------------------------------------- #
# Model plumbing
# --------------------------------------------------------------------------- #

def _chat(messages: list[dict[str, str]], *, model: str, temperature: float,
          timeout: float = 240.0) -> str:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    resp = httpx.post(
        OLLAMA_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "stream": False,
              "options": {"temperature": temperature}},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", re.DOTALL)


def extract_json(text: str) -> Any:
    text = (text or "").strip()
    for candidate in (text, *(m.group(1) for m in _FENCE_RE.finditer(text))):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"No JSON object found in model output: {text[:200]!r}")


# --------------------------------------------------------------------------- #
# Generation
# --------------------------------------------------------------------------- #

GEN_SYSTEM = """You write PTE Academic Reading Multiple-Choice practice items.

Write like an academic textbook or a quality science/social-science magazine:
neutral register, third person, no direct address, no lists, no headings.

Rules that decide whether the item is usable:
- The answer must be derivable from the passage ALONE. No outside knowledge.
- Exactly one defensible reading. A distractor must be clearly wrong to a careful
  reader — not merely less good than the key.
- Distractors must be plausible and drawn from the passage's vocabulary, so that
  skimming misleads but careful reading does not.
- Typical wrong-answer shapes: true but does not answer the question; contradicts
  the passage; overstates with "all"/"never"/"proves"; plausible outside fact the
  passage never states.
- Never signal the key with length, hedging or giveaway wording.

STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block."""


def gen_prompt(mode: str, count: int, avoid: list[str]) -> str:
    n_opts = SINGLE_OPTIONS if mode == "single" else MULTI_OPTIONS
    keys = ", ".join(OPTION_KEYS[:n_opts])
    if mode == "single":
        correct_rule = ("Exactly ONE correct option. \"correct\" is a one-element list, "
                        "e.g. [\"C\"].")
        length = "180-230 words"
    else:
        correct_rule = ("TWO or THREE correct options — each independently and "
                        "verifiably true per the passage. \"correct\" lists them, "
                        "e.g. [\"A\", \"D\"].")
        length = "260-320 words"
    avoid_line = f"\nDo NOT reuse these topics: {', '.join(avoid)}." if avoid else ""

    return f"""Write {count} PTE Reading Multiple-Choice items, mode "{mode}".

Each item:
- "topic": 2-4 word subject label
- "title": short title for the passage
- "passage": {length}, academic register, self-contained
- "question": one clear question about the passage
- "skill": one of {", ".join(SKILLS)}
- "options": exactly {n_opts} objects, keys {keys}, each with "key" and "text"
- "correct": {correct_rule}
- "rationale": an object mapping EVERY option key to one sentence saying why it
  is correct or exactly what makes it wrong

Vary topic across the sciences, history, economics, environment and technology.{avoid_line}

Return ONLY:
```json
{{"items": [{{"topic": "...", "title": "...", "passage": "...", "question": "...",
"skill": "...", "options": [{{"key": "A", "text": "..."}}],
"correct": ["B"], "rationale": {{"A": "...", "B": "..."}}}}]}}
```"""


def generate(mode: str, count: int, *, model: str, avoid: list[str]) -> list[dict[str, Any]]:
    raw = _chat(
        [{"role": "system", "content": GEN_SYSTEM},
         {"role": "user", "content": gen_prompt(mode, count, avoid)}],
        model=model, temperature=0.9,
    )
    obj = extract_json(raw)
    items = obj.get("items") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        raise ValueError("Model did not return a list of items.")
    for it in items:
        if isinstance(it, dict):
            it["mode"] = mode
    return [it for it in items if isinstance(it, dict)]


# --------------------------------------------------------------------------- #
# Contract validation — shape only, in code
# --------------------------------------------------------------------------- #

def contract_validate(item: Any) -> tuple[bool, str]:
    if not isinstance(item, dict):
        return False, "not an object"
    mode = item.get("mode")
    if mode not in ("single", "multiple"):
        return False, f"bad mode {mode!r}"
    for field in ("topic", "title", "passage", "question", "skill"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            return False, f"missing {field}"

    words = len(item["passage"].split())
    lo, hi = (120, 300) if mode == "single" else (200, 400)
    if not lo <= words <= hi:
        return False, f"passage {words} words, want {lo}-{hi}"

    n_opts = SINGLE_OPTIONS if mode == "single" else MULTI_OPTIONS
    options = item.get("options")
    if not isinstance(options, list) or len(options) != n_opts:
        return False, f"want {n_opts} options, got {len(options) if isinstance(options, list) else 'none'}"
    keys = [o.get("key") for o in options if isinstance(o, dict)]
    if keys != list(OPTION_KEYS[:n_opts]):
        return False, f"option keys must be {list(OPTION_KEYS[:n_opts])}, got {keys}"
    if any(not isinstance(o.get("text"), str) or not o["text"].strip() for o in options):
        return False, "an option has no text"
    texts = [o["text"].strip().lower() for o in options]
    if len(set(texts)) != len(texts):
        return False, "duplicate option text"

    correct = item.get("correct")
    if not isinstance(correct, list) or not correct:
        return False, "no correct answer given"
    if len(set(correct)) != len(correct):
        return False, "duplicate keys in correct"
    if any(c not in OPTION_KEYS[:n_opts] for c in correct):
        return False, f"correct {correct} outside option keys"
    if mode == "single" and len(correct) != 1:
        return False, f"single-answer item has {len(correct)} correct options"
    if mode == "multiple" and not 2 <= len(correct) <= n_opts - 1:
        return False, f"multiple-answer item has {len(correct)} correct (want 2..{n_opts - 1})"

    rationale = item.get("rationale")
    if not isinstance(rationale, dict):
        return False, "no rationale"
    missing = [k for k in OPTION_KEYS[:n_opts] if not str(rationale.get(k, "")).strip()]
    if missing:
        return False, f"rationale missing for {missing}"
    return True, "ok"


# --------------------------------------------------------------------------- #
# Blind solve — the check that actually protects the learner
# --------------------------------------------------------------------------- #

SOLVE_SYSTEM = """You are sitting a reading comprehension test.

Answer using ONLY the passage. Do not use outside knowledge. Choose the option a
careful reader would defend from the text itself.

STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block containing
{"answer": ["<option key>", ...], "why": "<one sentence>"} — list every option you
believe is correct, and nothing else."""


def solve_prompt(item: dict[str, Any]) -> str:
    opts = "\n".join(f"{o['key']}. {o['text']}" for o in item["options"])
    how_many = ("Exactly one option is correct." if item["mode"] == "single"
                else "More than one option is correct — select every correct one.")
    return (f"PASSAGE:\n{item['passage']}\n\nQUESTION: {item['question']}\n\n"
            f"OPTIONS:\n{opts}\n\n{how_many}\nAnswer now.")


def blind_solve(item: dict[str, Any], *, model: str, runs: int = SOLVER_RUNS) -> list[list[str]]:
    """Answer the item WITHOUT the key. Temperature is deliberately non-zero and
    varied: identical solves would only prove the model is consistent, not that
    the item is unambiguous."""
    answers = []
    for i in range(runs):
        raw = _chat(
            [{"role": "system", "content": SOLVE_SYSTEM},
             {"role": "user", "content": solve_prompt(item)}],
            model=model, temperature=0.3 + 0.2 * i,
        )
        try:
            got = extract_json(raw).get("answer")
        except (ValueError, AttributeError):
            answers.append([])
            continue
        if isinstance(got, str):
            got = [got]
        answers.append(sorted(str(g).strip().upper() for g in got) if isinstance(got, list) else [])
    return answers


def verify(item: dict[str, Any], *, model: str) -> tuple[bool, str]:
    key = sorted(item["correct"])
    answers = blind_solve(item, model=model)
    agree = sum(1 for a in answers if a == key)
    if agree >= SOLVER_AGREEMENT:
        return True, f"{agree}/{len(answers)} solvers matched"
    got = Counter(",".join(a) if a else "(none)" for a in answers).most_common()
    return False, (f"key {','.join(key)} but solvers said "
                   + "; ".join(f"{k} x{n}" for k, n in got))


# --------------------------------------------------------------------------- #
# Scoring — deterministic, the official rules
# --------------------------------------------------------------------------- #

def score_answer(item: dict[str, Any], chosen: list[str]) -> dict[str, Any]:
    """Mark a learner's selection.

    Single answer: 1 for the correct option, else 0.
    Multiple answers: +1 for each correct option chosen, -1 for each incorrect
    option chosen, and the item cannot go below 0 — the rule that punishes
    guessing everything, which is exactly what learners need to feel.
    """
    key = set(item["correct"])
    picked = {str(c).strip().upper() for c in chosen if str(c).strip()}
    all_keys = {o["key"] for o in item["options"]}
    picked &= all_keys

    hits = sorted(picked & key)
    misses = sorted(key - picked)
    wrong = sorted(picked - key)

    if item["mode"] == "single":
        score = 1 if picked == key else 0
        max_score = 1
    else:
        score = max(0, len(hits) - len(wrong))
        max_score = len(key)

    return {
        "score": score,
        "max_score": max_score,
        "correct_keys": sorted(key),
        "chosen_keys": sorted(picked),
        "hits": hits,
        "missed": misses,
        "wrong": wrong,
        "floored": item["mode"] == "multiple" and len(hits) - len(wrong) < 0,
        "rationale": item.get("rationale", {}),
    }


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


def build_item(item: dict[str, Any], seq: int) -> dict[str, Any]:
    return {
        "id": f"rmc-{seq:03d}-{_slug(item['topic'])}",
        "mode": item["mode"],
        "task_type": "reading_multiple_choice",
        "topic": item["topic"].strip(),
        "title": item["title"].strip(),
        "passage": item["passage"].strip(),
        "word_count": len(item["passage"].split()),
        "question": item["question"].strip(),
        "skill": item["skill"].strip(),
        "options": [{"key": o["key"], "text": o["text"].strip()} for o in item["options"]],
        "correct": sorted(item["correct"]),
        "rationale": {k: str(v).strip() for k, v in item["rationale"].items()},
        "max_score": 1 if item["mode"] == "single" else len(item["correct"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=8, help="items per mode")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--output", default=OUTPUT_FILE)
    ap.add_argument("--dry-run", action="store_true", help="do not write the bank")
    ap.add_argument("--append", action="store_true", help="add to the existing bank")
    args = ap.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    out_path = Path(args.output)
    existing: list[dict[str, Any]] = []
    if args.append and out_path.exists():
        existing = json.loads(out_path.read_text(encoding="utf-8"))
    avoid = [it["topic"] for it in existing]

    kept: list[dict[str, Any]] = []
    rejected: list[tuple[str, str]] = []

    for mode in ("single", "multiple"):
        print(f"\n=== {mode}-answer items ===")
        try:
            raw_items = generate(mode, args.count, model=args.model, avoid=avoid)
        except (httpx.HTTPError, ValueError) as exc:
            print(f"  generation failed: {exc}", file=sys.stderr)
            continue

        for item in raw_items:
            label = str(item.get("topic", "?"))[:34]
            ok, why = contract_validate(item)
            if not ok:
                print(f"  [drop ] {label:36} {why}")
                rejected.append((label, why))
                continue
            try:
                ok, why = verify(item, model=args.model)
            except (httpx.HTTPError, ValueError) as exc:
                print(f"  [drop ] {label:36} verification error: {exc}")
                rejected.append((label, f"verification error: {exc}"))
                continue
            if not ok:
                print(f"  [drop ] {label:36} {why}")
                rejected.append((label, why))
                continue
            print(f"  [keep ] {label:36} {why}")
            kept.append(item)
            avoid.append(item["topic"])

    bank = existing + [build_item(it, len(existing) + i + 1) for i, it in enumerate(kept)]

    print(f"\n{'='*60}")
    print(f"kept {len(kept)}, dropped {len(rejected)}  ->  bank has {len(bank)} items")
    if rejected:
        print("dropped because the answer key could not be trusted:")
        for label, why in rejected:
            print(f"  - {label}: {why}")
    if not kept:
        print("\nNothing survived verification — the bank is unchanged.", file=sys.stderr)

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0
    if kept:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(bank, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\nBank -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
