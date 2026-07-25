"""MCP server: every loop-fit checker we have, handed to an LLM as tools.

Supersedes enrichment_mcp_server.py — same design, wider coverage. It exposes the
checks across stages (extraction, the practice banks, enrichment) from the one
registry in pipeline_evaluators, all under the same contract and the same honesty
gate.

The rules the tools enforce, so the model cannot grade itself:
  - It chooses WHICH checks to call, from their descriptions.
  - It does NOT decide whether it passed — the verdict is ours, in code.
  - A check may only return PASS if, on this run, it caught its own planted error
    (`check_health`). An unhealthy check escalates; it never certifies.

Verdicts to obey: pass (accept), fix (regenerate the flagged part, loop),
escalate (a human's call, or a broken/damaged input — stop, do not loop).

Run:
  python evaluator_mcp_server.py            # stdio, for Claude Desktop / clients
"""

from __future__ import annotations

from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from mcp.server.fastmcp import FastMCP

import content_contract
import pipeline_evaluators as P
from evaluation_contract import combine

mcp = FastMCP("pte-evaluators")


@mcp.tool()
def list_evaluators() -> list[dict[str, str]]:
    """List every checker, what artifact it consumes, and what it proves.

    Read the descriptions to pick which apply to what you just generated, then
    call the matching check tool. `kind` is "deterministic" (fast, same answer
    every run) or "model" (uses the model, slower, advisory).
    """
    return [
        {"name": ev.name, "artifact": ev.artifact, "kind": ev.kind, "description": ev.description}
        for ev in P.REGISTRY.values()
    ]


@mcp.tool()
def check_health(deep: bool = False) -> dict[str, Any]:
    """Prove the checkers still work by running each one's planted-error tests.

    Each is fed inputs whose right answer is already known and must flag the
    broken ones and pass the sound ones. Any that fails is reported unhealthy and
    will refuse to certify until fixed. `all_healthy` is the single signal.

    deep=false (default) runs only the fast deterministic checks. deep=true also
    runs the model checks' self-tests, which cost model calls.
    """
    return P.health_report(deep=deep)


@mcp.tool()
def check_extraction(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    """Check extracted source chunks for empty or gap-damaged text.

    `chunks` is the list of chunk objects (each with a "text"). Damage escalates,
    it does not "fix" — bad extraction must be re-extracted, not reworded around.
    """
    return combine(P.evaluate("clean_chunks", chunks))


@mcp.tool()
def check_reading_item(item: dict[str, Any], verify_answer_key: bool = False) -> dict[str, Any]:
    """Check one Reading Multiple-Choice question.

    Always runs the deterministic shape check. With verify_answer_key=true it also
    runs the model blind-solver (slower): independent solvers answer the question
    without seeing the key, and it flags the item if they don't agree with it.
    """
    return combine(P.evaluate("reading_item", item, include_model=verify_answer_key))


@mcp.tool()
def check_describe_image_item(item: dict[str, Any]) -> dict[str, Any]:
    """Check one Describe Image chart item's shape (chart type, point count, value
    rules, pie totals). `item` is the chart-item object."""
    return combine(P.evaluate("describe_image_item", item))


@mcp.tool()
def evaluate_enrichment_lesson(lesson: dict[str, Any]) -> dict[str, Any]:
    """Run every enrichment check against a lesson and return the binding verdict.

    `lesson` is the enrichment JSON (needs "task_type" and "overview"). Findings
    marked fixable tell you exactly what to change; loop until accepted, and
    surface any escalate finding to a human.
    """
    return combine(P.evaluate("enrichment_lesson", lesson))


@mcp.tool()
def evaluate_with(evaluator_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one named checker against a payload (see `list_evaluators` for names and
    which artifact each expects). Useful to re-check just the thing you fixed. It
    still refuses to return pass if that checker failed its own self-test."""
    try:
        result = P.evaluate_one(evaluator_name, payload)
    except KeyError as exc:
        return {"error": str(exc), "available": list(P.REGISTRY)}
    return combine([result])


if __name__ == "__main__":
    mcp.run()


@mcp.tool()
def check_book_contract(book: str, limit: int | None = None) -> dict[str, Any]:
    """Can this book teach anybody yet?

    Maps a book onto the teaching contract and runs the content checks over it:
    every lesson able to fill a priming screen, every skill carrying an
    explanation, an example and its usual mistake, no circular definitions, and
    no example sentences that are a template with the word swapped out.

    Returns counts and the findings. `accepted` is false if anything was
    rejected — the book is not ready to put in front of a learner.

    book: "math5a", "pte", or "ela".
    """
    lessons, skills = content_contract.load_book(book, limit)
    r = content_contract.check_book(lessons, skills)
    return {
        "book": book,
        "lessons": r["lessons"],
        "skills": r["skills"],
        "teachable": r["teachable"],
        "rejected": r["rejected"],
        "accepted": r["accepted"],
        "by_check": dict(r["by_check"]),
        "findings": [
            {"check": f.check, "severity": f.severity, "where": f.where, "detail": f.detail}
            for f in r["findings"][:200]
        ],
    }
