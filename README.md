# Tiny Learning RAG Prototype

This project is a small prototype for learning-material retrieval.

The first goal is to prove that manually prepared learning chunks can be embedded, indexed, retrieved, and later used as context for generating learning material.

Current scope:

- Use manually prepared chunks for two Year 5 Math topics.
- Keep the prototype minimal.
- Build a local LlamaIndex vector index from the manual chunks.
- Generate one lesson from retrieved chunks using NVIDIA Mistral.
- Expose JSON lesson generation through a tiny FastAPI endpoint.
- Generate structured lesson JSON from a structured PDF index.

## Setup

Create and activate the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the minimal dependencies for the prototype:

```bash
pip install llama-index llama-index-embeddings-ollama llama-index-llms-openai-like python-dotenv
pip freeze > requirements.txt
```

Copy `.env.example` to `.env` later when you are ready to add real local credentials.

## Sample Data

`chunks.json` contains manually prepared Year 5 Math sample chunks for two topics: place value and rounding numbers. This lets the prototype test whether retrieval can separate closely related topics.

## Build The Local Index

Build the local LlamaIndex vector index from the manual chunks using Ollama embeddings:

```bash
source .venv/bin/activate
ollama pull nomic-embed-text
python build_index.py
```

## Test Retrieval

Load the persisted index and print retrieved chunks for a query:

```bash
source .venv/bin/activate
python retrieve_context.py
python retrieve_context.py "What is the value of 7 in 37,421?"
python retrieve_context.py "What common mistake happens with digit value?"
python retrieve_context.py "What is place value and what mistakes do students make?"
python retrieve_context.py "How do you round numbers to the nearest thousand?"
python retrieve_context.py "Generate a lesson about numbers" --topic "Place value"
python retrieve_context.py "Generate a lesson about numbers" --topic "Rounding numbers"
python retrieve_context.py "Give me common mistakes" --content-type "common_mistake"
python retrieve_context.py "Give me examples" --content-type "worked_example"
```

## Generate A Lesson

Generate a lesson from the retrieved chunks using NVIDIA Mistral:

```bash
source .venv/bin/activate
cp .env.example .env
# edit .env and add NVIDIA_API_KEY
python generate_lesson.py
python generate_lesson.py "Generate a Year 5 math lesson about rounding numbers to the nearest thousand."
python generate_lesson.py "Generate a Year 5 math lesson about place value and digit value."
python generate_lesson.py "Generate a Year 5 math lesson about numbers." --topic "Place value"
python generate_lesson.py "Generate a Year 5 math lesson about numbers." --topic "Rounding numbers"
python generate_lesson.py "Generate a short Year 5 math lesson using only worked examples." --content-type "worked_example"
```

## Generate JSON

Generate structured JSON lesson output for later app consumption:

```bash
python generate_lesson_json.py
python generate_lesson_json.py "Generate a Year 5 math lesson about rounding numbers." --topic "Rounding numbers"
python generate_lesson_json.py "Generate a Year 5 math lesson using only common mistakes." --content-type "common_mistake"
```

## Run The API

Expose JSON lesson generation through FastAPI:

```bash
source .venv/bin/activate
pip install fastapi uvicorn
pip freeze > requirements.txt
uvicorn api:app --reload
```

Available content structure:

```bash
curl http://127.0.0.1:8000/structure
```

Default place value lesson:

```bash
curl -X POST http://127.0.0.1:8000/lessons/generate \
  -H "Content-Type: application/json" \
  -d '{}'
```

Rounding lesson using a topic filter:

```bash
curl -X POST http://127.0.0.1:8000/lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a Year 5 math lesson about rounding numbers.",
    "topic": "Rounding numbers"
  }'
```

Common mistake lesson using a content type filter:

```bash
curl -X POST http://127.0.0.1:8000/lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a Year 5 math lesson using only common mistakes.",
    "content_type": "common_mistake"
  }'
```

Structured PDF lesson using a chapter number filter:

```bash
curl -X POST http://127.0.0.1:8000/pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a lesson from Chapter 1.",
    "chapter_number": 1
  }'
```

## API Contract And Smoke Tests

The API contract for future Laravel or frontend usage is documented in `docs/API.md`.

Run the manual smoke test after starting the API:

```bash
./smoke-test.sh
```

## Load A PDF With LlamaIndex

Inspect document text and metadata extracted from one local PDF without indexing it:

```bash
source .venv/bin/activate
mkdir -p input/pdfs
# copy one PDF into input/pdfs/
python load_pdf_with_llamaindex.py "input/pdfs/sample.pdf"
```

The extracted inspection files are written to `extracted/` and are ignored by git.

## Build A PDF Index

Build a separate local LlamaIndex vector index from one text-based PDF using Ollama embeddings:

```bash
source .venv/bin/activate
python build_pdf_index.py "input/pdfs/sample.pdf"
```

PDF indexes are persisted separately under `storage/pdf_<pdf_stem>/` and do not overwrite the manual chunk index at `storage/year5_math_tiny/`.

## Retrieve From A PDF Index

Load a persisted PDF index and print retrieved context using Ollama embeddings:

```bash
source .venv/bin/activate
python retrieve_pdf_context.py "input/pdfs/sample.pdf"
python retrieve_pdf_context.py "input/pdfs/sample.pdf" "What does this PDF say about fractions?"
python retrieve_pdf_context.py "input/pdfs/sample.pdf" "Find practice questions or examples."
```

## Convert A PDF To Chunks

Create one structured chunk per LlamaIndex-loaded PDF document for inspection and later enrichment:

```bash
source .venv/bin/activate
python pdf_to_chunks.py "input/pdfs/sample.pdf"
```

The chunk inspection files are written to `extracted/<pdf_stem>.chunks.json` and `extracted/<pdf_stem>.chunks.txt`.

## Inspect PDF Chunk Structure

Create a rule-based report of possible chapters, sections, headings, and metadata candidates from extracted PDF chunks:

```bash
source .venv/bin/activate
python inspect_pdf_chunks.py "extracted/sample.chunks.json"
```

The structure candidate reports are written to `extracted/<pdf_stem>.structure_candidates.json` and `extracted/<pdf_stem>.structure_candidates.txt`.

## Build A PDF Outline

Reduce noisy structure candidates into a cleaner rule-based outline:

```bash
source .venv/bin/activate
python build_pdf_outline.py "extracted/sample.structure_candidates.json"
python build_pdf_outline.py "extracted/sample.structure_candidates.json" --include-low-confidence
```

