"""MCP server: hands our verified enrichment evaluators to an LLM as callable tools.

This is packaging, not new logic. The checks live in audit_enrichment_facts.py and
are wrapped in the standard contract by enrichment_evaluators.py. This server just
exposes them over MCP so a model — in Claude Desktop, or a generation pipeline —
can call them, read what failed, fix its own lesson, and call again, until the
checks accept it.

The design rule the tools enforce, so a model cannot talk its way past it:
  - The model chooses WHICH tools to call (from their descriptions).
  - The model does NOT decide whether it passed. `evaluate_lesson` runs every
    applicable check and returns OUR verdict; `accepted` is true only when they
    all pass AND all are healthy.
  - `check_health` runs each evaluator's planted-error self-test. An evaluator
    that cannot catch its own planted error is reported unhealthy and can never
    return a passing verdict — a rotted check must not certify anything.

Verdicts a caller must obey:
  pass      -> accept the lesson.
  fix       -> regenerate the flagged parts and resubmit (the loop).
  escalate  -> stop; a human decides. Either a genuinely ambiguous point, or a
               broken evaluator. Never loop on escalate.

Run:
  python enrichment_mcp_server.py            # stdio, for Claude Desktop / clients
"""

from __future__ import annotations

from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP

import enrichment_evaluators as evaluators
from evaluation_contract import combine

mcp = FastMCP("pte-enrichment-evaluators")


@mcp.tool()
def list_evaluators() -> list[dict[str, str]]:
    """List every enrichment evaluator and what it checks.

    Read the descriptions to decide which checks apply to the lesson you are
    writing, then call `evaluate_lesson` to run all applicable ones at once, or
    `evaluate_with` to run a single named check.
    """
    return [
        {"name": ev.name, "description": ev.description}
        for ev in evaluators.REGISTRY.values()
    ]


@mcp.tool()
def check_health() -> dict[str, Any]:
    """Prove the evaluators still work, by running each one's planted-error tests.

    Call this before trusting a run. Each evaluator is fed inputs whose right
    answer is already known — some broken, some sound — and must flag the broken
    ones and pass the sound ones. Any evaluator that fails is reported unhealthy
    and will refuse to certify a lesson until it is fixed. `all_healthy` is the
    single signal: if false, do not rely on a passing verdict.
    """
    return evaluators.health_report()


@mcp.tool()
def evaluate_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    """Run every applicable check against a lesson and return the binding verdict.

    `lesson` is the enrichment JSON object (must include "task_type" and an
    "overview" with its format_facts, critical_rules and scoring_factors).

    Returns the combined result. Obey `verdict`:
      - "pass": `accepted` is true; the lesson cleared every check.
      - "fix": at least one check found a fixable defect. Each finding says
        exactly what to change. Regenerate those parts and call again.
      - "escalate": stop. Either a finding needs a human decision, or a check is
        unhealthy (see `unhealthy_evaluators`). Do not loop.

    A "pass" means no known defect was found — it does not certify the lesson is
    excellent, only that the traps these checks cover were avoided.
    """
    results = evaluators.evaluate_all(lesson)
    return combine(results)


@mcp.tool()
def evaluate_with(evaluator_name: str, lesson: dict[str, Any]) -> dict[str, Any]:
    """Run one named check against a lesson (see `list_evaluators` for names).

    Same result shape and verdict meaning as `evaluate_lesson`, for a single
    evaluator — useful to re-check just the thing you fixed. It still refuses to
    return "pass" if that evaluator failed its own self-test.
    """
    try:
        result = evaluators.evaluate_one(evaluator_name, lesson)
    except KeyError as exc:
        return {"error": str(exc), "available": list(evaluators.REGISTRY)}
    return combine([result])


if __name__ == "__main__":
    mcp.run()
