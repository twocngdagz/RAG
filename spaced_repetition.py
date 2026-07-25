"""Spaced-repetition scheduler — the Learning Engine core of the V2 study tool.

Per the V2 architecture this layer is deterministic and app-owned: it decides
which item to study next and how each answer changes an item's schedule, with no
AI involved. `now` is always passed in, never read from the clock here, so the
whole thing is testable against a controlled time.

Model (Leitner-style boxes with growing intervals):
- Each item has a `level`. A correct answer moves it up a level and pushes its
  next review further out; a wrong answer drops it a level and brings it back
  soon (weak-area reinforcement). Reaching the top level is mastery.
- Selection interleaves: due items first (weakest, most overdue), then a new
  item, then — so a sitting never dead-ends — the soonest-due unmastered item.

This is intentionally simple and defensible over a clever ease-factor scheme; the
point of the first slice is a correct, honest, deterministic loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

MINUTE = 60
DAY = 24 * 60 * 60

# Interval after answering an item correctly at each level (index = new level).
# Level 0 is the "just got it wrong, see it again this sitting" box.
INTERVALS = [1 * MINUTE, 10 * MINUTE, 1 * DAY, 3 * DAY, 7 * DAY, 16 * DAY]
MASTERY_LEVEL = len(INTERVALS)          # reaching this level = mastered
MASTERY_REVIEW = 60 * DAY               # mastered items still resurface, rarely


@dataclass
class ItemState:
    item_id: str
    level: int = 0
    due_at: float | None = None          # epoch seconds; None = never scheduled (new)
    introduced_at: float | None = None
    last_studied_at: float | None = None
    times_seen: int = 0
    times_correct: int = 0
    streak: int = 0
    mastered_at: float | None = None

    @property
    def is_new(self) -> bool:
        return self.introduced_at is None

    @property
    def is_mastered(self) -> bool:
        return self.mastered_at is not None

    def is_due(self, now: float) -> bool:
        return self.due_at is not None and self.due_at <= now


def update(state: ItemState, correct: bool, now: float) -> ItemState:
    """Apply one answer to an item's schedule. Mutates and returns the state."""
    state.times_seen += 1
    state.last_studied_at = now
    if state.introduced_at is None:
        state.introduced_at = now

    if correct:
        state.times_correct += 1
        state.streak += 1
        state.level = min(state.level + 1, MASTERY_LEVEL)
        if state.level >= MASTERY_LEVEL:
            state.mastered_at = state.mastered_at or now
            state.due_at = now + MASTERY_REVIEW
        else:
            state.due_at = now + INTERVALS[state.level]
    else:
        state.streak = 0
        state.level = max(0, state.level - 1)
        state.mastered_at = None          # a lapse must be re-earned
        state.due_at = now + INTERVALS[0]  # bring it back soon
    return state


def pick_next(
    states: dict[str, ItemState],
    all_item_ids: Iterable[str],
    now: float,
    *,
    avoid: str | None = None,
) -> tuple[str | None, str]:
    """The next item to study, and why. Deterministic.

    Priority:
      1. due now  — weakest first (lowest level), then most overdue
      2. new      — never introduced, in bank order
      3. ahead    — soonest-due unmastered item, so a sitting never dead-ends
    `avoid` (the item just answered) is skipped unless it is the only option.
    Returns (item_id or None, reason).
    """
    ids = list(all_item_ids)

    def not_avoided(cands: list[str]) -> list[str]:
        trimmed = [i for i in cands if i != avoid]
        return trimmed or cands  # never let `avoid` empty the pool entirely

    # 1. due
    due = [i for i in ids if i in states and states[i].is_due(now) and not states[i].is_mastered]
    if due:
        due = not_avoided(due)
        due.sort(key=lambda i: (states[i].level, states[i].due_at or 0, i))
        return due[0], "due"

    # 2. new
    new = [i for i in ids if i not in states or states[i].is_new]
    if new:
        new = not_avoided(new)
        # bank order is meaningful (interleaves skills already), so keep it
        return new[0], "new"

    # 3. study ahead — soonest-due unmastered, so practice continues
    ahead = [i for i in ids if i in states and not states[i].is_mastered]
    if ahead:
        ahead = not_avoided(ahead)
        ahead.sort(key=lambda i: (states[i].due_at or 0, states[i].level, i))
        return ahead[0], "review"

    return None, "all_mastered"


def summary(states: dict[str, ItemState], all_item_ids: Iterable[str], now: float) -> dict:
    """Progress numbers for the learner: total / mastered / due / new."""
    ids = list(all_item_ids)
    total = len(ids)
    mastered = sum(1 for i in ids if i in states and states[i].is_mastered)
    due = sum(1 for i in ids if i in states and states[i].is_due(now) and not states[i].is_mastered)
    new = sum(1 for i in ids if i not in states or states[i].is_new)
    return {"total": total, "mastered": mastered, "due": due, "new": new,
            "in_progress": total - mastered - new}
