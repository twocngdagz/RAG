> **NONCANONICAL RESEARCH INPUT.** This document is a dated observation or synthesis,
> not a decision. It does not adopt anything. Only explicitly accepted ADR and plan
> decisions are authoritative — see `docs/research-inputs/README.md` and
> `docs/research-rule-classification.md`.
>
> Captured 2026-07-26 · RAG `296d6b5` · Ela `da188c5`

# Pedagogy Guidelines

### From *A Mind for Numbers* to a multi-audience, evidence-based study engine

**Purpose of this document.** This is the pedagogy layer specification: the "why" and the "what must be true" that the two codebases (RAG Prototype and Ela) must implement. It takes every technique the book actually teaches (inventoried in `book_method.md`), cross-references each against the wider learning-science evidence base, and turns them into concrete, testable product invariants that work across four very different audiences: PTE/IELTS test-takers, adult language learners, interview/job-prep candidates, and children doing early maths and reading.

It is deliberately opinionated. Oakley's book is a popular-science synthesis, not a primary source; where the research literature is stronger, more precise, or more cautious than the book, this document follows the research and says so. Claims that carry real product weight are tagged `⟦cite⟧` and are backed by the references collected in the companion research pass (`04_research_citations.md`).

A note on how to read the three "layers" below. Everything in Part 1 is an **engine invariant** — it is true for every audience and must be enforced in app-owned code, never left to an AI model's discretion. Part 2 maps techniques to material types. Part 3 is the concrete scheduling/mastery model. Part 4 is where the four audiences genuinely diverge. Part 5 points at the code.

---

## Part 1 — The engine: seven invariants that hold for every audience

The book contains roughly thirty techniques. They are not thirty independent ideas. Underneath them are a small number of robust findings from cognitive psychology, and it is those findings — not the book's specific framing — that the engine should be built on. The book's value is that it operationalises them for a learner; the research is what tells us which ones are load-bearing.

### Invariant 1 — Retrieval is the unit of learning (not exposure)

**What the book says.** Active recall is the single most emphasised behaviour in the book: every chapter ends with a recall prompt, it is rule 1 of the closing list, and rereading/highlighting are named as the central failure mode ("illusions of competence").

**What the evidence says.** The *testing effect* (retrieval practice) is one of the most replicated results in the science of learning: retrieving information from memory produces substantially better long-term retention than restudying the same material for the same time, across ages, materials and formats.⟦cite⟧ The effect is strongest when retrieval is effortful but successful, and when it is followed by feedback.⟦cite⟧ Crucially, the benefit shows up on *delayed* tests, often reversing the ranking you'd predict from how things feel during study — learners reliably misjudge restudy as more effective than retrieval.⟦cite⟧

**Engine invariant.** Every material type must have a *productive* mode where the learner generates a response from memory before seeing the answer. Recognition-only interactions (multiple choice with the options visible from the start, "reveal answer" flashcards graded by self-report) are permitted only as a scaffold for brand-new items or very young learners, and must graduate to production. The system must record *what the learner produced*, not merely whether they clicked "I knew it."

> **Code consequence.** Ela's `flashcard_review` → `self_check` path is recognition + self-report; it is acceptable only as the `learn`-phase scaffold and must not be the terminal state for an item. RAG Prototype's reading-MCQ and describe-image tasks are production-scored and are the better model.

### Invariant 2 — Spacing beats massing, and the gap should grow

**What the book says.** "A little every day"; the brick-and-mortar image (consolidation happens *between* sessions); review new material within a day; cramming produces a heap, not a wall.

**What the evidence says.** Distributed practice is, with retrieval practice, the best-supported technique in the literature.⟦cite⟧ Two refinements matter for a scheduler. First, the optimal gap scales with the *retention interval* you care about — to remember something for a month, reviews spaced over days-to-weeks beat reviews spaced over hours; the ratio of optimal gap to retention interval sits very roughly in the 10–30% region and *lengthens* as the target delay grows (Cepeda et al.).⟦cite⟧ Second, *expanding* intervals (each successful review pushes the next one further out) are at least as good as fixed intervals and are the basis of every modern spaced-repetition algorithm.⟦cite⟧

