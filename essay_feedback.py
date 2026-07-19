"""Score a PTE Academic "Write Essay" response and return actionable feedback.

First *live-inference* step in the project (everything before was offline batch):
calls a hosted model on demand to assess a learner's essay against the current
public Pearson Write Essay criteria, so the app can move from "study guide" to
"trainer".

Backend: Ollama Cloud (https://ollama.com/api/chat) — a hosted open model reached
with an API key, so no local GPU is needed and cost is a flat subscription rather
than per-token. Set OLLAMA_API_KEY (create one at https://ollama.com/settings/keys).

Rubric (current public Pearson criteria, raw total 0-26):
  Content 0-6 | Form 0-2 | Development, structure & coherence 0-6 |
  Grammar 0-2 | General linguistic range 0-6 | Vocabulary range 0-2 | Spelling 0-2
Gating: if Content or Form is 0, the whole response scores 0.

No 10-90 conversion is produced: a single essay's raw trait score cannot be
officially converted to a PTE score (Pearson's Overall/Writing scores come from
whole-test performance). Only the raw rubric total is reported.

Word count and the Form band are computed deterministically in code (not trusted
to the model), so a 201-word essay is never misread as under 200.

Usage:
  export OLLAMA_API_KEY=...   # or put it in .env
  python essay_feedback.py --prompt-file prompt.txt --essay-file essay.txt
  python essay_feedback.py --prompt "Some people think..." --essay "Online education..."
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any

import httpx

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"
MAX_RAW_TOTAL = 26

# (trait, max) in the fixed output order. Content/DSC/GLR are the 0-6 traits.
TRAIT_MAX = {
    "content": 6,
    "form": 2,
    "development_structure_coherence": 6,
    "grammar": 2,
    "general_linguistic_range": 6,
    "vocabulary_range": 2,
    "spelling": 2,
}

SYSTEM_PROMPT = """You are a PTE Academic writing rater and feedback coach evaluating a
Write Essay response.

Apply the scoring criteria below strictly and consistently. Judge only
the learner's essay against the supplied essay prompt. Do not invent
ideas, evidence, errors, or facts that do not appear in the response.

Do not penalise a reasonable hypothetical example simply because it
does not contain a citation or statistic.

CURRENT WRITE ESSAY TRAITS
Raw trait maximum: 26

1. CONTENT — 0 to 6
6: Fully addresses the prompt in depth. The position is convincing,
   important points are developed specifically, and relevant supporting
   reasons or examples appear throughout.
5: Adequately addresses the prompt with a persuasive argument, relevant
   ideas, and generally effective support, with only minor weaknesses.
4: Addresses the main point and presents a generally convincing argument,
   but lacks depth or nuance. Support is inconsistent.
3: Remains relevant but does not adequately address or develop the main
   points. Supporting details are often missing or unsuitable.
2: Addresses the prompt superficially through generic statements,
   repetition, or weakly relevant ideas. Few useful details are provided.
1: Shows incomplete understanding. Ideas are generic, repetitive,
   disjointed, or only weakly connected to the prompt.
0: Does not properly address the prompt.

2. FORM — 0 to 2
2: 200-300 words.
1: 120-199 words or 301-380 words.
0: Fewer than 120 words or more than 380 words; OR written entirely in
   capitals; OR contains no punctuation; OR consists only of bullet
   points or very short sentences.

For consistency in this evaluation, count words as space-separated
tokens. Treat a hyphenated compound such as "face-to-face" as one word.

3. DEVELOPMENT, STRUCTURE AND COHERENCE — 0 to 6
6: Highly effective logical structure; clear and systematically developed
   argument; strong introduction and conclusion; cohesive, logically
   sequenced paragraphs; varied and effective connections between ideas.
5: Appropriate conventional structure and clear argument. Introduction,
   conclusion, and logical paragraphs are present. Some transitions may
   be slightly abrupt or some points may need fuller development.
4: Structure is mostly present, but some elements are underdeveloped,
   difficult to follow, poorly divided, or weakly connected.
3: A position and traces of essay structure are present, but the argument
   consists mainly of simple or insufficiently connected points.
2: Little recognisable structure. The position lacks clarity or
   development, and ideas are difficult to follow.
1: Disconnected ideas, no clear hierarchy, and no identifiable consistent
   position.
0: No recognisable structure.

A paragraph should have one controlling purpose. It may include several
closely related supporting details.

4. GRAMMAR — 0 to 2
2: Consistent control of complex grammar. Errors are rare and difficult
   to notice.
1: Relatively strong grammatical control. Errors do not cause
   misunderstanding.
0: Mainly simple structures and/or several basic grammatical errors.