The outline reports are written to `extracted/<pdf_stem>.outline_candidates.json` and `extracted/<pdf_stem>.outline_candidates.txt`.

## Build A PDF Body Outline

Filter outline candidates down to likely in-body chapter markers and separate likely table-of-contents entries:

```bash
source .venv/bin/activate
python build_pdf_body_outline.py "extracted/sample.outline_candidates.json" "extracted/sample.chunks.json"
python build_pdf_body_outline.py "extracted/sample.outline_candidates.json" "extracted/sample.chunks.json" --keep-toc
```

The body outline reports are written to `extracted/<pdf_stem>.body_outline.json` and `extracted/<pdf_stem>.body_outline.txt`.

## Assign PDF Chapter Metadata

Create enriched PDF chunks with chapter metadata assigned from the body outline:

```bash
source .venv/bin/activate
python assign_pdf_chapters.py "extracted/sample.chunks.json" "extracted/sample.body_outline.json"
```

The chapter-enriched files are written to `extracted/<pdf_stem>.chapter_chunks.json` and `extracted/<pdf_stem>.chapter_chunks.txt`.

## Build A Structured PDF Index

Build a separate local vector index from chapter-enriched PDF chunks:

```bash
source .venv/bin/activate
python build_structured_pdf_index.py "extracted/sample.chapter_chunks.json"
```

The structured PDF index is written to `storage/structured_pdf_<pdf_stem>`.

## Retrieve From A Structured PDF Index

Retrieve from the chapter-enriched PDF index with optional metadata filters:

```bash
source .venv/bin/activate
python retrieve_structured_pdf_context.py
python retrieve_structured_pdf_context.py "What is this chapter about?" --chapter-number 1
python retrieve_structured_pdf_context.py "Find examples or exercises." --chapter-number 1
python retrieve_structured_pdf_context.py "Find content from chapter 2." --chapter "CHAPTER 2"
python retrieve_structured_pdf_context.py "What appears before the first chapter?" --front-matter true
python retrieve_structured_pdf_context.py "Find unknown content type examples." --content-type "unknown"
```

## Generate Structured PDF Lesson JSON

Generate structured JSON lesson material from retrieved structured PDF context:

```bash
source .venv/bin/activate
python generate_structured_pdf_lesson_json.py "Generate a lesson from Chapter 1." --chapter-number 1
python generate_structured_pdf_lesson_json.py "Generate a lesson from Chapter 2." --chapter "CHAPTER 2"
python generate_structured_pdf_lesson_json.py "Generate a lesson using body content only." --front-matter false
```

The generated JSON is written to `output/structured_pdf_lesson.generated.json`.
Structured PDF lesson output includes short evidence previews in `source_chunks` and source chunk references in `key_ideas`.

## Audit Structured PDF Lesson Grounding

Check that generated structured PDF lesson key ideas cite retrieved source chunks:

```bash
source .venv/bin/activate
python audit_generated_lesson.py "output/structured_pdf_lesson.generated.json"
```

The audit reports are written to `output/structured_pdf_lesson.audit.json` and `output/structured_pdf_lesson.audit.txt`.

## Detect PDF Section/Topic Candidates

Inspect chapter-enriched PDF chunks for possible section and topic headings without assigning metadata:

```bash
source .venv/bin/activate
python detect_pdf_sections_topics.py "extracted/sample.chapter_chunks.json"
python detect_pdf_sections_topics.py "extracted/sample.chapter_chunks.json" --min-confidence low
python detect_pdf_sections_topics.py "extracted/sample.chapter_chunks.json" --include-front-matter
```

The section/topic candidate reports are written to `extracted/<pdf_stem>.section_topic_candidates.json` and `extracted/<pdf_stem>.section_topic_candidates.txt`.

## Build A PDF Section Outline

Reduce noisy section/topic candidates into a cleaner inspection outline without assigning metadata:

```bash
source .venv/bin/activate
python build_pdf_section_outline.py "extracted/sample.section_topic_candidates.json"
python build_pdf_section_outline.py "extracted/sample.section_topic_candidates.json" --include-low-confidence
python build_pdf_section_outline.py "extracted/sample.section_topic_candidates.json" --max-per-chapter 20
```

The section outline reports are written to `extracted/<pdf_stem>.section_outline.json` and `extracted/<pdf_stem>.section_outline.txt`.

## Build A Strict PDF Section Outline

Create a stricter inspection outline from section/topic candidates:

```bash
source .venv/bin/activate
python build_pdf_strict_section_outline.py "extracted/sample.section_topic_candidates.json"
python build_pdf_strict_section_outline.py "extracted/sample.section_topic_candidates.json" --max-per-chapter 8
python build_pdf_strict_section_outline.py "extracted/sample.section_topic_candidates.json" --high-only
```

The strict section outline reports are written to `extracted/<pdf_stem>.strict_section_outline.json` and `extracted/<pdf_stem>.strict_section_outline.txt`.

## Resolve Document Structure

Compare available structure signals and choose the best one for later metadata assignment:

```bash
source .venv/bin/activate
python resolve_document_structure.py \
  "extracted/sample.chapter_chunks.json" \
  --body-outline "extracted/sample.body_outline.json" \
  --section-candidates "extracted/sample.section_topic_candidates.json" \
  --section-outline "extracted/sample.section_outline.json" \
  --strict-section-outline "extracted/sample.strict_section_outline.json"
```

The structure resolution reports are written to `extracted/<pdf_stem>.structure_resolution.json` and `extracted/<pdf_stem>.structure_resolution.txt`.

## Assign PDF Section Metadata

Create section-enriched PDF chunks from the resolved document structure:

```bash
source .venv/bin/activate
python assign_pdf_sections.py \
  "extracted/sample.chapter_chunks.json" \
  "extracted/sample.structure_resolution.json"
```

The section-enriched files are written to `extracted/<pdf_stem>.section_chunks.json` and `extracted/<pdf_stem>.section_chunks.txt`.

## Clean PDF Section Boundaries

Create a new cleaned section chunks file that trims obvious previous-section or next-section text around section headings:

```bash
source .venv/bin/activate
python clean_pdf_section_boundaries.py \
  "extracted/sample.section_chunks.json" \
  "extracted/sample.structure_resolution.json"
```

The cleaned files are written to `extracted/<pdf_stem>.section_clean_chunks.json` and `extracted/<pdf_stem>.section_clean_chunks.txt`. The original `section_chunks` file is not modified.

Optional checks:

