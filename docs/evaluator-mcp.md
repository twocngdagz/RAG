# Evaluators as tools — the MCP server

We built a lot of checks across every stage — extraction damage, question-bank
shape, chart-item shape, enrichment facts — and for a long time a human ran them
by hand and pasted the failures back into chat. This server closes that gap: it
hands the checks to the LLM as tools it can call, so the model verifies and fixes
its own output against ground truth before a human sees it.

The rule the whole thing turns on: **the model is not the judge.** It chooses
which checks to call, but whether it passed is our verdict, computed in code, from
checks that have proven — on that run — they still catch a planted error.

## The pieces

| File | What it is |
|---|---|
| `evaluation_contract.py` | The shared shape every evaluator returns, and the gate that turns findings into one binding verdict. |
| `pipeline_evaluators.py` | The unified registry: wraps our existing checks (extraction, reading bank, describe-image bank, enrichment) in that shape, each with planted-error self-tests. Adds no checking logic. |
| `enrichment_evaluators.py` | The enrichment checks, reused by the registry above. |
| `evaluator_mcp_server.py` | The MCP layer: exposes every stage's checks as tools over stdio. |
| `enrichment_loop.py` | Closes the loop in code: generate → check → fix → re-check until the checks accept, or escalate, or the cap. |
| `test_evaluation_contract.py` | Unit test: verdict logic + the honesty gate. No network. |
| `test_evaluator_mcp.py` | Drives the server over a real stdio client, every stage, end to end. |

## The three verdicts

- **pass** — no known defect. Accept. (Means "no trap we check for was hit", not
  "this is excellent".)
- **fix** — a concrete defect the generator can correct and resubmit. The loop.
- **escalate** — stop. Either a human-judgment point, a damaged *source* (bad
  extraction is re-extracted, not reworded around), or a checker that failed its
  own self-test. Never loop on escalate.

## What is exposed (and what is not)

Checks come in two kinds:

- **deterministic** — pure code, same answer every run. The fast backbone.
- **model** — uses the model (the reading blind-solver). Slower, advisory; its
  self-test costs model calls, so it runs only in a *deep* health check.

| Evaluator | Artifact | Kind | Catches |
|---|---|---|---|
| `extraction_damage` | clean_chunks | deterministic | empty / gap-garbled extracted text |
| `reading_item_shape` | reading_item | deterministic | malformed question (options, keys, rationale) |
| `describe_image_item_shape` | describe_image_item | deterministic | malformed chart (points, values, pie totals) |
| `reading_answer_key` | reading_item | model | an answer key independent solvers won't agree with |
| `word_range` | enrichment_lesson | deterministic | a lesson that never states the word range Form gates on |
| `trait_names` | enrichment_lesson | deterministic | an official trait name attached to the wrong task |

**Deliberately NOT exposed here:** the grounded-base contract validator, the
claim-support audit, and the targeted evaluation. Those are batch pipelines —
disk fixtures, checkpoint/resume, long model runs — that do not fit a live
generate→check→fix loop. Wrapping them as synchronous tools without an honest
self-test would be exactly the false-confidence trap this design exists to
prevent. They need an async job interface, tracked as separate work.

## The honesty gate

Three times in this project a check silently stopped catching anything while still
printing green. So a checker here can only return **pass** if, on the same run, it
caught its own planted error. `check_health` runs those planted-error tests; any
that fails is marked unhealthy, and an unhealthy checker's empty finding list is
reported as **escalate**, never pass.

This is enforced by making the self-test and the live run call the *same* function
(`findings_fn`). An earlier version held a separate reference for the self-test —
so breaking the live path left the self-test passing, and a rotted check still
certified. `test_evaluation_contract.py` breaks `check_word_range` and asserts the
gate turns the result to escalate.

## The tools

- `list_evaluators()` — name, artifact, kind, description for each check.
- `check_health(deep=false)` — planted-error self-tests. deep=true also runs the
  model checks. `all_healthy` is the single signal.
- `check_extraction(chunks)` — extracted source chunks.
- `check_reading_item(item, verify_answer_key=false)` — shape always; the model
  blind-solver when asked.
- `check_describe_image_item(item)` — chart item shape.
- `evaluate_enrichment_lesson(lesson)` — all enrichment checks, binding verdict.
- `evaluate_with(evaluator_name, payload)` — one named check; re-verify a fix.

## Run it

```bash
python test_evaluation_contract.py   # verdict logic + gate, no network
python test_evaluator_mcp.py         # drive the server over stdio, every stage
python evaluator_mcp_server.py       # run the server itself (stdio)
```

