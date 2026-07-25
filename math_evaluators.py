"""Maths-domain checks: the arithmetic in a lesson must actually be true.

PTE needed a model judge because "is this claim supported by the Pearson guide?"
is a reading question. Maths is different and better: correctness is *computable*.
A worked example that says 4 x 3 = 10 is wrong, provably, with no judgement.

So the maths domain pack's core check is an arithmetic verifier, and it is fully
deterministic — the strongest kind of check we have.

The trap, learned the hard way: a naive "a op b = c" regex is useless here. Run
against real textbook output it produced a 55% false-positive rate, because
maths working is written as CHAINS:

    78 x 30 = 78 x 3 x 10 = 234 x 10 = 2340

A pairwise regex reads "78 x 30 = 78" and screams. The fix is to split the chain
on '=', evaluate every side independently with correct operator precedence, and
require them all to be equal. Anything containing a blank (the student's answer)
is skipped, not flagged — a fill-in-the-blank is not an error.

Exact arithmetic throughout (fractions.Fraction), so 1/3 + 1/6 = 1/2 is exact and
no float rounding can invent a false mismatch.
"""

from __future__ import annotations

import ast
import re
from fractions import Fraction
from typing import Any

from evaluation_contract import Finding

# A blank the learner is meant to fill: LaTeX \square, an underscore run, or the
# whitespace-in-braces LlamaParse emits for a blank numerator. Never an error.
_BLANK = re.compile(r"\\square|_{2,}|\{\s{2,}\}|\{\s*\}|\?|\\underline")

# Things we cannot evaluate: variables, units, words. Presence means "skip".
_NON_NUMERIC = re.compile(r"[A-Za-z]")


def _normalise(expr: str) -> str:
    """LaTeX/maths notation -> a plain arithmetic string."""
    s = expr
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("$", "").replace("\\,", "").replace("\\;", "")
    # mixed numbers first: 3\frac{1}{6} -> (3+1/6)
    s = re.sub(r"(\d+)\s*\\frac\{([^{}]+)\}\{([^{}]+)\}", r"(\1+(\2)/(\3))", s)
    s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", r"((\1)/(\2))", s)
    s = s.replace("\\times", "*").replace("\\cdot", "*").replace("\\div", "/")
    s = s.replace("×", "*").replace("÷", "/").replace("−", "-").replace("–", "-")
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s)      # 15,000 -> 15000
    s = s.replace("%", "").replace("°", "")
    return s.strip()


class _Unevaluable(Exception):
    pass


