# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**B21a — the inputs the rest of math5a needs.** This is the first half of
canonical batch B21, split because B21 assumes two things that do not exist:
a manifest-draft generator (B17's text promised "authored from generated
drafts" and no generator was ever built) and clean-chunks files for chapters
other than 3.

Read `docs/classroom-migration-batches.md` (B21) and `CONTEXT.md` first.

Three deliverables, in this order:

**1. Clean-chunks for every chapter.** Chapter 3 has
`output/math5a.chapter03.clean_chunks.json`; chapters 1, 2, 4, 5, 6, 7, 8 and
9 have none. Each chapter's `book_learning_materials.json` already carries its
`source_chunks`, so derive the chunks file the exporter needs from the same
material rather than re-parsing the PDF. Same input, same output, every time.

**2. A manifest-draft generator.** A command that reads a chapter's learning
materials and its exercise bank and writes a DRAFT manifest: the concepts it
can see, each with a proposed statement, a proposed `objective_type`, a
proposed `assessed` flag, and the exercises aligned to it. Chapter 3's
approved manifest at `manifests/math5a.chapter03.export_manifest.json` is the
shape to match.

A draft is NOT approved. Mark every draft explicitly as awaiting approval —
`"approved": false` or an equivalent the exporter checks — and make the
exporter REFUSE to export from an unapproved draft. That refusal is the
point: it keeps a machine's guess about what a chapter teaches from reaching
a learner without a person having read it. Prove the refusal with a test.

Chapter 3's existing manifest is already approved and must keep exporting
unchanged: same package, same content_hash `0cc0598abed2`. Prove that too.

**3. Draft manifests for the eight chapters.** Run the generator and commit
its output under `manifests/drafts/`. Do not mark them approved. Do not
invent teaching content for the three REVIEW chapters (4, 8, 9) — they teach
nothing and carry no exercises of their own; a review's manifest names the
lessons it reviews, per decision 4.

Report honestly what each draft looks like — especially chapters 5 and 7,
whose material is thin (one and two teaching lessons). Do not pad them.

Verification is EVERY suite in this repository, as this playlist's header
requires, plus chapter 3's export reproduced at its existing hash. Report
EXIT CODES. Commit locally.
