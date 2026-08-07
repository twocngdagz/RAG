# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**Fix the technique block's field name so a class lesson can be imported.**

B21's RAG half turns a class-lesson technique into a `concept_explanation`
teaching block. The consumer refuses every one of them:

    teaching block `class_lesson.math5a:ch05:identify-a-triangles-base-and-height.techniques.0`
    needs `how_to` in its content, and a concept_explanation block without it
    renders as a heading with nothing under it

The cause: a class lesson's technique carries its method under **`steps`** — a
list of `{step, detail}` pairs, which is what the class-lesson contract asks
the generator for. A `concept_explanation` block requires **`how_to`**. Nobody
translates between them, so the method arrives empty and the block is refused.

**The producer conforms to the consumer** — the same ruling that settled the
asset field earlier. When a technique becomes a block, its steps must reach
the block as `how_to`, keeping each step's name and its detail readable; a
step named "Write" whose detail is "Write Area = ½ × base × height" must not
lose either half.

Prove it end to end: export chapter 5 from its real material — the fixtures
under `tests/fixtures/b21/` are the tracked copies — and assert the technique
blocks carry `how_to` with the steps intact.

Do not weaken any refusal to make this pass, do not touch the approval gate,
and chapter 3 must still export byte-identical at `0cc0598abed2`.

Verification is EVERY suite in this repository. Report EXIT CODES. Commit
locally.
