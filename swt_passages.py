"""Generate and validate a bank of PTE "Summarize Written Text" source passages.

Same generate -> contract-validate -> semantic-audit -> dedup -> store pipeline as
essay_prompts.py, but the artefact is a source passage the learner must summarise
in one sentence.

A usable SWT passage is academic in register, 180-300 words, has ONE clear central
claim plus a few supporting points, and is self-contained (summarisable without
outside knowledge).

Usage:
  export OLLAMA_API_KEY=...        # or .env
  python swt_passages.py --count 8 --dry-run
  python swt_passages.py --count 8
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"
OUTPUT_FILE = "output/swt_passages.json"

MIN_WORDS, MAX_WORDS = 180, 300
MIN_SENTENCES = 4
REQUIRED_FIELDS = {"topic", "title", "passage"}
TIME_MINUTES = 10          # SWT is 10 minutes per item
SUMMARY_WORD_RANGE = [5, 75]


def _chat(messages: list[dict[str, str]], *, model: str, temperature: float = 0.7, timeout: float = 240.0) -> str:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    resp = httpx.post(
        OLLAMA_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "stream": False, "options": {"temperature": temperature}},
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
    for a, b in (("{", "}"), ("[", "]")):
        i, j = text.find(a), text.rfind(b)
        if i != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"No JSON found in reply ({len(text)} chars).")


def count_words(text: str) -> int:
    return len(text.split())


def count_sentences(text: str) -> int:
    return len([p for p in re.split(r"[.!?]+(?=\s|$)", text.strip()) if p.strip()])


# --------------------------------------------------------------------------- #
# 1. Generate
# --------------------------------------------------------------------------- #

def generate_batch(count: int, *, model: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    system = (
        "You write source passages for the PTE Academic 'Summarize Written Text' "
        "task. Each passage is an academic-register text a test taker must "
        "summarise in ONE sentence.\n\n"
        f"Write exactly {count} passages. Each MUST:\n"
        f"- be {MIN_WORDS}-{MAX_WORDS} words of connected prose (no bullet points, no headings inside);\n"
        "- have ONE clear central claim, plus two or three supporting points and, "
        "where natural, a qualification or counter-point;\n"
        "- be self-contained: summarisable without outside knowledge;\n"
        "- be factual and neutral in tone, on a varied academic topic (science, "
        "economics, history, technology, health, environment, education, urban "
        "planning, psychology). Do not repeat a topic.\n\n"
        "STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block "
        'containing {"passages": [ ... ]}. Each item has exactly: "topic" (short '
        'snake_case tag), "title" (short human title), "passage" (the full text as '
        "one string; use \\n\\n between paragraphs if you use more than one). "
        "No prose outside the code block."
    )
    raw = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": "Write the passages now."}],
        model=model,
    )
    data = extract_json(raw)
    items = data.get("passages", data) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


# --------------------------------------------------------------------------- #
# 2. Contract-validate (deterministic)
# --------------------------------------------------------------------------- #

def contract_validate(obj: Any) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "not an object"
    missing = REQUIRED_FIELDS - set(obj)
    if missing:
        return False, f"missing fields: {sorted(missing)}"
    for field in REQUIRED_FIELDS:
        if not isinstance(obj.get(field), str) or not obj[field].strip():
            return False, f"empty {field}"
    text = obj["passage"].strip()
    wc = count_words(text)
    if not (MIN_WORDS <= wc <= MAX_WORDS):
        return False, f"{wc} words (need {MIN_WORDS}-{MAX_WORDS})"
    sc = count_sentences(text)
    if sc < MIN_SENTENCES:
        return False, f"{sc} sentences (need >= {MIN_SENTENCES})"
    if re.search(r"^\s*[-*•]", text, re.MULTILINE):
        return False, "contains bullet points"
    return True, "ok"


def normalize(obj: dict[str, Any]) -> dict[str, Any]:
    text = obj["passage"].strip()
    return {
        "topic": obj["topic"].strip(),
        "title": obj["title"].strip(),
        "passage": text,
        "word_count": count_words(text),
        "time_minutes": TIME_MINUTES,
        "summary_word_range": list(SUMMARY_WORD_RANGE),
    }


# --------------------------------------------------------------------------- #
# 3. Semantic audit (model-judged), batched
# --------------------------------------------------------------------------- #

def semantic_audit(passages: list[dict[str, Any]], *, model: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    if not passages:
        return []
    catalogue = [
        {"index": i, "title": p["title"], "passage": p["passage"]} for i, p in enumerate(passages)
    ]
    system = (
        "You are a strict reviewer of source passages for PTE Academic 'Summarize "
        "Written Text'. Accept a passage only if ALL hold: it is coherent, "
        "factual-sounding academic prose; it has ONE identifiable central claim "
        "that a reader could capture in a single sentence; it contains supporting "
        "detail worth condensing; it is self-contained (no outside knowledge "
        "needed); and it is appropriate and free of nonsense or contradiction. "
        "Reject anything that is a list of unrelated facts, has no clear main "
        "idea, or is incoherent.\n\n"
        "STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block "
        'containing {"verdicts": [{"index": <int>, "accept": <bool>, "reason": '
        '"<short>", "central_claim": "<one clause naming the passage\'s main '
        'idea>"}]} — exactly one verdict per input index.'
    )
    raw = _chat(
        [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(catalogue, ensure_ascii=False)}],
        model=model,
        temperature=0.2,
    )
    data = extract_json(raw)
    verdicts = data.get("verdicts", []) if isinstance(data, dict) else data
    by_index = {v.get("index"): v for v in verdicts if isinstance(v, dict)}
    out = []
    for i, p in enumerate(passages):
        v = by_index.get(i, {"accept": False, "reason": "no verdict returned"})
        out.append({
            **p,
            "_accept": bool(v.get("accept")),
            "_reason": v.get("reason", ""),
            "central_claim": v.get("central_claim", ""),
        })
    return out


# --------------------------------------------------------------------------- #
# 4. Dedup + ids
# --------------------------------------------------------------------------- #

def dedup(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for p in passages:
        key = re.sub(r"\s+", " ", p["passage"][:120].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24] or "passage"


def assign_ids(passages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for p in passages:
        base = _slug(p["topic"])
        counts[base] = counts.get(base, 0) + 1
        p["id"] = f"{base}-{counts[base]:02d}"
    return passages


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Generate + validate SWT source passages.")
    p.add_argument("--count", type=int, default=8)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default=OUTPUT_FILE)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    print(f"Generating {args.count} passages…")
    candidates = generate_batch(args.count, model=args.model)
    print(f"  model returned {len(candidates)}\n")

    print("Contract validation (deterministic):")
    passed = []
    for c in candidates:
        ok, reason = contract_validate(c)
        title = (c.get("title") if isinstance(c, dict) else "?") or "?"
        if ok:
            passed.append(normalize(c))
            print(f"  PASS  {title[:40]:42} {count_words(c['passage'])}w")
        else:
            print(f"  FAIL  {title[:40]:42} {reason}")
    print(f"  -> {len(passed)}/{len(candidates)} passed\n")

    print("Semantic audit (model-judged):")
    audited = semantic_audit(passed, model=args.model)
    accepted = []
    for a in audited:
        mark = "ACCEPT" if a["_accept"] else "REJECT"
        print(f"  {mark}  {a['title'][:40]:42} {a['_reason'][:44]}")
        if a["_accept"]:
            accepted.append({k: v for k, v in a.items() if not k.startswith("_")})
    print(f"  -> {len(accepted)}/{len(passed)} accepted\n")

    final = assign_ids(dedup(accepted))
    print(f"Final bank: {len(final)} passages")
    for f in final:
        print(f"  [{f['id']}] {f['title']} ({f['word_count']}w) — {f.get('central_claim','')[:60]}")

    if args.dry_run:
        print("\n--dry-run: not writing.")
        return 0

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps({"passages": final}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {len(final)} passages to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
