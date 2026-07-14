# Tiny Learning RAG API Contract

This document describes the current HTTP contract for the tiny learning RAG service.

The API is served by FastAPI from `api.py`.

Base URL for local development:

```text
http://127.0.0.1:8000
```

Start the API before calling these endpoints:

```bash
source .venv/bin/activate
uvicorn api:app --reload
```

## GET /structure

Purpose:

Return the available learning content structure from `chunks.json` so a frontend or Laravel app can show valid books, chapters, sections, topics, and content types.

Request example:

```http
GET /structure
```

Request body:

None.

Response shape:

```json
{
  "books": [
    {
      "domain": "math",
      "grade": "year_5",
      "book_id": "year5_math_001",
      "book_title": "Year 5 Math Sample Book",
      "chapters": [
        {
          "chapter": "Chapter 1: Numbers",
          "sections": [
            {
              "section": "1.1 Place Value",
              "topics": [
                {
                  "topic": "Place value",
                  "content_types": [
                    "common_mistake",
                    "exercise",
                    "explanation",
                    "worked_example"
                  ],
                  "chunk_count": 4
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

Curl example:

```bash
curl http://127.0.0.1:8000/structure
```

Notes for frontend/Laravel usage:

- Use this endpoint to populate filter controls before generating lessons.
- The response is derived from `chunks.json`; no database is involved.
- `content_types` contains the exact values accepted by the lesson-generation filter.
- Call this endpoint with `GET`; do not send a request body.

## POST /lessons/generate

Purpose:

Retrieve relevant chunks from the local index and generate a structured Year 5 Math lesson as JSON.

Request example:

```json
{
  "query": "Generate a Year 5 math lesson about rounding numbers.",
  "topic": "Rounding numbers",
  "section": null,
  "content_type": null
}
```

Request fields:

```json
{
  "query": "string optional",
  "topic": "string optional",
  "section": "string optional",
  "content_type": "string optional"
}
```

If `query` is missing or empty, the API uses:

```text
Generate a Year 5 math lesson about place value.
```

Filters are exact-match metadata filters. Use values returned by `GET /structure`.

Response shape:

```json
{
  "lesson_title": "string",
  "grade": "Year 5",
  "domain": "Math",
  "topic": "string",
  "simple_explanation": "string",
  "key_idea": "string",
  "worked_examples": [
    {
      "question": "string",
      "solution": "string"
    }
  ],
  "practice_questions": [
    {
      "question": "string"
    }
  ],
  "answer_key": [
    {
      "question": "string",
      "answer": "string"
    }
  ],
  "common_mistakes": [
    {
      "mistake": "string",
      "correction": "string"
    }
  ],
  "source_chunks": [
    {
      "node_id": "string",
      "content_type": "string",
      "chapter": "string",
      "section": "string",
      "topic": "string",
      "page_start": 0,
      "page_end": 0
    }
  ]
}
```

Curl example, default place value lesson:

```bash
curl -X POST http://127.0.0.1:8000/lessons/generate \
  -H "Content-Type: application/json" \
  -d '{}'
```

Curl example, rounding lesson using a topic filter:

```bash
curl -X POST http://127.0.0.1:8000/lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a Year 5 math lesson about rounding numbers.",
    "topic": "Rounding numbers"
  }'
```

Curl example, common mistake lesson using a content type filter:

```bash
curl -X POST http://127.0.0.1:8000/lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a Year 5 math lesson using only common mistakes.",
    "content_type": "common_mistake"
  }'
