"""All our loop-fit checks, across stages, behind one contract.

For a long time each stage had its own checker that a human ran by hand:
extraction damage, question-bank shape, chart-item shape, enrichment facts. This
registry brings them under the one shape (evaluation_contract) so an LLM can call
any of them, read what failed, fix its output, and call again.

Every evaluator here carries planted-error self-tests, and the same honesty gate
applies to all of them: a check may only certify (PASS) if, on this run, it caught
its own planted error. A check that has silently rotted is reported unhealthy and
can never return PASS (evaluation_contract.verdict_of).

Artifacts an evaluator consumes:
  clean_chunks         the extracted source text, as a list of chunk dicts
  reading_item         one Reading Multiple-Choice question
  describe_image_item  one Describe Image chart item
  enrichment_lesson    one enrichment (teaching-layer) lesson

Two kinds of check:
  deterministic  pure code, same answer every run — the backbone. Fast health.
  model          uses the model (guide judge, blind solver). Advisory, and its
                 self-test costs model calls, so it runs only in a deep health check.

Not here, on purpose: the grounded-base contract validator, the claim-support
audit, and the targeted evaluation are batch pipelines (disk fixtures, checkpoint/
resume, long model runs). They do not fit a live generate->check->fix loop, and
wrapping them as synchronous tools without an honest self-test would be exactly
the false-confidence trap this whole design exists to prevent. They need an async
job interface, tracked separately.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from evaluation_contract import EvaluatorResult, Finding, verdict_of

import scan_clean_chunk_damage as extraction
import reading_mcq_items as reading
import describe_image_items as di
import enrichment_evaluators as enrich

ROOT = Path(__file__).resolve().parent


# --------------------------------------------------------------------------- #
# Evaluator model
# --------------------------------------------------------------------------- #

@dataclass
class Evaluator:
    name: str
    artifact: str                 # which artifact it consumes (see module docstring)
    kind: str                     # "deterministic" | "model"
    description: str              # written FOR the LLM: what it proves, when to call
    findings_fn: Callable[[Any], list[Finding]]
    # (payload, must_flag): must_flag=True -> has to produce a finding; False ->
    # must stay silent. Both the live run and the self-test call findings_fn, so a
    # broken check cannot pass its self-test while doing nothing in production.
    self_tests: list[tuple[Any, bool]]

    def run(self, payload: Any) -> EvaluatorResult:
        healthy, note = self_check(self.name)
        findings = self.findings_fn(payload) if healthy else []
        return EvaluatorResult(
            evaluator=self.name,
            verdict=verdict_of(findings, healthy=healthy),
            findings=findings,
            healthy=healthy,
            health_note=note,
            advisory={"artifact": self.artifact, "kind": self.kind},
        )


# --------------------------------------------------------------------------- #
# Stage 1 — extraction damage (deterministic)
# --------------------------------------------------------------------------- #

def _extraction_findings(chunks: list[dict[str, Any]]) -> list[Finding]:
    r = extraction.scan_chunks(chunks)
    out: list[Finding] = []
    if r["empty_count"]:
        out.append(Finding(
            summary=f"{r['empty_count']} extracted chunk(s) are empty.",
            detail="Empty source text cannot ground a lesson; re-extract these pages.",
            fixable=False,   # the SOURCE is damaged — a human/re-extract, not a reword
        ))
    if r["suspected_gap_count"]:
        ex = r["suspected_gap"][0]["examples"][0] if r["suspected_gap"][0]["examples"] else ""
        out.append(Finding(
            summary=f"{r['suspected_gap_count']} chunk(s) show gap damage from extraction.",
            detail=f"Words split by runs of spaces, e.g. …{ex}… — the PDF text is garbled.",
            evidence=ex,
            fixable=False,   # bad extraction; fix upstream, do not let the model paper over it
        ))
    return out


_DAMAGED_CHUNK = [{"node_id": "n1", "text": "the  quick  brown fox jumps over the lazy dog and runs"}]
_CLEAN_CHUNK = [{"node_id": "n1", "text": "The quick brown fox jumps over the lazy dog and then runs home."}]


# --------------------------------------------------------------------------- #
# Stage 2 — practice-bank shape (deterministic)
# --------------------------------------------------------------------------- #

def _reading_shape_findings(item: dict[str, Any]) -> list[Finding]:
    ok, why = reading.contract_validate(item)
    if ok:
        return []
    return [Finding(summary=f"Reading item fails its shape contract: {why}", detail=why, fixable=True)]


def _di_shape_findings(item: dict[str, Any]) -> list[Finding]:
    ok, why = di.contract_validate(item)
    if ok:
        return []
    return [Finding(summary=f"Describe Image item fails its shape contract: {why}", detail=why, fixable=True)]


def _load_json(path: str):
    p = ROOT / path
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("items", "passages", "prompts"):
            if k in data:
                return data[k]
    return data


def _reading_fixtures() -> list[tuple[dict, bool]]:
    bank = _load_json("output/reading_mcq_items.json") or []
    if not bank:
        return []
    good = bank[0]
    bad = json.loads(json.dumps(good))
    bad["options"] = bad["options"][:2]  # too few options -> must flag
    return [(good, False), (bad, True)]


def _di_fixtures() -> list[tuple[dict, bool]]:
    bank = _load_json("output/describe_image_items.json") or []
    if not bank:
        return []
    good = bank[0]
    bad = json.loads(json.dumps(good))
    bad["points"] = [bad["points"][0]]  # too few points -> must flag
    return [(good, False), (bad, True)]


# --------------------------------------------------------------------------- #
# Stage 2b — reading answer key, by blind solve (model, advisory)
# --------------------------------------------------------------------------- #

def _reading_key_findings(item: dict[str, Any]) -> list[Finding]:
    ok, why = reading.verify(item, model=reading.DEFAULT_MODEL)
    if ok:
        return []
    return [Finding(
        summary="Independent readers did not agree with the answer key.",
        detail=f"{why} — the item is ambiguous or the key is wrong; do not ship it.",
        fixable=True,   # regenerate the item
    )]


def _reading_key_fixtures() -> list[tuple[dict, bool]]:
    bank = _load_json("output/reading_mcq_items.json") or []
    single = next((i for i in bank if i.get("mode") == "single"), None)
    if not single:
        return []
    good = single
    bad = json.loads(json.dumps(single))
    # Re-key to a deliberately wrong option -> solvers must disagree -> must flag.
    wrong = next(o["key"] for o in bad["options"] if o["key"] not in bad["correct"])
    bad["correct"] = [wrong]
    return [(good, False), (bad, True)]


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

REGISTRY: dict[str, Evaluator] = {
    "extraction_damage": Evaluator(
        name="extraction_damage",
        artifact="clean_chunks",
        kind="deterministic",
        description=(
            "Flags source chunks whose extracted text is empty or garbled (words "
            "split by runs of spaces — a common PDF-extraction failure). Damaged "
            "source cannot ground a trustworthy lesson. Findings are ESCALATE, not "
            "fix: the model must not paper over bad extraction by rewording — the "
            "source has to be re-extracted."
        ),
        findings_fn=_extraction_findings,
        self_tests=[(_DAMAGED_CHUNK, True), (_CLEAN_CHUNK, False)],
    ),
    "reading_item_shape": Evaluator(
        name="reading_item_shape",
        artifact="reading_item",
        kind="deterministic",
        description=(
            "Checks one Reading Multiple-Choice question has the required shape: "
            "passage length, the right number of options with keys A.., a correct "
            "set that matches the mode (one for single, 2+ for multiple), and a "
            "rationale for every option. Call on each generated question."
        ),
        findings_fn=_reading_shape_findings,
        self_tests=_reading_fixtures(),
    ),
    "describe_image_item_shape": Evaluator(
        name="describe_image_item_shape",
        artifact="describe_image_item",
        kind="deterministic",
        description=(
            "Checks one Describe Image chart item has the required shape: a known "
            "chart type, 4-8 data points with non-negative numeric values, pie "
            "values that sum to 100, and not every value identical. Call on each "
            "generated chart item."
        ),
        findings_fn=_di_shape_findings,
        self_tests=_di_fixtures(),
    ),
    "reading_answer_key": Evaluator(
        name="reading_answer_key",
        artifact="reading_item",
        kind="model",
        description=(
            "Checks a Reading question's ANSWER KEY by having independent solvers "
            "answer it cold, without seeing the key. If they don't unanimously land "
            "on the keyed answer, the item is ambiguous or mis-keyed and must not "
            "ship. Uses the model (several solves per item), so it is slower and "
            "advisory. Call before publishing a question."
        ),
        findings_fn=_reading_key_findings,
        self_tests=_reading_key_fixtures(),
    ),
}

# Reuse the enrichment evaluators exactly as they are — same contract, same gate.
for _name, _ev in enrich.REGISTRY.items():
    REGISTRY[_name] = Evaluator(
        name=_ev.name,
        artifact="enrichment_lesson",
        kind="deterministic",
        description=_ev.description,
        findings_fn=_ev.findings_fn,
        self_tests=_ev.self_tests,
    )


# --------------------------------------------------------------------------- #
# Health + dispatch
# --------------------------------------------------------------------------- #

def self_check(name: str) -> tuple[bool, str]:
    ev = REGISTRY[name]
    if not ev.self_tests:
        return False, "no self-tests registered (cannot prove it still catches errors)"
    for payload, must_flag in ev.self_tests:
        try:
            flagged = bool(ev.findings_fn(payload))
        except Exception as exc:
            return False, f"self-test raised {type(exc).__name__}: {exc}"
        if flagged != must_flag:
            verb = "missed a planted error" if must_flag else "flagged a correct input"
            return False, f"self-test failed: {verb}"
    return True, f"{len(ev.self_tests)} planted-error cases pass"


def health_report(*, deep: bool = False) -> dict[str, Any]:
    """Run every deterministic evaluator's self-test; include model ones only when
    deep (they cost model calls). all_healthy covers whatever was actually run."""
    report = {}
    for name, ev in REGISTRY.items():
        if ev.kind == "model" and not deep:
            report[name] = {"kind": ev.kind, "healthy": None, "note": "skipped (deep=true to run model self-test)"}
            continue
        healthy, note = self_check(name)
        report[name] = {"kind": ev.kind, "healthy": healthy, "note": note}
    ran = [v for v in report.values() if v["healthy"] is not None]
    return {
        "all_healthy": all(v["healthy"] for v in ran) if ran else False,
        "checked": len(ran),
        "deep": deep,
        "evaluators": report,
    }


def by_artifact(artifact: str) -> list[str]:
    return [n for n, ev in REGISTRY.items() if ev.artifact == artifact]


def evaluate(artifact: str, payload: Any, *, include_model: bool = False) -> list[EvaluatorResult]:
    """Run every applicable evaluator for an artifact. Model checks are skipped
    unless include_model, so the fast deterministic gate stays fast by default."""
    out = []
    for name in by_artifact(artifact):
        if REGISTRY[name].kind == "model" and not include_model:
            continue
        out.append(REGISTRY[name].run(payload))
    return out


def evaluate_one(name: str, payload: Any) -> EvaluatorResult:
    if name not in REGISTRY:
        raise KeyError(f"unknown evaluator {name!r}; have {list(REGISTRY)}")
    return REGISTRY[name].run(payload)
