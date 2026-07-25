"""Maths *reasoning* items — the second V2 slice, where the answer is an explanation.

The first slice worked because for arithmetic, correct is computable. Reasoning is
not: no code can decide whether "you have to make the bottoms the same because the
pieces are different sizes" is a good explanation. That is exactly why this module
draws a hard line and keeps the computable part in code:

  computable (here, authoritative)      not computable (a model, advisory only)
  ------------------------------------  --------------------------------------
  did they reach the right answer?      is the explanation clear?
  did they show a real step of working?  do they say *why*, not just what?
  ...............................        do they use maths words correctly?

Only the left column scores, and only the left column moves the spaced-repetition
schedule. The right column is help, never a mark — see math_reasoning_feedback.py.

Checking working without a model, honestly
------------------------------------------
Each item is generated together with the intermediate values a correct method
actually produces (the common denominator, the converted fractions, the amount
poured away). A response earns "working shown" by containing enough of them. The
trap is a learner who copies the question back: its numbers must never count as
working. So a required value matches either
  - literally, as written (e.g. the text "3/6"), or
  - by value (e.g. "0.25" for 1/4) but ONLY if that value is absent from the
    question, so nothing quoted from the question can be mistaken for working.
self_test() plants a copy-the-question-back response against every generated item
and requires it to fail. A check that cannot fail is not a check.

Usage:
  python math_reasoning_items.py --count 12       # write a bank
  python math_reasoning_items.py --self-test      # prove the checker is honest
"""

from __future__ import annotations

import argparse
import json
import random
import re
from fractions import Fraction
from math import lcm
from pathlib import Path
from typing import Any, Callable

OUTPUT_FILE = "output/math_reasoning_items.json"

# Capability tags (see the V2 architecture). These are the two capabilities that
# need an open response, which is what makes this slice different from the first.
REASONING = "reasoning"
COMMUNICATION = "communication"


# --------------------------------------------------------------------------- #
# Reading numbers out of free text
# --------------------------------------------------------------------------- #

# Order matters: a mixed number must win over the bare fraction inside it.
_NUM_RE = re.compile(
    r"(?P<mw>\d+)\s+(?P<mn>\d+)\s*/\s*(?P<md>\d+)"   # 1 1/2
    r"|(?P<fn>\d+)\s*/\s*(?P<fd>\d+)"                # 3/4
    r"|(?P<dec>\d+\.\d+)"                            # 0.75
    r"|(?P<int>\d+)"                                 # 6
)
_FRAC_TEX = re.compile(r"\\[dt]?frac\s*\{\s*(-?\d+)\s*\}\s*\{\s*(\d+)\s*\}")


def _de_tex(text: str) -> str:
    r"""Turn \frac{3}{4} into 3/4 so questions and typed answers tokenise the same."""
    return _FRAC_TEX.sub(r"\1/\2", text or "")


def read_numbers(text: str) -> tuple[list[str], set[Fraction]]:
    """Every number in the text, as (literal forms, values).

    Literals are normalised for spacing only ("3 / 6" -> "3/6") so that what the
    learner *wrote* can be compared, not just what it equals.
    """
    literals: list[str] = []
    values: set[Fraction] = set()
    for m in _NUM_RE.finditer(_de_tex(text)):
        if m.group("mw") is not None:
            w, n, d = int(m.group("mw")), int(m.group("mn")), int(m.group("md"))
            if d == 0:
                continue
            literals.append(f"{w} {n}/{d}")
            values.add(w + Fraction(n, d))
        elif m.group("fn") is not None:
            n, d = int(m.group("fn")), int(m.group("fd"))
            if d == 0:
                continue
            literals.append(f"{n}/{d}")
            values.add(Fraction(n, d))
        elif m.group("dec") is not None:
            literals.append(m.group("dec"))
            values.add(Fraction(m.group("dec")))
        else:
            literals.append(m.group("int"))
            values.add(Fraction(int(m.group("int"))))
    return literals, values


# --------------------------------------------------------------------------- #
# Item generators — each returns a fully-formed item whose ground truth is
# computed here, exactly, alongside the working a correct method produces.
# --------------------------------------------------------------------------- #

def _token_value(token: str) -> Fraction:
    """A required-working token as a value ('3/6' -> 1/2, '6' -> 6)."""
    return Fraction(token) if "/" in token else Fraction(int(token))


def _tex(n: int, d: int) -> str:
    return f"\\frac{{{n}}}{{{d}}}" if d != 1 else str(n)