### Connect it to Claude Desktop

Add to `claude_desktop_config.json` (needs `OLLAMA_API_KEY` in `.env` for the
model checks; the deterministic ones run without it):

```json
{
  "mcpServers": {
    "pte-evaluators": {
      "command": "/Users/roy/Documents/RAG Prototype/.venv/bin/python",
      "args": ["/Users/roy/Documents/RAG Prototype/evaluator_mcp_server.py"],
      "cwd": "/Users/roy/Documents/RAG Prototype"
    }
  }
}
```

Then: generate something, ask the model to call the matching check, and have it
fix whatever comes back `fix` and resubmit until `accepted` — surfacing any
`escalate` to you rather than looping on it.

## Closing the loop without a human

`enrichment_loop.py` drives the whole cycle in code: a model produces or corrects
a lesson, the checks judge it, the flagged findings go back to the model, and it
tries again — until the checks accept it. The guarantees:

- **The stop condition is our verdict, never the model's.** The loop ends only
  when `combine(...).accepted` is true. The model never declares its own success.
- **It refuses to start if the checks aren't healthy.** A broken checker would
  "accept" anything, so `health_report` runs first and an unhealthy check aborts
  the run (`status: refused`).
- **It stops, not grinds, on escalate** — a human-judgment finding or a broken
  check. Looping there would waste calls.
- **It is capped.** No convergence in `max_rounds` → `status: gave_up`, with the
  last attempt and the round-by-round history returned.

The fixer is injected, so the control logic is tested with no network
(`test_enrichment_loop.py`: refuses-when-broken, converges, gives-up-at-cap,
accepts-clean) and run live with `ollama_fixer()`.

```python
from enrichment_loop import close_loop, ollama_fixer
result = close_loop(lesson, fixer=ollama_fixer(), max_rounds=5)
# result["status"] in {accepted, escalate, refused, gave_up}
```

Acceptance means no *known* defect remains — the checks we run — not that the
lesson is excellent. Passing is a floor, not a certificate.

## Adding an evaluator

Register it in `pipeline_evaluators.py` with an `artifact`, a `kind`, a
`findings_fn(payload) -> [Finding]`, and at least two planted-error self-tests
(one that must flag, one that must not). It joins the server automatically and
inherits the honesty gate. Keep mechanical judgement in code; reserve the model
for open-ended wording, and treat those verdicts as advisory.

## Domain packs — adding a subject that isn't PTE

`domain_packs.py` declares everything that changes when the book changes: the
slug, the audience, the file naming, and **which checks apply**. The engine (the
loop, the contract, the honesty gate, the teaching schema) is subject-agnostic.

The interesting difference between packs is what "correct" is checked *against*:

| Pack | Ground truth | Consequence |
|---|---|---|
| `pte` | the official Pearson Score Guide | correctness is a *reading* question — needs evidence lookup, and a model judge for open wording (measured unreliable on anything mechanical) |
| `math5a` | arithmetic itself | correctness is **computable** — no judge, no evidence lookup, fully deterministic |

Checks declare which domains they belong to, and `evaluate()` filters by the
lesson's pack. This matters: running the PTE checks against a maths lesson would
find nothing and **read as a pass**.

### The maths check

`math_evaluators.arithmetic_findings` verifies every calculation in a lesson is
true. It splits each `=` chain, evaluates every side exactly (`fractions.Fraction`,
so no float rounding), and requires them to agree.

Chains, not pairs — this is the whole trick. Maths working is written as
`78 × 30 = 78 × 3 × 10 = 234 × 10 = 2340`; a pairwise `a op b = c` regex reads
that as "78 × 30 = 78" and screams. Measured against the real textbook, the naive
version had a **55% false-positive rate**. Blanks (`\square`, `____`) are the
pupil's answer and are skipped, never flagged.

Validated both ways: 11 planted cases (including the exact multi-step chains the
naive version got wrong), and a run over the whole parsed Singapore Math 5A book —
181 equation chains, **0 false positives**.

### Source quality is a hard prerequisite for maths

Generic OCR destroys fractions (`½ × 14` becomes loose digits on separate lines)
and turns fill-in blanks into junk tokens. Measured on two OCR'd copies of this
book: ~24% of lines garbled, and at least one wrong answer presented as fact.
LlamaParse (`agentic` tier) preserves fractions as LaTeX and describes diagrams;
that is the supported path. See `output/singapore-math-5a.parsed.md`.
