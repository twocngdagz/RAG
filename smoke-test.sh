#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "Smoke test base URL: ${BASE_URL}"
echo

echo "1. GET /structure"
curl -sS "${BASE_URL}/structure"
echo
echo

echo "2. POST /lessons/generate - default lesson"
curl -sS -X POST "${BASE_URL}/lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
echo

echo "3. POST /lessons/generate - rounding lesson with topic filter"
curl -sS -X POST "${BASE_URL}/lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a Year 5 math lesson about rounding numbers.",
    "topic": "Rounding numbers"
  }'
echo
echo

echo "4. POST /lessons/generate - common mistake lesson with content_type filter"
curl -sS -X POST "${BASE_URL}/lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a Year 5 math lesson using only common mistakes.",
    "content_type": "common_mistake"
  }'
echo
echo

echo "5. POST /pdf-lessons/generate - structured PDF lesson with chapter_number filter"
curl -sS -X POST "${BASE_URL}/pdf-lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Generate a lesson from Chapter 1.",
    "chapter_number": 1
  }'
echo
echo

echo "6. POST /section-pdf-lessons/generate - exact section PDF lesson (clean default)"
curl -sS -X POST "${BASE_URL}/section-pdf-lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a practical lesson about writing better prompts.",
    "chapter_number": 5,
    "section": "Prompt Engineering Best Practices",
    "include_descendants": false,
    "top_k": 8
  }' > /tmp/step30-smoke-default-clean.json
cat /tmp/step30-smoke-default-clean.json
echo
echo

echo "7. Verify section PDF lesson defaults to clean index"
python - <<'PY'
import json
from pathlib import Path

lesson = json.loads(Path("/tmp/step30-smoke-default-clean.json").read_text())
source = lesson["source"]

if source.get("index_id") != "section_clean_pdf_sample":
    raise SystemExit(
        "Expected default index_id section_clean_pdf_sample, "
        f"got {source.get('index_id')!r}."
    )

if source.get("storage_dir") != "./storage/section_clean_pdf_sample":
    raise SystemExit(
        "Expected default storage_dir ./storage/section_clean_pdf_sample, "
        f"got {source.get('storage_dir')!r}."
    )

print("default_index_id:", source["index_id"])
print("default_storage_dir:", source["storage_dir"])
print("clean_default_verified: true")
PY
echo

echo "7A. POST /section-pdf-lessons/ask - default Q&A does not use fallback"
curl -sS -X POST "${BASE_URL}/section-pdf-lessons/ask" \
  -H "Content-Type: application/json" \
  -d '{
    "lesson_file": "/tmp/step30-smoke-default-clean.json",
    "question": "What are prompt engineering best practices?"
  }' > /tmp/step33c-smoke-ask-default.json
cat /tmp/step33c-smoke-ask-default.json
echo
echo

echo "7B. Verify Q&A API fallback defaults to disabled"
python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/step33c-smoke-ask-default.json").read_text())
grounding = payload.get("grounding") or {}
expected = {
    "answer",
    "source_chunk_ids",
    "confidence",
    "follow_up_questions",
    "grounding",
}

if set(payload) != expected:
    raise SystemExit(f"Unexpected public response keys: {sorted(payload)}")

if set(grounding) != {
    "fallback_attempted",
    "lesson_source_chunk_ids",
    "retrieved_source_chunk_ids",
}:
    raise SystemExit(f"Unexpected grounding keys: {sorted(grounding)}")

if grounding.get("fallback_attempted") is not False:
    raise SystemExit("Expected fallback_attempted false by default.")

if grounding.get("retrieved_source_chunk_ids") != []:
    raise SystemExit("Expected no retrieved fallback source chunks by default.")

if "source" in payload or "insufficient_evidence" in payload:
    raise SystemExit("Q&A response leaked internal diagnostics.")

print("public_keys:", sorted(payload))
print("fallback_attempted:", grounding["fallback_attempted"])
print("retrieved_source_chunk_ids:", grounding["retrieved_source_chunk_ids"])
print("qna_fallback_default_verified: true")
PY
echo

