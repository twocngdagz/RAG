"""The spaced-repetition scheduler, against a controlled clock.

A scheduler that schedules wrong is worse than none — it would drill mastered
items and drop weak ones. These pin the behaviour that matters:
  - correct pushes review out; wrong brings it back soon and drops a level
  - mastery is earned by climbing every box, and a lapse un-masters
  - selection prefers due (weakest first), then new, then studies ahead
  - a sitting never dead-ends until everything is mastered
  - it is deterministic (no clock reads, no randomness)

    python test_spaced_repetition.py
"""
from __future__ import annotations

import spaced_repetition as sr

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


T0 = 1_000_000.0  # a fixed 'now'

print("one answer moves the schedule the right way")
s = sr.ItemState("a")
sr.update(s, correct=True, now=T0)
check("new -> introduced", s.introduced_at == T0)
check("correct -> level 1", s.level == 1)
check("correct -> due pushed to +10 min", s.due_at == T0 + sr.INTERVALS[1], str(s.due_at))
check("not due at T0", not s.is_due(T0))

s2 = sr.ItemState("b", level=3, due_at=T0)
sr.update(s2, correct=False, now=T0)
check("wrong -> level drops", s2.level == 2)
check("wrong -> due back soon (+1 min)", s2.due_at == T0 + sr.INTERVALS[0])
check("wrong -> streak reset", s2.streak == 0)

print("\nmastery is earned by climbing every box, and a lapse un-masters")
m = sr.ItemState("m")
now = T0
for _ in range(sr.MASTERY_LEVEL):
    now += 100 * sr.DAY  # always answer when due
    sr.update(m, correct=True, now=now)
check("reaches mastery after MASTERY_LEVEL correct", m.is_mastered, f"level={m.level}")
check("mastered review is far out", m.due_at == now + sr.MASTERY_REVIEW)
sr.update(m, correct=False, now=now + 1)
check("a lapse un-masters", not m.is_mastered)
check("un-mastered comes back soon", m.due_at == (now + 1) + sr.INTERVALS[0])

print("\nselection: due (weakest first) > new > study-ahead")
ids = ["i1", "i2", "i3", "i4"]
# i1 due & weak (level 0), i2 due & stronger (level 2), i3 new, i4 far future
states = {
    "i1": sr.ItemState("i1", level=0, due_at=T0 - 10, introduced_at=T0 - 100),
    "i2": sr.ItemState("i2", level=2, due_at=T0 - 5, introduced_at=T0 - 100),
    "i4": sr.ItemState("i4", level=3, due_at=T0 + sr.DAY, introduced_at=T0 - 100),
}
pick, why = sr.pick_next(states, ids, T0)
check("picks the weakest due item", pick == "i1" and why == "due", f"{pick}/{why}")

# no due -> a new item
states_nodue = {"i1": sr.ItemState("i1", level=3, due_at=T0 + sr.DAY, introduced_at=T0 - 100)}
pick, why = sr.pick_next(states_nodue, ids, T0)
check("no due -> introduces a new item", why == "new" and pick in ("i2", "i3", "i4"), f"{pick}/{why}")

# nothing due, nothing new -> study ahead (soonest due, not mastered)
all_scheduled = {
    "i1": sr.ItemState("i1", level=3, due_at=T0 + 5 * sr.DAY, introduced_at=T0 - 100),
    "i2": sr.ItemState("i2", level=2, due_at=T0 + 2 * sr.DAY, introduced_at=T0 - 100),
}
pick, why = sr.pick_next(all_scheduled, ["i1", "i2"], T0)
check("nothing due/new -> study ahead, soonest due", pick == "i2" and why == "review", f"{pick}/{why}")

print("\nnever repeats the just-answered item when there's a choice")
pick, _ = sr.pick_next(states, ids, T0, avoid="i1")
check("avoids the previous item", pick != "i1", str(pick))
# ...but if it's the only option, show it rather than nothing
solo = {"only": sr.ItemState("only", level=0, due_at=T0 - 1, introduced_at=T0 - 10)}
pick, _ = sr.pick_next(solo, ["only"], T0, avoid="only")
check("shows the only item even if avoided", pick == "only")

print("\nall mastered -> session complete")
allm = {"x": sr.ItemState("x", mastered_at=T0, due_at=T0 + sr.MASTERY_REVIEW, introduced_at=T0)}
pick, why = sr.pick_next(allm, ["x"], T0)
check("returns nothing when all mastered", pick is None and why == "all_mastered")

print("\ndeterministic: same inputs -> same pick")
a = sr.pick_next(states, ids, T0)
b = sr.pick_next(states, ids, T0)
check("stable across calls", a == b)

print("\nprogress summary counts correctly")
summ = sr.summary(states, ids, T0)
check("summary totals", summ["total"] == 4 and summ["due"] == 2 and summ["new"] == 1, str(summ))

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "scheduler behaviour holds")
raise SystemExit(1 if fails else 0)
