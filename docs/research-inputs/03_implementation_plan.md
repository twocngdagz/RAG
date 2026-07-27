> **NONCANONICAL RESEARCH INPUT.** This document is a dated observation or synthesis,
> not a decision. It does not adopt anything. Only explicitly accepted ADR and plan
> decisions are authoritative — see `docs/research-inputs/README.md` and
> `docs/research-rule-classification.md`.
>
> Captured 2026-07-26 · RAG `296d6b5` · Ela `da188c5`

# Implementation Plan

### Sequenced changes to make the pedagogy real, against the actual code

**Purpose.** `01` says what must be true; `02` says what the learner sees; this document says *what to change, in which file, in what order*. Every item names real files from the recon maps, states the change, its dependency, a rough size, and how it's verified. It is ordered by **leverage ÷ risk** and by dependency — do the enabling schema/scheduler work before the surfaces that depend on it.

**Two guardrails carried from the recon, honoured throughout:**
- *App owns state; AI assists.* Every change keeps the right/wrong decision and the schedule in deterministic app code. Both repos already state this; nothing here weakens it.
- *Ela verification commands are real and must pass:* `composer check` (baseline) and `composer browser-check`. But note the recon found `composer check` is partly decorative (no `phpstan.neon`, write-mode formatters, CI runs Pest only) — **Phase 0 fixes the safety net first**, because a scheduler rewrite must not land on a hollow gate.

**Estimates** are relative T-shirt sizes (S ≈ hours, M ≈ 1–3 days, L ≈ a week+, XL ≈ multi-week), not commitments.

---

## Phase 0 — Make the safety net real (do this first, it's cheap)

You are about to rewrite the most sensitive code in the product (scheduling). The recon shows the guardrails that *look* strict are substantially non-functional. Fix that before touching the scheduler.

| # | Change | Files | Size |
|---|---|---|---|
| 0.1 | Add a real `phpstan.neon` (Larastan, a committed level) so step 1 of `composer check` actually analyses | new `phpstan.neon` (Ela root) | S |
| 0.2 | Switch `pint`/`lint`/`format` in `composer check` to **check mode**; make CI run the full `composer check` (not Pest-only), add `npx playwright install` to the browser job | `composer.json`, `.github/workflows/tests.yml`, `lint.yml` | S |
| 0.3 | Characterisation tests capturing *current* scheduler behaviour before changing it (so the rewrite is a deliberate diff, not a silent one) | new `tests/Unit` around `UpdateLearnerItemStatesAfterSession` | M |
| 0.4 | Stop re-parsing the 28 MB seed JSON 7× per `composer check` | `tests/Feature/MergedLearningItemsDatasetTest.php` | S |
| 0.5 | Free cheap wins while in here: dead `TaskTrackerRepository` singleton binding, undeclared `--font-serif`, Laravel/Fortify branding leaks | `app/Providers/AppServiceProvider.php`, `resources/css/app.css`, logo/sidebar | S |

**Verify:** `composer check` now fails on a deliberately introduced type error, a formatting violation, and a broken test. That proves the net catches things before Phase 1 leans on it.

---

## Phase 1 — The scheduler and item-state model (highest leverage, both repos)

This is the single most important change in either codebase (`01` Invariant 2). It is a small, well-isolated diff in Ela and a focused rewrite in RAG.

### 1A — Ela: stability-based scheduler + graded outcomes

