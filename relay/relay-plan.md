# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**Rebuild the chapter lesson plans (export manifests) from the enrichment.**
This corrects B21a, whose generator read the exercise bank's `skill` labels and
produced concept statements like "Place value" — throwing away the class
material an external LLM had already written for all nine chapters. Read
`docs/classroom-migration-batches.md` (the contract section, and B21) and
`CONTEXT.md` first.

**The rule the plan now states, and this batch exists to honour:** a lesson
plan is DERIVED from the chapter's enrichment, never invented. A concept's
statement is that chapter's own `learning_goals` line — "You will find the
value of any digit", not "Place value". Nothing in this batch writes teaching
content; it maps what an external generator already wrote.

Rework `draft_export_manifest.py` so a chapter's draft is built from
`output/math5a.chapterNN.enrichment.json`:

- **Concepts come from the enrichment.** Its `learning_goals`, `techniques`
  and `mastery_checklist` describe what the chapter teaches; the exercise
  bank's `skill` values say which questions exist. Match them, and say plainly
  in the draft how each concept was matched.
- **A goal with no matching questions is still a concept.** It is taught and
  not yet practised; do not drop it, and do not invent questions for it.
- **A `skill` with no matching goal is reported, not silently attached.** The
  draft names it as unmatched so a person can see the gap.
- **`objective_type` and `assessed` are the enrichment's evidence, not a
  default.** If the material does not say, leave the field absent and report
  it rather than stamping every concept `procedure, assessed=true` as the
  previous generator did.
- REVIEW chapters (4, 8, 9) carry no concepts and name the chapters they
  review, per decision 4. Take the coverage from the chapter's own material,
  not from a shape you choose.

Then regenerate all eight drafts under `manifests/drafts/`, still unapproved.
Chapter 3's approved manifest must keep exporting **byte-identical at
content_hash `0cc0598abed2`** — prove it.

Report honestly, per chapter: how many concepts, how many matched to
questions, what was left unmatched, and where the material was too thin to say.
Do not pad.

Verification is EVERY suite in this repository. Report EXIT CODES. Commit
locally.
