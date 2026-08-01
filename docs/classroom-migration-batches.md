# Migration batches — split, with named tests

Splits and details ADR-0002 v3 §38 Batches 0–16. Same acceptance model (learner-facing + technical), same hold criteria, but the size-L batches are split and every test names a file and an assertion.

**Scope against §38.** This document covers §38 Batches 0–16. **ADR §38 Batch 17 — Authoring, enrichment, and mobile compatibility expansion — is deliberately EXCLUDED** as noncanonical follow-on work, and is not restored unless separately approved.

**Count: 37 required batches, plus optional B4.5.** An earlier revision said 26 and omitted legacy retirement entirely; both are corrected.

**This plan adopts runtime retirement (B16) as required work in its own right.** It is not required merely because the still-proposed ADR lists it.

**Sizes:** S ≈ 1 day · M ≈ 2–3 days · L ≈ 4–5 days. Nothing here is larger than M.

**Test conventions:** `tests/Unit`, `tests/Feature`, `tests/Browser/*BrowserTest.php` (Pest + Playwright), RAG root-level `test_*.py`.


## Batch execution and review pacing

**A batch is the minimum reviewable unit.** It must not be subdivided into informal slices, micro-milestones, per-finding reports, or per-commit approval events unless the workflow owner revises the plan and creates separate batches.

### Implementer

Work continues until one of these is true:

1. Every batch acceptance criterion is implemented.
2. Required automated and manual verification is complete.
3. The implementation is ready for the batch's commit boundary.
4. A genuine escalation condition prevents further progress.

**Discovering a defect, failing test, fixture mismatch, missing regression test, type error, or local design choice is not a reason to stop.** Resolve it within the authorised scope.

Do not return per-finding progress reports, per-commit or partial-slice completion reports, requests for routine implementation decisions, or requests to review work before the batch is complete.

**Authority.** Within the approved plan and file boundaries: choose internal implementation details, correct defects, add or revise tests, update fixtures when intended behaviour or an approved internal contract legitimately changes, refactor affected code, add evidence, make non-material plan clarifications.

**Approval is required** only when a decision materially changes scope, changes approved user-visible behaviour, changes an external compatibility contract, removes an acceptance criterion, requires destructive or irreversible action, requires unavailable credentials or access, or contradicts the approved plan.

**Escalate early only for:** contradictory requirements, unavoidable material scope expansion, inaccessible systems or credentials, destructive operations needing approval, a security or safety concern, or an external dependency making further work impossible. An escalation states the exact blocking condition, work completed, work that can still proceed, and the smallest decision required.

### Reviewer

Inspect the complete implementation, diff, tests and evidence before returning a verdict. Complete the review, collect all findings, deduplicate, classify by severity and disposition, and return them in **one** consolidated response.

Do not report findings incrementally, review one commit at a time, approve informal slices, stop at the first valid defect, or request re-review before the full finding set is addressed.

**Every finding carries one disposition:**

| Disposition | Meaning |
|---|---|
| `BLOCKS_BATCH` | The batch cannot be approved until corrected. |
| `FIX_IN_CURRENT_PASS` | Correct during the consolidated fix pass; no owner decision needed. |
| `DEFERRED` | Does not block; recorded for later work. |

Preferences and optional improvements must not be blockers without a concrete correctness, compatibility, security, maintainability, or acceptance-criterion risk.

### Correction pass

Address every finding in **one uninterrupted pass**, giving each exactly one disposition: fixed, no change with evidence, blocked by a genuine escalation, deferred where marked non-blocking, or superseded by another accepted correction. Do not return after each finding.

### Bounded re-review

Two complete rounds by default — full implementation review, then full disposition and regression review with the final verdict. A third round only for a newly discovered critical or high-severity correctness defect that could not reasonably have been found in Round 1. Re-review must not introduce new stylistic preferences, expand scope, or reopen accepted design choices.

### Reporting

Progress may be recorded internally. User-facing handoffs occur **only** at: implementation complete, genuine escalation, consolidated review complete, consolidated correction complete, final verdict. Intermediate commits, test fixes and completed subparts are not milestones.

### Coordinator

Reject: review requests before implementation completion, partial finding reviews, per-finding correction reviews, starting the next batch before the current verdict, repeated reopening of accepted findings, and unapproved informal batch subdivision.

The coordinator optimises for completing the approved batch; the reviewer protects correctness at the batch boundary.

## Acceptance model

Each batch has two independent acceptance layers.

### Learner-facing acceptance

This describes observable product behaviour:

- the learner problem solved;
- what must be visible in the browser;
- phase and ordering behaviour;
- refresh, resume, retry, and completion behaviour;
- safe failure behaviour;
- what must remain unchanged.

For schema, validation, research, or infrastructure batches, the correct learner-facing outcome is usually **no visible change**.

### Technical acceptance

The existing **Done when**, **Tests**, and **Hold** sections remain the engineering acceptance layer. They validate migrations, schemas, invariants, deterministic logic, integrations, and browser automation.

A batch is shippable only when both layers pass. Passing unit or feature tests alone does not prove the learner experience is acceptable.


### Standing regression gate for every batch

`tests/Browser/VocabularyBaselineBrowserTest.php` is a permanent CI gate from B0 onward.

Every batch must run:

```bash
composer check
composer browser-check
```

The browser suite must include the B0 vocabulary baseline. This applies even when a batch says **no visible change**.

Rules:

- Infrastructure batches pass only when the baseline learner journey remains unchanged.
- Visible batches pass only when both the new learner behaviour and the existing vocabulary baseline pass.
- Updating the baseline fixture requires an explicit approved learner-facing change; it must never be refreshed merely to make a failing test green.
- A batch summary must state whether the baseline passed and whether the baseline fixture changed.

---

## Decide before B2: where does the scheduler go?

Two separate questions were being run together. They are now split, and only the second is still open.

**Settled — mastery demotion is B0.3, and it is mandatory.** A learner who forgets something the app called mastered currently never sees it again. `requirements.md:411` already promises the opposite. That is a broken promise against an adopted requirement, so it is repaired on its own, early, using the scheduling that already exists. It is not a scheduling change and does not wait for ADR-0003.

**Still open — how long the gaps between reviews should be.** ADR v3 puts all scheduling behind ADR-0003 at its batch 14. `03_implementation_plan` puts it first and calls it the single most important change in either codebase.

- **ADR v3 order** — evidence model first, scheduling last. You cannot decide how to interpret evidence before you can record it. Cost: the `12h / 1d / {1d,3d,7d}` ladder and its seven-day ceiling stay live for the whole migration, so a well-known item keeps reappearing weekly.
- **Scheduler first** — change the intervals now. Cost: you tune them against item-level state you are about to replace with objective-level evidence, so some of that work is redone.

**Recommendation:** keep ADR v3's order and write ADR-0003 alongside from B1 onward. B4.5 remains available as an interim interval-expansion batch if the weekly reappearance turns out to hurt real learners, and remains **skipped** until then. Under ruling F1 the seven-day ceiling is a known temporary limitation, not a policy violation.

---

## B0 — Baseline lock · S · —

**Does:** Commits the current vocabulary payload and browser journey as golden fixtures. No app code changes.

### Learner-facing acceptance

**Learner problem solved**

No new feature is introduced. This batch protects the vocabulary journey that already works so later architecture changes cannot alter it unnoticed.

**What the learner should see in the browser**

- The same priming screen, learning steps, recall activity, feedback, progress, and wrap-up as before.
- The same item order for the same stored learner state and injected time.
- No new labels, controls, loading states, or error messages.
- Existing in-progress and completed sessions remain usable.

**Behaviour expectations**

- Given the same learner state, seed, and time, when the learner opens the session twice, then the visible activity order and content are identical.
- Given an existing vocabulary session, when the learner progresses from priming to wrap-up, then every current interaction behaves as before.
- Given the learner refreshes during the baseline journey, when the page reloads, then the existing resume behaviour is unchanged.
- Any unapproved visible difference from the recorded baseline fails this batch.


### Technical acceptance
- Same seed + injected time → byte-identical payload, twice.
- Fixture regenerable by one documented command.
- Corpus item-type distribution audit committed.

### Technical tests
- `tests/Feature/StudySessionGoldenPayloadTest.php` — payload equals committed fixture
- `tests/Feature/StudySessionGoldenPayloadTest.php` — two runs from one seed are identical
- `tests/Browser/VocabularyBaselineBrowserTest.php` — full journey: priming → learning → recall → wrap-up

---

## B0.1 — Repair the verification gate · S · B0

**Does:** Adds `phpstan.neon` (Larastan, committed level). Switches `pint`/`lint`/`format` to check mode inside `composer check`. Adds full `composer check` + `npx playwright install` to CI.

### Learner-facing acceptance

**Learner problem solved**

No new learner capability is introduced. The learner is protected from regressions that previously could pass a verification command unnoticed.

**What the learner should see in the browser**

- No visible change.
- Login, dashboard, priming, study, recall, feedback, and wrap-up remain available.
- No page becomes slower, blank, or broken because verification tooling changed.
- No formatting or internal diagnostic output appears in learner pages.

**Behaviour expectations**

- Given a normal learner journey, when the verification-gate changes are deployed, then all existing pages render and behave exactly as before.
- Given a browser interaction that worked before this batch, when repeated afterwards, then it still succeeds without new warnings.
- This batch is rejected if repairing CI changes runtime behaviour or frontend assets.


### Technical acceptance
- A deliberately introduced type error fails `composer check`.
- A deliberately misformatted file fails `composer check`.
- CI fails on both, not just on Pest.

### Technical tests
- Manual verification, recorded in the PR: three deliberate breakages, three red builds
- `tests/Feature/MergedLearningItemsDatasetTest.php` — parses the 28 MB seed once, not seven times

**Why separate and first:** you are about to change schema and scheduling on a gate that currently rewrites files instead of failing.

---

### B0.1 closure note

**Closed 2026-07-27 by approved substitution.** The original acceptance asked for three designed failure probes recorded as commit/revert pairs on a draft PR. That was replaced, with approval, by the following combined evidence:

1. **Three isolated local failures.** A formatting violation caught by `pint --test`; a PHP wrong-argument-type error caught by PHPStan at level 5 (`argument.type`, *"expects int, string"*), which drove `composer check` to exit 1 while pint, pest and prettier stayed green; and a failing test caught by pest. Each probe was removed and its absence verified.
2. **Genuine CI red/green.** The repaired lint job failed on PR #4 with 17 real eslint `import/order` errors — Wayfinder-generated modules are gitignored and that job never built them — and went green after `php artisan wayfinder:generate --with-form` was added. Real defect, real red, real green, not a synthetic probe.
3. **Merged main green.** After merge, `composer lint:check`, `composer check` and `composer browser-check` all exit 0 on `main`, including the standing vocabulary baseline journey.

No throwaway probe PR was created, and none is required.

---

## B0.2 — Research-rule classification · S · — · **CLOSED 2026-07-27**

**Does:** Classifies every pedagogical rule as `invariant` / `initial_policy` / `domain_policy` / `experiment` / `optional_technique` (ADR §5). Records recon commit SHAs and audit dates. Re-runs `test_audit_sensitivity.py`.

### Learner-facing acceptance

**Learner problem solved**

No new screen is introduced. This batch prevents tentative research hypotheses or arbitrary numeric thresholds from being presented to the learner as proven rules.

**What the learner should see in the browser**

- No visible change.
- Existing session length, review, feedback, and mastery wording remain unchanged.
- No experimental confidence prompt, reminder, or mastery rule appears merely because it exists in a research document.

**Behaviour expectations**

- Given a rule classified as an experiment or optional technique, when this batch is complete, then it does not alter production learner behaviour without a later approved implementation batch.
- Given an existing vocabulary session, when the learner completes it, then no research-classification metadata is exposed.
- The learner experience changes only through a later batch with explicit learner-facing acceptance.


### Technical acceptance
- Classification table approved and committed.
- Every numeric threshold in the ADR carries a classification.
- `test_audit_sensitivity.py` has a current result — the deterministic-over-judge rule is load-bearing in `01` Inv. 5. **Verified 2026-07-27**; see the result below.

### Technical tests
- `test_audit_sensitivity.py` — passes, result recorded with date

### B0.2 audit-sensitivity result — 2026-07-27

**Passed. All 12 checks.** Run on `main` in the RAG repo against the live guide
corpus and `gpt-oss:120b`.