def _plain(f: Fraction) -> str:
    if f.denominator == 1:
        return str(f.numerator)
    whole, rem = divmod(abs(f.numerator), f.denominator)
    sign = "-" if f < 0 else ""
    if whole and rem:
        return f"{sign}{whole} {rem}/{f.denominator}"
    return f"{sign}{rem}/{f.denominator}"


_UNLIKE_PAIRS = [(2, 3), (2, 5), (3, 4), (3, 5), (4, 5), (2, 6), (3, 10), (4, 6), (5, 6), (2, 7)]


def _spot_the_mistake(rng: random.Random) -> dict[str, Any] | None:
    """A classic misconception made visible: adding tops and bottoms.

    Reasoning, not recall — the learner has to say *why* it is wrong, which no
    amount of arithmetic drill teaches.
    """
    d1, d2 = rng.choice(_UNLIKE_PAIRS)
    n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
    a, b = Fraction(n1, d1), Fraction(n2, d2)
    answer = a + b
    wrong_n, wrong_d = n1 + n2, d1 + d2          # what the misconception produces
    L = lcm(d1, d2)
    c1, c2 = n1 * L // d1, n2 * L // d2

    question = (
        f"Tom worked out ${_tex(n1, d1)} + {_tex(n2, d2)} = {_tex(wrong_n, wrong_d)}$. "
        "Explain what Tom did wrong, then work it out correctly."
    )
    return {
        "skill": "spot_the_mistake_add",
        "skill_title": "Spot the mistake: adding fractions",
        "capability": REASONING,
        "question": question,
        "answer": answer,
        # the values a correct method actually writes down
        "working_tokens": [str(L), f"{c1}/{L}", f"{c2}/{L}"],
        "working_min": 2,
        "rubric": [
            "says Tom added the numerators and the denominators, which is not how adding works",
            "explains that the fractions must be changed to the same denominator first",
            f"shows the conversion to {L}ths and gives {_plain(answer)}",
        ],
        "model_answer": (
            f"Tom added the top numbers together and the bottom numbers together. You cannot do that, "
            f"because {_plain(a)} and {_plain(b)} are made of different sized pieces, so they do not add "
            f"straight across. First I changed them both into {L}ths: {_plain(a)} = {c1}/{L} and "
            f"{_plain(b)} = {c2}/{L}. Now the pieces are the same size, so I add the top numbers only: "
            f"{c1}/{L} + {c2}/{L} = {c1 + c2}/{L}, which is {_plain(answer)}."
        ),
    }


def _compare_and_explain(rng: random.Random) -> dict[str, Any] | None:
    """Which is greater, and how do you know? The 'how do you know' is the item."""
    d1, d2 = rng.choice(_UNLIKE_PAIRS)
    n1, n2 = rng.randint(1, d1 - 1), rng.randint(1, d2 - 1)
    a, b = Fraction(n1, d1), Fraction(n2, d2)
    if a == b:
        return None
    L = lcm(d1, d2)
    c1, c2 = n1 * L // d1, n2 * L // d2
    answer = max(a, b)

    question = (
        f"Which is greater, ${_tex(n1, d1)}$ or ${_tex(n2, d2)}$? "
        "Explain how you know, and show your working."
    )
    return {
        "skill": "compare_and_explain",
        "skill_title": "Compare fractions and explain",
        "capability": REASONING,
        "question": question,
        "answer": answer,
        # NOTE: the answer is one of the two fractions in the question, so on this
        # item type the working is what actually carries the check — which is why
        # working_min is 2 and the copy-the-question-back self-test matters most here.
        "working_tokens": [str(L), f"{c1}/{L}", f"{c2}/{L}"],
        "working_min": 2,
        "rubric": [
            "states which fraction is greater",
            f"changes both to the same denominator ({L}ths) so they can be compared fairly",
            "explains that with equal-sized pieces you can compare the numerators",
        ],
        "model_answer": (
            f"You cannot compare them straight away because the pieces are different sizes. I changed them "
            f"both into {L}ths: {_plain(a)} = {c1}/{L} and {_plain(b)} = {c2}/{L}. Now the pieces are the "
            f"same size, so I just compare the top numbers. {max(c1, c2)} is more than {min(c1, c2)}, "
            f"so {_plain(answer)} is greater."
        ),
    }


_STORIES = [
    ("A jug holds {q} of a litre of juice. Mia pours out {p} of the juice in the jug. "
     "How much juice is left in the jug? Show your working and explain each step.", "litre"),
    ("Sam has {q} of a metre of ribbon. He uses {p} of his ribbon to wrap a present. "
     "How much ribbon is left? Show your working and explain each step.", "metre"),
    ("A tank holds {q} of a litre of water. {p} of the water leaks out. "
     "How much water is left in the tank? Show your working and explain each step.", "litre"),
]


