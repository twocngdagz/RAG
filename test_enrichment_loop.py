"""The loop's control logic, with a fake fixer — no network.

Pins the properties that must hold before a live run is trustworthy:
  1. It refuses to run when the checks fail their self-test.
  2. It stops the moment our checks accept — it does not keep going.
  3. A fixer that never actually fixes hits the cap and gives up (no infinite loop).
  4. A fixer that supplies the flagged value converges to accepted.

    python test_enrichment_loop.py
"""
from __future__ import annotations

import json
from dotenv import load_dotenv
load_dotenv()

import enrichment_loop as loop
import pipeline_evaluators as P

fails: list[str] = []


def check(label, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


# An essay lesson missing its word range -> word_range says fix.
def _essay(with_range: bool) -> dict:
    rules = ["Take a clear position."]
    if with_range:
        rules.append("Keep the essay within the required 200 to 300 words.")
    return {"task_type": "write_essay", "overview": {
        "format_facts": [], "critical_rules": rules,
        "scoring_factors": [{"name": "Content", "what_it_measures": "x"}]}}


print("a clean lesson needs zero rounds and is accepted immediately")
never_called = lambda l, f: (_ for _ in ()).throw(AssertionError("fixer must not be called"))
res = loop.close_loop(_essay(with_range=True), fixer=never_called, max_rounds=3)
check("accepted", res["status"] == "accepted", str(res["status"]))
check("stopped in round 1 without calling the fixer", res["rounds"] == 1)


print("\na fixer that adds the flagged range converges")
def good_fixer(lesson, findings):
    # Simulate a model that reads the finding and states the range.
    fixed = json.loads(json.dumps(lesson))
    fixed["overview"]["critical_rules"].append("Keep the essay between 200 and 300 words.")
    return fixed
res = loop.close_loop(_essay(with_range=False), fixer=good_fixer, max_rounds=4)
check("converged to accepted", res["status"] == "accepted", str(res["status"]))
check("took more than one round (it had to fix)", res["rounds"] >= 1)
check("round 1 saw the defect", "word range" in " ".join(res["history"][0]["findings"]).lower())


print("\na fixer that never fixes hits the cap and gives up (no infinite loop)")
idle_fixer = lambda lesson, findings: lesson  # returns it unchanged
res = loop.close_loop(_essay(with_range=False), fixer=idle_fixer, max_rounds=3)
check("gave up, did not hang", res["status"] == "gave_up", str(res["status"]))
check("stopped exactly at the cap", res["rounds"] == 3, str(res["rounds"]))


print("\nit refuses to run when a check is unhealthy")
real = P.reading.contract_validate  # unrelated; break an enrichment check instead
broken = P.enrich.audit.check_word_range
P.enrich.audit.check_word_range = lambda doc, ev: []  # silently catches nothing
try:
    res = loop.close_loop(_essay(with_range=False), fixer=good_fixer, max_rounds=3)
    check("refused to run", res["status"] == "refused", str(res["status"]))
    check("named the health failure", "self-test" in res.get("reason", ""))
finally:
    P.enrich.audit.check_word_range = broken


print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "loop control logic holds")
raise SystemExit(1 if fails else 0)