Both `CONTRADICTED` probes were detected — the essay word range (guide says
120–380, claim says 500–600) and the spoken-summary Form band (guide says 0 below
40 words, claim says 35 words still scores 2). Those are the two the test itself
records as historically unreliable: at one point the judge returned
`NOT_IN_GUIDE` for a plainly contradicted range in three runs out of four, which
is why they are bucketed as advisory and do not decide the exit code. They passed
here, but one clean run does not overturn that measurement — the deterministic
`check_word_range` and `check_trait_vocabulary` remain the load-bearing evidence
for Inv. 5, and both passed as hard failures.

**This was the last of B0.2's three acceptance criteria.** The classification
table is committed as `docs/research-rule-classification.md` — Table A covers 29
pedagogical rules, Table B every numeric threshold in ADR-0002 v3, Table C the
16 shipped values that were never decided. With the audit result recorded,
**B0.2 is closed.**

The same run is recorded in `docs/research-rule-classification.md`
§ Sensitivity-test record with the full command, provider and model. This
section states the outcome where the batch is defined; that one holds the
evidence.

---

## B0.3 — Mastery lapse repair · S · B0.1 · *runs in parallel with B1*

**Does:** Makes a mastered item return to review when the learner gets it wrong, using the scheduling that already exists. **Does not touch the seven-day cap.**

**Mandatory.** `documentation/requirements.md:411` already states *"A mastered item may later become weak again if performance drops."* Ela's `lifecycleState()` never demotes out of `mastered`. This is a live defect against an adopted requirement, not deferred scheduling work — which is why it is separate from the optional B4.5.

### Learner-facing acceptance

**Learner problem solved**

A learner who forgets something the app marked as mastered currently never sees it again. After this, forgetting brings it back.

**What the learner should see in the browser**

- Answering a mastered item incorrectly puts it back into normal review.
- It reappears in a later session like any other item needing work.
- Progress stops claiming the learner has mastered something they just got wrong.
- Nothing else about timing changes — review gaps are as they were.
- No new screen, label or setting appears.

**Behaviour expectations**

- Given an item is mastered, when the learner answers it incorrectly, then it leaves the mastered state and returns to review.
- Given an item is mastered, when the learner answers it correctly, then nothing changes.
- Given an item was demoted, when the learner answers it correctly enough times again, then it can become mastered again.
- Given the demotion happens, then the next review date is chosen by the existing scheduler — this batch adds no new interval behaviour.
- Given a partial answer on a mastered item, then behaviour follows the existing weak-score rules, not a new rule invented here.

### Technical acceptance
- `lifecycleState()` is no longer absorbing: an `incorrect` outcome on a `mastered` item demotes it.
- Demotion uses the existing weak-score and due-date logic. No new columns, no interval changes.
- The seven-day cap is untouched.
- Re-mastery remains possible via the existing `MINIMUM_SAFE_MASTERY_REVIEWS` path.
- Characterisation tests of current behaviour land first, so the change is a deliberate diff.

### Technical tests
- `tests/Unit/UpdateLearnerItemStatesAfterSessionTest.php` — incorrect on mastered demotes out of `mastered`
- `tests/Unit/UpdateLearnerItemStatesAfterSessionTest.php` — correct on mastered leaves it mastered
- `tests/Unit/UpdateLearnerItemStatesAfterSessionTest.php` — a demoted item can be re-mastered
- `tests/Unit/UpdateLearnerItemStatesAfterSessionTest.php` — interval ladder unchanged, cap still 7 days
- `tests/Feature/StudySessionSchedulingUpdateTest.php` — a demoted item is composable into a later session
- `tests/Feature/StudySessionGoldenPayloadTest.php` — baseline payload unchanged
- `tests/Browser/MasteryLapseBrowserTest.php` — a learner answers a mastered item incorrectly, its mastered status is gone, and the item reappears in a later session

**Hold:** stop if demotion requires changing interval behaviour, adding columns, or pre-empting ADR-0003.

---

## B1 — Throwaway fractions spike · M · B0 · **CLOSED 2026-07-27**

**Does:** One fractions skill behind a flag, disposable code, hand-written JSON. Deleted afterwards.

### Decision — recorded 2026-07-27

**Keep the phase order.** The learner continues through:

```text
goal → teaching → guided practice → closed-book practice → explain → finish
```

Walked end to end against a hand-written Year 5 fractions lesson. The sequence
holds; everything downstream may assume it.

**Three behaviours the permanent implementation must correct.** These came out of
the walkthrough and are folded into B10, B10.1 and B10.3 below.

1. **Asking for a mixed number means requiring a mixed number.** The spike marked
   by value alone, so `22/8` was accepted for 11/4 — and the unchanged `11/4`
   would have been too. The learner never performed the conversion that was asked
   for. Marking must check the form of the answer, not only its value.
2. **A wrong closed-book answer needs a way forward.** Offer an optional hint, or
   a route back to the worked example, before the retry. The spike simply said
   "Not quite" and left the learner with nowhere to go.
3. **Explaining must be answered.** After the learner writes their reasoning,
   show a short model explanation or checklist to compare against. In the spike
   nothing happened after submitting.

**Wrong-answer feedback must explain the mistake**, not just restate the correct
answer. "Not quite, you wrote 2 1/4" tells a learner nothing about what went
wrong.

**Setup note for anyone re-running a spike.** Passing the feature flag as a
process environment variable did not reach PHP under Herd — the child process did
not inherit it. Adding the flag to `.env` temporarily worked. Document the `.env`
route, not the inline variable.

**Disposal.** The spike code was deleted once this decision was recorded, as
planned. It survives only in the history of the Ela branch
`codex/b1-fractions-spike`.



### Learner-facing acceptance

**Learner problem solved**

Validate that the proposed classroom sequence is understandable and instructionally coherent before permanent architecture is built. A later real-learner observation can strengthen the evidence but does not block this batch.

**What the learner should see in the browser**

- A clearly labelled experimental fractions lesson available only while the feature flag is enabled.
- A simple learning goal written in child-friendly language.
- A short explanation and meaningful illustration.
- Guided practice with visible support.
- Closed-book practice without the worked solution or answer-revealing support.
- An explanation prompt asking the learner to describe the method.
- A clear completion screen.
- No experimental route or navigation entry when the flag is disabled.

**Behaviour expectations**

- Given the experiment is enabled, when the learner starts it, then phases appear in this order: goal → teach → guided practice → closed-book practice → explain → finish.
- Given the learner is in guided practice, when help is needed, then relevant support is visible.
- Given the learner enters closed-book practice, then answer-revealing teaching content is absent.
- Given the learner makes an error, then an observer can classify it as conceptual, procedural, reading-related, or arithmetic.
- Given the learner recognises a method but cannot independently produce it, then the observation notes record that distinction.
- Given the learner finishes the explanation step, then the browser shows an unambiguous completion state.


### Technical acceptance
- The product owner walks the complete flow end to end and records whether the sequence teaches clearly, drags, hides support at the right time, and makes the explanation step useful.
- Observation notes record likely error *types* — conceptual, procedural, reading, arithmetic — and whether the flow distinguishes recognition from independent production.
- A real Year 5 learner observation is recommended evidence when available, but it is not required to complete this batch.
- A written decision: keep the phase order, or change it.
- Flag defaults off.

### Technical tests
- `tests/Browser/FractionsSpikeBrowserTest.php` — flow completes
- `tests/Feature/FeatureFlagTest.php` — route absent when flag off

**Hold:** if the sequence doesn't teach, fix pedagogy before any schema work.

---

## B2 — Competency + objective tables · M · B0.3 **and** B1

**Does:** `competency_frameworks`, `learning_objectives`, `learning_objective_associations`. Stable keys and revisions. Nothing reads them.

### Learner-facing acceptance

**Learner problem solved**

No visible feature yet. This batch prepares future lessons and progress reporting to refer to stable learning objectives instead of disconnected exercises.

**What the learner should see in the browser**

- No visible change.
- Existing vocabulary sessions continue to open, progress, resume, and complete.
- No objective IDs, framework keys, or revision numbers appear in learner pages.
- Historical sessions remain readable.

**Behaviour expectations**

- Given an existing learning item with no objective alignment, when it appears in a current vocabulary session, then it behaves normally.
- Given the new tables are empty, when the learner studies, then no empty objective card or missing-content state appears.
- Any learner-facing dependency on the new graph before an approved runtime batch fails this batch.


### Technical acceptance
- Migrations up and down clean.
- `stable_key + revision` unique on both tables.
- Missing objective reference rejected.

### Technical tests
- `tests/Feature/Migrations/CompetencyGraphMigrationTest.php` — up, down, existing sessions load
- `tests/Feature/ObjectiveGraphTest.php` — duplicate `stable_key + revision` rejected
- `tests/Feature/ObjectiveGraphTest.php` — dangling objective FK rejected

---

## B2.1 — Objective associations + cycle validation · S · B2

**Does:** Typed associations (`requires`, `builds_on`, `is_child_of`, `is_equivalent_to`, `aligns_with`) and the graph validator.

### Learner-facing acceptance

**Learner problem solved**

No visible feature yet. This batch ensures future lesson order and prerequisites cannot be based on an invalid or circular objective graph.

**What the learner should see in the browser**

- No visible change.
- Current session composition remains unchanged.
- No graph-validation details or cycle paths appear in learner pages.

**Behaviour expectations**

- Given valid existing vocabulary data, when a learner opens a session, then the graph validator does not block the journey.
- Given invalid future curriculum data, when it is authored or imported, then it is rejected before it can create a broken learner sequence.
- A learner must never discover a curriculum cycle halfway through a session.


### Technical acceptance
- A prerequisite cycle is rejected with the cycle path in the error.
- `is_equivalent_to` is symmetric or explicitly documented as not.

### Technical tests
- `tests/Unit/ObjectiveGraphValidatorTest.php` — direct cycle A→B→A rejected
- `tests/Unit/ObjectiveGraphValidatorTest.php` — indirect cycle A→B→C→A rejected
- `tests/Unit/ObjectiveGraphValidatorTest.php` — valid DAG accepted
- `tests/Unit/ObjectiveGraphValidatorTest.php` — equivalence across two frameworks resolves

---

## B2.2 — Item↔objective alignment · S · B2.1

**Does:** `learning_item_objectives` with `alignment_role`. Many-to-many both ways.

### Learner-facing acceptance

**Learner problem solved**

No immediate visible feature. This batch allows one item to teach or assess several objectives and one objective to appear in several learning items.

**What the learner should see in the browser**

- No visible change.
- Existing zero-alignment vocabulary items still compose and study normally.
- No objective-alignment controls or internal roles appear in the learner runtime.

**Behaviour expectations**

- Given an existing item with no objective links, when the learner studies it, then the current journey remains available.
- Given future content has several objective links, then those links do not duplicate the item in the session by themselves.
- The learner sees one coherent activity, not one repeated card per objective.


### Technical acceptance
- One item aligns to several objectives; one objective to several items.
- Existing items can have zero alignments during migration.
- No `objective_id` column is added to `learner_item_states`.

### Technical tests
- `tests/Feature/ItemObjectiveAlignmentTest.php` — many-to-many both directions
- `tests/Feature/ItemObjectiveAlignmentTest.php` — zero-alignment item still composes into a session
- `tests/Feature/Migrations/LearnerItemStatesUnchangedTest.php` — asserts no `objective_id` column exists

---

## B3 — Activity-definition identity and `study_session_activities` · S · B0.3 **and** B1

**Does:** Creates the permanent activity-definition identity, then the child table that points at it. Nothing reads or writes either.

**Why two tables in one batch.** `study_session_activities.activity_definition_id` is a required foreign key, and a required key cannot point at a table that does not exist. B3 therefore creates the definition table first — identity only, `stable_key` plus `revision` — so the constraint is real from the moment the child table exists. B5 fills that same table in; it does not replace it, and the ids B3 creates are permanent.

### Learner-facing acceptance

**Learner problem solved**

No visible feature yet. This batch creates the storage needed for one skill to contain several ordered classroom activities.

**What the learner should see in the browser**

- No visible change.
- Existing sessions remain one coherent item per selected skill.
- No duplicate item, empty child activity, or changed progress count appears.
- Existing session resume behaviour remains intact.

**Behaviour expectations**

- Given a pre-migration session, when the learner opens or completes it, then it renders through the existing path.
- Given the new child table contains no rows for a legacy session, then the browser does not show an empty activity state.
- Any change to existing item order or item count fails this batch.


