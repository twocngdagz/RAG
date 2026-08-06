# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

Canonical batch **B20.1 — Class lessons: the transform stage**. RAG only.
Read `docs/classroom-migration-batches.md` (B20.1) and `CONTEXT.md` first.
B20.1's section is the specification; this brief does not restate it.

**You are building a CONTRACT and a RUNNER. You are not writing lessons.**
Any lesson content you write yourself is a defect, however good it reads. The
generator is external — ChatGPT through Playwright, exactly as
`enrich_lessons.py` already drives enrichment. Read that file first; this is
its sibling, not its replacement.

What the batch delivers:

1. **The contract.** A document, in the repository, that an outside generator
   could be handed with no other instructions: what a class lesson must
   contain for one concept, the structure it returns in, the format, the
   length, and the context it is given. Chapter 3's existing lesson material
   is the shape to describe — goal, technique with its steps and its common
   error, worked examples with decoding/plan/model answer/annotations — but
   describe the contract, do not copy that chapter's content into it.

2. **The runner.** Per concept, never per chapter. Every run sends the
   concept's CURRENT class lesson as context so the generator expands rather
   than repeats, and nothing already there is deleted. Unlimited re-runs. A
   chapter of nine concepts that fails at the fifth resumes at the fifth and
   never re-runs the four completed.

3. **Illustrations are out of scope here** and must not appear in the prompt.
   They attach afterwards through the asset contract that already exists (an
   asset names the concept it `illustrates`). Do not generate, stub, or call
   any image service.

Do not run the automation against ChatGPT in this batch — Roy runs it. Build
it so it can be run, and prove the pieces with tests that need no network.

The named tests are in the canonical B20.1 section:
`test_class_lesson_contract.py`, `test_class_lesson_runner.py`,
`test_class_lesson_resume.py`.

Verification is EVERY suite in this repository, as this playlist's header
requires. Report EXIT CODES. Commit locally.
