"""Unit tests for the evaluator contract and the honesty gate.

No network: these pin the two properties that make the loop safe.
  1. A verdict is PASS only from a healthy evaluator with no findings.
  2. A rotted check cannot certify — break the underlying check and the gate must
     turn the result into ESCALATE, never a false PASS.

    python test_evaluation_contract.py
"""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import enrichment_evaluators as E
from evaluation_contract import Finding, Verdict, combine, verdict_of

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


print("verdict_of")
check("no findings + healthy -> pass",
      verdict_of([], healthy=True) is Verdict.PASS)
check("no findings but UNHEALTHY -> escalate (never a false all-clear)",
      verdict_of([], healthy=False) is Verdict.ESCALATE)
check("a fixable finding -> fix",
      verdict_of([Finding("x", fixable=True)], healthy=True) is Verdict.FIX)
check("a non-fixable finding -> escalate",
      verdict_of([Finding("x", fixable=False)], healthy=True) is Verdict.ESCALATE)
check("escalate outranks fix",
      verdict_of([Finding("a", fixable=True), Finding("b", fixable=False)],
                 healthy=True) is Verdict.ESCALATE)

print("\ncombine (the gate)")
# A task with no length band and no scoring-factor names has nothing for these
# checks to catch, so it passes cleanly. (An essay would NOT: it must state its
# 200-300 word range, so an empty essay correctly gets 'fix'.)
doc_ok = {"task_type": "answer_short_question", "overview": {
    "format_facts": [], "critical_rules": [], "scoring_factors": []}}
res = combine(E.evaluate_all(doc_ok))
check("a lesson with nothing to flag passes cleanly",
      res["verdict"] == "pass" and res["accepted"], str(res["verdict"]))

# And the essay case is the useful one: silence here would be the bug.
essay_empty = {"task_type": "write_essay", "overview": {
    "format_facts": [], "critical_rules": [], "scoring_factors": []}}
res = combine(E.evaluate_all(essay_empty))
check("an essay that omits its word range gets 'fix', not a pass",
      res["verdict"] == "fix" and not res["accepted"], str(res["verdict"]))

print("\nhealth")
h = E.health_report()
check("all registered evaluators are healthy", h["all_healthy"] is True, str(h))

print("\nthe honesty gate: a broken check must not certify")
real = E.audit.check_word_range
E.audit.check_word_range = lambda doc, ev: []  # silently catches nothing
try:
    res = combine(E.evaluate_all(doc_ok))
    check("broken check -> escalate, not pass", res["verdict"] == "escalate", str(res["verdict"]))
    check("broken check -> not accepted", res["accepted"] is False)
    check("broken check named in unhealthy list", "word_range" in res["unhealthy_evaluators"])
finally:
    E.audit.check_word_range = real
check("health recovers after repair", E.health_report()["all_healthy"] is True)

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "contract + gate hold")
raise SystemExit(1 if fails else 0)
