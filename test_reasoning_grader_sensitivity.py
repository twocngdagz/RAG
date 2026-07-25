"""Is the advisory explanation coach worth listening to? Measured, not assumed.

test_math_reasoning.py proves the coach cannot affect a mark. That is a guarantee
about the wiring, and it holds whether the coach is brilliant or useless. This
asks the other question: does it actually distinguish a real explanation from a
hollow one? If it praises "because my teacher said so" as warmly as a worked
argument, it is noise on the screen and the child learns to ignore it.

Costs real model calls, so it is NOT part of the regression:

    python test_reasoning_grader_sensitivity.py

Severity is split, following test_audit_sensitivity.py. What the coach is relied
on for — discriminating explanation quality — is a hard failure. Its tone and
phrasing wander run to run, so those are reported as advisory and do not decide
the exit code. Everything that must be certain is already covered in code.
"""
from __future__ import annotations

import math_reasoning_feedback as mrf
import math_reasoning_items as mri

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

failures: list[str] = []
advisory: list[str] = []

# One item, several responses of known quality. Same question throughout so the
# only thing that varies is how well the thinking is explained.
ITEM = next(i for i in mri.build_items(20, seed=11) if i["skill"] == "spot_the_mistake_add")

HOLLOW = "because my teacher said so"
BARE = f"{ITEM['answer_plain']}"
PARTIAL = (
    f"Tom did it wrong. The answer is {ITEM['answer_plain']}."
)
GOOD = ITEM["model_answer"]

HARSH_WORDS = ("stupid", "bad at", "you failed", "poor effort", "terrible")
VERDICT_WORDS = ("your answer is correct", "your answer is wrong", "incorrect answer")


def grade(label: str, response: str) -> dict:
    det = mri.check_working(ITEM, response)
    out = mrf.score_reasoning(ITEM, response, det)
    why = next(t["score"] for t in out["traits"] if t["name"] == "explains_why")
    print(f"\n  {label}: explains_why={why}/3 "
          f"clear_steps={next(t['score'] for t in out['traits'] if t['name'] == 'clear_steps')}/3")
    print(f"    strength : {out['strength']}")
    print(f"    next step: {out['next_step']}")
    out["_why"] = why
    return out


def hard(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        failures.append(label)


def soft(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'warn'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        advisory.append(label)


print(f"Question: {ITEM['question']}")
print("\ngrading four responses of known quality")
hollow = grade("hollow    ", HOLLOW)
bare = grade("bare answer", BARE)
partial = grade("partial   ", PARTIAL)
good = grade("worked    ", GOOD)

print("\n--- what the coach is relied on for (hard) ---")
hard("a worked explanation scores well on 'says why'", good["_why"] >= 2, f"{good['_why']}/3")
hard("a hollow non-reason scores low on 'says why'", hollow["_why"] <= 1, f"{hollow['_why']}/3")
hard("the bare answer scores low on 'says why'", bare["_why"] <= 1, f"{bare['_why']}/3")
hard("it separates a worked explanation from a hollow one",
     good["_why"] > hollow["_why"], f"good={good['_why']} hollow={hollow['_why']}")
hard("it separates a worked explanation from a bare answer",
     good["_why"] > bare["_why"], f"good={good['_why']} bare={bare['_why']}")
hard("a partial answer lands between the two",
     hollow["_why"] <= partial["_why"] <= good["_why"], f"partial={partial['_why']}")
hard("every response still gets usable next-step text",
     all(o["next_step"].strip() for o in (hollow, bare, partial, good)))

print("\n--- tone and phrasing (advisory: model wording wanders run to run) ---")
for label, out in (("hollow", hollow), ("bare", bare), ("partial", partial), ("worked", good)):
    blob = " ".join((out["strength"], out["next_step"], out["coach_note"])).lower()
    soft(f"{label}: nothing harsh said to a child",
         not any(w in blob for w in HARSH_WORDS), blob[:120])
    soft(f"{label}: the coach does not pronounce on right/wrong",
         not any(w in blob for w in VERDICT_WORDS), blob[:120])
    soft(f"{label}: names a genuine strength", len(out["strength"].split()) >= 4, out["strength"])

print("\n" + "=" * 62)
if advisory:
    print(f"advisory ({len(advisory)}) — model wording, covered by code elsewhere:")
    for a in advisory:
        print(f"  · {a}")
if failures:
    print(f"\n{len(failures)} FAILED: {failures}")
    print("The explanation coach cannot tell good reasoning from hollow reasoning.")
    print("It must not be shown to a learner as advice while this fails.")
else:
    print("the coach discriminates explanation quality — worth showing as advice")
raise SystemExit(1 if failures else 0)