| # | Change | Files | Size |
|---|---|---|---|
| 1A.1 | Migration: add `stability`, `difficulty`, `lapses`, `objective_id` (nullable FK) to `learner_item_states`; keep existing columns | new migration; `LearnerItemState` model | M |
| 1A.2 | Replace the `12h/1d/{1d,3d,7d}` `match` with an FSRS-style (or SM-2-with-fuzz) update: intervals expand unbounded, failure → `relearning` with reduced stability, interval fuzz | `app/Actions/StudySessions/UpdateLearnerItemStatesAfterSession.php` | M |
| 1A.3 | Change the scheduler input from boolean-ish outcome to a **4-point grade** (`again/hard/good/easy`); add the native-outcome→grade mapping (`01` §3.3) with deterministic signals overriding downward | same file + a small `GradeFromOutcome` mapper | M |
| 1A.4 | Make `mastered` **non-absorbing**: a lapse demotes to `relearning`; mastery becomes objective-level + retention-gated (`01` §3.4) | `UpdateLearnerItemStatesAfterSession`, `LearnerItemState::lifecycleState`, mastery predicate | M |
| 1A.5 | Keep rubric-priority + cooldown machinery, but re-express as **modifiers** on the new scheduler (short-leash / recovery bonus become stability nudges, not the whole interval) | `ComposeStudySession` weak-priority, `UpdateLearnerItemStates...` | M |
| 1A.6 | Daily new-item cap and daily review cap as profile/preset parameters | `ComposeStudySession` (`minimumNewItems`/`maximumWeakItems` neighbours) | S |

**Verify:** the characterisation tests from 0.3 are replaced by new ones asserting the acceptance behaviours in `01` §3.2 (unbounded expansion, lapse→relearning with reduced stability, fuzz spreads clumped items, caps hold, determinism given injected `now`).

### 1B — RAG Prototype: unify on the same model

