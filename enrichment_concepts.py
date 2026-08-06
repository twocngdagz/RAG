"""Matching a chapter's own sentences to the other things the chapter says.

A lesson plan is DERIVED from the chapter's enrichment, never invented. The
enrichment says what the chapter teaches — `learning_goals` in the chapter's own
words, `techniques` giving the methods, `mastery_checklist` saying what a learner
should be able to check. The exercise bank says which questions exist. Neither
one names the other, so something has to say which goal a skill practises, which
technique carries out a goal, and which checklist line confirms it.

That something is here, and it is deliberately dull: shared words. Nothing in
this module writes teaching, summarises it, or asks a model what a sentence
means. It compares vocabulary, weights each shared word by how many candidates
use it, and reports the words that produced every match so a person reading the
draft can check it at a glance and move it in seconds when it is wrong.

WHY A WORD'S WEIGHT IS ONE OVER ITS SPREAD. In a chapter about angles every
skill says "angle", so "angle" cannot tell two of them apart; "point" belongs to
one, so it can. Dividing by the number of candidates using a word says exactly
that, and it needs no tuning per chapter: the chapter's own vocabulary decides
which of its words are distinctive.

WHAT IT REFUSES TO DO. Below the threshold there is no match — not a weak one.
Where two candidates match equally, the material has not said which, and this
module says so rather than picking. Both of those become reported gaps in a
draft, which is the point: a gap a person can see beats a guess that reads like
a decision.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

# One shared word that only one candidate uses is a match; a word every candidate
# uses never is. Two words shared with half the field also clears it. Stated in
# every draft, because a reader has to know what "matched" claimed.
MATCH_THRESHOLD = 1.0

# What the drafts print so a person knows what a match means before trusting one.
MATCH_RULE = (
    "Matched on shared words. Each sentence is lowercased, stripped of its LaTeX and "
    "of the everyday words the whole book uses, and what is left is reduced to a rough "
    "stem so 'fractions' and 'fraction' count as one word. A shared word is worth 1 "
    "divided by the number of candidates that use it, so a word only one candidate uses "
    f"decides a match and a word all of them use decides nothing. A total of "
    f"{MATCH_THRESHOLD} or more is a match. Every match lists the words that produced it."
)

# Words that say nothing about which maths a sentence is about: grammar, and the
# instruction verbs that appear in goals and in questions alike ("find", "write",
# "work out"). Leaving them in would match a goal to whichever skill happened to
# phrase its questions as an instruction.
#
# Words that read as everyday English but are maths here stay OUT of this list --
# "place" (place value), "right" (right angle), "even". A general-purpose stop
# list drops exactly the words a maths book means most.
EVERYDAY_WORDS = frozenset("""
about after all also and another any are around back because been before being below
best between both but can choose come correct correctly did does doing done down each
either else ever every find finds first for from get gets give gives going had
has have her here him his how into its itself just keep keeps know known let like
made make makes many may more most much must need needs new next not now off often
once one only onto other our out over own put puts read reads same say
says see seen set should show shows simple simply since solve solves some still such
take takes than that the their them then there these they thing things this those
through together too under until upon use used uses using very want was way well were
what when where whether which while who why will with within without work working
works would write writes you your
""".split())

# Every LaTeX span is dropped whole. The numbers in "$4{,}865$" are this question's
# numbers, not what it is about, and its command names ("frac", "times") would
# quietly become vocabulary that no sentence a person wrote could ever share.
LATEX = re.compile(r"\$[^$]*\$")
NOT_A_LETTER = re.compile(r"[^a-z]+")


def stem(word: str) -> str:
    """A rough stem, so one chapter's plural is another's singular.

    Not linguistics: enough that 'fractions'/'fraction', 'rounding'/'round' and
    'lines'/'line' each count once. It over-reaches sometimes ('halves' and
    'half' stay apart) and that costs a match rather than inventing one.
    """
    if word.endswith("ies") and len(word) > 4:
        word = word[:-3] + "y"
    elif word.endswith("es") and len(word) > 4 and not word.endswith("ses"):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        word = word[:-1]

    if word.endswith("ing") and len(word) > 5:
        word = word[:-3]

    if word.endswith("e") and len(word) > 3:
        word = word[:-1]

    return word


def words(*texts: object) -> set[str]:
    """The distinctive words of some sentences, stemmed."""
    found: set[str] = set()

    for text in texts:
        stripped = LATEX.sub(" ", str(text or "").lower())

        for token in NOT_A_LETTER.split(stripped):
            if len(token) > 2 and token not in EVERYDAY_WORDS:
                stemmed = stem(token)

                if stemmed not in EVERYDAY_WORDS:
                    found.add(stemmed)

    return found


@dataclass(frozen=True)
class Match:
    """One candidate a sentence matched, and the evidence for it."""

    key: str
    score: float
    matched_on: tuple[str, ...]
    # How much of the sentence, and how much of the candidate, the shared words
    # account for. Only ever used to break a tie the score could not, and
    # reported so a reader can see which way a close call went.
    of_sentence: float
    of_candidate: float

    def as_note(self) -> dict[str, object]:
        return {
            "score": round(self.score, 2),
            "matched_on": list(self.matched_on),
        }


@dataclass
class Assignment:
    """Which sentence a candidate belongs to, once every sentence has been scored."""

    key: str
    sentence_index: int | None
    match: Match | None
    # The other sentences this candidate matched, best first, as (index, match).
    # A draft shows them: seeing what a skill nearly belonged to is how a reader
    # catches one that landed on the wrong goal.
    runners_up: list[tuple[int, "Match"]] = field(default_factory=list)
    # Set when two sentences scored a candidate identically. The candidate is
    # assigned to neither: the material did not say which, and a coin toss here
    # would read as a decision in the draft.
    tied_between: list[int] = field(default_factory=list)


def score(sentence: str, candidates: dict[str, set[str]]) -> list[Match]:
    """Every candidate this sentence shares words with, best first.

    Includes candidates below the threshold: a draft shows what a match beat, and
    a near miss is exactly what a reader wants to see when the winner is wrong.
    """
    spread = Counter()

    for vocabulary in candidates.values():
        spread.update(vocabulary)

    sentence_words = words(sentence)
    matches: list[Match] = []

    for key, vocabulary in candidates.items():
        shared = sentence_words & vocabulary

        if not shared:
            continue

        matches.append(
            Match(
                key=key,
                score=sum(1.0 / spread[word] for word in shared),
                matched_on=tuple(sorted(shared)),
                of_sentence=len(shared) / len(sentence_words) if sentence_words else 0.0,
                of_candidate=len(shared) / len(vocabulary) if vocabulary else 0.0,
            )
        )

    matches.sort(key=lambda match: (-match.score, -match.of_candidate, match.key))

    return matches


def matched(sentence: str, candidates: dict[str, set[str]]) -> list[Match]:
    """Only the candidates that cleared the threshold, best first."""
    return [match for match in score(sentence, candidates) if match.score >= MATCH_THRESHOLD]


def assign(sentences: list[str], candidates: dict[str, set[str]]) -> list[Assignment]:
    """Give every candidate to the one sentence that matched it best.

    A candidate belongs to one sentence, not to every sentence it resembles: a
    skill's questions are one concept's question bank, and the same questions
    proposed under two concepts would schedule a learner the same exercise twice
    under two different claims about what it shows.
    """
    # Scored against the whole field, once: a word's weight is how many of THESE
    # candidates use it, so scoring a candidate on its own would make every word
    # it shares look distinctive.
    by_key: dict[str, list[tuple[int, Match]]] = {key: [] for key in candidates}

    for index, sentence in enumerate(sentences):
        for match in matched(sentence, candidates):
            by_key[match.key].append((index, match))

    assignments: list[Assignment] = []

    for key in candidates:
        scored = list(by_key[key])
        scored.sort(key=lambda pair: (-pair[1].score, -pair[1].of_sentence, -pair[1].of_candidate, pair[0]))

        if not scored:
            assignments.append(Assignment(key=key, sentence_index=None, match=None))
            continue

        tied = [index for index, match in scored if _rank(match) == _rank(scored[0][1])]

        if len(tied) > 1:
            assignments.append(
                Assignment(
                    key=key,
                    sentence_index=None,
                    match=None,
                    runners_up=list(scored),
                    tied_between=tied,
                )
            )
            continue

        assignments.append(
            Assignment(
                key=key,
                sentence_index=scored[0][0],
                match=scored[0][1],
                runners_up=list(scored[1:]),
            )
        )

    return assignments


def _rank(match: Match) -> tuple[float, float, float]:
    """What "equally well" means, so a tie is a fact rather than a rounding accident."""
    return (round(match.score, 6), round(match.of_sentence, 6), round(match.of_candidate, 6))


def common_words(texts: Iterable[str], *, at_least: float = 0.5) -> set[str]:
    """The words a group of sentences keeps using, rather than one sentence's own.

    A skill's questions share the wording of what they ask ("Round ... to the
    nearest ...") and differ in their numbers and names. Keeping only what most
    of them say leaves what the skill is about; keeping every word would make
    one question's ribbon or protractor part of the skill's vocabulary.
    """
    texts = list(texts)

    if not texts:
        return set()

    counts: Counter = Counter()

    for text in texts:
        counts.update(words(text))

    return {word for word, seen in counts.items() if seen >= at_least * len(texts)}
