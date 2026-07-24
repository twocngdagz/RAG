# Evaluators as tools — the MCP server

We built a lot of checks — word ranges, trait names, guide contradictions, blind
solvers — and for a long time a human ran them by hand and pasted the failures
back into chat. This server closes that loop: it hands the checks to the LLM as
tools it can call, so the model verifies and fixes its own output against ground
truth before a human sees it.

The rule the whole thing turns on: **the model is not the judge.** It chooses
which checks to call, but whether it passed is our verdict, computed in code, from
checks that have proven — on that run — they still catch a planted error.

## The pieces

| File | What it is |
|---|---|
| `evaluation_contract.py` | The shared shape every evaluator returns, and the gate that turns findings into one binding verdict. |
| `enrichment_evaluators.py` | Wraps the existing `audit_enrichment_facts.py` checks in that shape. Adds no checking logic; adds a planted-error self-test to each. |
| `enrichment_mcp_server.py` | The MCP layer: exposes the evaluators as four tools over stdio. |
| `test_evaluation_contract.py` | Unit test: the verdict logic and the honesty gate. No network. |
| `test_enrichment_mcp.py` | Drives the server over a real stdio client, end to end. |

## The three verdicts

- **pass** — no known defect. Accept the lesson. (Means "no trap we check for was
  hit", not "this lesson is excellent".)
- **fix** — a concrete, mechanical defect the generator can correct. Each finding
  says exactly what to change. This is the loop: regenerate, resubmit.
- **escalate** — stop. Either a genuinely ambiguous point that is a human's call
  (does Answer Short Question test speaking, when the guide's table says only
  Listening?), or an evaluator that failed its own self-test. Never loop on this.

## The honesty gate

Three times in this project a check silently stopped catching anything while still
printing green. So an evaluator here can only return **pass** if, on the same run,
it caught its own planted error. `check_health` runs those planted-error tests;
any evaluator that fails is marked unhealthy, and an unhealthy evaluator's empty
finding list is reported as **escalate**, never pass.

This is enforced by making the self-test and the live run call the *same* function
(`findings_fn`). An earlier version held a separate reference to the check for its
self-test — so breaking the live path left the self-test passing, and a rotted
check still certified. The tests pin this: `test_evaluation_contract.py` breaks
`check_word_range` and asserts the gate turns the result to escalate.

## The tools

- `list_evaluators()` — names + descriptions, so the model can pick what applies.
- `check_health()` — run every evaluator's planted-error self-test. Call before
  trusting a run; `all_healthy` is the single signal.
- `evaluate_lesson(lesson)` — run all applicable checks, return the binding
  verdict. `lesson` is the enrichment JSON (needs `task_type` and `overview`).
- `evaluate_with(evaluator_name, lesson)` — run one named check; handy to
  re-verify just the thing you fixed.

## Run it

```bash
# smoke-test the checks and the gate (no network)
python test_evaluation_contract.py

# drive the server exactly as a client would (spawns it over stdio)
python test_enrichment_mcp.py

# run the server itself (stdio)
python enrichment_mcp_server.py
```

### Connect it to Claude Desktop

Add to `claude_desktop_config.json` (needs `OLLAMA_API_KEY` in `.env` for the
guide-contradiction judge; the deterministic checks run without it):

```json
{
  "mcpServers": {
    "pte-enrichment-evaluators": {
      "command": "/Users/roy/Documents/RAG Prototype/.venv/bin/python",
      "args": ["/Users/roy/Documents/RAG Prototype/enrichment_mcp_server.py"],
      "cwd": "/Users/roy/Documents/RAG Prototype"
    }
  }
}
```

Then: generate a lesson, ask the model to call `evaluate_lesson`, and have it fix
whatever comes back `fix` and resubmit until `accepted` is true — surfacing any
`escalate` to you rather than looping on it.

## Adding an evaluator

Register it in `enrichment_evaluators.py` with a `findings_fn(doc) -> [Finding]`
and at least two planted-error self-tests (one that must flag, one that must not).
It joins `evaluate_lesson` automatically and inherits the honesty gate. Keep the
mechanical judgement in code; reserve the model for open-ended wording, and treat
those verdicts as advisory.
