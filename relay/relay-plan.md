# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

**Fix: a chapter cannot export because its lesson plan never says what form a
correct answer takes.** Read `docs/classroom-migration-batches.md` (the
contract section and B21) and `CONTEXT.md` first.

Importing chapter 5 into the consumer is refused:

    Activity definition [math5a:ch05:mp-015-triangle_area] does not satisfy
    learning.activity.v1: evaluation.marking.required_form is required and missing

**Why.** The numeric marker needs two things to mark an answer: `expected`
(the answer, which the pipeline computes) and `required_form` (what a correct
answer must look like — a plain number, or a fraction reduced to simplest
form). Chapter 3's approved plan carries `required_form: simplest_fraction`
because a person set it. The draft generator (`draft_export_manifest.py`)
never emits it, so every generated plan is unexportable at the first
deterministic-marked concept.

Do this:

- **The draft generator proposes `required_form` from the exercises
  themselves.** The answers in each concept's bank say what form fits: chapter
  5's triangle-area answers are whole numbers and simple decimals; chapter
  3's are fractions. Derive it from the answer data (`answer_kind`,
  `answer_den`, whether it reduces), do not hard-code per chapter.
- **Where the answers do not make the form unambiguous, say so** — leave it
  absent and report it, exactly as the generator already reports an unmatched
  skill. Do not guess a form onto a concept whose answers do not imply one; a
  wrong `required_form` marks a correct learner wrong.
- Regenerate the eight drafts under `manifests/drafts/`, still unapproved.
- Chapter 3's approved manifest is untouched and must still export
  byte-identical at content_hash `0cc0598abed2` — prove it.

Do not touch the approval gate. Do not weaken the marker's requirement; the
plan must satisfy it, not the marker relax it.

Verification is EVERY suite in this repository. Report EXIT CODES. Commit
locally.
