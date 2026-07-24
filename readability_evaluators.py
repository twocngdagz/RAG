"""Is the lesson actually readable by the pupil it is written for?

A maths lesson for ten-year-olds that reads at US grade 9 is a failed lesson, no
matter how correct its arithmetic. The A/B measured exactly that: telling the
model "write for 10-11 year olds" moved the reading grade from 10.3 to 8.9 — real
improvement, still far above the ~5 the audience needs. Prose difficulty is
measurable, so it should be checked and gated like anything else, not hoped for.

Two numbers, because they are fixed differently:

  sentence length   the big lever, and entirely under the writer's control.
                    "Because the denominators are different, you must first find
                    a common denominator before you can add the numerators
                    together" is one 20-word sentence that should be three.
  word difficulty   partly forced by the subject: "denominator" is five syllables
                    and a fractions lesson cannot avoid it. So the finding leads
                    with sentence length, which is always fixable.

What is measured is PROSE only. Model answers, formulas and LaTeX are stripped —
a worked solution is meant to contain `\\frac{29}{8}`, and counting that as hard
vocabulary would penalise a lesson for doing its job.
"""

from __future__ import annotations

import re
from typing import Any

from evaluation_contract import Finding

# Fields whose content is working, notation or stimulus — not prose to the pupil.
_NOT_PROSE = {"model_answer", "example", "formula", "input", "item", "source_label",
              "schema_version", "task_type", "tags"}

_MATH_SPAN = re.compile(r"\$\$.+?\$\$|\$[^$]*\$|\\[a-zA-Z]+\{[^{}]*\}")


def _syllables(word: str) -> int:
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(re.findall(r"[aeiouy]+", w))
    if w.endswith("e") and n > 1:
        n -= 1
    return max(1, n)


def prose_of(doc: Any) -> str:
    """Every string meant to be READ by the learner."""
    bits: list[str] = []

    def walk(value: Any, key: str | None = None) -> None:
        if isinstance(value, str):
            if key not in _NOT_PROSE:
                bits.append(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for v in value:
                walk(v, key)

    walk(doc)
    return " ".join(bits)


def measure(text: str) -> dict[str, float] | None:
    """Flesch-Kincaid grade plus its two components, or None if unmeasurable."""
    text = _MATH_SPAN.sub(" ", text or "")
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.split()) >= 3]
    words = re.findall(r"[A-Za-z']+", text)
    # Too little prose to measure is not evidence of anything. But keep the
    # sentence floor LOW: bad writing has fewer, longer sentences, so a high
    # sentence threshold would let the worst prose escape as "unmeasurable".
    if len(sentences) < 3 or len(words) < 80:
        return None
    syl = sum(_syllables(w) for w in words)
    wps = len(words) / len(sentences)
    spw = syl / len(words)
    return {
        "grade": 0.39 * wps + 11.8 * spw - 15.59,
        "words_per_sentence": wps,
        "syllables_per_word": spw,
        "sentences": float(len(sentences)),
    }


def common_long_words(text: str, n: int = 6) -> list[tuple[str, int]]:
    """The most frequent 3+ syllable words — the ones worth replacing."""
    import collections
    text = _MATH_SPAN.sub(" ", text or "")
    words = [w.lower() for w in re.findall(r"[A-Za-z']+", text) if _syllables(w) >= 3]
    return collections.Counter(words).most_common(n)


def longest_sentences(text: str, n: int = 3) -> list[str]:
    text = _MATH_SPAN.sub(" ", text or "")
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 3]
    return sorted(sents, key=lambda s: -len(s.split()))[:n]