def _word_problem(rng: random.Random) -> dict[str, Any] | None:
    """Two steps, and the learner must talk through both. Communication, not just
    application: the working alone would not show whether they understood it."""
    story, _unit = rng.choice(_STORIES)
    qd = rng.choice([2, 3, 4, 5, 6, 8])
    qn = rng.randint(1, qd - 1)
    pd = rng.choice([2, 3, 4, 5])
    pn = rng.randint(1, pd - 1)
    have, part = Fraction(qn, qd), Fraction(pn, pd)
    used = have * part
    left = have - used
    if left <= 0 or used == have:
        return None

    question = story.format(q=f"${_tex(qn, qd)}$", p=f"${_tex(pn, pd)}$")
    item = {
        "skill": "two_step_word_problem",
        "skill_title": "Two-step problem: explain your steps",
        "capability": COMMUNICATION,
        "question": question,
        "answer": left,
        # the amount used up is the intermediate a correct method must produce
        "working_tokens": [_plain(used)],
        "working_min": 1,
        "rubric": [
            "works out how much was used first (a fraction of a fraction)",
            "takes that away from the starting amount",
            "says what each step means, not just the calculation",
        ],
        "model_answer": (
            f"First I worked out how much was used. {_plain(part)} of {_plain(have)} means "
            f"{_plain(part)} × {_plain(have)} = {_plain(used)}. That is the amount that went. "
            f"Then I took it away from what there was at the start: {_plain(have)} − {_plain(used)} = "
            f"{_plain(left)}. So there is {_plain(left)} left."
        ),
    }
    # the intermediate must be genuinely new information, not a number already given
    _, qvals = read_numbers(question)
    if used in qvals or left in qvals:
        return None
    return item


GENERATORS: list[Callable[[random.Random], dict[str, Any] | None]] = [
    _spot_the_mistake,
    _compare_and_explain,
    _word_problem,
]

# The advisory rubric the model grades against. Deliberately about the explanation
# only — correctness is settled in code before the model is ever called.
ADVISORY_TRAIT_MAX = {"explains_why": 3, "clear_steps": 3, "maths_language": 2}
ADVISORY_MAX_TOTAL = sum(ADVISORY_TRAIT_MAX.values())


def build_items(count: int, *, seed: int = 4242) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    guard = 0
    while len(items) < count and guard < count * 40:
        guard += 1
        raw = rng.choice(GENERATORS)(rng)
        if raw is None or raw["question"] in seen:
            continue
        answer: Fraction = raw["answer"]
        _, qvals = read_numbers(raw["question"])
        # For the two item types where the answer is new information, keep it new:
        # an answer already printed in the question would mark a copy-back correct.
        if raw["skill"] != "compare_and_explain" and answer in qvals:
            continue
        # Reject any item where writing the bare answer would also earn a working
        # hit — i.e. a required value that equals the answer and is value-matchable
        # (not shielded by being in the question). Caught by the self-test on word
        # problems where the amount used happens to equal the amount left.
        if any(_token_value(t) == answer and answer not in qvals for t in raw["working_tokens"]):
            continue
        seen.add(raw["question"])
        items.append({
            "id": f"mr-{len(items) + 1:03d}-{raw['skill']}",
            "kind": "reasoning",
            "skill": raw["skill"],
            "skill_title": raw["skill_title"],
            "capability": raw["capability"],
            "question": raw["question"],
            "answer_num": answer.numerator,
            "answer_den": answer.denominator,
            "answer_plain": _plain(answer),
            "working_tokens": raw["working_tokens"],
            "working_min": raw["working_min"],
            "question_values": sorted(f"{v.numerator}/{v.denominator}" for v in qvals),
            "rubric": raw["rubric"],
            "model_answer": raw["model_answer"],
        })
    return items


# --------------------------------------------------------------------------- #
# The deterministic check — what code can honestly decide on its own
# --------------------------------------------------------------------------- #

