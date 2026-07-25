"""Maths practice items — the first slice of the V2 study tool.

The V2 principle this makes concrete: for maths, *correct is computable*. Every
item's answer is worked out by code (exact rational arithmetic), never by a model,
and the learner's typed answer is checked exactly. No model runs at practice time,
so it is instant, free, and cannot be wrong.

Items are parametric and generated from a seed, so the bank is reproducible and
effectively infinite — the shape a spaced-repetition scheduler will want later.
Each item carries a capability tag (Recall / Application), matching the V2
capability model; Reasoning / Communication need open responses graded by an
(advisory) model and are a later slice.

Usage:
  python math_practice_items.py --count 40          # write a bank
  python math_practice_items.py --self-test         # prove the checker is honest
"""

from __future__ import annotations

import argparse
import json
import random
import re
from fractions import Fraction
from math import gcd
from pathlib import Path
from typing import Any, Callable

OUTPUT_FILE = "output/math_practice_items.json"

# Capability tags (see the V2 architecture). Only computable-answer capabilities
# belong in this deterministic slice.
RECALL = "recall"
APPLICATION = "application"


# --------------------------------------------------------------------------- #
# Rendering helpers
# --------------------------------------------------------------------------- #

def _frac_tex(f: Fraction) -> str:
    """A fraction as LaTeX, as a Year-5 pupil would write the answer: a whole
    number stays whole, an improper fraction shows as a mixed number."""
    if f.denominator == 1:
        return str(f.numerator)
    whole, rem = divmod(abs(f.numerator), f.denominator)
    sign = "-" if f < 0 else ""
    if whole and rem:
        return f"{sign}{whole}\\frac{{{rem}}}{{{f.denominator}}}"
    return f"{sign}\\frac{{{rem}}}{{{f.denominator}}}"


def _plain(f: Fraction) -> str:
    """A plain-text canonical answer, e.g. '3/4', '2 1/2', '8'."""
    if f.denominator == 1:
        return str(f.numerator)
    whole, rem = divmod(abs(f.numerator), f.denominator)
    sign = "-" if f < 0 else ""
    if whole and rem:
        return f"{sign}{whole} {rem}/{f.denominator}"
    return f"{sign}{rem}/{f.denominator}"


# --------------------------------------------------------------------------- #
# Skill generators — each returns (prompt_latex, answer, capability, skill)
# The ANSWER is computed here, exactly. That is the whole point.
# --------------------------------------------------------------------------- #

def _times_table(rng: random.Random):
    a, b = rng.randint(2, 12), rng.randint(2, 12)
    return f"{a} \\times {b}", Fraction(a * b), RECALL, "times_table"


def _add_unlike_fractions(rng: random.Random):
    d1, d2 = rng.choice([(2, 3), (3, 4), (2, 5), (3, 5), (4, 6), (2, 6), (3, 10), (4, 5)])
    n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
    a, b = Fraction(n1, d1), Fraction(n2, d2)
    return f"\\frac{{{n1}}}{{{d1}}} + \\frac{{{n2}}}{{{d2}}}", a + b, APPLICATION, "add_fractions"


def _subtract_unlike_fractions(rng: random.Random):
    d1, d2 = rng.choice([(2, 3), (3, 4), (2, 5), (3, 5), (4, 5), (3, 10)])
    n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
    a, b = Fraction(n1, d1), Fraction(n2, d2)
    if a < b:
        a, b = b, a
        d1, d2, n1, n2 = d2, d1, n2, n1
    return f"\\frac{{{n1}}}{{{d1}}} - \\frac{{{n2}}}{{{d2}}}", a - b, APPLICATION, "subtract_fractions"


def _fraction_times_whole(rng: random.Random):
    d = rng.choice([2, 3, 4, 5, 6])
    n = rng.randint(1, d - 1)
    w = rng.randint(2, 12)
    return f"\\frac{{{n}}}{{{d}}} \\times {w}", Fraction(n, d) * w, APPLICATION, "fraction_times_whole"