5. GENERAL LINGUISTIC RANGE — 0 to 6
6: Uses varied expressions and language precisely and naturally. Meaning
   is completely clear and there are no meaningful restrictions.
5: Uses a suitable variety of expressions. Ideas are clear, with only
   occasional minor limitations or errors.
4: Has enough range to express the main ideas, but limitations appear
   when communicating complex or abstract points. Some repetition,
   awkward formulation, or occasional loss of clarity occurs.
3: Uses a narrow range and repeatedly relies on simple expressions.
   Errors sometimes disrupt reading.
2: Limited language dominates. Some ideas are unclear, and frequent
   errors cause breakdowns.
1: Language is highly restricted and meaning is generally unclear.
0: Meaning is inaccessible.

6. VOCABULARY RANGE — 0 to 2
2: Broad and precise lexical repertoire with natural, accurate word
   combinations.
1: Suitable vocabulary for general academic topics, but some repetition,
   imprecision, awkward collocation, or circumlocution occurs.
0: Mainly basic vocabulary that is insufficient for the topic.

7. SPELLING — 0 to 2
2: No spelling errors.
1: Exactly one spelling error.
0: More than one spelling error.

GATING RULE
If Content is 0 or Form is 0:
- Set every trait score to 0.
- Set raw_total to 0.
- Still explain the Content or Form failure and provide useful corrections.

