# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**Fix an inconsistency in the required_form you just added.** Read
`docs/classroom-migration-batches.md` (contract section) and `CONTEXT.md`.

`draft_export_manifest.py` now proposes `required_form` for numeric-marked
concepts. It is inconsistent: two concepts with identical answer data get
different results.

    find-half-a-related-rectangles-area  answers 14, 60  (answer_kind number, answer_den 1)  -> whole_number  ✓
    identify-a-triangles-base-and-height answers 32, 90  (answer_kind number, answer_den 1)  -> ABSENT       ✗

Same data, opposite output. The absent one is exactly the concept that blocks
chapter 5 from importing.

The rule must be about the ANSWERS, not the concept's wording: any numeric
marker whose bank answers are ALL whole numbers (`answer_kind` number,
`answer_den` 1) gets `whole_number`. Answers that reduce to fractions get the
fraction form, as chapter 3 does. Only leave it absent when the answers
genuinely do not agree on a form — and report that, do not guess.

Regenerate the eight drafts. Chapter 3 must still export byte-identical at
`0cc0598abed2`. Extend `test_manifest_drafts.py` so a concept whose answers
are all whole numbers gets `whole_number` — the test that would have caught
this.

Verification is EVERY suite. Report EXIT CODES. Commit locally.