echo "8. POST /section-pdf-lessons/generate - section PDF lesson with descendants"
curl -sS -X POST "${BASE_URL}/section-pdf-lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a comprehensive practical lesson about writing better prompts.",
    "chapter_number": 5,
    "section": "Prompt Engineering Best Practices",
    "include_descendants": true,
    "top_k": 8,
    "ordering": "semantic"
  }' > /tmp/step25-smoke-semantic.json
cat /tmp/step25-smoke-semantic.json
echo
echo

echo "9. POST /section-pdf-lessons/generate - section PDF lesson with descendants in document order"
curl -sS -X POST "${BASE_URL}/section-pdf-lessons/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Create a comprehensive practical lesson about writing better prompts.",
    "chapter_number": 5,
    "section": "Prompt Engineering Best Practices",
    "include_descendants": true,
    "top_k": 8,
    "ordering": "document"
  }' > /tmp/step25-smoke-document.json
cat /tmp/step25-smoke-document.json
echo
echo

echo "10. Verify semantic/document selected node sets and document ordering"
python - <<'PY'
import json
from pathlib import Path

semantic = json.loads(Path("/tmp/step25-smoke-semantic.json").read_text())
document = json.loads(Path("/tmp/step25-smoke-document.json").read_text())
semantic_ids = [chunk["node_id"] for chunk in semantic["source_chunks"]]
document_ids = [chunk["node_id"] for chunk in document["source_chunks"]]
document_pages = [chunk["page_start"] for chunk in document["source_chunks"]]

if set(semantic_ids) != set(document_ids):
    raise SystemExit("Semantic and document ordering selected different node IDs.")

if document_pages != sorted(document_pages):
    raise SystemExit("Document ordering did not sort selected chunks by page order.")

if "section_coverage" not in semantic["source"] or "section_coverage" not in document["source"]:
    raise SystemExit("Missing section coverage in section PDF lesson response.")

if semantic["source"]["section_coverage"] != document["source"]["section_coverage"]:
    raise SystemExit("Coverage mismatch between semantic and document ordering.")

if semantic["source"].get("index_id") != "section_clean_pdf_sample":
    raise SystemExit("Semantic response did not use clean default index.")

if document["source"].get("index_id") != "section_clean_pdf_sample":
    raise SystemExit("Document response did not use clean default index.")

print("same_node_id_set: true")
print("document_pages_sorted: true")
print("coverage_fields_exist: true")
print("clean_default_index_id: true")
PY
echo

echo "11. POST /section-pdf-lessons/generate - invalid section returns 404"
invalid_status="$(
  curl -sS -o /tmp/invalid-section.json -w "%{http_code}" \
    -X POST "${BASE_URL}/section-pdf-lessons/generate" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Generate a lesson.",
      "chapter_number": 5,
      "section": "This Section Does Not Exist",
      "include_descendants": true
    }'
)"

echo "HTTP status: ${invalid_status}"
cat /tmp/invalid-section.json
echo

if [[ "${invalid_status}" != "404" ]]; then
  echo "Expected invalid section request to return HTTP 404." >&2
  exit 1
fi

echo
echo "12. POST /section-pdf-lessons/generate - invalid ordering returns 422"
invalid_ordering_status="$(
  curl -sS -o /tmp/invalid-ordering.json -w "%{http_code}" \
    -X POST "${BASE_URL}/section-pdf-lessons/generate" \
    -H "Content-Type: application/json" \
    -d '{
      "query": "Generate a lesson.",
      "chapter_number": 5,
      "section": "Prompt Engineering Best Practices",
      "include_descendants": true,
      "ordering": "alphabetical"
    }'
)"

echo "HTTP status: ${invalid_ordering_status}"
cat /tmp/invalid-ordering.json
echo

if [[ "${invalid_ordering_status}" != "422" ]]; then
  echo "Expected invalid ordering request to return HTTP 422." >&2
  exit 1
fi
