"""Maths practice — the V2 first slice — end to end, against a throwaway DB.

Two properties, both non-negotiable:
  1. The marker is honest: it fails wrong answers and the "right value, wrong
     form" case (math_practice_items.self_test). A marker that cannot fail is
     not marking.
  2. Every bank answer is independently correct, and the API serves the bank with
     answers withheld, marks deterministically, and records history.

    python test_math_practice.py
"""
from __future__ import annotations

import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ["LEARNING_MATERIALS_DB_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"  # never the real DB

import math_practice_items as mp

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


print("marker honesty (fails wrong answers)")
check("self-test passes", mp.self_test() == 0)

print("\nevery generated answer is independently correct")
items = mp.build_items(60, seed=99)
import math_evaluators as M
wrong = 0
for it in items:
    stored = Fraction(it["answer_num"], it["answer_den"])
    independent = M.evaluate(it["prompt_inline"].strip("$"))
    if independent is None or independent != stored:
        wrong += 1
check("60 items, all answers verify against the arithmetic checker", wrong == 0, f"{wrong} wrong")

print("\nAPI: bank served (answers withheld), marked, recorded")
from fastapi.testclient import TestClient
import learning_materials_api as api

# point the API at this run's freshly-built bank
bank_path = Path(tempfile.mktemp(suffix=".json"))
bank_path.write_text(json.dumps(items))
os.environ["MATH_PRACTICE_ITEMS_FILE"] = str(bank_path)

c = TestClient(api.create_app())
served = c.get("/math-practice-items").json()
check("bank served", len(served) == len(items), str(len(served)))
check("answers withheld from the wire",
      all("answer_num" not in s and "answer_plain" not in s for s in served))

first = items[0]
ok = c.post("/books/math5a/chapters/1/math-practice-answer",
            json={"item_id": first["id"], "answer": first["answer_plain"]}).json()
check("correct answer -> correct", ok["correct"] is True, ok.get("message"))
check("capability recorded on the attempt", ok["traits"][0]["name"] == first["capability"])

bad = c.post("/books/math5a/chapters/1/math-practice-answer",
             json={"item_id": first["id"], "answer": "123456"}).json()
check("wrong answer -> not correct", bad["correct"] is False)
check("wrong answer reveals the real answer", first["answer_plain"] in bad["one_line_verdict"])

check("unknown item -> 404",
      c.post("/books/math5a/chapters/1/math-practice-answer",
             json={"item_id": "nope", "answer": "1"}).status_code == 404)

hist = c.get("/books/math5a/essay-attempts?task_type=math_practice").json()
check("both attempts in history", len(hist) == 2, str(len(hist)))

print("\nscheduler: next-item selection, progress, and persistence")
# fresh app on a fresh DB + tiny bank so the counts are exact
os.environ["LEARNING_MATERIALS_DB_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"
small = mp.build_items(5, seed=3)
bp2 = Path(tempfile.mktemp(suffix=".json"))
bp2.write_text(json.dumps(small))
os.environ["MATH_PRACTICE_ITEMS_FILE"] = str(bp2)
c2 = TestClient(api.create_app())

n = c2.get("/books/math5a/math-practice-next").json()
check("first item is new", n["reason"] == "new" and n["item"], n["reason"])
check("progress starts all-new", n["progress"] == {"total": 5, "mastered": 0, "due": 0, "new": 5, "in_progress": 0}, str(n["progress"]))

item0 = next(x for x in small if x["id"] == n["item"]["id"])
r = c2.post("/books/math5a/chapters/1/math-practice-answer",
            json={"item_id": item0["id"], "answer": item0["answer_plain"]}).json()
check("answer returns updated progress", r["progress"]["new"] == 4 and r["progress"]["in_progress"] == 1, str(r["progress"]))

nxt = c2.get(f"/books/math5a/math-practice-next?after={item0['id']}").json()
check("scheduler does not repeat the just-answered item", nxt["item"]["id"] != item0["id"])

# state survives a fresh app instance on the same DB
c3 = TestClient(api.create_app())
persisted = c3.get("/books/math5a/math-practice-next").json()
check("state persists across restart", persisted["progress"]["new"] == 4, str(persisted["progress"]))

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "maths practice slice holds")
raise SystemExit(1 if fails else 0)
