# Research-rule classification — batch B0.2

**Audit date:** 2026-07-27
**Rulings applied:** F1–F6 and the A5/A9/A11 corrections, approved 2026-07-27.

## How to read this document

Two things are tracked separately and must not be conflated.

**Classification** is the ADR §5 taxonomy — `invariant`, `initial_policy`, `domain_policy`, `experiment`, `optional_technique`. It says what *kind* of rule this is and how strongly it should bind.

**Canonical status** says whether the rule has been adopted, and by what authority. **Classifying a rule does not adopt it.** A rule can be classified `invariant` and still be unadopted.

> ADR-0002 v3 is headed *"Status: Proposed for architecture review."* Nothing existing only in that ADR is adopted, including its §5.1 invariant list — that list is a proposal about what should become invariant.

### Authorities

Only these may confer "adopted". Every adopted row below cites one of them by file and line.

| Authority | Location (Ela) |
|---|---|
| Architecture guidelines | `documentation/architecture guidelines.md` |
| Requirements | `documentation/requirements.md` |
| Priming spec | `documentation/priming screen.md` |
| ADR-0001 | `docs/adr/0001-focus-sessions-and-mastery-targets.md` |

`CONTEXT.md` is deliberately **not** an authority. It is a bounded-context glossary — `docs/knowledge/README.md` describes it as a glossary and `docs/work/README.md` as vocabulary. It defines terms, not rules.

**Implemented ≠ adopted.** Many values run in production having never been decided in a document. `requirements.md` §15 still lists the review-scheduling formula, mastery thresholds, and whether AI scores may influence weak-item calculations as **OPEN**, while the code has chosen answers for all three. Those are Table C.

---

## Provenance

| Item | Value |
|---|---|
Recon audit date | 2026-07-26 (source doc mtimes 14:05) |
RAG SHA at recon | `296d6b5` — *Find the send button by locator so a re-render cannot break the send* (2026-07-26 08:33) |
Ela SHA at recon | `da188c5` — *Target items by id, ask for inline JSON, and catch reused sentence shapes* (2026-07-25 23:49) |
Classification date | 2026-07-27 |
Ela SHA at classification | `f196777` — merge of PR #4 (B0/B0.1) |
RAG SHA at classification | `296d6b5` (unchanged) |

Research documents classified, all dated 2026-07-26:
`01_pedagogy_guidelines.md` · `02_ux_spec.md` · `03_implementation_plan.md` · `04_research_citations.md` · `recon_ela_map.md` · `recon_rag_map.md` · `recon_book_method.md`

These are **noncanonical research inputs** — dated observations and syntheses, not decisions. See `research-inputs/README.md`.

---

## Table A — Pedagogical rules

Source: `01_pedagogy_guidelines.md` unless noted.