```

Notes for frontend/Laravel usage:

- Send JSON with `Content-Type: application/json`.
- Do not send `NVIDIA_API_KEY` from the frontend or Laravel caller; the RAG service reads it from its local `.env`.
- `topic`, `section`, and `content_type` are optional exact-match filters.
- Prefer using values from `GET /structure` to avoid filter mismatches.
- The API returns parsed JSON directly, not Markdown.
- If the model returns invalid JSON, the API responds with an error that includes the raw model response for debugging.
- Lesson generation requires Ollama to be running locally and `NVIDIA_API_KEY` to be configured on the RAG service.

## POST /pdf-lessons/generate

Purpose:

Retrieve structured PDF chunks from the local structured PDF index and generate a structured lesson as JSON.

Request example:

```json
{
  "query": "Generate a lesson from Chapter 1.",
  "storage_dir": "./storage/structured_pdf_sample",
  "index_id": "structured_pdf_sample",
  "chapter": null,
  "chapter_number": 1,
  "content_type": null,
  "front_matter": null
}
```

Request fields:

```json
{
  "query": "string optional",
  "storage_dir": "string optional",
  "index_id": "string optional",
  "chapter": "string optional",
  "chapter_number": "number optional",
  "content_type": "string optional",
  "front_matter": "boolean optional"
}
```

Defaults:

```json
{
  "query": "Generate a student-friendly lesson from this PDF chapter.",
  "storage_dir": "./storage/structured_pdf_sample",
  "index_id": "structured_pdf_sample"
}
```

Filters are exact-match metadata filters. `chapter_number` is matched as an integer, and `front_matter` is matched as a boolean.

Response shape:

```json
{
  "lesson_title": "string",
  "source": {
    "index_id": "string",
    "storage_dir": "string",
    "chapter": "string or null",
    "chapter_number": "number or null",
    "filters": {}
  },
  "lesson_level": "string",
  "topic": "string",
  "simple_explanation": "string",
  "key_ideas": [
    {
      "idea": "string",
      "source_chunk_ids": [
        "string"
      ]
    }
  ],
  "worked_examples": [
    {
      "question": "string",
      "solution": "string"
    }
  ],
  "practice_questions": [
    {
      "question": "string"
    }
  ],
  "answer_key": [
    {
      "question": "string",
      "answer": "string"
    }
  ],
  "common_mistakes": [
    {
      "mistake": "string",
      "correction": "string"
    }
  ],
  "source_chunks": [
    {
      "node_id": "string",
      "source_pdf": "string or null",
      "chapter": "string or null",
      "chapter_number": "number or null",
      "section": "string or null",
      "topic": "string or null",
      "content_type": "string or null",
      "page_start": "number or string or null",
      "page_end": "number or string or null",
      "is_front_matter": "boolean or null",
      "text_preview": "string"
    }
  ]
}
```

Curl example, Chapter 1 using chapter number:

```bash
curl -X POST http://127.0.0.1:8000/pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a lesson from Chapter 1.",
    "chapter_number": 1
  }'
```

Curl example, Chapter 2 using chapter filter:

```bash
curl -X POST http://127.0.0.1:8000/pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a lesson from Chapter 2.",
    "chapter": "CHAPTER 2"
  }'
```

Curl example, body content only:

```bash
curl -X POST http://127.0.0.1:8000/pdf-lessons/generate \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a lesson using body content only.",
    "front_matter": false
  }'
