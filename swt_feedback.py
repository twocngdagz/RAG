"""Score a PTE Academic "Summarize Written Text" response and return feedback.

Same shape as essay_feedback.py (hosted model on Ollama Cloud, strict JSON, code
owning the mechanical checks), but SWT scores on a different, smaller rubric.

Rubric — current public Pearson criteria (Score Guide pp. 32-33), raw total 0-9:
  Content 0-4 | Form 0-1 | Grammar 0-2 | Vocabulary 0-2
Form is 1 only for ONE single complete sentence of 5-75 words, not in capitals.
Gating (Score Guide p. 8): if Content or Form is 0, the whole response scores 0.

No 10-90 conversion: a single response can't be officially converted to a PTE
score (Pearson computes that from whole-test performance). Raw total only.

Usage:
  export OLLAMA_API_KEY=...        # or .env
  python swt_feedback.py --passage-file p.txt --summary "The passage argues that..."
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
MAX_RAW_TOTAL = 9

TRAIT_MAX = {"content": 4, "form": 1, "grammar": 2, "vocabulary": 2}

# Traits whose score code computes rather than the model — disclosed per trait
# so a learner can tell a measured mark from a judged one.
CODE_SCORED_TRAITS = {"form"}

SYSTEM_PROMPT = """You are a PTE Academic rater and feedback coach evaluating a
Summarize Written Text response: the test taker must summarise the source passage
in ONE single complete sentence of 5-75 words.

Apply the criteria below strictly. Judge only the response against the supplied
passage. Do not invent ideas or errors that are not present.

TRAITS (raw maximum 9)

1. CONTENT - 0 to 4
4: The source text is summarised comprehensively, demonstrating full
   comprehension. Paraphrasing is used effectively; extraneous detail is removed.
   All main ideas are correctly identified and synthesised concisely and
   coherently, with appropriate and varied connective devices.
3: Summarised adequately, demonstrating good comprehension. Paraphrasing is used
   but not consistently well, and extraneous details may interfere with clarity.
   Main ideas are correct with minor omissions; ideas are connected but not
   synthesised efficiently. Simple or repetitive connectives.
2: Summarised partially, demonstrating basic comprehension. No discernment
   between main points and peripheral detail. Relies heavily on repeating
   excerpts from the source without reformulating in own words. Can be followed
   with effort.
1: Relevant but not meaningfully summarised; limited comprehension. Disconnected
   ideas or excerpts without context or synthesis. Main ideas omitted or
   misrepresented. Lacks coherence.
0: Too limited to score higher; demonstrates no comprehension of the source text.

2. FORM - 0 to 1
1: Written in one, single, complete sentence.
0: Not one single complete sentence, OR fewer than 5 or more than 75 words, OR
   written in capital letters.

3. GRAMMAR - 0 to 2
2: Correct grammatical structure.
1: Contains grammatical errors but with no hindrance to communication.
0: Defective grammatical structure which could hinder communication.

4. VOCABULARY - 0 to 2
2: Appropriate choice of words.
1: Contains lexical errors but with no hindrance to communication.
0: Defective word choice which could hinder communication.

GATING RULE
If Content is 0 or Form is 0:
- Set every trait score to 0 and raw_total to 0.
- Still explain the failure and give useful corrections.

KEY JUDGEMENT
Reward genuine paraphrase and synthesis of the MAIN ideas. Penalise a summary
that merely stitches together copied excerpts, or that captures a peripheral
detail while missing the passage's central claim.

NEVER SUGGEST SPLITTING THE SENTENCE
A conforming response is exactly ONE sentence, so never advise splitting it into
two sentences, starting a new sentence, or adding a full stop mid-response —
that advice would score the test taker 0 for Form. If a response is unwieldy,
advise tightening the wording, cutting extraneous detail, or using commas,
semicolons and connectives within the single sentence instead.

SURFACE ERRORS
In "errors", list up to 15 concrete, correctable surface errors in the response -
spelling, grammar, punctuation, and clear word-choice mistakes. "wrong" MUST be
the exact text as it appears in the response (a short span), "correct" the
minimal fix, "type" one of: spelling, grammar, punctuation, word_choice. List
them in order of appearance. No stylistic rewrites.

SCORING RULES
- Whole-number scores only, each within its stated range.
- raw_total must equal the sum of the four trait scores.
- Do NOT convert the result into an official PTE score from 10 to 90.
- Evidence must quote a short span of the response or passage.
- Each fix must be one concrete action.

