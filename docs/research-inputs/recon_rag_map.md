> **NONCANONICAL RESEARCH INPUT.** This document is a dated observation or synthesis,
> not a decision. It does not adopt anything. Only explicitly accepted ADR and plan
> decisions are authoritative — see `docs/research-inputs/README.md` and
> `docs/research-rule-classification.md`.
>
> Captured 2026-07-26 · RAG `296d6b5` · Ela `da188c5`

# Learning-Science Map — `RAG Prototype`

Repo root (device): `/sessions/rcw-01avnwvlp6hkenjdevedcs5x/mnt/RAG Prototype`. 38,031 LOC of top-level Python + 4,632 LOC of TypeScript/TSX frontend. Audited via device shell; four sub-audits ran in parallel and are reconciled here. Confidence caveats are flagged inline.

**Headline:** this is a *content-generation and grounding-verification* system with world-class provenance discipline and almost no learner model. Exactly one file (`spaced_repetition.py`, 133 LOC, 6 days old) constitutes the entire learner-facing pedagogy, it covers maths only, and it has 2 rows of state in the live DB. Pedagogical *quality* is asserted in markdown prompts the pipeline cannot read, and gated by exactly one continuous check (`reading_level`) which is inert for the PTE domain.

---

## 1. The output data contract

Two separate contracts, two schema versions, no shared model.

### 1a. Grounded base — `book_learning_materials_contract.py` (1,134 LOC)

`BOOK_LEARNING_MATERIALS_SCHEMA_VERSION = "book_learning_materials.v2"`; audit envelope `book_learning_materials_contract_audit.v1`. Validation is one class, `ContractValidator`, entry point `validate_book_contract(...)`, 26 error codes.

**Top level** (all required, type-checked not just presence-checked — a comment records that `learning_materials` arriving as a string once skipped *all* content validation and still returned PASS):
```
schema_version            == "book_learning_materials.v2"
book        {slug, title, source_pdf}
generation  {backend, model, generated_at, pipeline_version == schema_version}
learning_materials {...}
source_chunks  []
audit       {}
```

**`learning_materials` — the material-type vocabulary:**
```
book_overview          GroundedContent      kinds{source_summary}
audience              [GroundedContent]     optional
usage_instructions    [GroundedContent]     optional
study_plan            [{focus: GC, activities: [GC]}]        kinds{study_plan}
global_key_terms      [{term: str, meaning: GC}]             kinds{definition}
final_review          {summary: GC, questions: [{question: GC, answer: GC}]}
chapters              [Chapter]             REQUIRED array
```

**`Chapter`** — `chapter_number` (positive int, unique), `chapter_title` (non-empty str), `source_chunk_ids`, then nine material types:

| field | shape | allowed `claim_kind` | required? |
|---|---|---|---|
| `estimated_study_time` | GC | `study_plan` | – |
| `chapter_summary` | GC | `source_summary` | – |
| `learning_objectives` | [GC] | `learning_objective` | **required** |
| `key_terms` | [{`term`, `meaning`:GC}] | `definition` | – |
| `core_lessons` | [{`title`, `explanation`:GC}] | `source_summary`/`official_rule`/`task_format`/`strategy`/`factual_explanation`/`pronunciation_rule`/`grammar_rule` | – |
| `worked_examples` | [{`title`, `example`:GC, `explanation`:GC}] | `pedagogical_example` / (expl: strategy, factual_explanation, official_rule, task_format, pronunciation_rule, grammar_rule) | – |
| `common_misconceptions` | [{`misconception`:GC, `correction`:GC}] | `misconception_statement` / `misconception_correction` | – |
| `practice_questions` | [{`question`:GC, `answer`:GC}] | `practice_question` / `practice_answer` | – |
| `review_checklist` | [GC] | `self_assessment` | **required** |

**`GroundedContent` — the atom.** `GROUNDED_CONTENT_FIELDS` are all seven mandatory (a missing one is `INVALID_GROUNDED_CONTENT_SHAPE`): `text`, `claim_kind`, `origin`, `source_chunk_ids`, `grounded_in_source_chunk_ids`, `evidence_spans`, `reason`.

**Enums:**
- `ORIGINS` (3): `source_grounded`, `pedagogical_generation`, `insufficient_source_evidence`
- `CLAIM_KINDS` (18): `source_summary, learning_objective, definition, official_rule, task_format, strategy, factual_explanation, pronunciation_rule, grammar_rule, pedagogical_example, misconception_statement, misconception_correction, practice_question, practice_answer, learner_instruction, self_assessment, study_plan, other`
- `HIGH_RISK_CLAIM_KINDS` (4): `official_rule, task_format, pronunciation_rule, grammar_rule` — these **may not** use `pedagogical_generation`, and when `source_grounded` they **must** carry ≥1 `evidence_span`.
- `PEDAGOGICAL_GENERATION_ALLOWED_KINDS` (7): `pedagogical_example, practice_question, practice_answer, learner_instruction, self_assessment, study_plan, misconception_statement` — the last with an explicit rationale: "A misconception names a false belief, so it is generated, not grounded: the source states the truth and never the error."

**Origin×field cross-rules** (`INVALID_ORIGIN_FIELD_COMBINATION`): `source_grounded` needs non-empty `text` + ≥1 `source_chunk_ids`, forbids `grounded_in_source_chunk_ids`, `reason` must be null; `pedagogical_generation` needs `text`, forbids `source_chunk_ids` *and* `evidence_spans`, `reason` null; `insufficient_source_evidence` requires `text` to be **null** and `reason` non-empty. Chapter-scoped grounded content must carry local citations (`INHERITED_CITATION_NOT_SUPPORTED`).

**`evidence_spans`** = `[{node_id, quote}]`. Quote must be 4–80 words, normalize-exact-substring of the clean chunk text (`EVIDENCE_SPAN_QUOTE_NOT_FOUND`), `node_id` must appear in `source_chunk_ids`, no duplicates. This is the strongest thing in the codebase.

**Audit summary fields:** `grounded_content_count`, `source_grounded_count`, `pedagogical_generation_count`, `insufficient_source_evidence_count`, `high_risk_claim_count`, `high_risk_verified_span_count`, `verified_evidence_span_count`, `unique_referenced_source_chunk_count`, `invalid_claim_count`, `claims_by_kind`, `claims_by_origin`, `errors_by_code`.

### 1b. Enrichment (teaching layer) — schema hardcoded in `enrich_lessons._SCHEMA_CONTRACT`

