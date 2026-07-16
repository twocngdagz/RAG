# Grounded-Base Generation Pipeline (generation · audit · evaluation)

How a raw book PDF becomes the **grounded base** learning material
(`output/<slug>.chapterNN.book_learning_materials.json`) that storage, the API,
the frontend, and the enrichment stage all build on.

This is the pre-enrichment half of the system. For the teaching layer that sits on
top of this, see [enrichment-workflow.md](enrichment-workflow.md).

> The exhaustive, chronological history (including ~30 legacy exploratory steps)
> lives in the top-level `README.md`. This file is the **focused reference** for
> the current canonical path. Run any script with `--help` for the full flag set.

## Design in one line

Turn a PDF into structured learning material where **every generated claim is
traceable to exact source text**, then *deterministically prove* that grounding
before the material is trusted. Generation is an offline batch job run once or
twice per book — quality matters far more than throughput.

## Pipeline

```
input/pdfs/<book>.pdf
      │  generate_book_learning_materials.py <pdf>
      │    orchestrates PDF prep (chunks → outline → sections → clean index)
      │    then per-chapter grounded generation against the contract
      ▼
extracted/<slug>.section_clean_chunks.json      ← the clean evidence index
output/<slug>.chapterNN.book_learning_materials.json   ← the grounded base (v2)
      │
      ├─ validate_book_learning_materials_contract.py   deterministic schema/contract
      ├─ extract_book_learning_claims.py                claims → resolved evidence
      ├─ audit_book_claim_support.py                    semantic support judge
      ├─ evaluate_targeted_book_learning_materials.py   semantic + coverage eval
      └─ repair_book_learning_materials.py              fix unsupported/damaged claims
      ▼
book_learning_materials_store.py → FastAPI (learning_materials_api.py) → frontend
      ▼
(then) enrichment-workflow.md  ← teaching layer on top of the grounded base
```

Contract / schema source of truth: `book_learning_materials_contract.py`
(`book_learning_materials.v2`).

## Stages

### 1. Generate (PDF → grounded base)
`generate_book_learning_materials.py` is the orchestrator. It runs the PDF-prep
sibling scripts (chunking, outline, section detection, clean index) via subprocess,
then generates each chapter against the grounding contract.

```bash
python generate_book_learning_materials.py input/pdfs/pte.pdf \
  --backend claude-cli --claude-model sonnet \
  --chapter-number 7 \
  --output output/pte.chapter07.book_learning_materials.json \
  --report output/pte.chapter07.report.txt
```
Key flags: `--backend {nvidia,claude-cli,codex-cli}`, `--chapter-number` /
`--max-chapters`, `--model-max-tokens` (default 8000), `--continue-on-chapter-error`,
`--resume-missing-chapters`, `--prepare-only` / `--skip-prepare`,
`--model-timeout-seconds`, `--model-max-retries`. Full list: `--help`.

Backends run under a subscription/local model (no metered API): `claude-cli` shells
to `claude -p`; `codex-cli` to `codex exec`; `nvidia` is the original metered path.

### 1a. Pre-generation safety — damaged chunks
```bash
python scan_clean_chunk_damage.py   # flags empty / word-dropped clean chunks
```
Run before generation; a damaged source chunk produces `SOURCE_DAMAGED` audit
results downstream.

### 2. Validate the contract (deterministic)
```bash
python validate_book_learning_materials_contract.py \
  --book-file output/pte.chapter07.book_learning_materials.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.chapter07.contract.json
```
Checks the artifact conforms to `book_learning_materials.v2` (shape, required
fields, origin/evidence bookkeeping). No model involved.

### 3. Extract claims → evidence
```bash
python extract_book_learning_claims.py \
  --book-file output/pte.chapter07.book_learning_materials.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.chapter07.claims.json
```
Resolves each claim's cited `source_chunk_ids` against the **full clean chunk
text** (never the `text_preview`). Records citation origin: `local`,
`inherited_chapter`, or `none`. Prepares evidence; does not judge support.

### 4. Semantic claim-support audit
```bash
python audit_book_claim_support.py \
  --input output/pte.chapter07.claims.json \
  --output output/pte.chapter07.audit.json
```
A semantic judge decides, per claim, whether the **exact cited evidence** supports
it. It sees only the claim + its resolved evidence — no PDF re-open, no retrieval,
no external knowledge. Statuses: `SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`,
`CONTRADICTED`, `SOURCE_DAMAGED`, `NOT_A_FACTUAL_CLAIM`. This is what makes the
"grounded" label trustworthy.

### 5. Evaluate (semantic + coverage)
```bash
python evaluate_targeted_book_learning_materials.py \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.chapter07.eval.json
```
Judges teaching quality and how well the material covers the source. Flags:
`--evaluation-chapter-number`, `--max-new-evaluation-chapters`,
`--reevaluate-selected-chapter`, `--checkpoint`.

### 6. Repair (optional)
```bash
python repair_book_learning_materials.py \
  --book-file output/pte.chapter07.book_learning_materials.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.chapter07.repaired.json
```
Regenerates or nulls claims the audit found unsupported/contradicted/damaged, so
the grounded label stays honest.

## Grounding model (two ideas that make "grounded" mean something)

- **Every claim carries provenance** — `origin` (source_grounded /
  pedagogical_generation / insufficient_source_evidence), `source_chunk_ids`, and
  `evidence_spans`. See `Grounded` in the contract and `frontend/src/lib/types.ts`.
- **Support is proven, not assumed** — a valid chunk ID does not prove the text
  supports the claim; stage 4 judges *evidence support* explicitly. A cited-but-
  unsupported claim is caught, not trusted.

## Where the deeper docs are

| Topic | Location |
|---|---|
| Whole-book lesson generation (overview) | `docs/WHOLE_BOOK_LESSON.md`, `README.md` §"Generate Whole Book Lesson" |
| Generation contract | `README.md` §"Grounding-Aware Whole-Book Generation Contract" |
| Claim extraction / semantic audit | `README.md` §"Whole-book claim evidence extraction" / §"…semantic claim support audit" |
| Targeted v2 evaluation | `README.md` §"Targeted v2 semantic and coverage evaluation" |
| HTTP API contract | `docs/API.md` |
| Storage → API → frontend, enrichment | `docs/enrichment-workflow.md` |
