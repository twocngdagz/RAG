"""Score a PTE Academic "Describe Image" response against a generated chart item.

Content is the trait we can assess honestly, and it is the one that gates the
whole question (Score Guide p.8: Content 0 -> no further scoring). Oral Fluency
and Pronunciation need the audio signal and are NOT scored here — see the
`not_scored` field, which says so explicitly rather than implying a full score.

Rubric — official Describe Image Content, 0-6 (Score Guide pp.18-19):
  6 full, accurate, expands RELATIONSHIPS, nuanced; complete mental picture
  5 main features accurate, some relationships, not expanded; minor gaps
  4 simple descriptions + basic relationships; may miss main features
  3 mainly superficial, minor inaccuracies, narrow/repetitive expression
  2 minimal superficial description, some inaccuracies, limited vocabulary
  1 disconnected elements or a bare LIST of points, no elaboration
  0 relevant but too limited (or irrelevant/memorised)

Two layers, as elsewhere in this project:
  - deterministic (code): word count, and a numeric-accuracy check comparing every
    figure said against the item's real data (the rubric punishes inaccuracies)
  - model: per-fact coverage against the item's COMPUTED facts, structure, band

Usage:
  python describe_image_feedback.py --item <id> --response "The bar chart shows..."
  python describe_image_feedback.py --list
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
ITEMS_FILE = "output/describe_image_items.json"
MAX_CONTENT = 6
TARGET_WORDS = (80, 120)  # a full 40-second response

SYSTEM_PROMPT = """You are a PTE Academic rater evaluating a Describe Image spoken
response (transcribed). Judge ONLY the Content trait against the official criteria.

CONTENT - 0 to 6
6: Describes the image fully and accurately and EXPANDS ON THE RELATIONSHIPS between
   features to give a nuanced interpretation. Varied vocabulary used with ease and
   precision. A listener could build a COMPLETE mental picture.
5: Describes the main features accurately and identifies some relationships without
   expanding on them. Varied expressions throughout. Accurate mental picture, minor
   details missing or misrepresented.
4: Some accurate simple descriptions and basic relationships, but may not cover all
   the main features. Range sufficient for basic description, with some repetition.
3: Mainly superficial descriptions with MINOR INACCURACIES. Narrow range, simple
   expressions repeated. Listener gets elements, not a cohesive whole.
2: Minimal, superficial description with some inaccuracies. Limited vocabulary
   dominates. A listener could visualise some elements only with effort.
1: Disconnected elements, or a bare LIST of points with no description or
   elaboration. Highly restricted vocabulary.
0: Relevant but too limited to score higher, OR irrelevant / clearly pre-memorised.

KEY DISCRIMINATOR: bands 5-6 require RELATIONSHIPS between features (comparisons,
trends, contrasts), not just a list of values. A response that only recites numbers
cannot score above 4 no matter how many it recites.

You are given the chart's TRUE FACTS, computed from its underlying data. Use them to
judge coverage and accuracy — anything the response states that contradicts them is
an inaccuracy and must lower the band.

STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block containing one
valid object, no prose outside it:

