# RAG relay plan — Phase 2 execution playlist (RAG halves)

Read first, both of you: `docs/classroom-migration-batches.md` (Phase 2
section) and `CONTEXT.md` at the repo root. The thirteen decisions in
CONTEXT.md win any disagreement with anything, including this file. The
standing Hold applies to every batch: no batch closes on tests narrower than
its sentences — when a test and a sentence disagree, the sentence wins and
the test is wrong.

### Batch 1

The RAG half of canonical batch **B17 — The v2 package: export everything**.

Do exactly what the canonical plan's B17 section states for the RAG side:
`learning.package.v2` — the full teaching document as ordered blocks
(method, concept explanations, every worked example with
decode/plan/annotations, common mistakes), concepts as first-class entries
each simultaneously the objective, each concept's exercise bank, an asset
channel (SVG inline, raster as base64), the whole file fingerprinted; the
enrichment comparison that prints "N added, 0 removed" and refuses to export
a removal as enrichment. Prove it on chapter 3: emit
`output/math5a.chapter03.package.json` in v2 form and report its
`content_hash` in your summary — the operator carries it to the Ela run.

Acceptance and named tests are in the canonical B17 section.

Verification means EVERY suite in the repository, not the ones this batch
happened to touch:

    for t in test_export_v2 test_package_schema test_export_mapping \
             test_export_cli test_representative_package test_provenance_continuity; do
      .venv/bin/python $t.py; echo "$t exit $?"
    done

A batch is not done until every one exits 0. Report the EXIT CODES, not
output lines. Do not narrow the list to the suites you edited — a batch is
judged by what it broke as well as by what it built.

Commit locally when they are all green.