```

Notes for frontend/Laravel usage:

- Send JSON with `Content-Type: application/json`.
- Do not send `NVIDIA_API_KEY` from the frontend or Laravel caller; the RAG service reads it from its local `.env`.
- Use `chapter`, `chapter_number`, `content_type`, and `front_matter` to narrow PDF retrieval before generation.
- `source_chunks[*].text_preview` contains a short normalized evidence preview from the retrieved PDF chunk.
- `key_ideas[*].source_chunk_ids` references only retrieved chunk IDs; the API rejects unknown source references.
- The API returns parsed JSON directly, not Markdown.
- If the model returns invalid JSON, the API responds with an error that includes the raw model response for debugging.
- Structured PDF lesson generation requires Ollama to be running locally, the structured PDF index to exist, and `NVIDIA_API_KEY` to be configured on the RAG service.

## POST /section-pdf-lessons/generate

Purpose:

Retrieve section-enriched PDF chunks and generate a grounded structured lesson as JSON. This endpoint supports exact section retrieval and optional parent-section expansion with descendant subsections.

Request example:

```json
{
  "query": "Create a comprehensive practical lesson about writing better prompts.",
  "chapter_number": 5,
  "section": "Prompt Engineering Best Practices",
  "include_descendants": true,
  "top_k": 8
}
```

Request fields:

```json
{
  "query": "string optional",
  "storage_dir": "string optional",
  "index_id": "string optional",
  "structure_resolution": "string optional",
  "chapter": "string optional",
  "chapter_number": "number optional",
  "section": "string optional",
  "topic": "string optional",
  "content_type": "string optional",
  "front_matter": "boolean optional",
  "include_descendants": "boolean optional",
  "top_k": "number optional",
  "ordering": "semantic or document optional"
}
```

Defaults:

```json
{
  "query": "Generate a student-friendly lesson from this section.",
  "storage_dir": "./storage/section_clean_pdf_sample",
  "index_id": "section_clean_pdf_sample",
  "structure_resolution": "extracted/sample.structure_resolution.json",
  "include_descendants": false,
  "top_k": 8,
  "ordering": "semantic"
}
```

When `storage_dir` / `index_id` are omitted, the endpoint uses the clean section index. The original section index remains available by explicit override:

```json
{
  "storage_dir": "./storage/section_pdf_sample",
  "index_id": "section_pdf_sample",
  "chapter_number": 6,
  "section": "Memory",
  "ordering": "document"
}
```

Response shape:

```json
{
  "title": "string",
  "learning_objectives": [
    "string"
  ],
  "introduction": "string",
  "key_ideas": [
    {
      "idea": "string",
      "source_chunk_ids": [
        "string"
      ]
    }
  ],
  "explanation": "string",
  "worked_examples": [
    {
      "title": "string",
      "explanation": "string",
      "source_chunk_ids": [
        "string"
      ]
    }
  ],
  "common_misconceptions": [
    {
      "misconception": "string",
      "correction": "string",
      "source_chunk_ids": [
        "string"
      ]
    }
  ],
  "practice_questions": [
    {
      "question": "string",
      "answer": "string"
    }
  ],
  "summary": "string",
  "source": {
    "index_id": "section_clean_pdf_sample",
    "storage_dir": "./storage/section_clean_pdf_sample",
    "query": "string",
    "filters": {},
    "retrieved_chunk_count": 8,
    "ordering": "document",
    "section_coverage": {
      "expanded_section_count": 8,
      "covered_section_count": 6,
      "missing_section_count": 2,
      "covered_section_titles": [
        "Prompt Engineering Best Practices"
      ],
      "missing_section_titles": [
        "Provide Sufficient Context"
      ]
    },
    "requested_section": "Prompt Engineering Best Practices",
    "include_descendants": true,
    "resolved_chapter": "CHAPTER 5",
    "resolved_chapter_number": 5,
    "expanded_section_titles": [
      "Prompt Engineering Best Practices",
      "Write Clear and Explicit Instructions"
    ]
  },
  "source_chunks": [
    {
      "node_id": "sample_chunk_244",
      "score": 0.81,
      "source_pdf": "input/pdfs/sample.pdf",
      "book_title": "sample",
      "chapter": "CHAPTER 5",
      "chapter_number": 5,
      "section": "Prompt Engineering Best Practices",
      "topic": "Prompt Engineering Best Practices",
      "page_start": 220,
      "page_end": 220,
      "text_preview": "Short normalized source preview..."
    }
  ]
}
```

Curl example, exact section:

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

Curl example, parent section with descendants:

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

Error responses:

```json
{
  "detail": "Clear error message"
}
```

Expected status codes:

- `400`: ambiguous section title without chapter disambiguation.
- `404`: missing storage directory, missing structure-resolution file, unknown section title, or no matching chunks.
- `422`: invalid request body, including `top_k` outside `1..50` or `include_descendants=true` without `section`.
- `502`: invalid model JSON, unknown generated source references, or NVIDIA API call failure.
- `503`: missing `NVIDIA_API_KEY`.
- `500`: unexpected internal failure.

Notes for frontend/Laravel usage:

- Use this endpoint when the caller wants lessons scoped to PDF sections/topics rather than whole chapters.
- `include_descendants: false` preserves exact section matching.
- `include_descendants: true` requires `section` and expands from `structure_resolution` without modifying the index.
- `chapter_number` is recommended when expanding descendants to avoid ambiguous duplicate section titles.
- `source.expanded_section_titles` shows the exact section scope used for retrieval.
- `source.ordering` is either `semantic` or `document`.
- `source.section_coverage` reports which expanded section titles are represented by final retrieved chunks.
- Ordering changes presentation/context order only; it does not replace semantic retrieval or change the selected node set.
- `source_chunks[*].text_preview` is deterministic evidence text from retrieved chunks.
- The API validates generated source references before returning a response.

## POST /section-pdf-lessons/ask

Purpose:

Answer a learner question using one already-generated section PDF lesson JSON file and the source chunks embedded in that lesson. By default this endpoint does not retrieve additional chunks from any index.

The lesson JSON provides the ordered source chunk IDs and metadata. The service resolves those IDs by exact lookup against the clean section-chunk JSON artifact and sends the full cleaned chunk text to the model. `text_preview` is metadata only and is not authoritative evidence.

If `allow_index_fallback` is explicitly `true`, the endpoint still answers from the lesson first. It only queries the clean section index after the validated lesson-only answer says the lesson materials do not provide enough information. Fallback retrieval is constrained to the same source document and same chapter.

Request example:

```json
{
  "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
  "question": "What is the difference between short-term memory and long-term memory?"
}
```

Explicit clean chunks override:

```json
{
  "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
  "clean_chunks_file": "extracted/sample.section_clean_chunks.json",
  "question": "What is memory?"
}
```

Request fields:

```json
{
  "lesson_file": "string required",
  "clean_chunks_file": "string optional",
  "question": "string required",
  "allow_index_fallback": "boolean optional, default false",
  "fallback_storage_dir": "string optional, default ./storage/section_clean_pdf_sample",
  "fallback_index_id": "string optional, default section_clean_pdf_sample",
  "fallback_top_k": "number optional, default 10, range 1-50",
  "max_fallback_chunks": "number optional, default 5, range 1-10"
}
```

Response shape:

```json
{
  "answer": "string",
  "source_chunk_ids": [
    "string"
  ],
  "confidence": "high",
  "follow_up_questions": [
    "string",
    "string"
  ],
  "grounding": {
    "fallback_attempted": false,
    "lesson_source_chunk_ids": [
      "string"
    ],
    "retrieved_source_chunk_ids": []
  }
}
```

The successful public response contains exactly these top-level fields:

```text
answer
source_chunk_ids
confidence
follow_up_questions
grounding
```

The `grounding` object contains exactly:

```text
fallback_attempted
lesson_source_chunk_ids
retrieved_source_chunk_ids
```

Fallback-supported response example:

```json
{
  "answer": "Sparse retrieval uses term matching, while dense retrieval uses vector similarity.",
  "source_chunk_ids": [
    "sample_chunk_282"
  ],
  "confidence": "high",
  "follow_up_questions": [
    "How does retrieval help memory?",
    "When would dense retrieval be useful?"
  ],
  "grounding": {
    "fallback_attempted": true,
    "lesson_source_chunk_ids": [],
    "retrieved_source_chunk_ids": [
      "sample_chunk_282"
    ]
  }
}
```

Grounding behavior:

- Answers only from the supplied lesson file and full clean chunk text resolved by exact source chunk ID.
- Without `allow_index_fallback: true`, it does not query `section_clean_pdf_sample`, `section_pdf_sample`, or any other index.
- With `allow_index_fallback: true`, it retrieves clean-index fallback chunks only after a valid insufficient-evidence lesson-only answer.
- `text_preview` is not used as authoritative evidence.
- Supported answers must cite one or more valid `source_chunks[*].node_id` values.
- Invented source chunk IDs are rejected.
- Insufficient-evidence answers use `confidence: "low"`, empty `source_chunk_ids`, and clearly state that the lesson materials do not provide enough information.
- `grounding.lesson_source_chunk_ids` contains cited IDs from the original lesson evidence.
- `grounding.retrieved_source_chunk_ids` contains cited IDs from fallback retrieval. It is always empty when fallback is disabled or not attempted.
- `grounding.fallback_attempted` reports whether fallback retrieval actually ran, not whether it was merely allowed.
- The public response does not include orchestration diagnostics such as `source`, `insufficient_evidence`, fallback storage/index settings, candidate counts, or selected fallback counts.
- When `clean_chunks_file` is omitted, the service derives `extracted/<document_slug>.section_clean_chunks.json` from `source_chunks[*].source_pdf`.
- All lesson source chunks must resolve exactly once in the clean chunks artifact.

Curl example:

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

Explicit clean chunks curl example:

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

Fallback-enabled curl example:

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

Fallback-disabled curl example:

```bash
curl -sS \
  -X POST \
  "http://127.0.0.1:8000/section-pdf-lessons/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "lesson_file": "output/chapter6_memory_lesson.default.generated.json",
    "question": "What does the chapter say about retrieval algorithms?",
    "allow_index_fallback": false
  }'
```

Expected status codes:

- `400`: invalid lesson JSON, invalid clean chunks JSON, malformed source IDs, inconsistent source documents, or unresolved full chunk text.
- `404`: lesson file does not exist.
- `404`: clean chunks file does not exist.
- `422`: blank `lesson_file`, blank `question`, or blank `clean_chunks_file`.
- `422`: invalid fallback limits, such as `fallback_top_k` outside `1` to `50` or `max_fallback_chunks` outside `1` to `10`.
- `502`: NVIDIA failure, invalid model JSON, or grounding validation failure.
- `503`: missing `NVIDIA_API_KEY`.
- `500`: unexpected internal failure.