```bash
python clean_pdf_section_boundaries.py \
  "extracted/sample.section_chunks.json" \
  "extracted/sample.structure_resolution.json" \
  --dry-run

head -80 extracted/sample.section_clean_chunks.txt
```

## Build A Section PDF Index

Build a separate local vector index from section-enriched PDF chunks:

```bash
source .venv/bin/activate
python build_section_pdf_index.py "extracted/sample.section_chunks.json"
```

The section PDF index is written to `storage/section_pdf_<pdf_stem>`.

## Build A Clean Section PDF Index (Step 28)

Build a separate vector index from cleaned section chunks. This does not overwrite the original section index at `storage/section_pdf_sample`.

```bash
source .venv/bin/activate
python build_clean_section_pdf_index.py \
  "extracted/sample.section_clean_chunks.json" \
  --storage-dir "./storage/section_clean_pdf_sample" \
  --index-id "section_clean_pdf_sample" \
  --overwrite
```

The clean index is written to `storage/section_clean_pdf_sample` with index ID `section_clean_pdf_sample`.

## Prepare Clean Section Index For Any Document (Step 31)

Step 31 generalizes the clean-section index build flow for any document slug. It does not change API defaults or lesson generation behavior.

Inspect derived artifact paths:

```bash
source .venv/bin/activate
python pdf_artifact_paths.py "extracted/sample.section_chunks.json"
python pdf_artifact_paths.py "input/pdfs/My Book.pdf"
```

Dry-run the preparation plan without writing files:

```bash
python prepare_clean_section_index.py \
  --section-chunks "extracted/sample.section_chunks.json" \
  --dry-run
```

Safe temporary end-to-end test that does not overwrite the production clean index:

```bash
python prepare_clean_section_index.py \
  --section-chunks "extracted/sample.section_chunks.json" \
  --clean-output "extracted/sample.step31.section_clean_chunks.json" \
  --clean-report "extracted/sample.step31.section_clean_chunks.txt" \
  --storage-dir "./storage/section_clean_pdf_sample_step31_test" \
  --index-id "section_clean_pdf_sample_step31_test" \
  --overwrite-index
```

For a future document:

```bash
python prepare_clean_section_index.py \
  --section-chunks "extracted/my_book.section_chunks.json" \
  --overwrite-index
```

This preparation flow does not run lesson generation and does not call NVIDIA.

## Generate Whole Book Lesson

Generate one book-level learning-materials JSON package from a raw PDF. This is the first book-level user-facing command: it does not require exact section titles, but internally it still uses the cleaned section pipeline.

Detailed notes for this workflow are in `docs/WHOLE_BOOK_LESSON.md`.

Live verification for `input/pdfs/pte.pdf`:

- Status: complete
- Detected lesson groups: 17
- Generated chapters: 17
- Checkpoint: complete
- Final JSON: `output/pte.book_learning_materials.generated.json`
- Final TXT report: `output/pte.book_learning_materials.generated.txt`
- Invalid source references: 0
- Audit: `PASS_WITH_WARNINGS`

The accepted warnings from the verified run are:

- `book_synthesis_model_json_invalid_repair_attempted`
- `book_synthesis_model_json_repaired`

```bash
source .venv/bin/activate
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --output "output/pte.book_learning_materials.generated.json" \
  --overwrite \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

Dry run without writing files or calling NVIDIA:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" --dry-run
```

Prepare PDF artifacts and the clean section index without calling NVIDIA:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" --prepare-only
```

Debug a small one-chapter generation run:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --max-chapters 1 \
  --output "output/pte.book_learning_materials.chapter1.generated.json" \
  --overwrite
```

The command saves generated chapter packages before final book synthesis:

```text
output/pte.chapter_packages.generated.json
```

Resume from saved chapter packages without regenerating chapters:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --resume-chapter-packages "output/pte.chapter_packages.generated.json" \
  --output "output/pte.book_learning_materials.generated.json" \
  --overwrite \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

Resume a partial checkpoint and generate only missing chapters:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --resume-chapter-packages "output/pte.chapter_packages.generated.json" \
  --resume-missing-chapters \
  --output "output/pte.book_learning_materials.generated.json" \
  --overwrite \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

Chapter packages are checkpointed after every generated chapter. If a model call fails or times out, the command saves progress to `output/pte.chapter_packages.generated.json` and can resume from that checkpoint. Timeout and retry settings protect the command from waiting indefinitely on a single model request.

The command calls NVIDIA only during actual generation, not during `--dry-run` or `--prepare-only`. For scanned or image-only PDFs, extraction may be poor because OCR is not part of this prototype milestone.

## Whole-book claim evidence extraction

Extract deterministic, auditable claims from the generated whole-book learning-material JSON and resolve cited source IDs against the full clean chunk text. This step does not judge semantic support; it only prepares normalized evidence for a later audit step.

The extractor uses full clean chunks from `extracted/<slug>.section_clean_chunks.json`. It never treats `source_chunks[*].text_preview` as authoritative evidence. Cited chunks are resolved by exact ID lookup, and complete source text is stored once in a normalized `evidence_chunks` collection so claims can reference it without repeating full text.

Citation origins are recorded explicitly:

- `local`: the same object as the claim has `source_chunk_ids`
- `inherited_chapter`: approved chapter fields inherit the chapter package source IDs
- `none`: no approved citation exists, and the claim remains visible for later audit

Run the PTE extraction:

```bash
source .venv/bin/activate
python extract_book_learning_claims.py \
  --book-file output/pte.book_learning_materials.generated.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.book_claim_evidence.generated.json \
  --report output/pte.book_claim_evidence.generated.txt
```

If `--clean-chunks-file` is omitted, the command reads `generation.clean_chunks_path` from the book JSON and fails clearly if it is missing. Use `--dry-run` to validate paths without writing files:

```bash
python extract_book_learning_claims.py \
  --book-file output/pte.book_learning_materials.generated.json \
  --output output/pte.book_claim_evidence.generated.json \
  --report output/pte.book_claim_evidence.generated.txt \
  --dry-run
```

Step 34B will use this artifact to judge semantic support. Step 34A does not rewrite claims, split claims into sentences, call a model, load an index, or generate embeddings.

## Whole-book semantic claim support audit

Audit the Step 34A claim/evidence artifact with a semantic judge. This checks whether each generated claim is supported by its exact cited full clean evidence.

Important: a valid source chunk ID does not prove that the cited text supports the claim. Step 34B judges evidence support, not universal truth. The judge receives only each claim, its context, its citation metadata, and the full text for the exact `source_chunk_ids` already resolved by Step 34A. It does not reopen the PDF, search for more chunks, load an index, use vector retrieval, or use web/external PTE knowledge.