STRICT OUTPUT CONTRACT
Reply with ONLY one fenced ```json code block containing one valid,
JSON.parse-able object, no prose before or after. Use exactly this structure:

{
  "word_count": <integer>,
  "gating_applied": <true or false>,
  "traits": [
    {"name": "content", "score": <int>, "max": 4, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "form", "score": <int>, "max": 1, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "grammar", "score": <int>, "max": 2, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"},
    {"name": "vocabulary", "score": <int>, "max": 2, "evidence": "<brief evidence>", "fix": "<one concrete improvement>"}
  ],
  "raw_total": <integer 0 to 9>,
  "max_raw_total": 9,
  "errors": [{"type": "<spelling|grammar|punctuation|word_choice>", "wrong": "<exact text>", "correct": "<corrected>"}],
  "top_priorities": ["<one to three highest-impact improvements>"],
  "one_line_verdict": "<one encouraging but honest sentence>"
}"""


def build_messages(passage: str, summary: str) -> list[dict[str, str]]:
    user = (
        f"SOURCE PASSAGE:\n{passage.strip()}\n\n"
        f"TEST TAKER'S ONE-SENTENCE SUMMARY:\n{summary.strip()}\n\n"
        "Score this summary now and return the JSON."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# --------------------------------------------------------------------------- #
# Deterministic checks — Form is mechanical, so compute it in code.
# --------------------------------------------------------------------------- #

def count_words(text: str) -> int:
    return len(text.split())


def sentence_count(text: str) -> int:
    """Number of terminal-punctuated sentences. A conforming SWT response is 1."""
    parts = [p for p in re.split(r"[.!?]+(?=\s|$)", text.strip()) if p.strip()]
    return len(parts)


def form_score(text: str) -> tuple[int, str]:
    """Deterministic Form (0-1) with the reason, per the official criteria."""
    stripped = text.strip()
    wc = count_words(stripped)
    letters = [c for c in stripped if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return 0, "written in capital letters"
    if wc < 5:
        return 0, f"{wc} words (fewer than 5)"
    if wc > 75:
        return 0, f"{wc} words (more than 75)"
    n = sentence_count(stripped)
    if n > 1:
        return 0, f"{n} sentences (must be one single sentence)"
    return 1, f"one sentence, {wc} words (within 5-75)"


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


def _reconcile(result: dict[str, Any], summary: str) -> dict[str, Any]:
    """Authoritative word count + Form from code, clamp traits, apply gating,
    recompute raw_total — so the numbers are always self-consistent."""
    wc = count_words(summary)
    result["word_count"] = wc
    code_form, reason = form_score(summary)

    for tr in result.get("traits", []):
        name = tr.get("name")
        # Form is mechanical (computed below); the rest is the model's judgement.
        tr["scored_by"] = "code" if name in CODE_SCORED_TRAITS else "model"
        cap = TRAIT_MAX.get(name)
        if cap is None:
            continue
        tr["max"] = cap
        tr["score"] = max(0, min(int(tr.get("score", 0)), cap))
        if name == "form":  # mechanical → code wins
            tr["score"] = code_form
            tr["evidence"] = f"{reason}."

    by_name = {tr.get("name"): tr for tr in result.get("traits", [])}
    gated = by_name.get("content", {}).get("score", 0) == 0 or by_name.get("form", {}).get("score", 0) == 0
    result["gating_applied"] = gated
    if gated:
        for tr in result.get("traits", []):
            tr["score"] = 0
        result["raw_total"] = 0
    else:
        result["raw_total"] = sum(tr.get("score", 0) for tr in result.get("traits", []))
    result["max_raw_total"] = MAX_RAW_TOTAL
    result["scored_by"] = "model"
    return result


def score_summary(
    passage: str,
    summary: str,
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
            "and add it to .env."
        )
    messages = build_messages(passage, summary)
    last_err: Exception | None = None
    for _ in range(max(1, attempts)):
        resp = httpx.post(
            OLLAMA_URL,
            headers={"Authorization": f"Bearer {api_key}"},
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
            return _reconcile(extract_json(content), summary)
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = exc
    raise ValueError(f"Model did not return valid JSON after {attempts} attempts: {last_err}")


def format_report(r: dict[str, Any]) -> str:
    total, mx = r.get("raw_total", "?"), r.get("max_raw_total", MAX_RAW_TOTAL)
    lines = [
        f"Raw rubric total: {total}/{mx}  (not an official PTE score)",
        f"Words: {r.get('word_count', '?')}"
        + ("   [GATED: Content or Form scored 0 → whole response scores 0]" if r.get("gating_applied") else ""),
        f"Verdict: {r.get('one_line_verdict', '')}",
        "",
        "Traits:",
    ]
    for tr in r.get("traits", []):
        lines.append(f"  {tr.get('name'):12} {tr.get('score')}/{tr.get('max')}   {tr.get('evidence', '')}")
        if tr.get("fix"):
            lines.append(f"      fix: {tr['fix']}")
    if r.get("errors"):
        lines += ["", "Corrections:"] + [
            f"  [{e.get('type')}] {e.get('wrong')!r} -> {e.get('correct')!r}" for e in r["errors"]
        ]
    if r.get("top_priorities"):
        lines += ["", "Top priorities:"] + [f"  - {p}" for p in r["top_priorities"]]
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Score a PTE Summarize Written Text response.")
    p.add_argument("--passage")
    p.add_argument("--passage-file")
    p.add_argument("--summary")
    p.add_argument("--summary-file")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--json", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    args = parse_args(argv)
    passage = args.passage or (open(args.passage_file).read() if args.passage_file else "")
    summary = args.summary or (open(args.summary_file).read() if args.summary_file else "")
    if not passage or not summary:
        print("Provide --passage/--passage-file and --summary/--summary-file.", file=sys.stderr)
        return 2
    result = score_summary(passage, summary, model=args.model)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else format_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
