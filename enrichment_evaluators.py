"""The enrichment evaluators, wrapped in the standard contract for an LLM to call.

This adds no new checking logic. Every check here already lives in
audit_enrichment_facts.py, tested and trusted; this module only re-expresses it in
the shared shape (see evaluation_contract) and attaches, to each one, a self-test
that plants a known-wrong input and confirms the check still catches it.

That self-test is not decoration. Three times in this project a check silently
stopped catching anything while still printing green. An evaluator that cannot
pass its own planted-error test is marked unhealthy, and an unhealthy evaluator is
never allowed to certify a lesson (evaluation_contract.verdict_of). The health
check runs on demand — cheaply, in code — so the agent (or a human) can confirm
the tools still bite before trusting a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import audit_enrichment_facts as audit
from evaluation_contract import EvaluatorResult, Finding, Verdict, verdict_of

# Loaded once; the guide is the ground truth every enrichment check reads from.
_PAGES: list[str] | None = None


def _guide_pages() -> list[str]:
    global _PAGES
    if _PAGES is None:
        _PAGES = audit.load_guide_pages(audit.DEFAULT_GUIDE)
    return _PAGES


def _rubric(task_type: str) -> tuple[str, bool]:
    """The task's own rubric text from the guide, and whether it was located."""
    evidence, _pages, matched = audit.guide_text_for(task_type, _guide_pages(), rubric_only=True)
    return evidence, matched


# --------------------------------------------------------------------------- #
# Evaluator registry
# --------------------------------------------------------------------------- #

@dataclass
class Evaluator:
    name: str
    # Written FOR THE LLM: what the check proves and when to call it. The model
    # reads these to decide which tools apply to the lesson in hand.
    description: str
    # The raw check: doc -> findings. BOTH the live run and the self-test call
    # exactly this, so the self-test can never pass while the real path is broken
    # (the bug that let a rotted check keep certifying — they must be one path).
    findings_fn: Callable[[dict[str, Any]], list[Finding]]
    # Planted-error cases: (a doc, must_flag). must_flag=True -> the check has to
    # produce a finding; False -> it must stay silent. The docs carry their own
    # task_type, so the self-test drives the very function the live run uses.
    self_tests: list[tuple[dict[str, Any], bool]]

    def run(self, doc: dict[str, Any]) -> EvaluatorResult:
        healthy, note = _self_check_one(self.name)
        findings = self.findings_fn(doc) if healthy else []
        return EvaluatorResult(
            evaluator=self.name,
            verdict=verdict_of(findings, healthy=healthy),
            findings=findings,
            healthy=healthy,
            health_note=note,
        )


def _word_range_findings(doc: dict[str, Any]) -> list[Finding]:
    task = doc.get("task_type", "")
    evidence, matched = _rubric(task)
    if not matched:
        return []  # no rubric located -> this check simply does not apply
    out = []
    for d in audit.check_word_range(doc, evidence):
        out.append(Finding(
            summary=f"The {d['range']}-word range that gates Form is never stated.",
            detail=d["reason"],
            evidence=f"Guide rubric for {task}",
            fixable=True,   # add the range to the lesson and resubmit
        ))
    return out


def _trait_findings(doc: dict[str, Any]) -> list[Finding]:
    task = doc.get("task_type", "")
    evidence, matched = _rubric(task)
    if not matched:
        return []
    out = []
    for d in audit.check_trait_vocabulary(doc, evidence):
        out.append(Finding(
            summary=f"Uses the official trait name '{d['factor']}' on the wrong task.",
            detail=d["reason"],
            evidence=f"Guide rubric for {task}",
            fixable=True,   # rename to the task's real trait, or paraphrase
        ))
    return out


# Minimal docs whose only meaningful content is the field each check reads.
def _doc(task: str, *, facts=None, rules=None, factors=None) -> dict[str, Any]:
    return {"task_type": task, "overview": {
        "format_facts": facts or [],
        "critical_rules": rules or [],
        "scoring_factors": factors or [],
    }}


