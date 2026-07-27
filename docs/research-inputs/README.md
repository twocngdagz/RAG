# Research inputs — NONCANONICAL

**Nothing in this directory is authoritative. Nothing here adopts anything.**

These are dated observations and syntheses produced on 2026-07-26 to inform a decision. They are inputs to that decision, not the decision. Authority rests only with the documents listed in the authority table of `../research-rule-classification.md` — which includes the requirements and architecture guidelines, not only ADRs and plans.

Two different kinds of mismatch, handled differently:

- **Against an accepted decision.** The accepted decision takes precedence. These documents cannot override it.
- **Against the current code.** Neither one wins by default. Code is implementation, not authority — it can be wrong about what was decided, and several shipped values here were never decided at all. Where an observation no longer matches the code, treat it as a **historical record of the capture date**, not as an error, and check the classification document for what is actually adopted.

## Capture provenance

| | |
|---|---|
Captured | 2026-07-26 (source mtimes 14:05) |
RAG SHA | `296d6b5` — *Find the send button by locator so a re-render cannot break the send* |
Ela SHA | `da188c5` — *Target items by id, ask for inline JSON, and catch reused sentence shapes* |

Both repositories have moved since. Ela in particular has merged PR #4 (`f196777`), which changed the verification gate these documents describe.

## Contents

| File | What it is |
|---|---|
`recon_ela_map.md` | Observation of the Ela repository at `da188c5` |
`recon_rag_map.md` | Observation of the RAG repository at `296d6b5` |
`recon_book_method.md` | Inventory of study techniques from *A Mind for Numbers* |
`01_pedagogy_guidelines.md` | Proposed pedagogy layer — invariants, scheduling model, per-audience adaptation |
`02_ux_spec.md` | Proposed per-audience interface and session design |
`03_implementation_plan.md` | Proposed sequenced changes against real files |
`04_research_citations.md` | Primary references behind the ⟦cite⟧ claims in `01` |

## How these were used

`docs/research-rule-classification.md` classifies every pedagogical rule and numeric threshold in these documents, and records separately whether each has actually been adopted and by what authority. **Read that document before acting on anything here.**

Known corrections already recorded there:

- `01` Invariant 5's "every response gets feedback" is not established by any authority; the adopted rule is the narrower "no AI-required user-critical flow".
- `03` compresses the CI description inaccurately — the recon maps state it correctly.
- Several rules are real and working in code but were never written down as decisions, and are marked *implemented, not adopted*.

Known drift since capture, historical rather than wrong:

- `recon_ela_map` §9 describes a verification gate that could not fail. Ela PR #4 (`f196777`) repaired it. The observation was accurate on 2026-07-26.

## Editing

Don't. These are a dated snapshot. If the world changes, record that in the classification document or in an ADR — not by editing history.