### Technical acceptance
- `activity_definitions` exists with identity only: `stable_key` + `revision`, uniquely constrained on the pair so B5 adds columns without changing the constraint.
- All contract-path columns on `study_session_activities` non-null, including `activity_definition_id`.
- **Deleting a session item deletes its activities** — cascade. The session is the owner.
- **Deleting a definition that a session used is rejected** — restrict. A published lesson may be superseded, never erased out from under a learner's history.
- `unique(study_session_item_id, position)` enforced.
- `unique(study_session_id, learning_item_id)` on the parent preserved.
- Index on `(study_session_item_id, phase, phase_position)`.

### Technical tests
- `tests/Feature/Migrations/SessionActivitiesMigrationTest.php` — up, down
- `tests/Feature/SessionActivityConstraintTest.php` — null in any required column rejected
- `tests/Feature/SessionActivityConstraintTest.php` — duplicate position rejected
- `tests/Feature/SessionActivityConstraintTest.php` — an activity pointing at a definition that does not exist is rejected
- `tests/Feature/SessionActivityConstraintTest.php` — deleting a session item cascades to its activities
- `tests/Feature/SessionActivityConstraintTest.php` — deleting a definition a session used is rejected, and the activity survives
- `tests/Feature/StudySessionGoldenPayloadTest.php` — still matches B0

---

## B4 — Response→activity linkage · M · B3

**Does:** Adds `study_session_activity_id` (nullable, legacy only), `response_path`, `attempt_number` to `study_session_responses`. Backfills existing rows as `legacy`.

### Learner-facing acceptance

**Learner problem solved**

Each submitted answer can belong to the exact activity that produced it, and retries no longer need to overwrite earlier attempts.

**What the learner should see in the browser**

- Existing legacy answers and feedback remain unchanged.
- When a retry is available, a new attempt is created rather than silently replacing the previous one.
- Feedback remains attached to the correct guided, recall, or explanation activity.
- Attempt order remains stable when attempt history is shown.
- No database identifiers or `response_path` values appear.

**Behaviour expectations**

- Given two activities belong to the same skill, when the learner answers both, then each answer and feedback remain attached to the correct activity.
- Given the learner submits attempt 1 and retries, when attempt 2 is submitted, then attempt 1 remains preserved.
- Given the learner refreshes after a submission, then the correct activity and latest attempt are restored.
- Given a legacy response has no activity link, when the learner opens its historical session, then it still renders normally.


### Technical acceptance
- Contract response without an activity is rejected at DB and application layer.
- Legacy response with null activity still loads.
- `unique(study_session_activity_id, attempt_number)`.
- Activity→item→session consistency validated on write.

### Technical tests
- `tests/Feature/ResponseActivityLinkageTest.php` — contract response, null activity → rejected
- `tests/Feature/ResponseActivityLinkageTest.php` — legacy response, null activity → loads
- `tests/Feature/ResponseActivityLinkageTest.php` — attempts 1 and 2 both persist, ordered
- `tests/Feature/ResponseActivityLinkageTest.php` — duplicate `(activity, attempt)` rejected
- `tests/Feature/ResponseActivityLinkageTest.php` — activity belonging to another session rejected
- `tests/Feature/LegacyResponseCompatibilityTest.php` — pre-migration rows render in wrap-up

---

## B4.1 — Criterion scores · S · B4

**Does:** `study_session_response_criterion_scores`, plus `rubric_key`, `rubric_revision`, `evaluator_type`, `evaluator_version` on the feedback table. Existing English score columns stay.

### Learner-facing acceptance

**Learner problem solved**

Future domains can provide activity-specific feedback criteria while the current English vocabulary feedback remains unchanged.

**What the learner should see in the browser**

- Existing vocabulary feedback wording, ordering, and scores remain identical.
- No empty generic rubric section appears for legacy responses.
- When generic criteria are eventually present, they appear in the intended order and belong to the current activity.
- Internal rubric keys and evaluator versions remain hidden unless a deliberate disclosure UI is specified.

**Behaviour expectations**

- Given an existing vocabulary response, when feedback opens, then the same definition, usage, example, grammar, and overall feedback is shown.
- Given criterion rows coexist with English columns, then the learner does not see duplicated feedback.
- Given several criteria exist, then the UI preserves their authored order.


### Technical acceptance
- Criterion rows and English columns coexist on the same response.
- `unique(response_id, criterion_key)`.
- `score <= maximum_score` rejected when both present and inverted.

### Technical tests
- `tests/Feature/CriterionScoreTest.php` — criterion rows written alongside `definition_score` etc.
- `tests/Feature/CriterionScoreTest.php` — duplicate criterion key rejected
- `tests/Feature/CriterionScoreTest.php` — score above maximum rejected
- `tests/Feature/CriterionScoreTest.php` — ordered by `position`

---

## B4.2 — Evidence records · M · B4.1, B2.2

**Does:** `study_session_response_evidence` with `evidence_mode`, `evidence_classification`, objective FK, evaluator identity, `assistance_summary`.

### Learner-facing acceptance

**Learner problem solved**

No progress surface is added yet, but the system can record what the learner actually demonstrated rather than only storing a raw score.

**What the learner should see in the browser**

- No visible change.
- Existing feedback and completion remain unchanged.
- No evidence classifications, objective IDs, evaluator keys, or internal confidence values appear yet.

**Behaviour expectations**

- Given one response supports several objectives, when the learner completes the activity, then the visible completion happens once, not once per evidence row.
- Given evidence is assisted or independent, then that internal distinction does not unexpectedly alter the current vocabulary UI.
- Given the mutable activity definition changes later, then historical learner responses remain viewable.


### Technical acceptance
- One response can create several evidence rows against different objectives.
- `evidence_classification` ∈ `independent` / `assisted` / `invalidated` / `observational` / `pending_review` is persisted.
- No evidence row can be written from model prose alone — evaluator identity required.
- `strength` is nullable and constrained to the range 0–1, stored in an **exact decimal** type. Floating point is not acceptable.

#### `strength` — storage convention

This is a **storage convention, not a mastery threshold**. It defines how to read a stored number. It says nothing about how much evidence is enough, which is domain policy and belongs to a later batch and its own ADR.

| Value | Meaning |
| --- | --- |
| `NULL` | Not evaluated |
| `0` | Evaluated, and provides no support |
| `1` | Strongest support **under that evaluator and rubric** |

**Values produced by different evaluator versions must not be compared or averaged without calibration.** `0.8` from one evaluator version and `0.8` from another are not the same quantity. This is why every evidence row carries `evaluator_type`, `evaluator_version`, `rubric_key` and `rubric_revision` alongside the number — a strength value read without them is meaningless.

The exact decimal requirement follows from the boundaries: `0` and `1` are load-bearing values, and a binary floating-point type cannot be relied upon to store or compare them exactly.

### Technical tests
- `tests/Feature/EvidenceRecordTest.php` — one response → three objective evidence rows
- `tests/Feature/EvidenceRecordTest.php` — assisted and independent rows distinguishable
- `tests/Feature/EvidenceRecordTest.php` — missing evaluator version rejected
- `tests/Feature/EvidenceRecordTest.php` — evidence survives deletion of the mutable definition
- `tests/Feature/EvidenceRecordTest.php` — `strength` stored as exact decimal; `NULL`, `0` and `1` round-trip unchanged
- `tests/Feature/EvidenceRecordTest.php` — `strength` below 0 or above 1 rejected

### Standing boundary test

`tests/Feature/EvidenceRecordTest.php` carries a permanent assertion that **no B4.1 or B4.2 internal field reaches the browser** — evaluator, rubric, criterion, objective, evidence and `strength` fields, and their values.

It asserts on the runtime **resource**, not on the internal payload. The payload legitimately carries the full feedback model including evaluator columns; `StudySessionResponseResource` whitelists fields and drops them. Asserting on the payload tests the wrong boundary.

Any later batch that deliberately surfaces one of these fields must change this test as a visible diff and record why.

---

## B4.5 — Interim interval expansion · M · B4 · *optional, currently skipped*

### Decision required before implementation

B4.5 changes how long the app waits before showing an item again, so it is not enabled automatically.

**Mastery demotion is not part of this decision.** That is B0.3, it is mandatory, and it ships regardless of what happens here.

The remaining question is only about interval length:

- **Include B4.5** if production data shows the seven-day ceiling is causing real harm before ADR-0003 is ready — repeated reviews of items the learner clearly knows, crowding out work that needs attention.
- **Skip B4.5** if weekly reappearance of well-known items is tolerable for now and avoiding an interim scheduling migration is worth more.

**Currently skipped.** There is not yet enough learner history to show harm either way. This decision does not block any other batch; it only determines whether B4.5 runs before B5.


**Does:** Under `legacy_review` only: removes the 7-day interval cap so successful reviews expand unbounded. No FSRS, no stability/difficulty columns, no new algorithm.

**Scope note.** Mastery demotion is NOT part of this batch — it moved to B0.3, which is mandatory. B4.5 concerns interval expansion only.

### Learner-facing acceptance

**Learner problem solved**

Well-known vocabulary stops returning every seven days forever.

**What the learner should see in the browser**

- A consistently successful item gradually appears less often than under the current seven-day cap.
- Existing due work does not undergo an unexplained mass reshuffle immediately after deployment.
- Review messaging remains understandable and does not expose interval formulas.

**Behaviour expectations**

- Given an item is recalled correctly across several delayed reviews, when the next review is scheduled, then its interval can grow beyond seven days.
- Given existing due dates already exist at deployment, when the repair is applied, then most learners do not suddenly receive a large unexpected backlog.
- Given the same item state and injected time, then the next due decision is deterministic.


### Technical acceptance
- Six consecutive correct reviews produce an interval well beyond 7 days.
- Existing due dates migrate without a mass reshuffle.

### Technical tests
- `tests/Unit/UpdateLearnerItemStatesAfterSessionTest.php` — interval expands past 7 days
- `tests/Unit/UpdateLearnerItemStatesAfterSessionTest.php` — deterministic given injected `now`
- `tests/Feature/SchedulerMigrationTest.php` — existing due dates shift within a stated bound

**Note:** characterisation tests capturing *current* behaviour must land before this batch, so the change is a deliberate diff.

---

## B5 — Complete activity definitions · M · B2.2 **and** B3

**Does:** Completes the `activity_definitions` table B3 created, and adds `activity_definition_objectives`. Immutable published revisions.

**Extends, never replaces.** B3's table and its ids are permanent. B5 adds columns — contract version, activity type, content, provenance, content hash, status, publication — to the existing rows and keys. Dropping and recreating the table would break every `study_session_activities` row that already points at it.

### Learner-facing acceptance

**Learner problem solved**

A learner's in-progress lesson remains stable even when authors publish a newer version of the activity.

**What the learner should see in the browser**

- No general visual change.
- A session started with revision 1 continues showing revision 1.
- New sessions may use revision 2 only after it is published and selected.
- No revision numbers or immutable-record terminology appear in the normal learner journey.

**Behaviour expectations**

- Given the learner starts revision 1, when revision 2 is published, then refresh and resume still show revision 1.
- Given a new session is composed after revision 2 becomes active, then it may use revision 2 according to policy.
- A published edit must never silently change prompts, answers, or resources inside an active session.


### Technical acceptance
- The table B3 created is extended in place; its ids and its `stable_key` + `revision` constraint are unchanged.
- Editing a published revision is rejected; a new edit creates a new revision.
- One activity aligns to several objectives with `alignment_role` and `evidence_weight`.
- `evidence_weight` is nullable and constrained to the range 0–1, stored in an **exact decimal** type. Floating point is not acceptable.

#### `evidence_weight` — storage convention

A **storage convention, not a mastery threshold**, parallel to B4.2's `strength`. It defines how to read a stored number and nothing more.

| Value | Meaning |
| --- | --- |
| `NULL` | Contribution not specified |
| `0` | Contributes no weight |
| `1` | Maximum configured contribution under this contract and rubric |

**`1` does not mean "sufficient on its own", and no value here means mastery.** How much evidence is enough is domain policy, deferred by this plan to a later batch and its own ADR, and it must not arrive through a schema comment or column semantics.

**Cross-version values require calibration before comparison or aggregation.** A `0.75` authored against one contract version and a `0.75` authored against another are not the same quantity.

If "sufficient on its own" is ever wanted, it needs a separate domain-policy decision recorded here first.