REGISTRY: dict[str, Evaluator] = {
    "word_range": Evaluator(
        name="word_range",
        description=(
            "Checks a Summarize/Write lesson STATES the word range that Pearson uses "
            "to score Form. Form gates the whole response — miss the range and the "
            "score collapses regardless of quality — so a lesson that never gives the "
            "number leaves the learner blind. Call this for any lesson whose task has "
            "a length band (write_essay, summarize_written_text, summarize_spoken_text "
            "…). Passes silently for tasks with no length band."
        ),
        findings_fn=_word_range_findings,
        self_tests=[
            # SST rubric gates Form on 50-70 words; a lesson that names no range must flag.
            (_doc("summarize_spoken_text_and_highlight_correct_summary",
                  rules=["Verify content, word-count compliance, and spelling."]), True),
            # ...and one that states it must NOT flag.
            (_doc("summarize_spoken_text_and_highlight_correct_summary",
                  rules=["Keep the summary between 50 and 70 words."]), False),
        ],
    ),
    "trait_names": Evaluator(
        name="trait_names",
        description=(
            "Checks the lesson does not attach one of Pearson's OFFICIAL trait names "
            "(Content, Form, Grammar, Vocabulary Range, Spelling, Oral Fluency, "
            "Pronunciation …) to a task that is not scored on it — e.g. calling an "
            "essay's vocabulary trait 'Vocabulary' when essays use 'Vocabulary Range', "
            "or listing 'Oral Fluency' on a writing task. Teaching paraphrases in the "
            "lesson's own words are fine and are ignored. Call for any scored task."
        ),
        findings_fn=_trait_findings,
        self_tests=[
            # 'Oral Fluency' is a speaking trait; on write_essay it must flag.
            (_doc("write_essay", factors=[{"name": "Oral Fluency", "what_it_measures": "x"}]), True),
            # 'Spelling' genuinely scores Write Essay; must NOT flag.
            (_doc("write_essay", factors=[{"name": "Spelling", "what_it_measures": "x"}]), False),
            # A teaching paraphrase is not an official name; must NOT flag.
            (_doc("write_essay", factors=[{"name": "Main-idea coverage", "what_it_measures": "x"}]), False),
        ],
    ),
}


# --------------------------------------------------------------------------- #
# Health — the honesty gate
# --------------------------------------------------------------------------- #

def _self_check_one(name: str) -> tuple[bool, str]:
    """Run one evaluator's planted-error cases through the SAME findings_fn the
    live run uses. Healthy iff every case comes out as expected: the broken inputs
    are flagged, the sound ones are not. Because this drives findings_fn — not a
    separately-held reference — a check that has been broken cannot pass here while
    silently doing nothing in production; the two are the same code path."""
    ev = REGISTRY[name]
    for doc, must_flag in ev.self_tests:
        try:
            flagged = bool(ev.findings_fn(doc))
        except Exception as exc:  # a check that throws is not a healthy check
            return False, f"self-test raised {type(exc).__name__}: {exc}"
        if flagged != must_flag:
            verb = "missed a planted error" if must_flag else "flagged a correct input"
            return False, f"self-test failed: {verb}"
    return True, f"{len(ev.self_tests)} planted-error cases pass"


def health_report() -> dict[str, Any]:
    """Every evaluator's self-test result — the proof the tools still bite."""
    report = {}
    for name in REGISTRY:
        healthy, note = _self_check_one(name)
        report[name] = {"healthy": healthy, "note": note}
    return {
        "all_healthy": all(v["healthy"] for v in report.values()),
        "evaluators": report,
    }


def applicable(task_type: str) -> list[str]:
    """Which evaluators have something to say about this task. An evaluator whose
    rubric isn't in the guide, or that finds no length band, simply passes — so
    'applicable' here means 'registered and healthy enough to run', and the run
    itself decides pass/skip."""
    return list(REGISTRY)


def evaluate_all(doc: dict[str, Any]) -> list[EvaluatorResult]:
    return [REGISTRY[name].run(doc) for name in applicable(doc.get("task_type", ""))]


def evaluate_one(name: str, doc: dict[str, Any]) -> EvaluatorResult:
    if name not in REGISTRY:
        raise KeyError(f"unknown evaluator {name!r}; have {list(REGISTRY)}")
    return REGISTRY[name].run(doc)
