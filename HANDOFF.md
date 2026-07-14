# HANDOFF — RAG Prototype (context for continuing in Claude Code)

This file is a handoff from a Cowork session that audited this project and made a
first code change. Read it, then continue the work here in Claude Code — which,
unlike that session, can actually run the code, tests, git, and Ollama on this
machine. Ask me to "apply the patch and run the tests" as a good first step.

---

## What this project is

A retrieval-augmented pipeline that turns a book PDF into structured, **grounded**
learning material (lessons, key terms, worked examples, practice, checklists) and
then deterministically audits that every generated claim is supported by the source
text. Entry point: `generate_book_learning_materials.py`, which orchestrates ~11
sibling scripts (PDF → chunks → outline → sections → clean index → generate) and
then runs an extract → semantic-audit → contract-validate → evaluate chain.

It began as a "tiny prototype" (the README title) but is now ~26k lines / 43
top-level scripts. The current focus is the whole-book `book_learning_materials`
v1/v2 path.

## Product vision (decided this session)

- The pipeline should handle **any book** — Year-5 math, PTE, IELTS, language
  courses — and generate learning content generically.
- Generation is run **once or twice per book**, then results are stored in a
  **database and reused**; later, learning sections get **enriched**. So this is an
  offline batch job, not live traffic — which means quality matters far more than
  throughput/cost, and the grounding-audit design is the right shape.

## Model backend decision

The NVIDIA-hosted Mistral model was the weak link, and we don't want metered API
spend. Decision: use the **Claude Code CLI as the model backend** (runs under the
existing subscription, no per-token cost) while developing, with a local Ollama
model as the free overflow option if subscription limits are hit. A stronger model
is worth it because the cost is amortized across every future use of each book.

---

## Code change already made (needs applying + testing here)

Two files were produced but NOT yet applied to the repo:

- `generate_book_learning_materials.backend.patch` — apply with `git apply`.
- `tests/test_backend_and_token_cap.py` — new regression test (already placed).

What the patch does (additive; default behavior unchanged):
1. **Fixes the truncation bug (audit finding H-1).** The v2 chapter generator was
   hard-capped at `max_tokens=1500`, far too small for a conforming chapter, so
   output truncated mid-JSON and no retry could fix it. Now configurable via
   `--model-max-tokens` (default **8000**), and a response cut off at the token
   limit (`finish_reason == "length"`) raises a *retryable* error.
2. **Adds a pluggable model backend.** New `--backend {nvidia,claude-cli}` (default
   `nvidia`, so existing runs are identical). `claude-cli` shells out to `claude -p`
   under the subscription. New `--claude-model` (default `sonnet`).

The changes are isolated to the model-call plumbing (a `resolve_complete_fn`
factory + a `complete_via_claude_cli` function). Everything else is untouched.

**First actions in Claude Code:**
```bash
git checkout -b claude-backend
git apply generate_book_learning_materials.backend.patch
python -m pytest tests/test_backend_and_token_cap.py -q
python -m pytest -q          # confirm no regressions elsewhere
```

> Note: the tests above were written and statically verified in the Cowork session
> but never executed (that environment had no deps). Running them here is the real
> confirmation.

### Using the Claude backend (subscription, no API cost)
- Run `claude login` once. Make sure `ANTHROPIC_API_KEY` is **not** exported (if it
  is, Claude Code bills the API instead of using the subscription).
- Do **not** use `--bare` mode anywhere — it ignores subscription auth.

---

## Immediate next milestone: prove "any book" works

The thing most likely to break on a new (non-PTE) book is **structure detection**,
not the model. Test it cheaply first:

```bash
cp "/path/to/some non-PTE book.pdf" "input/pdfs/newbook.pdf"
# builds structure + clean index, calls NO model:
python generate_book_learning_materials.py "input/pdfs/newbook.pdf" --prepare-only
# then inspect what it detected:
cat extracted/newbook.body_outline.txt
cat extracted/newbook.section_outline.txt
cat extracted/newbook.structure_resolution.txt
```

If chapters/sections look wrong, that's the heuristic breakage to fix before the
model stage matters. (No OCR yet, so scanned/image-only books extract poorly.)
Then generate one chapter with `--backend claude-cli --max-chapters 1` to sanity
check quality, then the full book.

---

## Open items from the audit (not yet fixed)

Priority order. Full detail is in the audit report from the Cowork session
(`RAG_Prototype_Audit.md`, delivered separately — ask to regenerate if not present).

**Correctness — grounding holes (do before trusting the "grounded" label):**
- **H-2**: `audit_book_claim_support.py` marks a claim `SUPPORTED` even when the
  judge cites zero evidence — no check that SUPPORTED requires non-empty evidence.
- **H-3**: `book_learning_materials_contract.py` returns `PASS` when
  `learning_materials` is the wrong type (e.g. a string) — content validation is
  skipped entirely. Needs explicit type errors for top-level fields.
- **M-8**: non-high-risk `source_grounded` claims are accepted on a citation alone,
  with no check that the text actually matches the source.
- **H-4 / M-5 / M-6**: validation failures aren't retried; failed chapters both
  skip regeneration on `--resume-missing-chapters` and pass the final audit
  silently as empty content.

**Architecture / cruft (schedule after correctness, behind the test net):**
- ~10 dead/superseded scripts safe to archive (the old `retrieve_*` demos,
  `build_pdf_section_topic_outline.py`, `generate_lesson.py`, etc.).
- No package structure; helpers copy-pasted 7–15× → introduce a `common/` lib.
- Pipeline wired by subprocess string-paths → convert stages to importable
  functions.
- README is a 1,475-line "Step 1…34C.3" build log → split into a short README +
  a history doc.

**Future build (after a 2nd book validates the output shape):**
- Persistence layer: store generated learning items in a DB with stable IDs so
  re-generation/enrichment can update without clobbering.
- Enrichment = an update/merge operation (different from the current
  generate-once-write-file model); enriched pieces must re-pass the grounding audit.
