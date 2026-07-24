"""The standard shape every evaluator speaks, so one agent can loop over any check.

The point of exposing our checks to an LLM is that it can call them, read what
failed, fix its own output, and call again — until the checks accept it. For that
loop to be generic (work for a check we haven't written yet), every evaluator has
to answer in the SAME shape, and the loop's stop condition has to be OUR verdict,
never the model's opinion of its own work.

Three verdicts, not two — this distinction is the whole design:

  PASS      nothing to fix.
  FIX       a concrete, mechanical defect the generator can correct and re-submit
            (a missing word range, a wrong trait name). Loop on these.
  ESCALATE  a real question that is not the model's to settle (does "Answer Short
            Question" test speaking, when the guide's table says only Listening?).
            The loop must STOP and surface it to a human, not grind against it.

And one safety property that outranks all of them: an evaluator is only allowed to
say PASS if it has proven, on this run, that it can still catch a planted error.
A check that has silently rotted must never certify anything — a dead checker
returning PASS is worse than no checker, because it manufactures the exact
confidence the check exists to provide. `health` carries that proof.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    PASS = "pass"
    FIX = "fix"
    ESCALATE = "escalate"


@dataclass
class Finding:
    """One thing an evaluator has to say about the input."""
    summary: str                       # one line, plain enough to act on
    detail: str = ""                   # the why, with specifics
    evidence: str = ""                 # the ground-truth quote it relied on, if any
    fixable: bool = True               # True -> FIX (retry), False -> ESCALATE (human)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluatorResult:
    """What every evaluator returns, and the only thing the agent should trust."""
    evaluator: str
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)
    # Did this evaluator prove, on this run, that it still catches planted errors?
    # PASS is not honoured from an unhealthy evaluator (see verdict_of).
    healthy: bool = True
    health_note: str = ""
    # Free-form extras an evaluator may add (model verdicts it treats as advisory,
    # the guide pages it read, etc.). Never load-bearing for the loop.
    advisory: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


def verdict_of(findings: list[Finding], *, healthy: bool) -> Verdict:
    """Turn findings into the single verdict the loop obeys.

    - Any non-fixable finding -> ESCALATE (a human decides; do not loop).
    - Any fixable finding      -> FIX (regenerate and try again).
    - None                     -> PASS, but ONLY from a healthy evaluator. An
      evaluator that failed its own self-test cannot certify anything, so its
      empty finding list is reported as ESCALATE, not a false all-clear.
    """
    if any(not f.fixable for f in findings):
        return Verdict.ESCALATE
    if findings:
        return Verdict.FIX
    return Verdict.PASS if healthy else Verdict.ESCALATE


def combine(results: list[EvaluatorResult]) -> dict[str, Any]:
    """The gate: collapse every applicable evaluator into one answer for the loop.

    The whole batch is PASS only if every evaluator passed. One FIX makes the
    batch FIX; any ESCALATE (including an unhealthy evaluator) makes it ESCALATE,
    because an unresolved human question or a broken checker both mean "do not
    accept this output yet".
    """
    verdicts = {r.verdict for r in results}
    if Verdict.ESCALATE in verdicts or any(not r.healthy for r in results):
        overall = Verdict.ESCALATE
    elif Verdict.FIX in verdicts:
        overall = Verdict.FIX
    else:
        overall = Verdict.PASS

    unhealthy = [r.evaluator for r in results if not r.healthy]
    return {
        "verdict": overall.value,
        "accepted": overall is Verdict.PASS,
        "evaluators_run": [r.evaluator for r in results],
        "unhealthy_evaluators": unhealthy,
        "results": [r.to_dict() for r in results],
        "next_action": _guidance(overall, unhealthy),
    }


def _guidance(overall: Verdict, unhealthy: list[str]) -> str:
    if unhealthy:
        return (f"Do not trust this result. These checks failed their own self-test "
                f"and cannot certify anything: {', '.join(unhealthy)}. Fix the "
                f"evaluator before relying on the loop.")
    if overall is Verdict.PASS:
        return ("All applicable checks passed. This means no known defect was found — "
                "it does not certify the lesson is excellent, only that the traps we "
                "check for were avoided.")
    if overall is Verdict.FIX:
        return ("Regenerate the flagged parts and submit again. Every finding marked "
                "fixable tells you exactly what to change.")
    return ("Stop and surface the escalate findings to a human — these are not the "
            "model's call to make. Do not loop on them.")
