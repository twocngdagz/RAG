"""Repair grounded claims the semantic audit flagged, then re-audit until clean.

Chapters kept passing the contract yet failing the semantic audit on a single
recurring defect: a grounded text asserting slightly more than its evidence
spans cover -- "the answer as psychologist" with no span quoting the answer, or a
list of eight word-bank categories whose span quotes only five. Not a
hallucination; the source usually contains the missing support, the model just
did not quote all of it. So the fix is normally to cite more, occasionally to
say less.

This feeds each flagged claim back to the model with the finding and the
chapter's own source chunks, regenerates that single grounded object to be fully
covered, normalizes it through the same enforcement the generator uses (a claim
that still cannot be covered is downgraded, not kept as an over-claim), and
writes the repaired chapter. The CLI drives extract -> audit -> repair for up to
--max-rounds, stopping as soon as no repairable finding remains.

SOURCE_DAMAGED is deliberately NOT repaired: it means the source chunk itself is
garbled, which rewriting a claim cannot fix. Those are reported and left for
scan_clean_chunk_damage.py and a source fix.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import book_learning_materials_v2_generation as v2
import generate_book_learning_materials as backends

# Statuses a claim rewrite can plausibly fix. SOURCE_DAMAGED and
# NOT_A_FACTUAL_CLAIM are excluded on purpose: the first is a source defect, the
# second is not a grounding failure.
REPAIRABLE_STATUSES = {"PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED"}


class RepairError(RuntimeError):
    pass


# --------------------------------------------------------------------------- #
# json_path navigation
# --------------------------------------------------------------------------- #

def parse_json_path(path: str) -> list[Any]:
    """`$.learning_materials.chapters[0].worked_examples[2].explanation`
    -> ['learning_materials','chapters',0,'worked_examples',2,'explanation']."""
    body = path.lstrip("$").lstrip(".")
    tokens: list[Any] = []
    for part in body.split("."):
        match = re.match(r"^([^\[\]]+)((?:\[\d+\])*)$", part)
        if not match:
            raise RepairError(f"Unparseable json_path segment: {part!r} in {path!r}")
        tokens.append(match.group(1))
        tokens.extend(int(i) for i in re.findall(r"\[(\d+)\]", match.group(2)))
    return tokens


def get_at(root: Any, tokens: list[Any]) -> Any:
    node = root
    for token in tokens:
        node = node[token]
    return node


def set_at(root: Any, tokens: list[Any], value: Any) -> None:
    parent = get_at(root, tokens[:-1])
    parent[tokens[-1]] = value


# --------------------------------------------------------------------------- #
# Findings
# --------------------------------------------------------------------------- #

def repairable_findings(audit: dict[str, Any]) -> list[dict[str, Any]]:
    results = audit.get("results") or []
    return [
        r
        for r in results
        if r.get("support_status") in REPAIRABLE_STATUSES and r.get("json_path")
    ]


def unrepairable_findings(audit: dict[str, Any]) -> list[dict[str, Any]]:
    results = audit.get("results") or []
    return [r for r in results if r.get("support_status") == "SOURCE_DAMAGED"]


# --------------------------------------------------------------------------- #
# Repair prompt + one-field repair
# --------------------------------------------------------------------------- #

def build_repair_prompt(
    *,
    current: dict[str, Any],
    finding: dict[str, Any],
    source_context: str,
    allowed_ids: list[str],
) -> str:
    return f"""{v2.v2_schema_rules_text()}

You are repairing ONE grounded content object from a chapter. A grounding audit
judged it {finding.get("support_status")}: the text asserts more than its
evidence spans support.

Return JSON only: a single grounded content object with exactly the seven keys
text, claim_kind, origin, source_chunk_ids, grounded_in_source_chunk_ids,
evidence_spans, reason. Keep claim_kind = {current.get("claim_kind")!r}.

Fix it by making the evidence cover the WHOLE text:
- Prefer to CITE MORE: if the source supports an assertion you did not quote, add
  an exact evidence span for it. The missing support is often already in the
  source.
- Otherwise NARROW the text to exactly what the source supports, and drop any
  clause the source does not state.
Every assertion remaining in text must be covered by an exact quote in
evidence_spans. Do not add outside knowledge.

Allowed source chunk IDs: {allowed_ids}
Source chunks:
{source_context}

