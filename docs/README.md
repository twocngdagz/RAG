# Documentation

The system turns a book PDF into grounded, teaching-enriched learning material,
stores it, serves it over an API, and renders it in the frontend.

```
PDF ─▶ grounded base ─▶ [store · API] ─▶ enrichment (teaching layer) ─▶ frontend
       (generation +                     (ChatGPT project +
        audit + eval)                     strict schema)
```

## Stage docs

| # | Stage | Doc |
|---|---|---|
| 1 | **Grounded-base generation, audit, evaluation** (PDF → `book_learning_materials.v2`) | [generation-pipeline.md](generation-pipeline.md) |
| 2 | **HTTP API contract** (serving stored materials) | [API.md](API.md) |
| 3 | **Enrichment workflow** (grounded base → teaching-first Coach layer) | [enrichment-workflow.md](enrichment-workflow.md) |
| — | Enrichment prompt — verbatim ChatGPT project instructions | [enrichment-prompt.md](enrichment-prompt.md) |
| — | Enrichment prompt — reusable **engine** (book-agnostic) | [enrichment-engine.md](enrichment-engine.md) |
| — | Enrichment prompt — **PTE domain pack** (swappable per book) | [enrichment-domain-pte.md](enrichment-domain-pte.md) |
| 4 | **Class lessons** (enriched chapter → one class lesson per concept, run by `run_class_lessons.py`) | [class-lesson-contract.md](class-lesson-contract.md) |
| — | Whole-book lesson generation (overview) | [WHOLE_BOOK_LESSON.md](WHOLE_BOOK_LESSON.md) |

The top-level `README.md` is the full chronological history (including legacy
exploratory steps); the docs above are the focused references for the current path.

## Reusing the system for a new book

Generation/audit/evaluation is already book-agnostic — point it at a new PDF.
For enrichment, keep the [engine](enrichment-engine.md) and write a new domain pack
(copy [enrichment-domain-pte.md](enrichment-domain-pte.md)); see the "Reusing" notes
in [enrichment-workflow.md](enrichment-workflow.md).