| # | Rule | Source | Classification | Canonical status | Rationale |
|---|---|---|---|---|---|
A1 | Retrieval is the unit of learning; every material type must have a productive mode where the learner generates before seeing the answer | Inv. 1 | `invariant` | **Proposed** (ADR §5.1) | Testing effect is among the most replicated results in the field (`04` Inv. 1) |
A2 | Recognition-only interactions are a scaffold for new items only and must graduate to production | Inv. 1 | `initial_policy` | **Not adopted** | Direction follows from A1; the graduation trigger is unset |
A3 | Intervals expand without bound on success and contract on failure — **for memory-recall scheduling only** | Inv. 2 | `invariant` (scoped) | **Proposed. Not adopted until ADR-0003** (ruling F1) | Scoped deliberately: essays and performance tasks are not memory cards. The current seven-day cap is a **known temporary limitation, not a policy violation.** B4.5 remains skipped |
A4 | Optimal gap scales with target retention interval (~10–30%, declining as horizon lengthens) | Inv. 2, `04` Cepeda 2008 | `experiment` | **Not adopted** | Published effect; unmeasured for this population |
A5a | A session mixes skills rather than drilling one to exhaustion | Inv. 3 | `invariant` | **Proposed** (ruling F3) | The mixing rule itself |
A5b | Confusable skills are deliberately placed near each other | Inv. 3 | `experiment` | **Not adopted** (ruling F3) | Untested here. The app will not deliberately place confusing items together until measured |
A5c | Topic coherence in new-item ranking | `ComposeStudySession::baseNewItemScore` | `domain_policy` (English) | **Implemented, not adopted** | Runs today. Pulls against A5b, which is why A5b stays an experiment |
A6 | Stop surfacing an item for same-session repetition once answered correctly | Inv. 3 | `initial_policy` | **Implemented, not adopted** | Cooldown exists in `ComposeStudySession::latestCompletedSessionContext`; no canonical document states it |
A6a | Exempt a rubric-DECLINED item from that cooldown | Inv. 3 | `initial_policy` | **DECIDED (B13.1): REMOVED.** Never recorded by the classification sweep — A6 captured the correctness exemption only, so this leg was implemented, undecided and unlisted, which is the state C6 exists to prevent. It let advisory model output decide WHEN an item returned, which B13.1's ruling forbids; the incorrect-answer leg stays on deterministic grounds. ADR-0003 may revisit it | Reasoning in `classroom-migration-batches.md` § B13.1 |
A7 | Instruction leads with a complete worked model, then fades support as learner state improves | Inv. 4 | `invariant` | **Not adopted** | Expertise reversal is well evidenced (`04` Kalyuga 2003). Ela renders up to 8 static steps regardless of state |
A8 | New elements per sitting are capped, lower for younger learners | Inv. 4 | `initial_policy` | **Not adopted** | Caps exist but not as a cognitive-load rule; no age banding exists |
A9a | Every response gets feedback | Inv. 5 | `initial_policy` | **Not adopted** — no authority states it | Corrected: the architecture guideline does not establish this |
A9b | No AI-required user-critical flow — AI failure must not block critical behaviour | Inv. 5 | `invariant` | **Adopted** — `architecture guidelines.md:518` §7 | Every AI path except enrichment and priming rewrite has a deterministic fallback |
A10 | Deterministic checks own correctness and scheduling wherever correctness is determinable; a model may elaborate or evaluate subjective traits but may never change learner state or scheduling | Inv. 5 | `invariant` | **Adopted, engine-wide within existing scope** (ruling F2) — `architecture guidelines.md:247`; `requirements.md:524` | Code decides exact answers such as maths. Models may score subjective essay traits, but cannot move learner state or review timing |
A11 | The honesty gate: a check may certify PASS only if, on this run, it just caught its own planted error | Inv. 5, `recon_rag_map` §5 | `invariant` | **Implemented (RAG), not adopted** | Real and working — see the sensitivity-test record — but no canonical document establishes it |
A12 | Capture predicted confidence before revealing truth; surface the felt-vs-actual gap | Inv. 6 | `experiment` | **Not adopted** | Neither repo captures pre-answer confidence; interaction cost unmeasured |
A13 | Progress must show demonstrated retention, never items viewed or time spent | Inv. 6 | `invariant` | **Proposed** | Opposes what `BuildLearnerProgressSnapshot` shows today |
A14 | Mastery is earned through evidence and never self-declared | Inv. 6 | `invariant` | **Adopted** — `architecture guidelines.md:247`; `requirements.md:409`, `:484` | *"review timing and mastery state must remain deterministic app-side behavior"*; *"skipping must not advance the item to a higher mastery state"* |
A15 | Bounded focus sessions with a clear stop | Inv. 7 | `initial_policy` | **Adopted (session concept only)** — `docs/adr/0001-focus-sessions-and-mastery-targets.md:3` | Streaks, cues and rewards are not built and not adopted |
A16 | Sleep consolidates memory; pre-sleep and next-day review nudges | Inv. 7, `04` Diekelmann & Born | `optional_technique` | **Not adopted** | Mechanism well evidenced; the product feature is unbuilt |
A17 | The scheduler must accept graded, not boolean, outcomes | Part 2 Rule A | `invariant` | **Not adopted** — deferred to ADR-0003 | Structural: half the material types produce partial credit a boolean scheduler cannot consume |
A18 | Every item must point back to a learning objective | Part 2 Rule B | `invariant` | **Proposed** (ADR §9) | Mastery cannot aggregate above a single item without this |
A19 | Mastery is retention-gated and **revocable** | Part 3.4 | `invariant` (revocability) + `initial_policy` (thresholds) | **Revocability ADOPTED** — `requirements.md:411`: *"A mastered item may later become weak again if performance drops."* Thresholds not adopted | **Ela's `mastered` is absorbing and never demotes. That is a live defect against an adopted rule, not a contradiction with a proposal.** |
A20 | Phrase/chunk first, word second, sentence pattern third | Part 4.2 | `domain_policy` (English) | **Adopted for English** — `requirements.md:60` *"Primary learning unit: phrase/chunk"* (also `:288`) (ruling F4) | **RECLASSIFIED (B15): English domain policy, not a universal rule.** Maths and PTE do not inherit it, and now demonstrably cannot: `CompositionItemTypes::all()` gives the ordering to the three English types only, each domain orders within itself, and `CompositionItemTypesTest` pins the sequence so a fourth domain inheriting it would fail rather than pass quietly. B15's track presets make the separation structural — English, maths and PTE carry their own defaults, and no preset can reach another domain's ordering |
A21 | Production in a sentence is required to graduate a vocabulary item | Part 4.2 | `initial_policy` | **Not adopted** | Graduation criterion unset |
A22 | Deterministic-first feedback, always, for children | Part 4.4 | `domain_policy` (children) | **Blocked** — children are an explicit non-goal in three Ela docs; ADR §42 requires a separate privacy ADR | Cannot be adopted without that ADR |
A23 | Learning styles are excluded by design | `04` honesty note 2 | `invariant` | **Proposed** | Modality matching has repeatedly failed to replicate (Pashler et al. 2008) |
A24 | Memory palace, handwriting-over-typing, equation poems, mental contrasting | Inv. 7 omission | `optional_technique` | **Not adopted** | The book is candid the handwriting evidence is thin |
A25 | Pomodoro / time-boxing | `04` Inv. 7 | `optional_technique` | **Not adopted** | `04` states there is no large Pomodoro trial base |
A26 | STAR answer structure | `04` §4.3 | `optional_technique` | **Not adopted** | `04` is explicit: an industry formatting convention, not a validated intervention |

