import argparse
import json
import os
import re
import shutil
import signal
import sys
import time
from collections import Counter, OrderedDict, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.llms.openai_like import OpenAILike


load_dotenv()

CLAIM_EVIDENCE_SCHEMA_VERSION = "book_claim_evidence.v1"
AUDIT_SCHEMA_VERSION = "book_claim_support_audit.v1"
CHECKPOINT_SCHEMA_VERSION = "book_claim_support_checkpoint.v1"
CLAIM_SUPPORT_PROMPT_VERSION = "book_claim_support.v1"

DEFAULT_NVIDIA_BASE_URL = os.getenv(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
)
DEFAULT_MODEL = "mistralai/mistral-medium-3.5-128b"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

SUPPORT_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "SOURCE_DAMAGED",
    "NOT_A_FACTUAL_CLAIM",
}
CLAIM_NATURES = {
    "official_rule",
    "task_format",
    "definition",
    "source_summary",
    "strategy",
    "factual_explanation",
    "pedagogical_example",
    "learner_instruction",
    "self_assessment",
    "study_plan",
    "other",
}
SEVERITIES = {"HIGH", "MEDIUM", "LOW"}
CONFIDENCES = {"HIGH", "MEDIUM", "LOW"}
FINDING_STATUSES = {
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "SOURCE_DAMAGED",
}
RECOMMENDED_ACTIONS = {
    "SUPPORTED": "keep",
    "PARTIALLY_SUPPORTED": "rewrite_with_supported_scope",
    "UNSUPPORTED": "rewrite_or_remove",
    "CONTRADICTED": "remove_or_correct",
    "SOURCE_DAMAGED": "inspect_source_and_regenerate",
    "NOT_A_FACTUAL_CLAIM": "keep_but_label_generated_when_needed",
}
STATUS_SORT_PRIORITY = {
    "CONTRADICTED": 0,
    "SOURCE_DAMAGED": 1,
    "UNSUPPORTED": 2,
    "PARTIALLY_SUPPORTED": 3,
}
KNOWN_HIGH_RISK_CLAIM_IDS = {
    "chapter_02.worked_examples.2.explanation",
    "chapter_15.key_terms.1.meaning",
    "chapter_11.common_misconceptions.2.correction",
    "chapter_16.core_lessons.4.explanation",
}
HIGH_RISK_PATTERN = re.compile(
    r"\b("
    r"score|scoring|zero score|partial credit|time limit|timed|minutes?|"
    r"word limit|words?|sentence or less|response format|must|mandatory|"
    r"listening|reading|writing|speaking|pronunciation|grammar|spelling|"
    r"essay|dictation|test takers?|pte academic"
    r")\b",
    re.IGNORECASE,
)


class BookClaimSupportAuditError(Exception):
    pass


class ModelCallError(BookClaimSupportAuditError):
    pass


class ModelJSONError(BookClaimSupportAuditError):
    pass


@dataclass(frozen=True)
class PlannedBatch:
    batch_id: str
    chapter_number: int | None
    source_chunk_ids: tuple[str, ...]
    claims: list[dict[str, Any]]