### Technical tests
- `tests/Feature/ActivityDefinitionRevisionTest.php` — published revision immutable
- `tests/Feature/ActivityDefinitionRevisionTest.php` — edit creates revision 2, revision 1 intact
- `tests/Feature/ActivityDefinitionRevisionTest.php` — many-to-many objective alignment
- `tests/Feature/ActivityDefinitionRevisionTest.php` — in-flight session keeps revision 1
- `tests/Feature/ActivityDefinitionRevisionTest.php` — definitions created in B3 keep their ids after B5's migration, tested against the migration itself rather than after it
- `tests/Feature/ActivityDefinitionRevisionTest.php` — `evidence_weight` stored as exact decimal; `NULL`, `0` and `1` round-trip unchanged
- `tests/Feature/ActivityDefinitionRevisionTest.php` — `evidence_weight` below 0 or above 1 rejected

---

## B5.1 — `learning.activity.v1` schema + validator · M · B5

**Does:** The contract itself: presentation blocks, response spec, evaluation authority, evidence claims, scaffolding, answer visibility, scheduling descriptor.

### Learner-facing acceptance

**Learner problem solved**

No visible feature yet. This batch defines a complete portable activity shape so future activities behave predictably across domains and devices.

**What the learner should see in the browser**

- No visible change.
- Existing vocabulary activities continue through the current or explicit adapter path.
- Invalid activity definitions are blocked before they can produce a broken learner page.
- No PHP class names, React component names, or contract errors appear in the UI.

**Behaviour expectations**

- Given a valid current activity, when the learner opens it, then its current visible behaviour remains unchanged.
- Given an invalid future activity definition, then it is rejected before learner delivery.
- The browser must never infer a missing evidence mode, answer policy, or scheduling policy on its own.


### Technical acceptance
- A definition missing any required field is rejected with the field path.
- `evidence_mode` incompatible with `answer_visibility` is rejected (e.g. `production` + `never`).
- An unknown `scheduling.policy` key is rejected.
- No React or PHP class name can be stored in a definition.

### Technical tests
- `tests/Unit/ActivityContractValidatorTest.php` — valid fixture passes
- `tests/Unit/ActivityContractValidatorTest.php` — missing `evidence_mode` rejected, path named
- `tests/Unit/ActivityContractValidatorTest.php` — `production` + `answer_visibility: never` rejected
- `tests/Unit/ActivityContractValidatorTest.php` — unknown scheduling policy rejected
- `tests/Unit/ActivityContractValidatorTest.php` — `"type": "App\\Foo"` rejected

---

## B5.2 — Block schemas + illustration accessibility · S · B5.1

**Does:** Per-block-type schemas and validators. `illustration` distinct from `image`.

### Learner-facing acceptance

**Learner problem solved**

No new block is delivered yet. This batch ensures future illustrations and content blocks can be rendered safely and accessibly.

**What the learner should see in the browser**

- No visible change to current vocabulary content.
- Invalid illustrations do not reach learner sessions.
- When illustrations are later enabled, meaningful alternative text and a text equivalent are available.
- Decorative images do not create noisy screen-reader output.

**Behaviour expectations**

- Given a complex illustration lacks an adequate text equivalent, then it cannot be published to the learner.
- Given a client cannot render the visual asset later, then the contract contains enough information for an equivalent fallback.
- Existing text-only vocabulary activities remain unchanged.


### Technical acceptance
- Illustration without `alt_text` rejected.
- Complex illustration without `text_equivalent` rejected.
- Every block carries its own `version`.

### Technical tests
- `tests/Unit/BlockValidatorTest.php` — each registered block type validates its fixture
- `tests/Unit/BlockValidatorTest.php` — illustration without alt text rejected
- `tests/Unit/BlockValidatorTest.php` — complex illustration without text equivalent rejected
- `tests/Unit/BlockValidatorTest.php` — unversioned block rejected

---

## B5.3 — Provenance contract · S · B5.1

**Does:** Origin values and per-origin required fields (ADR §21).

### Learner-facing acceptance

**Learner problem solved**

No visible feature yet. This batch prevents generated practice, transformed explanations, and direct source material from being falsely presented as the same kind of content.

**What the learner should see in the browser**

- No new provenance badge is required yet.
- Current vocabulary study remains unchanged.
- Invalid or misleading provenance prevents publication before the learner sees the content.
- Internal source chunk IDs remain hidden.

**Behaviour expectations**

- Given generated practice is authored from a source concept, then it is recorded as pedagogical generation rather than a direct source quotation.
- Given required source links are missing, then the content is blocked before learner delivery.
- Future disclosure UI can distinguish source-derived content from generated practice without changing historical records.


### Technical acceptance
- `source_grounded` without `source_chunk_ids` rejected.
- `pedagogical_generation` carrying `evidence_spans` rejected.
- Generated content cannot be labelled `source_grounded`.
- **Every published block declares an origin.** A block with no `provenance` is rejected at that block's path, and publication fails.

#### Why block-level provenance is required, not optional

ADR-0002 v3 §21: *"Every published activity, block, and resource declares an origin."*

A lesson is assembled from blocks, and a disclosure surface has to answer "where did this come from?" for the thing the learner is actually looking at — this paragraph, this illustration. One block with no origin makes that answer wrong for the whole lesson, and no later batch can recover an origin that was never recorded.

#### What the validator does and does not prove

It checks that a provenance record is **internally consistent**: each origin has a set of fields it may carry, and a field from another origin's set is refused. Content carrying `generator_version` cannot also claim to be a direct quotation.

It does **not** verify that source-grounded text actually appears in the source. Nothing in Ela reads a book, follows a chunk id, or compares words. A record saying `source_grounded` with a plausible chunk id passes, and the text beside it may have been invented.

**Actual grounding verification belongs to B11 (RAG emits the package) and B11.1 (Ela imports and rejects)**, where the source is available. B5.3 catches a contradiction, not a lie told consistently.

### Technical tests
- `tests/Unit/ProvenanceValidatorTest.php` — one case per origin value
- `tests/Unit/ProvenanceValidatorTest.php` — `source_grounded` missing chunk ids rejected
- `tests/Unit/ProvenanceValidatorTest.php` — generated content with evidence spans rejected
- `tests/Unit/BlockValidatorTest.php` — a block with no provenance rejected, for every registered block type
- `tests/Unit/BlockValidatorTest.php` — missing block provenance reported at the block's own path

---

## B5.4 — Resources, roles, assistance effects · M · B5.1

**Does:** `learning_resources`, **two** of the three pivots, `learning.resource.v1`, availability triggers, phase visibility, assistance effects.

### Learner-facing acceptance

**Learner problem solved**

No resource is delivered yet. This batch prepares optional help, remediation, extension, reference, and accessibility materials without hard-coding them into subject screens.

**What the learner should see in the browser**

- No visible change to current vocabulary sessions.
- Invalid resources or visibility rules do not reach the learner.
- Future resources can be shown only in allowed phases.
- Answer-revealing resources cannot be silently treated as harmless assistance.

**Behaviour expectations**

- Given the same illustration is used as core teaching material in one activity and remediation in another, then its role is determined by the link, not its media type.
- Given a resource reveals an answer, then the contract must define how later evidence is classified.
- Given a resource is hidden during recall, then the renderer cannot expose it through a generic resource panel.


### Technical acceptance
- Resource type and role are independent (illustration can be `core` or `remediation`).
- A resource with `reveals_answer` and no `evidence_classification` is rejected.
- Phase visibility validates against the canonical phase list.
- **Two pivots are created: `learning_item_resources` and `activity_definition_resources`.** `lesson_resources` is deferred to B11.1.

#### Why `lesson_resources` is deferred to B11.1

ADR-0002 v3 §27 names three pivots. Ela has no `lessons` table, and a foreign key cannot point at one that does not exist.

§27 rejects a generic polymorphic target *precisely to preserve foreign-key integrity*, so inventing a `lessons` table now — with no importer, no shape and no content — to satisfy the pivot would defeat the reason the pivot is relational in the first place.

**B11.1 is where a stored lesson first exists.** RAG emits the package in B11; Ela imports it in B11.1. That is the batch that gives `lesson_resources` something real to point at, and the batch that adds it.

B5.4 must not create the table, and a test asserts its absence so the deferral is visible rather than forgotten.

#### `evidence_classification` and assistance effects

`reveals_strategy`, `reveals_partial_answer` and `reveals_answer` **require** a classification: a learner shown the answer who then types it has demonstrated copying, and without the classification the attempt banks as ordinary evidence.

`provides_representation` and `provides_prompt` **may** carry one. Whether a representation or a prompt amounts to assistance is domain policy — a formula sheet during teaching is not the same as the same sheet during an exam — and the contract must not decide that for every domain at once.

`none` **may not** carry one, and only because it is self-contradictory: help that by its own declaration does nothing cannot change what an attempt proves.

### Technical tests
- `tests/Feature/LearningResourceRevisionTest.php` — published resource immutable
- `tests/Unit/ResourceValidatorTest.php` — type/role independence
- `tests/Unit/ResourceValidatorTest.php` — `reveals_answer` without classification rejected
- `tests/Unit/ResourceValidatorTest.php` — unknown phase in `phase_visibility` rejected
- `tests/Unit/ResourceValidatorTest.php` — unknown availability trigger rejected
- `tests/Unit/ResourceValidatorTest.php` — a contract with no inner `definition`, or an empty one, rejected
- `tests/Unit/ResourceValidatorTest.php` — non-revealing help may carry a classification; `none` may not
- `tests/Feature/LearningResourceRevisionTest.php` — a row column contradicting its contract is refused; a blank one is filled from it
- `tests/Feature/LearningResourceRevisionTest.php` — `conditional_triggers = []` rejected at the database, on both pivots, through a raw insert
- `tests/Feature/LearningResourceRevisionTest.php` — no `lesson_resources` table is created

---

## B6 — Type registries · M · B5.4

**Does:** Explicit array registries for activity types, block types, resource types. No dynamic discovery.

### Learner-facing acceptance

**Learner problem solved**

Supported content renders through controlled type registries, and unsupported content fails safely instead of showing a blank page or stack trace.

**What the learner should see in the browser**

- Existing vocabulary activity looks and behaves as before.
- If deliberately unsupported content reaches a preview or test session, a clear content-unavailable message appears.
- Navigation to leave, retry, or return remains usable.
- No exception trace, PHP class, or component name appears.

**Behaviour expectations**

- Given a known activity, block, or resource type, when the learner opens it, then it renders normally.
- Given an unknown type, when delivery is attempted, then the page remains stable and communicates that the content cannot be displayed.
- The generic runtime shows no subject-specific fork to the learner.


### Technical acceptance
- Unknown type fails with the type name in the message.
- One existing vocabulary activity resolves through the registry with a payload identical to B0.
- No domain conditional anywhere in the generic path.

### Technical tests
- `tests/Unit/ActivityRegistryTest.php` — known resolves, unknown throws with name
- `tests/Unit/BlockRegistryTest.php` — same
- `tests/Unit/ResourceRegistryTest.php` — same
- `tests/Feature/StudySessionGoldenPayloadTest.php` — parity holds
- Static check in CI: no `$domain ===` in the generic runtime path

---

## B6.1 — Evaluator registry + authority + health · M · B6

**Does:** Evaluator registry with authority modes (`deterministic` / `hybrid` / `model_advisory` / `human_review` / `unscored`), version, health state, `on_unhealthy` behaviour.

### Learner-facing acceptance

**Learner problem solved**

A model outage or unhealthy evaluator cannot lose the learner's work, invent an authoritative pass, or block session completion when only optional feedback is affected.

**What the learner should see in the browser**

- The submitted answer remains saved.
- Deterministic feedback still appears where available.
- Optional AI commentary may show a friendly unavailable or pending message.
- The learner can continue or finish the session.
- No false score is shown merely because the model returned text.

**Behaviour expectations**

- Given the model service times out, when the learner submits, then the attempt remains stored.
- Given deterministic correctness is available, then it remains authoritative despite model failure.
- Given a model evaluator is unhealthy, then no authoritative rubric result is presented.
- Given AI feedback is advisory, then it cannot change visible correctness, weak state, or due date.


### Technical acceptance
- An unhealthy model evaluator cannot issue an authoritative pass.
- Model failure never deletes or alters a stored attempt.
- Health state at evaluation time is persisted on the result.

### Technical tests
- `tests/Feature/EvaluatorAuthorityTest.php` — deterministic result authoritative
- `tests/Feature/EvaluatorAuthorityTest.php` — unhealthy model evaluator → no authoritative score, attempt intact
- `tests/Feature/EvaluatorAuthorityTest.php` — model advisory cannot change outcome
- `tests/Feature/EvaluatorAuthorityTest.php` — health state persisted per result
- `tests/Feature/AiFailureIsolationTest.php` — provider timeout leaves score, weak state, due date untouched

