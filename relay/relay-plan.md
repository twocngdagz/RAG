# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**B21, RAG half — carry class lessons into the package.** Read
`docs/classroom-migration-batches.md` (B21, and the contract section) and
`CONTEXT.md` first.

B20.1 generates class lessons per concept into
`output/<slug>.chapterNN.class_lessons.json`. **The exporter does not read
them yet** — a package is still built from the enrichment alone, so the
techniques and worked examples an external generator wrote are ignored.
Closing that is this batch.

Chapter 5 is the proof: it has real class lessons for all five concepts
(11 techniques, 16 worked examples), generated through the live contract.

Do this:

- **The export reads a chapter's class lessons when they exist** and turns
  each concept's goal, techniques and worked examples into teaching blocks
  for that concept, in the package's existing block vocabulary. A concept's
  blocks belong to that concept, not to the chapter at large.
- **A chapter with no class lessons still exports**, exactly as it does
  today, from the enrichment. Chapter 3 must keep exporting **byte-identical
  at content_hash `0cc0598abed2`** — prove it.
- **Class lessons ADD to a package; they never replace the enrichment's
  material.** The enrichment's overview, method, goals, mistakes and practice
  plan stay.
- **Approval is not yours to grant.** The exporter refuses an unapproved
  manifest and must keep refusing. Do not flip `approved`, do not add a flag
  that bypasses it, and do not weaken the refusal to make a test pass. Where a
  test needs an approved mapping, build a fixture, never edit a real draft.

Verification is EVERY suite in this repository. Report EXIT CODES. Commit
locally.