**Engine invariant.** Intervals must **expand without bound** on repeated success and contract on failure. A ladder that caps at a fixed maximum (see the code consequence) cannot produce durable long-term retention and must be replaced by a stability-based algorithm (Part 3).

> **Code consequence — this is the single highest-leverage change in either repo.** Ela's interval logic is `12h / 1d / {1d,3d,7d}` recomputed from `times_seen` every review and **capped at 7 days forever** — it is memoryless and cannot expand. RAG Prototype's Leitner ladder tops out at a 60-day "mastery" review. Both must move to a per-item stability model.

### Invariant 3 — Interleave; make practice desirably difficult

**What the book says.** Mix problem types rather than blocking; "learning carpentry with only a hammer"; textbooks are organised *against* interleaving so you must impose it; overlearning (practising past criterion in the same session) wastes time and feeds the competence illusion.

**What the evidence says.** Interleaving of related-but-confusable categories improves the ability to *discriminate* and to *select* the right procedure, even though it feels harder and slower during practice — the classic desirable-difficulty pattern.⟦cite⟧ The effect is clearest when items are confusable (maths problem types, painters' styles, grammatical forms); for wholly unrelated material blocking is fine. Overlearning gives short-lived gains that decay quickly and is a poor use of time relative to spacing.⟦cite⟧

**Engine invariant.** A session must mix item types/skills rather than drilling one to exhaustion, and the mix should place *confusable* skills near each other. The scheduler must stop surfacing an item for same-session repetition once it is answered correctly (convert repetition into spacing). "Feels harder" is not a bug to be smoothed away; the UI must not optimise for in-session ease at the expense of the delayed outcome.

> **Code consequence.** Ela already interleaves structurally (phrase-first round-robin over due/weak/new) — keep it, but its ranker optimises *topic coherence*, which can work against confusability-based interleaving; the two goals need explicit reconciliation. RAG Prototype has no session concept at all.

### Invariant 4 — Manage cognitive load; teach with worked examples and fade them

**What the book says.** Working memory holds ~4 items; chunking exists to economise it; understand the idea before memorising; a mnemonic is a retrieval handle, not understanding; multitasking shallows encoding.

**What the evidence says.** Cognitive Load Theory: working memory is severely limited for novel information but effectively unlimited when drawing on schemas in long-term memory.⟦cite⟧ For novices, studying *worked examples* is more efficient than solving equivalent problems (the worked-example effect), and the fastest route is *faded* worked examples — full example → partially completed → solve unaided.⟦cite⟧ This reverses as expertise grows: what helps a novice *hurts* an expert (the expertise-reversal effect), so scaffolding must be withdrawn as mastery increases.⟦cite⟧ New-term/element load must be capped for beginners.

**Engine invariant.** Instruction for a new item leads with a complete worked model, then fades support as the learner's state on that skill improves. The number of genuinely new elements introduced in one sitting is capped, and the cap is lower for younger/earlier learners. Scaffolding level is a *function of learner state*, not a fixed property of the content.

> **Code consequence.** RAG Prototype's enrichment schema already encodes an implicit faded-guidance model (`worked_examples` with `input → decoding → plan → model_answer → annotations`) but nothing checks completeness or varies it by learner state. Ela's runtime "learning phase" renders up to 8 static steps regardless of state. Both need state-driven fading.

### Invariant 5 — Feedback is part of practice, and its source must be honest

**What the book says.** Testing helps even without feedback, but during study you *should* check against solutions; review every error, work out why, rework it; self-deception is the easiest kind, so use other people to catch blind spots.

**What the evidence says.** Feedback substantially amplifies the testing effect, especially for errors and low-confidence correct answers; delayed feedback can beat immediate feedback for retention in some conditions, but timely, specific, correction-focused feedback is the safe default.⟦cite⟧ Elaborated feedback (why the answer is wrong, what to do) outperforms right/wrong feedback for complex material.⟦cite⟧ For anything that can be checked deterministically, a rule-based checker is more reliable than a model judge — and this project already has direct internal evidence for that (a model judge at temperature 0 flipped a plainly-contradicted numeric claim across runs, while the deterministic check caught it every time).

**Engine invariant.** Every response gets feedback. Where correctness is deterministically checkable (arithmetic, exact/pattern match, numeric tolerance), a **rule-based checker is the primary signal and the source of record**; an AI model may *elaborate* ("here's why, here's the fix") but must never be the thing that decides right/wrong or moves the schedule. Where correctness is genuinely open (an essay, a spoken answer), the model scores against an explicit rubric, its output is labelled as a model judgement, and it is gated/backed by deterministic sub-checks wherever one exists (word count, required-structure presence, banned patterns). The "honesty gate" from RAG Prototype — a check may only certify PASS if, on this run, it just caught its own planted error — is the correct discipline and should govern both repos.

> **Code consequence.** Preserve RAG Prototype's `scored_by` disclosure and honesty gate; preserve Ela's rule that the AI rubric "does not change review scheduling." Extend both: Ela currently lets a *learner self-graded* three-way radio drive all scheduling (Invariant 5 says that is acceptable only where no deterministic check is possible, and never for children's maths or exam scoring).

### Invariant 6 — Metacognition and calibration are first-class, because learners misjudge themselves

**What the book says.** Illusions of competence are the book's reason for existing; the two checklists (test-prep audit, good/bad habits) are behavioural self-audits; "prove retention by generating with the source closed."

**What the evidence says.** Learners are systematically miscalibrated — fluency of processing is read as knowledge, and confidence correlates poorly with accuracy, especially for weaker learners (Dunning–Kruger-type patterns).⟦cite⟧ Prompting a *prediction* before an answer and showing the gap afterwards improves calibration; confidence-weighted retrieval and "judgements of learning" taken at a delay are more accurate than immediate ones.⟦cite⟧

**Engine invariant.** The system captures the learner's *predicted* confidence or answer before revealing the truth, and surfaces the gap between felt and actual mastery rather than hiding it. Progress displays must show *demonstrated* retention (retrieval success at a delay), never "items viewed" or "time spent," which are exactly the illusion the book warns about. Mastery is *earned through evidence*, never self-declared.

> **Code consequence.** Ela's `CONTEXT.md` already forbids a learner marking an item mastered directly — good, keep it as an engine rule. Neither repo currently captures a pre-answer confidence prediction; both progress surfaces show counts, not demonstrated retention.

### Invariant 7 — The behavioural scaffolding is real, and it is mostly UI

The book spends more page-count on *procrastination and habit* than on any other practical topic, plus sleep, focused/diffuse alternation, exercise, and planning. These are not learning-content; they are the conditions under which learning happens, and the evidence for the big ones is solid: sleep consolidates memory and sleep deprivation impairs encoding and consolidation⟦cite⟧; the Pomodoro/time-boxing and implementation-intention ("if-then" plans) literatures support bounded, cue-triggered work sessions⟦cite⟧; distributed daily practice depends on the habit loop actually firing.

**Engine invariant.** The product must make the *right behaviour* the easy default: bounded focus sessions with a clear stop, a daily cue and a small completion reward, a visible-but-non-punitive streak, pre-sleep/next-day review nudges tied to a real schedule, and process-framed goals ("study 20 minutes," "clear today's reviews") rather than outcome-framed nagging ("finish the chapter"). Test-day audiences additionally get a countdown that schedules a sleep reminder the night before and breathing-rehearsal well *before* the day, not just on it.

> **Code consequence.** This is where the per-audience UI/UX spec (`02_ux_spec.md`) does most of its work. Ela's priming screen and `queue_quality_signal` linter are a strong foundation; scheduled-task infrastructure (Cowork) can drive the review nudges.

**A deliberate omission.** The book's memory-palace/mnemonic chapters, equation poems, handwriting-over-typing, and "recall in varied physical locations" are genuinely useful but are *minor tips* by the book's own framing and/or weakly evidenced (the book is candid that the handwriting research is thin). They belong in an optional "techniques" surface, not baked into the engine. Handwriting in particular argues *against* pure on-screen input — worth offering a "capture on paper, photograph in" path for some audiences, but not a core dependency.

---

## Part 2 — Mapping techniques to material types

The four audiences don't consume the same content. This table maps each engine invariant to what it concretely means for each *material type*, which is what the item-generation and evaluation code has to produce and check. (Item types are drawn from what the two repos already generate or clearly imply.)

| Material type | Retrieval mode (Inv. 1) | Deterministic check available? (Inv. 5) | Worked-example/fade model (Inv. 4) | Primary audiences |
|---|---|---|---|---|
| **Numeric/maths problem** | Produce the answer + working, source closed | **Yes** — exact `Fraction`/numeric, working-token check | Full worked example → faded steps → solo; bar-model-in-words first for children | Children maths |
| **Short-answer / cloze / conjugation** | Produce the form from memory | **Yes** — exact/normalised match, pattern rules | Model form → partial → produce | Language, PTE/IELTS |
| **Vocabulary / phrase-chunk** | Produce meaning *and* use in a sentence (both directions) | **Partial** — presence/normalisation deterministic; usage quality needs rubric | Definition+example shown → produce use | Language |
| **Reading comprehension (MCQ)** | Answer before seeing options where possible; per-option rationale after | **Yes** — key + blind-solve agreement (already in RAG) | Passage → question → distractor rationale | PTE/IELTS, children reading |
| **Extended writing (essay, SWT, describe-image)** | Produce full response under time | **Partial** — word count, structure presence, numeric-accuracy (describe-image), banned patterns are deterministic; overall quality is rubric | Model answer + annotations → prompts with fading support | PTE/IELTS |
| **Spoken/performed answer (interview STAR, PTE speaking)** | Produce aloud, recorded | **Weak** — structure presence (did all STAR parts appear?) deterministic; delivery is rubric/human | Model structure → beats → free delivery | Interview, PTE speaking |
| **Early-reading decoding (phonics)** | Decode aloud, unaided | **Partial** — target grapheme/phoneme presence; ideally ASR or adult-scored | Blend shown → guided → unaided; one pattern at a time | Children reading |

Two cross-cutting rules fall out of this table:

**Rule A — the scheduler must accept graded, not just boolean, outcomes.** Half the material types above produce partial credit (a 0–100 rubric total, a "2 of 4 STAR parts present," a "covered 3 of 5 essential facts"). Both current schedulers take `correct: bool`. This is a structural blocker (Part 3 fixes it).

**Rule B — every item must point back to a learning objective.** Today, in both repos, practice items and the lessons/objectives they exercise are "two disconnected universes" (RAG: `learning_goals` is required by the schema and read by no code; Ela: no objective/skill entity at all). Mastery cannot aggregate above a single item without this link. Part 3 makes the objective the unit of mastery.

---

## Part 3 — The scheduling and mastery model (concrete and implementable)

This is the heart of the engine and the part both repos most need. It is specified concretely enough to implement and test.

### 3.1 The item-state model (replaces both current schemas)

Each `(learner, item)` pair carries, at minimum:

```
stability        float   # days; expected time until recall prob. falls to the retrieval threshold
difficulty       float   # per-item, per-learner; how fast stability grows on success
due_at           datetime
last_reviewed_at datetime
reps             int      # successful reviews
lapses           int      # failures after graduation
state            enum {new, learning, review, relearning, mastered}
last_grade       enum/int # the graded outcome (see 3.3)
objective_id     FK       # the skill/objective this item exercises  ← the Rule-B link
```

This is the FSRS/SM-2 shape. It adds `stability` and `difficulty` columns that neither repo has today, and — critically — an `objective_id` foreign key so mastery can aggregate.

### 3.2 The scheduler: stability-based, expanding, with fuzz

Recommendation: **FSRS-style** (free spaced repetition scheduler) rather than raw SM-2, because it models a retrievability curve explicitly and is straightforward to reason about; SM-2-with-fuzz is an acceptable simpler fallback. The behaviour the algorithm must exhibit (these are the acceptance tests):

1. **Intervals expand without bound on repeated success** — the 7-day and 60-day caps are gone. A well-known item can reach months.⟦cite⟧
2. **Failure drops the item into `relearning`** with a short interval and *reduces its stability* (and nudges difficulty up), so a lapsed item is reviewed more often than a never-lapsed one — the current "recompute from `times_seen`" approach loses this history.
3. **Interval fuzz** (±a few %) so items introduced together don't clump on the same future day — a named gap in both repos.
4. **A daily new-item cap and a daily review cap**, per learner and lower for children, so load stays bounded (Invariant 4).
5. **Deterministic given `(state, grade, now)`** — `now` always injected, never read from the clock inside the function (RAG already does this; keep it — it is what makes the scheduler testable).

### 3.3 Graded outcomes → scheduler input

The scheduler consumes a **grade**, not a boolean. The mapping from each material type's native score to the grade is app-owned and explicit:

| Native outcome | Grade |
|---|---|
| Deterministic correct, fluent (fast, no hint) | `easy` / 4 |
| Deterministic correct | `good` / 3 |
| Correct with hint, or partial credit above a threshold | `hard` / 2 |
| Incorrect / below threshold | `again` / 1 |

Rubric-scored tasks map their 0–100 total onto this 4-point scale with fixed, documented cut-points. Deterministic sub-signals (a maths answer wrong, a required STAR part missing, describe-image numbers inaccurate) override any model opinion downward — the model may never *raise* a grade above what the deterministic check allows. This directly implements Invariant 5 and unblocks Rule A.

### 3.4 Mastery — earned, evidence-based, retention-gated, revocable

Mastery is a property of an **objective**, computed from the states of the items that exercise it. An objective is `mastered` when:

- a **minimum number of successful retrievals** of its items have occurred (≥3, matching Ela's existing `MINIMUM_SAFE_MASTERY_REVIEWS`), **and**
- those successes are **spaced across a real elapsed retention interval** (e.g. the item's stability has passed a floor of ~14–21 days) — so mastery cannot be "climbed" in a single sitting by advancing the clock, which is the accidental-not-designed weakness the RAG map flags, **and**
- the learner's recent **graded outcomes** on the objective's items are strong (no current lapse).

Mastery is **revocable**: a subsequent lapse demotes the objective out of `mastered` into `relearning` ("a lapse must be re-earned" — RAG already says this at the item level; Ela currently makes `mastered` absorbing/terminal, which is wrong and must change). This is the demotion path Invariant 2/6 requires.

### 3.5 What this replaces, per repo

- **Ela:** replace the `12h/1d/{1d,3d,7d}` `match` in `UpdateLearnerItemStatesAfterSession.php` and add stability/difficulty/lapses columns + `objective_id` to `learner_item_states`. Keep the excellent rubric-priority and cooldown machinery — it becomes a *modifier* on the new scheduler, not the scheduler itself. Make `mastered` non-absorbing.
- **RAG Prototype:** replace the fixed Leitner ladder in `spaced_repetition.py` with the same model; change `update(state, correct: bool, ...)` to `update(state, grade, ...)`; give item state a real FK to an item and an objective (today it's a bare string with no referential integrity). Unify the two schedulers on one algorithm so the two products behave identically.

---

## Part 4 — Per-audience adaptation

Everything above is shared. Here is where the four audiences genuinely diverge. For each: who the learner is, what content types dominate, how the session is shaped, how scheduling/mastery is tuned, where feedback comes from, and what is non-negotiable.

### 4.1 PTE / IELTS test-takers

**Learner.** Adult, motivated, deadline-driven (a real test date), needs a *band/score* not just "knowledge," and self-assessment of their own speaking/writing is unreliable.

**Content.** Extended writing (essay, summarise-written-text), describe-image, reading MCQ, speaking tasks; each tied to the official rubric traits. RAG Prototype already generates most of these.

**Session shape.** Two modes: *skill-building* (interleaved short tasks, immediate elaborated feedback) and *mock/exam-condition* (timed, feedback deferred to the end — matching real conditions and the delayed-feedback evidence). Hard-start–jump-to-easy is taught as a test-day tactic but only where the format allows revisiting (flag that computer-adaptive sections don't).

**Scheduling/mastery tuning.** The organising unit is the *band descriptor / rubric trait*, not a vocabulary item. Mastery = consistently hitting the target band on that trait across spaced, timed attempts. Deliberate practice targets the learner's specific weak descriptor (Invariant 3 + the book's "attack your weakness").

**Feedback source.** Deterministic wherever possible (word count, required structure, describe-image numeric accuracy, banned patterns like "split the sentence" for SWT), rubric model judge for the rest, **clearly labelled** and never shown as a certified mark while the grader's self-tests fail (RAG's existing banner rule).

**Non-negotiable.** A countdown to the test date that (a) shifts the mix toward full timed mocks as the date approaches, (b) schedules a sleep reminder the night before, and (c) rehearses breathing/reframing in the weeks prior. The test-prep checklist (Technique 27) is a literal feature.

### 4.2 Adult language learners (Spanish, Japanese, English, …)

**Learner.** Adult, often self-directed, long horizon, no single deadline; wants durable usable language, not test points.

**Content.** Phrase-chunks first (Ela's thesis, and well-supported: formulaic sequences and collocations carry disproportionate communicative load⟦cite⟧), then words, then sentence patterns; comprehension and production both directions. Vocabulary coverage thresholds matter (functional text coverage needs a large known-word base⟦cite⟧), so *volume plus spacing* is the regime.

**Session shape.** The canonical Ela workflow (prime → focused block → mixed recall + interleaving → wrap-up → schedule) is already right. Comprehensible-input framing: new items introduced in understandable context, not as bare pairs.

**Scheduling/mastery tuning.** This is the classic SRS home turf — long expanding intervals, big banks, daily new-item cap to control load. Mastery per lexical item is fine here (objective ≈ the item), but group by semantic/lexical family (Ela already does) to interleave confusable forms. Production (use it in a sentence), not just recognition, is required to graduate (Invariant 1).

**Feedback source.** Deterministic for form (spelling, conjugation, exact/pattern match); model rubric for usage naturalness with a deterministic fallback (Ela's coach + rubric already do this). Corrective feedback on errors is explicit and elaborated.

**Non-negotiable.** Real phrase-chunk content must exist — today Ela's 17,631-item seeded library is 100% single `word` items, so the entire phrase-first design has nothing to run on. Content supply is the binding constraint for this audience.

### 4.3 Interview / job-prep candidates

**Learner.** Adult, specific near-term goal (a role), needs to *perform under pressure and think on their feet*, not recall facts. Highest-variance audience for "what counts as correct."

**Content.** Behavioural questions (STAR-structured answers), role/technical questions, company-specific prep. Answers are *performed*, mostly spoken.

**Session shape.** Rehearse-and-review loops: draft an answer, leave it (diffuse mode / overnight), redraft, deliver aloud, review the recording. Interleave behavioural/technical/situational rather than drilling one type (Invariant 3). Deliberate practice on the one question that unsettles them.

**Scheduling/mastery tuning.** The objective is a *competency* (e.g. "conflict-resolution story," "system-design fundamentals"), exercised by several question variants. Spacing applies to *rehearsal* — a story rehearsed once is not retained; space the re-deliveries. Mastery = delivering a structured, complete answer to an unseen variant of the competency, spaced.

**Feedback source.** Deterministic structure check (did the answer contain all STAR parts? was it within a time bound?) as the backbone; model rubric for content/impact; peer/mock-interview human feedback strongly encouraged (Invariant 5 — self-assessment of one's own delivery is unreliable). Arousal-reappraisal ("reframe nerves as excitement") is taught and rehearsed, as the book prescribes.⟦cite⟧

**Non-negotiable.** A capture path for spoken answers (record, optionally transcribe) — this audience cannot be served by typed input alone. Structured-answer scaffolding that fades: full STAR template → prompts for each beat → free delivery.

### 4.4 Children (early maths and reading)

**Learner.** Young, shorter attention span, still developing metacognition and self-regulation, cannot reliably self-grade, and needs a parent/guardian in the loop. This is the audience *least* like the others and the one entirely absent from both codebases today (Ela has an unused `age_group` string; RAG's maths pack targets Year-5 content but has no child-specific *learner* model).

**Content.** Early numeracy (the RAG maths generators: fractions, times tables, reasoning with bar models) and early literacy (decoding/phonics, sight words, reading comprehension). Reading instruction follows the evidence base for systematic synthetic phonics within a broader "reading rope" of word-recognition + language-comprehension strands.⟦cite⟧

**Session shape.** *Short* — 5–10 minute sessions, far fewer new elements per sitting (Invariant 4 cap is lowest here), one phonics/maths pattern at a time before interleaving. Heavy scaffolding (worked example / blend-shown-first) that fades slowly. Play/movement between bursts (the book's daily-short-bursts-with-play advice; also serves focused/diffuse).

**Scheduling/mastery tuning.** Same stability-based scheduler but with a lower daily cap, gentler difficulty growth, and mastery defined conservatively (retention-gated, revocable — a child who "had it last week" and lapsed must be brought back). Objective = a concrete skill ("add fractions with like denominators," "decode CVC words with short *a*").

**Feedback source.** **Deterministic first, always** — children cannot self-grade, and self-grading is explicitly ruled out here (Invariant 5). Maths uses the exact `Fraction`/numeric checkers RAG already has. Reading ideally uses ASR or a parent-scored path; where neither exists, keep interactions recognition-and-structure-checkable rather than self-reported. Feedback is warm, specific, and never punitive.

**Non-negotiable (and genuinely new build):** a **parent/guardian account and oversight surface** (progress visibility, session setup, consent), age-appropriate simplified UI (large targets, minimal text, audio support, no time pressure by default), COPPA-style consent and data-minimisation, and reading-level-controlled language in every generated string (RAG's `reading_level` evaluator is the seed of this but is inert for anything but maths today). Because Ela's docs name generalisation — and specifically children — as an explicit *non-goal* in three places, **this audience requires a documented product decision (an ADR) before any code moves.**

---

## Part 5 — Where this lives in the code (pointer; full plan in `03_implementation_plan.md`)

The two repos already split cleanly along the right seam, and the pedagogy layer respects it:

- **RAG Prototype = the offline content-and-grounding backend.** It generates items, worked examples, distractor rationales, and objectives from a source (book/PDF/rubric), and it verifies them with deterministic-first checks and the honesty gate. The pedagogy work here is: make `learning_goals`/objectives *real and linked* to items (Rule B), enforce worked-example completeness and fading metadata, extend the deterministic checkers per material type, and stop the enrichment layer from being PTE-shaped by default.
- **Ela = the learner-facing product that owns state.** It owns identity, sessions, the scheduler, mastery, progress, and the UI. The pedagogy work here is: replace the scheduler with the stability model (3.2), accept graded outcomes (3.3), make mastery revocable and objective-level (3.4), capture pre-answer confidence (Invariant 6), add the daily caps and per-audience session shapes (Part 4), and build the children/parent surface and the test-date countdown.

The one architectural principle both must honour, and both already state in their own words: **the application owns learner state; AI assists but never owns memory, scheduling, or the right/wrong decision.** Every invariant above is designed to be enforced in deterministic app code, with the model confined to elaboration and to genuinely-open scoring that is always labelled and always deterministically bounded.

---

*Next documents: `02_ux_spec.md` (per-audience interface and session design) and `03_implementation_plan.md` (sequenced changes against the real files). Citations for every ⟦cite⟧ claim are collected in `04_research_citations.md`.*