---

## B7 — Frontend: extract the shell · M · B6

**Does:** Splits `SessionRuntimePage`, `SessionProgress`, `PhaseHeader` and `SessionWrapUp` out of the 3,702-line runtime. Existing vocabulary rendering untouched, and still inline.

**`SessionActivityController` moves to B7.1.** The activity branch closes over ~70 identifiers in the runtime's component scope, including ten state setters and two refs. Extracting it in B7 would mean a component taking seventy props — a worse structure than the one it replaced — and hand-threading them in a batch whose entire purpose is to change nothing is the wrong risk. B7.1 introduces the block and response registries, which give that region a real seam; the split belongs against that seam, not against prop plumbing.

### Learner-facing acceptance

**Learner problem solved**

The learner keeps the same vocabulary journey while the oversized frontend runtime is split into maintainable responsibilities.

**What the learner should see in the browser**

- Identical vocabulary layout and interaction.
- The same progress, phase labels, prompts, response fields, feedback, and wrap-up.
- Refresh restores the exact persisted phase and position.
- Existing stable browser selectors still work.
- No flash, duplicated screen, or lost response during navigation.

**Behaviour expectations**

- Given the learner is on a specific activity, when the page refreshes, then that exact activity and phase return.
- Given the backend marks the current phase, then the frontend displays that phase rather than inferring another one.
- Given the learner completes the full session, then no new shell boundary is visible.
- Browser Back or Forward must not submit or advance an activity unexpectedly.


### Technical acceptance
- Phase and position read from the backend payload, never derived in React.
- `runtime.tsx` no longer owns the whole flow. The shell — page frame, phase header, progress, wrap-up — is separable from what is being studied.
- All existing `data-test` selectors still resolve.
- **The existing browser baseline passes with no test file edited.** If it needs updating rather than simply passing, the extraction has changed behaviour and the batch is not done.

### Technical tests

`tests/Browser/VocabularyBaselineBrowserTest.php` (batch B0) **supplies B7's full-journey and refresh coverage**. It already walks priming → learning pass → recall → feedback → wrap-up and asserts that a reload returns the learner to the same item and phase. A separate `StudyRuntimeShellBrowserTest` covering the same ground would duplicate it, and two tests asserting the same journey drift apart — one gets updated and the other quietly stops meaning anything.

The baseline passing **unmodified** is the evidence for B7. That is a stronger claim than a new test passing, because a new test is written against the code as it now is.

- `tests/Browser/VocabularyBaselineBrowserTest.php` — full vocabulary journey, unchanged
- `tests/Browser/VocabularyBaselineBrowserTest.php` — refresh restores exact phase and position, unchanged
- `tests/Browser/M08StudyRuntimeBrowserTest.php` — existing coverage unchanged
- `tests/Browser/StudyRuntimeHistoryBrowserTest.php` — **new.** Browser Back and Forward submit nothing and advance nothing. The baseline never touches history, so this is the one B7 promise it cannot evidence. Back is the button people press when they think they have made a mistake: if it re-posts, a learner who wanted to change their mind has recorded the same answer twice with nothing on screen to tell them.

---

## B7.1 — Frontend: block + response registries · M · B7

**Does:** `PresentationBlockRegistry`, `ResponseRendererRegistry`, `ResourceRendererRegistry`. Existing vocabulary teaching steps rendered through typed blocks or an explicit named adapter. **Extracts `SessionActivityController`, deferred from B7.**

#### `SessionActivityController`, deferred from B7

B7 extracted the session shell — page frame, phase header, progress, wrap-up — and stopped short of the activity area, because at that point it closed over around seventy identifiers in the runtime's component scope, including ten state setters and two refs. A seventy-prop component is a worse structure than the one it replaces.

**This batch is what makes the split worth doing.** Once blocks and responses resolve through registries, the activity area stops being a single interlocked expression and becomes: pick a renderer for this block, pick a renderer for this response. The controller then has a real boundary to sit on rather than a wall of props.

The same rule applies as in B7: the vocabulary baseline must pass **unmodified**. If it needs updating, behaviour has changed and the extraction is wrong.

### Learner-facing acceptance

**Learner problem solved**

Content and response controls are rendered by type, allowing new domains later while keeping the current vocabulary experience intact.

**What the learner should see in the browser**

- Existing vocabulary teaching and response controls look the same.
- Unsupported block or response types show a safe, visible unavailable state.
- Rapid repeated clicking creates one submission.
- Browser navigation does not resubmit.
- No maths- or PTE-specific UI path appears yet.

**Behaviour expectations**

- Given a known vocabulary block, when it renders through the registry, then content and accessibility remain equivalent.
- Given an unsupported block, then the rest of the page remains usable.
- Given submission is processing, when the learner clicks again, then only one attempt is created.
- Given the learner goes back and forward, then the submitted response is not sent again.


### Technical acceptance
- Vocabulary blocks render through the registry.
- Unsupported block and unsupported response kind both fail visibly and safely.
- No maths- or PTE-specific branch in the controller.
- Double submission prevented while a response is in flight.

### Technical tests
- `tests/Browser/BlockRegistryBrowserTest.php` — vocabulary renders via registry
- `tests/Browser/BlockRegistryBrowserTest.php` — unknown block type shows the safe message
- `tests/Browser/BlockRegistryBrowserTest.php` — unknown response kind shows the safe message
- `tests/Browser/BlockRegistryBrowserTest.php` — rapid double-click submits once
- `tests/Browser/BlockRegistryBrowserTest.php` — browser back does not resubmit

---

## B8 — Vocabulary on the contract path · M · B4.2, B7.1

**Does:** One vocabulary skill composed as multiple `study_session_activities` with activity-specific responses, criterion and evidence rows, immutable snapshots, `legacy_review` scheduling.

### Learner-facing acceptance

**Learner problem solved**

One vocabulary skill now uses the permanent multi-activity architecture without changing the familiar learning experience.

**What the learner should see in the browser**

- One skill appears once in high-level session progress.
- The learner advances through the journey vocabulary already has: **learning pass → recall → feedback panel.** B8 preserves that shape and does not add a phase.
- There is **no separate practice activity** for vocabulary, and none is invented. The four-phase shape named elsewhere in this plan is what the architecture supports, not a promise every domain contains all four.
- **Feedback belongs to the recall response**, as it does today — a panel attached to the submitted answer, not a step the learner advances into.
- Prompts, examples, response controls, feedback, weak-state messaging, and review timing match the legacy journey.
- Pause and resume return to the exact activity.
- No “legacy,” “contract,” “snapshot,” or “evidence” terminology appears.

**Provenance ruling (settled during B8)**

- **Every current learner-visible vocabulary field publishes as `insufficient_source_evidence`.** No field qualifies for a stronger origin, because AI enrichment can overwrite the word, definition, usage notes and example sentences on any item whatever its source type, and the enrichment log records only that a pass ran — never which fields it changed.
- **Provenance is assigned per rendered field, never per item.** `source_type` records how an item entered the system, not who wrote the text a learner reads. A manually created item can carry an AI-written definition, and nothing distinguishes the two. `manually_authored` is used only where that exact field is known to have been written by the recorded user.
- Origins that assert grounding are **unavailable for concrete reasons, not preference.** `source_grounded` and `source_transformed` require chunk ids nothing ever recorded; `pedagogical_generation` additionally asserts what the generator was grounded in and which version produced it, and neither was kept. Filling those with empty lists or guessed versions would manufacture a source-grounding claim.
- **The label is internal and does not block B8 delivery.** Learners see no "unverified" warning — it describes our records, not the content, which is what they already study today.
- **B11.1 republishes verified content as a new revision.** Because published revisions are immutable, truthful grounding arrives as a new revision rather than silently upgrading what earlier learners were shown.

**Publisher / composer boundary**

- The **publisher** renders the activity, validates the completed contract, and publishes it. Rendering happens once, before anything is published.
- The **composer** does not render. It resolves the published revision the eligibility rule selects and copies it exactly into the frozen snapshot.
- Every input that changes what the learner sees selects a **distinct published definition**. There is no runtime filtering of published content, and no fallback: a composition request for an impossible or unpublished combination fails before the learner starts.

**Behaviour expectations**

- Given one skill has several activities, when the learner advances, then they appear in persisted order.
- Given the learner pauses on activity 2, when returning, then activity 2 and its attempt state are restored.
- Given the contract path completes, then visible score, weak-state result, and next-review message match the legacy path.
- The skill is not counted several times merely because it has several activities.


### Technical acceptance
- Golden payload parity (or a named adapter projection).
- Outcome, weak-state and due-date parity with the legacy path.
- Resume returns to the exact activity.
- Evidence rows written without changing visible feedback — **conditionally**, per the rule below.

**Evidence is conditional on real objective alignment**

- Evidence is written **only where the published activity definition carries a genuine objective alignment.**
- An **unaligned legacy vocabulary item writes no evidence row and still completes normally.** That is the designed behaviour, not a degraded one: most of the migrated corpus is unaligned. B8 invents no vocabulary objective catalogue — a row naming an objective nobody authored would be evidence about a goal that does not exist.
- Evaluation reads the alignment **frozen on the activity definition**, never the live `learning_item_objectives` pivot. Adding an alignment after a session starts must not change what an older attempt meant.
- Mapping the existing vocabulary corpus to objectives needs its **own explicit content-authoring batch** if wanted. It is not B2.2 (which supplied the storage), not B9 (which guards composition), and not B8. B11/B11.1 may bring objective-bearing packages later.

**Objective alignment belongs to the frozen revision**

- `activity_definition_objectives` is part of the immutable published revision, exactly like content and provenance. Alignment decides what answering an activity demonstrates, so changing it would rewrite the meaning of every answer already given to that revision while its content and hash stayed identical.
- Alignment on a published, superseded or retired definition **cannot be inserted, changed, or deleted** — through the ORM or through raw SQL.
- The pivot's parent foreign keys **RESTRICT** rather than cascade, so historical alignment cannot be deleted as a side effect of removing a definition, an objective, or the framework containing it. Draft deletion removes its own alignment rows explicitly.
- **An alignment change creates a new revision**, on the same footing as a content or provenance change.

### Technical tests
- `tests/Feature/StudySessionGoldenPayloadTest.php` — parity
- `tests/Feature/ContractPathParityTest.php` — same score, weak update, due date as legacy
- `tests/Browser/MultiActivitySessionBrowserTest.php` — one item advances through several activities
- Aligned item produces evidence for the exact objective; unaligned item produces none
- Frozen alignment resists ORM and raw SQL; neither parent nor framework can be deleted while it points at them
- `tests/Feature/SessionResumeTest.php` — resume lands on exact activity and attempt
- `tests/Feature/SnapshotImmutabilityTest.php` — publishing revision 2 mid-session changes nothing

### Hold resolved — no vocabulary fields in the universal contract

**Answered: no.** `learning.activity.v1` does not gain `definition`, `usage_notes`, `example_sentences` or any other English-vocabulary field.

Everything the learner sees is already a rendered string or list before it reaches them: the learning pass builds `{key, title, description, content, bullets}` per step, and the recall prompt is a sentence built from the item's content. `content` is a `prose` block; `bullets` is a `phrase-list`. Nothing on screen needs the contract to name a lexical field.

Adding them would make the universal contract English-vocabulary-shaped, which is the thing this migration exists to undo.

#### Concrete per-item definitions

Each word gets its own published definitions:

```text
vocab:{item-key}:teach:learn
vocab:{item-key}:teach:refresh
vocab:{item-key}:recall:{exercise-type}
```

Keyed **by variant**, because every input that changes what the learner sees must select a distinct published definition — nothing is filtered at runtime. The teaching pass differs between meeting an item (`learn`) and re-teaching it (`refresh`); a **due** item is never taught at all, so `teach:review` must not exist. Recall is keyed by exercise type, which the composer picks from the item type and the source bucket together, so the same word is a different activity in a different session.

Only **reachable** variants are published. A word can never be a sentence-building activity, and publishing one would claim a learner could receive something they cannot.

Each contains **complete rendered blocks and real provenance** — no placeholders, no template to be filled in later. A learner-visible content change creates a **new revision**, and a session snapshot copies that exact published revision.

This was chosen over a reusable-structure-plus-recipe design. A recipe contract would have been new architecture introduced to avoid a manageable number of rows, and it would have weakened B3's requirement that every `study_session_activities` row names a real definition — `activity_definition_id` would have to become nullable, and composition would be assembling content that was never published.

