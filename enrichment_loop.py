"""Close the loop: generate -> check -> fix -> re-check, until our checks accept it.

This is the payoff of exposing the evaluators. A model produces (or corrects) an
enrichment lesson; our checks judge it; if they flag a fixable defect, the flagged
findings go back to the model, it corrects only those, and we check again. No
human copies failures back and forth.

The properties that keep it from lying to us:

  - The stop condition is OUR verdict, never the model's. The loop ends only when
    `combine(...).accepted` is true — the model does not get to declare success.
  - It refuses to start if the checks can't prove they still bite. `health_report`
    runs each evaluator's planted-error self-test first; if any is unhealthy the
    loop does not run, because a broken checker would "accept" anything.
  - It stops, it does not grind, on ESCALATE — a human-judgment finding or a
    broken check. Looping there would burn calls against a wall.
  - It is capped. If it hasn't converged in `max_rounds`, it gives up and hands
    back the last state and history, rather than spinning forever.

And the honest limit, stated in the result: acceptance means no *known* defect
remains — the checks we have — not that the lesson is excellent.

The fixer is injected, so the control logic is testable with no network (a fake
fixer) and runnable live with the model (ollama_fixer).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import httpx

import pipeline_evaluators as P
from evaluation_contract import combine

OLLAMA_URL = "https://ollama.com/api/chat"
DEFAULT_MODEL = "gpt-oss:120b"

# A fixer takes (lesson, fixable_findings) and returns a corrected lesson dict.
Fixer = Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]]


class LoopError(RuntimeError):
    pass


def close_loop(
    lesson: dict[str, Any],
    *,
    fixer: Fixer,
    max_rounds: int = 5,
    deep_health: bool = False,
) -> dict[str, Any]:
    """Drive one enrichment lesson to acceptance (or escalate / give up).

    Returns {status, rounds, lesson, history, ...}. status is one of:
      accepted   the checks accept it; `lesson` is the accepted version.
      escalate   a finding needs a human, or a check is unhealthy; stopped.
      refused    the checks failed their self-test; the loop never ran.
      gave_up    still failing after max_rounds; `lesson` is the last attempt.
    """
    health = P.health_report(deep=deep_health)
    if not health["all_healthy"]:
        return {
            "status": "refused",
            "reason": "evaluators failed their self-test; a broken check cannot be trusted to accept anything",
            "health": health,
            "rounds": 0,
            "history": [],
        }

    current = lesson
    history: list[dict[str, Any]] = []

    for rnd in range(1, max_rounds + 1):
        res = combine(P.evaluate("enrichment_lesson", current))
        fixable = [f for r in res["results"] for f in r["findings"] if f.get("fixable")]
        blocking = [f for r in res["results"] for f in r["findings"] if not f.get("fixable")]
        history.append({
            "round": rnd,
            "verdict": res["verdict"],
            "findings": [f["summary"] for r in res["results"] for f in r["findings"]],
        })

        if res["accepted"]:
            return {"status": "accepted", "rounds": rnd, "lesson": current,
                    "history": history, "note": _accept_note()}
        if res["verdict"] == "escalate":
            return {"status": "escalate", "rounds": rnd, "lesson": current,
                    "history": history, "escalate_findings": blocking or fixable}

        # verdict == fix: hand the flagged findings back to the model.
        try:
            nxt = fixer(current, fixable)
        except Exception as exc:  # a bad correction is a round failure, not a crash
            history[-1]["fixer_error"] = f"{type(exc).__name__}: {exc}"
            return {"status": "gave_up", "rounds": rnd, "lesson": current,
                    "history": history, "reason": "fixer failed to produce a valid lesson"}
        if not isinstance(nxt, dict):
            history[-1]["fixer_error"] = "fixer did not return a lesson object"
            return {"status": "gave_up", "rounds": rnd, "lesson": current, "history": history}
        current = nxt

    final = combine(P.evaluate("enrichment_lesson", current))
    return {
        "status": "accepted" if final["accepted"] else "gave_up",
        "rounds": max_rounds,
        "lesson": current,
        "history": history,
        "note": _accept_note() if final["accepted"] else "did not converge within max_rounds",
    }


def _accept_note() -> str:
    return ("Accepted means no KNOWN defect remains (the checks we run) — not that "
            "the lesson is excellent. Passing checks is a floor, not a certificate.")


# --------------------------------------------------------------------------- #
# The live fixer — the model corrects only what the checks flagged
# --------------------------------------------------------------------------- #

_FIX_SYSTEM = """You correct PTE Academic enrichment lessons.

You are given a lesson as JSON and a list of SPECIFIC problems an automated checker
found. Fix exactly those problems and nothing else. Preserve every other field and
all wording that was not flagged. The problem descriptions tell you what is wrong
and often the exact value to use (e.g. a required word range).

STRICT OUTPUT CONTRACT: reply with ONLY one fenced ```json code block containing
the COMPLETE corrected lesson object."""

import re as _re

_FENCE = _re.compile(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", _re.DOTALL)


def _extract_json(text: str) -> Any:
    text = (text or "").strip()
    for cand in (text, *(m.group(1) for m in _FENCE.finditer(text))):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue
    raise LoopError(f"no JSON object in model reply: {text[:160]!r}")


def ollama_fixer(model: str = DEFAULT_MODEL, *, timeout: float = 300.0) -> Fixer:
    def fix(lesson: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
        api_key = os.environ.get("OLLAMA_API_KEY")
        if not api_key:
            raise LoopError("OLLAMA_API_KEY is not set (add it to .env).")
        problems = "\n".join(
            f"{i+1}. {f['summary']} {f.get('detail','')}".strip()
            for i, f in enumerate(findings)
        )
        user = (f"LESSON JSON:\n{json.dumps(lesson, ensure_ascii=False)}\n\n"
                f"PROBLEMS TO FIX (change only these):\n{problems}\n\n"
                f"Return the complete corrected lesson.")
        resp = httpx.post(
            OLLAMA_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "stream": False, "options": {"temperature": 0.2},
                  "messages": [{"role": "system", "content": _FIX_SYSTEM},
                               {"role": "user", "content": user}]},
            timeout=timeout,
        )
        resp.raise_for_status()
        return _extract_json(resp.json().get("message", {}).get("content", ""))
    return fix