def _fraction_times_fraction(rng: random.Random):
    n1, d1 = rng.randint(1, 5), rng.randint(2, 6)
    n2, d2 = rng.randint(1, 5), rng.randint(2, 6)
    return (f"\\frac{{{n1}}}{{{d1}}} \\times \\frac{{{n2}}}{{{d2}}}",
            Fraction(n1, d1) * Fraction(n2, d2), APPLICATION, "fraction_times_fraction")


def _fraction_divided_by_whole(rng: random.Random):
    d = rng.choice([2, 3, 4, 5])
    n = rng.randint(1, d - 1)
    w = rng.randint(2, 6)
    return (f"\\frac{{{n}}}{{{d}}} \\div {w}",
            Fraction(n, d) / w, APPLICATION, "fraction_div_whole")


SKILLS: list[Callable[[random.Random], tuple[str, Fraction, str, str]]] = [
    _times_table,
    _add_unlike_fractions,
    _subtract_unlike_fractions,
    _fraction_times_whole,
    _fraction_times_fraction,
    _fraction_divided_by_whole,
]

_SKILL_TITLE = {
    "times_table": "Times tables",
    "add_fractions": "Add fractions",
    "subtract_fractions": "Subtract fractions",
    "fraction_times_whole": "Multiply a fraction by a whole number",
    "fraction_times_fraction": "Multiply two fractions",
    "fraction_div_whole": "Divide a fraction by a whole number",
}


def build_items(count: int, *, seed: int = 12345) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    guard = 0
    while len(items) < count and guard < count * 20:
        guard += 1
        gen = rng.choice(SKILLS)
        prompt, answer, capability, skill = gen(rng)
        if prompt in seen:
            continue
        seen.add(prompt)
        items.append({
            "id": f"mp-{len(items) + 1:03d}-{skill}",
            "skill": skill,
            "skill_title": _SKILL_TITLE[skill],
            "capability": capability,
            "prompt": f"$${prompt}$$",
            "prompt_inline": f"${prompt}$",
            # The computed answer — withheld from the learner until they submit.
            "answer_num": answer.numerator,
            "answer_den": answer.denominator,
            "answer_tex": f"${_frac_tex(answer)}$",
            "answer_plain": _plain(answer),
            # Simplest form matters pedagogically: is the exact answer already reduced?
            "answer_is_reduced": True,  # Fraction is always reduced; kept for the UI
        })
    return items


# --------------------------------------------------------------------------- #
# Answer parsing + checking — the deterministic marker
# --------------------------------------------------------------------------- #

_MIXED = re.compile(r"^\s*(-?\d+)\s+(\d+)\s*/\s*(\d+)\s*$")   # "2 3/4"
_FRAC = re.compile(r"^\s*(-?\d+)\s*/\s*(\d+)\s*$")            # "3/4"
_INT = re.compile(r"^\s*(-?\d+)\s*$")                         # "8"
_DEC = re.compile(r"^\s*(-?\d+)\.(\d+)\s*$")                  # "0.75"


def parse_answer(text: str) -> Fraction | None:
    """A learner's typed answer as an exact Fraction, or None if unparseable.
    Accepts integers, 'a/b', mixed 'w a/b', and terminating decimals."""
    if not text or not text.strip():
        return None
    s = text.strip().replace("−", "-")
    m = _MIXED.match(s)
    if m:
        w, n, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if d == 0:
            return None
        mag = abs(w) + Fraction(n, d)
        return -mag if w < 0 else mag
    m = _FRAC.match(s)
    if m:
        d = int(m.group(2))
        return Fraction(int(m.group(1)), d) if d else None
    m = _INT.match(s)
    if m:
        return Fraction(int(m.group(1)))
    m = _DEC.match(s)
    if m:
        return Fraction(s)
    return None


