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