Support statuses:

- `SUPPORTED`: the evidence directly supports, clearly paraphrases, or reasonably entails all material parts
- `PARTIALLY_SUPPORTED`: some material parts are supported and others are not
- `UNSUPPORTED`: the evidence does not establish the factual claim
- `CONTRADICTED`: the evidence clearly conflicts with the claim
- `SOURCE_DAMAGED`: source corruption prevents a reliable judgment
- `NOT_A_FACTUAL_CLAIM`: the item is mainly generated guidance, a prompt, an example, a checklist, or a study suggestion

`SOURCE_DAMAGED` is different from `UNSUPPORTED`: damaged source text means the evidence cannot be judged reliably; unsupported means the readable evidence simply does not establish the claim.

The audit also records claim nature (`official_rule`, `task_format`, `definition`, `source_summary`, `strategy`, `factual_explanation`, `pedagogical_example`, `learner_instruction`, `self_assessment`, `study_plan`, `other`), severity (`HIGH`, `MEDIUM`, `LOW`), confidence, deterministic recommended actions, and high-priority findings.

Execution status is separate from content quality:

- `run_status: COMPLETE` means all selected claims were judged successfully
- `audit_verdict: FAIL` means unsafe or unsupported high-severity content was found
- `audit_verdict: PASS_WITH_WARNINGS` means only medium/low findings were found
- `audit_verdict: PASS` means all factual claims were supported and non-factual items were classified appropriately

The command batches only claims with the same chapter and ordered evidence bundle. It checkpoints after every validated batch and supports resume after interruption. Malformed model JSON is saved under `output/<name>.raw/` and one narrow repair call is attempted without sending new evidence.

Dry run:

```bash
source .venv/bin/activate
python audit_book_claim_support.py \
  --input output/pte.book_claim_evidence.generated.json \
  --output output/pte.book_claim_support.audit.json \
  --report output/pte.book_claim_support.audit.txt \
  --checkpoint output/pte.book_claim_support.audit.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --batch-size 6 \
  --dry-run
```

Subset smoke audit:

```bash
python audit_book_claim_support.py \
  --input output/pte.book_claim_evidence.generated.json \
  --output output/pte.book_claim_support.smoke.audit.json \
  --report output/pte.book_claim_support.smoke.audit.txt \
  --checkpoint output/pte.book_claim_support.smoke.audit.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --batch-size 6 \
  --model-timeout-seconds 180 \
  --model-max-retries 2 \
  --claim-id chapter_01.key_terms.0.meaning \
  --claim-id chapter_02.worked_examples.2.explanation \
  --claim-id chapter_07.core_lessons.1.explanation \
  --claim-id chapter_11.common_misconceptions.2.correction \
  --claim-id chapter_15.key_terms.1.meaning \
  --claim-id chapter_16.core_lessons.4.explanation
```

Full PTE audit:

```bash
python audit_book_claim_support.py \
  --input output/pte.book_claim_evidence.generated.json \
  --output output/pte.book_claim_support.audit.json \
  --report output/pte.book_claim_support.audit.txt \
  --checkpoint output/pte.book_claim_support.audit.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --batch-size 6 \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

Resume after interruption:

```bash
python audit_book_claim_support.py \
  --input output/pte.book_claim_evidence.generated.json \
  --output output/pte.book_claim_support.audit.json \
  --report output/pte.book_claim_support.audit.txt \
  --checkpoint output/pte.book_claim_support.audit.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --batch-size 6 \
  --model-timeout-seconds 180 \
  --model-max-retries 2 \
  --resume
```

Known limitation: this audit still depends on model judgment. It is designed to be strict, evidence-isolated, checkpointed, and auditable, but Step 34B does not rewrite claims or repair the learning material.

## Grounding-Aware Whole-Book Generation Contract

`book_learning_materials.v2` is the hardened whole-book output contract. Step 34C.1 defines the deterministic validator. Step 34C.2 adds a targeted chapter-generation path to `generate_book_learning_materials.py` while keeping `book_learning_materials.v1` as the temporary default.

The central rule is:

> A source-grounded label means the exact field has its own explicit evidence. Chapter-level citations are not inherited.

The validator distinguishes three origins for every auditable learner-facing field:

- `source_grounded`: the field has its own explicit `source_chunk_ids`; high-risk claims must also include exact evidence spans
- `pedagogical_generation`: useful generated pedagogy such as examples, practice prompts, self-assessment, and study-plan items; it must not use `source_chunk_ids`
- `insufficient_source_evidence`: the field is intentionally omitted with `text: null` and a non-empty `reason`

A source ID alone is insufficient. For high-risk claim kinds such as `official_rule`, `task_format`, `pronunciation_rule`, and `grammar_rule`, `source_grounded` content must include short exact quotes from the clean source text. Evidence spans are checked by exact normalized substring match against the authoritative clean chunks. The validator does not use previews, fuzzy matching, retrieval, indexes, embeddings, models, web sources, or external test facts.

Pedagogical generation may be useful, but it must never be presented as an official source-derived rule.

Current `book_learning_materials.v1` artifacts are intentionally rejected. They are not auto-upgraded or migrated by this validator.

Validate the compact v2 fixture:

```bash
source .venv/bin/activate
python validate_book_learning_materials_contract.py \
  --book-file tests/fixtures/book_learning_materials_v2.valid.json \
  --clean-chunks-file tests/fixtures/book_learning_materials_v2.clean_chunks.json \
  --output output/book_learning_materials_v2.contract.example.audit.json \
  --report output/book_learning_materials_v2.contract.example.audit.txt
```

Dry run without writing files:

```bash
python validate_book_learning_materials_contract.py \
  --book-file tests/fixtures/book_learning_materials_v2.valid.json \
  --clean-chunks-file tests/fixtures/book_learning_materials_v2.clean_chunks.json \
  --output output/book_learning_materials_v2.contract.example.audit.json \
  --report output/book_learning_materials_v2.contract.example.audit.txt \
  --dry-run