CLAIM COHERENCE
Actively check for self-contradictions and logically incoherent claims —
for example, stating a position and then its opposite, or a sentence whose
meaning is broken by a missing or wrong word (e.g. "we should solely rely on
them" where the argument needs "should not"). If you find one, quote it in the
evidence for Content and/or Development, structure and coherence, and lower
those trait scores accordingly. Do not silently ignore a contradiction.

SURFACE ERRORS
In "errors", list up to 25 concrete, correctable surface errors in the essay —
spelling, grammar, punctuation, and clear word-choice mistakes. For each, "wrong"
MUST be the exact text as it appears in the essay (a short span, so it can be
located and highlighted), and "correct" is the minimal corrected version. Set
"type" to one of: spelling, grammar, punctuation, word_choice. List them in the
order they appear. Do not include stylistic preferences or rewrites of whole
sentences; only genuine errors a reader would mark.

WORD COUNT
Count the words yourself. Do not trust a word count supplied by the user.

SCORING RULES
- Use whole-number scores only.
- Every score must be within the stated range.
- raw_total must exactly equal the sum of all seven trait scores.
- Do not convert the result into an official PTE score from 10 to 90.
- Evidence must use a brief quotation or identify a specific part of the
  essay.
- Each fix must describe one concrete action that would improve that
  trait.
- Do not rewrite the complete essay unless explicitly requested.

STRICT OUTPUT CONTRACT
Reply with ONLY one fenced ```json code block containing one valid,
JSON.parse-able object. Include no prose before or after the code block.

Use exactly this structure:

{
  "word_count": <integer>,
  "gating_applied": <true or false>,
  "traits": [
    {"name": "content", "score": <integer>, "max": 6, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "form", "score": <integer>, "max": 2, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "development_structure_coherence", "score": <integer>, "max": 6, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "grammar", "score": <integer>, "max": 2, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "general_linguistic_range", "score": <integer>, "max": 6, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "vocabulary_range", "score": <integer>, "max": 2, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "spelling", "score": <integer>, "max": 2, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"}
  ],
  "raw_total": <integer from 0 to 26>,
  "max_raw_total": 26,
  "errors": [{"type": "<spelling|grammar|punctuation|word_choice>", "wrong": "<exact text as written in the essay>", "correct": "<corrected version>"}],
  "top_priorities": ["<one to three highest-impact improvements>"],
  "one_line_verdict": "<one encouraging but honest sentence>"
}"""


def build_messages(prompt_text: str, essay_text: str) -> list[dict[str, str]]:
    user = (
        f"ESSAY PROMPT:\n{prompt_text.strip()}\n\n"
        f"LEARNER'S ESSAY:\n{essay_text.strip()}\n\n"
        "Score this essay now and return the JSON."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
# Deterministic checks — word count and the Form band are mechanical, so compute
# them in code instead of trusting the model (guards the "201 read as <200" bug).
# --------------------------------------------------------------------------- #

def count_words(text: str) -> int:
    """Space-separated tokens; a hyphenated compound stays one word."""
    return len(text.split())


def form_score(text: str) -> tuple[int, str]:
    """Deterministic Form score (0-2) with the reason, per the current criteria."""
    stripped = text.strip()
    wc = count_words(stripped)
    letters = [c for c in stripped if c.isalpha()]
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if letters and all(c.isupper() for c in letters):
        return 0, "written entirely in capitals"
    if not any(p in stripped for p in ".?!"):
        return 0, "contains no sentence-ending punctuation"
    if lines and all(re.match(r"^[-*••]", ln) for ln in lines):
        return 0, "consists only of bullet points"
    if wc < 120:
        return 0, f"{wc} words (fewer than 120)"
    if wc > 380:
        return 0, f"{wc} words (more than 380)"
    if 200 <= wc <= 300:
        return 2, f"{wc} words (within 200-300)"
    return 1, f"{wc} words (120-199 or 301-380)"


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    for candidate in (text, *(m.group(1) for m in _FENCE_RE.finditer(text))):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError(f"No JSON object in model reply ({len(text)} chars).")


def _reconcile(result: dict[str, Any], essay_text: str) -> dict[str, Any]:
    """Enforce the rubric arithmetic so the numbers are always self-consistent:
    authoritative word count + Form from code, clamp every trait to its max, apply
    the Content/Form-zero gating rule, and recompute raw_total."""
    wc = count_words(essay_text)
    result["word_count"] = wc
    code_form, form_reason = form_score(essay_text)

    for tr in result.get("traits", []):
        name = tr.get("name")
        cap = TRAIT_MAX.get(name)
        if cap is None:
            continue
        tr["max"] = cap
        tr["score"] = max(0, min(int(tr.get("score", 0)), cap))
        if name == "form":  # Form is mechanical → code is authoritative
            tr["score"] = code_form
            tr["evidence"] = f"{form_reason}."

    by_name = {tr.get("name"): tr for tr in result.get("traits", [])}
    content = by_name.get("content", {}).get("score", 0)
    form = by_name.get("form", {}).get("score", 0)
    gated = content == 0 or form == 0
    result["gating_applied"] = gated
    if gated:
        for tr in result.get("traits", []):
            tr["score"] = 0
        result["raw_total"] = 0
    else:
        result["raw_total"] = sum(tr.get("score", 0) for tr in result.get("traits", []))
    result["max_raw_total"] = MAX_RAW_TOTAL
    return result


def score_essay(
    prompt_text: str,
    essay_text: str,
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    timeout: float = 180.0,
    attempts: int = 2,
) -> dict[str, Any]:
    api_key = api_key or os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OLLAMA_API_KEY is not set. Create one at https://ollama.com/settings/keys "
            "and `export OLLAMA_API_KEY=...` (or add it to .env)."
        )
    messages = build_messages(prompt_text, essay_text)
    last_err: Exception | None = None
    for _ in range(max(1, attempts)):
        resp = httpx.post(
            OLLAMA_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            # Low temperature: scoring should be as deterministic as possible, which
            # also cuts malformed-JSON replies and run-to-run trait variance.
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        try:
            return _reconcile(extract_json(content), essay_text)
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = exc  # transient malformed JSON — retry once
    raise ValueError(f"Model did not return valid JSON after {attempts} attempts: {last_err}")


def format_report(r: dict[str, Any]) -> str:
    total, mx = r.get("raw_total", "?"), r.get("max_raw_total", MAX_RAW_TOTAL)
    pct = f"{round(100 * total / mx)}%" if isinstance(total, int) and mx else "?"
    lines = [
        f"Raw rubric total: {total}/{mx}  ({pct} of rubric — not an official PTE score)",
        f"Words: {r.get('word_count', '?')}"
        + ("   [GATED: Content or Form scored 0 → whole response scores 0]" if r.get("gating_applied") else ""),
        f"Verdict: {r.get('one_line_verdict', '')}",
        "",
        "Traits:",
    ]
    for tr in r.get("traits", []):
        lines.append(f"  {tr.get('name'):32} {tr.get('score')}/{tr.get('max')}   {tr.get('evidence', '')}")
        if tr.get("fix"):
            lines.append(f"      fix: {tr['fix']}")
    if r.get("top_priorities"):
        lines += ["", "Top priorities:"] + [f"  - {p}" for p in r["top_priorities"]]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Score a PTE Write Essay response.")
    p.add_argument("--prompt")
    p.add_argument("--prompt-file")
    p.add_argument("--essay")
    p.add_argument("--essay-file")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--json", action="store_true", help="Print raw JSON instead of a report.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:  # pick up OLLAMA_API_KEY from .env like the rest of the project
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    args = parse_args(argv)
    prompt_text = args.prompt or (open(args.prompt_file).read() if args.prompt_file else "")
    essay_text = args.essay or (open(args.essay_file).read() if args.essay_file else "")
    if not prompt_text or not essay_text:
        print("Provide --prompt/--prompt-file and --essay/--essay-file.", file=sys.stderr)
        return 2
    result = score_essay(prompt_text, essay_text, model=args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