`ENRICHMENT_SCHEMA_VERSION = "pte_lesson_enrichment.v1"` — **still PTE-named**, and the maths book must claim it. 15 required top-level keys:
```
overview {what_it_is, format_facts[{...,value}], scoring_factors[{name, what_it_measures}], critical_rules[]}
learning_goals []                        <- REQUIRED non-empty
core_method {name, summary, steps[{step, detail}], formula}
techniques [{name, purpose, how_to, example, why_it_matters, common_error}]   <- REQUIRED non-empty
worked_examples [{title, input, decoding, plan, model_answer, annotations}]   <- REQUIRED non-empty
useful_language [{category, items[{item, when_to_use}]}]                      optional
common_mistakes [{mistake, why_it_hurts, fix}]                                <- REQUIRED non-empty
practice_plan {time_budget, drills, routine}
mastery_checklist []                                                          <- REQUIRED non-empty
strategy_notes                                                               optional
metadata {difficulty, estimated_study_time, tags, provenance_note}
+ task_type, modality, lesson_title, source_label
```
`modality` enum: `writing|speaking|reading|listening|integrated` — language-skill-oriented; the maths pack works around it with `"modality is 'reading' for a maths lesson unless the lesson is clearly oral"`. `overview.scoring_factors` and `strategy_notes` are exam vestiges; maths fills the former with `[{"name":"Correct answer","what_it_measures":"Whether the arithmetic is right"}]`.

`REQUIRED_NONEMPTY_LISTS` is a *pedagogy decision made by frontend rendering*: `useful_language` and `strategy_notes` are optional "because CoachView gracefully hides them".

**No grounding at all in the enrichment layer** — no `origin`, no `evidence_spans`, no claim kinds. The provenance discipline of 1a evaporates in the layer that actually teaches.

### 1c. `evaluation_contract.py` (126 LOC)
`Verdict(str,Enum)` = `PASS="pass"` / `FIX="fix"` / `ESCALATE="escalate"`. `Finding{summary, detail="", evidence="", fixable=True}`. `EvaluatorResult{evaluator, verdict, findings[], healthy=True, health_note="", advisory={}}`. `verdict_of(findings,*,healthy)`: any `not fixable`→ESCALATE; any findings→FIX; else PASS **only if healthy** else ESCALATE. `combine(results)` → `{verdict, accepted, evaluators_run, unhealthy_evaluators, results, next_action}`. The PASS guidance string is honest: *"no known defect was found — it does not certify the lesson is excellent."*

---

## 2. Practice item types

**None of the ten are grounded in book content.** Maths synthesises parametrically from a seeded RNG; PTE synthesises freely from model prompts. This contradicts the pipeline's stated purpose and is the sharpest gap.

| File | Item discriminator | Key fields | Grading | Audience |
|---|---|---|---|---|
| `math_practice_items.py` | *none* — `"skill"` is the discriminator (`times_table, add_fractions, subtract_fractions, fraction_times_whole, fraction_times_fraction, fraction_div_whole`) | `id, skill, skill_title, capability, prompt, prompt_inline, answer_num/_den/_tex/_plain, answer_is_reduced` | **100% deterministic.** `check_answer` → `{correct, equal, not_simplest, parsed, answer_tex, answer_plain, message}`; exact `Fraction`; `correct = equal and simplest` | Yr5 maths |
| `math_reasoning_items.py` | `"kind": "reasoning"` | `+ question, working_tokens, working_min, question_values, rubric[3], model_answer` | **Deterministic** `check_working` with a copy-the-question-back defence (a value token counts only if it does *not* appear in the question). Declares `ADVISORY_TRAIT_MAX = {explains_why:3, clear_steps:3, maths_language:2}` (total 8) | Yr5 maths |
| `reading_mcq_items.py` | `"task_type":"reading_multiple_choice"` + `"mode": single\|multiple` | `id, mode, task_type, topic, title, passage, word_count, question, skill, options[{key,text}], correct[], rationale{per-key}, max_score` | **Blind-solve key verification**: `SOLVER_RUNS=3, SOLVER_AGREEMENT=3` unanimous at temp 0.3/0.5/0.7. `score_answer` deterministic PTE scoring (`max(0, hits-wrong)`). Rationale required for **every** option | **PTE** |
| `swt_passages.py` | none | `topic, title, passage, word_count, time_minutes, summary_word_range, central_claim` | generator only; `contract_validate` (180–300 words, ≥4 sentences, no bullets) → model `semantic_audit` → dedup | **PTE** (Summarize Written Text) |
| `essay_prompts.py` | `"type"` ∈ `agree_disagree, advantages_disadvantages, problem_solution, positive_negative, discuss_two_views` | `type, topic, statement, directive, instruction, time_minutes, word_range` | `DIRECTIVE_RULES` = per-type lambdas asserting the directive text matches the declared type | **PTE** |
| `describe_image_items.py` | `"chart_type"` ∈ `bar,line,pie` | `id, chart_type, title, subject, x_label, y_label, unit, points[{label,value}], facts[{key,importance,text}], svg, prep_seconds, speak_seconds` | **Computed ground truth**: model invents only the numbers; `compute_facts` and `render_svg` both derive from them, so image and fact list cannot disagree. `importance` ∈ `essential\|supporting` | **PTE** |
| `math_reasoning_feedback.py` | – | `traits[{name,score,max,evidence,fix,advisory:True}], advisory_total, advisory_max, strength, next_step, coach_note, advisory:True, written_by:"model"` | **LLM coach, explicitly advisory.** Comment: *"`written_by`, not `scored_by`: this text scores nothing."* Never enters `raw_total`, never reaches the scheduler | Yr5 maths |
| `essay_feedback.py` | – | `word_count, gating_applied, traits[7], raw_total(0-26), max_raw_total, errors[≤25 {type,wrong,correct}], top_priorities[1-3], one_line_verdict, scored_by` | **Model judge + code-owned trait.** `TRAIT_MAX = {content:6, form:2, development_structure_coherence:6, grammar:2, general_linguistic_range:6, vocabulary_range:2, spelling:2}`; `CODE_SCORED_TRAITS={"form"}`; `form_score()` pure code; Content 0 or Form 0 → all traits 0 | **PTE** |
| `swt_feedback.py` | – | same shape, 4 traits | `TRAIT_MAX = {content:4, form:1, grammar:2, vocabulary:2}`, `MAX_RAW_TOTAL=9`. Prompt carries a "NEVER SUGGEST SPLITTING THE SENTENCE" rule because that advice would score 0 for Form | **PTE** |
| `describe_image_feedback.py` | – | `content_score(0-6), band_reason, facts[{key,covered∈yes/partial/no,note}], structure{overview,key_features,relationships,closing}, inaccuracies, coverage{essential_covered/...}, accuracy, not_scored:["Oral Fluency","Pronunciation"]` | Single-trait judge + **deterministic numeric-accuracy check** (`allowed_numbers`, `_stated_tolerance` inferring ±slack from stated precision, `check_numbers`). Band rule: *"A response that only recites numbers cannot score above 4"* | **PTE** |

