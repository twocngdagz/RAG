> **NONCANONICAL RESEARCH INPUT.** This document is a dated observation or synthesis,
> not a decision. It does not adopt anything. Only the authorities listed in
> `docs/research-rule-classification.md` are authoritative — that list includes the
> requirements and architecture guidelines, not only ADRs and plans.
>
> Captured 2026-07-26 · RAG `296d6b5` · Ela `da188c5`

# Product & UI/UX Spec — Per Audience

### Turning the pedagogy invariants into interface and session design

**Purpose.** `01_pedagogy_guidelines.md` says *what must be true* about learning. This document says *what the learner sees and does*. It specifies the shared interaction shell, then the four audience-specific surfaces, then the cross-cutting systems (progress/calibration, motivation, accessibility), and finally which repo owns which screen. It is written to be buildable against the real code: every screen maps to something Ela already has (to extend) or names as a genuinely new build.

Design constraint carried from the recon: Ela's UI is *not* a scaffold — it is ~11,000 lines of bespoke page code with a 3,702-line runtime and a 1,358-line priming screen, all currently English-vocabulary-shaped and single-audience. The move is to **generalise the existing surfaces behind an audience concept**, not to build four separate apps.

---

## Part 1 — The shared shell (one engine, four skins)

All four audiences share the same underlying loop, because the engine is shared:

**Prime → Focus session (learn-phase where needed → retrieval) → Feedback → Wrap-up → Scheduled return.**

This is exactly Ela's existing flow. What changes per audience is the *content of each step, the density, the language, the timing, and the framing* — not the skeleton. Three shell-level decisions govern everything below.

**1. Audience is a first-class dimension of the learner profile.** A learner (or, for a child, their parent) picks a track: *Exam (PTE/IELTS) · Language · Interview · Kids*. This selects a **preset** — a bundle of session-length defaults, new-item caps, exercise-type palette, feedback sources, motivation framing, and theme tokens. Presets are data, not forks in the code. Ela's `learner_profiles` already has `primary_learning_context`, `age_group`, `learner_level`, `preferred_explanation_style` — the preset reads these; today nothing does.

**2. The session-composer and scheduler are the same code for everyone** (per `01`, Part 3). The preset only supplies *parameters* (caps, weights, allowed exercise types, mastery-interval floor). This keeps the "app owns state" guarantee intact and means a scheduler fix helps all four audiences at once.

**3. Every generated string is reading-level-controlled and domain-labelled.** The provenance/scoring-disclosure discipline (green "from the source" vs amber "practice/AI," `scored_by` labels) is shown to *all* audiences, in age-appropriate words. Learners always know what is fact vs. generated, and what was marked by code vs. by a model.

### The session-runtime states (generalised from Ela's runtime.tsx)

```
draft → primed → in_progress(learning? → retrieval → per-item feedback) → completed(wrap-up) → [scheduled return]
```

The single most important control in the whole product is the **response input** on the retrieval step. Today Ela renders a raw three-way radio (Correct/Partial/Incorrect) that the *learner* sets — a self-grade. Per Invariant 1 & 5 this changes: the learner **produces a response** (types, selects, speaks, or writes) and the **system grades it** wherever a deterministic check exists; self-rating survives only as an optional confidence prediction (Invariant 6) captured *before* the reveal, never as the thing that moves the schedule for checkable content.

---

## Part 2 — Audience surfaces

Each subsection specifies: the **home/dashboard**, the **session setup & priming**, the **retrieval interaction**, the **feedback surface**, and the **framing/tone**.

### 2.1 Exam track — PTE / IELTS

**Home.** Dominated by a **test-date countdown** and a **band-tracker**. The hero is "X days to your test," with today's recommended session and a readiness signal per rubric trait (e.g. Writing–coherence, Speaking–fluency), each shown as *current estimated band vs target band* — demonstrated, not self-declared. A "weakest descriptor" card drives deliberate practice (Invariant 3).

**Setup & priming.** Two clearly separated modes:
- *Skill build* — short, interleaved tasks across task types, immediate elaborated feedback.
- *Full mock* — timed, exam-condition, feedback withheld to the end (matches real conditions and the delayed-feedback evidence). As the date nears, the recommended mix shifts from skill-build toward full mocks.

Priming reuses Ela's "Today's Study Preview" pattern (session facts, preview items, weak-area card, expected benefit) plus a test-day-tactic reminder when relevant (hard-start–jump-to-easy where the format allows; flagged off for computer-adaptive sections).

**Retrieval interaction.** Task-type-specific runners — most already exist in RAG Prototype's frontend and should be ported/shared: essay (exam timer, live word count, trait bars, ideas-vs-language split, inline corrections), summarise-written-text, describe-image (inline SVG chart + spoken/typed response), reading-MCQ (answer first, per-option rationale after submit). Speaking tasks add a **record** control.