---

## Table B — ADR-0002 v3 numeric thresholds

| # | Threshold | ADR location | Classification | Canonical status |
|---|---|---|---|---|
B1 | `maximum_independent_successes: 1` — fade scaffolding after one independent success | §14 | `initial_policy` | **Not adopted.** ADR §14 itself says fading thresholds are policy or experiment |
B2 | Remediation after **2** incorrect attempts | §5.2, Batch 10 | `initial_policy` | **Not adopted.** Named as an `initial_policy` example by ADR §5.2 |
B3 | `minimum_characters: 20` | §11 example | *illustrative* | Not a decision |
B4 | `difficulty: 2` | §11 example | *illustrative* | Not a decision |
B5 | `success_condition: "criterion:reasoning >= 2"` | §24.1 example | *illustrative* | Not a decision |
B6 | `type_version: 1`, `version: 1`, `content_revision: 1` | §11, §18, §34 | *version initialisers* | n/a |
B7 | Enumerations — scaffolding levels (5), evidence modes (7), answer visibility (5), assistance effects (6), evidence classifications (5), authority modes (5), scheduling policies (8) | §12–§25 | `initial_policy` | **Not adopted.** Each list is explicitly "initial" |

**Finding.** The ADR contains only **two** genuine numeric thresholds — B1 and B2 — and self-classifies both as `initial_policy`. Everything else is illustrative or a version initialiser. §5 did its job: the ADR largely avoided baking in constants.

