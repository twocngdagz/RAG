> **NONCANONICAL RESEARCH INPUT.** This document is a dated observation or synthesis,
> not a decision. It does not adopt anything. Only explicitly accepted ADR and plan
> decisions are authoritative — see `docs/research-inputs/README.md` and
> `docs/research-rule-classification.md`.
>
> Captured 2026-07-26 · RAG `296d6b5` · Ela `da188c5`

All paths below are relative to the repo root `~/mnt/Ela` on your machine (device shell). Nothing was modified; every finding is from reading files.

---

# ELA — Current Product and Data Model Map

## 0. Stack facts (verified from `composer.json`, `package.json`, `components.json`)

Laravel 12 / PHP 8.4, Inertia v2 + React 19.2, TypeScript 5.9, Vite 7, Tailwind **v4** (CSS-first, **no `tailwind.config.js` exists anywhere**), shadcn/ui (`new-york`, `neutral`, cssVariables, lucide), Laravel Fortify (auth + 2FA), Horizon + Redis, `laravel/mcp` 0.6.7, `laravel/ai`, Laravel Boost, Wayfinder, React Compiler. Tests: Pest 4 + `pestphp/pest-plugin-browser` (Playwright, **not** Dusk). PHP and npm are **not installed in the device shell**, so nothing was executed — all findings are static reads.

---

## 1. Documentation set (the stated source of truth)

`documentation/` ≈ 13,200 lines. Product vision (`documentation/requirements.md` §1): *"not just a flashcard app or dictionary. It is a learning workflow system."* Learning-unit hierarchy is deliberate: **phrase/chunk primary, word secondary, sentence pattern tertiary**. Canonical learner workflow: priming/preview → focused study block → mixed recall + interleaving → wrap-up → future review scheduling.

