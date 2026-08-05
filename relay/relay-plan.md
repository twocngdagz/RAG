# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

The RAG half of canonical batch **B18 — Pictures: diagrams computed,
friendly images gated**.

Read `docs/classroom-migration-batches.md` (B18) and `CONTEXT.md` first.

**Scope for this batch: computed diagrams only.** Build the deterministic
drawing — bar models, area models, step-by-step layouts — from the numbers
in a concept's worked examples and exercises, emitted as SVG inside the v2
package's existing asset channel and referenced by illustration blocks with
caption and alt-text, provenance `pedagogical_generation`. The same input
must always draw the same picture, and a test must prove that.

**Explicitly NOT in this batch: friendly generated images.** They need a
hosted image model and an author-approval gate that does not exist yet. Do
not call any image service, do not add an API key, do not stub one. If your
work would need one, stop and say so rather than inventing it.

Enrich chapter 3 with its diagrams and re-export: the enrichment comparison
must print its added/removed counts and must refuse a removal, and the
package hash must change because the assets changed.

Verification is EVERY suite in the repository, exactly as this playlist's
header requires, plus the export reproduced end to end. Report EXIT CODES.
Commit locally when they are all green.