The real threshold surface is the shipped code.

---

## Table C — Shipped values that were never decided

Source: `recon_ela_map` §3, verified against Ela `f196777`.

| # | Value | Location | Classification | Canonical status |
|---|---|---|---|---|
C1 | Interval ladder `12h / 1d / {1d, 3d, 7d}`, capped at 7 days | `UpdateLearnerItemStatesAfterSession` | `initial_policy` | **Implemented; OPEN** in requirements §15. Known temporary limitation under ruling F1 |
C2 | `MINIMUM_SAFE_MASTERY_REVIEWS = 3` | same | `initial_policy` | **Implemented; OPEN** in requirements §15 |
C3 | `mastered` is absorbing, never demoted | `lifecycleState()` | *defect* | **Violates A19, which is adopted** (`requirements.md:411`) |
C4 | Weak deltas: correct −1, partial +1, incorrect +2, clamp 0–10 | same | `initial_policy` | **Implemented, undocumented** |
C5 | Weak threshold `>= 1` (scheduler) vs `>= 2` (dashboard) | `LearnerItemState::weak()` / `BuildLearnerProgressSnapshot` | *defect* | **Defect** (ruling F5). "Weak" must mean one thing. If two bars are wanted later they need different learner-facing names |
C6 | Rubric trend ±5, recovery gate `s0 >= 70`, 3 most recent scores | `ComposeStudySession::weakItemPriorityProfiles` | `initial_policy` | **DECIDED (B13.1).** Advisory feedback may order otherwise-equivalent weak items, because the influence is bounded to reordering within a deterministically selected set and is disclosed on the card it moved. It may not touch a mark, `weak_score`, `due_at` or mastery, and may never decide when an item returns. Absence of the signal degrades to the stable order. Reasoning in `classroom-migration-batches.md` § B13.1 |
C7 | `DECLINE_SHORT_LEASH_HOURS = 12`, `RECOVERY_DUE_DAY_BONUS = 1` | `UpdateLearnerItemStatesAfterSession` | `initial_policy` | **DECIDED (B14): REMOVED.** Both were the rubric priority status reaching `dueAt` — the leash replaced the interval ladder on a declining trend, the bonus lengthened it on recovery. ADR-0003 § 7 forbids advisory influence over when an item is due or how long an interval becomes. The deterministic content survives in the outcome layer: a wrong answer keeps its own twelve-hour leash, a correct one its own ladder |
C7a | Rubric priority status adjusts `weak_score` by ±1 | same | `initial_policy` | **DECIDED (B14): REMOVED.** Never recorded by the sweep. `weak_score` selects an item into a session and is what the dashboard counts, so this was advisory influence over *whether* an item is selected — § 7's first named axis. An incorrect answer inside the watch set received +3, the outcome's +2 plus this +1, a weight nobody designed |
C7b | The `recovered` branch of C7 and C7a | same | *eligibility trap* | **DECIDED (B14): REMOVED, and this is the one that looks clean.** Its TRIGGER is deterministic — a correct answer — but its ELIGIBILITY is not: the status exists only for items in the rubric watch set, which is built over items a model has scored. Two learners answering the same item correctly were scheduled differently because a model happened to be watching one of them. A deterministic trigger does not launder advisory membership, and a reader checking only the trigger will call this clean again |
C8 | Duration ∈ {10, 15, 20}; items ∈ {6, 8, 10}; `minimumNewItems` 2–3; `maximumWeakItems` 2–3 | `GenerateStudySessionRequest`, `ComposeStudySession` | `initial_policy` | **Implemented, undocumented** |
C9 | New-item weights: phrase +30 / word +18 / pattern +10; topic +45/+28; utility ÷2; teachability ÷5 | `ComposeStudySession::baseNewItemScore` | `domain_policy` (English) | **Implemented, undocumented.** See A5c |
C10 | `itemTypeRank` default `=> 3` | `ComposeStudySession` | *defect* | **Implemented.** Silently ranks any new domain last. ADR Batch 9 removes it |
C11 | Rubric weights `{definition 35, usage 35, example 20, grammar 10}` | `StudySessionResponseRubricAgent` | `domain_policy` (English) | **Implemented, undocumented** |
C12 | Queue-quality thresholds: ≥4 topics; ≥3 with modal < ⌈total/2⌉; word-heavy ≥4 and ≥75%; new > (due+weak)×2; family group ≥3 | `BuildStudySessionPrimingPayload` | `initial_policy` | **Implemented, undocumented** |