```

## Targeted grounding-aware whole-book generation

Use explicit schema selection to choose the current whole-book generation contract:

- `--schema-version book_learning_materials.v1`: existing workflow and temporary default
- `--schema-version book_learning_materials.v2`: targeted grounding-aware chapter generation

In Step 34C.2, v2 intentionally requires explicit chapter selection with repeatable `--chapter-number`. Accidental full-book v2 generation is blocked until the later full-book v2 milestone. Targeted v2 generation skips Stage 2 book synthesis, so the final v2 artifact contains only the selected chapters under `learning_materials.chapters`.

The v2 path validates every generated chapter against the deterministic contract before checkpointing it. If a chapter candidate fails, the command saves the raw response, parsed candidate, and contract errors under `output/<name>.invalid/`, then attempts exactly one evidence-aware repair using the same source chunks. Failed repairs preserve the checkpoint and exit non-zero with a resume command.

Every auditable learner-facing field uses one of these origins:

- `source_grounded`: local explicit source IDs; high-risk claims also need exact evidence spans
- `pedagogical_generation`: generated pedagogy such as examples, study plans, checklist items, and practice prompts; no `source_chunk_ids`
- `insufficient_source_evidence`: `text: null` plus a reason when the local source is not enough

High-risk claim kinds are `official_rule`, `task_format`, `pronunciation_rule`, and `grammar_rule`. They must never use `pedagogical_generation`.

Contract PASS proves structural grounding discipline. It does not by itself prove that every claim is semantically supported. Step 34C.3 will perform targeted semantic comparison.

Run targeted PTE v2 generation:

```bash
source .venv/bin/activate
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --schema-version book_learning_materials.v2 \
  --chapter-number 2 \
  --chapter-number 11 \
  --chapter-number 15 \
  --chapter-number 16 \
  --chapter-packages-output output/pte.v2.targeted.chapter_packages.generated.json \
  --output output/pte.v2.targeted.book_learning_materials.generated.json \
  --overwrite \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

Resume a compatible targeted v2 checkpoint:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --schema-version book_learning_materials.v2 \
  --chapter-number 2 \
  --chapter-number 11 \
  --chapter-number 15 \
  --chapter-number 16 \
  --chapter-packages-output output/pte.v2.targeted.chapter_packages.generated.json \
  --resume-chapter-packages output/pte.v2.targeted.chapter_packages.generated.json \
  --resume-missing-chapters \
  --output output/pte.v2.targeted.book_learning_materials.generated.json \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

Dry run without writing files or calling NVIDIA:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --schema-version book_learning_materials.v2 \
  --chapter-number 2 \
  --chapter-number 11 \
  --chapter-number 15 \
  --chapter-number 16 \
  --chapter-packages-output output/pte.v2.targeted.chapter_packages.generated.json \
  --output output/pte.v2.targeted.book_learning_materials.generated.json \
  --dry-run
```

Successful targeted v2 generation writes sibling contract-audit artifacts next to the final book:

```text
output/pte.v2.targeted.book_learning_materials.contract.audit.json
output/pte.v2.targeted.book_learning_materials.contract.audit.txt
```

## Targeted v2 semantic and coverage evaluation

Step 34C.3 evaluates the targeted `book_learning_materials.v2` chapters `2`, `11`, `15`, and `16` for semantic safety and content retention. A contract `PASS` proves that the v2 JSON follows the grounding schema; it is not semantic proof that each learner-facing claim is supported or that important chapter content was preserved.

The evaluator uses the existing Step 34B result as the v1 baseline. It does not rejudge v1 claims. It extracts a source-concept inventory independently from clean source text, then compares the v1 baseline and v2 records against those concepts.

The source-concept inventory is generated from source text alone. It does not receive v1 or v2 generated material.

Origin-specific v2 evaluation:

- `source_grounded`: semantic support status (`SUPPORTED`, `PARTIALLY_SUPPORTED`, `UNSUPPORTED`, `CONTRADICTED`, `SOURCE_DAMAGED`)
- `pedagogical_generation`: usability status (`USABLE`, `NEEDS_REVISION`, `MISLEADING`)
- `insufficient_source_evidence`: abstention quality (`JUSTIFIED`, `OVERCAUTIOUS`, `MISALIGNED`)

Removing an unsafe claim is not sufficient when an important source concept is silently lost. Safe omission must be represented explicitly as `insufficient_source_evidence` when the chapter still needs to account for that concept.

The final result includes:

- `safety_verdict`
- `coverage_verdict`
- `comparison_verdict`
- known-pattern traces for wanted pronunciation, spelling/zero-score, Highlight Correct Summary, and essay timing
- source-concept coverage statuses including safe withholding versus silent omission

The normal targeted run plans exactly eight model calls: four source-concept inventory calls and four chapter-evaluation calls. One repair call may be made for a malformed response. The checkpoint supports compatible resume and rejects changed input hashes, changed model, changed prompt versions, or changed selected chapter order.

Dry run:

```bash
source .venv/bin/activate
python evaluate_targeted_book_learning_materials.py \
  --v1-book-file output/pte.book_learning_materials.generated.json \
  --v1-audit-file output/pte.book_claim_support.audit.json \
  --v2-book-file output/pte.v2.targeted.book_learning_materials.generated.json \
  --v2-contract-audit-file output/pte.v2.targeted.book_learning_materials.contract.audit.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.v2.targeted.evaluation.json \
  --report output/pte.v2.targeted.evaluation.txt \
  --checkpoint output/pte.v2.targeted.evaluation.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --dry-run
```

Live targeted evaluation:

```bash
python evaluate_targeted_book_learning_materials.py \
  --v1-book-file output/pte.book_learning_materials.generated.json \
  --v1-audit-file output/pte.book_claim_support.audit.json \
  --v2-book-file output/pte.v2.targeted.book_learning_materials.generated.json \
  --v2-contract-audit-file output/pte.v2.targeted.book_learning_materials.contract.audit.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.v2.targeted.evaluation.json \
  --report output/pte.v2.targeted.evaluation.txt \
  --checkpoint output/pte.v2.targeted.evaluation.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --model-timeout-seconds 180 \
  --model-max-retries 2 \
  --model-retry-backoff-seconds 5 \
  --overwrite
```

Resume after interruption:

```bash
python evaluate_targeted_book_learning_materials.py \
  --v1-book-file output/pte.book_learning_materials.generated.json \
  --v1-audit-file output/pte.book_claim_support.audit.json \
  --v2-book-file output/pte.v2.targeted.book_learning_materials.generated.json \
  --v2-contract-audit-file output/pte.v2.targeted.book_learning_materials.contract.audit.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.v2.targeted.evaluation.json \
  --report output/pte.v2.targeted.evaluation.txt \
  --checkpoint output/pte.v2.targeted.evaluation.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --model-timeout-seconds 180 \
  --model-max-retries 2 \
  --model-retry-backoff-seconds 5 \
  --resume