Current object to repair:
{json.dumps(current, ensure_ascii=False, indent=2)}
"""


def repair_field(
    *,
    current: dict[str, Any],
    finding: dict[str, Any],
    allowed_ids: list[str],
    clean_lookup: dict[str, dict[str, Any]],
    complete_fn: Callable[[str], str],
) -> tuple[dict[str, Any], str]:
    """Regenerate one grounded object; return (normalized_object, outcome).

    outcome is 'repaired' (now source_grounded with covering spans), 'downgraded'
    (could not be covered, safely reduced), or 'unchanged' (model output unusable
    so the original is kept)."""
    source_context = build_source_context(allowed_ids, clean_lookup)
    prompt = build_repair_prompt(
        current=current,
        finding=finding,
        source_context=source_context,
        allowed_ids=allowed_ids,
    )
    try:
        raw = complete_fn(prompt)
        candidate = json.loads(_strip_json(raw))
    except (backends.ModelCallError, backends.ModelJSONError, json.JSONDecodeError, ValueError):
        return current, "unchanged"

    if not isinstance(candidate, dict):
        return current, "unchanged"

    normalized = v2.normalize_grounded_content_object(
        candidate,
        allowed_ids=set(allowed_ids),
        clean_chunks_lookup=clean_lookup,
    )
    if normalized.get("origin") == "source_grounded" and normalized.get("evidence_spans"):
        return normalized, "repaired"
    # A covered rewrite was not achievable; the normalized downgrade (text nulled)
    # is still preferable to keeping an over-claim labelled source_grounded.
    return normalized, "downgraded"


def _strip_json(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def build_source_context(
    allowed_ids: list[str], clean_lookup: dict[str, dict[str, Any]]
) -> str:
    parts = []
    for node_id in allowed_ids:
        chunk = clean_lookup.get(node_id)
        if chunk and isinstance(chunk.get("text"), str):
            parts.append(
                json.dumps({"node_id": node_id, "text": chunk["text"]}, ensure_ascii=False)
            )
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# Repair a whole chapter/book from one audit
# --------------------------------------------------------------------------- #

def chapter_allowed_ids(book: dict[str, Any], chapter_index: int) -> list[str]:
    chapter = book["learning_materials"]["chapters"][chapter_index]
    ids = chapter.get("source_chunk_ids")
    return [str(i) for i in ids] if isinstance(ids, list) else []


def repair_book(
    book: dict[str, Any],
    audit: dict[str, Any],
    *,
    clean_lookup: dict[str, dict[str, Any]],
    complete_fn: Callable[[str], str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    log: list[dict[str, Any]] = []
    for finding in repairable_findings(audit):
        tokens = parse_json_path(finding["json_path"])
        try:
            current = get_at(book, tokens)
        except (KeyError, IndexError, TypeError):
            log.append({"json_path": finding["json_path"], "outcome": "not_found"})
            continue
        if not isinstance(current, dict):
            log.append({"json_path": finding["json_path"], "outcome": "not_grounded_object"})
            continue

        chapter_index = tokens[tokens.index("chapters") + 1]
        allowed_ids = chapter_allowed_ids(book, chapter_index)
        new_object, outcome = repair_field(
            current=current,
            finding=finding,
            allowed_ids=allowed_ids,
            clean_lookup=clean_lookup,
            complete_fn=complete_fn,
        )
        if outcome != "unchanged":
            set_at(book, tokens, new_object)
        log.append(
            {
                "json_path": finding["json_path"],
                "status": finding.get("support_status"),
                "outcome": outcome,
            }
        )
    return book, log


# --------------------------------------------------------------------------- #
# CLI: drive extract -> audit -> repair for up to --max-rounds
# --------------------------------------------------------------------------- #

def load_clean_lookup(clean_chunks_file: str) -> dict[str, dict[str, Any]]:
    from clean_section_chunk_lookup import clean_chunk_node_id, load_clean_chunk_collection

    chunks = load_clean_chunk_collection(clean_chunks_file)
    lookup: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        node_id = clean_chunk_node_id(chunk)
        if node_id:
            lookup.setdefault(node_id, chunk)
    return lookup


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--book-file", required=True)
    p.add_argument("--clean-chunks-file", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-rounds", type=int, default=2)
    p.add_argument("--codex-model", default=backends.DEFAULT_CODEX_MODEL)
    p.add_argument("--codex-reasoning-effort", default="high")
    p.add_argument("--audit-reasoning-effort", default="medium")
    p.add_argument("--work-dir", default=None, help="Where to write per-round claims/audit.")
    return p.parse_args(argv)


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd)
    if result.returncode not in (0, 1):  # audit exits 1 on FAIL verdict, which is fine
        raise RepairError(f"Command failed ({result.returncode}): {' '.join(cmd)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    book_path = Path(args.output)
    work = Path(args.work_dir) if args.work_dir else book_path.parent
    work.mkdir(parents=True, exist_ok=True)

    book = json.loads(Path(args.book_file).read_text(encoding="utf-8"))
    clean_lookup = load_clean_lookup(args.clean_chunks_file)
    complete_fn = lambda prompt: backends.complete_via_codex_cli(
        prompt,
        model=args.codex_model,
        reasoning_effort=args.codex_reasoning_effort,
        timeout_seconds=backends.DEFAULT_CLI_TIMEOUT_SECONDS,
    )

    book_path.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")
    claims_path = work / (book_path.stem + ".repair.claims.json")
    audit_path = work / (book_path.stem + ".repair.support.audit.json")
    py = sys.executable

    for round_no in range(1, args.max_rounds + 1):
        run([py, "extract_book_learning_claims.py", "--book-file", str(book_path),
             "--clean-chunks-file", args.clean_chunks_file, "--output", str(claims_path), "--overwrite"])
        run([py, "audit_book_claim_support.py", "--input", str(claims_path),
             "--output", str(audit_path), "--backend", "codex-cli",
             "--codex-model", args.codex_model,
             "--codex-reasoning-effort", args.audit_reasoning_effort, "--overwrite"])
        audit = json.loads(audit_path.read_text(encoding="utf-8"))

        findings = repairable_findings(audit)
        damaged = unrepairable_findings(audit)
        print(f"Round {round_no}: verdict={audit.get('audit_verdict')} "
              f"repairable={len(findings)} source_damaged={len(damaged)}", flush=True)
        for d in damaged:
            print(f"  SOURCE_DAMAGED (not repaired): {d.get('json_path')}", flush=True)
        if not findings:
            print("No repairable findings remain.", flush=True)
            return 0

        book, log = repair_book(book, audit, clean_lookup=clean_lookup, complete_fn=complete_fn)
        for entry in log:
            print(f"  {entry.get('outcome')}: {entry.get('json_path')} ({entry.get('status')})", flush=True)
        book_path.write_text(json.dumps(book, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Reached --max-rounds ({args.max_rounds}) with repairable findings still present.", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