Non-negotiable principle (`documentation/architecture guidelines.md`): **"The application owns learner state. AI assists, but does not own memory or product logic."** Plus 13 "Core Product Foundations" (numbering is buggy — two #12s and two #13s), 10 "Architecture Guardrails" (incl. *"Abstractions must be earned"*, *"No AI-required user-critical flow"*), and "Architecture Drift Detection Rules".

**Milestone state (`documentation/milestone.md`, last_updated 2026-03-20): all 12 MVP milestones M01–M12 are recorded `accepted` / 100% / `conformant`. There is no in-progress milestone.** M01 Foundation, M02 Auth+Learner Profile, M03 Core Content Domain, M04 Content Intake, M05 Admin/Content Panel, M06 Session Composition, M07 Priming Payload+Screen, M08 Exercise Runtime+Completion, M09 Review Scheduling+Weak-Item Engine, M10 Progress Dashboard, M11 AI Enrichment, M12 Hardening/MVP Acceptance. Forward work is post-MVP **PM01–PM06**, all unchecked: PM01 Advanced Review Tuning, PM02 Richer Personalization, PM03 Speaking Prep, PM04 Pronunciation/Fluency, PM05 Multi-User, PM06 AI Feedback and Scoring Layer. Note the code contains policy tags up to `m15_focus_session_v1`, so **the code is ahead of `milestone.md`**.

Explicitly **OPEN** decisions (`documentation/requirements.md` §15) — all still open in the doc even though code has since chosen values: exact review scheduling formula; mastery thresholds; exact learner-level model (CEFR vs custom); AI failure handling per feature; whether the AI priming summary is automatic or on-demand; whether AI priming can be disabled; whether same-day sessions reuse priming; **whether AI scores should influence weak-item calculations** (code has since decided: yes, see §3).

Stale/contradictory docs — flagging because they will mislead a redesign: `README.md` still says "Milestone alignment target: M01"; `milestone.md` header still says "Status: Proposed Baseline Plan" and §11.1 shows M01/M02 `not_started`; an unclosed YAML fence swallows §11.2+; `documentation/initial guide.md` is a stale near-duplicate of `documentation/execution guide.md` (97 diff lines); `documentation/ai enhancement plan.md` recommends **gpt-5-mini on a $10/month hard budget** (soft $6 / degraded $8 / hard stop $10) which is entirely stale — shipped code uses Ollama + NVIDIA. `documentation/chrome devtools element mapping.md` is stale in claiming no system-admin role exists (it does).

`documentation/priming screen.md` specifies the priming screen literally: title **"Today's Study Preview"**, subtitle `{duration}-minute focused session · {session_mode_label}`, 7 blocks (Header, optional AI Coach Summary, Session Facts Card, Practice Items Preview 3–5, Weak Area Card, Expected Benefit Card, CTA Row = Start Session / Edit Session / Skip Priming), target under 1–2 minutes, justified by Oakley's "prime your mental pump", hybrid rule: **rule-based output is source of truth, AI may only rewrite**.

**Critical mismatch with your redesign brief:** generalisation is an explicit **NON-GOAL** in three docs ("a generalized all-subject learning platform", "a generalized edtech platform for every subject"). There is **no mention anywhere in the source-of-truth docs of children, kids, PTE, or reading instruction**. Only `documentation/v2/` mentions IELTS/interview and math, and `documentation/v2/` is **orphaned** — not referenced by any source-of-truth doc. Also: the "Actions pattern", `declare(strict_types=1)`, and Inertia conventions the code actually follows are **not in the doc set at all** — they come from `AGENTS.md` (Laravel Boost guidelines).

### `documentation/v2/` — designed, essentially unbuilt

`documentation/v2/architecture.md` (self-labelled "Version: v1"): *"The system is not an English learning application. It is a universal learning engine capable of supporting any domain."* Layers: Learning Engine (core, immutable, deterministic) + Domain Adapter (replaceable) + Content Pipeline + Verification Layer + AI Assistance Layer. Six capabilities: `recall, conceptual_understanding, application, reasoning, transfer, communication`. Adapter surface `generateExercisesByCapability() / evaluateByCapability() / generatePrimingByCapability()`.

**Build status, verified by grep: `grep -ril capability app/ database/migrations/` returns ZERO matches.** No `capabilities` table, no `DomainAdapter`, no `EvaluationEngine`, no `app/Domain`, none of the 8 proposed content-pipeline jobs. v2 is 100% document.

v2 spec gaps that matter for planning: `documentation/v2/session-engine.md` defines `StudySessionEntry {study_session_id, learning_item_id, concept_id, capability, source_bucket, sequence, difficulty, metadata}`, status enum `draft → primed → in_progress → completed`, 7 session modes, `balanced_default` weights **due 40% / weak 35% / new 25%**, duration shaping (10min = 2–3 capabilities, 15min = 3+, 20min = 4+ and 3–5 preview items), min capability breadth 2/3/4, anti-clumping "no more than **2 consecutive** same source bucket or same capability", a 12-step composition algorithm, and `selection_score = due_weight + weak_weight + capability_gap_weight + novelty_weight - repetition_penalty - overload_penalty` — **symbolic only, no coefficients, no normalisation. That is the single biggest spec gap in v2.** There is **no spaced-repetition interval logic, no ease factor, no graduation criteria anywhere in v2**. `evaluation-engine.md`: `capability_score = (accuracy + clarity + depth) / 3`, `overall_score = average(all capability_scores)` — criteria keys are inconsistent between formula and example, and no scale bounds are given. `math-domain-adapter.md` gives one prompt per capability ("What is 6 × 7?" … "Explain your steps in solving 12 × 8"), **conflicts with session-engine** by requiring all 6 capability stages in every math session, and says **nothing about children specifically** — no age banding, no reading level, no parent surface. `content-pipeline.md` uses `difficulty` as integer `1-5`, which conflicts with the shipped string difficulty (see §7).

### `docs/adr/` — one ADR only

`docs/adr/0001-focus-sessions-and-mastery-targets.md` is the entire ADR set, 3 lines, verbatim: *"We represent immediate one-item practice as a real study session, called a Focus Session, instead of a separate AI coach or dictionary workflow. This keeps spontaneous learner intent inside the same app-owned response, scheduling, weak-state, and mastery rules while allowing Mastery Targets to boost normal session composition without overriding due and weak review safety."*

### `docs/knowledge/` — agent project memory, MCP-served

Markdown-backed. Document frontmatter schema: `id, title, type (architecture|product|guide|schema|meta), status (draft|active|deprecated), tags, summary (max 200 chars), related.{issues,adrs}`; protected ids `readme, context, discoveries, index` are never upsertable; atomic temp-file+rename writes; slug regex `/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/`. **Exactly one recorded discovery** (2026-07-25, tag `[v2]`): the RAG-Prototype Python/FastAPI side project (PTE + Year-5 maths) is the concrete implementation of the v2 Verification Layer. Its key principles: prefer deterministic checks over an LLM judge (a judge *"at temperature 0 flipped a plainly-contradicted numeric claim across runs"*); the **honesty gate — "a check may only certify (PASS) if, on this run, it just caught its own planted error"**; three verdicts `pass/fix/escalate`; *"Accepted means no KNOWN defect — a floor, not a certificate"*; generic OCR destroyed ~24% of lines (LaTeX-preserving parsing needed for maths). The `discoveries.md` entry itself is **malformed** — it leaked a raw MCP argument fragment instead of a `- Related:` line.

---

## 2. Data model

24 migrations in `database/migrations/`, 4 of which are starter-kit/users. Domain tables, columns verbatim:

**`learner_profiles`** — `id`, `user_id` (unique, FK cascade), `default_session_duration_minutes` unsignedTinyInteger default **20**, `age_group`(32), `english_background`(32), `home_language`(100), `current_country`(100), `learner_level`, `proficiency_reference`(100), `primary_learning_context`(64), `preferred_explanation_style`(32), `learning_goals`(text), `preferred_content_focus`, `coach_focuses`(json), `progress_snapshot`(json), timestamps.

**`learning_items`** — `id`, `owner_user_id` (nullable FK users nullOnDelete; **null = seeded/global**), `item_type`, `content`(text), `definition`(text), `topic`, `difficulty`, `source_type`, `source_label`, `usage_notes`(text), `example_sentences`(json), `metadata`(json), `archived_at`, `archived_reason`, timestamps. Indexes `[item_type,topic]`, `[source_type,owner_user_id]`, `learning_items_owner_archived_idx`. **All rich lexical data lives inside `metadata.lexical_data`, not in columns** — see §6/§7.

**`learner_item_states`** — `id`, `user_id` FK, `learning_item_id` FK, `introduced_at`, `reviewed_at`, `mastered_at`, `mastery_target_started_at`, `mastery_target_removed_at`, `last_studied_at`, `due_at`, `weak_score` unsignedTinyInteger default 0, `times_seen` unsignedSmallInteger default 0, `lifecycle_state` string default `'reviewed'`, timestamps. Unique `lis_user_learning_item_unique`; indexes `lis_user_due_idx`, `lis_user_weak_idx`, `lis_user_lifecycle_idx`, `lis_user_mastery_target_idx [user_id, mastery_target_started_at, mastery_target_removed_at]`. **There is no interval column, no ease factor, no lapse counter, and no intensity column.** Lifecycle backfill logic used at migration: `times_seen >= 4 && weak_score === 0 => 'mastered'`, `times_seen >= 1 => 'reviewed'`, `introduced_at !== null => 'introduced'`, default `'reviewed'`.

**`study_sessions`** — `id`, `user_id` FK, `session_date`(date), `session_mode`(50, default `'mixed_review'`), `duration_minutes` unsignedTinyInteger default 20, `status`(50 default `'draft'`), `summary`(json), `metadata`(json), timestamps. **The entire runtime state machine (priming state, runtime state, wrap-up) lives in `metadata` JSON, not in columns.**

**`study_session_items`** — `id`, `study_session_id` FK, `learning_item_id` FK, `source_bucket`(50), `position` unsignedSmallInteger, `metadata`(json). Unique `ssi_session_learning_item_unique`, index `ssi_session_position_idx`. **`study_mode`, `exercise_type`, `response_mode`, `prompt`, `selection_reason`, `selection_context` all live in `metadata`, not columns.**

**`study_session_responses`** — `id`, `study_session_id` FK, `study_session_item_id` FK **unique**, `learning_item_id` FK, `exercise_type`(40), `response_text`(text), `outcome`(20), `metadata`(json), `submitted_at`. One response per session item, ever.

**`study_session_response_feedback`** (+2 alters) — `study_session_response_id` (unique), `study_session_id`, `learning_item_id`, `user_id`, `deterministic_outcome`(20), `learner_self_rating`(tinyint), `definition_score`+`definition_reason`, `usage_score`+`usage_reason`, `example_score`+`example_reason`, `grammar_score`+`grammar_reason`, `overall_score`(unsignedSmallInteger), `matches_self_rating`(bool), `what_was_good`/`what_was_wrong`/`missing_points`(json), `better_answer_example`(text), `next_time_focus`(text), `confidence`(20), `provider`(50), `model`(100), `primary_model`(100), `fallback_used`(bool false), `fallback_model`(100), `fallback_reason`(100), `fallback_error_message`(text), `prompt_version`(80), `input_tokens`, `output_tokens`, `estimated_cost` decimal(12,6), `generated_at`, `reused_from_feedback_id` (self FK nullOnDelete). Indexes `response_feedback_item_history_index [user_id, learning_item_id, generated_at]`, plus study_session_id, overall_score, prompt_version. This is the most operationally mature table in the schema — full provider/model/fallback/cost telemetry.

**`extracted_learning_item_candidates`** — `owner_user_id` FK, `accepted_learning_item_id` (nullable FK), `source_text`(longText), `source_label` default `'pasted-text'`, `item_type`(50), `content`(string 5000), `extraction_method`(100) default `'heuristic_phrase_first'`, `review_status`(50) default `'pending'`, `position`, `metadata`(json), `reviewed_at`.

**`learning_item_enrichment_passes`** — `learning_item_id` FK, `pass_name`(100), `status`(32 default `'pending'`), `attempts` unsignedSmallInteger 0, `last_error`(text), `started_at`, `completed_at`. Unique `li_enrichment_pass_unique [learning_item_id, pass_name]`, index `li_enrichment_pass_status_idx [status, pass_name]`.

**`learning_item_coach_interactions`** (+alter) — `user_id`, `learning_item_id`, `study_session_id`(nullable), `question`, `answer`, `correction`, `more_natural_version`, `explanation`, `example`, `provider`(100), `model`(255), `primary_model`(255), `fallback_used`, `fallback_model`(255), `fallback_reason`(100), `fallback_error_message`, `task`(100). Index `coach_interactions_lookup`.

**`learning_item_curriculum_profiles`** — `learning_item_id` FK **unique**, `curriculum_cluster_key`, `curriculum_cluster_label`, `semantic_family_key`, `sibling_group_key`(nullable), `usage_domain`, `difficulty_band`, `progression_stage`, `utility_score`, `teachability_score`, `contrastive_value_score`, `review_priority_score` (all unsignedTinyInteger 0–255), `is_high_frequency`(bool), `is_foundational`(bool), `metadata`(json), `generated_by`, `generated_at`, `approved_at`. Indexes `curriculum_cluster_band_idx`, `curriculum_usage_band_idx`, semantic_family_key, sibling_group_key, utility_score, teachability_score.

**`users.is_system_admin`** bool default false (added after `password`).

### Model classes (`app/Models/`, 12 files)

No model declares `$guarded`; all use `$fillable`. No SoftDeletes anywhere (archival is manual `archived_at` + `scopeNotArchived`).

Constants that are the de-facto domain enums:
- `LearningItem`: `TYPE_PHRASE_CHUNK='phrase_chunk'`, `TYPE_WORD='word'`, `TYPE_SENTENCE_PATTERN='sentence_pattern'`; `SOURCE_SEEDED='seeded'`, `SOURCE_MANUAL='manual'`, `SOURCE_EXTRACTED='extracted'`.
- `LearnerItemState`: `LIFECYCLE_UNSEEN='unseen'`, `LIFECYCLE_INTRODUCED='introduced'`, `LIFECYCLE_REVIEWED='reviewed'`, `LIFECYCLE_MASTERED='mastered'`.
- `StudySession`: `MODE_MIXED_REVIEW='mixed_review'`, `MODE_FOCUS='focus_session'` (asymmetric name/value), `STATUS_DRAFT='draft'`, `STATUS_IN_PROGRESS='in_progress'`, `STATUS_COMPLETED='completed'`.
- `StudySessionItem`: `SOURCE_DUE='due'|SOURCE_WEAK='weak'|SOURCE_NEW='new'`; `MODE_LEARN='learn'|MODE_REFRESH='refresh'|MODE_REVIEW='review'`; `EXERCISE_FLASHCARD_REVIEW='flashcard_review'|EXERCISE_QUIZ_RECALL='quiz_recall'|EXERCISE_SENTENCE_BUILDING='sentence_building'|EXERCISE_MIXED_REVIEW='mixed_review'`. **`MODE_*` and `EXERCISE_*` have no backing column on this table** — they are `metadata` JSON vocabularies.
- `StudySessionResponse`: `OUTCOME_CORRECT='correct'|OUTCOME_PARTIAL='partial'|OUTCOME_INCORRECT='incorrect'`; `RUBRIC_FEEDBACK_QUEUED|PROCESSING|READY|FAILED|NOT_APPLICABLE`; `RUBRIC_FEEDBACK_SOURCE_AI='ai'|SOURCE_BASIC='basic'` — again all metadata keys, no columns.
- `StudySessionResponseFeedback`: `PROVIDER_APP='app'`, `MODEL_DETERMINISTIC_RUBRIC='deterministic-rubric-v1'`, `PROMPT_VERSION_DETERMINISTIC_RUBRIC='study_response_rubric_v2'`, `PROMPT_VERSION_AI_RUBRIC='study_response_ai_rubric_v2'`.
- `ExtractedLearningItemCandidate`: `STATUS_PENDING|ACCEPTED|REJECTED`, `METHOD_HEURISTIC_PHRASE_FIRST='heuristic_phrase_first'`.
- `LearningItemEnrichmentPass`: `STATUS_PENDING|QUEUED|RUNNING|COMPLETED|FAILED`, `DEFAULT_STALE_MINUTES=30`.
- `LearningItemCurriculumProfile`: `GENERATED_BY_DETERMINISTIC_V1='deterministic_v1'`.
- `LearningItemCoachInteraction`: **no constants at all** (task/provider vocabularies are bare strings).

Notable scopes: `LearningItem::visibleTo(User)` (admin → `notArchived()`; else `notArchived()` AND (`seeded` OR owner)), `phraseFirstOrder` (`orderByRaw` CASE phrase_chunk 0 / word 1 / sentence_pattern 2), `searchRelevanceOrder($search)` (7-tier CASE: exact content → content prefix → content contains → definition → topic → source_label). `LearnerItemState::dueAtOrBefore($anchor)`, `weak(int $threshold = 1)`, `activeMasteryTarget` (`started_at NOT NULL AND removed_at NULL`).

`LearnerProfile` deliberately **omits `user_id` from `$fillable`**. `ExtractedLearningItemCandidate::isPending` is the **only** Eloquent `Attribute` accessor in the entire Models directory; there are no `isWeak`/`isDue`/`isOverdue`/`isLapsed` helpers anywhere. `User` has no `studySessionResponses()` relation (responses reach the user only via session).

---

## 3. The scheduling / mastery algorithm (read in full)

### 3a. Session composition — `app/Actions/StudySessions/ComposeStudySession.php` (2023 lines)

Policy tag `COMPOSITION_POLICY = 'm12_session_mix_curriculum_profiles_v1'`; metadata `composition_strategy = 'phrase_first_round_robin'`.

**Size** — `targetItemCount(int $durationMinutes)`: `10 => 6`, `15 => 8`, `default => 10`. `GenerateStudySessionRequest` restricts duration to **[10, 15, 20]** and `session_mode` to `MODE_MIXED_REVIEW` only. So a session is always exactly 6, 8 or 10 items. `minimumNewItems`: `6 => 2, default => 3`. `maximumWeakItems`: `6 => 2, default => 3`.

**Anchor** — `$anchor = CarbonImmutable::parse($sessionDate)->endOfDay()`, i.e. anything due by end of the chosen day counts as due.

**Three buckets, computed in order (each excludes the previous):**

1. `dueItems()` — `LearnerItemState` where `due_at IS NOT NULL AND due_at <= anchor`. Sorted by `itemTypeRank` (phrase_chunk 0, word 1, sentence_pattern 2, other 3), then `due_at`, then `learning_item_id`. `study_mode = weak_score >= 1 ? MODE_REFRESH : MODE_REVIEW`. Reason `due_review`.
2. `weakItems()` — `weak_score >= 1` (scope default) AND (`due_at IS NULL OR due_at > anchor`), minus due ids, minus **cooldown ids**. Sorted by `itemTypeRank`, then `-priority_rank`, then `-weak_score`, then id. `study_mode = MODE_REFRESH`. Reason `weak_reinforcement` or `rubric_decline_priority`.
3. `newItems()` = `masteryTargetItems()` **concat** `rankNewItems(candidates)`, deduped by learning-item id. So **mastery targets are prepended to the new bucket, never given their own slots** — exactly as ADR 0001 describes.

**Cooldown (`latestCompletedSessionContext`)** — from the single most recent completed session: take every responded learning-item id, then *remove* those answered `incorrect` and those whose rubric score declined. The remainder becomes `cooldown_excluded_item_ids`, which are barred from the weak bucket. Effect: an item you got right or partially right last session can't be re-drawn as "weak" immediately; an item you got wrong, or whose rubric declined, is exempt from cooldown and can come straight back.

**Rubric-driven weak priority (`weakItemPriorityProfiles`)** — for each weak candidate, take the **3 most recent** `StudySessionResponseFeedback.overall_score` values (0–100 scale). `latestDelta = s0 - s1`, `previousDelta = s1 - s2`. Signal: `latestDelta <= -5` → `rubric_decline_priority` (`priority_rank 2`, highest); `latestDelta >= 5 && previousDelta >= 5 && s0 >= 70` → `rubric_recovery_stable` (`priority_rank 0`, deprioritised); else `standard_weak_priority` (rank 1). **This is where AI rubric scores do influence review scheduling** — which `documentation/requirements.md` §15 still lists as an open question.

**Mastery targets (`masteryTargetItems`)** — `activeMasteryTarget` AND (`due_at IS NULL OR due_at > anchor`) — i.e. **due targets are deliberately left to the due bucket**. Sorted by `masteryTargetIntensityRank` then `itemTypeRank` then id. `study_mode = (times_seen === 0 || lifecycle_state === 'introduced') ? MODE_LEARN : MODE_REVIEW`. Reason `mastery_target_priority`, `selection_context = {target_intensity, mastery_target_started_at, reason_label: 'Learner-selected mastery target'}`.

**"Target intensity" — the direct answer to your question.** There is no intensity column. It is derived, and **it does not decay at all.** `app/Models/LearnerItemState.php:182-197` verbatim:

```php
public function masteryTargetIntensity(): ?string
{
    if (! $this->isActiveMasteryTarget()) { return null; }
    if ($this->weak_score > 0 || $this->times_seen === 0 || $this->lifecycle_state === self::LIFECYCLE_INTRODUCED) {
        return 'high';
    }
    if ($this->lifecycle_state === self::LIFECYCLE_MASTERED) { return 'low'; }
    return 'medium';
}
```

Ranked by `ComposeStudySession::masteryTargetIntensityRank`: `'high' => 0, 'medium' => 1, 'low' => 2, default => 3`. **`mastery_target_started_at` is read only for the active check and for display — elapsed time never enters the computation.** A target set six months ago on a clean `reviewed` item reads `'medium'` forever. `'high'|'medium'|'low'` are bare string literals with no class constants, duplicated across three files (`LearnerItemState`, `ComposeStudySession`, and `resources/js/pages/learning-items/show.tsx` which types it `string | null`). `grep -ri intensity documentation/` returns **zero** — intensity is entirely undocumented.

**New-item ranking (`baseNewItemScore`)** — this is the most sophisticated part of the engine, and it is purely about *content coherence*, not memory:

```
item_type:      phrase_chunk +30 | word +18 | sentence_pattern +10
topic === anchor_topic:        +45 if anchor_topic_source === 'session_topic', else +28
topic === weak_topic:         +18
difficultyFitScore(...)       (see below)
if curriculumProfile present:
    + intdiv(utility_score, 2)              // up to +50
    + intdiv(teachability_score, 5)         // up to +20
    + intdiv(contrastive_value_score, 8)
    + intdiv(review_priority_score, 10)
    + 24/16 if curriculum_cluster_key === anchor_cluster_key
    + 14    if curriculum_cluster_key === weak_cluster_key
    + 10    if difficulty_band === preferred_difficulty_band
if topic seen >= 2 recently AND topic !== anchor_topic:  -10
```

Candidate pool is bounded: `NEW_ITEM_CANDIDATE_SLICE_LIMIT = 80`, `NEW_ITEM_CANDIDATE_FALLBACK_LIMIT = 120`. After ranking, entries are re-sorted with **lexical-family and sibling-group reservations** so the session does not serve three morphological variants of the same word. Selection reasons drive the learner-facing "why this item" copy: `new_item_weak_topic_support` ("Supports a weaker topic"), `new_item_topic_match` ("Matches today's main topic"), `new_item_topic_set` ("Sets a coherent topic lane"), `new_item_difficulty_fit` ("Fits your current difficulty band"), `new_item_introduction` ("Adds fresh language without breaking focus").

**Ordering (`interleavedSelection`)** — a **strict round-robin over `[due, weak, new]`** until `targetItemCount` is reached, each bucket already internally phrase-first sorted. `canSelectBucket` gates it: `due` is always allowed; `weak` is refused once `maximumWeakItems` is hit, and refused if taking it would make it impossible to still reach `minimumNewItems` (`remainingSlotsAfterSelection >= remainingNewItemsRequired`); `new` is always allowed. If the round-robin under-fills, `fillRemainingSelection` drains buckets in the order `due → new → weak`. **There is no anti-clumping rule** (v2 specifies max 2 consecutive same-bucket; the shipped round-robin achieves interleaving implicitly, but the fill pass can produce a same-bucket tail).

`summary()` written to `study_sessions.summary`: `total_items, due_count, weak_count, new_count, learn_count, refresh_count, review_count, duration_minutes, session_mode, primary_learning_unit` (hardcoded `TYPE_PHRASE_CHUNK`).

Also in this class, used by the draft editor: `replacementForDraftItem` and `addSuggestionsForDraft` with `MINIMUM_COMPATIBLE_REPLACEMENT_SCORE = 45`.

### 3b. Runtime — what the learner actually does

`app/Actions/StudySessions/StartStudySessionRuntime.php` (138 lines). Guards: `completed` → `ValidationException` "Completed study sessions cannot be restarted into runtime."; `in_progress` → idempotent no-op. Sets `status = in_progress`, `metadata.runtime_state = 'in_progress'`, `metadata.runtime_started_at`, and preserves `priming_state` if already `started`/`skipped` else forces `'started'`. **Deterministically assigns per item** (this is the only place exercise types are chosen):

`exercise_type`, first match wins:
1. `source_bucket === 'weak'` → `quiz_recall`
2. `item_type === 'sentence_pattern'` → `sentence_building`
3. `source_bucket === 'due'` AND `item_type === 'phrase_chunk'` → `flashcard_review`
4. default → `mixed_review`

`response_mode` (bare literals, not constants): `flashcard_review → 'self_check'`, `quiz_recall → 'free_recall'`, `sentence_building → 'sentence_build'`, default → `'context_recall'`.

`study_mode` from bucket: `new → learn`, `weak → refresh`, else `review`.

`app/Actions/StudySessions/BuildStudySessionRuntimePayload.php` (762 lines) drives `resources/js/pages/study-sessions/runtime.tsx`. Phase machine: `'learning'` (only for `study_mode ∈ {learn, refresh}`, until the learner marks the phase complete) → `'recall'` → `'wrap_up'`. The learning phase renders up to 8 generated steps — `content, definition, meaning, usage_notes, example_sentences, vocabulary_network, memory_support, word_forms` (last is `learn`-mode only) — each `{key, title, description, content, bullets[]}`, with empty steps filtered out. Per-item payload also carries `coach_history` (last 8 coach Q&A for the current item) and `feedback_history` (last 5 prior rubric scores per item, from other sessions), both collapsed by default. `rubric_priority` renders as `{is_active: true, label: 'Returned sooner', reason: 'Recent rubric quality slipped on this item, so it came back early for steadier review.'}`.

### 3c. How a response is "scored" — **the learner self-grades**

`app/Http/Requests/StoreStudySessionResponseRequest.php`: the client submits `outcome` as a required `Rule::in([correct, partial, incorrect])`, plus `definition_response_text` (required, max 1000) and `usage_example_response_text` (required, max 2000). **The outcome that drives all scheduling is a learner self-rating from a three-way radio button.** The AI rubric (§4) produces a 0–100 `overall_score` stored alongside, and it influences *weak-item priority and cooldown exemption* on the **next** composition — but it never overrides the outcome that moved the state.

`app/Actions/StudySessions/CreateStudySessionResponseFeedback.php` (862 lines) runs synchronously inside `completeRuntime` (and via job `GenerateStudySessionResponseFeedback` on queue `study-session-feedback`). `completeRuntime` **requires `responses->count() === items->count()`**, then `rubricSummary()` → `rubricPrioritySummary()` → `UpdateLearnerItemStatesAfterSession` → `BuildLearnerProgressSnapshot` persisted into `learner_profiles.progress_snapshot`.

`rubricScoreTrend(?int $delta)`: `null → 'no_prior_feedback'`, `>= 5 → 'improved'`, `<= -5 → 'declined'`, else `'unchanged'`. `rubricPriorityStatus(?outcome, trend)`: `trend === 'declined' || outcome === incorrect → 'declined_again'`; `outcome === correct → 'recovered'`; else `'still_unstable'`.

### 3d. State transitions and intervals — `app/Actions/StudySessions/UpdateLearnerItemStatesAfterSession.php` (263 lines)

```php
private const MINIMUM_SAFE_MASTERY_REVIEWS = 3;
private const RUBRIC_PRIORITY_RECOVERY_DUE_DAY_BONUS = 1;
private const RUBRIC_PRIORITY_DECLINE_SHORT_LEASH_HOURS = 12;
```

Per response: `firstOrNew(['user_id','learning_item_id'])`, `$timesSeen = max(1, (int) $state->times_seen + 1)`.

**Weak score** (clamped 0..10):
```php
$weakScore = match ($response->outcome) {
    OUTCOME_CORRECT   => max($currentWeakScore - 1, 0),
    OUTCOME_PARTIAL   => min($currentWeakScore + 1, 10),
    OUTCOME_INCORRECT => min($currentWeakScore + 2, 10),
};
return match ($rubricPriorityStatus) {
    'recovered'      => max($weakScore - 1, 0),
    'declined_again' => min($weakScore + 1, 10),
    default => $weakScore,
};
```

**The complete interval logic — this is the entire spaced-repetition system:**
```php
$dueAt = match ($response->outcome) {
    OUTCOME_INCORRECT => $submittedAt->addHours(12),
    OUTCOME_PARTIAL   => $submittedAt->addDay(),
    OUTCOME_CORRECT   => $submittedAt->addDays(match (true) {
        $timesSeen <= 1 => 1,
        $timesSeen <= 3 => 3,
        default         => 7,
    }),
};
return match ($rubricPriorityStatus) {
    'recovered'      => $dueAt->addDays(1),   // RUBRIC_PRIORITY_RECOVERY_DUE_DAY_BONUS
    'declined_again' => $submittedAt->addHours(12), // DECLINE_SHORT_LEASH_HOURS
    default => $dueAt,
};
```

**Answer to "is there any spaced-repetition interval logic at all": there is a three-step fixed ladder and nothing more. 12h / 1d / 1d → 3d → 7d. Maximum interval is 7 days, forever. There is no ease factor, no SM-2, no FSRS, no per-item interval or stability column, no lapse handling, no graduation, no fuzz. The interval is recomputed from scratch every review out of `times_seen` + outcome, so it is memoryless and cannot expand past 7 days no matter how many perfect reviews accumulate.**

**Mastery:**
```php
return $response->outcome === StudySessionResponse::OUTCOME_CORRECT
    && $timesSeen >= self::MINIMUM_SAFE_MASTERY_REVIEWS   // 3
    && $weakScore === 0;
```

`lifecycleState()`: **`mastered` is absorbing/terminal** — once mastered, never demoted, even on a subsequent `incorrect`. Otherwise `shouldMarkMastered` → `mastered`; else `correct` → `reviewed`; else `introduced_at === null ? INTRODUCED : ($state->lifecycle_state ?: INTRODUCED)`. `LIFECYCLE_UNSEEN` is defined but **never assigned by this action** (a state row only exists after a response).

Return payload (persisted into the wrap-up): `updated_items, introduced_items_after_update, reviewed_items_after_update, mastered_items_after_update, weak_items_after_update, due_within_day_count, next_due_at, scheduling_policy => 'm09_minimum_safe_intervals_v1', rubric_priority_policy => 'm14_rubric_priority_follow_through_v1', rubric_priority_recovered_adjustments, rubric_priority_decline_adjustments, lifecycle_policy => 'm13_minimum_safe_state_transitions_v1'`.

### 3e. Priming — `app/Actions/StudySessions/BuildStudySessionPrimingPayload.php` (520 lines)

Fully rule-based, matching the doc's "rule-based is source of truth" rule. Keys: `study_session_id, session_facts, preview_items, supporting_items, weak_area_signal, queue_quality_signal, new_item_signal, rubric_priority_signal, expected_benefits`. `main_topic` = modal non-empty topic, fallback `'General English practice'`. `preview_items` = phrase-first sorted, **take(5)**. `weak_area_signal` includes `dominant_topic`, `items_to_watch_count`, `highlights` (take 3).

`queue_quality_signal` is a genuinely useful editorial linter with real thresholds — `empty_queue` (severity warning), `topic_spread` (distinct topics ≥ 4, or ≥ 3 with modal topic count < ceil(total/2)), `no_phrase_chunks` (0 phrase chunks and ≥ 3 items), `word_heavy_queue` (wordCount ≥ 4 and ≥ 75%), `new_items_dominating` (`newCount > (due+weak) * 2`), `lexical_sibling_crowding` (any lexical family group ≥ 3). Status is `'ready'` or `'review'`; the session can always still start.

`RewriteStudySessionPrimingSummaryWithAi.php` (205 lines) is the optional AI rewrite (see §4).

### 3f. Progress — `app/Actions/LearnerProgress/BuildLearnerProgressSnapshot.php` (258 lines)

Policy `'m11_dashboard_progress_snapshot_v3'`. Keys: `generated_at, tracked_items_count, overdue_count` (`due_at <= now`), `weak_count` (**`weak(2)`, i.e. `weak_score >= 2` — note the composition engine uses the scope default of 1, so "weak" means different things in the dashboard and in the scheduler**), `recently_studied_count` (`last_studied_at >= now - 7 days`, the only day window in the file), `next_due_at`, `history{completed_sessions_count, recent_wrap_up, recent_rubric_trends, recent_sessions}` (latest **3** completed sessions), `signals{overdue, weak, recently_studied}` (each **limit 3**), `policy`.

**There is no streak metric and no mastery percentage in the snapshot.** `lifecycle_state`, mastered counts, and mastery-target state are **not surfaced at all** — despite `lifecycle_state` being the whole point of M13. The dashboard sees raw counts, next due date, and rubric trend aggregates only.

---

## 4. AI layer

**`config/ai.php` is NOT published.** The single source of truth is `config/services.php → ai_enrichment`: `enabled`, `provider: 'ollama'`, `model: qwen3:4b`, `learning_item_provider: 'nvidia'` / `learning_item_driver: 'openai'` / `learning_item_base_url: https://integrate.api.nvidia.com/v1`, `learning_item_model: meta/llama-4-maverick-17b-128e-instruct`, `coach_model: mistralai/mistral-medium-3.5-128b`, `local_coach_model: gemma3:4b`, `coach_fallback_provider: 'ollama'` / `coach_fallback_model: gemma3:4b`, `rubric_*` mirroring `coach_*`, `timeout: env('AI_ENRICHMENT_TIMEOUT', 60)`. The `nvidia` provider **does not exist in config** — each action's `synchronizeProviderKey()` mutates `ai.providers.{provider}.{driver,key,url}` at runtime. (`.env` holds live secrets; only variable names and committed defaults are reported here.)

**`routes/ai.php` contains ZERO HTTP routes** — only `Mcp::local('knowledge-center', ...)` and `Mcp::local('task-tracker', ...)`.

Six classes of model call:

1. **`app/Ai/Agents/LearningItemEnrichmentAgent`** — `HasStructuredOutput`, 17-field JSON schema, **fill-only** (writes a field only if blank), task `learning_item_enrichment_v1`. Budgets in the prompt: 3 examples, up to 4 synonyms/antonyms, up to 3 confusing pairs, up to 5 tags, up to 3 `similar_confusing_items`, up to 3 `practice_prompts`. **No retry, no fallback model.** Throws `RuntimeException('AI enrichment request failed.')` / `UnexpectedValueException('AI enrichment returned an invalid response.')`.
2. **`app/Ai/Agents/LearningItemCoachAgent`** — `#[MaxTokens(400)] #[Temperature(0.2)]`, asks for JSON **in prose, not structured output**, three-layer resilience with raw-text salvage (`extractFirstJsonObject`, `payloadFromLabeledSections`); `fallback_reason ∈ {provider_error, invalid_payload}`; task `learning_item_coach_answer_v2`. Question type is detected **deterministically** by `app/Support/LearningItemCoachQuestionTypeDetector.php` (`sentence_check, synonym_check, naturalness_check, context_or_register, meaning_or_usage`), which drives per-type instructions and a response-shape hint. Caps: 3 examples, 3 synonyms, 2 antonyms, 4 collocations, 2 confusing pairs; `response_preferences.max_answer_words: 80`.
3. **`app/Ai/Agents/StudySessionResponseRubricAgent`** — `#[MaxTokens(700)] #[Temperature(0.1)]`, `HasStructuredOutput`, scores **1–5** on definition/usage/example/grammar plus a `*_reason` each. Prompt explicitly instructs *"Do not change review scheduling or infer durable mastery."* Weighting `{definition: 35, usage: 35, example: 20, grammar: 10}` and **`overall_score` is computed in PHP, not by the model**: `round((definition/5*35)+(usage/5*35)+(example/5*20)+(grammar/5*10))` → 0–100. Deterministic fallback `scoresForOutcome()`: correct `5/5/5/5`, partial `3/3/3/4`, else `1/1/1/3`, recorded as `provider: 'app'`, `model: 'deterministic-rubric-v1'`. Eligibility: `response_mode ∈ {free_recall, context_recall}` or `exercise_type ∈ {quiz_recall, sentence_building, mixed_review}` — so `flashcard_review`/`self_check` items get `not_applicable`.
4. **`app/Ai/Agents/StudySessionPrimingSummaryRewriteAgent`** — 49 lines, one-field schema `ai_summary`, "two or three calm coaching sentences", task `study_session_priming_rewrite_v1`, **no fallback model**. Controller maps failure to 502, unconfigured to 503.
5. **Seven raw-HTTP Ollama enrichment passes** in `app/Console/Commands/EnrichLearningItem*Command.php` that **bypass `laravel/ai` entirely**: `Http::connectTimeout(10)->timeout($timeout)->retry(2, 200, throw: false)->post("{$baseUrl}/api/chat")`, defaults `--model=qwen3:4b --base-url=http://localhost:11434 --timeout=120 --limit=50`. Each enforces an identity check that `item_type`/`content`/`source_label` come back byte-identical. Parsed by `app/Support/OllamaSingleRowResponseParser.php` (192 lines, balanced-brace extraction, modes `direct_object|direct_array|extracted_object|extracted_array`).
6. **Offline eval harness** `app/Actions/AiEvaluation/RunAiEvaluation.php` (652 lines) — calls provider HTTP directly (`ollama_local`, `ollama_cloud`, `gemini_api`, `xai_api`, `openrouter_api`), writes `storage/app/evals/runs/{runId}/{meta.json, *-results.jsonl, failures.jsonl, summary.json}`. `ExportAiEvaluationScoreSheet.php` emits CSVs whose quality columns are **deliberately `null` for a human to fill in** — it is a scoring template, not an automated scorer.

Validation posture: structured output (JSON schema) for enrichment / rubric / priming rewrite; prose-JSON plus salvage for the coach; byte-identity guards plus a strict parser for the raw Ollama passes; content-quality gates in `app/Actions/LearningItems/ValidateGeneratedLearningItemsBatch.php` (see §7). **Every AI path has a deterministic fallback except enrichment and the priming rewrite.** `app/Support/OllamaChatClient.php` is a **14-line empty stub — dead code**.

**Bug:** `app/Providers/AppServiceProvider::register()` calls `$this->app->singleton(TaskTrackerRepository::class)` **with no `use` import**, so it binds the non-existent `App\Providers\TaskTrackerRepository`. The singleton is silently dead.

Jobs (`app/Jobs/`): `GenerateStudySessionResponseFeedback` (queue `study-session-feedback`, tries 2, timeout 90, `WithoutOverlapping(...)->releaseAfter(10)->expireAfter(180)`), `RunLearningItemEnrichmentPass` (queue `ollama-enrichment`, tries 3, timeout 240, `backoff() = [15, 60, 180]`; claims the pass row with a conditional UPDATE then `Artisan::call(... --limit 1)`), `DispatchNextLearningItemEnrichment` (serial driver, tries 1, timeout 60). Horizon's `ollama-enrichment` supervisor is pinned to **1 worker** because, per `documentation/learning item enrichment operations.md`, *"Ollama is reliable for one learning item at a time but unstable under larger queued batches."*

---

## 5. Routes and controllers

`routes/web.php`, `routes/settings.php`, `routes/ai.php` (MCP only). **There is no `routes/api.php`** — "JSON API" behaviour is the same web routes branching on `$request->expectsJson()`. All auth routes come from Fortify (`config/fortify.php`: home `/dashboard`; features registration, resetPasswords, emailVerification, twoFactorAuthentication with confirm + confirmPassword).

**Only 5 real controllers** in `app/Http/Controllers/`: `StudySessionController` (**1514 lines**), `LearningItemController`, `LearningItemExtractionController`, `ContentPanelController`, plus settings controllers. 24 Form Request classes in `app/Http/Requests/`.

Learner-facing routes, all inside `Route::middleware(['auth','verified'])`:

| Method | URI | Name |
|---|---|---|
| GET | `dashboard` | `dashboard` (prop-less `Route::inertia`) |
| GET | `study-guide` | `study-guide` (prop-less `Route::inertia`) |
| POST | `study-sessions/generate` | `study-sessions.store` |
| POST | `study-sessions/{s}/regenerate` | `study-sessions.regenerate` |
| GET | `study-sessions/{s}` | `study-sessions.show` |
| GET | `study-sessions/{s}/priming` | `study-sessions.priming` |
| POST | `study-sessions/{s}/priming/start` \| `/skip` \| `/rewrite` | priming actions |
| PATCH | `study-sessions/{s}` | `study-sessions.update` (edit draft) |
| POST | `study-sessions/{s}/items` | add item to draft |
| POST | `study-sessions/{s}/items/{i}/replace` | replace draft item |
| POST | `study-sessions/{s}/runtime/start` | start runtime |
| GET | `study-sessions/{s}/runtime` | runtime page |
| GET | `study-sessions/{s}/runtime/feedback-status` | poll rubric status |
| POST | `study-sessions/{s}/runtime/learning-phase` | mark learning phase done |
| POST | `study-sessions/{s}/runtime/responses` | submit one response |
| POST | `study-sessions/{s}/runtime/complete` | complete session |
| POST | `learning-items/{i}/coach` | AI coach question |
| POST | `learning-items/{i}/focus-session` | one-item Focus Session |
| POST / DELETE | `learning-items/{i}/mastery-target` | set / clear mastery target |

Content-admin routes: `content-panel.*` (including seeded-library `export` / `export-batch` / `import`, gated by `can:exportSeededLibrary|importSeededLibrary`), `learning-items.*` (create/index/show/edit/store/store-json/update/patch-json/ai-enrichment/destroy), `learning-item-extractions.*` (index/store/show/update).

`focusSession` creates a `StudySession` with `session_mode = MODE_FOCUS`, `duration_minutes = 5`, `composition_policy = 'm15_focus_session_v1'`, `priming_state = 'skipped'`, exactly one item — and **409s if a session is already in progress** (single-active-session invariant, also enforced in `startRuntime`).

**Authorization gap:** every `StudySessionController` method opens with `abort_unless($studySession->user_id === $request->user()->id, 403)` — **there is no `StudySessionPolicy`**. `LearningItemPolicy` does exist: `before()` returns true for `isSystemAdmin()`; `view` = seeded OR owner; `update` = owner && not seeded && not archived.

**Reachable learner flows today:** dashboard → generate session (10/15/20 min, mixed_review only) → priming screen (edit / regenerate / rewrite AI summary / skip) → runtime (learning phase for learn/refresh items, then recall with self-graded outcome + optional coach questions) → wrap-up with rubric summary → progress snapshot on the dashboard. Plus: browse/search the library, create items manually or by JSON paste, paste-text extraction with accept/reject review, per-item AI enrichment, per-item Focus Session, per-item Mastery Target. **`learning-items.index` is a JSON-only endpoint returning `LearningItemResource::collection` — it renders no Inertia page** (there is no `resources/js/pages/learning-items/index.tsx`); the browse UI is `content-panel/index.tsx`.

**Not reachable:** any session mode other than `mixed_review` (blocked by `GenerateStudySessionRequest`), anything capability-based, anything non-English, anything for a second audience.

---

## 6. Frontend

89 files under `resources/js`. **21 pages**, 12,610 lines total:

*Real learner product:* `welcome.tsx` (176), `dashboard.tsx` (**1052**), `study-guide.tsx` (247), `study-sessions/priming.tsx` (**1358**), `study-sessions/runtime.tsx` (**3702 — the largest file in the repo**).
*Admin/content tooling:* `content-panel/index.tsx` (1268), `learning-items/show.tsx` (958), `edit.tsx` (750), `create.tsx` (695), `learning-item-extractions/index.tsx` (521), `show.tsx` (346).
*Settings:* `settings/profile.tsx` (602, hybrid — real learner-profile fields), `security.tsx` (268), `appearance.tsx` (35).
*Untouched Fortify scaffold:* 7 auth pages, 632 lines total.

**≈88% of page code (11,073 / 12,610 lines) is bespoke; pure scaffold ≈7.4%.** This is not a skeleton at the UI layer.

`resources/js/components/learning-items/` contains **exactly one file**, `learning-item-json-panel.tsx` (314). The big custom admin component is one level up: `components/learning-item-admin-sheet.tsx` (**1401 lines, a 28-field flat FormState**).

`components/ui/` = 25 files / 2554 lines of **unmodified shadcn** (tell: 2-space/double-quote formatting vs the app's 4-space/single-quote). Radix packages present: avatar, checkbox, collapsible, dialog, dropdown-menu, label, navigation-menu, select, separator, slot, toggle, toggle-group, tooltip. **Components the app hand-rolls because they were never added: `textarea` (all raw `<textarea>`), `progress` (hand-rolled div pair in runtime), `radio-group` (raw `<input type="radio">` for the Correct/Partial/Incorrect selector — i.e. the single most important control in the product), `tabs`, `table`, `sonner`/`toast`, popover, accordion, switch, alert-dialog, chart.**

Theming: fully wired but entirely starter-kit — `resources/js/hooks/use-appearance.tsx` (115 lines, `Appearance = 'light'|'dark'|'system'`, localStorage + `appearance` cookie, toggles `.dark`), `components/appearance-tabs.tsx`, FOUC guard in `resources/views/app.blade.php`. The **only** CSS file is `resources/css/app.css` and it is **byte-for-byte the default Laravel 12 React starter-kit token file** (neutral grayscale oklch, `--primary: oklch(0.205 0 0)`, `--radius: 0.625rem`, no brand hue). **No semantic learning-domain tokens exist** — nothing for learn/refresh/review, correct/partial/incorrect, weak/overdue; all of that is ad-hoc utility classes scattered through the pages.

**Real shippable bug:** `font-serif` is used for display headings, but only Instrument Sans is loaded and **`--font-serif` is never declared** — those headings silently fall back to the browser default serif.

Branding leaks: `components/app-logo-icon.tsx` is still the default Laravel hexagon SVG; the sidebar `footerNavItems` are literally "Laravel Docs" and "Fortify Docs"; the Inertia progress bar colour is `#4B5563`. Active shell is `layouts/app/app-sidebar-layout.tsx`; `app-header-layout.tsx` and `components/app-header.tsx` (246 lines) are **dead code**.

`data-test="…"` attributes are pervasive (Playwright convention, established in `documentation/chrome devtools element mapping.md`: `data-test` → accessible label → visible text → route/title, and never store Chrome DevTools snapshot `uid` values).

`dashboard.tsx` and `study-guide.tsx` are prop-less `Route::inertia` and are fed entirely by `app/Http/Middleware/HandleInertiaRequests.php` shared props: `auth.user`, `auth.learner_profile`, `flash.{success,error,coach}`, `latestDraftStudySession`, `latestInProgressStudySession`, `dashboardProgressSnapshot`, `learnerLibrarySummary`, `sidebarOpen`. **There is no dedicated progress page** — progress lives inside `dashboard.tsx` and the runtime wrap-up.

---

## 7. Content intake — the exact shape the Python pipeline must emit

Per `documentation/content intake contract.md` and `app/Actions/LearningItems/ImportSeededLearningItems.php`:

**Command:** `php artisan learning-items:import {file?}`. Path is absolute or `base_path`-relative. Default file: `database/seeders/data/learning-items-merged-v3.json`.

**Top level must be a JSON array. A top-level object with a wrapper key is invalid.**

```json
[
  {
    "item_type": "phrase_chunk",          // REQUIRED, exactly one of: phrase_chunk | word | sentence_pattern
    "content": "under pressure",          // REQUIRED, max 5000 chars
    "source_label": "coca-merged-v3",     // REQUIRED, max 255
    "definition": "…",                    // dictionary-like; must NOT equal `meaning`
    "meaning": "…",
    "topic": "workplace",                 // max 255
    "difficulty": "intermediate",         // string label (see conflict below)
    "source_type": "seeded",              // if present MUST be "seeded"
    "usage_notes": "…",                   // single STRING, not an array
    "example_sentences": ["…", "…"],      // array, max 5, each max 1000
    "register": "neutral_general",         // formal_general|formal_academic|neutral_general|informal_conversational|technical
    "memory_hook": "…",
    "learner_tip": "…",
    "metadata": { }                        // object
  }
]
```

**Forbidden key: `owner_user_id`** (`prohibited` in validation). Normalisation on import: `source_type` forced to `'seeded'`, `owner_user_id` forced to `null`, `metadata.primary_learning_unit` defaults to `item_type`, `example_sentences` defaults to `[]`. CSV/TSV are explicitly unsupported.

The importer also accepts and folds the wider lexical set into `metadata.lexical_data`: `synonyms[{word,note}]`, `antonyms[{word,note}]`, `collocations[]`, `confusing_pairs[{word,difference}]`, `word_forms{verb_base, third_person_singular, past_tense, past_participle, present_participle, noun_form}`, `tags[]`, `recommended_supporting_phrase`, `common_contexts[]`. Array caps: 20 entries for tags/common_contexts/collocations/synonyms/antonyms/confusing_pairs; `note` max 1000; `difference` max 2000; 255 for topic/source_label/recommended_supporting_phrase/word-form fields; 100 for difficulty and each tag. Processing: `array_chunk($items, 500)`; `--fast` bulk-`insert()`s only missing rows, otherwise `updateOrCreate` keyed on `{item_type, content, source_type, source_label}` inside a transaction. Returns `{processed_count, inserted_count, updated_count, skipped_existing_count, skipped_duplicate_payload_rows}`. `ExportSeededLearningItems.php` is the exact inverse — use it to generate a golden sample.

**Two ambiguities to resolve before the Python side commits:** (a) `difficulty` is a **string** (`"intermediate"`) in the canonical example and in shipped code, but **integer 1–5** in `documentation/v2/content-pipeline.md`; (b) `register` appears both top-level and inside `metadata` in different docs.

**Quality gates the pipeline must pass** — `app/Actions/LearningItems/ValidateGeneratedLearningItemsBatch.php` (188 lines) is a real anti-slop filter that throws `ValidationException` keyed `items.{i}.{field}`. It rejects: `usage_notes` that is not a string; `meaning` identical to `definition` after punctuation-stripped lowercasing; and a blocklist of template shells — examples `/\bIn this lesson\b/i`, `/\bUse the definition and usage notes\b/i`, `/\bThe word\b.+\bis used in many contexts\b/i`, `/\bbecame the focus of the discussion\b/i`, `/\bWe learned more about\b.+\bin class today\b/i`, plus content-interpolated `He spoke X during the interview.`, `The team worked X to finish on time.`, `It was a(n) X decision under pressure.`, `Her explanation was clear and X.`; definitions `/^A common (noun|verb|adjective|adverb|phrase|sentence pattern)\s*:/i`, `/^An? … used in English\.?$/i`, `/^Used to describe something with a quality related to\b/i`; meanings `/\bused in many contexts\b/i`, `/\ba word in English\b/i`, `/^It means X\.?$/i`; usage notes `/\bused in many contexts\b/i`, `/\bUse this word when appropriate\b/i`, `/^Use 'X' in many contexts\.?$/i`.

`documentation/content generation standard.md` adds: canonical **20-field** set, 2–3 example sentences preferred, batch size **100–300**, 10 hard quality rules including *"no output accepted purely because it is structurally valid JSON"* and *"The quality bar is learner value, not field completion."*

**Two other intake paths:**
- **Manual:** `GET /learning-items/create` → `POST /learning-items`; `source_type` allowed `manual|extracted` only; UI-only fields `example_sentences_text` (newline-split) and `metadata_tags` (comma-split). Also `POST /learning-items/json` and `PATCH /learning-items/{i}/json` via `ParseLearningItemJsonInput` → `ValidateLearningItemJson` → `NormalizeLearningItemJsonPayload` (`ALLOWED_INBOUND_KEYS` = the 21 keys above; `FORBIDDEN_INBOUND_KEYS` = `source_type, owner_user_id`; `SEEDED_METADATA_KEYS_TO_STRIP` = `merged_library, coca_rank, coca_frequency, import_batch_id, import_source, repair_pass, repair_source`; duplicate key = `mb_strtolower(trim(type))|mb_strtolower(trim(content))`).
- **Paste-text extraction (heuristic, NOT AI):** `POST /learning-item-extractions` with `source_text` required. `app/Actions/LearningItems/ExtractPastedLearningItemCandidates.php` (239 lines) uses preposition anchors (`on, in, at, for, with, from, under, over, by, about, after, before`), tries phrase windows of length **[5,4,3,2]** (valid if 2–5 tokens, ≥2 non-stopwords, no second anchor inside, last token not a stopword), plus significant words (length ≥ 5, non-stopword, **take(5)**), plus sentence-pattern triggers (`could you` / `would you` / `would rather`). Staged as `review_status: pending`, reviewed via `PATCH /learning-item-extractions/{id}` with `action: accept|reject`.

**Enrichment operations** (`documentation/learning item enrichment operations.md`) — 7 sequential passes: `definition_meaning` → `topic_difficulty_usage_notes` → `example_sentences_synonyms` → `antonyms_collocations` → `confusing_pairs_word_forms_register` → `learner_tip_memory_hook_tags` → `supporting_phrase_common_contexts`. Commands `learning-items:enrich-all` / `:retry-enrichment` / `:enrich-status`. **Hard data boundary: records 1..7000 were manually enriched with ChatGPT and must remain untouched**; the normal invocation is `--starting-id=7101 --mode=queue --resume`. Pass statuses include derived `stale_running` / `stale_queued` via `LearningItemEnrichmentPass::displayStatus()`, `--stale-minutes` default 30.

**Actual content on disk — this is important for planning.** `database/seeders/data/learning-items-merged-v3.json` is **28 MB, 17,631 items, and every single one is `item_type: "word"` (0 phrase_chunk, 0 sentence_pattern)**, with a generic repeated `usage_notes` template string. `merged-v1` (19 MB / 17,679) and `merged-v2` (24 MB / 17,679) also exist. `storage/app/batches/` holds **126 MB** across 556 enrichment intermediates. So the phrase-first product thesis — and every phrase-first ranking bonus in the composition engine — currently has **zero content to work with**. `DatabaseSeeder` calls only `DemoAppSeeder`; `LearningItemSeeder` is **not wired in**, and the file it reads (`database/seeders/data/learning-items.json`) has only **4 items**. The real library is reachable only via `php artisan learning-items:import`.

---

## 8. MCP / Knowledge Center / Task Tracker

**Unambiguously developer tooling, not product features.** All three are markdown-file-backed (`docs/knowledge`, `docs/work`), exposed over **stdio only** via `php artisan mcp:start <handle>`, registered in `routes/ai.php`. **16 MCP tools:**

- `knowledge-center` (5): `list-knowledge-documents`, `search-knowledge`, `upsert-knowledge-document`, `record-knowledge-discovery`, `validate-knowledge-center`.
- `task-tracker` (11): `list-milestones`, `create-milestone`, `list-tasks`, `create-task`, `move-task-to-milestone`, `update-task-status`, `append-task-progress`, `record-task-blocker`, `next-task`, `search-task-tracker`, `validate-task-tracker`.

`app/TaskTracker/TaskTrackerRepository.php` is ~1490 lines, yet **`docs/work/tasks/` contains zero actual tasks** — the tracker is built and unused. `app/KnowledgeCenter` holds exactly one recorded discovery (§1). Combined, **53 of 337 Feature test cases (~16%) test developer tooling**, and the `TaskTrackerRepository` singleton binding is broken (§4). If a redesign needs to cut scope, this subsystem is the clearest candidate.

---

## 9. Testing and quality gates

**Counts:** `tests/Unit` 12 files / 32 cases; `tests/Feature` 73 / 337; `tests/Browser` 17 / 35 — **102 files, 404 cases**. 12 factories cover the full domain.

`composer check` (from `composer.json`):
```
bash -lc 'status=0; vendor/bin/phpstan analyse app database || status=1; \
  vendor/bin/pint app tests database || status=1; \
  vendor/bin/pest --compact --exclude-group=browser --parallel || status=1; \
  npm run types:check || status=1; npm run lint || status=1; npm run format || status=1; exit $status'
```
`composer browser-check` stashes `public/hot`, then `npm run build && ./vendor/bin/pest tests/Browser --group=browser`. Also defined: `rector-dryrun`, `rector`, `ide:helper`, and `ci:check` (defined but unused).

**Quality-gate defects, all real:**
- **There is no `phpstan.neon` anywhere outside `vendor/`.** So step 1 of `composer check` runs with no level configured and **Larastan's extension never loads** — the static-analysis gate is largely decorative.
- Steps 2, 5 and 6 (`pint`, `lint`, `format`) run in **write mode, not check mode**, so they fix files rather than failing the build.
- CI (`.github/workflows/tests.yml`) runs **only `./vendor/bin/pest`** — no phpstan, no `tsc`, no rector, no `--exclude-group=browser`, and **no `npx playwright install`**. `lint.yml` runs all three formatters in write mode with the auto-commit step commented out, so it **cannot fail on formatting**.
- Zero coverage enforcement despite xdebug being installed. **No numeric coverage target exists anywhere in the docs.**
- `rector.php` imports `Spatie\Ray\Rector\RemoveRayCallRector` but `spatie/ray` is not a dependency.
- `tests/Pest.php` applies `RefreshDatabase` to **Unit** tests too, and contains deep coupling to `laravel/mcp` internals in helpers such as `readKnowledgeCenterDocument`.
- `tests/Feature/MergedLearningItemsDatasetTest.php` **re-parses the 28 MB JSON file in 7 places on every `composer check`.**
- `DemoAppSeeder` commits hardcoded `password` credentials for `admin@example.com` (is_system_admin true) and `demo.learner@example.com`.

**What the testing standard demands** (`documentation/testing and verification standard.md`, 956 lines): five layers (unit / feature — *"the default testing style for most backend work"* / integration / browser — *"selective not default"* / content-generation verification §5.5 plus manual verification); §8 a required-by-change-type matrix; §18 four Definition-of-Done checklists (Backend, UI, Refactor, Data-model); §15 an **eleven-field truthful report contract** (Summary, Files changed, MCP availability, Verification outputs, Manual verification highlights, Acceptance checklist, Remaining risks, Next milestone recommendation, Confidence statement, Candidate git commit titles, Commit body summary); §20 *"no agent may claim verification that was not actually run."* The doc itself has structural defects: missing §12, missing §4.3, duplicated §5.5, §20 skips rule 8, and §17.2's naming convention doesn't match the repo's actual Pest prose-string style.

---

## Build-maturity assessment

**This is a real, coherent, single-audience product — roughly 70–75% real product and 25–30% skeleton — but it is a narrow product built deep, and the depth is in the wrong places for the redesign you are planning.**

Genuinely mature and worth preserving:
- The **app-owns-state architecture** is real and consistently enforced. Every AI call is advisory; every AI path except enrichment and the priming rewrite has a deterministic fallback; the rubric prompt literally forbids the model from touching scheduling.
- The **write path is well-factored**: 30+ single-purpose Action classes, 24 Form Requests, transactional controllers, full provider/model/fallback/cost telemetry on every AI record.
- The **UI is not a scaffold** — 11,073 lines of bespoke page code, a 3,702-line runtime, a 1,358-line priming screen, and a genuinely thoughtful `queue_quality_signal` linter.
- **Content ingestion, enrichment orchestration, and anti-slop validation are the most production-ready subsystems in the repo** — the enrichment-pass state machine with stale detection, serial queue driver, byte-identity guards and template blocklists is real operational engineering.

Skeleton or hollow:
- **The learning science is the thinnest layer in the entire codebase.** Scheduling is ~60 lines of `match` statements. The 2,023-line `ComposeStudySession` optimises *content coherence* (topic lanes, curriculum clusters, lexical-sibling avoidance) with real care, and spends almost nothing on *memory*.
- **v2 is 100% documentation, 0% code** (grep-verified).
- **The seeded library is 17,631 items that are all `word`** — the phrase-first thesis has no content behind it, and every phrase-first bonus in the ranker is currently dead weight.
- `docs/adr/` has one 3-line ADR; `docs/work/tasks/` is empty; `milestone.md` is behind the code by three policy generations.
- Quality gates look strict and are substantially non-functional (no `phpstan.neon`, write-mode formatters, CI runs Pest only).

---

## Top 8 things missing between today's code and a multi-audience, learning-science-driven study app

1. **A real spaced-repetition scheduler.** Today: 12h / 1d / {1d, 3d, 7d} recomputed from `times_seen` every time, capped at 7 days forever, no ease factor, no stability, no lapse handling, `mastered` absorbing. This cannot produce long-term retention and cannot express per-learner difficulty. You need per-item interval/stability/difficulty columns on `learner_item_states` and an explicit algorithm (FSRS or SM-2-with-fuzz), plus a demotion path out of `mastered`. This is the single highest-leverage change and it is a small, well-isolated diff (`UpdateLearnerItemStatesAfterSession.php` plus one migration).
2. **Objective response scoring.** The outcome that drives all state transitions is a **learner self-graded three-way radio button**. The AI rubric exists, produces a good 0–100 score, and is explicitly forbidden from touching scheduling. For children doing maths, and for exam prep, self-grading is not viable — you need deterministic checkers (exact/numeric/pattern match) as the primary signal, with the RAG-Prototype honesty-gate discipline from `docs/knowledge` as the model.
3. **The capability/domain-adapter abstraction — designed, unbuilt, and under-specified.** `documentation/v2/` has zero code behind it, and its central formula (`selection_score = due_weight + weak_weight + capability_gap_weight + novelty_weight - repetition_penalty - overload_penalty`) has **no coefficients and no normalisation**. Multi-audience is impossible without this, and the spec is not yet implementable. Note also that `documentation/v2/math-domain-adapter.md` contradicts `session-engine.md` on whether all 6 capabilities appear in every session.
4. **Non-English, non-vocabulary content has no home in the schema.** `learning_items` is a vocabulary table: `item_type ∈ {phrase_chunk, word, sentence_pattern}`, `content`/`definition`/`usage_notes`/`example_sentences`, and everything rich buried in `metadata.lexical_data`. There is no concept/skill entity, no prerequisite graph, no problem/answer representation, no LaTeX, no image. Maths and reading need either a polymorphic item model or a sibling table.
5. **Children as an audience are entirely absent — from code AND from docs.** No age banding, no reading-level model, no parent/guardian account or oversight surface, no COPPA-style consent, no simplified UI mode, no session-length adaptation for shorter attention. `learner_profiles.age_group` exists as a 32-char string and nothing reads it for behaviour. And `documentation/requirements.md` names generalisation as an explicit **non-goal** in three places — that contradiction needs an ADR before any code moves.
6. **Session shape is hard-locked to one mode and three durations.** `GenerateStudySessionRequest` allows `duration_minutes ∈ [10,15,20]` and `session_mode ∈ [mixed_review]` only; `targetItemCount` is `{6, 8, 10}`; four exercise types are assigned by a 4-branch `if` in `StartStudySessionRuntime`; `summary.primary_learning_unit` is hardcoded `phrase_chunk`. Every one of these is a hardcoded English-vocabulary assumption on the critical path.
7. **Content supply is the binding constraint, and the contract has unresolved conflicts.** The importer is solid, but: the 17,631-item library is 100% `word`, the manual 1–7000 enrichment boundary is a fragile hand-maintained invariant, `difficulty` is string-vs-integer between the shipped contract and `documentation/v2/content-pipeline.md`, and `register` is specified in two places. Freeze the contract (ideally as a versioned JSON Schema generated from `ExportSeededLearningItems`) before the Python pipeline scales.
8. **Progress, mastery visibility, and quality gates are all hollow enough to hide regressions.** `BuildLearnerProgressSnapshot` exposes no streak, no mastery percentage, and **never surfaces `lifecycle_state` at all** despite M13 existing to create it; "weak" means `>= 2` in the dashboard and `>= 1` in the scheduler; there is no dedicated progress page. Meanwhile `composer check` runs phpstan with **no `phpstan.neon`**, three of its six steps are write-mode, and CI runs Pest alone — so a scheduling-algorithm rewrite would land with far less safety net than the 404-test count suggests. Also fix, cheaply, while in there: the dead `TaskTrackerRepository` singleton binding in `AppServiceProvider::register()`, the undeclared `--font-serif`, the Laravel/Fortify branding leaks, and the 28 MB JSON re-parsed 7× per test run.
