"""The advisory coach for maths reasoning — a model, kept firmly in its place.

math_reasoning_items.py already decided the things code can decide: was the answer
right, was real working shown. That verdict is final before this module runs. What
is left is the part no code can judge — whether a nine-year-old's explanation
actually explains anything — and for that a model is genuinely useful.

Three rules keep it advisory, enforced in _reconcile() rather than merely requested
in the prompt (a prompt is a wish; reconcile is a guarantee):

  1. It never decides correctness. The one-line verdict the learner reads is the
     deterministic message, always. The model's own sentence is demoted to a note.
  2. Its scores never enter raw_total and never reach the spaced-repetition
     scheduler. They ride in their own advisory block, flagged trait by trait.
  3. If it is unavailable or malformed, the learner still gets marked. The caller
     is expected to catch and carry on — see the endpoint in learning_materials_api.

Usage:
  python math_reasoning_feedback.py --demo      # grade one worked example
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

import httpx

from math_reasoning_items import ADVISORY_MAX_TOTAL, ADVISORY_TRAIT_MAX

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"

# Order is the order the learner reads them in.
TRAIT_ORDER = ["explains_why", "clear_steps", "maths_language"]

SYSTEM_PROMPT = """You are a warm, encouraging Year 5 (age 9-10) maths teacher in
Australia giving feedback on how a child EXPLAINED their thinking.

WHAT YOU ARE NOT DOING
Whether the child's answer and working are correct has already been decided by
software, exactly, and you are told the result. Do not re-mark it, do not argue
with it, and never tell the child they are right or wrong — that is not your job
here. If the software says the answer was wrong, still give warm, useful feedback
on the explaining, because explaining well is what this task practises.

WHAT YOU ARE JUDGING
Only the quality of the explanation, on three traits:

- explains_why (0-3): does the child give a REASON, not just a list of moves?
  0 = no reason at all, only numbers or "I just knew".
  1 = hints at a reason but it is vague ("because you have to").
  2 = a real reason, but partly unclear or incomplete.
  3 = a clear mathematical reason a classmate would find convincing
      (e.g. that the pieces must be the same size before you can add them).

- clear_steps (0-3): could a classmate follow what was done, in order?
  0 = no steps. 1 = jumbled or missing a step. 2 = mostly followable.
  3 = each step in order and it is obvious what each one was for.

- maths_language (0-2): correct, natural use of maths words
  (numerator, denominator, equivalent, simplest form, common denominator).
  0 = none or misused. 1 = some, or everyday words used correctly.
  2 = accurate maths vocabulary used naturally.

HOW TO WRITE IT
- Talk to the child, not about them. Short, plain sentences a 9-year-old reads
  easily. No jargon in your feedback unless you explain it.
- Be kind and specific. Never sarcastic, never discouraging.
- "evidence" must quote a few words the child actually wrote (or say
  "nothing written yet" if the response is empty).
- "fix" is ONE small concrete thing to add or change, phrased as an invitation.
- "strength" names one real thing they did well. Find something genuine, even in
  a weak response; if there is truly nothing, praise the attempt itself honestly.
- "next_step" is the single most useful thing to try next time, in one sentence.
- The worked example you are shown is ONE good answer, not the only one. A
  different but sound explanation is just as good — do not mark it down for
  being different.