**Cross-cutting:**
- **No shared helper module.** One cross-module import in the whole set (`math_reasoning_feedback` ← `math_reasoning_items`). `_chat`, `extract_json`, `_FENCE_RE`, `_slug`, `count_words`, the Ollama constants (`OLLAMA_URL="https://ollama.com/api/chat"`, `DEFAULT_MODEL="gpt-oss:120b"`) and the `_reconcile` trust boundary are each duplicated 4–10×.
- **No difficulty, no Bloom/DOK, no IRT.** Repo-wide grep for `bloom|cognitive_level|difficulty|dok` finds zero hits in any generator; `metadata.difficulty` in enrichment is unvalidated free text.
- **Four incompatible tagging vocabularies:** maths `capability` ∈ `recall|application|reasoning|communication` (the only cognitive axis anywhere); maths `skill` (9 slugs); reading `skill` ∈ free-text `main idea|detail|inference|author's purpose|tone`; describe-image `importance`. **Nothing maps to a learning objective, syllabus outcome, or book section id.**
- **Distractor rationale exists only on reading MCQ**, and is contract-required for every option.
- **`test_grader_agreement.py`** (357 LOC, real model calls, not in regression) is **not** human inter-rater agreement — it measures DISCRIMINATION / PLANTED DEFECTS / GATING / REPEATABILITY against `grader_agreement_corpus.py` ("the corpus IS the truth"): `PLANTED_MISSPELLINGS`, `PLANTED_WRONG_NUMBERS=[9400,850,5100,3300]`, essays levelled 3/2/1/0 on *argument quality only*. Repeatability tolerances: essay range ≤6/26, SWT ≤3/9, DI ≤2/6. Failure banner: *"These scores are shown to learners as marks. They must not be shown while this fails."*
- **`test_scoring_disclosure.py`** (162 LOC, offline) asserts every payload carries `scored_by`, that legacy rows are back-filled from `task_type`, and that legacy Form deliberately stays `"code"` — *"back-filling it as an AI judgement would be a fresh untruth told to fix an old silence."*

---

## 3. Spaced repetition — `spaced_repetition.py` (133 LOC)

**Leitner-style fixed ladder. Not SM-2 — no ease factor, no graded response.**

```python
INTERVALS = [1*MINUTE, 10*MINUTE, 1*DAY, 3*DAY, 7*DAY, 16*DAY]   # index = new level
MASTERY_LEVEL = len(INTERVALS)   # == 6
MASTERY_REVIEW = 60*DAY
```

`ItemState`: `item_id, level=0, due_at=None, introduced_at=None, last_studied_at=None, times_seen=0, times_correct=0, streak=0, mastered_at=None`; properties `is_new` (`introduced_at is None`), `is_mastered`, `is_due(now)`.

`update(state, correct: bool, now: float)` — **boolean only, no grade 0–5, no partial credit**:
- correct → `times_correct+=1`, `streak+=1`, `level = min(level+1, 6)`; at level 6 → `mastered_at`, `due_at = now + 60d`; else `due_at = now + INTERVALS[level]`
- wrong → `streak=0`, `level = max(0, level-1)`, `mastered_at = None` (*"a lapse must be re-earned"*), `due_at = now + INTERVALS[0]` (1 minute)

`pick_next(states, all_item_ids, now, *, avoid)` → `(item_id|None, reason)` with reason ∈ `"due" | "new" | "review" | "all_mastered"`:
1. **due** — not mastered, sorted by `(level, due_at, id)` → weakest, most overdue first
2. **new** — bank order preserved ("bank order is meaningful (interleaves skills already)")
3. **review** — soonest-due unmastered, "so a sitting never dead-ends"
`avoid` (the item just answered) is skipped unless it would empty the pool.

`summary(...)` → `{total, mastered, due, new, in_progress}`.

`now` is always injected, never read from the clock. `test_spaced_repetition.py` (11 assertion groups against `T0=1_000_000.0`) pins: interval progression, level drop, streak reset, mastery-by-climbing-every-box, lapse un-masters, the three-tier selection priority, avoid semantics, all-mastered, determinism, summary counts.

