"""Generate and validate a bank of PTE Academic "Write Essay" practice prompts.

Same generate -> validate -> audit pattern as the grounded-base pipeline, applied
to prompts and reusing the Ollama Cloud backend:

  generate (model)            a batch of prompt objects as strict JSON
  -> contract_validate (code) deterministic: schema, fixed constraints, and the
                              key rule that the directive matches the type
  -> semantic_audit (model)   is it coherent, answerable, on-type, appropriate?
  -> dedup
  -> output/essay_prompts.json  git-tracked; served to the Practice UI

A valid Write Essay prompt is fixed at 20 minutes / 200-300 words, so those are
forced in code rather than trusted to the model.

Usage:
  export OLLAMA_API_KEY=...          # or put it in .env
  python essay_prompts.py --per-type 3            # generate + validate a batch
  python essay_prompts.py --per-type 3 --dry-run  # don't write the file
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
OUTPUT_FILE = "output/essay_prompts.json"

TIME_MINUTES = 20
WORD_RANGE = [200, 300]
REQUIRED_FIELDS = {"type", "topic", "statement", "directive", "instruction"}

# The recognised PTE Write Essay task types and the directive pattern each must
# satisfy (checked case-insensitively). This is the rule that "governs" a prompt.
DIRECTIVE_RULES = {
    "agree_disagree": lambda d: "agree" in d and "disagree" in d,
    "advantages_disadvantages": lambda d: "advantage" in d and "disadvantage" in d,
    "problem_solution": lambda d: (
        any(w in d for w in ("cause", "problem", "issue", "reason"))
        and any(w in d for w in ("solution", "solve", "measure", "address", "tackle", "be done", "what should", "steps"))
    ),
    "positive_negative": lambda d: "positive" in d and "negative" in d,
    "discuss_two_views": lambda d: "discuss" in d and ("both" in d or "views" in d or "opinion" in d),
}
ALLOWED_TYPES = set(DIRECTIVE_RULES)

DIRECTIVE_EXAMPLES = {
    "agree_disagree": "To what extent do you agree or disagree?",
    "advantages_disadvantages": "Discuss the advantages and disadvantages and give your own opinion.",
    "problem_solution": "What are the main causes, and what measures can be taken to address them?",
    "positive_negative": "Is this a positive or negative development?",
    "discuss_two_views": "Discuss both views and give your own opinion.",
}


# --------------------------------------------------------------------------- #
# Ollama Cloud chat
# --------------------------------------------------------------------------- #

def _chat(messages: list[dict[str, str]], *, model: str, temperature: float = 0.7, timeout: float = 180.0) -> str:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OLLAMA_API_KEY is not set. Create one at https://ollama.com/settings/keys "
            "and add it to .env."
        )
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


# --------------------------------------------------------------------------- #
# 1. Generate
# --------------------------------------------------------------------------- #

def generate_batch(per_type: int, *, model: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    type_spec = "\n".join(
        f'- {t}: directive like "{DIRECTIVE_EXAMPLES[t]}"' for t in sorted(ALLOWED_TYPES)
    )
    system = (
        "You are a test-item writer for PTE Academic. Write authentic 'Write Essay' "
        "prompts on varied academic/real-world topics (education, technology, "
        "environment, health, work, society, culture). Each prompt must be a "
        "coherent, answerable argumentative question — never a nonsense or self-"
        "contradictory statement.\n\n"
        f"Produce exactly {per_type} prompt(s) for EACH of these types, with a "
        f"directive that matches the type:\n{type_spec}\n\n"
        "STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block "
        'containing an object {"prompts": [ ... ]}. Each item has exactly: '
        '"type" (one of the types above), "topic" (short tag), "statement" (1-2 '
        'sentence context), "directive" (the question, matching the type), '
        '"instruction" (e.g. "Support your position with reasons and examples."). '
        "No prose outside the code block. Vary the topics; do not repeat a topic."
    )
    raw = _chat([{"role": "system", "content": system},
                 {"role": "user", "content": "Generate the prompts now."}], model=model)
    data = extract_json(raw)
    items = data.get("prompts", data) if isinstance(data, dict) else data
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
    t = obj.get("type")
    if t not in ALLOWED_TYPES:
        return False, f"unknown type {t!r}"
    for field in ("statement", "directive", "instruction", "topic"):
        if not isinstance(obj.get(field), str) or not obj[field].strip():
            return False, f"empty {field}"
    if not DIRECTIVE_RULES[t](obj["directive"].lower()):
        return False, f"directive does not match type {t!r}: {obj['directive']!r}"
    return True, "ok"


def normalize(obj: dict[str, Any]) -> dict[str, Any]:
    """Force the fixed Write Essay constraints; trim text."""
    return {
        "type": obj["type"],
        "topic": obj["topic"].strip(),
        "statement": obj["statement"].strip(),
        "directive": obj["directive"].strip(),
        "instruction": obj["instruction"].strip(),
        "time_minutes": TIME_MINUTES,
        "word_range": list(WORD_RANGE),
    }


# --------------------------------------------------------------------------- #
# 3. Semantic audit (model-judged), batched
# --------------------------------------------------------------------------- #

def semantic_audit(prompts: list[dict[str, Any]], *, model: str = DEFAULT_MODEL) -> list[dict[str, Any]]:
    if not prompts:
        return []
    catalogue = [
        {"index": i, "type": p["type"], "statement": p["statement"], "directive": p["directive"]}
        for i, p in enumerate(prompts)
    ]
    system = (
        "You are a strict reviewer of PTE Academic 'Write Essay' prompts. For each "
        "item decide accept=true only if ALL hold: it is coherent and answerable as "
        "a 200-300 word argumentative essay; it is genuinely of its stated type; it "
        "is on a single clear topic; it is appropriate and non-offensive; and it "
        "contains no self-contradiction, nonsense, or non-sequitur. Otherwise "
        "accept=false with a short reason.\n\n"
        "STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block "
        'containing {"verdicts": [{"index": <int>, "accept": <bool>, "reason": '
        '"<short>"}]} — exactly one verdict per input index.'
    )
    raw = _chat(
        [{"role": "system", "content": system},
         {"role": "user", "content": json.dumps(catalogue, ensure_ascii=False)}],
        model=model, temperature=0.2,
    )
    data = extract_json(raw)
    verdicts = data.get("verdicts", []) if isinstance(data, dict) else data
    by_index = {v.get("index"): v for v in verdicts if isinstance(v, dict)}
    out = []
    for i, p in enumerate(prompts):
        v = by_index.get(i, {"accept": False, "reason": "no verdict returned"})
        out.append({**p, "_accept": bool(v.get("accept")), "_reason": v.get("reason", "")})
    return out


# --------------------------------------------------------------------------- #
# 4. Dedup + ids
# --------------------------------------------------------------------------- #

def dedup(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for p in prompts:
        key = re.sub(r"\s+", " ", p["statement"].lower()).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24] or "topic"


def assign_ids(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for p in prompts:
        base = _slug(p["topic"])
        counts[base] = counts.get(base, 0) + 1
        p["id"] = f"{base}-{counts[base]:02d}"
    return prompts


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    p = argparse.ArgumentParser(description="Generate + validate PTE essay prompts.")
    p.add_argument("--per-type", type=int, default=3)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--output", default=OUTPUT_FILE)
    p.add_argument("--dry-run", action="store_true", help="Do not write the file.")
    args = p.parse_args(argv)

    print(f"Generating {args.per_type} per type ({args.per_type * len(ALLOWED_TYPES)} candidates)…")
    candidates = generate_batch(args.per_type, model=args.model)
    print(f"  model returned {len(candidates)} candidates\n")

    print("Contract validation (deterministic):")
    passed = []
    for c in candidates:
        ok, reason = contract_validate(c)
        label = (c.get("type") if isinstance(c, dict) else "?")
        if ok:
            passed.append(normalize(c))
            print(f"  PASS  {label:26} {c['directive'][:60]}")
        else:
            print(f"  FAIL  {label!s:26} {reason}")
    print(f"  -> {len(passed)}/{len(candidates)} passed the contract\n")

    print("Semantic audit (model-judged):")
    audited = semantic_audit(passed, model=args.model)
    accepted = []
    for a in audited:
        mark = "ACCEPT" if a["_accept"] else "REJECT"
        print(f"  {mark}  {a['type']:26} {a['_reason'][:60]}")
        if a["_accept"]:
            accepted.append({k: v for k, v in a.items() if not k.startswith("_")})
    print(f"  -> {len(accepted)}/{len(passed)} accepted\n")

    final = assign_ids(dedup(accepted))
    by_type: dict[str, int] = {}
    for f in final:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
    print(f"Final bank: {len(final)} prompts  " + ", ".join(f"{t}:{n}" for t, n in sorted(by_type.items())))

    if args.dry_run:
        print("\n--dry-run: not writing. Sample:")
        print(json.dumps(final[:3], indent=2, ensure_ascii=False))
        return 0

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps({"prompts": final}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote {len(final)} prompts to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