```

Limiting targeted chapter evaluations:

Use `--max-new-evaluation-chapters 1` when resuming the targeted comparison if you want one new chapter-evaluation stage to run and then stop. Completed source-concept inventories are reused from the checkpoint, already completed chapter evaluations do not count against the limit, and the checkpoint remains resumable. Final evaluation JSON and TXT output are written only after all selected chapter evaluations are complete.

Model calls run in an isolated worker process. If `--model-timeout-seconds` is exceeded, the worker is terminated and then force-killed if needed; the command exits non-zero, records a concise checkpoint error, and preserves completed checkpoint work.

Next live step: evaluate Chapter 2 only, then stop before Chapter 11.

```bash
source .venv/bin/activate
python evaluate_targeted_book_learning_materials.py \
  --v1-book-file output/pte.book_learning_materials.generated.json \
  --v1-audit-file output/pte.book_claim_support.audit.json \
  --v2-book-file output/pte.v2.targeted.book_learning_materials.generated.json \
  --v2-contract-audit-file output/pte.v2.targeted.book_learning_materials.contract.audit.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.v2.targeted.evaluation.json \
  --report output/pte.v2.targeted.evaluation.txt \
  --checkpoint output/pte.v2.targeted.evaluation.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --model-timeout-seconds 180 \
  --model-max-retries 2 \
  --model-retry-backoff-seconds 5 \
  --resume \
  --max-new-evaluation-chapters 1
```

Running one exact chapter evaluation:

Use `--evaluation-chapter-number 2` to target exactly one chapter-evaluation stage. Exact selection prevents the evaluator from automatically advancing to the next incomplete chapter. If the selected chapter is already complete, the command reports that and stops without running another chapter.

Use `--reevaluate-selected-chapter` only with `--resume` and `--evaluation-chapter-number`. Reevaluation preserves the previous valid result in the checkpoint until a complete replacement validates successfully. Source-concept inventories are reused, every other completed chapter evaluation is preserved, and final output remains unwritten until all four selected chapter evaluations are complete.

```bash
python evaluate_targeted_book_learning_materials.py \
  --v1-book-file output/pte.book_learning_materials.generated.json \
  --v1-audit-file output/pte.book_claim_support.audit.json \
  --v2-book-file output/pte.v2.targeted.book_learning_materials.generated.json \
  --v2-contract-audit-file output/pte.v2.targeted.book_learning_materials.contract.audit.json \
  --clean-chunks-file extracted/pte.section_clean_chunks.json \
  --output output/pte.v2.targeted.evaluation.json \
  --report output/pte.v2.targeted.evaluation.txt \
  --checkpoint output/pte.v2.targeted.evaluation.checkpoint.json \
  --model mistralai/mistral-medium-3.5-128b \
  --model-timeout-seconds 180 \
  --model-max-retries 2 \
  --model-retry-backoff-seconds 5 \
  --resume \
  --evaluation-chapter-number 2
```

To replace an already completed selected chapter later, add:

```bash
--reevaluate-selected-chapter
```

## Promote Clean Section Index As Default (Step 30)

Section-level retrieval, lesson generation, and `POST /section-pdf-lessons/generate` now default to the clean index:

- `storage_dir`: `./storage/section_clean_pdf_sample`
- `index_id`: `section_clean_pdf_sample`

The original section index remains available by explicit override:

```bash
python retrieve_section_pdf_context.py \
  "Explain memory in AI agents." \
  --storage-dir "./storage/section_pdf_sample" \
  --index-id "section_pdf_sample" \
  --chapter-number 6 \
  --section "Memory" \
  --ordering document \
  --top-k 8
```

Default CLI retrieval (clean index):

```bash
python retrieve_section_pdf_context.py \
  "Explain memory in AI agents." \
  --chapter-number 6 \
  --section "Memory" \
  --ordering document
```

Default CLI generation (clean index):

```bash
python generate_section_pdf_lesson_json.py \
  "Create a beginner-friendly lesson explaining memory in AI agents." \
  --chapter-number 6 \
  --section "Memory" \
  --ordering document \
  --output "output/chapter6_memory_lesson.default.generated.json"
```

## Retrieve From A Section PDF Index

Retrieve from the section-enriched PDF index with optional metadata filters. Defaults use the clean section index (`section_clean_pdf_sample`).

```bash
source .venv/bin/activate
python retrieve_section_pdf_context.py \
  "What is AI engineering?" \
  --chapter-number 1 \
  --section "The Rise of AI Engineering"
python retrieve_section_pdf_context.py \
  "Explain retrieval augmented generation" \
  --chapter-number 6 \
  --topic "RAG"
python retrieve_section_pdf_context.py \
  "What are evaluation methods?" \
  --chapter-number 3
python retrieve_section_pdf_context.py \
  "What is prompt engineering?" \
  --section "Prompt Engineering Best Practices"
python retrieve_section_pdf_context.py \
  "Find content from front matter" \
  --front-matter true
```

Exact section retrieval keeps only chunks directly assigned to that section:

```bash
source .venv/bin/activate
python retrieve_section_pdf_context.py \
  "What are the main ideas in this section?" \
  --chapter-number 5 \
  --section "Prompt Engineering Best Practices"
```

Parent section retrieval can include descendant subsections:

```bash
python retrieve_section_pdf_context.py \
  "What are the main prompt engineering best practices?" \
  --chapter-number 5 \
  --section "Prompt Engineering Best Practices" \
  --include-descendants \
  --top-k 8 \
  --ordering semantic
python retrieve_section_pdf_context.py \
  "What are the main prompt engineering best practices?" \
  --chapter-number 5 \
  --section "Prompt Engineering Best Practices" \
  --include-descendants \
  --top-k 8 \
  --ordering document
```

## Generate A Section PDF Lesson

Generate grounded JSON lessons from the section-enriched PDF index. Defaults use the clean section index (`section_clean_pdf_sample`).

```bash
source .venv/bin/activate
python generate_section_pdf_lesson_json.py \
  "Generate a beginner-friendly lesson about the rise of AI engineering." \
  --chapter-number 1 \
  --section "The Rise of AI Engineering"
python generate_section_pdf_lesson_json.py \
  "Explain retrieval-augmented generation to a software developer." \
  --chapter-number 6 \
  --topic "RAG"
python generate_section_pdf_lesson_json.py \
  "Create a practical lesson about writing better prompts." \
  --section "Prompt Engineering Best Practices"
