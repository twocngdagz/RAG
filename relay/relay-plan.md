# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**Fix: exported teaching blocks are not tagged with the concept they teach, so
the consumer's lesson skips teaching and jumps straight to recall.** Read
`docs/classroom-migration-batches.md` (contract section, B21) and `CONTEXT.md`.

Reproduced end to end: import chapter 5, open a concept in the lesson, and it
goes directly to the question. The consumer selects a concept's teaching by a
`teaches` field on each teaching block (`block.teaches == concept stable_key`).
The exporter never sets it — it puts the concept in the block's KEY
(`class_lesson.<concept>.techniques.0`) instead — so every block has an empty
`teaches`, every concept resolves zero teaching steps, and a concept with no
teaching is asked without being taught. Verified: 0 of 36 chapter-5 blocks
have `teaches` set.

Do this:

- **Every teaching block that belongs to a concept carries `teaches:
  <concept stable_key>` in the package.** A class-lesson block (goal,
  technique, worked example generated for one concept) is tagged with that
  concept. An illustration already names what it illustrates; tag it to the
  concept it teaches too.
- **Chapter-level blocks that belong to no single concept** (the chapter
  method, overview, whole-chapter practice plan) carry no `teaches`, and that
  is correct — they are not a concept's teaching.
- The tag is derived from where the block already comes from (the class-lesson
  concept it was generated under), never guessed.

Prove it: after export, each concept declared in the manifest has at least one
block whose `teaches` equals its stable_key, for a chapter that has class
lessons. Chapter 3 must still export byte-identical at `0cc0598abed2` — its
blocks are enrichment-level and may legitimately have no per-concept teaching
yet; do not fabricate tags it has no basis for.

Do not weaken the consumer's contract; the producer supplies the field the
consumer reads.

Verification is EVERY suite in this repository. Report EXIT CODES. Commit
locally.
