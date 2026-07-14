# Whole Book Lesson Generation

This document describes the first book-level user-facing workflow for the tiny RAG prototype.

The workflow starts from a raw local PDF and produces one structured whole-book learning-material JSON file. The user does not need to choose exact chapter, section, or topic titles.

## Current Status

Milestone: Generate Whole Book Lesson

Status: complete

Live verification was run against:

```text
input/pdfs/pte.pdf
```

Verified result:

- Full-book command: pass
- Detected lesson groups: 17
- Generated chapters: 17
- Checkpoint: complete
- Final JSON written: yes
- Final TXT report written: yes
- Source references: valid
- `invalid_source_reference_count`: 0
- Audit: `PASS_WITH_WARNINGS`
- Failures: none

Accepted warnings from the verified run:

- `book_synthesis_model_json_invalid_repair_attempted`
- `book_synthesis_model_json_repaired`

These warnings mean the model returned malformed JSON during final book synthesis, the repair path fixed it, and the command still produced the final book output.

## Primary Command

```bash
source .venv/bin/activate

python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --output "output/pte.book_learning_materials.generated.json" \
  --overwrite \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

## Resume Command

If a future book fails halfway through chapter generation, resume from the checkpoint:

```bash
python generate_book_learning_materials.py "input/pdfs/pte.pdf" \
  --resume-chapter-packages "output/pte.chapter_packages.generated.json" \
  --resume-missing-chapters \
  --output "output/pte.book_learning_materials.generated.json" \
  --overwrite \
  --model-timeout-seconds 180 \
  --model-max-retries 2
```

## Outputs

The verified `pte.pdf` run produced:

```text
output/pte.book_learning_materials.generated.json
output/pte.book_learning_materials.generated.txt
output/pte.chapter_packages.generated.json
output/pte.book_synthesis.raw_response.txt
```

`output/pte.chapter_packages.generated.json` is the checkpoint file. It is updated after each successfully generated chapter package.

## What The Command Does

The command prepares missing PDF artifacts, builds or reuses the clean section index, loads cleaned chunks, groups content by detected lesson/chapter, generates chapter packages, and then synthesizes the final book-level overview and study plan.

Internally, the current `pte.pdf` source uses lesson headers rather than standard `CHAPTER N` markers, so the whole-book command uses the lesson-header fallback structure for this PDF:

```text
LESSON 1
LESSON 2
...
RECAP LESSON 2
```

This fallback is local to the whole-book workflow and does not change the section-level API, Q&A, PDF preparation scripts, or clean index defaults.

## Reliability Behavior

Model calls are bounded by:

- `--model-timeout-seconds`
- `--model-max-retries`
- `--model-retry-backoff-seconds`

If a chapter model call fails after retries, the command saves a checkpoint before exiting. If `--continue-on-chapter-error` is used, failed chapters are recorded in the checkpoint and generation continues.

If final book synthesis returns malformed JSON, the command saves the raw response, asks the model to repair the JSON once, and falls back to deterministic synthesis if repair also fails.

## Verification Snapshot

The successful `pte.pdf` run ended with:

```text
audit_status: PASS_WITH_WARNINGS
invalid_source_reference_count: 0
chapter_count: 17
source_chunk_count: 83
checkpoint_status: COMPLETE
generated_chapter_count: 17
target_chapter_count: 17
last_completed_chapter_number: 17
checkpoint_errors: []
```

## Not Included

This workflow does not add:

- API changes
- Laravel integration
- Frontend work
- OCR
- LlamaParse
- External vector databases
- Quiz mode
