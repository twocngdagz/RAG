# Lesson Enrichment Workflow

Turns a grounded, reference-like lesson into a teaching-first lesson (the "Coach"
view) by driving a ChatGPT project as the generation backend, then storing and
serving the result.

## Pipeline

```
output/pte.chapterNN.book_learning_materials.json   grounded base (source-faithful)
        │  enrich_lessons.py build_payload(n)
        │    → clean teaching text + SCHEMA_CONTRACT (exact output shape)
        ▼
   ChatGPT project  (fresh chat per lesson)
        │    ← project Instructions = docs/enrichment-prompt.md (the "engine")
        │  chatgpt_browser_driver.py: type payload → wait → scrape ```json block
        ▼
   normalize_document → validate_enrichment (strict, pte_lesson_enrichment.v1)
        ▼
   output/pte.chapterNN.enrichment.json  →  DB (learning_material_enrichments)
        →  FastAPI (/books/{slug}/chapters/{n}/enrichment)  →  frontend Coach tab
```

## Where the "instructions" live (two layers)

| Layer | What | Where |
|---|---|---|
| **Per-lesson message** | the grounded base + output contract sent for each lesson | in code — `enrich_lessons.py` (`build_payload`, `SCHEMA_CONTRACT`) |
| **Standing project prompt** | "you are a lesson-enrichment engine…" applied to every chat | ChatGPT project settings → copied verbatim into `docs/enrichment-prompt.md` |

The output schema is intentionally asserted in **both** the project prompt and
`SCHEMA_CONTRACT`. Keep them in sync; the code copy is what makes a run robust
even in a fresh chat with no history.

## Commands

```bash
# one-time: log the automation's dedicated Chrome profile into ChatGPT
python chatgpt_browser_driver.py login

# inspect the message that would be sent for a lesson (no browser)
python enrich_lessons.py payload 8

# enrich one or more lessons: drive ChatGPT → scrape → validate → store
caffeinate -is python enrich_lessons.py run \
  --project-url "https://chatgpt.com/g/g-p-6a4c9da8…-pte/project" 5 6 7