def _eval_node(node: ast.AST) -> Fraction:
    """Evaluate a restricted arithmetic AST exactly. No names, no calls, no eval()."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise _Unevaluable("non-numeric constant")
        return Fraction(str(node.value))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _eval_node(node.operand)
        return v if isinstance(node.op, ast.UAdd) else -v
    if isinstance(node, ast.BinOp):
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise _Unevaluable("division by zero")
            return left / right
    raise _Unevaluable(f"unsupported syntax {type(node).__name__}")


def evaluate(expr: str) -> Fraction | None:
    """Exact value of an arithmetic expression, or None if it isn't evaluable
    (contains a blank, a variable, units, or anything we don't understand)."""
    if not expr or not expr.strip():
        return None
    if _BLANK.search(expr):
        return None
    s = _normalise(expr)
    if not s or _NON_NUMERIC.search(s):
        return None
    if not re.search(r"\d", s):
        return None
    try:
        return _eval_node(ast.parse(s, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, _Unevaluable, RecursionError):
        return None


def check_chain(chain: str) -> tuple[bool, str]:
    """Verify one '=' chain. Every evaluable side must have the same value.

    Returns (ok, detail). ok=True also when there is nothing checkable — a chain
    we cannot evaluate is not evidence of an error.
    """
    sides = [p for p in chain.split("=")]
    values: list[tuple[str, Fraction]] = []
    for side in sides:
        v = evaluate(side)
        if v is not None:
            values.append((side.strip(), v))
    if len(values) < 2:
        return True, "nothing checkable"
    first_text, first = values[0]
    for text, v in values[1:]:
        if v != first:
            return False, f"'{first_text}' = {first} but '{text}' = {v}"
    return True, f"all {len(values)} sides = {first}"


# Chains appear inline ($...$) and in display blocks ($$...$$), and as plain text.
_MATH_SPAN = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.DOTALL)


# One math block often holds SEVERAL equations, separated by \qquad, a line break
# or a comma:  "3\frac{5}{8}=\frac{29}{8},\qquad 1\frac{7}{12}=\frac{19}{12}".
# Treating that as one chain compares the first side against the last and reports
# a false error — both equations are individually correct. Split them apart first.
_EQ_SEPARATOR = re.compile(r"\\qquad|\\quad|\\\\|\\newline|;|\n")
_ALIGN_ENV = re.compile(r"\\(?:begin|end)\{(?:aligned|align\*?|gather\*?|array)\}(?:\{[^}]*\})?")


def _split_equations(span: str) -> list[str]:
    span = _ALIGN_ENV.sub(" ", span).replace("&", "")
    # Drop thousands separators BEFORE splitting on commas, or "15,000 \div 30"
    # gets torn into "15" and "000 \div 30". (_normalise does this too, but it
    # runs later — order matters here.)
    span = re.sub(r"(?<=\d),(?=\d{3}\b)", "", span)
    parts = list(_EQ_SEPARATOR.split(span))
    out: list[str] = []
    for part in parts:
        # A comma separates equations only when what remains still holds more than
        # one '='; otherwise it is ordinary punctuation.
        if "," in part and part.count("=") > 1:
            out.extend(x for x in part.split(","))
        else:
            out.append(part)
    return [p for p in out if p.count("=") >= 1]


def _chains_in(text: str) -> list[str]:
    """Equation chains, from LaTeX math spans only.

    Deliberately NOT scanning plain prose for arithmetic. Tried, and it produced
    fragments: it cannot span the "x" in "6 x 105 = 630", so it matched
    "105 = 630" and reported a false error; and "11 / 4 = 2 remainder 3" is
    correct integer division it cannot model. That is the same failure as the
    original pairwise regex, in a new costume.

    The real risk plain-scanning was meant to address — a file whose maths is
    never checked at all, passing vacuously — is handled honestly instead, by
    `checkable_chain_count`: absence of verifiable maths is REPORTED rather than
    guessed at. See build_math_grounded_base.check.
    """
    out = []
    for m in _MATH_SPAN.finditer(text or ""):
        span = m.group(1) or m.group(2) or ""
        if "=" in span:
            out.extend(_split_equations(span))
    return out


# Fields that quote a PROBLEM or a wrong belief, not the lesson's asserted maths.
# A "find and correct the mistake" worked example must contain a false equation in
# its `input`, and `common_mistakes[].mistake` / `misconception` are wrong by
# definition. Scanning these flags the very error the lesson is teaching pupils to
# catch — so the arithmetic check reads only what the lesson ASSERTS as true
# (model_answer, example, formula, the final working), never the stimulus.
_STIMULUS_KEYS = frozenset({"input", "mistake", "misconception"})


def checkable_chain_count(doc: Any) -> int:
    """How many equations we could actually verify. Zero means the arithmetic
    check said nothing about this artifact — which callers must not read as a pass."""
    n = 0
    for text in _walk_asserted(doc):
        for chain in _chains_in(text):
            if check_chain(chain)[1] != "nothing checkable":
                n += 1
    return n


def _walk_strings(value: Any):
    """Every string anywhere in the lesson — worked examples, techniques, rules."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def _walk_asserted(value: Any):
    """Strings the lesson asserts as true — skips the problem-statement and
    labelled-mistake fields where wrong maths is deliberate (see _STIMULUS_KEYS)."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in _STIMULUS_KEYS:
                yield from _walk_asserted(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_asserted(v)


def arithmetic_findings(doc: dict[str, Any]) -> list[Finding]:
    """Every false arithmetic statement the lesson ASSERTS as true."""
    out: list[Finding] = []
    seen: set[str] = set()
    for text in _walk_asserted(doc):
        for chain in _chains_in(text):
            key = re.sub(r"\s+", " ", chain).strip()
            if key in seen:
                continue
            seen.add(key)
            ok, detail = check_chain(chain)
            if not ok:
                out.append(Finding(
                    summary=f"The maths is wrong: {key[:70]}",
                    detail=f"{detail}. A lesson must not teach a false calculation.",
                    evidence=key[:200],
                    fixable=True,
                ))
    return out


# --------------------------------------------------------------------------- #
# Planted-error cases — the honesty gate for this checker
# --------------------------------------------------------------------------- #

def _doc(*expressions: str) -> dict[str, Any]:
    return {"worked_examples": [{"model_answer": " ".join(f"$${e}$$" for e in expressions)}]}


SELF_TESTS: list[tuple[dict[str, Any], bool]] = [
    # (payload, must_flag)
    # The exact false positive a pairwise regex produced on the real textbook:
    # a correct multi-step chain must stay silent.
    (_doc(r"78 \times 30 = 78 \times 3 \times 10 = 234 \times 10 = 2340"), False),
    (_doc(r"15,000 \div 30 = 15,000 \div 10 \div 3 = 1500 \div 3 = 500"), False),
    # Operator precedence must be respected.
    (_doc(r"10 + 4 \times 3 = 10 + 12 = 22"), False),
    # Genuinely wrong arithmetic must flag.
    (_doc(r"4 \times 3 = 10"), True),
    (_doc(r"420 \div 4 = 120"), True),
    # Exact fractions, including mixed numbers.
    (_doc(r"\frac{1}{2} + \frac{1}{3} = \frac{5}{6}"), False),
    (_doc(r"\frac{1}{2} + \frac{1}{3} = \frac{2}{5}"), True),
    (_doc(r"3\frac{1}{6} + 1\frac{9}{10} = 5\frac{1}{15}"), False),
    # A blank is the student's job, not an error.
    (_doc(r"4 \frac{3}{4} - 3\frac{7}{12} = 1\frac{\square}{12}"), False),
    (_doc(r"\$630 - \$378 = \$\square"), False),
    # Units/words are not evaluable -> must not flag.
    (_doc(r"5 \text{ cm} \times 3 = 15 \text{ cm}"), False),
    # Several correct equations in ONE block, separated by \qquad / comma / line
    # break. An earlier version chained them together and compared the first side
    # against the last, inventing errors in output that was entirely correct —
    # and it did so more often on the arm that used MORE LaTeX, i.e. it punished
    # the better output. These must all stay silent.
    (_doc(r"3\frac{5}{8}=\frac{29}{8},\qquad 1\frac{7}{12}=\frac{19}{12}"), False),
    (_doc(r"\frac{29}{8}=\frac{87}{24},\qquad \frac{19}{12}=\frac{38}{24}"), False),
    (_doc(r"\begin{aligned} 3\frac{5}{8}&=\frac{29}{8}\\ 1\frac{1}{4}&=\frac{5}{4} \end{aligned}"), False),
    # ...but a genuine error inside a multi-equation block must STILL be caught.
    (_doc(r"\frac{1}{2}=\frac{2}{4},\qquad \frac{1}{3}=\frac{2}{5}"), True),
    # Plain prose arithmetic is NOT scanned — see _chains_in for why. These must
    # stay silent rather than produce the fragment errors that scanning caused.
    ({"worked_examples": [{"example": "11 / 4 = 2 remainder 3"}]}, False),
    ({"worked_examples": [{"example": "6 x 105 = 630 and 630 - 378 = 252"}]}, False),
    # A "find the mistake" example has a deliberately WRONG equation in its input.
    # That is the exercise, not a defect — the stimulus fields must be skipped.
    # (Lesson 3 looped forever because this was flagged.)
    ({"worked_examples": [{"input": r"A pupil writes $\frac{1}{3}+\frac{1}{2}=\frac{2}{5}$.",
                           "model_answer": r"The answer is $\frac{5}{6}$."}]}, False),
    ({"common_mistakes": [{"mistake": r"They write $2 	imes 3 = 5$."}]}, False),
    # ...but the SAME wrong equation ASSERTED in the solution must still be caught.
    ({"worked_examples": [{"model_answer": r"$\frac{1}{3}+\frac{1}{2}=\frac{2}{5}$"}]}, True),
]
