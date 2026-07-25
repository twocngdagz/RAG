"""Maths reasoning — the open-response slice — end to end, against a throwaway DB.

The property that matters here is the *boundary*, not the model. An advisory
grader that quietly starts deciding marks, or moving the spaced-repetition
schedule, would turn a study tool into a machine that guesses at children. So:

  1. The deterministic check is honest (math_reasoning_items.self_test): it fails
     a copied-back question, a bare answer with no working, and working with the
     wrong answer.
  2. The mark and the schedule come from code alone — proved by driving the API
     with a *stubbed* grader that returns maximum praise for a wrong response, and
     requiring the mark and the schedule to be unmoved by it.
  3. When the grader is unavailable the learner is still marked.

No model is called, so this runs in the normal regression: free, offline, fast.
The live grader has its own sensitivity test (test_reasoning_grader_sensitivity.py).

    python test_math_reasoning.py
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["LEARNING_MATERIALS_DB_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"  # never the real DB

import math_reasoning_items as mri
import math_reasoning_feedback as mrf

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


print("the deterministic check is honest")
check("self-test passes over a fresh bank", mri.self_test(40) == 0)

print("\nthe advisory reconcile is structurally safe whatever the model returns")
det_ok = {"correct": True, "answer_shown": True, "working_shown": True}
junk = mrf._reconcile({"traits": [{"name": "explains_why", "score": 99},
                                  {"name": "made_up_trait", "score": 5},
                                  {"name": "explains_why", "score": 0}]}, det_ok)
names = [t["name"] for t in junk["traits"]]
check("exactly the three known traits, in order", names == mrf.TRAIT_ORDER, str(names))
check("scores clamped to their max", junk["traits"][0]["score"] == 3, str(junk["traits"][0]))
check("a missing trait defaults to 0", junk["traits"][2]["score"] == 0)
check("every advisory trait is flagged advisory", all(t["advisory"] for t in junk["traits"]))
check("advisory total is recomputed, not trusted", junk["advisory_total"] == 3, str(junk["advisory_total"]))
check("empty model output still yields usable text",
      mrf._reconcile({}, det_ok)["next_step"].strip() != "")

print("\nAPI: code marks, the model only advises")
from fastapi.testclient import TestClient
import learning_materials_api as api

bank = mri.build_items(6, seed=7)
bank_path = Path(tempfile.mktemp(suffix=".json"))
bank_path.write_text(json.dumps(bank))
os.environ["MATH_REASONING_ITEMS_FILE"] = str(bank_path)

# A grader that is maximally, wrongly enthusiastic about everything. If any of it
# leaks into the mark or the schedule, the boundary is broken.
FLATTERER = {
    "traits": [{"name": n, "score": m, "max": m, "evidence": "great", "fix": "", "advisory": True}
               for n, m in mrf.ADVISORY_TRAIT_MAX.items()],
    "advisory_total": mrf.ADVISORY_MAX_TOTAL, "advisory_max": mrf.ADVISORY_MAX_TOTAL,
    "strength": "Perfect.", "next_step": "Nothing to change.", "coach_note": "Flawless.",
    "advisory": True, "graded_by": "model",
}
api.math_reasoning_feedback.score_reasoning = lambda *a, **k: dict(FLATTERER)

c = TestClient(api.create_app())

nxt = c.get("/books/math5a/math-reasoning-next").json()
check("scheduler serves a reasoning item", bool(nxt["item"]) and nxt["reason"] == "new", str(nxt["reason"]))
served = nxt["item"]
for leaked in ("answer_plain", "answer_num", "working_tokens", "model_answer", "rubric"):
    check(f"{leaked} withheld before answering", leaked not in served)

item = next(i for i in bank if i["id"] == served["id"])

# --- a wrong response, with the grader singing its praises ------------------- #
bad = c.post("/books/math5a/chapters/3/math-reasoning-answer",
             json={"item_id": item["id"], "response": "i dont know it is easy"}).json()
check("wrong response is not marked correct", bad["correct"] is False)
check("mark ignores the flattering grader", bad["raw_total"] == 0, str(bad["raw_total"]))
check("verdict comes from code, not the model",
      bad["one_line_verdict"] == mri.check_working(item, "i dont know it is easy")["message"],
      bad["one_line_verdict"])
check("advisory praise is present but flagged",
      bad["advisory"]["advisory"] is True and bad["advisory"]["advisory_total"] == mrf.ADVISORY_MAX_TOTAL)
check("every trait states whether it is advisory, code first",
      [t.get("advisory") for t in bad["traits"]] == [False, False, True, True, True],
      str([t.get("advisory") for t in bad["traits"]]))
check("advisory scores stay out of raw_total", bad["raw_total"] < bad["max_raw_total"])
check("schedule moved on the code verdict (wrong -> comes back soon)",
      bad["progress"]["in_progress"] == 1 and bad["progress"]["mastered"] == 0, str(bad["progress"]))

# --- the same item answered properly ----------------------------------------- #
good = c.post("/books/math5a/chapters/3/math-reasoning-answer",
              json={"item_id": item["id"], "response": item["model_answer"]}).json()
check("worked answer is marked correct", good["correct"] is True, good["one_line_verdict"])
check("full deterministic mark", good["raw_total"] == 2, str(good["raw_total"]))
check("worked example revealed only after answering", bool(good["model_answer"]))
check("rubric revealed only after answering", len(good["rubric"]) == 3)

# --- right answer, no working: the case this task exists to catch ------------- #
bare = c.post("/books/math5a/chapters/3/math-reasoning-answer",
              json={"item_id": item["id"], "response": f"the answer is {item['answer_plain']}"}).json()
check("right answer with no working is not fully correct", bare["correct"] is False, str(bare["raw_total"]))
check("...but the answer itself is credited", bare["answer_shown"] is True)

print("\nthe learner is still marked when the coach is unavailable")


def _down(*a, **k):
    raise RuntimeError("OLLAMA_API_KEY is not set.")


api.math_reasoning_feedback.score_reasoning = _down
offline = c.post("/books/math5a/chapters/3/math-reasoning-answer",
                 json={"item_id": item["id"], "response": item["model_answer"]}).json()
check("still marked with no grader", offline["correct"] is True and offline["raw_total"] == 2)
check("advisory absent, and said so plainly",
      offline["advisory"] is None and "only the maths was checked" in (offline["advisory_error"] or ""),
      str(offline["advisory_error"]))
check("schedule still advanced without the grader", offline["progress"]["total"] == len(bank))

print("\nhistory records reasoning attempts under their own task type")
hist = c.get("/books/math5a/essay-attempts?task_type=math_reasoning").json()
check("all four attempts recorded", len(hist) == 4, str(len(hist)))
detail = c.get(f"/books/math5a/essay-attempts/{hist[0]['id']}").json()
check("saved feedback round-trips", detail["feedback"]["kind"] == "reasoning")

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "reasoning slice holds — code marks, the model advises")
raise SystemExit(1 if fails else 0)
