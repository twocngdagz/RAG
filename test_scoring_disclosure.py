"""Every score says who decided it — the model, or code.

A rubric number produced by a model and a rubric number measured by code look
identical on screen, and the confident layout does the arguing for both. Three of
these tasks are graded entirely by a model and used to say nothing about it, so a
learner had no way to know which of their marks was a machine's opinion.

What this pins:
  - every feedback payload carries `scored_by`, and it is right for the task
  - inside a model-scored rubric, the traits code actually computes (Form) are
    marked `code`, so the measured parts stay distinguishable from the judged ones
  - attempts saved before `scored_by` existed get it filled in on read, derived
    from the task type — history discloses too, not just new work
  - advisory traits stay flagged as scoring nothing

No model is called: the graders are stubbed and the reconcile functions are
exercised directly, so this runs in the normal regression.

    python test_scoring_disclosure.py
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ["LEARNING_MATERIALS_DB_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"  # never the real DB

import describe_image_feedback as dif
import essay_feedback as ef
import math_reasoning_items as mri
import swt_feedback as swt

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


def by_name(traits):
    return {t["name"]: t for t in traits}


print("the graders label their own output (no network)")

essay = ef._reconcile(
    {"traits": [{"name": n, "score": 1, "evidence": "", "fix": ""} for n in ef.TRAIT_MAX]},
    "A sentence. " * 120,
)
check("essay payload is model-scored", essay["scored_by"] == "model", str(essay.get("scored_by")))
et = by_name(essay["traits"])
check("essay Form is code-scored (it is computed in form_score)",
      et["form"]["scored_by"] == "code", str(et["form"]))
check("essay Content is model-scored", et["content"]["scored_by"] == "model")
check("every essay trait declares a source",
      all(t.get("scored_by") in ("code", "model") for t in essay["traits"]))

summary = swt._reconcile(
    {"traits": [{"name": n, "score": 1, "evidence": "", "fix": ""} for n in swt.TRAIT_MAX]},
    "One sentence that summarises the passage in a reasonable number of words indeed.",
)
check("SWT payload is model-scored", summary["scored_by"] == "model")
st = by_name(summary["traits"])
check("SWT Form is code-scored", st["form"]["scored_by"] == "code", str(st["form"]))
check("SWT Content is model-scored", st["content"]["scored_by"] == "model")

di_item = {"facts": [{"key": "peak", "importance": "essential", "text": "peaks in 2020"}],
           "points": [{"label": "2020", "value": 10}], "unit": "%", "title": "t",
           "x_label": "x", "y_label": "y", "chart_type": "line", "subject": "s"}
di = dif._reconcile({"content_score": 3, "facts": [], "top_priorities": ["x"]}, di_item, "It went up to 10%.")
check("describe-image payload is model-scored", di["scored_by"] == "model")
check("describe-image Content trait is model-scored", di["traits"][0]["scored_by"] == "model")

print("\nthe API discloses on every task, and back-fills old attempts")
from fastapi.testclient import TestClient
import book_learning_materials_store as store
import learning_materials_api as api

reasoning_bank = mri.build_items(4, seed=3)
bank_path = Path(tempfile.mktemp(suffix=".json"))
bank_path.write_text(json.dumps(reasoning_bank))
os.environ["MATH_REASONING_ITEMS_FILE"] = str(bank_path)

# stubbed graders — nothing reaches the network
api.essay_feedback.score_essay = lambda *a, **k: ef._reconcile(
    {"traits": [{"name": n, "score": 1, "evidence": "", "fix": ""} for n in ef.TRAIT_MAX],
     "top_priorities": [], "one_line_verdict": "ok", "errors": []},
    a[1] if len(a) > 1 else "words " * 200,
)
api.math_reasoning_feedback.score_reasoning = lambda *a, **k: {
    "traits": [{"name": n, "score": 1, "max": m, "evidence": "", "fix": "", "advisory": True}
               for n, m in mri.ADVISORY_TRAIT_MAX.items()],
    "advisory_total": 3, "advisory_max": mri.ADVISORY_MAX_TOTAL,
    "strength": "s", "next_step": "n", "coach_note": "c",
    "advisory": True, "written_by": "model",
}

c = TestClient(api.create_app())

live = c.post("/books/math5a/chapters/1/essay-feedback",
              json={"prompt": "p", "essay": "word " * 250}).json()
check("live essay feedback discloses AI scoring", live["scored_by"] == "model", str(live.get("scored_by")))

item = reasoning_bank[0]
reasoning = c.post("/books/math5a/chapters/1/math-reasoning-answer",
                   json={"item_id": item["id"], "response": item["model_answer"]}).json()
check("reasoning payload is code-scored (the model scores nothing)",
      reasoning["scored_by"] == "code", str(reasoning.get("scored_by")))
rt = reasoning["traits"]
check("its code traits are labelled code",
      [t["scored_by"] for t in rt[:2]] == ["code", "code"], str([t.get("scored_by") for t in rt[:2]]))
check("its advisory traits are the model's opinion but score nothing",
      all(t["advisory"] and t["scored_by"] == "model" for t in rt[2:]),
      str([(t.get("advisory"), t.get("scored_by")) for t in rt[2:]]))

print("\nattempts saved before scored_by existed still disclose on read")
with store.Session(api.store.create_db(os.environ["LEARNING_MATERIALS_DB_URL"])) as s:
    for task in ("write_essay", "summarize_written_text", "describe_image", "reading_multiple_choice"):
        store.save_essay_attempt(
            s, book_slug="math5a", chapter_number=1,
            prompt_text=f"old {task}", essay_text="old response",
            # exactly what the old code wrote: no scored_by anywhere
            feedback={"traits": [{"name": "content", "score": 1, "max": 6, "evidence": "", "fix": ""},
                                 {"name": "form", "score": 2, "max": 2, "evidence": "", "fix": ""}],
                      "raw_total": 1, "max_raw_total": 6, "word_count": 5,
                      "top_priorities": [], "one_line_verdict": "old"},
            task_type=task,
        )
    s.commit()

want = {"write_essay": "model", "summarize_written_text": "model",
        "describe_image": "model", "reading_multiple_choice": "code"}
for task, expected in want.items():
    rows = c.get(f"/books/math5a/essay-attempts?task_type={task}").json()
    old = next(r for r in rows if r["prompt_excerpt"].startswith("old "))
    detail = c.get(f"/books/math5a/essay-attempts/{old['id']}").json()
    check(f"old {task} attempt back-filled to {expected}",
          detail["feedback"]["scored_by"] == expected, str(detail["feedback"].get("scored_by")))
    check(f"old {task} traits back-filled too",
          detail["feedback"]["traits"][0]["scored_by"] == expected)
    check(f"{task} history rows carry it for the list view", old["scored_by"] == expected)
    # Form was measured in code even in the old payloads, so back-filling it as an
    # AI judgement would be a fresh untruth told to fix an old silence.
    if task in ("write_essay", "summarize_written_text"):
        form = next(t for t in detail["feedback"]["traits"] if t["name"] == "form")
        check(f"old {task} Form still labelled code, not AI", form["scored_by"] == "code", str(form))

print("\nthe disclosure cannot be silently dropped")
check("a payload with no traits still gets a payload-level label",
      api._with_scoring_disclosure({}, "write_essay")["scored_by"] == "model")
check("an unknown task type defaults to code, not to a silent absence",
      api._with_scoring_disclosure({}, "something_new")["scored_by"] == "code")
check("an explicit label is never overwritten",
      api._with_scoring_disclosure({"scored_by": "code"}, "write_essay")["scored_by"] == "code")

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "every score discloses who decided it")
raise SystemExit(1 if fails else 0)