@dataclass
class RuntimeStats:
    model_call_count: int = 0
    repair_call_count: int = 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit whole-book generated claims against resolved clean evidence."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    parser.add_argument("--checkpoint")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=6)
    parser.add_argument("--model-timeout-seconds", type=int, default=180)
    parser.add_argument("--model-max-retries", type=int, default=2)
    parser.add_argument("--model-retry-backoff-seconds", type=float, default=5)
    parser.add_argument("--claim-id", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def text_preview(value: str, max_chars: int = 220) -> str:
    normalized = normalize_whitespace(value)
    if len(normalized) <= max_chars:
        return normalized
    return f"{normalized[: max_chars - 3].rstrip()}..."


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise BookClaimSupportAuditError(f"{label} does not exist: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BookClaimSupportAuditError(
            f"{label} is not valid JSON: {path}\nError: {error}"
        ) from error


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def default_checkpoint_path(output_path: Path) -> Path:
    if output_path.name.endswith(".json"):
        return output_path.with_name(output_path.name[: -len(".json")] + ".checkpoint.json")
    return output_path.with_name(output_path.name + ".checkpoint.json")


def raw_dir_for_output(output_path: Path) -> Path:
    name = output_path.name
    if name.endswith(".audit.json"):
        raw_name = name[: -len(".audit.json")] + ".raw"
    elif name.endswith(".json"):
        raw_name = name[: -len(".json")] + ".raw"
    else:
        raw_name = name + ".raw"
    return output_path.with_name(raw_name)


def require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BookClaimSupportAuditError(f"{label} must be a JSON object.")
    return value


def validate_string_array(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list):
        raise BookClaimSupportAuditError(f"{label} must be a list.")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise BookClaimSupportAuditError(f"{label} must contain only strings.")
        output.append(item)
    return output


def validate_claim_evidence_artifact(data: Any) -> dict[str, Any]:
    artifact = require_object(data, "Claim evidence artifact")
    if artifact.get("schema_version") != CLAIM_EVIDENCE_SCHEMA_VERSION:
        raise BookClaimSupportAuditError(
            f"Unsupported schema_version: {artifact.get('schema_version')}"
        )
    if artifact.get("status") != "PASS":
        raise BookClaimSupportAuditError(
            f"Input status must be PASS, got: {artifact.get('status')}"
        )

    claims = artifact.get("claims")
    evidence_chunks = artifact.get("evidence_chunks")
    summary = artifact.get("summary")
    if not isinstance(claims, list):
        raise BookClaimSupportAuditError("claims must be a list.")
    if not isinstance(evidence_chunks, list):
        raise BookClaimSupportAuditError("evidence_chunks must be a list.")
    if not isinstance(summary, dict):
        raise BookClaimSupportAuditError("summary must be an object.")

    claim_ids: set[str] = set()
    evidence_ids: set[str] = set()

    for chunk in evidence_chunks:
        if not isinstance(chunk, dict):
            raise BookClaimSupportAuditError("evidence_chunks must contain objects.")
        node_id = chunk.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise BookClaimSupportAuditError("Evidence chunk has empty node_id.")
        if node_id in evidence_ids:
            raise BookClaimSupportAuditError(f"Duplicate evidence ID: {node_id}")
        evidence_ids.add(node_id)
        text = chunk.get("text")
        if not isinstance(text, str) or not text.strip():
            raise BookClaimSupportAuditError(f"Evidence chunk has empty text: {node_id}")
        if "text_preview" in chunk:
            raise BookClaimSupportAuditError(
                f"Evidence chunk must not contain text_preview: {node_id}"
            )

    for claim in claims:
        if not isinstance(claim, dict):
            raise BookClaimSupportAuditError("claims must contain objects.")
        claim_id = claim.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise BookClaimSupportAuditError("Claim has empty claim_id.")
        if claim_id in claim_ids:
            raise BookClaimSupportAuditError(f"Duplicate claim ID: {claim_id}")
        claim_ids.add(claim_id)
        text = claim.get("claim_text")
        if not isinstance(text, str) or not text.strip():
            raise BookClaimSupportAuditError(f"Claim has empty claim_text: {claim_id}")
        source_ids = validate_string_array(
            claim.get("source_chunk_ids"), label=f"{claim_id}.source_chunk_ids"
        )
        duplicates = [
            node_id for node_id, count in Counter(source_ids).items() if count > 1
        ]
        if duplicates:
            raise BookClaimSupportAuditError(
                f"{claim_id} contains duplicate source IDs: {', '.join(duplicates)}"
            )
        missing = [node_id for node_id in source_ids if node_id not in evidence_ids]
        if missing:
            raise BookClaimSupportAuditError(
                f"{claim_id} references missing evidence IDs: {', '.join(missing)}"
            )

    if summary.get("claim_count") != len(claims):
        raise BookClaimSupportAuditError("summary.claim_count does not match claims.")
    if summary.get("unique_evidence_chunk_count") != len(evidence_chunks):
        raise BookClaimSupportAuditError(
            "summary.unique_evidence_chunk_count does not match evidence_chunks."
        )

    return artifact


def load_claim_evidence(path: Path) -> dict[str, Any]:
    return validate_claim_evidence_artifact(load_json(path, "Claim evidence file"))


def evidence_lookup(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {chunk["node_id"]: chunk for chunk in artifact["evidence_chunks"]}


def select_claims(
    claims: list[dict[str, Any]], requested_claim_ids: list[str] | None
) -> tuple[list[dict[str, Any]], str, list[str]]:
    requested = requested_claim_ids or []
    if not requested:
        return list(claims), "all", []

    normalized: list[str] = []
    for claim_id in requested:
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise BookClaimSupportAuditError("--claim-id values must be non-empty.")
        normalized.append(claim_id.strip())

    duplicates = [item for item, count in Counter(normalized).items() if count > 1]
    if duplicates:
        raise BookClaimSupportAuditError(
            "Duplicate requested claim IDs: " + ", ".join(duplicates)
        )

    known = {claim["claim_id"] for claim in claims}
    unknown = [claim_id for claim_id in normalized if claim_id not in known]
    if unknown:
        raise BookClaimSupportAuditError(
            "Unknown requested claim IDs: " + ", ".join(unknown)
        )

    requested_set = set(normalized)
    return (
        [claim for claim in claims if claim["claim_id"] in requested_set],
        "claim_ids",
        normalized,
    )


def build_batches(selected_claims: list[dict[str, Any]], batch_size: int) -> list[PlannedBatch]:
    if batch_size < 1:
        raise BookClaimSupportAuditError("--batch-size must be at least 1.")

    groups: OrderedDict[tuple[int | None, tuple[str, ...]], list[dict[str, Any]]] = (
        OrderedDict()
    )
    for claim in selected_claims:
        key = (claim.get("chapter_number"), tuple(claim.get("source_chunk_ids") or []))
        groups.setdefault(key, []).append(claim)

    batches: list[PlannedBatch] = []
    for (chapter_number, source_ids), claims_for_group in groups.items():
        for start in range(0, len(claims_for_group), batch_size):
            batch_claims = claims_for_group[start : start + batch_size]
            batches.append(
                PlannedBatch(
                    batch_id=f"batch_{len(batches) + 1:04d}",
                    chapter_number=chapter_number,
                    source_chunk_ids=source_ids,
                    claims=batch_claims,
                )
            )
    return batches


def largest_evidence_bundle_chars(
    batches: list[PlannedBatch], evidence_by_id: dict[str, dict[str, Any]]
) -> int:
    largest = 0
    for batch in batches:
        total = sum(len(evidence_by_id[node_id]["text"]) for node_id in batch.source_chunk_ids)
        largest = max(largest, total)
    return largest


def build_judge_prompt(
    *,
    batch: PlannedBatch,
    evidence_by_id: dict[str, dict[str, Any]],
) -> str:
    evidence = [
        {
            "node_id": node_id,
            "text": evidence_by_id[node_id]["text"],
        }
        for node_id in batch.source_chunk_ids
    ]
    claims = [
        {
            "claim_id": claim["claim_id"],
            "claim_type": claim.get("claim_type"),
            "claim_text": claim.get("claim_text"),
            "context": claim.get("context") or {},
            "citation_origin": claim.get("citation_origin"),
            "source_chunk_ids": claim.get("source_chunk_ids") or [],
        }
        for claim in batch.claims
    ]
    return f"""
You are auditing generated learning-material claims against cited source evidence.

Use only the supplied evidence. Do not use outside knowledge. Do not correct the claim from memory or general expertise.
Do not assume that a plausible statement is supported. If a factual statement is absent from the supplied evidence, classify it as UNSUPPORTED.
If the relevant evidence is materially corrupted, garbled, truncated, or missing notation/numbers required for judgment, classify SOURCE_DAMAGED.

High-risk trap checks:
- Pronunciation claims: exact phonetic symbols inside /.../ must be legible and match the claim. Empty slashes like //, slash pairs with missing symbols like / /, replacement characters, or visibly missing IPA symbols mean the source is damaged for that material point. Do not fill missing pronunciation symbols from outside knowledge.
- Task-format claims: verify the exact learner action in the evidence (reads, hears/listens, writes, says, selects). A skill list, item title, or page reference is not enough to prove a specific task action. If the claim says "reads a text" but the evidence only lists Reading as a skill, do not mark it SUPPORTED.
- Scoring and zero-score claims: the evidence must explicitly state the scoring or zero-score behavior. A skill list or a pointer to scoring pages is not enough.
- Timing claims: exact minute allocations must be explicitly stated for the same task. General "timed conditions" or classroom activity durations are not enough to support a precise test-time allocation.

Question to answer for each claim:
Does the supplied evidence support this generated claim?

Support status definitions:
- SUPPORTED: every materially factual part is directly stated, clearly paraphrased, or reasonably entailed by the evidence.
- PARTIALLY_SUPPORTED: at least one material part is supported and at least one other material part lacks support, without contradiction.
- UNSUPPORTED: the claim is factual/procedural/strategic/official but the evidence does not establish it.
- CONTRADICTED: the evidence clearly states something materially incompatible with the claim.
- SOURCE_DAMAGED: source corruption prevents a reliable support judgment.
- NOT_A_FACTUAL_CLAIM: learner instruction, checklist, generated study plan, pedagogical prompt, subjective recommendation, or illustrative sentence that does not present itself as an official/source-derived fact.

Claim nature values:
official_rule, task_format, definition, source_summary, strategy, factual_explanation, pedagogical_example, learner_instruction, self_assessment, study_plan, other

Severity values:
HIGH, MEDIUM, LOW
Use HIGH for official scoring, zero-score behavior, task timing, word limits, response format, modality, mandatory test behavior, pronunciation rules, grammar rules, or claims that could materially damage exam performance.

Confidence values:
HIGH, MEDIUM, LOW
SOURCE_DAMAGED should normally have LOW confidence.

Return strict JSON only, no Markdown and no code fences, in this exact shape:
{{
  "results": [
    {{
      "claim_id": "one input claim_id",
      "support_status": "SUPPORTED",
      "claim_nature": "definition",
      "severity": "MEDIUM",
      "confidence": "HIGH",
      "rationale": "Concise evidence-grounded rationale.",
      "supported_elements": ["short paraphrase"],
      "unsupported_elements": [],
      "contradicted_elements": [],
      "evidence_chunk_ids_used": ["one cited node_id"]
    }}
  ]
}}

Rules:
- Return exactly one result for each supplied claim.
- Use only these claim IDs: {[claim["claim_id"] for claim in batch.claims]}
- evidence_chunk_ids_used must be a subset of that claim's source_chunk_ids.
- For uncited claims, evidence_chunk_ids_used must be [].
- Do not quote long source passages.
- Do not add extra fields.

Evidence chunks, included once and in citation order:
{json.dumps(evidence, ensure_ascii=False, indent=2)}

Claims to audit:
{json.dumps(claims, ensure_ascii=False, indent=2)}
""".strip()


def build_repair_prompt(
    *,
    raw_response: str,
    validation_error: str,
    expected_claim_ids: list[str],
) -> str:
    return f"""
Repair the invalid JSON audit response below.

Return strict JSON only. No Markdown. No code fences. No explanation.
Do not reconsider the semantic judgments. Only repair JSON/schema shape enough to match the required schema.
Expected claim IDs: {expected_claim_ids}

Required shape:
{{
  "results": [
    {{
      "claim_id": "one expected claim id",
      "support_status": "SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED | CONTRADICTED | SOURCE_DAMAGED | NOT_A_FACTUAL_CLAIM",
      "claim_nature": "official_rule | task_format | definition | source_summary | strategy | factual_explanation | pedagogical_example | learner_instruction | self_assessment | study_plan | other",
      "severity": "HIGH | MEDIUM | LOW",
      "confidence": "HIGH | MEDIUM | LOW",
      "rationale": "concise non-empty string",
      "supported_elements": ["short strings"],
      "unsupported_elements": ["short strings"],
      "contradicted_elements": ["short strings"],
      "evidence_chunk_ids_used": ["only IDs already cited by that claim"]
    }}
  ]
}}

Validation error:
{validation_error}

Invalid response:
{raw_response}
""".strip()


def parse_model_results(raw_response: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_response)
    except json.JSONDecodeError as error:
        raise ModelJSONError(f"Model response was not valid JSON: {error}") from error

    if isinstance(parsed, list):
        results = parsed
    elif isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
        results = parsed["results"]
    else:
        raise ModelJSONError("Model response must be a list or an object with results.")

    if not all(isinstance(item, dict) for item in results):
        raise ModelJSONError("Model results must be objects.")
    return results


def severity_floor_for_claim(claim: dict[str, Any]) -> str | None:
    claim_id = str(claim.get("claim_id") or "")
    if claim_id in KNOWN_HIGH_RISK_CLAIM_IDS:
        return "HIGH"

    text = " ".join(
        [
            str(claim.get("claim_text") or ""),
            json.dumps(claim.get("context") or {}, ensure_ascii=False),
            str(claim.get("claim_type") or ""),
        ]
    )
    if HIGH_RISK_PATTERN.search(text):
        return "HIGH"
    return None


def apply_severity_floor(
    *, claim: dict[str, Any], model_severity: str
) -> tuple[str, bool]:
    floor = severity_floor_for_claim(claim)
    if floor == "HIGH" and model_severity != "HIGH":
        return "HIGH", True
    return model_severity, False


def validate_model_batch_results(
    *,
    batch_claims: list[dict[str, Any]],
    raw_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    expected_ids = [claim["claim_id"] for claim in batch_claims]
    claim_by_id = {claim["claim_id"]: claim for claim in batch_claims}
    seen: set[str] = set()
    normalized_by_id: dict[str, dict[str, Any]] = {}

    for item in raw_results:
        claim_id = item.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise ModelJSONError("Model result has empty claim_id.")
        if claim_id in seen:
            raise ModelJSONError(f"Duplicate model result claim_id: {claim_id}")
        seen.add(claim_id)
        if claim_id not in claim_by_id:
            raise ModelJSONError(f"Model returned extra claim_id: {claim_id}")

        support_status = item.get("support_status")
        claim_nature = item.get("claim_nature")
        model_severity = item.get("severity")
        confidence = item.get("confidence")
        if support_status not in SUPPORT_STATUSES:
            raise ModelJSONError(f"{claim_id} has invalid support_status.")
        if claim_nature not in CLAIM_NATURES:
            raise ModelJSONError(f"{claim_id} has invalid claim_nature.")
        if model_severity not in SEVERITIES:
            raise ModelJSONError(f"{claim_id} has invalid severity.")
        if confidence not in CONFIDENCES:
            raise ModelJSONError(f"{claim_id} has invalid confidence.")

        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise ModelJSONError(f"{claim_id} rationale must be non-empty.")

        supported_elements = validate_string_array(
            item.get("supported_elements"), label=f"{claim_id}.supported_elements"
        )
        unsupported_elements = validate_string_array(
            item.get("unsupported_elements"), label=f"{claim_id}.unsupported_elements"
        )
        contradicted_elements = validate_string_array(
            item.get("contradicted_elements"), label=f"{claim_id}.contradicted_elements"
        )
        evidence_used = validate_string_array(
            item.get("evidence_chunk_ids_used"),
            label=f"{claim_id}.evidence_chunk_ids_used",
        )
        duplicates = [node_id for node_id, count in Counter(evidence_used).items() if count > 1]
        if duplicates:
            raise ModelJSONError(
                f"{claim_id} evidence_chunk_ids_used contains duplicates: "
                + ", ".join(duplicates)
            )
        cited = set(claim_by_id[claim_id].get("source_chunk_ids") or [])
        outside = [node_id for node_id in evidence_used if node_id not in cited]
        if outside:
            raise ModelJSONError(
                f"{claim_id} used evidence IDs outside claim citations: "
                + ", ".join(outside)
            )

        severity, floor_applied = apply_severity_floor(
            claim=claim_by_id[claim_id],
            model_severity=model_severity,
        )

        normalized_by_id[claim_id] = {
            "support_status": support_status,
            "claim_nature": claim_nature,
            "severity": severity,
            "model_severity": model_severity,
            "severity_floor_applied": floor_applied,
            "confidence": confidence,
            "rationale": normalize_whitespace(rationale),
            "supported_elements": supported_elements,
            "unsupported_elements": unsupported_elements,
            "contradicted_elements": contradicted_elements,
            "evidence_chunk_ids_used": evidence_used,
            "recommended_action": RECOMMENDED_ACTIONS[support_status],
        }

    missing = [claim_id for claim_id in expected_ids if claim_id not in seen]
    if missing:
        raise ModelJSONError("Model response missing claim IDs: " + ", ".join(missing))
    extra = [claim_id for claim_id in seen if claim_id not in expected_ids]
    if extra:
        raise ModelJSONError("Model response has extra claim IDs: " + ", ".join(extra))

    return [normalized_by_id[claim_id] for claim_id in expected_ids]


@contextmanager
def model_timeout(seconds: int):
    if seconds <= 0 or not hasattr(signal, "SIGALRM"):
        yield
        return
    old_handler = signal.getsignal(signal.SIGALRM)

    def timeout_handler(_signum, _frame):
        raise TimeoutError("model_call_timeout")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def default_complete(prompt: str, *, model: str, timeout_seconds: int) -> str:
    if not NVIDIA_API_KEY:
        raise ModelCallError("Missing NVIDIA_API_KEY. Create a real .env file from .env.example.")
    Settings.llm = OpenAILike(
        model=model,
        api_base=DEFAULT_NVIDIA_BASE_URL,
        api_key=NVIDIA_API_KEY,
        is_chat_model=True,
        context_window=262144,
        max_tokens=6000,
        timeout=timeout_seconds,
    )
    return str(Settings.llm.complete(prompt))


def complete_with_retries(
    *,
    prompt: str,
    model: str,
    timeout_seconds: int,
    max_retries: int,
    retry_backoff_seconds: float,
    label: str,
    complete_fn: Callable[[str], str] | None,
    on_attempt: Callable[[], None] | None = None,
) -> str:
    attempts = max(0, max_retries) + 1
    last_error: Exception | None = None
    completer = complete_fn or (
        lambda value: default_complete(value, model=model, timeout_seconds=timeout_seconds)
    )
    for attempt in range(1, attempts + 1):
        try:
            if on_attempt is not None:
                on_attempt()
            with model_timeout(timeout_seconds):
                return completer(prompt)
        except Exception as error:
            last_error = error
            if attempt >= attempts:
                break
            print(
                f"{label} model call failed; retry {attempt}/{max_retries}: {error}",
                flush=True,
            )
            if retry_backoff_seconds > 0:
                time.sleep(retry_backoff_seconds)
    raise ModelCallError(f"{label} model call failed after {attempts} attempt(s): {last_error}")


def save_raw_response(raw_dir: Path, batch_id: str, kind: str, raw_response: str) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{batch_id}.{kind}.raw_response.txt"
    atomic_write_text(path, raw_response)
    return path


def checkpoint_payload(
    *,
    status: str,
    input_file: Path,
    input_sha256: str,
    model: str,
    batch_size: int,
    selected_claim_ids: list[str],
    selected_claim_count: int,
    planned_batch_count: int,
    completed_batch_count: int,
    results_by_claim_id: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    model_call_count: int,
    repair_call_count: int,
) -> dict[str, Any]:
    completed_claim_ids = [
        claim_id for claim_id in selected_claim_ids if claim_id in results_by_claim_id
    ]
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "status": status,
        "input_file": str(input_file),
        "input_sha256": input_sha256,
        "prompt_version": CLAIM_SUPPORT_PROMPT_VERSION,
        "model": model,
        "batch_size": batch_size,
        "selected_claim_count": selected_claim_count,
        "planned_batch_count": planned_batch_count,
        "completed_claim_count": len(completed_claim_ids),
        "completed_batch_count": completed_batch_count,
        "completed_claim_ids": completed_claim_ids,
        "selected_claim_ids": selected_claim_ids,
        "results_by_claim_id": results_by_claim_id,
        "model_call_count": model_call_count,
        "repair_call_count": repair_call_count,
        "errors": errors,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_json(path, payload)


def validate_resume_checkpoint(
    *,
    checkpoint: dict[str, Any],
    input_file: Path,
    input_sha256: str,
    model: str,
    batch_size: int,
    selected_claim_ids: list[str],
) -> None:
    if checkpoint.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
        raise BookClaimSupportAuditError("Checkpoint schema version is incompatible.")
    if checkpoint.get("input_file") != str(input_file):
        raise BookClaimSupportAuditError("Checkpoint input file is incompatible.")
    if checkpoint.get("input_sha256") != input_sha256:
        raise BookClaimSupportAuditError("Checkpoint input SHA-256 mismatch.")
    if checkpoint.get("prompt_version") != CLAIM_SUPPORT_PROMPT_VERSION:
        raise BookClaimSupportAuditError("Checkpoint prompt version mismatch.")
    if checkpoint.get("model") != model:
        raise BookClaimSupportAuditError("Checkpoint model mismatch.")
    if checkpoint.get("batch_size") != batch_size:
        raise BookClaimSupportAuditError("Checkpoint batch size mismatch.")
    if checkpoint.get("selected_claim_ids") != selected_claim_ids:
        raise BookClaimSupportAuditError("Checkpoint selected claim IDs mismatch.")


def ensure_outputs_can_write(
    *,
    output_path: Path,
    report_path: Path | None,
    checkpoint_path: Path,
    resume: bool,
    overwrite: bool,
) -> None:
    if resume:
        if not checkpoint_path.exists():
            raise BookClaimSupportAuditError(f"Checkpoint does not exist: {checkpoint_path}")
        return
    if overwrite:
        return
    existing = [
        path
        for path in [output_path, report_path, checkpoint_path]
        if path is not None and path.exists()
    ]
    if existing:
        raise BookClaimSupportAuditError(
            "Output already exists. Use --overwrite or --resume: "
            + ", ".join(str(path) for path in existing)
        )


def audit_batch_with_repair(
    *,
    batch: PlannedBatch,
    evidence_by_id: dict[str, dict[str, Any]],
    args: argparse.Namespace,
    raw_dir: Path,
    complete_fn: Callable[[str], str] | None,
    repair_complete_fn: Callable[[str], str] | None,
    stats: RuntimeStats,
) -> list[dict[str, Any]]:
    prompt = build_judge_prompt(batch=batch, evidence_by_id=evidence_by_id)
    raw = complete_with_retries(
        prompt=prompt,
        model=args.model,
        timeout_seconds=args.model_timeout_seconds,
        max_retries=args.model_max_retries,
        retry_backoff_seconds=args.model_retry_backoff_seconds,
        label=batch.batch_id,
        complete_fn=complete_fn,
        on_attempt=lambda: setattr(stats, "model_call_count", stats.model_call_count + 1),
    )
    try:
        raw_results = parse_model_results(raw)
        return validate_model_batch_results(batch_claims=batch.claims, raw_results=raw_results)
    except ModelJSONError as error:
        save_raw_response(raw_dir, batch.batch_id, "invalid", raw)
        repair_prompt = build_repair_prompt(
            raw_response=raw,
            validation_error=str(error),
            expected_claim_ids=[claim["claim_id"] for claim in batch.claims],
        )
        repaired_raw = complete_with_retries(
            prompt=repair_prompt,
            model=args.model,
            timeout_seconds=args.model_timeout_seconds,
            max_retries=args.model_max_retries,
            retry_backoff_seconds=args.model_retry_backoff_seconds,
            label=f"{batch.batch_id} repair",
            complete_fn=repair_complete_fn or complete_fn,
            on_attempt=lambda: setattr(
                stats, "repair_call_count", stats.repair_call_count + 1
            ),
        )
        try:
            repaired_results = parse_model_results(repaired_raw)
            return validate_model_batch_results(
                batch_claims=batch.claims,
                raw_results=repaired_results,
            )
        except ModelJSONError as repair_error:
            save_raw_response(raw_dir, batch.batch_id, "repair_invalid", repaired_raw)
            raise ModelJSONError(
                f"{batch.batch_id} repair failed: {repair_error}"
            ) from repair_error


def merge_claim_and_result(claim: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    output = {
        "claim_id": claim["claim_id"],
        "json_path": claim.get("json_path"),
        "scope": claim.get("scope"),
        "chapter_number": claim.get("chapter_number"),
        "chapter_title": claim.get("chapter_title"),
        "claim_type": claim.get("claim_type"),
        "claim_text": claim.get("claim_text"),
        "context": claim.get("context") or {},
        "citation_origin": claim.get("citation_origin"),
        "source_chunk_ids": claim.get("source_chunk_ids") or [],
    }
    output.update(result)
    return output


def result_counts_by_chapter(results: list[dict[str, Any]]) -> dict[str, Any]:
    chapters: dict[str, dict[str, Any]] = {}
    for item in results:
        key = str(item.get("chapter_number")) if item.get("chapter_number") is not None else "book"
        record = chapters.setdefault(
            key,
            {
                "claim_count": 0,
                "supported_count": 0,
                "partially_supported_count": 0,
                "unsupported_count": 0,
                "contradicted_count": 0,
                "source_damaged_count": 0,
                "not_factual_count": 0,
                "high_severity_finding_count": 0,
            },
        )
        record["claim_count"] += 1
        status = item["support_status"]
        status_key = {
            "SUPPORTED": "supported_count",
            "PARTIALLY_SUPPORTED": "partially_supported_count",
            "UNSUPPORTED": "unsupported_count",
            "CONTRADICTED": "contradicted_count",
            "SOURCE_DAMAGED": "source_damaged_count",
            "NOT_A_FACTUAL_CLAIM": "not_factual_count",
        }[status]
        record[status_key] += 1
        if item["severity"] == "HIGH" and status in FINDING_STATUSES:
            record["high_severity_finding_count"] += 1
    return dict(sorted(chapters.items(), key=lambda pair: (pair[0] == "book", pair[0])))


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(item["support_status"] for item in results)
    claim_type_counts = Counter(item["claim_type"] for item in results)
    nature_counts = Counter(item["claim_nature"] for item in results)
    finding_results = [item for item in results if item["support_status"] in FINDING_STATUSES]
    return {
        "claim_count": len(results),
        "judged_claim_count": len(results),
        "supported_count": status_counts["SUPPORTED"],
        "partially_supported_count": status_counts["PARTIALLY_SUPPORTED"],
        "unsupported_count": status_counts["UNSUPPORTED"],
        "contradicted_count": status_counts["CONTRADICTED"],
        "source_damaged_count": status_counts["SOURCE_DAMAGED"],
        "not_factual_count": status_counts["NOT_A_FACTUAL_CLAIM"],
        "high_severity_finding_count": sum(
            1 for item in finding_results if item["severity"] == "HIGH"
        ),
        "medium_severity_finding_count": sum(
            1 for item in finding_results if item["severity"] == "MEDIUM"
        ),
        "low_severity_finding_count": sum(
            1 for item in finding_results if item["severity"] == "LOW"
        ),
        "severity_floor_applied_count": sum(
            1 for item in results if item["severity_floor_applied"]
        ),
        "uncited_claim_count": sum(1 for item in results if not item["source_chunk_ids"]),
        "results_by_status": dict(sorted(status_counts.items())),
        "results_by_claim_type": dict(sorted(claim_type_counts.items())),
        "results_by_claim_nature": dict(sorted(nature_counts.items())),
        "results_by_chapter": result_counts_by_chapter(results),
    }


def audit_verdict(summary: dict[str, Any]) -> str:
    if summary["high_severity_finding_count"] > 0:
        return "FAIL"
    if summary["medium_severity_finding_count"] > 0 or summary["low_severity_finding_count"] > 0:
        return "PASS_WITH_WARNINGS"
    return "PASS"


def build_priority_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = {item["claim_id"]: position for position, item in enumerate(results)}
    findings = [
        item
        for item in results
        if item["severity"] == "HIGH" and item["support_status"] in FINDING_STATUSES
    ]
    findings.sort(
        key=lambda item: (
            STATUS_SORT_PRIORITY.get(item["support_status"], 99),
            item.get("chapter_number") if item.get("chapter_number") is not None else 10**9,
            indexed[item["claim_id"]],
        )
    )
    return [
        {
            "claim_id": item["claim_id"],
            "chapter_number": item.get("chapter_number"),
            "claim_type": item.get("claim_type"),
            "support_status": item["support_status"],
            "severity": item["severity"],
            "claim_text": text_preview(item.get("claim_text") or ""),
            "recommended_action": item["recommended_action"],
        }
        for item in findings
    ]


def build_final_output(
    *,
    artifact: dict[str, Any],
    input_path: Path,
    input_sha256: str,
    selected_claims: list[dict[str, Any]],
    selection_mode: str,
    requested_claim_ids: list[str],
    batches: list[PlannedBatch],
    checkpoint: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    results_by_claim_id = checkpoint["results_by_claim_id"]
    missing = [
        claim["claim_id"]
        for claim in selected_claims
        if claim["claim_id"] not in results_by_claim_id
    ]
    if missing:
        raise BookClaimSupportAuditError(
            "Cannot build final output; missing results for: " + ", ".join(missing)
        )
    results = [
        merge_claim_and_result(claim, results_by_claim_id[claim["claim_id"]])
        for claim in selected_claims
    ]
    summary = build_summary(results)
    input_info = artifact.get("input") or {}
    output = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "run_status": "COMPLETE",
        "audit_verdict": audit_verdict(summary),
        "input": {
            "claim_evidence_file": str(input_path),
            "input_sha256": input_sha256,
            "source_pdf": input_info.get("source_pdf"),
            "book_slug": input_info.get("book_slug"),
            "input_claim_count": len(artifact["claims"]),
            "selected_claim_count": len(selected_claims),
            "selection_mode": selection_mode,
            "selected_claim_ids": requested_claim_ids if selection_mode == "claim_ids" else [],
        },
        "generation": {
            "model": args.model,
            "prompt_version": CLAIM_SUPPORT_PROMPT_VERSION,
            "batch_size": args.batch_size,
            "planned_batch_count": len(batches),
            "completed_batch_count": checkpoint["completed_batch_count"],
            "model_call_count": checkpoint.get("model_call_count", 0),
            "repair_call_count": checkpoint.get("repair_call_count", 0),
            "model_timeout_seconds": args.model_timeout_seconds,
            "model_max_retries": args.model_max_retries,
        },
        "summary": summary,
        "results": results,
        "priority_findings": build_priority_findings(results),
        "warnings": [],
        "errors": checkpoint.get("errors") or [],
    }
    return output


def format_report(result: dict[str, Any], output_path: Path, checkpoint_path: Path) -> str:
    summary = result["summary"]
    generation = result["generation"]
    input_info = result["input"]
    lines = [
        "BOOK CLAIM SUPPORT AUDIT",
        f"Input: {input_info['claim_evidence_file']}",
        f"Source PDF: {input_info.get('source_pdf')}",
        f"Book slug: {input_info.get('book_slug')}",
        f"Model: {generation['model']}",
        f"Prompt version: {generation['prompt_version']}",
        f"Run status: {result['run_status']}",
        f"Audit verdict: {result['audit_verdict']}",
        "",
        "EXECUTION",
        f"Input claims: {input_info['input_claim_count']}",
        f"Selected claims: {input_info['selected_claim_count']}",
        f"Judged claims: {summary['judged_claim_count']}",
        f"Planned batches: {generation['planned_batch_count']}",
        f"Completed batches: {generation['completed_batch_count']}",
        f"Model calls: {generation['model_call_count']}",
        f"Repair calls: {generation['repair_call_count']}",
        "",
        "SUPPORT RESULTS",
        f"Supported: {summary['supported_count']}",
        f"Partially supported: {summary['partially_supported_count']}",
        f"Unsupported: {summary['unsupported_count']}",
        f"Contradicted: {summary['contradicted_count']}",
        f"Source damaged: {summary['source_damaged_count']}",
        f"Not factual: {summary['not_factual_count']}",
        "",
        "SEVERITY",
        f"High findings: {summary['high_severity_finding_count']}",
        f"Medium findings: {summary['medium_severity_finding_count']}",
        f"Low findings: {summary['low_severity_finding_count']}",
        f"Severity floors applied: {summary['severity_floor_applied_count']}",
        "",
        "CLAIM NATURE",
    ]
    for key, count in summary["results_by_claim_nature"].items():
        lines.append(f"{key}: {count}")
    lines.extend(["", "CLAIM TYPE RESULTS"])
    for key, count in summary["results_by_claim_type"].items():
        lines.append(f"{key}: {count}")
    lines.extend(["", "CHAPTER RESULTS"])
    for key, record in summary["results_by_chapter"].items():
        lines.append(
            f"{key}: claims={record['claim_count']} supported={record['supported_count']} "
            f"partial={record['partially_supported_count']} unsupported={record['unsupported_count']} "
            f"contradicted={record['contradicted_count']} source_damaged={record['source_damaged_count']} "
            f"not_factual={record['not_factual_count']} high_findings={record['high_severity_finding_count']}"
        )
    lines.extend(["", "HIGH-PRIORITY FINDINGS"])
    for item in result["priority_findings"][:50]:
        lines.append(
            f"- {item['claim_id']} | chapter {item.get('chapter_number')} | "
            f"{item['support_status']} | {item['claim_type']} | "
            f"{item['claim_text']} | {item['recommended_action']}"
        )
    if not result["priority_findings"]:
        lines.append("- none")

    known_checks = {
        "wanted pronunciation": "chapter_02.worked_examples.2.explanation",
        "Highlight Correct Summary": "chapter_15.key_terms.1.meaning",
        "spelling/zero-score rule": "chapter_11.common_misconceptions.2.correction",
        "essay timing": "chapter_16.core_lessons.4.explanation",
    }
    results_by_id = {item["claim_id"]: item for item in result["results"]}
    lines.extend(["", "KNOWN PTE CHECKS"])
    for label, claim_id in known_checks.items():
        item = results_by_id.get(claim_id)
        if item is None:
            lines.append(f"- {label}: not selected")
        else:
            lines.append(
                f"- {label}: {item['support_status']} | {item['severity']} | "
                f"{item['recommended_action']}"
            )

    lines.extend(["", "WARNINGS"])
    lines.extend([f"- {warning}" for warning in result.get("warnings") or []] or ["- none"])
    lines.extend(["", "ERRORS"])
    lines.extend([f"- {error}" for error in result.get("errors") or []] or ["- none"])
    lines.extend(
        [
            "",
            "OUTPUT",
            f"JSON: {output_path}",
            f"Checkpoint: {checkpoint_path}",
            "",
        ]
    )
    return "\n".join(lines)


def dry_run_diagnostics(
    *,
    artifact: dict[str, Any],
    selected_claims: list[dict[str, Any]],
    batches: list[PlannedBatch],
    evidence_by_id: dict[str, dict[str, Any]],
    output_path: Path,
    checkpoint_path: Path,
    report_path: Path | None,
) -> None:
    cited_claim_count = sum(1 for claim in selected_claims if claim.get("source_chunk_ids"))
    uncited_claim_count = len(selected_claims) - cited_claim_count
    bundle_count = len(
        {
            (batch.chapter_number, batch.source_chunk_ids)
            for batch in batches
        }
    )
    print(f"Input claims: {len(artifact['claims'])}")
    print(f"Selected claims: {len(selected_claims)}")
    print(f"Cited claims: {cited_claim_count}")
    print(f"Uncited claims: {uncited_claim_count}")
    print(f"Evidence chunks available: {len(artifact['evidence_chunks'])}")
    print(f"Evidence bundles: {bundle_count}")
    print(f"Planned model batches: {len(batches)}")
    print(f"Largest evidence bundle chars: {largest_evidence_bundle_chars(batches, evidence_by_id)}")
    print(f"Output would be written: {output_path}")
    print(f"Checkpoint would be written: {checkpoint_path}")
    if report_path is not None:
        print(f"Report would be written: {report_path}")
    print("Model calls made: 0")
    print("Dry run complete: no files written")


def run_audit(
    args: argparse.Namespace,
    *,
    complete_fn: Callable[[str], str] | None = None,
    repair_complete_fn: Callable[[str], str] | None = None,
) -> dict[str, Any] | None:
    input_path = Path(args.input)
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else None
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else default_checkpoint_path(output_path)
    raw_dir = raw_dir_for_output(output_path)

    if args.batch_size < 1:
        raise BookClaimSupportAuditError("--batch-size must be at least 1.")
    if args.model_timeout_seconds < 1:
        raise BookClaimSupportAuditError("--model-timeout-seconds must be at least 1.")
    if args.model_max_retries < 0:
        raise BookClaimSupportAuditError("--model-max-retries cannot be negative.")

    artifact = load_claim_evidence(input_path)
    input_hash = sha256_file(input_path)
    evidence_by_id = evidence_lookup(artifact)
    selected_claims, selection_mode, requested_claim_ids = select_claims(
        artifact["claims"],
        args.claim_id,
    )
    selected_claim_ids = [claim["claim_id"] for claim in selected_claims]
    batches = build_batches(selected_claims, args.batch_size)

    if args.dry_run:
        dry_run_diagnostics(
            artifact=artifact,
            selected_claims=selected_claims,
            batches=batches,
            evidence_by_id=evidence_by_id,
            output_path=output_path,
            checkpoint_path=checkpoint_path,
            report_path=report_path,
        )
        return None

    ensure_outputs_can_write(
        output_path=output_path,
        report_path=report_path,
        checkpoint_path=checkpoint_path,
        resume=args.resume,
        overwrite=args.overwrite,
    )

    if args.overwrite and not args.resume and raw_dir.exists():
        shutil.rmtree(raw_dir)

    if args.resume:
        checkpoint = require_object(load_json(checkpoint_path, "Checkpoint"), "Checkpoint")
        validate_resume_checkpoint(
            checkpoint=checkpoint,
            input_file=input_path,
            input_sha256=input_hash,
            model=args.model,
            batch_size=args.batch_size,
            selected_claim_ids=selected_claim_ids,
        )
        results_by_claim_id = dict(checkpoint.get("results_by_claim_id") or {})
        completed_batch_count = int(checkpoint.get("completed_batch_count") or 0)
        errors = list(checkpoint.get("errors") or [])
        stats = RuntimeStats(
            model_call_count=int(checkpoint.get("model_call_count") or 0),
            repair_call_count=int(checkpoint.get("repair_call_count") or 0),
        )
    else:
        results_by_claim_id = {}
        completed_batch_count = 0
        errors = []
        stats = RuntimeStats()
        initial = checkpoint_payload(
            status="IN_PROGRESS",
            input_file=input_path,
            input_sha256=input_hash,
            model=args.model,
            batch_size=args.batch_size,
            selected_claim_ids=selected_claim_ids,
            selected_claim_count=len(selected_claims),
            planned_batch_count=len(batches),
            completed_batch_count=0,
            results_by_claim_id=results_by_claim_id,
            errors=errors,
            model_call_count=0,
            repair_call_count=0,
        )
        write_checkpoint(checkpoint_path, initial)

    for batch in batches:
        batch_claim_ids = [claim["claim_id"] for claim in batch.claims]
        missing_claims = [
            claim for claim in batch.claims if claim["claim_id"] not in results_by_claim_id
        ]
        if not missing_claims:
            continue

        effective_batch = PlannedBatch(
            batch_id=batch.batch_id,
            chapter_number=batch.chapter_number,
            source_chunk_ids=batch.source_chunk_ids,
            claims=missing_claims,
        )
        try:
            batch_results = audit_batch_with_repair(
                batch=effective_batch,
                evidence_by_id=evidence_by_id,
                args=args,
                raw_dir=raw_dir,
                complete_fn=complete_fn,
                repair_complete_fn=repair_complete_fn,
                stats=stats,
            )
        except Exception as error:
            errors.append(
                {
                    "batch_id": batch.batch_id,
                    "claim_ids": [claim["claim_id"] for claim in missing_claims],
                    "error": str(error),
                }
            )
            failure_checkpoint = checkpoint_payload(
                status="IN_PROGRESS",
                input_file=input_path,
                input_sha256=input_hash,
                model=args.model,
                batch_size=args.batch_size,
                selected_claim_ids=selected_claim_ids,
                selected_claim_count=len(selected_claims),
                planned_batch_count=len(batches),
                completed_batch_count=completed_batch_count,
                results_by_claim_id=results_by_claim_id,
                errors=errors,
                model_call_count=stats.model_call_count,
                repair_call_count=stats.repair_call_count,
            )
            write_checkpoint(checkpoint_path, failure_checkpoint)
            resume_command = (
                f'python audit_book_claim_support.py --input "{input_path}" '
                f'--output "{output_path}" '
                + (f'--report "{report_path}" ' if report_path else "")
                + f'--checkpoint "{checkpoint_path}" --model {args.model} '
                f"--batch-size {args.batch_size} "
                f"--model-timeout-seconds {args.model_timeout_seconds} "
                f"--model-max-retries {args.model_max_retries} --resume"
            )
            raise BookClaimSupportAuditError(
                f"Batch {batch.batch_id} failed: {error}\nResume with:\n{resume_command}"
            ) from error

        for claim, result in zip(missing_claims, batch_results):
            results_by_claim_id[claim["claim_id"]] = result

        completed_batch_count += 1
        checkpoint = checkpoint_payload(
            status="IN_PROGRESS",
            input_file=input_path,
            input_sha256=input_hash,
            model=args.model,
            batch_size=args.batch_size,
            selected_claim_ids=selected_claim_ids,
            selected_claim_count=len(selected_claims),
            planned_batch_count=len(batches),
            completed_batch_count=completed_batch_count,
            results_by_claim_id=results_by_claim_id,
            errors=errors,
            model_call_count=stats.model_call_count,
            repair_call_count=stats.repair_call_count,
        )
        write_checkpoint(checkpoint_path, checkpoint)
        print(
            f"Completed {batch.batch_id}: {len(batch_results)} claim(s). "
            f"Completed claims: {len(results_by_claim_id)}/{len(selected_claims)}",
            flush=True,
        )

    complete_checkpoint = checkpoint_payload(
        status="COMPLETE",
        input_file=input_path,
        input_sha256=input_hash,
        model=args.model,
        batch_size=args.batch_size,
        selected_claim_ids=selected_claim_ids,
        selected_claim_count=len(selected_claims),
        planned_batch_count=len(batches),
        completed_batch_count=len(batches),
        results_by_claim_id=results_by_claim_id,
        errors=errors,
        model_call_count=stats.model_call_count,
        repair_call_count=stats.repair_call_count,
    )
    write_checkpoint(checkpoint_path, complete_checkpoint)

    final = build_final_output(
        artifact=artifact,
        input_path=input_path,
        input_sha256=input_hash,
        selected_claims=selected_claims,
        selection_mode=selection_mode,
        requested_claim_ids=requested_claim_ids,
        batches=batches,
        checkpoint=complete_checkpoint,
        args=args,
    )
    atomic_write_json(output_path, final)
    if report_path is not None:
        atomic_write_text(report_path, format_report(final, output_path, checkpoint_path))

    print("Book claim support audit completed.")
    print(f"Input claims: {len(artifact['claims'])}")
    print(f"Selected claims: {len(selected_claims)}")
    print(f"Judged claims: {len(final['results'])}")
    print(f"Audit verdict: {final['audit_verdict']}")
    print(f"Priority findings: {len(final['priority_findings'])}")
    print(f"Output written: {output_path}")
    if report_path is not None:
        print(f"Report written: {report_path}")
    print(f"Checkpoint written: {checkpoint_path}")
    return final


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        run_audit(args)
        return 0
    except BookClaimSupportAuditError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