With per-item definitions, B5's guarantee holds unchanged: **published means complete, and what the learner received is what was published.**

#### Composition rules

1. **The word's lexical data is rendered into complete generic blocks, and published as a definition revision.** Rendering happens once, before publication — not during composition.
2. **Validate before saving, at both points.** The definition passes the contract validator at publication (B5.1 already enforces this), and the snapshot copied into a session is checked against the revision it claims to come from.
3. **Preserve the word and source revision and provenance in the snapshot.** A snapshot that cannot say which revision of which word it was built from cannot be audited later.
4. **The learner always resumes from the frozen snapshot, never from live lexical data.** Resume reads what was stored, not what the word says today.
5. **Editing a word or a definition affects only newly composed sessions.** A session in progress is unaffected by an edit made while the learner is inside it.
6. **No unexplained placeholders inside an activity contract.** A snapshot must not contain a token pretending to be finished learner content; if a field could not be rendered, the block is absent, not filled with a stand-in.

**Hold:** resolved above. Reopen only if parity turns out to need something these rules cannot express.

---

## B9 — Composer guard · S · B8

**Does:** Removes `default => 3` from `itemTypeRank`. Registers English item types explicitly. An **unregistered item type** stops composition with an actionable error naming the type and what is registered.

**Scope note.** B9 guarantees that unregistered item types cannot become session items. It does **not** introduce domain identity: `learning_items` has no domain column, no second domain's types exist, and inventing them to have something to interleave would be content authoring rather than a guard. The registry records the domain each type belongs to, so a second domain registers through that seam rather than through a branch added to the ordering path.

**Cross-domain ordering, and errors naming a domain, belong to the batch that introduces the second domain.** Until then a mixed session means a session containing content no domain has registered, and the policy for that is to stop.

### Learner-facing acceptance

**Learner problem solved**

Unknown content cannot silently be placed last or treated as a valid session item.

**What the learner should see in the browser**

- Existing English phrase, word, and sentence-pattern order remains as approved.
- A session mixing the supported English types follows that documented order.
- If composition cannot understand content, the learner sees a recoverable preparation error.
- Retry and return actions are available.
- No stack trace or unknown-type key is exposed.

**Behaviour expectations**

- Given a supported English session, when it opens, then expected ordering is preserved.
- Given a session mixing supported types, then ordering follows the explicit registry rather than a fallback rank.
- Given an unregistered item type, then the learner is not shown a misleading partial session.
- Composition failure occurs before study starts.


### Technical acceptance
- Unregistered item type stops composition rather than ranking last, on **every** public composition path — session build, draft replacement, draft addition and draft suggestions. A single candidate is never sorted, so ordering alone is not a guard.
- English ordering asserted through the real composer action by a fixture containing a phrase chunk, a word and a sentence pattern — not by sorting values in a test, which passes even if the composer stops applying the registry.
- The error names the item type and the registered types. Naming a domain waits for the batch that introduces one.

### Technical tests
- `tests/Unit/CompositionItemTypesTest.php` — unregistered type throws, message names the type and what is registered
- `tests/Unit/ComposeStudySessionTest.php` — English ordering through the real action; unregistered content refused on session build, replacement, addition and suggestions
- `tests/Feature/CompositionFailureTest.php` — recoverable error, no session created, no internals exposed
- `tests/Playwright/composition-failure.spec.ts` — the learner sees a recoverable message with retry and return available

---

## B9.1 — Renderer availability check · S · B9

**Does:** Composition refuses to select an activity whose type, block types or required services the target client can't render.

### Learner-facing acceptance

**Learner problem solved**

The learner never reaches an activity that their current client cannot render or operate.

**What the learner should see in the browser**

- No half-rendered activity.
- No missing response control.
- No activity asking for audio when audio capture is unavailable.
- A valid fallback is shown when one exists.
- Otherwise, the activity is excluded before the session begins.

**Behaviour expectations**

- Given the target client lacks a required renderer, then that activity is not selected.
- Given a required service is unavailable, then an incompatible activity is not presented.
- Given a valid equivalent fallback exists, then the learner receives the fallback with the same intended learning meaning.
- Runtime compatibility failure must not be discovered after the learner has answered earlier phases of the same activity.


### Technical acceptance
- Missing renderer blocks selection before the session is presented.
- Missing required service (e.g. audio capture) blocks selection.

### Technical tests
- `tests/Feature/RuntimeCompatibilityTest.php` — unsupported activity type not selected
- `tests/Feature/RuntimeCompatibilityTest.php` — missing required service not selected
- `tests/Feature/RuntimeCompatibilityTest.php` — valid fallback allows selection

---

## B10 — Fractions: teach + guided · M · B9.1

**Does:** Objective graph for fractions, one learning item, teach activity, worked example, guided practice. Core fraction representation. Hand-authored content.

### Learner-facing acceptance

**Learner problem solved**

Teach one real fractions skill with a clear explanation, meaningful visual representation, guided practice, and deterministic feedback.

**What the learner should see in the browser**

- A priming screen explaining the fractions goal.
- A teaching explanation in age-appropriate language.
- A labelled, accessible fraction representation.
- A worked example.
- Guided practice with visible help.
- Immediate deterministic feedback.
- The same application shell and navigation used by vocabulary.

**Behaviour expectations**

- Given the learner enters teaching, then the representation and explanation are visible.
- Given the learner enters guided practice, then the allowed support remains available.
- Given the learner submits an answer, then the mark is shown immediately and the activity is HELD until they explicitly continue — the session cannot advance or complete past unread feedback.
- Given the learner submits the same answer repeatedly under the same conditions, then correctness is identical.
- No model-generated judgement decides exact mathematical correctness.
- The learner can complete teaching and guided practice without encountering vocabulary-specific controls.


### Technical acceptance
- Representation visible during teaching.
- Deterministic marking on the guided task — no model call decides correctness.
- **Marking checks the form the question asked for, not only the value** (B1 decision 1). A task asking for a mixed number rejects `11/4` and `22/8` even though both equal 2 3/4.
- **Wrong-answer feedback names the mistake** (B1 decision 4), e.g. "that is the right size but you have not split it into wholes yet" — not a restatement of the correct answer.
- **A marked answer holds its activity open until the learner explicitly continues.** The mark is a response-feedback state within the guided activity, not a new phase. Completion is refused while any composed activity is unfinished, so the Continue step is part of the flow rather than a convention of the page.
- **Cross-domain ordering policy: English first, then maths.** The reason is the learner's attention rather than any ranking of the subjects — language items are short and recall-like, maths items are longer and need working out. A composed session groups by domain and keeps the due/weak/new interleave within each domain. This is a pedagogical decision and belongs here, not only in code.
- Maths renders in the same shell as vocabulary.

### Technical tests
- `tests/Feature/MathEvaluationTest.php` — marking deterministic across runs
- `tests/Feature/MathEvaluationTest.php` — no model call in the correctness path
- `tests/Feature/MathEvaluationTest.php` — a mixed-number question rejects `11/4` and `22/8`, accepts `2 3/4`
- `tests/Feature/MathEvaluationTest.php` — wrong-answer feedback names the mistake, not the answer
- `tests/Playwright/fractions-teach.spec.ts` — priming → teach → guided → mark → explicit continue → wrap-up
- `tests/Feature/IllustrationProvenanceTest.php` — the fraction representation carries origin and accessibility fields
- `tests/Unit/ComposeStudySessionTest.php` — a MIXED queue composed through `ComposeStudySession` puts every English item before any maths item, including when the maths item is due and the English items are new
- `tests/Unit/ComposeStudySessionTest.php` — an ordinary learner's composed session can contain the fractions item

---

## B10.1 — Fractions: closed-book + phase visibility · S · B10

**Does:** Independent exact-answer practice with answer-revealing support hidden.

### Learner-facing acceptance

**Learner problem solved**

Test whether the learner can solve independently rather than merely following a visible example.

**What the learner should see in the browser**

- A closed-book fractions task.
- No worked solution, answer, or method-revealing representation.
- Clear response controls.
- A non-revealing accessibility equivalent when needed.
- Feedback only according to the activity's answer-visibility policy.
- No “show lesson” shortcut that invalidates independent evidence.

**Behaviour expectations**

- Given the learner enters closed-book practice, then answer-revealing teaching blocks are absent from the DOM.
- Given a screen reader is used, then an equivalent instruction remains available without revealing the method.
- Given the learner refreshes, then hidden resources remain hidden.
- The learner cannot reopen a hidden teaching resource without the attempt being ended or reclassified according to policy.


### Technical acceptance
- Method-revealing representation hidden during `closed_book_practice`.
- Accessibility text equivalent still available where it doesn't reveal the answer.
- **After a wrong answer the learner is offered a way forward** (B1 decision 2): an optional hint, or a route back to the worked example, before retrying. Taking either is recorded and classifies the later evidence as assisted; declining leaves it independent.

### Technical tests
- `tests/Feature/PhaseVisibilityTest.php` — method-revealing representation hidden in closed-book phase
- `tests/Feature/PhaseVisibilityTest.php` — non-revealing accessibility equivalent still served
- `tests/Playwright/fractions-closed-book.spec.ts` — no teaching content in the page during independent practice, including after a refresh
- `tests/Playwright/fractions-closed-book.spec.ts` — a wrong answer offers a hint or a way back to the example
- `tests/Feature/AssistanceClassificationTest.php` — declining the offered help keeps the evidence independent
- `tests/Feature/AssistanceClassificationTest.php` — help is refused before the task has been attempted, and the independent task cannot be finished without being answered
- `tests/Feature/FractionsLearnerStateTest.php` — one learner-state update per item per session, however many attempts it took

---

## B10.2 — Fractions: remediation + assistance classification · M · B10.1

**Does:** Remediation resource triggered after two incorrect attempts. Opening it reclassifies later evidence as assisted.

### Learner-facing acceptance

**Learner problem solved**

Offer targeted help after repeated difficulty while honestly recording that later success used assistance.

**What the learner should see in the browser**

- Standard corrective feedback after the first wrong attempt.
- No remediation resource after attempt 1.
- One remediation offer after attempt 2.
- A clear explanation of what the support is for.
- The support does not repeatedly reappear after being opened.
- Refresh preserves attempts and the remediation state.

**Behaviour expectations**

- Given attempt 1 is incorrect, then remediation remains hidden.
- Given attempt 2 is incorrect, then remediation appears once.
- Given the learner opens remediation, then later success is internally classified as assisted.
- Given the learner refreshes after opening it, then the resource state and attempt history remain consistent.
- Assisted classification does not shame the learner or display internal evidence terminology unless the UX later specifies it.


### Technical acceptance
- **The two-attempt threshold applies to the REMEDIATION RESOURCE only.** B10.1's optional hint and route back to the worked example remain available after the first wrong attempt — that is B10.1's own acceptance condition and the B1 decision behind it. This batch adds a resource on top; it does not move the existing help behind a second attempt.
- Attempt 1 wrong → corrective feedback and the existing optional help; no remediation resource. Attempt 2 wrong → remediation resource, once.
- Opening any answer- or strategy-revealing help marks subsequent evidence `assisted`.
- Refresh preserves attempts, the remediation resource's offered and opened state, and position.

### Technical tests
- `tests/Feature/ConditionalResourceTest.php` — fires on attempt 2, not 1
- `tests/Feature/ConditionalResourceTest.php` — fires once, not repeatedly
- `tests/Feature/AssistanceClassificationTest.php` — evidence after remediation is `assisted`
- `tests/Playwright/fractions-remediation.spec.ts` — refresh preserves attempts and the opened state
- `tests/Playwright/fractions-remediation.spec.ts` — the unopened offer carries a neutral label and leaks no strategy
- `tests/Feature/ConditionalResourceTest.php` — the link's threshold, phase visibility and availability each control delivery
- `tests/Feature/RemediationRevisionTest.php` — a session in flight keeps its revision while a new session gets the correction

---

## B10.3 — Fractions: explain + multi-objective evidence · S · B10.2

**Does:** Explain-the-method activity producing reasoning evidence separately from procedural correctness.

### Learner-facing acceptance

**Learner problem solved**

Distinguish being able to calculate the answer from being able to explain why the method works.

**What the learner should see in the browser**

- A prompt asking for an explanation in the learner's own words.
- A reference explanation after submission.
- Clear feedback on what was included and what was missing.
- Procedural correctness remains separate from explanation quality.
- The lesson ends with a clear completion state.