```

Generate a lesson from a parent section and its descendant subsections:

```bash
python generate_section_pdf_lesson_json.py \
  "Create a comprehensive practical lesson about writing better prompts." \
  --chapter-number 5 \
  --section "Prompt Engineering Best Practices" \
  --include-descendants \
  --top-k 8 \
  --ordering document
```

The generated lesson is written to `output/section_pdf_lesson.generated.json`.

Ordering modes:

- `semantic`: default, highest similarity score first.
- `document`: select the same semantic results first, then present them in chapter/section/page order.

When descendant sections are included, the lesson output includes deterministic `source.section_coverage` showing which expanded sections were represented by retrieved chunks.

## Audit A Section PDF Lesson (Step 26)

Audit generated section-level lesson JSON for grounding and quality problems without regenerating lessons or calling NVIDIA:

```bash
source .venv/bin/activate
python audit_section_pdf_lesson.py "output/chapter6_memory_lesson.generated.json"
python audit_section_pdf_lesson.py "output/section_pdf_lesson.document.generated.json"
```

The audit writes sibling reports next to the input file:

- `output/chapter6_memory_lesson.audit.json`
- `output/chapter6_memory_lesson.audit.txt`

Optional flags:

```bash
python audit_section_pdf_lesson.py \
  "output/chapter6_memory_lesson.generated.json" \
  --structure-resolution extracted/sample.structure_resolution.json

python audit_section_pdf_lesson.py \
  "output/chapter6_memory_lesson.generated.json" \
  --strict
```

`--strict` treats warnings (for example possible page-boundary contamination) as audit failures.

Inspect the audit summary:

```bash
python - <<'PY'
import json
from pathlib import Path

audit = json.loads(Path("output/chapter6_memory_lesson.audit.json").read_text())
print("status:", audit["status"])
print("requested_section:", audit["summary"]["requested_section"])
print("ordering:", audit["summary"]["ordering"])
print("invalid_source_reference_count:", audit["summary"]["invalid_source_reference_count"])
print("document_order_valid:", audit["summary"]["document_order_valid"])
print("warning_count:", audit["summary"]["warning_count"])
print("warnings:", audit.get("warnings", []))
print("failures:", audit.get("failures", []))
PY
```

## Compare Old Vs Clean Section Lessons (Step 29)

Step 29 compares lessons generated from the original section index against lessons generated from the clean section index. Use explicit `--storage-dir` / `--index-id` overrides so both indexes can still be compared after Step 30 made the clean index the default.

Generate old-index and clean-index lessons:

```bash
source .venv/bin/activate

python generate_section_pdf_lesson_json.py \
  "Create a beginner-friendly lesson explaining memory in AI agents." \
  --storage-dir "./storage/section_pdf_sample" \
  --index-id "section_pdf_sample" \
  --chapter-number 6 \
  --section "Memory" \
  --ordering document \
  --top-k 8 \
  --output "output/chapter6_memory_lesson.generated.json"

python generate_section_pdf_lesson_json.py \
  "Create a beginner-friendly lesson explaining memory in AI agents." \
  --storage-dir "./storage/section_clean_pdf_sample" \
  --index-id "section_clean_pdf_sample" \
  --chapter-number 6 \
  --section "Memory" \
  --ordering document \
  --top-k 8 \
  --output "output/chapter6_memory_lesson.clean.generated.json"

python generate_section_pdf_lesson_json.py \
  "Create a comprehensive practical lesson about writing better prompts." \
  --storage-dir "./storage/section_pdf_sample" \
  --index-id "section_pdf_sample" \
  --chapter-number 5 \
  --section "Prompt Engineering Best Practices" \
  --include-descendants \
  --top-k 8 \
  --ordering document \
  --output "output/prompt_engineering_descendants_lesson.generated.json"

python generate_section_pdf_lesson_json.py \
  "Create a comprehensive practical lesson about writing better prompts." \
  --storage-dir "./storage/section_clean_pdf_sample" \
  --index-id "section_clean_pdf_sample" \
  --chapter-number 5 \
  --section "Prompt Engineering Best Practices" \
  --include-descendants \
  --top-k 8 \
  --ordering document \
  --output "output/prompt_engineering_descendants_lesson.clean.generated.json"
```

Audit all four lessons:

```bash
python audit_section_pdf_lesson.py "output/chapter6_memory_lesson.generated.json"
python audit_section_pdf_lesson.py "output/chapter6_memory_lesson.clean.generated.json"
python audit_section_pdf_lesson.py "output/prompt_engineering_descendants_lesson.generated.json"
python audit_section_pdf_lesson.py "output/prompt_engineering_descendants_lesson.clean.generated.json"
```

Compare old vs clean runs:

```bash
python compare_section_lesson_runs.py \
  --old-lesson "output/chapter6_memory_lesson.generated.json" \
  --clean-lesson "output/chapter6_memory_lesson.clean.generated.json"

python compare_section_lesson_runs.py \
  --old-lesson "output/prompt_engineering_descendants_lesson.generated.json" \
  --clean-lesson "output/prompt_engineering_descendants_lesson.clean.generated.json"
```

Comparison reports are written next to the clean lesson:

- `output/chapter6_memory_lesson.clean.comparison.json`
- `output/chapter6_memory_lesson.clean.comparison.txt`

## Ask A Question About A Generated Lesson (Step 32)

Answer a learner question using one generated lesson JSON file and the source chunks already attached to that lesson. This step does not retrieve additional chunks from the clean section index.

The Q&A script resolves each lesson `source_chunks[*].node_id` by exact ID against the clean section-chunk JSON artifact, then sends the full cleaned chunk text to the model. `text_preview` is metadata only and is not authoritative evidence.

For `input/pdfs/sample.pdf`, the default clean chunks artifact is derived as `extracted/sample.section_clean_chunks.json`. For a different PDF name, the artifact path is derived from the document slug, for example `input/pdfs/My Book.pdf` resolves to `extracted/my_book.section_clean_chunks.json`.

CLI usage:

```bash
source .venv/bin/activate
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --question "What is the difference between short-term memory and long-term memory?" \
  --output output/chapter6_memory_lesson.memory_question.generated.json
```

Explicit clean chunks override:

```bash
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --clean-chunks-file extracted/sample.section_clean_chunks.json \
  --question "What is the difference between short-term memory and long-term memory?"
```

Output files are protected by default. If `--output` already exists, the script exits non-zero before calling NVIDIA and leaves the file unchanged. Use `--overwrite` only when replacement is intentional:

```bash
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --question "What is memory?" \
  --output output/chapter6_memory_lesson.memory_question.generated.json \
  --overwrite