**Feedback surface.** The trait-scored card with **explicit `scored_by` labels per trait** (code vs model), deterministic sub-checks called out (word count, structure, numeric accuracy), and a banner suppressing any score whose grader self-test is currently failing (RAG's existing rule). Errors listed with correction and a single "next focus."

**Framing.** Outcome-aware but process-scheduled: "you've done 3 timed Writing tasks this week; coherence is trending up." Countdown schedules the **sleep-before-test reminder** and **breathing-rehearsal** sessions in the weeks prior (Technique 23/27). The 12-item test-prep checklist is a literal screen the learner ticks honestly.

### 2.2 Language track — Spanish / Japanese / English / …

**Home.** A **retention-and-coverage** dashboard: items due today, current stable vocabulary size (demonstrated retention, not "items seen"), streak, and topic/family coverage. Phrase-chunks foregrounded over single words (the phrase-first thesis).

**Setup & priming.** Ela's existing priming screen, essentially unchanged — it is already well-built for this audience. Duration presets (10/15/20 now; extend upward for keen learners), main-topic lane, weak-area card, queue-quality linter (keep it — it's genuinely good). New items introduced in understandable context, not bare pairs (comprehensible-input framing).

**Retrieval interaction.** Both directions (meaning→form and form→meaning) and, to graduate an item, **production in a sentence** — not recognition alone (Invariant 1). Confusable lexical/morphological families interleaved but sibling-crowding avoided (Ela already reserves against this). Optional coach question per item (Ela's coach agent exists).

**Feedback surface.** Deterministic for form (spelling, conjugation, exact/pattern match); model rubric with deterministic fallback for usage naturalness (Ela already has both, with `scored_by` disclosure). Elaborated corrective feedback on errors.

**Framing.** Long-horizon, habit-first: daily streak, "a little every day," pre-sleep and next-day review nudges via scheduled tasks. No deadline pressure. Process goals ("clear today's reviews") over outcome nagging.

**Content dependency (call it out on the roadmap, not the UI).** This track needs real phrase-chunk content; the current 17,631-item library is 100% single words. The UI can ship, but the experience is hollow until the content pipeline produces phrases.

### 2.3 Interview track — job / behavioural prep

**Home.** A **competency board**: the target role's competencies (behavioural, technical, situational) as cards showing rehearsal recency and readiness. "Weakest / least-rehearsed competency" surfaced for deliberate practice. A prep countdown if an interview date is set.

**Setup & priming.** Pick competencies to rehearse; the composer interleaves types (behavioural/technical/situational) rather than blocking. Priming frames the *rehearse-and-review* loop and, where a draft exists from a prior day, surfaces it for redraft (diffuse-mode/overnight gain).

**Retrieval interaction.** The defining new capability: **spoken-answer capture** (record; optionally transcribe). Answer construction uses a **fading STAR scaffold** — first the full Situation/Task/Action/Result template with prompts, fading to bare beat-labels, fading to free delivery under a time bound. A deterministic structure check runs on the transcript/notes ("did all four STAR parts appear? within time?").

**Feedback surface.** Structure check (deterministic, backbone) + content/impact rubric (model, labelled) + a strong nudge toward **human/mock feedback** (self-assessment of delivery is unreliable — Invariant 5). Playback of the recording for self-review. Arousal-reappraisal prompt ("reframe nerves as excitement") rehearsed, not just stated.

**Framing.** Performance-under-pressure: rehearsals spaced (a story told once isn't retained), confidence prediction before delivery, calibration surfaced. Breathing/reframing rehearsal scheduled before a known interview date.

### 2.4 Kids track — early maths & reading (the largest new build)

This audience is absent from both codebases and is the least like the others; it gets the most new UI and a **parent surface**.

**Two accounts, two surfaces.**
- **Parent/guardian surface** — account creation and consent (COPPA-style, data-minimisation), child profile setup (age band, reading level, goals), session-length and daily-cap controls, and a **progress view** showing demonstrated mastery per skill, current weak skills, and time-on-task. Parents set up and oversee; they do not do the child's grading.
- **Child surface** — radically simplified: large touch targets, minimal on-screen text, **audio support** for all instructions (a young reader can't be gated on reading the UI), no default time pressure, warm non-punitive feedback, one clear action at a time.

**Home (child).** A short, friendly "today's practice" with a small number of items and a visible, gentle progress indicator (stars/path, not percentages). Sessions are **5–10 minutes**.

**Setup & priming.** Mostly parent-configured; the child sees a one-tap start. New elements per session are capped low (Invariant 4's lowest cap); one phonics or maths pattern at a time before interleaving.

**Retrieval interaction.**
- *Maths* — produce the answer + working; graded by RAG's exact `Fraction`/numeric checkers. Bar-model-in-words shown before arithmetic (the maths pack already demands this; nothing enforces it — now it's a UI requirement). Heavy worked-example scaffolding that fades slowly.
- *Reading* — decoding/phonics with **audio**: hear the target, decode aloud (ASR where available, else a parent-scored or recognition-and-structure path — never child self-report), sight-word and comprehension checks. One grapheme/pattern at a time.

**Feedback surface.** **Deterministic first, always** (children cannot self-grade). Warm, concrete, immediate: "You added the tops right — now let's make it simpler." Errors framed as the next thing to try, never as failure. Reading-level-controlled language in every string (RAG's `reading_level` evaluator generalised beyond maths).

**Framing.** Play between short bursts, movement encouraged, streaks gentle and loss-averse-safe (a missed day doesn't nuke months of progress — see motivation, Part 3). Parent gets the honest progress; the child gets encouragement.

**Gating decision.** Because Ela's docs name generalisation and children as an explicit *non-goal* three times, and because a children's product carries real legal/safety obligations, **this track requires a written product decision (ADR) and a consent/privacy review before build.** Flagged here and in `03`.

---

## Part 3 — Cross-cutting systems

### 3.1 Progress & calibration (the anti-illusion surface)

The book's central warning is that learners mistake fluency for knowledge. The progress UI must therefore refuse to show the metrics that *feel* like progress but aren't.

**Show:** demonstrated retention (retrieval success at a delay), stable mastery per objective/skill, what's due and overdue, weak skills, and **calibration** — the gap between predicted confidence (captured before answers, Invariant 6) and actual accuracy. A "you felt sure on these but missed them" panel is the single most on-thesis feature in the product.

**Don't show as achievement:** items viewed, minutes spent, lessons "completed," or anything self-declared. These are the illusion.

**Code note.** Ela's `BuildLearnerProgressSnapshot` today exposes raw counts and never surfaces `lifecycle_state`/mastery at all, and "weak" means different things in the dashboard (`≥2`) and scheduler (`≥1`) — both must be fixed and unified. There is no dedicated progress page; there should be one per audience (parent-facing for kids).

### 3.2 Motivation (habit loop, done ethically)

From the habit-loop technique, made concrete and *non-manipulative* (wellbeing constraint — no dark patterns, no loss-shaming):

- **Cue + bounded session + small reward.** A daily cue (learner-chosen time), a clearly bounded focus session with a real stop, and a modest completion reward. Pomodoro-style timing available.
- **Streaks that encourage, not punish.** A streak is a gentle nudge with a built-in grace/"freeze" so a single missed day doesn't erase long progress — this matters most for children and for wellbeing generally.
- **Process framing.** Goals are "study 20 minutes / clear today's reviews," never "finish the chapter." Mental-contrasting prompt (where you started vs where you're heading) available for low-motivation moments.
- **Scheduled nudges** (Cowork scheduled tasks): review-due reminders, pre-sleep and next-morning review prompts, and for exam/interview tracks the date-anchored sleep and breathing-rehearsal reminders.

### 3.3 Accessibility & inclusivity

- **Audio-first for early readers** (Kids track can't gate on reading), and audio support available everywhere.
- **Reading-level-controlled generated language**, per audience — the `reading_level` evaluator generalised so it isn't inert outside maths.
- Standard a11y: large targets, keyboard navigation, sufficient contrast (Ela's theme tokens are currently the untouched Laravel starter grayscale with no semantic learning tokens — add tokens for learn/refresh/review, correct/partial/incorrect, weak/overdue, and per-audience theming).
- **Recording/transcription** paths (interview, PTE speaking, kids reading) with graceful fallback where a device lacks a mic.

### 3.4 A visual reference (to build, not yet built)

A single self-contained HTML mock of the **shared runtime retrieval step** rendered four ways (Exam / Language / Interview / Kids) is the most useful visual artifact and is the recommended next tangible deliverable once this spec is approved — it makes the "one engine, four skins" idea concrete and is cheap to produce. (Held for a follow-up so this pass stays document-only per the agreed plan.)

---

## Part 4 — Screen ownership map (Ela vs RAG Prototype)

| Surface | Owner | Status today |
|---|---|---|
| Learner identity, auth, profile, audience preset | **Ela** | auth exists (Fortify); preset concept new |
| Session composer, scheduler, mastery, progress | **Ela** | exists but English-vocab-shaped; needs `01` Part 3 rework |
| Runtime retrieval UI (all tracks) | **Ela** | 3,702-line runtime exists; generalise behind preset |
| Priming screen | **Ela** | 1,358-line screen exists; reusable across tracks |
| Task-type runners (essay/SWT/describe-image/reading-MCQ) | **RAG → shared** | built in RAG's React frontend; port/share into Ela |
| Item, worked-example, distractor, objective generation | **RAG** | exists; needs objective-linking + fading metadata |
| Deterministic checkers (maths/numeric/pattern/structure) | **RAG** | strong for maths & PTE; extend per material type |
| Parent surface + child simplified UI | **new (Ela)** | does not exist |
| Spoken-answer capture (interview, speaking, kids reading) | **new (Ela)** | does not exist |
| Test-date countdown + tactic/sleep/breathing scheduler | **new (Ela + Cowork tasks)** | does not exist |
| Calibration / confidence-gap surface | **new (Ela)** | does not exist |

The seam is clean and worth stating once more: **RAG Prototype makes and verifies content; Ela runs the learner and owns all state and UI.** The four audiences are presets over one shell, not four products.

---

*Next: `03_implementation_plan.md` — the sequenced changes against the actual files, with the scheduler rework, the objective-linking, the graded-outcome plumbing, the audience preset, and the new surfaces, ordered by leverage and dependency. Citations for the ⟦cite⟧ claims in `01` are in `04_research_citations.md`.*