{
  "content_score": <integer 0-6>,
  "band_reason": "<one sentence citing the band descriptor you applied>",
  "facts": [
    {"key": "<fact key>", "covered": "<yes|partial|no>", "note": "<brief, quoting the response where possible>"}
  ],
  "structure": {
    "overview": <bool>, "key_features": <bool>,
    "relationships": <bool>, "closing": <bool>
  },
  "inaccuracies": ["<anything stated that contradicts the true facts>"],
  "errors": [{"type": "<grammar|word_choice|vocabulary>", "wrong": "<exact text>", "correct": "<fix>"}],
  "top_priorities": ["<one to three highest-impact improvements>"],
  "one_line_verdict": "<one encouraging but honest sentence>"
}
Include one entry in "facts" for EVERY fact key supplied, in the same order."""


# --------------------------------------------------------------------------- #
# Items
# --------------------------------------------------------------------------- #

def load_items(path: str = ITEMS_FILE) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("items", data) if isinstance(data, dict) else data


def get_item(item_id: str, path: str = ITEMS_FILE) -> dict[str, Any]:
    for it in load_items(path):
        if it["id"] == item_id:
            return it
    raise KeyError(f"No item {item_id!r}. Use --list to see available items.")


# --------------------------------------------------------------------------- #
# Deterministic checks
# --------------------------------------------------------------------------- #

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def count_words(text: str) -> int:
    return len(text.split())


def allowed_numbers(item: dict[str, Any]) -> set[float]:
    """Figures a learner could legitimately say: the data values, the total, the
    max-min gap, the ratio, and any numbers appearing in labels (e.g. years)."""
    values = [float(p["value"]) for p in item["points"]]
    allowed = set(values)
    allowed.add(sum(values))
    allowed.add(max(values) - min(values))
    if min(values):
        allowed.add(round(max(values) / min(values), 1))
    for p in item["points"]:
        for m in _NUM_RE.findall(p["label"]):
            allowed.add(float(m))
    for m in _NUM_RE.findall(item.get("title", "")):
        allowed.add(float(m))
    # Combined shares ("the top two together make up 70%") are natural only for
    # pie charts. Allowing every pairwise sum elsewhere covered so much of the
    # number line that real misreadings slipped through unflagged.
    if item["chart_type"] == "pie":
        ordered = sorted(values, reverse=True)
        for k in range(2, len(ordered) + 1):
            allowed.add(sum(ordered[:k]))
    return allowed


def _stated_tolerance(n: float) -> float:
    """How much slack a figure earns, inferred from how precisely it was stated.
    'about 8000' (3 trailing zeros) tolerates +/-500, so it fairly matches 7800;
    a precise '77' tolerates +/-0.5, so it will not pass for 80. This lets honest
    rounding through while still catching misread values."""
    s = f"{n:g}"
    if "." in s:
        return 0.5 * 10 ** (-len(s.split(".")[1]))
    digits = s.lstrip("-")
    trailing = len(digits) - len(digits.rstrip("0"))
    return max(0.5 * (10**trailing), 0.5)


def check_numbers(text: str, item: dict[str, Any]) -> dict[str, Any]:
    """Flag figures that match no real value. Tolerance follows the precision the
    speaker used, and small counting numbers ('three categories') are ignored."""
    allowed = allowed_numbers(item)
    said = [float(m) for m in _NUM_RE.findall(text.replace(",", ""))]
    unsupported = []
    for n in said:
        if n <= 12 and not any(abs(n - a) < 1e-9 for a in allowed):
            continue  # likely a count/ordinal, not a data figure
        tol = _stated_tolerance(n)
        if not any(abs(n - a) <= tol for a in allowed):
            unsupported.append(n)
    return {"numbers_said": said, "unsupported": sorted(set(unsupported))}


# --------------------------------------------------------------------------- #
# Model call
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    for cand in (text, *(m.group(1) for m in _FENCE_RE.finditer(text))):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    i, j = text.find("{"), text.rfind("}")
    if i != -1 and j > i:
        return json.loads(text[i : j + 1])
    raise ValueError(f"No JSON object in model reply ({len(text)} chars).")


def build_messages(item: dict[str, Any], response: str) -> list[dict[str, str]]:
    facts = "\n".join(f"- [{f['key']}] ({f['importance']}) {f['text']}" for f in item["facts"])
    data = ", ".join(f"{p['label']}={p['value']}" for p in item["points"])
    user = (
        f"CHART: {item['title']} ({item['chart_type']} chart, unit: {item['unit']})\n"
        f"UNDERLYING DATA: {data}\n\n"
        f"TRUE FACTS (computed from that data):\n{facts}\n\n"
        f"TEST TAKER'S SPOKEN RESPONSE (transcribed):\n{response.strip()}\n\n"
        "Score the Content now and return the JSON."
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def _reconcile(result: dict[str, Any], item: dict[str, Any], response: str) -> dict[str, Any]:
    """Code owns the arithmetic: clamp the band, recompute coverage counts, attach
    the deterministic numeric check, and apply Content-zero gating."""
    result["word_count"] = count_words(response)
    result["max_content"] = MAX_CONTENT
    result["content_score"] = max(0, min(int(result.get("content_score", 0)), MAX_CONTENT))

    by_key = {f.get("key"): f for f in result.get("facts", []) if isinstance(f, dict)}
    merged = []
    for f in item["facts"]:
        got = by_key.get(f["key"], {})
        merged.append({
            "key": f["key"],
            "importance": f["importance"],
            "text": f["text"],
            "covered": got.get("covered", "no"),
            "note": got.get("note", ""),
        })
    result["facts"] = merged
    ess = [f for f in merged if f["importance"] == "essential"]
    sup = [f for f in merged if f["importance"] == "supporting"]
    result["coverage"] = {
        "essential_covered": sum(1 for f in ess if f["covered"] == "yes"),
        "essential_total": len(ess),
        "supporting_covered": sum(1 for f in sup if f["covered"] == "yes"),
        "supporting_total": len(sup),
    }
    result["accuracy"] = check_numbers(response, item)
    result["gating_applied"] = result["content_score"] == 0
    result["not_scored"] = ["Oral Fluency", "Pronunciation"]
    # Shared shape so the stored-attempt history, trend and per-trait progress
    # components work for this task without special-casing.
    result["raw_total"] = result["content_score"]
    result["max_raw_total"] = MAX_CONTENT
    result["traits"] = [
        {
            "name": "content",
            "score": result["content_score"],
            "max": MAX_CONTENT,
            "evidence": result.get("band_reason", ""),
            "fix": (result.get("top_priorities") or [""])[0],
            "scored_by": "model",
        }
    ]
    # The Content band is the model's call. (result["accuracy"] beside it is the
    # deterministic number check — code — and is presented separately.)
    result["scored_by"] = "model"
    return result


def score_response(
    item: dict[str, Any],
    response: str,
    *,
    model: str = DEFAULT_MODEL,
    timeout: float = 180.0,
    attempts: int = 2,
) -> dict[str, Any]:
    api_key = os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError("OLLAMA_API_KEY is not set (add it to .env).")
    messages = build_messages(item, response)
    last: Exception | None = None
    for _ in range(max(1, attempts)):
        resp = httpx.post(
            OLLAMA_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.2}},
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        try:
            return _reconcile(extract_json(content), item, response)
        except (ValueError, json.JSONDecodeError) as exc:
            last = exc
    raise ValueError(f"Model did not return valid JSON after {attempts} attempts: {last}")


def format_report(r: dict[str, Any]) -> str:
    cov = r["coverage"]
    lines = [
        f"Content: {r['content_score']}/{r['max_content']}  ({r['word_count']} words)"
        + ("   [GATED: Content 0 → no further scoring]" if r.get("gating_applied") else ""),
        f"Reason: {r.get('band_reason','')}",
        f"Verdict: {r.get('one_line_verdict','')}",
        "",
        f"Fact coverage: {cov['essential_covered']}/{cov['essential_total']} essential, "
        f"{cov['supporting_covered']}/{cov['supporting_total']} supporting",
    ]
    for f in r["facts"]:
        mark = {"yes": "✓", "partial": "~", "no": "✗"}.get(f["covered"], "?")
        lines.append(f"  {mark} [{f['importance'][:4]}] {f['text']}")
        if f.get("note"):
            lines.append(f"        {f['note']}")
    st = r.get("structure", {})
    lines += ["", "Structure: " + ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in st.items())]
    acc = r.get("accuracy", {})
    if acc.get("unsupported"):
        lines.append(f"Figures not matching the chart: {acc['unsupported']}")
    if r.get("inaccuracies"):
        lines += ["", "Inaccuracies:"] + [f"  - {x}" for x in r["inaccuracies"]]
    if r.get("errors"):
        lines += ["", "Corrections:"] + [
            f"  [{e.get('type')}] {e.get('wrong')!r} -> {e.get('correct')!r}" for e in r["errors"]
        ]
    if r.get("top_priorities"):
        lines += ["", "Top priorities:"] + [f"  - {p}" for p in r["top_priorities"]]
    lines += ["", f"Not scored (needs audio): {', '.join(r.get('not_scored', []))}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    p = argparse.ArgumentParser(description="Score a Describe Image response.")
    p.add_argument("--item")
    p.add_argument("--response")
    p.add_argument("--response-file")
    p.add_argument("--items-file", default=ITEMS_FILE)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--list", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if args.list:
        for it in load_items(args.items_file):
            print(f"{it['id']:34} {it['chart_type']:5} {it['title']}")
        return 0
    text = args.response or (open(args.response_file).read() if args.response_file else "")
    if not args.item or not text:
        print("Provide --item and --response/--response-file (or --list).", file=sys.stderr)
        return 2
    item = get_item(args.item, args.items_file)
    result = score_response(item, text, model=args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