| # | Change | Files | Size |
|---|---|---|---|
| 1B.1 | Replace the fixed Leitner ladder with the same stability model; change `update(state, correct: bool, ...)` → `update(state, grade, ...)` | `spaced_repetition.py`, `test_spaced_repetition.py` | M |
| 1B.2 | Give item state a real FK to item **and objective** (today it's a bare string with no referential integrity; regenerating item ids orphans state) | `spaced_repetition.py`, `book_learning_materials_store.py` (`math_item_states`) | M |
| 1B.3 | Make the rubric-scored task types (essay/SWT/describe-image) able to drive the schedule via the graded outcome (they produce `raw_total/max_raw_total` the current boolean scheduler structurally can't consume) | the six attempt paths in `learning_materials_api.py` | M |

**Verify:** `test_spaced_repetition.py` rewritten to the grade API; a lapsed item is reviewed sooner than a never-lapsed one; mastery cannot be reached in one clock-advanced sitting.

**Decision to make explicit:** one scheduler, two implementations (PHP + Python) that must stay behaviourally identical, or does Ela become the single scheduler of record and RAG defer to it? Recommendation: **Ela owns the live learner scheduler; RAG's is for its own standalone tool and offline simulation**, and they share a written spec + a common test vector file so they can't drift. (Raised as an open question at the end.)

---

## Phase 2 — The objective link (unblocks mastery aggregation, both repos)

`01` Rule B: today practice items and the objectives they exercise are "two disconnected universes." Nothing aggregates above a single item.

| # | Change | Files | Size |
|---|---|---|---|
| 2.1 | RAG: make `learning_goals`/objectives **real records with ids**, and stamp every generated practice item / worked example with its `objective_id`(s) | `book_learning_materials_contract.py` (schema), the item generators, `enrich_lessons.py` | L |
| 2.2 | RAG: add a check that every objective is exercised by ≥1 item and that items reference existing objectives (closes the "learning_goals read by no `.py` file" gap) | new evaluator in `pipeline_evaluators.py` with its ≥2 planted-error self-tests (honesty-gate contract) | M |
| 2.3 | Ela: content-intake contract carries `objective_id` onto imported items; `learner_item_states.objective_id` populated on introduction | `ImportSeededLearningItems.php`, content-intake contract, migration from 1A.1 | M |
| 2.4 | Ela: mastery + progress aggregate by objective (feeds the calibration/progress surfaces) | `BuildLearnerProgressSnapshot.php`, mastery predicate | M |

**Verify:** an objective's mastery is computable from its items' states; RAG's new evaluator fails a lesson whose items reference no objective and passes one correctly linked; both prove they catch their own planted error.

---

## Phase 3 — Feedback correctness & content quality (RAG-heavy)

Make feedback deterministic-first per material type (`01` Invariant 5) and enforce the pedagogy the markdown packs only *describe*.

| # | Change | Files | Size |
|---|---|---|---|
| 3.1 | Enforce worked-example **completeness and variety** (the maths pack demands 4 kinds — straightforward/twist/word-problem/mistake-correction + bar-model-first — nothing checks it) | schema flag marking the complete model answer; new evaluator + self-tests | M |
| 3.2 | Add **state-driven fading** metadata to worked examples so the runtime can withdraw scaffolding as mastery grows (`01` Invariant 4, expertise-reversal) | contract schema; enrichment generation | M |
| 3.3 | De-PTE-ify the enrichment layer: `pte_lesson_enrichment.v1` naming, `enrichment_loop._FIX_SYSTEM` opening "You correct PTE Academic…", the `slug_of` silent fallback to `pte`, the `Evaluator.domains=("pte",)` default that silently skips new checks for maths | `enrich_lessons.py`, `enrichment_loop.py`, `domain_packs.py`, evaluator registration | M |
| 3.4 | Wire the *good* enrichment loop (`close_loop`, built/tested/**unused**) into production instead of the regenerate-from-scratch path that never feeds findings back; fix the two fail-open gates (`check_lesson_facts` returns `[]` on error; health not domain-filtered) | `enrich_lessons.cmd_run`, `enrichment_loop.py`, `pipeline_evaluators.health_report` | L |
| 3.5 | Generalise `reading_level` so it isn't inert outside maths (it's the seed of the per-audience reading-level control in `02` §3.3) | `readability_evaluators.py`, evaluator `domains` | M |
| 3.6 | Extend deterministic checkers per material type: STAR-structure presence (interview), phonics-target presence (kids reading), keeping the maths numeric checkers as the model | new checker modules + self-tests | L |

**Verify:** each new evaluator ships with the mandatory ≥2 planted-error self-tests (one that must flag, one that must not) and passes the honesty gate; the maths pipeline no longer depends on a PTE PDF at a hardcoded `~/Downloads` path.

---

## Phase 4 — Audience presets & session generalisation (Ela)

Unlock the four audiences as *presets over one shell* (`02` Part 1), not forks.

| # | Change | Files | Size |
|---|---|---|---|
| 4.1 | Introduce an **audience preset**: session-length defaults, new-item caps, allowed exercise types, feedback sources, motivation framing, theme tokens — read from `learner_profiles` (`primary_learning_context`/`age_group`/`learner_level` already exist, nothing reads them) | new preset config; `HandleInertiaRequests` shared props; `learner_profiles` usage | L |
| 4.2 | Unlock session shape: `GenerateStudySessionRequest` currently allows only `duration ∈ [10,15,20]` and `session_mode = mixed_review`; `targetItemCount ∈ {6,8,10}`; exercise types picked by a 4-branch `if`; `primary_learning_unit` hardcoded `phrase_chunk`. Drive all of these from the preset | `GenerateStudySessionRequest`, `ComposeStudySession`, `StartStudySessionRuntime` | L |
| 4.3 | Replace the **learner self-graded 3-way radio** as the scheduling signal with produced-response + deterministic grading; keep an optional **pre-answer confidence** capture (calibration, `01` Invariant 6) | `StoreStudySessionResponseRequest`, runtime.tsx response step, feedback action | L |
| 4.4 | Reconcile interleaving-for-confusability with the topic-coherence ranker (they can pull against each other; make it an explicit, tunable balance) | `ComposeStudySession::baseNewItemScore` + ordering | M |
| 4.5 | Semantic theme tokens (learn/refresh/review, correct/partial/incorrect, weak/overdue) + per-audience theming; today it's the untouched starter grayscale | `resources/css/app.css`, components | M |

**Verify:** a profile switch changes session length, caps, exercise palette and theme without code change; browser tests cover each preset's runtime; scheduling is driven by graded produced responses, not self-report, for checkable content.

---

## Phase 5 — Progress, calibration & motivation surfaces (Ela)

The anti-illusion surfaces from `02` §3.

| # | Change | Files | Size |
|---|---|---|---|
| 5.1 | Rework `BuildLearnerProgressSnapshot` to show demonstrated retention + objective-level mastery + `lifecycle_state` (never surfaced today) + calibration gap; unify the "weak" definition (dashboard `≥2` vs scheduler `≥1`) | `BuildLearnerProgressSnapshot.php`, dashboard.tsx | M |
| 5.2 | Dedicated per-audience progress page (parent-facing for kids); stop showing views/minutes as achievement | new page(s) | M |
| 5.3 | Calibration surface: "felt sure but missed" panel from captured confidence vs accuracy (4.3) | new component; snapshot | M |
| 5.4 | Motivation: bounded focus session with cue + small reward, grace-protected streak, process-framed goals, mental-contrasting prompt | runtime, dashboard, profile | M |
| 5.5 | Scheduled nudges via **Cowork scheduled tasks** (create_trigger): review-due, pre-sleep/next-morning review, and for exam/interview tracks date-anchored sleep + breathing-rehearsal reminders | scheduled-task setup + Ela endpoints they hit | M |

**Verify:** progress page shows no vanity metric as achievement; calibration panel populates from real confidence captures; a scheduled nudge fires on a test schedule.

---

## Phase 6 — New capabilities: speaking capture, exam countdown, kids + parent (gated)

The genuinely new builds. **Sequence-critical: 6C is gated on a product decision.**

| # | Change | Files | Size |
|---|---|---|---|
| 6A | **Spoken-answer capture** (interview, PTE speaking, kids reading): record, store, optional transcribe; deterministic structure check on transcript; playback for self-review | new Ela runtime capability + storage | L |
| 6B | **Exam track**: test-date countdown, band-tracker per rubric trait, skill-build vs full-mock modes, test-prep checklist screen; port RAG's task-type runners into the shared runtime | new Ela surfaces + ported RAG frontend components | XL |
| 6C | **Kids track + parent surface**: parent account/consent (COPPA-style, data-minimisation), child profile, oversight/progress view; simplified audio-first child UI; phonics + early-maths runners | new subsystem | XL |

**Gate on 6C:** Ela's source-of-truth docs name generalisation — and children specifically — a **non-goal** in three places. **Write an ADR resolving that contradiction, plus a privacy/consent review, before building 6C.** This is the one place in the plan where a decision must precede code.

---

## Dependency order (the critical path)

```
Phase 0 (safety net)
      └─▶ Phase 1 (scheduler + item state)  ──┬─▶ Phase 2 (objective link)
                                              ├─▶ Phase 4 (presets/session) ─▶ Phase 5 (progress/calibration)
                                              └─▶ Phase 6A/6B/6C (new surfaces)
Phase 3 (RAG feedback/content) runs in parallel with 1B/2, feeds 4 & 6
```

Do **0 → 1 → 2** as the spine; they unlock everything and are mostly small, well-isolated diffs. Phase 3 (RAG) can proceed alongside. Phases 4–5 turn the engine into the four-audience product. Phase 6 is the big new surface area, with 6C gated on the ADR.

## The three decisions that need a human before code

1. **Children as an audience** — resolve the explicit non-goal in Ela's docs (ADR) and complete a consent/privacy review before Phase 6C. Highest-stakes, and it's a product/legal call, not an engineering one.
2. **One scheduler or two** — Ela owns the live scheduler and RAG's is standalone (recommended), vs. a single shared service. Determines Phase 1B's shape.
3. **Content supply for the Language track** — the phrase-first thesis has zero phrase content today (17,631 items are all single `word`). Decide whether the RAG pipeline generates phrase-chunks, or another source fills them, before investing in the Language surfaces. It's the binding constraint for that audience.

---

*Companion: `04_research_citations.md` supplies the evidence for every ⟦cite⟧ claim in `01`. This plan is intentionally paced so nothing high-risk lands before the safety net and the characterisation tests exist.*