def is_reduced(f: Fraction, learner_num: int, learner_den: int) -> bool:
    """Did the learner give it in simplest form? Compares the fraction they wrote
    against its reduced form. Whole numbers are trivially reduced."""
    if learner_den in (0, 1):
        return True
    return gcd(abs(learner_num), abs(learner_den)) == 1


def check_answer(item: dict[str, Any], typed: str) -> dict[str, Any]:
    """Mark a typed answer against an item's computed answer.

    correct      : mathematically equal AND (for fractions) in simplest form
    equal        : mathematically equal, regardless of form
    not_simplest : equal but not reduced (e.g. 2/4 for 1/2) — a teaching moment
    """
    answer = Fraction(item["answer_num"], item["answer_den"])
    parsed = parse_answer(typed)
    if parsed is None:
        return {"correct": False, "equal": False, "not_simplest": False,
                "parsed": None, "answer_tex": item["answer_tex"],
                "answer_plain": item["answer_plain"],
                "message": "That is not a number I can read. Try like 3/4, 2 1/2, or 8."}

    equal = parsed == answer
    # was the learner's own written form reduced? re-parse the raw fraction parts.
    fm = _FRAC.match(typed.strip()) or _MIXED.match(typed.strip())
    if fm and equal:
        ln = int(fm.group(len(fm.groups()) - 1))
        ld = int(fm.group(len(fm.groups())))
        simplest = is_reduced(answer, ln, ld)
    else:
        simplest = True
    correct = equal and simplest
    if correct:
        msg = "Correct!"
    elif equal and not simplest:
        msg = f"Right value, but make it simpler: {item['answer_plain']}."
    else:
        msg = f"Not quite. The answer is {item['answer_plain']}."
    return {"correct": correct, "equal": equal, "not_simplest": equal and not simplest,
            "parsed": _plain(parsed), "answer_tex": item["answer_tex"],
            "answer_plain": item["answer_plain"], "message": msg}


# --------------------------------------------------------------------------- #
# Self-test — the honesty gate: prove the marker catches known-wrong answers
# --------------------------------------------------------------------------- #

def self_test() -> int:
    """Feed the checker answers whose right/wrong-ness is already known. A marker
    that cannot fail a wrong answer is not marking anything."""
    half = {"answer_num": 1, "answer_den": 2, "answer_tex": "$\\frac{1}{2}$", "answer_plain": "1/2"}
    eight = {"answer_num": 8, "answer_den": 1, "answer_tex": "$8$", "answer_plain": "8"}
    two_and_half = {"answer_num": 5, "answer_den": 2, "answer_tex": "$2\\frac{1}{2}$", "answer_plain": "2 1/2"}

    cases = [
        (half, "1/2", "correct", True),
        (half, "2/4", "equal-not-simplest", False),   # right value, wrong form
        (half, "0.5", "decimal equal", True),
        (half, "3/4", "wrong", False),
        (half, "", "empty", False),
        (half, "banana", "garbage", False),
        (eight, "8", "whole correct", True),
        (eight, "7", "whole wrong", False),
        (two_and_half, "2 1/2", "mixed correct", True),
        (two_and_half, "5/2", "improper equal", True),   # equal, and 5/2 is reduced
        (two_and_half, "2 2/4", "mixed not simplest", False),
    ]
    bad = 0
    for item, typed, label, want_correct in cases:
        got = check_answer(item, typed)["correct"]
        ok = got == want_correct
        bad += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label:22} typed={typed!r:10} -> correct={got} (want {want_correct})")
    print(f"\n{'marker is honest — it fails wrong answers' if not bad else str(bad)+' FAILED'}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--seed", type=int, default=12345)
    ap.add_argument("--output", default=OUTPUT_FILE)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    items = build_items(args.count, seed=args.seed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    by_skill: dict[str, int] = {}
    for it in items:
        by_skill[it["skill_title"]] = by_skill.get(it["skill_title"], 0) + 1
    print(f"wrote {len(items)} practice items -> {out}")
    for k, v in sorted(by_skill.items()):
        print(f"  {v:2}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