**Behaviour expectations**

- Given the learner solved the number correctly but explains poorly, then the browser may show strong procedural feedback and weaker reasoning feedback separately.
- Given the advisory reasoning service fails, then the correct mathematical result remains unchanged.
- Given the learner completes explanation, then procedure and reasoning are recorded as separate evidence internally.
- The learner is not told the numerical answer was wrong because an AI disliked the wording.


### Technical acceptance
- One lesson produces separate procedure and reasoning evidence.
- Reasoning feedback is advisory and cannot change procedural correctness.
- **Submitting an explanation is answered** (B1 decision 3): a short model explanation or checklist appears for comparison. Never silence.

### Technical tests
- `tests/Feature/EvidenceRecordTest.php` — procedure and reasoning evidence rows differ
- `tests/Feature/AiAdvisoryIsolationTest.php` — model failure leaves procedural evidence intact
- `tests/Browser/FractionsExplainBrowserTest.php` — full journey, teach → explain → finish
- `tests/Browser/FractionsExplainBrowserTest.php` — after submitting, a model explanation or checklist is shown
- `tests/Feature/AiAdvisoryIsolationTest.php` — the comparison text still appears when the model is unavailable

---

## B11 — RAG: emit the package · M · B8, B10.3

**Does:** RAG-side `schema_version`, producer version, domain-pack version, content revision, content hash, objective and activity export.

### Learner-facing acceptance

**Learner problem solved**

No visible feature yet. This batch ensures RAG can emit stable, versioned lesson packages that preserve objectives, activities, resources, and provenance.

**What the learner should see in the browser**

- No visible change.
- Existing hand-authored lessons remain available.
- No partially generated package reaches learner navigation.
- No schema version, hash, or producer metadata appears in normal learner screens.

**Behaviour expectations**

- Given the producer emits the same semantic lesson twice, then it does not create a visibly duplicated lesson merely because generation ran again.
- Given provenance is missing, then publication is blocked before learner delivery.
- Given the package is only generated but not imported, then no learner-facing item appears.


### Technical acceptance
- Same semantic content → same hash across runs.
- Objective graph and alignments serialise.
- Provenance attached to every generated teaching element.
- **Scope: ONE representative complete chapter. Corpus-wide manifest authoring is deferred.** The batch ships a single chapter package that exercises every relationship B11.1 imports — objectives, a teaching activity built from ordered claims of several kinds, an evidence-producing activity with an explicit evaluation contract and alignment, a resource with lesson-level link semantics, per-block provenance, and stable identifiers. Authoring manifests for the remaining chapters is content work, not this batch, and B11.1 must not assume the corpus is ready.
- **The mapping is declared, never inferred.** RAG's generated chapters carry no stable keys, no objective statements and no objective references, so an export manifest supplies them. A chapter without one is refused: deriving an objective from an explanation's wording, or aligning a question to whichever objective sits nearest it, publishes an alignment nobody authored, and evidence is then recorded against goals nobody set.

**Tests (RAG)**
- `test_package_schema.py` — required top-level fields emitted
- `test_package_schema.py` — hash stable across two runs, and moved by reordering or realigning the lesson
- `test_package_schema.py` — objective associations round-trip
- `test_provenance_continuity.py` — ≥2 planted-error cases, one must flag, one must not
- `test_export_mapping.py` — an unmapped chapter is refused rather than inferred, and `manually_authored` requires evidence of authorship
- `test_representative_package.py` — one complete chapter exercises every relationship B11.1 imports

---

## B11.1 — Ela: import + reject · M · B11

**Does:** Import validation, major-version rejection, objective coverage evaluator, orphan detection, **and the `lesson_resources` pivot deferred from B5.4**.

### Learner-facing acceptance

**Learner problem solved**

A generated lesson can enter Ela without manual repair, while incompatible or incomplete packages are rejected before a learner starts them.

**What the learner should see in the browser**

- The imported fractions lesson behaves like the reviewed native fixture.
- Expected objectives, activities, illustrations, responses, and resources are present.
- An incompatible package is absent from learner sessions.
- Import failure never appears halfway through study.
- Source or generated-content disclosure appears only where intentionally designed.

**Behaviour expectations**

- Given a supported package, when imported and assigned, then the learner completes the same journey as the native lesson.
- Given an unsupported major version, then the learner cannot start a broken lesson.
- Given an assessment objective lacks an evidence-producing activity, then the lesson is blocked before publication.
- Given an orphan activity exists, then it is reported to authors rather than surfacing as an unexplained learner step.


### Technical acceptance
- Supported package imports with no hand editing.
- Unsupported major version rejected with a clear message.
- An objective intended for assessment with no evidence-producing activity is reported.
- Import fails before session composition, never during.
- **`lesson_resources` is created in this batch**, with foreign keys to the stored lesson and to `learning_resources`, and the same link columns the other two pivots carry: `role`, `availability`, `conditional_triggers`, `phase_visibility`, `assistance_effect`.
- **A lesson-level resource in an imported package is stored through that pivot**, not flattened onto an activity or an item.

#### Recorded during B11.1: three things this batch deliberately did not do

**`objective_associations` are emitted and hashed by B11, and not imported.** RAG builds the objective-to-objective graph — `requires`, `builds_on`, `is_child_of`, `is_equivalent_to`, `aligns_with` — and folds it into the package's content hash, so a change to it changes the hash. Ela's importer ignores it. Nothing in B11.1's acceptance asks for it, and no learner-facing behaviour depends on it yet, but **B13 — Learner objective state** is the first batch that reasons across objectives, so the graph must be imported by then or B13 works from a graph that exists only in RAG.

**An activity's `evidence_mode` vocabulary is now major-version surface.** B11.1's importer refuses a package whose activity carries an evidence mode the runtime cannot place in a session, rather than defaulting it to teaching — a learner must never be shown an activity nobody decided how to deliver. The consequence is that a `learning.package.v1.x` release which legitimately ADDS a mode is refused by an older Ela, even though minor versions are additive by contract. That is the intended conservatism, and it means adding a mode requires shipping the runtime that understands it first.

**A dropped objective persists after re-import, and that is harmless.** Activities, resource links and lesson membership are all cleaned up when a package stops declaring them, because each of those reaches a learner. Objectives are not: nothing delivers an objective directly, and both the coverage and assessed rules read the package rather than the database, so a withdrawn objective creates no stale learner path. It stays in its competency framework until something needs it removed.

#### `lesson_resources`, deferred here from B5.4

ADR-0002 v3 §27 names three resource pivots. B5.4 created two —
`learning_item_resources` and `activity_definition_resources` — and could not create the third: Ela had no `lessons` table, and a foreign key cannot point at one that does not exist. §27 rejects a generic polymorphic target precisely to preserve foreign-key integrity, so inventing a lessons table with no importer, no shape and no content would have defeated the reason the pivot is relational at all.

**This is the batch where a stored lesson first exists.** B11 has RAG emit the package; B11.1 imports it. The lesson row created here is the thing `lesson_resources` points at, so this batch adds the table.

Until it exists, a package carrying a lesson-level resource — a formula sheet for the whole lesson rather than for one activity — has nowhere correct to put it. Flattening it onto every activity would be a workaround that survives into production, so the import must reject such a package rather than distort it, until this pivot lands.

`tests/Feature/LearningResourceRevisionTest.php` in B5.4 asserts the table's absence. That test must be updated or removed **in this batch**, and its failure is the intended signal that the deferral has come due.

### Technical tests
- `tests/Feature/ContentImportTest.php` — supported version imports
- `tests/Feature/ContentImportTest.php` — unsupported major version rejected
- `tests/Feature/ContentImportTest.php` — provenance survives import
- `tests/Feature/ObjectiveCoverageTest.php` — uncovered objective reported
- `tests/Feature/ObjectiveCoverageTest.php` — orphan activity reported
- `tests/Feature/LessonResourceImportTest.php` — `lesson_resources` exists, with the same link columns as the other two pivots
- `tests/Feature/LessonResourceImportTest.php` — a lesson-level resource in an imported package is stored on `lesson_resources`, not copied onto activities
- `tests/Feature/LessonResourceImportTest.php` — deleting a lesson removes its resource links and leaves the shared resource intact
- `tests/Browser/ImportedFractionsBrowserTest.php` — imported lesson matches native fixture

---

## B12 — PTE: teach + idea generation · M · B11.1

**Does:** One PTE writing skill, teaching activity, idea-generation resource, planning scaffold as remediation.

### Learner-facing acceptance

**Learner problem solved**

Teach one PTE writing skill with idea-generation support and a planning scaffold without creating a separate PTE runtime.

**What the learner should see in the browser**

- A clear PTE learning goal.
- Teaching content explaining the writing method.
- An idea-generation resource during teaching.
- A planning scaffold when the learner is eligible for remediation.
- The same generic shell, progress, resources, and navigation used by other domains.
- No independent writing task yet in this batch.

**Behaviour expectations**

- Given the learner is in teaching, when the idea-generation resource is opened, then it supports learning and is not recorded as the final response.
- Given the planning scaffold becomes eligible, then it appears only in the allowed phase.
- Given the resource is opened, then its declared assistance effect is persisted for later evidence rules.
- No PTE-specific branch should create visibly inconsistent navigation or controls.


### Technical acceptance
- Scaffolds render through the same registries — no PTE branch.
- Resources declare assistance effects.

### Technical tests
- `tests/Feature/PhaseVisibilityTest.php` — idea generation allowed in `teach`
- `tests/Browser/PteTeachBrowserTest.php` — teach phase completes
- Static check: no PTE conditional in the generic controller

---

## B12.1 — PTE: independent response + hybrid evaluation · M · B12

**Does:** Constructed response with deterministic bounds (word count, structure) plus rubric evaluation writing criterion and evidence rows.

### Learner-facing acceptance

**Learner problem solved**

Let the learner write independently and receive honest trait-level feedback while preserving the attempt when AI evaluation is unavailable.

**What the learner should see in the browser**

- A clear writing prompt and response area.
- No prepared ideas or planning scaffold during independent production.
- A visible word count when appropriate.
- Clear submission and processing states.
- Deterministic feedback for word count and required structure.
- Trait-level rubric feedback when the evaluator is healthy.
- A friendly unavailable or pending message when optional model evaluation fails.
- The session can still complete under the approved fallback.

**Behaviour expectations**

- Given independent writing begins, then teaching scaffolds are absent.
- Given the response violates a deterministic word-count rule, then that result is calculated in application code.
- Given the model evaluator is unhealthy, then the response remains saved and no false authoritative trait score appears.
- Given one essay demonstrates several objectives, then feedback remains one coherent response rather than duplicated essays.
- The task must use a skill/performance scheduling descriptor, not memory-recall.


### Technical acceptance
- Scaffolds hidden during independent production.
- Deterministic checks own word count and structure.
- Rubric revision and evaluator health persisted.
- One essay creates evidence for several objectives.
- Scheduling uses `skill_practice` or `performance_rehearsal`, never memory-recall.

### Technical tests
- `tests/Feature/PhaseVisibilityTest.php` — scaffold hidden during independent production
- `tests/Feature/PteDeterministicChecksTest.php` — word count and structure checked in code
- `tests/Feature/EvaluatorAuthorityTest.php` — unhealthy rubric evaluator → attempt stored, no authoritative trait score
- `tests/Feature/EvidenceRecordTest.php` — one essay → multiple objective evidence rows
- `tests/Feature/AiFailureIsolationTest.php` — model down, session completes
- `tests/Browser/PteWritingBrowserTest.php` — full journey

---

## B13 — Learner objective state · M · B10.3, B12.1

**Does:** `learner_objective_states` derived from evidence, with independent and assisted counts and a versioned aggregation policy.

### Learner-facing acceptance

**Learner problem solved**

No new progress UI yet. This batch makes future progress derivable from actual independent and assisted evidence rather than opaque completion counts.

**What the learner should see in the browser**

- No visible change.
- Current dashboard and session completion continue to work.
- No empty objective progress section appears prematurely.
- No lesson completion alone is newly labelled as mastery.

**Behaviour expectations**

- Given a learner completes a lesson without successful evidence, then no visible mastery claim is introduced.
- Given success used remediation, then it is not silently treated as identical to independent success.
- Given objective state is recalculated, then current learner pages remain stable until the progress batch deliberately consumes it.
- No model prose can directly create a mastered state.