### RAG values (ruling F6)

**Ela owns live learner scheduling. RAG's scheduler is standalone/legacy and does not schedule Ela learners.** RAG produces content; Ela decides when learners see it again.

| # | Value | Location | Classification | Canonical status |
|---|---|---|---|---|
C13 | Leitner `[1min, 10min, 1d, 3d, 7d, 16d]`, mastery review 60d | `spaced_repetition.py` | *standalone/legacy* | **Out of scope for Ela learner scheduling** (ruling F6) |
C14 | `min_worked_examples`: pte 3, math5a 4; `reading_grade_max`: math5a 6.0 | `domain_packs.py` | `domain_policy` | **Implemented, not adopted.** RAG content-quality policy; no authority states it |
C15 | `max_words_per_sentence = 14.0`, `GRADE_TOLERANCE = 0.5` | `readability_evaluators.py` | `domain_policy` | **Implemented, not adopted.** RAG content-quality policy. Module constants, not pack fields, so they cannot vary by domain |
C16 | `SOLVER_RUNS = 3`, `SOLVER_AGREEMENT = 3` | `reading_mcq_items.py` | `initial_policy` | **Implemented, not adopted.** RAG content-quality policy; no authority states it |

---

## Consequences of the rulings

Three items change status materially:

1. **C3 is now a defect against an adopted rule.** `requirements.md:411` states a mastered item may become weak again. Ela never demotes. Previously read as "contradicts a proposal"; it contradicts adopted requirements.
2. **The seven-day cap (C1) is not a violation.** Under F1, unbounded expansion is proposed for memory-recall scheduling and unadopted until ADR-0003. It is a known temporary limitation. B4.5 stays skipped.
3. **A5b will not be built before it is tested.** Deliberately placing confusable items together is an experiment; the shipped topic-coherence ranker (A5c) remains the implemented English policy.

---

## Sensitivity-test record

**Run:** 2026-07-27T01:58:39Z–01:58:49Z · exit 0 · **all 12 checks passed** · satisfies the B0.2 requirement.

| | |
|---|---|
Command | `.venv/bin/python test_audit_sensitivity.py` |
Provider | Ollama Cloud, `https://ollama.com/api/chat` |
Model | `gpt-oss:120b` |
Auth | existing `OLLAMA_API_KEY` from `.env`, unchanged |
Model calls | 2 (one per `task_type`) |
Guide | `~/Downloads/PTE-Academic-Test-Taker-Score-Guide.pdf`, present |
Retries | none |

Both planted `CONTRADICTED` claims were caught, both `SUPPORTED` claims confirmed, and all eight deterministic word-range and trait-vocabulary cases passed.

**Scope of the result.** It establishes that the audit can still detect planted errors on this date — what the test was written for: *"A run where everything comes back clean is only meaningful if this test passes on the same day."*

It is not a re-run of the historical 3-of-4 judge-flakiness measurement, and does not need to be. A10 is adopted on the strength of `architecture guidelines.md:247` and `requirements.md:524`, not on the strength of any single run.