def findings_for(doc: dict[str, Any], *, max_grade: float,
                 max_words_per_sentence: float = 14.0) -> list[Finding]:
    """Flag a lesson that reads above its audience's level.

    Findings are deliberately concrete: the model cannot act on "too hard", but it
    can act on "these three sentences are 26 words long, split them".
    """
    text = prose_of(doc)
    m = measure(text)
    if m is None:
        return []

    out: list[Finding] = []
    if m["grade"] > max_grade:
        # Name the lever that is ACTUALLY out of range. Telling a writer to
        # "split long sentences" when their sentences already average 11 words
        # is advice they cannot act on — measured against the real Singapore
        # Math 5A textbook (grade 4.0), our lessons matched it on sentence
        # length (11 vs 10.1) and missed entirely on word length (1.67 vs 1.33
        # syllables). The fix was vocabulary, and the finding must say so.
        long_sentences = m["words_per_sentence"] > max_words_per_sentence
        if long_sentences:
            worst = longest_sentences(text)
            lever = (f"Sentences average {m['words_per_sentence']:.0f} words — split them. "
                     f"Longest: \"{worst[0][:110] if worst else ''}\"")
            evidence = worst[0][:200] if worst else ""
        else:
            heavy = common_long_words(text)
            lever = (f"Sentences are fine ({m['words_per_sentence']:.0f} words). The problem "
                     f"is word length: {m['syllables_per_word']:.2f} syllables per word. "
                     f"Replace long words with everyday ones. Most frequent long words: "
                     + ", ".join(f"{w} (x{n})" for w, n in heavy))
            evidence = ", ".join(w for w, _ in heavy)
        out.append(Finding(
            summary=(f"Reads at grade {m['grade']:.1f}; this audience needs "
                     f"{max_grade:.0f} or below."),
            detail=lever,
            evidence=evidence,
            fixable=True,
        ))
    elif m["words_per_sentence"] > max_words_per_sentence:
        # Grade is fine but sentences are long — worth saying before it drifts.
        out.append(Finding(
            summary=(f"Sentences average {m['words_per_sentence']:.0f} words; "
                     f"aim for {max_words_per_sentence:.0f} or fewer."),
            detail="Shorter sentences are the main lever on readability for children.",
            fixable=True,
        ))
    return out


# --------------------------------------------------------------------------- #
# Planted cases — the honesty gate
# --------------------------------------------------------------------------- #

_SIMPLE = ("A fraction has two parts. The top number is the numerator. "
           "The bottom number is the denominator. It tells you how many equal "
           "parts there are. To add two fractions the bottoms must match. "
           "First make the bottoms the same. Then add the top numbers. "
           "Keep the bottom number the same. Now check your answer. "
           "Can you make it simpler? If you can, do it. That is the final answer. "
           "Try it with one half and one quarter. The answer is three quarters. ")

_HARD = ("Consequently, in order to successfully accomplish the addition of two "
         "fractional quantities possessing dissimilar denominators, it is "
         "absolutely necessary to initially determine an appropriate common "
         "denominator, subsequently transforming each individual fraction into an "
         "equivalent representation. Furthermore, the resulting numerators may "
         "then be combined additively, whereupon the practitioner should "
         "conscientiously evaluate whether simplification of the resultant "
         "fraction is achievable through identification of common factors. "
         "Additionally, comprehension of these underlying mathematical principles "
         "facilitates substantially improved computational proficiency overall. "
         "Moreover, learners who systematically internalise such procedural "
         "methodologies frequently demonstrate measurably superior performance "
         "when confronted with unfamiliar problem configurations requiring "
         "analogous conceptual transference and sustained analytical reasoning. ")


def _doc(text: str) -> dict[str, Any]:
    # source_label matters: the live check resolves the reading target from the
    # lesson's domain pack, so a fixture without one would resolve to a pack with
    # no limit and the check would silently pass everything. The honesty gate
    # caught exactly that when these fixtures lacked it.
    return {"source_label": "math5a:ch01", "overview": {"what_it_is": text}}


SELF_TESTS: list[tuple[dict[str, Any], bool]] = [
    (_doc(_SIMPLE), False),                 # short sentences, plain words -> silent
    (_doc(_HARD), True),                    # long clauses, latinate words -> must flag
    (_doc("Too short to judge."), False),   # not enough prose -> must not guess
    # Necessary maths vocabulary must not by itself trip the check.
    (_doc("The numerator is the top number. The denominator is the bottom number. "
          "A common denominator is one they share. Find it first. Then add. "
          "Check if you can simplify. Write the answer. That is all. "
          "Now try one yourself. Use one half and one third. The answer is five "
          "sixths. Well done. Keep going. "), False),
]