### Technical acceptance
- State recomputable from persisted evidence alone.
- Assisted success does not count identically to independent.
- Completing a lesson with no successful evidence does not mark an objective mastered.
- No model prose writes state.

### Technical tests
- `tests/Feature/ObjectiveStateAggregationTest.php` — recompute from evidence reproduces state
- `tests/Feature/ObjectiveStateAggregationTest.php` — assisted vs independent weighted differently
- `tests/Feature/ObjectiveStateAggregationTest.php` — lesson completed, no evidence → not mastered
- `tests/Feature/ObjectiveStateAggregationTest.php` — aggregation policy version recorded

---

## B13.1 — Progress + calibration surfaces · M · B13

**Does:** Objective-level progress, weak skills, due work, calibration gap where captured. Unifies the weak threshold (dashboard `≥2` vs scheduler `≥1`). Separates effort metrics from learning evidence. **Decides whether advisory model feedback may order weak items.**

### Open decision — advisory feedback and weak-item ordering

> **May advisory model feedback change the order of otherwise-equivalent weak items?**

`ComposeStudySession` raises an item's priority within the weak bucket when its rubric scores have declined (`rubric_decline_priority`). Those scores may come from the AI rubric evaluator, which B6.1 classifies as `model_advisory` — an evaluator whose results may never move authoritative learner state.

This is **not** a breach of B6.1's guarantees. Ordering within an already-selected weak set changes neither visible correctness, nor `weak_score`, nor `due_at`. It is a genuinely separate question, and it belongs here because **B13.1 owns weak-item behaviour** — it is the batch that unifies the weak threshold and decides what "weak" means across the dashboard and the scheduler.

It does not belong to B14. B14 owns *when* items return; this is their order within a set already chosen.

`docs/research-rule-classification.md` already classifies this behaviour as implemented but undecided, which is exactly what it is.

**Until this batch decides, preserve the existing ordering.** Changing it earlier would be adopting a policy nobody has approved, in the opposite direction from the current one.

Whichever way it goes, record the reasoning: an advisory evaluator influencing what a learner sees next is defensible if the influence is bounded and visible, and indefensible if it silently substitutes for evidence.

### Learner-facing acceptance

**Learner problem solved**

Show what the learner has actually demonstrated, what remains weak, and where confidence differs from performance—without presenting time spent or items viewed as mastery.

**What the learner should see in the browser**

- Objective- or skill-level progress based on stored evidence.
- Weak skills and due work using one consistent weak definition.
- Separate states for maths procedure and reasoning.
- Separate PTE trait progress where evidence exists.
- Optional calibration insight such as “felt sure but missed.”
- Effort metrics clearly labelled as effort or habit.
- No “items viewed” or minutes studied presented as proof of mastery.

**Behaviour expectations**

- Given procedure is strong and reasoning is weak, then the browser can show different states.
- Given confidence was not captured, then no calibration judgement is invented.
- Given confidence was high and the answer was wrong, then the calibration surface reflects that mismatch.
- Given the learner completes a planned session, then effort may be celebrated without claiming the objectives were mastered.
- Dashboard and scheduler use the same weak threshold.


### Technical acceptance
- One weak definition across dashboard and scheduler.
- Maths procedure and reasoning can show different states.
- Confidence shown only where captured.
- **The advisory-ordering question above is answered, recorded here with its reasoning, and enforced by a test.** Either outcome is acceptable; leaving it undecided is not. B13.1 cannot close while `rubric_decline_priority` sits in the composer with no ruling behind it.

### Technical tests
- `tests/Feature/ProgressSnapshotTest.php` — single weak threshold everywhere
- `tests/Feature/ProgressSnapshotTest.php` — procedure and reasoning states differ independently
- `tests/Feature/CalibrationTest.php` — "felt sure but missed" populates from captures
- `tests/Browser/ProgressPageBrowserTest.php` — no vanity metric presented as mastery
- `tests/Feature/WeakItemOrderingTest.php` — two weak items, equal on every stored signal except their rubric-score history, are ordered according to the recorded decision. If advisory feedback **may** order them, the declining item comes first and the test says why; if it **may not**, the order is stable and the rubric history changes nothing.

---

## B14 — ADR-0003 + scheduling policies · M · B13.1 · **gated**

### ADR-0003 preparation timing

ADR-0003 is a decision dependency for B14, not a blocker for B0 through B13.1.

Work on it in two stages:

1. **Draft the decision skeleton from B1 onward** using the known questions: eligible scheduling subjects, memory versus skill/performance policies, server authority, migration safety, assisted evidence, mastery, and reference vectors.
2. **Finalise and approve it after the evidence-producing slices are proven**—especially vocabulary contract parity, fractions evidence, PTE evidence, and learner objective aggregation—so the scheduler is designed against real evidence rather than assumptions.

B14 must not begin until ADR-0003 is accepted. Earlier batches may continue while the ADR is being drafted.


Start writing ADR-0003 at B1; it must be accepted before this batch. Scope, acceptance and tests are defined by that ADR.

Minimum: `legacy_review` compatibility, `memory_recall` for eligible recall units, an explicit non-memory policy for skill and performance activities, server-authoritative scheduling, policy version snapshots, reference test vectors.

**Scheduling-policy descriptors are owned by this batch.** ADR-0002 v3's Batch 6 lists them alongside the type and evaluator registries, and they were unassigned when B6 and B6.1 were written. They belong here.

The reason is that a scheduling-policy registry is not the same kind of object as a type registry. A block type registry says how to draw a block; a scheduling-policy registry says **when a learner sees something again**, which is a claim about how people forget and how a skill is built. ADR-0002 v3 §25 names eight initial policy keys and then says explicitly that it "defines the scheduling interface, not the final algorithms", leaving ADR-0003 to decide which policy uses FSRS, what a non-memory policy actually does, and how assisted evidence is interpreted.

Registering those keys before ADR-0003 decides what they mean would create an interface that looks settled and is not — and the first thing built against it would harden a guess into a contract. B5.1 already validates `scheduling.policy` and `scheduling.subject` against §25's lists, so a definition cannot name a policy nobody has heard of; what is deferred is the descriptor that says what each policy *does*.

`legacy_review` is the exception in practice, since it must preserve behaviour that already exists rather than choose new behaviour, but it is still described here so all policies live in one place.

### Learner-facing acceptance

**Learner problem solved**

Schedule different kinds of learning appropriately: recallable knowledge returns through a memory-review policy, while essays, reasoning, and performance tasks use explicit non-memory policies.

**What the learner should see in the browser**

- Vocabulary or other eligible recall items return at expanding, understandable intervals.
- A lapse brings an item back sooner according to the approved policy.
- PTE writing and broad performance tasks receive practice plans rather than flashcard-style intervals.
- Existing due work is migrated without an unexplained mass backlog.
- Review messaging identifies what is due without exposing algorithm internals.
- Browser state never becomes the source of the next due date.

**Behaviour expectations**

- Given the same evidence, stored state, policy version, and time, then the next scheduling decision is identical.
- Given an activity is not eligible for memory scheduling, then it is never sent through FSRS or an equivalent memory-card algorithm.
- Given evidence is assisted, then the approved policy interprets it differently where ADR-0003 requires.
- Given scheduling fails, then the learner's response and evidence remain intact.
- Exact intervals, mastery transitions, retention targets, and migration bounds must match the accepted ADR-0003 rather than being invented in this batch.

### Technical acceptance

Technical acceptance, reference vectors, migration bounds, rollback, and policy-specific tests are governed by the accepted ADR-0003. No implementation begins before that ADR is approved.

**Hold:** no implementation before ADR-0003 is accepted. Reject applying FSRS universally.

---

## B15 — Tracks, presets, source-of-truth update · M · B14

**Does:** `learning_tracks`, `learner_track_enrolments`, `track_presets`. Updates the source-of-truth docs for approved later-phase multi-domain scope. Reclassifies phrase-first as English domain policy.

### Learner-facing acceptance

**Learner problem solved**

Allow one learner to study English, maths, or exam-preparation tracks with appropriate defaults while keeping one coherent product and runtime.

**What the learner should see in the browser**

- A consistent application shell across tracks.
- Track-appropriate session duration, item caps, wording, and available activity palette.
- The ability to enrol in and switch between more than one approved track.
- Existing English remains the default until another track is enabled.
- Switching track changes defaults and content, not the identity of shared controls.
- No child-focused track or child account flow without the separate required ADR.

**Behaviour expectations**

- Given the learner switches from English to maths, then defaults and available learning content change while navigation remains consistent.
- Given the same activity type exists in two tracks, then it uses the same registered renderer.
- Given the learner has several enrolments, then progress and state remain attached to the correct objectives/items without duplicating the UI shell.
- Given a track is not approved or enabled, then it does not appear in navigation.
- Phrase-first remains the explicit English-domain policy rather than a universal rule for maths or PTE.


### Technical acceptance
- Changing a preset changes defaults only, never component identity.
- Renderer selection still keyed on contract type.
- Children remain gated behind a separate ADR.

### Technical tests
- `tests/Feature/TrackPresetTest.php` — preset changes session length, caps, palette
- `tests/Feature/TrackPresetTest.php` — same renderer resolved across two tracks
- `tests/Feature/TrackPresetTest.php` — multiple enrolments compose correctly
- `tests/Browser/TrackSwitchBrowserTest.php` — switching track changes defaults, not navigation

---

## B16 — Retire the legacy runtime · M · B15

**Does:** Stops composing legacy-format sessions, lets in-flight ones finish, and deletes the legacy projector.

**Required, not optional — this plan adopts it.** A migration is not finished while new sessions can still use the old runtime; leaving two paths live indefinitely is how a learner ends up on a half-migrated journey. ADR §40 happens to list the same thing, but that ADR is still proposed and is not the reason this batch is mandatory here.

### Learner-facing acceptance

**Learner problem solved**

Every new learner uses one reliable runtime. No learner can land on a half-migrated path, and nobody loses access to what they already completed.

**What the learner should see in the browser**

- New sessions always use the current runtime.
- A session already in progress when the change ships can still be finished.
- Completed past sessions still open, read-only.
- No "legacy" or "contract" wording anywhere.
- No dead route, no duplicate journey.

**Behaviour expectations**

- Given a new session is composed, then it always has child activities and snapshots.
- Given a session was in progress at cutover, when the learner returns, then it completes showing the content originally delivered.
- Given a completed historical session, when opened, then it renders read-only and cannot be resubmitted.
- Given the legacy projector is deleted, then no active route depends on it.

### Technical acceptance
- Zero new legacy-format compositions.
- Zero legacy fallbacks in runtime metrics after the grace period.
- Legacy projector deleted, not flagged off.
- Historical read path retained.
- English compatibility score columns either removed or explicitly retained read-only, decided and documented.

### Technical tests
- `tests/Feature/LegacyRetirementTest.php` — new sessions always create child activities
- `tests/Feature/LegacyRetirementTest.php` — in-flight legacy session completes with original content
- `tests/Feature/LegacyRetirementTest.php` — completed legacy session renders read-only
- `tests/Feature/LegacyRetirementTest.php` — resubmission of a historical session is rejected
- Static check in CI: the legacy projector class no longer exists
- `tests/Browser/LegacyRetirementBrowserTest.php` — historical session opens read-only

**Hold:** do not delete legacy code while any active session depends on it, or while historical auditability is unresolved.

---

## Order and parallelism

```
0 → 0.1 → 0.2 ─┬─ 0.3 ─┐
               └─ 1 ───┴─ [pedagogy decision]
                            ├── 2 → 2.1 → 2.2 ─┐
                            ├── 3 → 4 → 4.1 → 4.2 ─┤
                            └── (4.5 optional)     │
                                                   ↓
   5 → 5.1 → 5.2 / 5.3 / 5.4 → 6 → 6.1 → 7 → 7.1 → 8 → 9 → 9.1
   → 10 → 10.1 → 10.2 → 10.3 → 11 → 11.1 → 12 → 12.1 → 13 → 13.1 → 14 → 15 → 16
```

B0.3 and B1 run in parallel; B2 and B3 both wait for **both** to finish. Independent and parallelisable after that: the `2.x` chain against the `3 → 4.x` chain. B5 waits for both chains, because it completes the definition table B3 created and links it to the objectives B2.2 aligned. `5.2`, `5.3` and `5.4` after `5.1`. Everything from `6` onward is a single file.

37 required batches plus optional B4.5, none larger than M. The decision point after B1 still governs everything downstream.

ADR §38 Batch 17 (authoring, enrichment, mobile expansion) is excluded as noncanonical follow-on work.