STRICT OUTPUT CONTRACT
Reply with ONLY one fenced ```json code block containing one valid,
JSON.parse-able object. Include no prose before or after the code block.

Use exactly this structure:

{
  "traits": [
    {"name": "explains_why", "score": <integer 0-3>, "max": 3, "evidence": "<a few words the child wrote>", "fix": "<one small concrete thing to try>"},
    {"name": "clear_steps", "score": <integer 0-3>, "max": 3, "evidence": "<a few words the child wrote>", "fix": "<one small concrete thing to try>"},
    {"name": "maths_language", "score": <integer 0-2>, "max": 2, "evidence": "<a few words the child wrote>", "fix": "<one small concrete thing to try>"}
  ],
  "strength": "<one sentence naming something they genuinely did well>",
  "next_step": "<one sentence: the most useful thing to try next time>",
  "coach_note": "<one short encouraging sentence about their explaining>"
}"""


def build_messages(item: dict[str, Any], response: str, det: dict[str, Any]) -> list[dict[str, str]]:
    verdict = (
        "correct answer with working shown" if det.get("correct")
        else "answer correct but working not shown" if det.get("answer_shown")
        else "working shown but the final answer was wrong" if det.get("working_shown")
        else "neither the answer nor the working was right"
    )
    rubric = "\n".join(f"- {r}" for r in item.get("rubric", []))
    user = (
        f"THE QUESTION THE CHILD WAS ASKED:\n{item['question']}\n\n"
        f"WHAT A GOOD EXPLANATION COVERS:\n{rubric}\n\n"
        f"ONE GOOD WORKED ANSWER (not the only one):\n{item['model_answer']}\n\n"
        f"ALREADY DECIDED BY SOFTWARE (do not re-mark, do not contradict):\n"
        f"{verdict}. The correct answer is {item['answer_plain']}.\n\n"
        f"WHAT THE CHILD WROTE:\n{(response or '').strip() or '(nothing)'}\n\n"
        "Give feedback on the EXPLAINING only, and return the JSON."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


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


def _clean_sentence(value: Any, fallback: str, limit: int = 300) -> str:
    text = str(value or "").strip().replace("\n", " ")
    return (text[:limit] if text else fallback)


def _reconcile(result: dict[str, Any], det: dict[str, Any]) -> dict[str, Any]:
    """Make the advisory block structurally trustworthy whatever the model returned.

    Every trait present exactly once, in order, clamped to its max, and flagged
    advisory. Anything the model tried to say about correctness is dropped: the
    verdict belongs to the deterministic check.
    """
    by_name = {}
    for tr in result.get("traits", []) or []:
        name = tr.get("name")
        if name in ADVISORY_TRAIT_MAX and name not in by_name:
            by_name[name] = tr

    traits: list[dict[str, Any]] = []
    for name in TRAIT_ORDER:
        cap = ADVISORY_TRAIT_MAX[name]
        tr = by_name.get(name, {})
        try:
            score = int(tr.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        traits.append({
            "name": name,
            "score": max(0, min(score, cap)),
            "max": cap,
            "evidence": _clean_sentence(tr.get("evidence"), "", 240),
            "fix": _clean_sentence(tr.get("fix"), "", 240),
            # the flag the UI reads to style this as help, not a mark
            "advisory": True,
        })

    return {
        "traits": traits,
        "advisory_total": sum(t["score"] for t in traits),
        "advisory_max": ADVISORY_MAX_TOTAL,
        "strength": _clean_sentence(result.get("strength"), "You had a go at explaining your thinking."),
        "next_step": _clean_sentence(result.get("next_step"), "Try adding one sentence saying why you did each step."),
        "coach_note": _clean_sentence(result.get("coach_note"), ""),
        # stated in the payload so the UI can never present this as a mark by accident
        "advisory": True,
        "graded_by": "model",
    }


def score_reasoning(
    item: dict[str, Any],
    response: str,
    det: dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    timeout: float = 120.0,
    attempts: int = 2,
) -> dict[str, Any]:
    """Advisory feedback on how well the explanation explains. Raises on failure —
    callers are expected to carry on without it rather than fail the learner."""
    api_key = api_key or os.environ.get("OLLAMA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OLLAMA_API_KEY is not set. Create one at https://ollama.com/settings/keys "
            "and `export OLLAMA_API_KEY=...` (or add it to .env)."
        )
    messages = build_messages(item, response, det)
    last_err: Exception | None = None
    for _ in range(max(1, attempts)):
        resp = httpx.post(
            OLLAMA_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "stream": False,
                  "options": {"temperature": 0.2}},
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        try:
            return _reconcile(extract_json(content), det)
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = exc  # transient malformed JSON — retry once
    raise ValueError(f"Model did not return valid JSON after {attempts} attempts: {last_err}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="store_true", help="grade one worked example")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args(argv)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    import math_reasoning_items as mri

    item = mri.build_items(3)[0]
    response = args.demo and item["model_answer"] or item["model_answer"]
    det = mri.check_working(item, response)
    print(f"Q: {item['question']}\n\nA: {response}\n")
    print(f"deterministic: correct={det['correct']}  {det['message']}\n")
    advice = score_reasoning(item, response, det, model=args.model)
    for t in advice["traits"]:
        print(f"  {t['name']:16} {t['score']}/{t['max']}  {t['evidence']}")
        print(f"  {'':16} fix: {t['fix']}")
    print(f"\nadvisory total {advice['advisory_total']}/{advice['advisory_max']} (advisory — does not affect the mark)")
    print(f"strength : {advice['strength']}")
    print(f"next step: {advice['next_step']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