```

API usage:

```bash
curl -sS \
  -X POST \
  "http://127.0.0.1:8000/section-pdf-lessons/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
    "question": "What is the difference between short-term memory and long-term memory?"
  }'
```

Explicit clean chunks override through the API:

```bash
curl -sS \
  -X POST \
  "http://127.0.0.1:8000/section-pdf-lessons/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
    "clean_chunks_file": "extracted/sample.section_clean_chunks.json",
    "question": "What is memory?"
  }'
```

Grounding constraints:

- Resolve lesson source chunk IDs against the clean section-chunk JSON artifact.
- Use full cleaned chunk text as authoritative evidence.
- Treat `text_preview` as metadata only.
- Do not query any index, perform vector retrieval, or generate embeddings.
- Supported answers must cite valid `node_id` values from the lesson.
- Unsupported questions return `confidence: "low"` with empty `source_chunk_ids`.

Expected response shape:

```json
{
  "answer": "string",
  "source_chunk_ids": ["sample_chunk_325"],
  "confidence": "high",
  "follow_up_questions": ["string", "string", "string"]
}
```

Verification:

```bash
python -m pytest tests/test_ask_section_pdf_lesson.py -q
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --question "What year was the Eiffel Tower completed?" \
  --output output/chapter6_memory_lesson.unsupported_question.generated.json
```

Additional clean-index fallback retrieval for Q&A is intentionally deferred.

## Ask With Optional Same-Chapter Fallback (Step 33B)

The Q&A CLI can optionally use a two-stage flow:

1. Answer from the generated lesson's original source chunks first.
2. If that validated answer says the lesson materials do not provide enough information, and only if `--allow-index-fallback` is supplied, retrieve additional same-chapter context from the clean section index.
3. Generate a second answer using complete clean text from both the original lesson chunks and the selected fallback chunks.

Fallback is opt-in. Without `--allow-index-fallback`, the command never queries the clean index and the JSON response remains the existing four-field shape without `grounding`.

Lesson-only answer with fallback permission:

```bash
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --question "What is memory in AI?" \
  --allow-index-fallback
```

Fallback-requiring question:

```bash
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --question "What tools can an AI agent use?" \
  --allow-index-fallback
```

Existing behavior without fallback:

```bash
python ask_section_pdf_lesson.py \
  --lesson-file output/chapter6_memory_lesson.default.generated.json \
  --question "What tools can an AI agent use?"
```

When fallback is enabled, CLI responses include programmatic grounding provenance:

```json
{
  "grounding": {
    "fallback_attempted": true,
    "lesson_source_chunk_ids": [],
    "retrieved_source_chunk_ids": ["sample_chunk_303"]
  }
}
```

Fallback retrieval inherits Step 33A constraints: same source document, same chapter, no existing lesson source chunks, no more than five new chunks, and complete clean-text evidence from `extracted/<document_slug>.section_clean_chunks.json`.

## API Q&A With Optional Same-Chapter Fallback (Step 33C)

`POST /section-pdf-lessons/ask` now exposes the same opt-in fallback behavior for API callers. The default remains lesson-only: when `allow_index_fallback` is omitted or `false`, the endpoint does not query the clean index.

Fallback only runs after the lesson-only answer validates as insufficient evidence. When it runs, it retrieves same-document, same-chapter chunks from the clean section index and generates a second grounded answer from the original lesson chunks plus fallback chunks.

Fallback-disabled API request:

```bash
curl -sS \
  -X POST \
  "http://127.0.0.1:8000/section-pdf-lessons/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
    "question": "What does the chapter say about retrieval algorithms?"
  }'
```

Fallback-enabled API request:

```bash
curl -sS \
  -X POST \
  "http://127.0.0.1:8000/section-pdf-lessons/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
    "question": "What does the chapter say about retrieval algorithms?",
    "allow_index_fallback": true
  }'
```

Optional fallback controls:

- `fallback_storage_dir`, default `./storage/section_clean_pdf_sample`
- `fallback_index_id`, default `section_clean_pdf_sample`
- `fallback_top_k`, default `10`, allowed `1` to `50`
- `max_fallback_chunks`, default `5`, allowed `1` to `10`

API responses include grounding provenance:

```json
{
  "answer": "string",
  "source_chunk_ids": ["sample_chunk_325", "sample_chunk_282"],
  "confidence": "high",
  "follow_up_questions": ["string", "string"],
  "grounding": {
    "fallback_attempted": true,
    "lesson_source_chunk_ids": ["sample_chunk_325"],
    "retrieved_source_chunk_ids": ["sample_chunk_282"]
  }
}
```

The public response does not include internal orchestration diagnostics such as `source`, `insufficient_evidence`, fallback storage/index settings, fallback candidate counts, or selected fallback counts.

## Section PDF Lesson API

Start the API and call the section-aware lesson endpoint. When `storage_dir` / `index_id` are omitted, the endpoint uses the clean section index (`section_clean_pdf_sample`).

```bash
source .venv/bin/activate
uvicorn api:app --reload
```

Exact section request (clean default):

```bash
curl -X POST http://127.0.0.1:8000/section-pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a practical lesson about writing better prompts.",
    "chapter_number": 5,
    "section": "Prompt Engineering Best Practices",
    "include_descendants": false,
    "top_k": 8,
    "ordering": "semantic"
  }'
```

Old section index override:

```bash
curl -X POST http://127.0.0.1:8000/section-pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a beginner-friendly lesson explaining memory in AI agents.",
    "storage_dir": "./storage/section_pdf_sample",
    "index_id": "section_pdf_sample",
    "chapter_number": 6,
    "section": "Memory",
    "ordering": "document",
    "top_k": 8
  }'
```

Parent section with descendant subsections:

```bash
curl -X POST http://127.0.0.1:8000/section-pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a comprehensive practical lesson about writing better prompts.",
    "chapter_number": 5,
    "section": "Prompt Engineering Best Practices",
    "include_descendants": true,
    "top_k": 8,
    "ordering": "document"
  }'
```

Invalid section check:

```bash
curl -sS -o /tmp/invalid-section.json -w "%{http_code}\n" \
  -X POST http://127.0.0.1:8000/section-pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a lesson.",
    "chapter_number": 5,
    "section": "This Section Does Not Exist",
    "include_descendants": true
  }'
python -m json.tool /tmp/invalid-section.json
```

Do not commit the real `.env` file.

Not included yet:

- Laravel integration
- OCR or LlamaParse
- External vector databases
- More than two topics
- Database storage
- Authentication
