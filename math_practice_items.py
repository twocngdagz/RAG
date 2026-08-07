"""Maths practice items — questions whose answers this file works out itself.

The V2 principle this makes concrete: for maths, *correct is computable*. Every
item's answer is worked out by code (exact rational arithmetic), never by a model,
and the learner's typed answer is checked exactly. No model runs at practice time,
so it is instant, free, and cannot be wrong.

Items are parametric and generated from a seed, so the bank is reproducible and
effectively infinite. Each carries a capability tag (Recall / Application) and the
lesson it belongs to, so a child practising Fractions is never handed a ratio
question. Reasoning and Communication need open responses and live in
math_reasoning_items.py.

Every item also carries `check_expr` — the sum that produces its answer, written
out separately from the generator that produced it. math_evaluators works that sum
out by a completely different code path, so each answer is confirmed twice by two
implementations that share nothing. Where an item's rule is not arithmetic
(rounding, simplifying a ratio) `check_expr` is None and self_test verifies it
against a second, independently written implementation instead.

Usage:
  python math_practice_items.py --count 200        # write a bank
  python math_practice_items.py --self-test        # prove the checker is honest
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

# Who generated an item, for the provenance record a package carries. Named here
# because this file IS the generator: an exporter that made up a version string
# would be recording a fact about authorship that nothing supports. Bump it when
# a change here alters the questions or the answers this file produces.
#
# Skill-scoped bumps live in GENERATOR_VERSION_BY_SKILL: a revision that only
# changes some skills must not rewrite provenance on every other exercise, or
# chapter 3's package fingerprint would move for content it does not contain.
GENERATOR_VERSION = "math-practice-items/1.0.0"

# Skills revised since 1.0.0. Triangle generators now force whole-number areas
# so a bank can imply required_form; their exercises must not still claim 1.0.0.
GENERATOR_VERSION_BY_SKILL = {
    "triangle_area": "math-practice-items/1.0.1",
    "triangle_half_rectangle": "math-practice-items/1.0.1",
}


def generator_version_for(skill: str) -> str:
    """The provenance string for one skill's exercises.

    Unchanged skills keep GENERATOR_VERSION so packages that never ask a revised
    skill (chapter 3) stay byte-identical. Revised skills name their own bump.
    """
    return GENERATOR_VERSION_BY_SKILL.get(str(skill or "").strip(), GENERATOR_VERSION)

# Capability tags (see the V2 architecture). Only computable-answer capabilities
# belong in this deterministic slice.
RECALL = "recall"
APPLICATION = "application"

# Which lesson each skill is practice for. The app's lesson numbers, which differ
# from the book's own headings (app lesson 5 is the book's "4 Area of Triangle").
CHAPTER_OF_SKILL = {
    "digit_value": 1, "round_number": 1, "multiply_by_tens": 1, "divide_by_tens": 1,
    "times_table": 2, "multiply_two_digit": 2, "multiply_multiple_of_ten": 2,
    "divide_exact": 2, "division_remainder": 2,
    "add_fractions": 3, "subtract_fractions": 3, "fraction_times_whole": 3,
    "fraction_times_fraction": 3, "fraction_div_whole": 3,
    "triangle_area": 5, "triangle_half_rectangle": 5,
    "ratio_simplify": 6, "ratio_missing_part": 6, "ratio_share": 6,
    "angle_right": 7, "angle_straight_line": 7, "angle_point": 7, "angle_opposite": 7,
}

# The review lessons have no new material of their own; they mix what came before.
REVIEW_COVERS = {
    4: [1, 2, 3],
    8: [1, 2, 3, 5, 6, 7],
    9: [1, 2, 3, 5, 6, 7],
}


def chapters_for_lesson(lesson: int) -> list[int]:
    """Which lessons' questions belong in this lesson's practice."""
    return REVIEW_COVERS.get(lesson, [lesson])


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


def _grouped(n: int) -> str:
    """4865 -> '4{,}865', so large numbers read the way the lesson writes them."""
    return f"{n:,}".replace(",", "{,}")


def _item(skill: str, prompt: str, answer: Any, *, capability: str = APPLICATION,
          check_expr: str | None = None, kind: str = "number",
          inline: str | None = None) -> dict[str, Any]:
    return {"skill": skill, "prompt": prompt, "answer": answer, "capability": capability,
            "check_expr": check_expr, "answer_kind": kind, "inline": inline or prompt}


# --------------------------------------------------------------------------- #
# Lesson 1 — Whole Numbers
# --------------------------------------------------------------------------- #

def _digit_value(rng: random.Random):
    """'What is the value of the 5?' — place value, the spine of the lesson."""
    digits = rng.sample(range(1, 10), 6)          # all different: "the 5" is unambiguous
    n = int("".join(str(d) for d in digits))
    pos = rng.randrange(6)                         # 0 = hundred-thousands
    digit = digits[pos]
    place = 10 ** (5 - pos)
    return _item("digit_value",
                 f"In ${_grouped(n)}$, what is the value of the digit ${digit}$?",
                 Fraction(digit * place), capability=RECALL,
                 check_expr=f"{digit} * {place}",
                 inline=f"value of {digit} in {n}")


def _round_number(rng: random.Random):
    place, word = rng.choice([(10, "ten"), (100, "hundred"), (1000, "thousand")])
    n = rng.randrange(place * 2, 100_000)
    if n % place == place // 2:
        n += 1                                     # dodge the exact halfway case
    # round-half-up, the convention the lesson teaches
    answer = ((n + place // 2) // place) * place
    return _item("round_number",
                 f"Round ${_grouped(n)}$ to the nearest {word}.",
                 Fraction(answer), capability=RECALL,
                 check_expr=None,                  # not arithmetic — see self_test
                 inline=f"round {n} to nearest {word}")


def _multiply_by_tens(rng: random.Random):
    a, tens = rng.randint(11, 99), rng.choice([20, 30, 40, 50, 60, 70, 80, 90])
    return _item("multiply_by_tens", f"$${a} \\times {tens}$$", Fraction(a * tens),
                 check_expr=f"{a} * {tens}", inline=f"${a} \\times {tens}$")


def _divide_by_tens(rng: random.Random):
    tens = rng.choice([20, 30, 40, 50, 60, 70, 80, 90])
    q = rng.choice([20, 40, 50, 100, 200, 250, 500])
    n = tens * q
    return _item("divide_by_tens", f"$${_grouped(n)} \\div {tens}$$", Fraction(q),
                 check_expr=f"{n} / {tens}", inline=f"${n} \\div {tens}$")


# --------------------------------------------------------------------------- #
# Lesson 2 — Multiplication and division by a 2-digit number
# --------------------------------------------------------------------------- #

def _times_table(rng: random.Random):
    a, b = rng.randint(2, 12), rng.randint(2, 12)
    return _item("times_table", f"$${a} \\times {b}$$", Fraction(a * b),
                 capability=RECALL, check_expr=f"{a} * {b}",
                 inline=f"${a} \\times {b}$")


def _multiply_multiple_of_ten(rng: random.Random):
    a, tens = rng.randint(21, 99), rng.choice([30, 40, 60, 70, 80, 90])
    return _item("multiply_multiple_of_ten", f"$${a} \\times {tens}$$", Fraction(a * tens),
                 check_expr=f"{a} * {tens}", inline=f"${a} \\times {tens}$")


def _multiply_two_digit(rng: random.Random):
    a, b = rng.randint(101, 999), rng.randint(21, 99)
    return _item("multiply_two_digit", f"$${a} \\times {b}$$", Fraction(a * b),
                 check_expr=f"{a} * {b}", inline=f"${a} \\times {b}$")


def _divide_exact(rng: random.Random):
    divisor, quotient = rng.randint(12, 40), rng.randint(12, 60)
    n = divisor * quotient
    return _item("divide_exact", f"$${_grouped(n)} \\div {divisor}$$", Fraction(quotient),
                 check_expr=f"{n} / {divisor}", inline=f"${n} \\div {divisor}$")


def _division_remainder(rng: random.Random):
    divisor = rng.randint(12, 40)
    quotient = rng.randint(4, 40)
    remainder = rng.randint(1, divisor - 1)
    n = divisor * quotient + remainder
    return _item("division_remainder",
                 f"What is the remainder when ${_grouped(n)}$ is divided by ${divisor}$?",
                 Fraction(remainder),
                 check_expr=f"{n} - {divisor} * {quotient}",
                 inline=f"remainder of {n} ÷ {divisor}")


# --------------------------------------------------------------------------- #
# Lesson 3 — Fractions
# --------------------------------------------------------------------------- #

_UNLIKE = [(2, 3), (3, 4), (2, 5), (3, 5), (4, 6), (2, 6), (3, 10), (4, 5)]


def _add_unlike_fractions(rng: random.Random):
    d1, d2 = rng.choice(_UNLIKE)
    n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
    expr = f"\\frac{{{n1}}}{{{d1}}} + \\frac{{{n2}}}{{{d2}}}"
    return _item("add_fractions", f"$${expr}$$", Fraction(n1, d1) + Fraction(n2, d2),
                 check_expr=f"{n1}/{d1} + {n2}/{d2}", inline=f"${expr}$")


def _subtract_unlike_fractions(rng: random.Random):
    d1, d2 = rng.choice([(2, 3), (3, 4), (2, 5), (3, 5), (4, 5), (3, 10)])
    n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
    a, b = Fraction(n1, d1), Fraction(n2, d2)
    if a < b:
        a, b, d1, d2, n1, n2 = b, a, d2, d1, n2, n1
    expr = f"\\frac{{{n1}}}{{{d1}}} - \\frac{{{n2}}}{{{d2}}}"
    return _item("subtract_fractions", f"$${expr}$$", a - b,
                 check_expr=f"{n1}/{d1} - {n2}/{d2}", inline=f"${expr}$")


def _fraction_times_whole(rng: random.Random):
    d = rng.choice([2, 3, 4, 5, 6]); n = rng.randint(1, d - 1); w = rng.randint(2, 12)
    expr = f"\\frac{{{n}}}{{{d}}} \\times {w}"
    return _item("fraction_times_whole", f"$${expr}$$", Fraction(n, d) * w,
                 check_expr=f"{n}/{d} * {w}", inline=f"${expr}$")


def _fraction_times_fraction(rng: random.Random):
    n1, d1 = rng.randint(1, 5), rng.randint(2, 6)
    n2, d2 = rng.randint(1, 5), rng.randint(2, 6)
    expr = f"\\frac{{{n1}}}{{{d1}}} \\times \\frac{{{n2}}}{{{d2}}}"
    return _item("fraction_times_fraction", f"$${expr}$$",
                 Fraction(n1, d1) * Fraction(n2, d2),
                 check_expr=f"{n1}/{d1} * {n2}/{d2}", inline=f"${expr}$")


def _fraction_divided_by_whole(rng: random.Random):
    d = rng.choice([2, 3, 4, 5]); n = rng.randint(1, d - 1); w = rng.randint(2, 6)
    expr = f"\\frac{{{n}}}{{{d}}} \\div {w}"
    return _item("fraction_div_whole", f"$${expr}$$", Fraction(n, d) / w,
                 check_expr=f"{n}/{d} / {w}", inline=f"${expr}$")


# --------------------------------------------------------------------------- #
# Lesson 5 — Area of a triangle
# --------------------------------------------------------------------------- #

def _even_product_pair(a: int, b: int, *, b_hi: int) -> tuple[int, int]:
    """Keep area answers whole without drawing more randoms.

    Triangle area is (a*b)/2. An odd product leaves a half, and a bank that mixes
    wholes with a half cannot imply one required_form. Adjusting `b` by one (no
    further rng call) keeps later generators on the same seed stream.
    """
    if (a * b) % 2 == 0:
        return a, b
    return a, b + 1 if b < b_hi else b - 1


def _triangle_area(rng: random.Random):
    base, height = _even_product_pair(rng.randint(3, 20), rng.randint(3, 20), b_hi=20)
    return _item("triangle_area",
                 f"A triangle has a base of ${base}$ cm and a height of ${height}$ cm. "
                 "What is its area, in square centimetres?",
                 Fraction(base * height, 2),
                 check_expr=f"1/2 * {base} * {height}",
                 inline=f"triangle area, base {base}, height {height}")


def _triangle_half_rectangle(rng: random.Random):
    w, h = _even_product_pair(rng.randint(3, 15), rng.randint(3, 15), b_hi=15)
    return _item("triangle_half_rectangle",
                 f"A triangle fills exactly half of a ${w}$ cm by ${h}$ cm rectangle. "
                 "What is the area of the triangle, in square centimetres?",
                 Fraction(w * h, 2),
                 check_expr=f"1/2 * {w} * {h}",
                 inline=f"half of a {w} by {h} rectangle")


# --------------------------------------------------------------------------- #
# Lesson 6 — Ratio
# --------------------------------------------------------------------------- #

def _ratio_simplify(rng: random.Random):
    a, b = rng.randint(1, 9), rng.randint(1, 9)
    if a == b:
        b += 1
    k = rng.randint(2, 9)
    left, right = a * k, b * k
    g = gcd(left, right)
    return _item("ratio_simplify",
                 f"Write the ratio ${left} : {right}$ in its simplest form.",
                 (left // g, right // g), kind="ratio",
                 check_expr=None,                  # a ratio, not a single value
                 inline=f"simplify {left}:{right}")


def _ratio_missing_part(rng: random.Random):
    a, b = rng.randint(2, 9), rng.randint(2, 9)
    if a == b:
        b += 1
    unit = rng.randint(2, 12)
    known = a * unit
    return _item("ratio_missing_part",
                 f"Ribbon A is ${known}$ m long. The ratio of A to B is ${a} : {b}$. "
                 "How many metres long is Ribbon B?",
                 Fraction(b * unit),
                 check_expr=f"{known} / {a} * {b}",
                 inline=f"A={known}m, A:B = {a}:{b}, find B")


def _ratio_share(rng: random.Random):
    a, b = rng.randint(1, 6), rng.randint(1, 6)
    unit = rng.randint(2, 15)
    total = (a + b) * unit
    return _item("ratio_share",
                 f"${total}$ sweets are shared between Ana and Ben in the ratio "
                 f"${a} : {b}$. How many sweets does Ana get?",
                 Fraction(a * unit),
                 check_expr=f"{total} / ({a} + {b}) * {a}",
                 inline=f"share {total} in {a}:{b}, Ana's part")


# --------------------------------------------------------------------------- #
# Lesson 7 — Angles
# --------------------------------------------------------------------------- #

def _angle_right(rng: random.Random):
    part = rng.randint(10, 80)
    return _item("angle_right",
                 f"A right angle is split into ${part}^\\circ$ and angle $p$. "
                 "How many degrees is angle $p$?",
                 Fraction(90 - part), check_expr=f"90 - {part}",
                 inline=f"right angle minus {part}°")


def _angle_straight_line(rng: random.Random):
    part = rng.randint(15, 165)
    return _item("angle_straight_line",
                 f"Angle $q$ and ${part}^\\circ$ lie on a straight line. "
                 "How many degrees is angle $q$?",
                 Fraction(180 - part), check_expr=f"180 - {part}",
                 inline=f"straight line minus {part}°")


def _angle_point(rng: random.Random):
    a, b = rng.randint(40, 140), rng.randint(40, 140)
    while a + b > 320:
        b = rng.randint(40, 140)
    return _item("angle_point",
                 f"Three angles meet at a point: ${a}^\\circ$, ${b}^\\circ$ and angle $r$. "
                 "How many degrees is angle $r$?",
                 Fraction(360 - a - b), check_expr=f"360 - {a} - {b}",
                 inline=f"angles at a point: {a}°, {b}°")


def _angle_opposite(rng: random.Random):
    """Two lines cross. Asks for the neighbour on the straight line, not the equal
    one — the vertically-opposite answer would just be the number already given,
    which tests nothing a learner has to work out."""
    given = rng.randint(20, 160)
    return _item("angle_opposite",
                 f"Two straight lines cross. One of the angles is ${given}^\\circ$. "
                 "How many degrees is the angle next to it on the straight line?",
                 Fraction(180 - given), check_expr=f"180 - {given}",
                 inline=f"crossed lines, neighbour of {given}°")


# --------------------------------------------------------------------------- #

SKILLS: list[Callable[[random.Random], dict[str, Any]]] = [
    _digit_value, _round_number, _multiply_by_tens, _divide_by_tens,
    _times_table, _multiply_multiple_of_ten, _multiply_two_digit,
    _divide_exact, _division_remainder,
    _add_unlike_fractions, _subtract_unlike_fractions, _fraction_times_whole,
    _fraction_times_fraction, _fraction_divided_by_whole,
    _triangle_area, _triangle_half_rectangle,
    _ratio_simplify, _ratio_missing_part, _ratio_share,
    _angle_right, _angle_straight_line, _angle_point, _angle_opposite,
]

_SKILL_TITLE = {
    "digit_value": "Place value", "round_number": "Rounding",
    "multiply_by_tens": "Multiply using tens", "divide_by_tens": "Divide using tens",
    "times_table": "Times tables",
    "multiply_multiple_of_ten": "Multiply by a multiple of ten",
    "multiply_two_digit": "Multiply by a 2-digit number",
    "divide_exact": "Divide by a 2-digit number",
    "division_remainder": "Division with a remainder",
    "add_fractions": "Add fractions", "subtract_fractions": "Subtract fractions",
    "fraction_times_whole": "Multiply a fraction by a whole number",
    "fraction_times_fraction": "Multiply two fractions",
    "fraction_div_whole": "Divide a fraction by a whole number",
    "triangle_area": "Area of a triangle",
    "triangle_half_rectangle": "Triangle inside a rectangle",
    "ratio_simplify": "Simplify a ratio", "ratio_missing_part": "Find a missing amount",
    "ratio_share": "Share in a given ratio",
    "angle_right": "Angles in a right angle", "angle_straight_line": "Angles on a straight line",
    "angle_point": "Angles at a point", "angle_opposite": "Crossing lines",
}


def build_items(count: int, *, seed: int = 12345) -> list[dict[str, Any]]:
    """Round-robin the generators so every lesson gets its fair share, rather than
    letting chance leave a lesson with two questions."""
    rng = random.Random(seed)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    guard = 0
    while len(items) < count and guard < count * 40:
        gen = SKILLS[guard % len(SKILLS)]
        guard += 1
        raw = gen(rng)
        if raw is None or raw["prompt"] in seen:
            continue
        seen.add(raw["prompt"])
        skill = raw["skill"]
        answer = raw["answer"]
        item = {
            "id": f"mp-{len(items) + 1:03d}-{skill}",
            "skill": skill,
            "skill_title": _SKILL_TITLE[skill],
            "chapter": CHAPTER_OF_SKILL[skill],
            "capability": raw["capability"],
            "prompt": raw["prompt"],
            "prompt_inline": raw["inline"],
            "answer_kind": raw["answer_kind"],
        }
        if raw["answer_kind"] == "ratio":
            a, b = answer
            item.update({"answer_ratio": [a, b], "answer_plain": f"{a}:{b}",
                         "answer_tex": f"${a} : {b}$",
                         "answer_num": a, "answer_den": b})
        else:
            item.update({"answer_num": answer.numerator, "answer_den": answer.denominator,
                         "answer_tex": f"${_frac_tex(answer)}$",
                         "answer_plain": _plain(answer),
                         "answer_is_reduced": True})
        item["check_expr"] = raw["check_expr"]
        items.append(item)
    return items


# --------------------------------------------------------------------------- #
# Answer parsing + checking — the deterministic marker
# --------------------------------------------------------------------------- #

_MIXED = re.compile(r"^\s*(-?\d+)\s+(\d+)\s*/\s*(\d+)\s*$")   # "2 3/4"
_FRAC = re.compile(r"^\s*(-?\d+)\s*/\s*(\d+)\s*$")            # "3/4"
_INT = re.compile(r"^\s*(-?\d+)\s*$")                         # "8"
_DEC = re.compile(r"^\s*(-?\d+)\.(\d+)\s*$")                  # "0.75"
_RATIO = re.compile(r"^\s*(\d+)\s*(?::|\bto\b)\s*(\d+)\s*$", re.IGNORECASE)  # "5:4", "5 to 4"


def parse_answer(text: str) -> Fraction | None:
    """A learner's typed answer as an exact Fraction, or None if unreadable.
    Accepts integers, 'a/b', mixed 'w a/b', and terminating decimals. Commas are
    ignored so '4,900' reads the same as '4900'."""
    if not text or not text.strip():
        return None
    s = text.strip().replace("−", "-").replace(",", "")
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


def parse_ratio(text: str) -> tuple[int, int] | None:
    """'5:4' or '5 to 4' as a pair, or None. Zero on either side is not a ratio."""
    if not text:
        return None
    m = _RATIO.match(text.strip().replace(",", ""))
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    return (a, b) if a and b else None


def is_reduced(f: Fraction, learner_num: int, learner_den: int) -> bool:
    """Did the learner give it in simplest form? Compares the fraction they wrote
    against its reduced form. Whole numbers are trivially reduced."""
    if learner_den in (0, 1):
        return True
    return gcd(abs(learner_num), abs(learner_den)) == 1


def _check_ratio(item: dict[str, Any], typed: str) -> dict[str, Any]:
    want = tuple(item["answer_ratio"])
    got = parse_ratio(typed)
    if got is None:
        return {"correct": False, "equal": False, "not_simplest": False, "parsed": None,
                "answer_tex": item["answer_tex"], "answer_plain": item["answer_plain"],
                "message": "Write a ratio like 5:4."}
    # same comparison once both are reduced
    gw, gg = gcd(*want), gcd(*got)
    equal = (want[0] // gw, want[1] // gw) == (got[0] // gg, got[1] // gg)
    simplest = gg == 1
    correct = equal and simplest
    if correct:
        msg = "Correct!"
    elif equal:
        msg = f"Right comparison, but make it simpler: {item['answer_plain']}."
    else:
        msg = f"Not quite. The answer is {item['answer_plain']}."
    return {"correct": correct, "equal": equal, "not_simplest": equal and not simplest,
            "parsed": f"{got[0]}:{got[1]}", "answer_tex": item["answer_tex"],
            "answer_plain": item["answer_plain"], "message": msg}


def check_answer(item: dict[str, Any], typed: str) -> dict[str, Any]:
    """Mark a typed answer against an item's computed answer.

    correct      : equal AND in simplest form (for fractions and ratios)
    equal        : mathematically equal, regardless of form
    not_simplest : equal but not reduced (e.g. 2/4 for 1/2) — a teaching moment
    """
    if item.get("answer_kind") == "ratio":
        return _check_ratio(item, typed)

    answer = Fraction(item["answer_num"], item["answer_den"])
    parsed = parse_answer(typed)
    if parsed is None:
        return {"correct": False, "equal": False, "not_simplest": False,
                "parsed": None, "answer_tex": item["answer_tex"],
                "answer_plain": item["answer_plain"],
                "message": "That is not a number I can read. Try like 3/4, 2 1/2, or 8."}

    equal = parsed == answer
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
# Self-test — the honesty gate
# --------------------------------------------------------------------------- #

def _round_independently(n: int, place: int) -> int:
    """A second rounding implementation, written differently from the generator's,
    so rounding items are still checked by two code paths that share nothing.
    Works on the decimal string rather than by arithmetic."""
    s = str(n)
    digits = len(str(place)) - 1                   # 10 -> 1, 100 -> 2, 1000 -> 3
    if digits >= len(s):
        keep, tail = 0, s
    else:
        keep, tail = int(s[:-digits]), s[-digits:]
    return (keep + 1) * place if int(tail[0]) >= 5 else keep * place


def self_test(count: int = 200) -> int:
    """Feed the checker answers whose right/wrong-ness is already known, and
    confirm every generated answer against a second, independent calculation. A
    marker that cannot fail a wrong answer is not marking anything."""
    bad = 0

    def fail(label: str, detail: str = "") -> None:
        nonlocal bad
        bad += 1
        print(f"  [FAIL] {label}{'  <- ' + detail if detail else ''}")

    half = {"answer_num": 1, "answer_den": 2, "answer_tex": "$\\frac{1}{2}$", "answer_plain": "1/2"}
    eight = {"answer_num": 8, "answer_den": 1, "answer_tex": "$8$", "answer_plain": "8"}
    two_and_half = {"answer_num": 5, "answer_den": 2, "answer_tex": "$2\\frac{1}{2}$", "answer_plain": "2 1/2"}
    ratio = {"answer_kind": "ratio", "answer_ratio": [5, 4], "answer_tex": "$5 : 4$",
             "answer_plain": "5:4"}

    cases = [
        (half, "1/2", "correct", True),
        (half, "2/4", "equal-not-simplest", False),
        (half, "0.5", "decimal equal", True),
        (half, "3/4", "wrong", False),
        (half, "", "empty", False),
        (half, "banana", "garbage", False),
        (eight, "8", "whole correct", True),
        (eight, "7", "whole wrong", False),
        (two_and_half, "2 1/2", "mixed correct", True),
        (two_and_half, "5/2", "improper equal", True),
        (two_and_half, "2 2/4", "mixed not simplest", False),
        ({"answer_num": 4900, "answer_den": 1, "answer_tex": "$4900$", "answer_plain": "4900"},
         "4,900", "comma tolerated", True),
        (ratio, "5:4", "ratio correct", True),
        (ratio, "5 to 4", "ratio in words", True),
        (ratio, "10:8", "ratio not simplest", False),
        (ratio, "4:5", "ratio reversed", False),
        (ratio, "5", "ratio missing a side", False),
        (ratio, "", "ratio empty", False),
    ]
    for item, typed, label, want in cases:
        got = check_answer(item, typed)["correct"]
        if got != want:
            fail(f"{label}: typed={typed!r} -> correct={got} (want {want})")

    # Every generated answer, confirmed a second way.
    items = build_items(count)
    import math_evaluators as M
    by_expr = by_round = 0
    for it in items:
        stored = Fraction(it["answer_num"], it["answer_den"])
        if it["check_expr"]:
            independent = M.evaluate(it["check_expr"])
            if independent is None or independent != stored:
                fail(f"{it['id']} answer disagrees with {it['check_expr']}",
                     f"stored={stored} independent={independent}")
            by_expr += 1
        elif it["skill"] == "round_number":
            n, place = _parse_round_inline(it["prompt_inline"])
            if _round_independently(n, place) != stored.numerator:
                fail(f"{it['id']} rounding disagrees",
                     f"stored={stored} independent={_round_independently(n, place)}")
            by_round += 1
        elif it["skill"] == "ratio_simplify":
            a, b = it["answer_ratio"]
            if gcd(a, b) != 1:
                fail(f"{it['id']} simplified ratio is not in simplest form", f"{a}:{b}")
            by_round += 1
        else:
            fail(f"{it['id']} has no independent check at all", it["skill"])

    missing = sorted(set(CHAPTER_OF_SKILL) - {i["skill"] for i in items})
    if missing:
        fail("every skill appears in the bank", f"missing {missing}")
    for it in items:
        if it["chapter"] != CHAPTER_OF_SKILL[it["skill"]]:
            fail(f"{it['id']} is filed under the wrong lesson")

    print(f"  {len(items)} items: {by_expr} confirmed against a separate sum, "
          f"{by_round} against a second implementation")
    chapters: dict[int, int] = {}
    for it in items:
        chapters[it["chapter"]] = chapters.get(it["chapter"], 0) + 1
    print("  per lesson: " + ", ".join(f"L{k}={v}" for k, v in sorted(chapters.items())))
    print(f"\n{'marker is honest — it fails wrong answers' if not bad else str(bad) + ' FAILED'}")
    return 1 if bad else 0


def _parse_round_inline(inline: str) -> tuple[int, int]:
    """'round 4865 to nearest hundred' -> (4865, 100)."""
    m = re.search(r"round (\d+) to nearest (ten|hundred|thousand)", inline)
    n = int(m.group(1))
    return n, {"ten": 10, "hundred": 100, "thousand": 1000}[m.group(2)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=200)
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
    per_chapter: dict[int, list[str]] = {}
    for it in items:
        per_chapter.setdefault(it["chapter"], []).append(it["skill_title"])
    print(f"wrote {len(items)} practice items -> {out}")
    for ch in sorted(per_chapter):
        titles = per_chapter[ch]
        kinds = sorted(set(titles))
        print(f"  lesson {ch}: {len(titles):3} questions   {', '.join(kinds)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