def check_working(item: dict[str, Any], response: str) -> dict[str, Any]:
    """Score the computable part of an open response: right answer, working shown.

    This is crude on purpose. It cannot tell a good explanation from a bad one, and
    it does not pretend to — it decides only what is decidable, and that is what
    scores and what moves the schedule.
    """
    answer = Fraction(item["answer_num"], item["answer_den"])
    literals, values = read_numbers(response or "")
    qvals = {Fraction(s) for s in item.get("question_values", [])}
    literal_set = set(literals)

    answer_shown = answer in values

    hits: list[str] = []
    for token in item["working_tokens"]:
        if token in literal_set:
            hits.append(token)
            continue
        # A value-only match counts only when that value is not already in the
        # question — otherwise quoting the question would read as working.
        tok_val = _token_value(token)
        if tok_val in values and tok_val not in qvals:
            hits.append(token)

    working_min = int(item.get("working_min", 1))
    working_shown = len(hits) >= working_min
    correct = answer_shown and working_shown

    if correct:
        message = "Right answer, and you showed your working."
    elif answer_shown and not working_shown:
        message = "Right answer — but show the steps that got you there."
    elif working_shown and not answer_shown:
        message = f"Good working, but the final answer should be {item['answer_plain']}."
    else:
        message = f"Not there yet. The answer is {item['answer_plain']} — show each step."

    return {
        "correct": correct,
        "answer_shown": answer_shown,
        "working_shown": working_shown,
        "working_hits": hits,
        "working_needed": working_min,
        "answer_plain": item["answer_plain"],
        "message": message,
    }


# --------------------------------------------------------------------------- #
# Self-test — the honesty gate
# --------------------------------------------------------------------------- #

_EMPTY_ISH = ["", "   ", "i dont know", "It is easy.", "because my teacher said so"]


def self_test(count: int = 60, *, seed: int = 4242) -> int:
    """Prove the deterministic check both passes real work and fails non-work.

    Run against every generated item, so a generator that produces working tokens
    its own worked answer never writes is caught here rather than in front of a child.
    """
    items = build_items(count, seed=seed)
    bad = 0

    def fail(label: str, detail: str = "") -> None:
        nonlocal bad
        bad += 1
        print(f"  [FAIL] {label}{'  <- ' + detail if detail else ''}")

    if len(items) < count:
        fail("bank generation", f"only {len(items)}/{count} items")

    # 1. Every item's own worked answer must pass its own check.
    for it in items:
        r = check_working(it, it["model_answer"])
        if not r["correct"]:
            fail(f"worked answer passes ({it['id']})",
                 f"answer_shown={r['answer_shown']} working={r['working_hits']}")

    # 2. Copying the question back must never count as reasoning. This is the
    #    check that keeps 'working shown' meaningful.
    for it in items:
        r = check_working(it, it["question"])
        if r["correct"]:
            fail(f"question copied back is rejected ({it['id']})", str(r["working_hits"]))

    # 3. Empty and hand-waving responses must fail.
    for it in items[:8]:
        for junk in _EMPTY_ISH:
            if check_working(it, junk)["correct"]:
                fail(f"junk rejected ({it['id']})", repr(junk))

    # 4. The right answer with no working must NOT pass — the point of the task.
    for it in items:
        if check_working(it, f"The answer is {it['answer_plain']}.")["correct"]:
            fail(f"bare answer without working is rejected ({it['id']})")

    # 5. ...and working with the wrong final answer must not pass either.
    for it in items:
        wrong = Fraction(it["answer_num"], it["answer_den"]) + 100
        text = " ".join(it["working_tokens"]) + f" so the answer is {wrong.numerator}/{wrong.denominator}"
        if check_working(it, text)["correct"]:
            fail(f"working with a wrong answer is rejected ({it['id']})")

    # 6. Both directions on the tokeniser itself.
    lits, vals = read_numbers(r"I changed \frac{1}{2} into 3 / 6 and got 0.25 and 1 1/2 and 6")
    for want in ("1/2", "3/6", "0.25", "1 1/2", "6"):
        if want not in lits:
            fail("tokeniser reads all number forms", f"missing {want!r} in {lits}")
    if Fraction(3, 2) not in vals or Fraction(1, 4) not in vals:
        fail("tokeniser values", str(sorted(vals)))

    by_skill: dict[str, int] = {}
    for it in items:
        by_skill[it["skill_title"]] = by_skill.get(it["skill_title"], 0) + 1
    print(f"  checked {len(items)} items across {len(by_skill)} skills:")
    for k, v in sorted(by_skill.items()):
        print(f"    {v:3}  {k}")
    print(f"\n{'the working check is honest — it fails non-work' if not bad else str(bad) + ' FAILED'}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=12)
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--output", default=OUTPUT_FILE)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    items = build_items(args.count, seed=args.seed)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(items, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} reasoning items -> {out}")
    for it in items:
        print(f"  {it['id']:34} {it['capability']:14} {it['skill_title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