# load an enrichment JSON already produced by hand
python enrich_lessons.py load 8
```

Notes:
- **Headed, not headless** — ChatGPT renders differently under headless Chrome, so
  the driver runs a visible window. It reuses one window across a batch.
- **`caffeinate -is`** prevents system sleep so a long run survives a locked Mac.
- Point `--project-url` at the **project** URL (ends `/project`) so each lesson
  gets a fresh, prompt-primed chat (no cross-lesson context bleed).
- Failures save the raw reply to `output/_lessonNN.reply.txt` and are reported at
  the end (`FAILED: [...]`) for a targeted re-run.

## Fact audit (checking the exam facts against Pearson)

The enrichment layer's value comes precisely from facts added *beyond* the book —
timings, word counts, scoring traits — so nothing in the grounded pipeline can
verify it. `audit_enrichment_facts.py` checks those facts against the official
Pearson Score Guide PDF.

```bash
python test_audit_sensitivity.py          # FIRST — is the audit awake?
python audit_enrichment_facts.py          # then audit all lessons
python audit_enrichment_facts.py --chapters 7 15
```

**Run the sensitivity test first, and read a clean audit as meaningless without
it.** It plants claims whose truth is already known and asserts the verdicts. The
audit has quietly done nothing three separate times:

| Defect | Effect |
|---|---|
| Evidence truncated at 9K chars while the report printed the full page list | Judged lessons on a third less rulebook than claimed; invented a contradiction against Write Essay |
| `scoring_factors` rolled into "this task is scored on these traits: …" | Tested a claim the lesson never made; every combined lesson failed it |
| Trait list read from p.15, which names *every* task's traits | Masked genuinely wrong trait names |

### What is judged vs. what is code

The model judge handles open-ended wording. Anything mechanical is deterministic,
because the judge proved unreliable at it:

- `check_trait_vocabulary` — a lesson may describe scoring in its own teaching
  words ("Main-idea coverage"); those are unfalsifiable and ignored. But if it
  uses one of Pearson's **actual** trait names, that trait must belong to the
  task. The judge would not treat the guide's "Traits scored" list as closed no
  matter how the prompt was worded, and forcing it destabilised every other
  verdict.
- `check_word_range` — where the guide gates Form on a word range, the lesson
  must **state** that range. Lesson 15 shipped telling learners to "verify
  word-count compliance" while never saying what the count was; a check that only
  compares stated numbers would have passed it, because the bug was an absence.

Measured: at `temperature 0` the judge returned `NOT_IN_GUIDE` for a plainly
contradicted word range in **3 of 4 runs**, a different case each time. Those
verdicts are reported but advisory — they do not decide the test's exit code, and
`check_word_range` covers the same class of error 5/5. Do not move a check back
onto the judge without re-measuring.

`NOT_IN_GUIDE` is not a defect — the guide does not state every timing — but it
marks a claim as unverified, which is worth knowing.

## Plan limits (this can and did restrict the account)

Each lesson is a **30–60K-character generation** — a full book (with retries) can
consume a day's plan allowance even though the request *rate* looks human. The
run command mitigates this:

- **Every request is paced, not just failures.** `--cooldown` / `--cooldown-max`
  (default **300–600s, i.e. 5–10 min**) wait after *each* lesson before sending
  the next. The pause is randomised inside that window rather than fixed, so the
  cadence isn't a metronome. `--cooldown 0` disables it.
  Budget the elapsed time: 19 lessons × ~7.5 min average ≈ **~2.5 hours of waiting**
  plus generation — designed for an unattended overnight run, where wall-clock is
  free and steady pacing is the point.
- **Every lesson is checked twice before it is stored.** Layer 1 is the
  structural contract (`validate_enrichment`: all sections present, right shape).
  Layer 2 is the factual checks (`check_lesson_facts` → word range, trait names,
  worked-example rules) against the official guide. A lesson must pass BOTH.
- **A rejected lesson is re-generated, not dropped.** `--max-attempts` (default 3)
  asks again rather than leaving a hole — an unattended run has no human to
  re-run a dud. Between attempts it waits the normal 5–10 min pace.
- **Restriction detection → long backoff, not abort.** If ChatGPT shows a limit
  notice ("you've reached your limit", "usage cap", …), the run waits
  `--limit-backoff` (default **1800s = 30 min**) and retries **the same lesson**,
  instead of ending the batch. A capped account needs time, not another attempt —
  but an overnight run should survive a cap, not die at 3am.

Budgeting guidance: prefer one book per day; if a batch is interrupted by a cap,
resume after the limit window resets (per-lesson file+DB checkpointing means
nothing is lost). Avoid immediately re-running failed lessons back-to-back — each
retry is another full-size generation.

## Reusing this for a different book / exam

The system is **engine (reusable) + domain pack (swappable)**:

**Reusable as-is** — the pipeline, the `pte_lesson_enrichment.v1` schema (generic
teaching structures), the strict OUTPUT CONTRACT, and the QUALITY STANDARDS.

**Swap for a new domain** (in `docs/enrichment-prompt.md` and, where noted, code):
- the AUDIENCE line ("PTE Academic / CEFR B1–C1")
- the task-type list in INPUT PROTOCOL and the whole `TASK-TYPE ADAPTATION` section
- the `EXAMPLE` block (currently a PTE essay)
- `schema_version` / `source_label` literals if you want a non-PTE label
- the "well-established facts you may add" guidance (PTE word counts, scoring traits)

Reusable ≠ generic: the *authority* of the output (the accurate exam facts added
"beyond the book") comes from that domain pack. A prompt with no domain knowledge
produces thinner, less trustworthy enrichment. So for a new book, write a new
domain pack rather than stripping the domain out.