**Limitations (mine, not the module's):**
- Boolean correctness only — the four rubric-scored PTE task types produce `raw_total`/`max_raw_total` that the scheduler structurally cannot consume.
- Mastery = 6 consecutive correct at ever-widening gaps, with **no minimum retention interval** — the test itself masters an item in 6 answers by advancing the clock; a learner answering 6 times in one sitting climbs 1min→10min→1d→3d→7d→16d, so mastery genuinely requires ~27 days elapsed. That is a reasonable accident, not a designed retention criterion.
- No item difficulty, no ease factor, no fuzz/jitter (all items introduced together will come due together), no daily new-item cap, no session length concept, no forgetting curve, no lapse counter, no leech handling.
- One flat namespace per learner: `math-practice-next` and `math-reasoning-next` **share the same `math_item_states` table**, and `progress.total` is computed against only the calling bank's ids.
- Item identity is a bare string with no FK — regenerating `math_practice_items.json` with different ids orphans all state.
- The module docstring is candid: *"intentionally simple and defensible over a clever ease-factor scheme; the point of the first slice is a correct, honest, deterministic loop."*

---

## 4. Enrichment and domain packs

**Two unrelated "domain pack" concepts with disjoint field sets, and nothing reconciles them.**

### 4a. Python pack — `domain_packs.DomainPack` (frozen dataclass, 12 fields, **4 never read**)

| field | read by | note |
|---|---|---|
| `slug` | `enrich_lessons` (paths, `source_label` prefix) | |
| `title` | `enrich_lessons`, `build_math_grounded_base` | |
| `audience` | **nobody** | dead — the real audience reaches the model via markdown `{{AUDIENCE}}` |
| `ground_truth` | **nobody** | dead |
| `evaluators` | **nobody** | dead, *and already inconsistent with reality* — neither pack lists `worked_example_count` or `method_consistency` |
| `reading_grade_max` | `pipeline_evaluators._reading_findings` | pte `None`, math5a `6.0` |
| `min_worked_examples` | `_example_count_findings` | pte 3, math5a 4 |
| `task_type_examples` | `_SCHEMA_CONTRACT` substitution | |
| `payload_note` | `_SCHEMA_CONTRACT` substitution | the free-text escape hatch doing most of the real per-domain work |
| `base_file`, `enrich_file` | `base_path(n)`, `enrich_path(n)` | |
| `notes` | **nobody** | dead |

`REGISTRY` = exactly two packs: **`"pte"`** (PTE Academic) and **`"math5a"`** (Singapore Math Primary Mathematics 5A). `DEFAULT_SLUG = "pte"`.

### 4b. Markdown pack — `docs/enrichment-domain-<slug>.md`, 10 slots
`{{APP_NAME}} {{SUBJECT}} {{DOMAIN_EXPERT}} {{AUDIENCE}} {{TASK_TYPE_LIST}} {{DOMAIN}} {{ADDABLE_FACTS}} {{TASK_TYPE_EXAMPLES}} {{TASK_TYPE_ADAPTATION}} {{DOMAIN_EXAMPLE}}`, parsed by `render_enrichment_prompt.slots_for()`. Only `{{TASK_TYPE_EXAMPLES}}` overlaps the Python pack, stored independently, never cross-checked.

### 4c. Runtime selection — three mechanisms
1. CLI `--book`, `choices=sorted(domain_packs.REGISTRY)`
2. `domain_packs.slug_of(doc)` — prefers `doc["domain"]`, then `doc["book_slug"]`, then parses `source_label` (`"pte:ch07"`), **else silently falls back to `"pte"`**. A lesson with no provenance is checked as PTE.
3. `render_enrichment_prompt.py --book <slug>` globs `docs/enrichment-domain-<slug>.md` — a *different, unvalidated* namespace.

Evaluator↔domain gating lives on the *check*, not the pack: `Evaluator.domains: tuple[str,...] = ("pte",)`. **That default is a trap** — any new pedagogical check registered without explicit `domains` is silently skipped for every maths lesson and reads as a pass.

### 4d. Where the pedagogy actually lives

- **Hardcoded in Python:** the entire 15-key section taxonomy (`_SCHEMA_CONTRACT`); which five sections are load-bearing (`REQUIRED_NONEMPTY_LISTS`); `schema_version="pte_lesson_enrichment.v1"`; `readability_evaluators.max_words_per_sentence=14.0` and `GRADE_TOLERANCE=0.5` (module constants, **not** pack fields); the `modality` enum; `audit_enrichment_facts.TASK_ALIASES` (13 PTE tasks) and `OFFICIAL_TRAITS` (12 Pearson traits). **`enrichment_loop._FIX_SYSTEM` still opens `"You correct PTE Academic enrichment lessons."`** and is used verbatim on maths — the exact leak the `payload_note` refactor was written to fix, reappearing in the loop.
- **Pack-driven:** four levers, two of them pedagogical (`min_worked_examples`, `reading_grade_max`).
- **Markdown, zero code enforcement:** all the real teaching design. `enrichment-domain-math5a.md` `{{TASK_TYPE_ADAPTATION}}` demands *"At least FOUR worked examples… Vary them: one straightforward, one with a twist, one word problem, one showing a common mistake being corrected"*, *"show the **bar model** in words before the arithmetic — this book teaches through bar models"*, and *"`common_mistakes` are the real errors children make: adding denominators, forgetting to simplify, misreading 'how many more'"*. **None of these is checked by anything.** `{{AUDIENCE}}` carries the reading-level policy derived by *counting terms in the real textbook* (~10 words/sentence, ~1.33 syl/word, "the real 94-page textbook uses 'denominator' twice and never writes 'numerator' or 'simplify'"), with a preferred-word list (`use` not `utilise`, `work out` not `calculate`).
- **And the markdown prompts are not in the loop at all.** They are standing ChatGPT project Instructions, pasted by hand into a browser. `enrich_lessons.py` never reads them. `render_enrichment_prompt.py --check` only proves engine+`pte` byte-reproduces `docs/enrichment-prompt.md`; there is **no equivalent check for math5a** and no check the live project was ever updated.

Net: **shape in Python, two threshold numbers in the pack, teaching philosophy in markdown the pipeline cannot see or verify.**

### 4e. Two loops; the good one is unused

**`enrichment_loop.close_loop(lesson, *, fixer, max_rounds=5, deep_health=False)`** — genuine generate→check→**targeted fix**→re-check. Pre-flight `health_report()`; unhealthy → `status="refused"`, loop never runs. Splits findings by `fixable`; `escalate` exits immediately with no retry; stop condition is `combine(...)["accepted"]` — *"the loop's stop condition has to be OUR verdict, never the model's opinion of its own work."* `ollama_fixer` sends the numbered findings plus "Fix exactly those problems and nothing else". Acceptance note: *"Accepted means no KNOWN defect remains… Passing checks is a floor, not a certificate."* **Consumers: `test_enrichment_loop.py` and one doc. No production caller.**

**`enrich_lessons.cmd_run()`** — what actually runs the book: regenerate-from-scratch, `max_attempts=3`, each attempt re-sends the **same unmodified 30–60K-char payload** to a fresh chat; **findings are never fed back to the model**. Idempotence via `lesson_status(n, pack)` ∈ `ok|stale|missing` (`ok` requires passing checks, so pre-check lessons regenerate). Backoff 300–600s, `--limit-backoff` 1800s.

**Two gate failures that matter:** (a) `enrich_lessons.check_lesson_facts` **fails open** — any exception *or* `not health["all_healthy"]` returns `[]`, i.e. "no problems", with only a stderr warning invisible on an overnight run; `close_loop` does this correctly (`"refused"`), this path does not. (b) `pipeline_evaluators.health_report()` is **not domain-filtered** — it runs the PTE guide self-tests (which open `~/Downloads/PTE-Academic-Test-Taker-Score-Guide.pdf` via pypdf) even for a maths job, so the maths pipeline's deterministic arithmetic guarantee is coupled to the presence of a PTE PDF at a hardcoded home-directory path. *I could not verify whether that PDF is present on the real machine — the device shell's `~` resolves to the sandbox session home, where it is absent and `all_healthy` was False.*

### 4f. Intended design, per the docs
"**Engine + domain pack**"; "adding a book means adding a pack rather than editing the pipeline". The one explicit principle, and it cuts against the brief's direction: **"Reusable ≠ generic"** (`enrichment-workflow.md`) — *"A prompt with no domain knowledge produces thinner, less trustworthy enrichment. So for a new book, write a new domain pack rather than stripping the domain out."*

**There is no named learning-science framework anywhere** — no Bloom, no mastery learning, no cognitive load, no retrieval practice, no scaffolding/ZPD. What exists is an implicit, coherent model encoded in the schema order: *overview → learning_goals → core_method (named mental model + ordered steps) → techniques (how-to + why_it_matters + common_error) → worked_examples (input → decoding → plan → model_answer → annotations) → useful_language → common_mistakes (mistake/why_it_hurts/fix) → practice_plan → mastery_checklist ("I can…") → strategy_notes.* Unnamed but recognisable: worked-example effect, faded guidance, error-focused instruction, self-assessment, audience-matched readability.

**Stated deferrals:** (1) under-length worked examples are knowingly unchecked because *"properly needs the schema to mark which example is the complete model answer"* — **a schema change is a prerequisite to any real completeness check**; (2) the grounded-base contract validator, claim-support audit and targeted evaluation are deliberately excluded from the live loop ("They need an async job interface, tracked separately"); (3) `close_loop` built/tested/documented/unused; (4) PTE lessons 18–19 sit outside the pipeline (drafted from Pearson guidance, not the book); (5) the extension contract — every new check needs ≥2 planted-error self-tests, one that must flag and one that must not.

---

## 5. Evaluators / quality gates

11 registered evaluators. `Evaluator{name, artifact, kind, description, findings_fn, self_tests, domains}`; `kind` literals are **`"deterministic"`** and **`"model"`**.

| name | artifact | kind | domains | checks | class |
|---|---|---|---|---|---|
| `extraction_damage` | `clean_chunks` | det | pte, math5a | empty / gap-garbled chunks; both `fixable=False`→ESCALATE | format |
| `reading_item_shape` | `reading_item` | det | pte | `reading_mcq_items.contract_validate` | format |
| `describe_image_item_shape` | `describe_image_item` | det | pte | chart type, 4–8 points, pie sums 99–101, not-all-identical | format |
| `reading_answer_key` | `reading_item` | **model** | pte | 3 unanimous blind solves must match the key | grounding + *partial pedagogy* (ambiguous distractors) |
| `worked_example_rules` | `enrichment_lesson` | det | pte | the lesson's own `model_answer` obeys the rule it teaches (guide word ceiling; SWT exactly 1 sentence) | grounding + internal consistency |
| `math_arithmetic` | `enrichment_lesson` | det | **math5a** | every asserted `=` chain exactly true | correctness |
| `worked_example_count` | `enrichment_lesson` | det | pte, math5a | `len(worked_examples) >= pack.min_worked_examples` | *weak pedagogy* — `len() >= 4` |
| `method_consistency` | `enrichment_lesson` | det | pte, math5a | arrowed banner must not miscount its own `steps` | internal consistency |
| `reading_level` | `enrichment_lesson` | det | **math5a** | Flesch-Kincaid vs `reading_grade_max` | **the one real pedagogical check** |
| `word_range` | `enrichment_lesson` | det | pte | the lesson must *state* the guide's Form word range | grounding (detects an absence) |
| `trait_names` | `enrichment_lesson` | det | pte | no official Pearson trait attached to a task the guide doesn't score on it | terminology |

Live-confirmed dispatch: math5a → `[math_arithmetic, worked_example_count, method_consistency, reading_level]`; pte → `[worked_example_rules, worked_example_count, method_consistency, word_range, trait_names]`.

**`readability_evaluators.py`** — hand-rolled Flesch-Kincaid (`0.39*wps + 11.8*spw - 15.59`), no library. Math handled two ways: `_NOT_PROSE = {model_answer, example, formula, input, item, source_label, schema_version, task_type, tags}` keys dropped from the measure; `_MATH_SPAN` regex strips `$…$`/`\cmd{}`. Unmeasurable below 3 sentences / 80 words. Reports **which lever fails** — sentence length (quoting the longest) vs syllables-per-word (listing the 6 most frequent 3+-syllable words). A recorded measurement worth carrying forward: against the real textbook (grade 4.0) their lessons **matched on sentence length (11 vs 10.1) and missed entirely on word length (1.67 vs 1.33 syl/word)**.

**`math_evaluators.py`** — arithmetic *truth*, not parsing. `_walk_asserted` skips `_STIMULUS_KEYS = {input, mistake, misconception}` (a "spot the mistake" example must contain a false equation — *"Lesson 3 looped forever because this was flagged"*). Extracts LaTeX math spans only, splits on `\qquad|\quad|\\|;|\n`, `ast.parse` + restricted `_eval_node` over `Fraction` — no `eval()`, no names, no calls. Validated over the whole book: **181 chains, 0 false positives.** Honest limits: plain-prose arithmetic deliberately unscanned; `"11 / 4 = 2 remainder 3"` unmodellable; units/variables skipped. **`checkable_chain_count(doc)` exists — the right idea, "absence of verifiable maths is REPORTED rather than guessed at" — but is not wired into any `findings_fn`, so a maths lesson with zero LaTeX passes `math_arithmetic` vacuously and silently.**

**`evaluator_mcp_server.py`** — `FastMCP("pte-evaluators")`, stdio, 7 tools: `list_evaluators()`, `check_health(deep=False)`, `check_extraction(chunks)`, `check_reading_item(item, verify_answer_key=False)`, `check_describe_image_item(item)`, `evaluate_enrichment_lesson(lesson)`, `evaluate_with(evaluator_name, payload)`. The model chooses *which* checks to call but "does NOT decide whether it passed".

**The honesty gate.** `self_check(name)`: no self-tests → **unhealthy by default** ("cannot prove it still catches errors"); self-test and live run call the *same* `findings_fn` (an earlier version held a separate reference, so breaking the live path left the self-test green). `test_evaluation_contract.py` monkeypatches `check_word_range` to return `[]` and asserts the verdict becomes `escalate`. Three historical incidents of silently-dead checks are documented in `enrichment-workflow.md`. Self-check runs **per invocation, uncached** — `math_arithmetic` re-runs 20 fixtures every lesson.

### Central question: pedagogical quality
6 of 11 are grounding checks against external ground truth (Score Guide PDF, or arithmetic); 4 of 11 are shape contracts. **Exactly one** measures a pedagogical property on a continuous scale against an audience model — `reading_level` — and it is **inert for the entire PTE domain** (`reading_grade_max=None`). Two more are pedagogically *motivated* but mechanically shallow.

**Not checked at all**, despite the schema requiring the fields:
1. **`learning_goals` — goal/assessment alignment.** Required non-empty, then referenced by **no other `.py` file**. Nothing checks the examples, drills or checklist exercise the goals, or that goals are stated as observable behaviours. Largest single gap.
2. **`mastery_checklist`** — required non-empty, content never inspected.
3. **Misconception realism.** `common_mistakes`/`common_misconceptions` are *actively excluded* from the only content check touching them (`_STIMULUS_KEYS`). Nothing verifies a misconception is real, distinct, or that its `fix` addresses it.
4. **Worked-example variety.** Four near-identical problems pass `min_worked_examples=4`. The maths pack *demands* four kinds; nothing enforces it. Nor the bar-model requirement.
5. **Difficulty progression / prerequisite ordering.** `metadata.difficulty` is unvalidated free text. Zero cross-chapter checks.
6. **Cognitive load.** `reading_level` is a linguistic proxy only. A 12-step method for 10-year-olds passes `method_consistency` as long as the banner counts to 12. No check on simultaneous new-term load.
7. **Explanation completeness.** `worked_examples[].decoding/.plan/.annotations` optional and never inspected; a bare answer is indistinguishable from full working.
8. **`techniques[]`** — only `how_to` non-emptiness; `purpose`, `why_it_matters`, `common_error` unexamined.
9. **`practice_plan`** — not even in `REQUIRED_NONEMPTY_LISTS`; wholly unchecked.
10. **Practice-to-teaching coverage.** Item checks and lesson checks live on different `artifact`s and never meet. Nothing links any practice bank to any lesson goal.

**And the project has already measured its model judge and demoted it:** `test_audit_sensitivity.py` records that at temperature 0 the judge returned `NOT_IN_GUIDE` for a plainly contradicted word range in **3 of 4 runs**, while the deterministic `check_word_range` caught it **5/5**. Missed judge verdicts go to an `advisory` bucket that does not affect exit code. Since most pedagogical dimensions are not mechanically computable, this is the binding constraint on the redesign: the architecture supports a model judge (`kind="model"`, `EvaluatorResult.advisory`), but this project's own evidence argues against trusting one as a gate.

---

## 6. Storage and API

### Storage — `book_learning_materials_store.py` (536 LOC)
**SQLAlchemy 2.x ORM over SQLite**, `DEFAULT_DB_URL = "sqlite:///storage/learning_materials.db"` (env `LEARNING_MATERIALS_DB_URL`). Documents stored whole in TEXT columns, not normalised.

| table | class | columns |
|---|---|---|
| `learning_material_chapters` | `ChapterRecord` | `id` (`"{slug}:ch{nn}"`), `book_slug`*, `chapter_number`, `chapter_title`, `source_pdf`, `schema_version`, `backend`, `model`, `generated_at`, `contract_status`, `loaded_at`, `document` TEXT; `uq_book_chapter` |
| `learning_material_enrichments` | `EnrichmentRecord` | `id` (`"…:enrichment"`), `book_slug`*, `chapter_number`, `schema_version`, `task_type`, `lesson_title`, `source_label`, `loaded_at`, `document` |
| `essay_attempts` | `EssayAttempt` | `id`, `book_slug`*, `chapter_number`, `task_type`*, `prompt_type`, `prompt_text`, `essay_text`, `word_count`, `raw_total`, `max_raw_total` (**all INTEGER — no partial credit**), `feedback` TEXT, `created_at` |
| `math_item_states` | `MathItemState` | `id`, `learner`* (default `"local"`), `item_id`*, `level`, `due_at`, `introduced_at`, `last_studied_at`, `mastered_at`, `times_seen`, `times_correct`, `streak`; `mis_learner_item_unique` |

`essay_attempts` is misnamed on purpose (kept so rows survive) — it is the universal attempt table for all six task types. **No `learners`/`users` table.** `essay_attempts` has no learner column at all; attempts are global. `learner` appears only on `math_item_states`, hardcoded `"local"` at every call site — the docstring says "a learner slug so multi-user is a filter, not a migration."

Two chapter write paths: `load_chapter_file` (full contract, blocking errors → nothing stored, `contract_status="PASS"`) and `register_chapter_file` (added for maths, which "fails 2700+ of its rules", stores `contract_status="extracted"`, **never `"PASS"`**). `NON_BLOCKING_CONTRACT_CODES = {"EMPTY_CLEAN_CHUNK_TEXT"}`. Enrichment→chapter binding is a **parsed string** (`_SOURCE_LABEL_RE = ^([a-z0-9_-]+):ch0*(\d+)$`), not a FK.

**Migrations:** one 8-line hand-rolled `_ensure_column` using `PRAGMA table_info`, called exactly once (`essay_attempts.task_type`). No Alembic, no version table, additive-only. Every new column needs another hand-written line or existing DBs break silently.

**Six item banks live only as JSON files on disk**, re-read and re-parsed per request (`post_math_practice_answer` reads twice per call), env-overridable: `DESCRIBE_IMAGE_ITEMS_FILE`, `READING_MCQ_ITEMS_FILE`, `MATH_PRACTICE_ITEMS_FILE`, `MATH_REASONING_ITEMS_FILE`, `SWT_PASSAGES_FILE`, `ESSAY_PROMPTS_FILE`. **The only join between banks and learner state is a bare `item_id` string with no referential integrity.**

**Live DB row counts:** `learning_material_chapters` **28**, `learning_material_enrichments` **28**, `essay_attempts` **7**, `math_item_states` **2**. The learner-facing loop has essentially never been exercised. There is also a **stale empty DB at the repo root** (`learning_materials.db`, all four tables, zero rows, mtime *newer* than the real one) — start the API with the wrong cwd and it serves an empty library while looking healthy.

`output/` holds `math5a.chapter01..09` bases + enrichments, `pte.chapter01..17` bases + `pte.chapter01..19` enrichments, the six banks, `enrichment_fact_audit.json`, `grader_agreement.json`. `storage/` also holds 8 legacy LlamaIndex vector stores belonging to `api.py`.

### API — `learning_materials_api.py` (731 LOC) is live; `api.py` is superseded
Determined by: `app = create_app()` with `# Module-level app for uvicorn learning_materials_api:app`; the frontend's error screen literally instructs `uvicorn learning_materials_api:app`; `docs/generation-pipeline.md`; four current test files import it; the last 6 commits are all its endpoints. `api.py` (`FastAPI(title="Tiny Learning RAG API")`, Jul 11) still has 2 live tests and is still what `README.md` and `docs/API.md` tell you to run — **two FastAPI apps both defaulting to port 8000.**

**`docs/API.md` (21KB) is stale — it documents only `api.py` and contains zero documentation of any live route.** There is no written contract for the live API; the code and `frontend/src/lib/types.ts` are the only spec.

FastAPI, `create_app(engine=None)`, CORS `LEARNING_MATERIALS_CORS_ORIGINS` default `*`, `allow_methods=["GET","POST"]` — **no PUT/PATCH/DELETE, no auth, no learner identity anywhere.** Chapter/enrichment bodies are raw `dict[str,Any]` passthroughs by design.

**18 routes:**

*Content:* `GET /health` → `{status}` · `GET /books` → `[{slug, chapter_count}]` · `GET /books/{slug}/chapters` → `[{id, book_slug, chapter_number, chapter_title, backend, model, contract_status, has_enrichment}]` · `GET /books/{slug}/chapters/{n}` → the stored document verbatim · `GET /books/{slug}/chapters/{n}/sections/{section}` (section ∈ the 9 `CHAPTER_SECTIONS`; **never called by the frontend**) · `GET /books/{slug}/chapters/{n}/enrichment` → the enrichment document verbatim.

*Item banks (all book-agnostic, none namespaced by slug):* `GET /describe-image-items` (**nothing withheld — ships `facts`, the graded ground truth, and `points`**) · `GET /reading-mcq-items` (minus `correct`, `rationale`) · `GET /math-practice-items` (minus the 5 answer fields) · `GET /swt-passages` (**ships `central_claim`**) · `GET /essay-prompts`.

*Scheduling — 2, maths only:* `GET /books/{slug}/math-practice-next?after=<id>` and `GET /books/{slug}/math-reasoning-next?after=<id>` → `{item|null, reason ∈ new|due|review|all_mastered, progress{total,mastered,due,new,in_progress}}`. **`{slug}` is accepted and completely ignored** in both — the bank comes from a global env path and states are not filtered by book, so a `pte` slug gets maths items.

*Attempts — 6 POSTs, all writing `essay_attempts` + committing:* `/books/{slug}/chapters/{n}/essay-feedback` (model, `write_essay`) · `/swt-feedback` (model, `summarize_written_text`) · `/describe-image-feedback` (model, `describe_image`) · `/math-practice-answer` (**code only**, `math_practice`) · `/math-reasoning-answer` (**code marks, model advises**, `math_reasoning`) · `/reading-mcq-answer` (**code only**, `reading_multiple_choice`). Error mapping: `RuntimeError`→503, `httpx.HTTPError`→502, `ValueError`→502, unknown item→404. **Only the two maths endpoints touch `math_item_states`** — MCQ, essay, SWT and describe-image have history but no scheduling.

Every task type is coerced into the *essay rubric shape* (`traits`/`raw_total`/`max_raw_total`/`top_priorities`/`word_count`/`gating_applied`) so one history list renders all of them; `word_count: 0` and `gating_applied: false` are dead filler on non-writing tasks. Reasoning adds `marking: "computed; explanation feedback is advisory"`, `advisory`, `advisory_error`, and updates the schedule from `det["correct"]` *before* the advisory call — *"An advisory opinion must never decide when a child sees a question again."*

*Progress — 2:* `GET /books/{slug}/essay-attempts?task_type=` → `[{id, chapter_number, task_type, prompt_type, prompt_excerpt, raw_total, max_raw_total, word_count, created_at, scored_by, traits[{name,score,max,scored_by,advisory}]}]` limit 100 · `GET /books/{slug}/essay-attempts/{id}` → full `feedback`. **There is no aggregate progress endpoint** — no mastery-per-skill, no per-chapter completion, no streaks. `progress` exists only as a side-payload on the two maths endpoints.

**Scoring disclosure:** `_with_scoring_disclosure(feedback, task_type)`; `MODEL_SCORED_TASKS = {write_essay, summarize_written_text, describe_image}`, everything else `"code"`; per-trait, `advisory:true`→`"model"`, name in `CODE_SCORED_TRAITS_BY_TASK`→`"code"`. Applied on read as well as write so legacy rows back-fill. Worth preserving verbatim through any redesign.

---

## 7. Frontend

`frontend/` — **React 19.2 + TypeScript ~6.0 + Vite 8.1 + Tailwind 4.3 + react-router-dom 7.18 + KaTeX 0.18 + lucide-react**, linted with oxlint. No test framework, no state library.

**Real, working, non-trivial UI — not a scaffold.** 4,632 LOC of hand-written TSX across 15 files, with a current production build (`frontend/dist/assets/index-BxNpjCDw.js`, 583KB, Jul 25 02:11). Only scaffold residue is the stock Vite `frontend/README.md`.

```
pages/       Home.tsx 103   ChapterReader.tsx 447
components/  EssayPractice.tsx 860  CoachView.tsx 444  DescribeImagePractice.tsx 418
             MathReasoning.tsx 344  ReadingMcqPractice.tsx 337  MathPractice.tsx 327
             SwtPractice.tsx 251  Sidebar.tsx 128  MathText.tsx 105
             GroundedText.tsx 68  ErrorBoundary.tsx 42  Section.tsx 31
lib/         types.ts 397  api.ts 109  useAsync.ts 20
App.tsx 123  main.tsx 13  index.css 65
```

**Flows built:** (1) **lesson viewer** — complete, renders all 9 chapter sections, with a `GroundingLegend` teaching green="From the book" vs amber="Practice" and `GroundedText.tsx` rendering per-claim `origin`/`evidence_spans`; KaTeX for maths. (2) **CoachView** — complete, renders essentially the whole enrichment document including `metadata.provenance_note` as a "How this was made" footer. (3) **six practice runners** — all real: `EssayPractice` (exam timer, live word count, localStorage draft, trait bars, ideas-vs-language `SplitBar`, inline `Corrections` diffing against `errors[]`, `ScoredByNote`/`TraitSource`), `SwtPractice`, `DescribeImagePractice` (inline SVG), `ReadingMcqPractice` (per-option rationale after submit), `MathPractice` + `MathReasoning` (driven by `*-next`, `ProgressBar`, `ReasonChip` explaining *why* this item, `mastered_now` celebration). (4) **progress — partial**: `HistorySection`/`Sparkline`/`TraitProgress`/`TrendArrow`/`AttemptModal` all live inside `EssayPractice.tsx` and are imported by the other five, so every task gets history + trend, but scoped to one `task_type` per tab. **No top-level dashboard route.**

**State: React primitives only.** `lib/useAsync.ts` is a 20-line fetch-on-mount hook with **no caching, dedup, revalidation or retry** — every mount refetches; cache invalidation is a manual `historyVersion` counter. `localStorage` holds unsubmitted drafts only. **No auth token, no learner id, no progress cached client-side.** Tab selection is `useState`, so not deep-linkable and lost on reload.

**Generalisation debt:** practice-tab eligibility is a hardcoded allowlist plus `enrich.data.source_label.startsWith('math5a')` in `ChapterReader.tsx:50` — a third book gets no practice tab without editing the component. `bookLabel(slug) = slug.toUpperCase()` → the brand reads "MATH5A Learn". `Home.tsx` hardcodes the PTE "Coverage note" about *Summarize Group Discussion* / lessons 18–19 and renders it for **every** book including math5a. The Laravel consumer is referenced nowhere in the frontend or CORS config.

**No write path for the reading flow at all** — the `review_checklist` checkboxes and reveal-answer state are ephemeral `useState`. Only *scored submissions* persist, so the system has zero signal about content consumption.

---

## 8. Learner-model gap check

I grepped the whole repo (excluding `.venv`, `__pycache__`, `.claude`) for every learner-model term. Counts: `learner` 112 (all in comments/docstrings plus the one `MathItemState.learner` column and its default `"local"`), `mastered` 43, `progress` 37, `mastery` 9, `diagnostic` 2 (both `dry_run_diagnostics` in `audit_book_claim_support.py`, unrelated), `placement` 18 (**all false positives — every one is the substring in "replacement"**), and **zero** hits for `prerequisite`, `session_id`, `enrol`, `curriculum`, `objective_id`, `skill_id`. No auth/JWT/user_id anywhere (`token` in the API is `working_tokens`).

**Verdict: the system is content-generation-only, plus `spaced_repetition.py` as the sole learner-facing scheduling piece. Specifically:**

- **No learner identity.** One hardcoded string `"local"`, on one column, of one table. No users table, no auth, no multi-tenancy. `essay_attempts` has no learner column at all.
- **No mastery model** beyond per-item Leitner level. `mastered_at` is a per-item boolean-in-a-timestamp; nothing aggregates to a skill, objective, chapter, or book. There is no knowledge state, no BKT/DKT, no skill graph, no prerequisite ordering (`prerequisite`: 0 hits).
- **No session concept.** Nothing bounds a sitting, no session table, no session length, no daily new-item cap. `MathPractice` keeps a `seen`/`right` tally in `useState` that dies on reload.
- **No diagnostic or placement logic.** Zero. Every learner starts at level 0 on every item in bank order.
- **No learner-facing state for 4 of 6 task types.** Essay, SWT, describe-image and reading MCQ produce attempt rows and nothing else — no scheduling, no mastery, no next-item selection.
- **Structural blocker:** `spaced_repetition.update()` takes `correct: bool`. The rubric-scored tasks produce `raw_total`/`max_raw_total` integers. Partial credit cannot drive the schedule without changing that signature.
- **No content→learner link.** `learning_goals` is required by the schema and read by no `.py` file. No item, bank, or attempt references a learning objective, a chapter section, or a skill id. The practice banks and the lessons are two disconnected universes joined only by the frontend's tab layout.
- **No engagement signal.** Reading a lesson, ticking the review checklist, revealing an answer — none is recorded.

---

## Appendix A — LOC, top 15 (top-level `*.py`; 38,031 total)

| LOC | file | status |
|---|---|---|
| 2,954 | `generate_book_learning_materials.py` | **current** — the orchestrator |
| 2,864 | `evaluate_targeted_book_learning_materials.py` | current-but-batch (excluded from the live loop by design) |
| 1,557 | `audit_book_claim_support.py` | current-but-batch |
| 1,146 | `ask_section_pdf_lesson.py` | legacy (`api.py` Q&A path) |
| 1,134 | `book_learning_materials_contract.py` | **current** — the grounding gate |
| 1,093 | `extract_book_learning_claims.py` | current-but-batch |
| 1,038 | `book_learning_materials_v2_generation.py` | **current** |
| 1,016 | `generate_section_pdf_lesson_json.py` | legacy |
| 951 | `retrieve_section_pdf_context.py` | legacy |
| 921 | `audit_section_pdf_lesson.py` | **dead** (0 inbound refs, Jul 10) |
| 846 | `resolve_document_structure.py` | **current** (invoked by the orchestrator) |
| 785 | `build_pdf_section_topic_outline.py` | **dead** (0 refs, Jul 10) |
| 731 | `learning_materials_api.py` | **current** — the live API |
| 720 | `build_pdf_section_outline.py` | **current** (invoked) |
| 684 | `enrich_lessons.py` / 684 `api.py` | current / superseded |

## Appendix B — current vs dead

**Invoked by `generate_book_learning_materials.py`** (the authoritative "current preparation path", by `subprocess` literal): `pdf_to_chunks.py`, `inspect_pdf_chunks.py`, `build_pdf_outline.py`, `build_pdf_body_outline.py`, `assign_pdf_chapters.py`, `detect_pdf_sections_topics.py`, `build_pdf_section_outline.py`, `build_pdf_strict_section_outline.py`, `resolve_document_structure.py`, `assign_pdf_sections.py`, `prepare_clean_section_index.py`. It imports `book_learning_materials_v2_generation` and `pdf_artifact_paths`.

**Standalone current entrypoints (0 inbound refs but alive — they write `output/*.json` the API reads by path, mtimes Jul 18–25):** `essay_prompts.py`, `swt_passages.py`, `describe_image_items.py`, `reading_mcq_items.py`, `math_practice_items.py`, `math_reasoning_items.py`, `build_math_grounded_base.py`, `load_grounded_base.py`, `render_enrichment_prompt.py`, `enrich_lessons.py`, plus the 11 root-level `test_*.py`.

**Dead / superseded** (0 inbound refs, not invoked by the orchestrator, mtimes Jul 9–11 — the exploratory RAG era the README build-log documents): `build_index.py`, `build_pdf_index.py`, `build_section_pdf_index.py`, `build_structured_pdf_index.py`, `build_clean_section_pdf_index.py`, `build_pdf_section_topic_outline.py`, `retrieve_context.py`, `retrieve_pdf_context.py`, `retrieve_structured_pdf_context.py`, `generate_lesson.py`, `generate_lesson_json.py`, `generate_structured_pdf_lesson_json.py`, `load_pdf_with_llamaindex.py`, `audit_generated_lesson.py`, `audit_section_pdf_lesson.py`, `compare_section_lesson_runs.py`. `api.py` + `ask_section_pdf_lesson.py` + `retrieve_section_pdf_context.py` are superseded in role but still imported by 2 tests and still documented as the entrypoint in `README.md` and `docs/API.md`.

**Stale docs:** `docs/API.md` (documents the wrong server), `README.md` (1,475-line build log naming `api.py` as the entrypoint), `HANDOFF.md` (Jul 14, predates the entire V2 study-tool work). `docs/README.md` (Jul 16) is the accurate orientation doc but predates spaced repetition, practice items and feedback.

## Appendix C — test suite coverage

**`tests/` (22 files, pytest)** — grounded-base pipeline and store: contract validation, evidence-span enforcement, claim extraction, claim-support audit + judge backend + claim scope, targeted evaluation, generation v1/v2, backend/token caps, CLI infrastructure, repair, chunk-damage scan, store + enrichment store, `learning_materials_api`, manual v2 chapter, and 4 legacy `api.py` section-PDF tests.

**Root-level (11 files)** — the newer, mostly plain-script `python test_x.py` style with `SystemExit`:
- *Offline regression:* `test_spaced_repetition.py`, `test_math_practice.py`, `test_math_reasoning.py`, `test_scoring_disclosure.py`, `test_evaluation_contract.py`, `test_enrichment_loop.py`, `test_enrich_run_loop.py`
- *Needs a subprocess/fixtures:* `test_evaluator_mcp.py` (real stdio MCP client, depends on `output/*.json`)
- *Costs live model calls, NOT in regression:* `test_grader_agreement.py`, `test_reasoning_grader_sensitivity.py`, `test_audit_sensitivity.py`

Coverage is genuinely strong on **grounding, contract shape, deterministic marking, scheduler behaviour, provenance disclosure, and grader discrimination against a planted-defect corpus**. There are **no tests of pedagogical quality**, no tests of goal/assessment alignment, no frontend tests at all, and `pipeline_evaluators` health is environment-dependent (three self-test suites read `output/*.json`; three read a PDF at a hardcoded `~/Downloads` path).
