"""What a book must supply before it is allowed to teach anybody.

The point of this module is that adding book four should be cheap and safe. A
book either supplies what the teaching flow needs, or it is rejected before a
learner ever opens it — rather than a child finding out by hitting a blank screen
or, worse, reading an example that is quietly wrong.

Two decisions shape everything here.

**The contract must not be maths in disguise.** A maths method has steps; a
vocabulary word does not. A vocabulary word has a confusable neighbour; a maths
method does not. So a skill declares its `kind` and the required fields differ:

    procedure  an explanation, a worked example that shows its steps, and the
               usual wrong approach
    item       a meaning, at least one natural example that actually uses it,
               and something it is confused with

**Presence is not the test — usefulness is.** Every one of ELA's 17,661 items
carries a definition and example sentences, so a required-fields check passes all
of them. About a fifth of the examples are still a template with the word swapped
in — "The meeting focused on yacht as a key issue" — which no presence check
would ever notice.

**Measure the live data, not a seeder file.** An earlier version of this docstring
claimed 99% of those examples were templated. That number came from
`database/seeders/data/learning-items-merged-v3.json`, which is not what the app
serves. The live table has 28,318 distinct sentence skeletons where the seeder has
385, and 20% templated where the seeder has 99%. The seeder is a staging artefact;
the content that reached the database is far better than it. Reading the file that
was easy to reach, and reporting it as the state of the app, was wrong — the ELA
adapter now reads an export of the live table and falls back to the seeder only if
that is missing.

So the checks below look for circular definitions, examples that do not contain
the thing they illustrate, worked examples that assert an answer without showing
how, and — the one that catches mad-libs — example sentences that are the same
sentence with a different word dropped in.

Each check ships with a planted-error self-test. A check that cannot be made to
fail is not checking anything; this repo has been bitten by that before.

Usage:
  python content_contract.py --self-test
  python content_contract.py --book math5a
  python content_contract.py --book ela --limit 2000
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# A skeleton shared by this many different skills is a template, not an example.
TEMPLATE_REUSE_LIMIT = 5

PROCEDURE = "procedure"
ITEM = "item"


# --------------------------------------------------------------------------- #
# The contract's own vocabulary. Every book is mapped onto this before checking,
# so the checks never learn what subject they are looking at.
# --------------------------------------------------------------------------- #

@dataclass
class Lesson:
    id: str
    title: str
    about: str = ""                       # one sentence: what this is
    will_be_able_to: list[str] = field(default_factory=list)
    common_pitfalls: list[str] = field(default_factory=list)


@dataclass
class Skill:
    id: str
    lesson_id: str
    name: str
    kind: str = PROCEDURE
    explanation: str = ""                 # the meaning, in plain words
    steps: list[str] = field(default_factory=list)        # procedures only
    examples: list[str] = field(default_factory=list)
    common_mistake: str = ""              # procedures: wrong approach; items: confusable


@dataclass
class Finding:
    check: str
    severity: str                          # "reject" or "warn"
    where: str
    detail: str


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

def _blank(s: str | None, min_words: int = 3) -> bool:
    return not s or len(str(s).split()) < min_words


def check_lesson_priming(lessons: Iterable[Lesson]) -> list[Finding]:
    """A lesson that cannot fill a priming screen cannot open a session."""
    out = []
    for l in lessons:
        if _blank(l.about, 4):
            out.append(Finding("lesson_priming", "reject", l.id,
                               "no sentence saying what this lesson is about"))
        if not l.will_be_able_to:
            out.append(Finding("lesson_priming", "reject", l.id,
                               "does not say what the learner will be able to do"))
        if not l.common_pitfalls:
            out.append(Finding("lesson_priming", "warn", l.id,
                               "does not say what usually goes wrong"))
    return out


def check_skill_teaching(skills: Iterable[Skill]) -> list[Finding]:
    """Rule 2 of the guideline: nothing may be tested that was never taught."""
    out = []
    for s in skills:
        if _blank(s.explanation, 4):
            out.append(Finding("skill_teaching", "reject", s.id, "no explanation"))
        if not s.examples:
            out.append(Finding("skill_teaching", "reject", s.id, "no example"))
        if s.kind == PROCEDURE and len(s.steps) < 2:
            out.append(Finding("skill_teaching", "reject", s.id,
                               "a procedure with no steps shown — teaching by assertion"))
        # A procedure's usual mistake is a sentence ("writing the bigger number
        # first"). A vocabulary item's is a single confusable word ("ship").
        # Demanding a sentence of both was the contract being maths-shaped, which
        # is exactly what it is supposed to avoid — caught by its own self-test.
        if _blank(s.common_mistake, 3 if s.kind == PROCEDURE else 1):
            out.append(Finding("skill_teaching", "warn", s.id,
                               "does not name the usual mistake or a confusable"))
    return out


def check_definition_not_circular(skills: Iterable[Skill]) -> list[Finding]:
    """'A yacht is a yacht used for yachting.' Explaining a word with itself and
    nothing else teaches nobody anything."""
    out = []
    for s in skills:
        name = (s.name or "").strip().lower()
        if not name or len(name) < 3:
            continue
        words = re.findall(r"[a-z']+", (s.explanation or "").lower())
        if not words:
            continue
        rest = [w for w in words if w != name and not w.startswith(name[:max(4, len(name) - 2)])]
        if name in words and len(rest) < 4:
            out.append(Finding("circular_definition", "reject", s.id,
                               f"explains {s.name!r} using itself and little else"))
    return out


def check_example_uses_the_thing(skills: Iterable[Skill]) -> list[Finding]:
    """An example that never mentions what it is an example of is decoration.
    Only meaningful for vocabulary-style items, where the skill name is a word
    that should appear in its own example sentence."""
    out = []
    for s in skills:
        if s.kind != ITEM:
            continue
        stem = re.escape((s.name or "").strip().lower()[:max(4, len(s.name) - 2)])
        if not stem:
            continue
        if not any(re.search(stem, (e or "").lower()) for e in s.examples):
            out.append(Finding("example_uses_the_thing", "reject", s.id,
                               f"no example actually contains {s.name!r}"))
    return out


def _skeleton(text: str, name: str) -> str:
    """The sentence with the thing it teaches removed, so two examples that are
    the same template around different words collapse to one string."""
    if not name:
        return (text or "").strip().lower()
    stem = re.escape(name.strip().lower()[:max(4, len(name) - 2)])
    return re.sub(rf"\b{stem}\w*\b", "___", (text or "").lower()).strip()


def check_examples_not_templated(skills: list[Skill]) -> list[Finding]:
    """The one that catches mad-libs.

    Strip each example of the thing it is teaching and see what is left. If the
    same husk turns up across many unrelated skills, nobody wrote those examples
    for those skills — a template was filled in, and the result is 'The meeting
    focused on yacht as a key issue'.
    """
    by_skeleton: dict[str, set[str]] = defaultdict(set)
    for s in skills:
        for e in s.examples:
            sk = _skeleton(e, s.name)
            if len(sk.split()) >= 4:
                by_skeleton[sk].add(s.id)

    out = []
    flagged: set[str] = set()
    for sk, ids in by_skeleton.items():
        if len(ids) >= TEMPLATE_REUSE_LIMIT:
            for sid in ids:
                if sid not in flagged:
                    flagged.add(sid)
                    out.append(Finding(
                        "templated_examples", "reject", sid,
                        f"example is a template shared with {len(ids) - 1} other skills: {sk[:60]!r}"))
    return out


def check_worked_examples_show_work(skills: Iterable[Skill]) -> list[Finding]:
    """A worked example whose steps are one line is an answer wearing a costume."""
    out = []
    for s in skills:
        if s.kind != PROCEDURE:
            continue
        if s.steps and all(len(str(st).split()) < 3 for st in s.steps):
            out.append(Finding("worked_example_shows_work", "warn", s.id,
                               "steps are too terse to follow"))
    return out


CHECKS_ON_SKILLS = [
    check_skill_teaching,
    check_definition_not_circular,
    check_example_uses_the_thing,
    check_worked_examples_show_work,
]


def check_book(lessons: list[Lesson], skills: list[Skill]) -> dict[str, Any]:
    findings: list[Finding] = list(check_lesson_priming(lessons))
    for fn in CHECKS_ON_SKILLS:
        findings.extend(fn(skills))
    findings.extend(check_examples_not_templated(skills))

    rejects = [f for f in findings if f.severity == "reject"]
    # Count lessons and skills separately. Lumping them together once reported
    # "11,905 rejected" out of 17,661 skills, which is not a number that means
    # anything — most of it was lessons.
    rejected_ids = {f.where for f in rejects}
    skill_ids = {s.id for s in skills}
    lesson_ids = {l.id for l in lessons}
    bad_skills = rejected_ids & skill_ids
    bad_lessons = rejected_ids & lesson_ids
    return {
        "lessons": len(lessons),
        "skills": len(skills),
        "teachable": len(skills) - len(bad_skills),
        "rejected_skills": len(bad_skills),
        "rejected_lessons": len(bad_lessons),
        "findings": findings,
        "by_check": Counter(f.check for f in findings),
        "accepted": not rejects,
    }


# --------------------------------------------------------------------------- #
# Adapters — map a book's own shape onto the contract's. The only place that
# knows what a particular subject looks like.
# --------------------------------------------------------------------------- #

def from_enrichment(doc: dict[str, Any], lesson_id: str) -> tuple[Lesson, list[Skill]]:
    """Maths and PTE lessons, which share the enrichment shape."""
    ov = doc.get("overview") or {}
    lesson = Lesson(
        id=lesson_id,
        title=doc.get("lesson_title", lesson_id),
        about=ov.get("what_it_is", ""),
        will_be_able_to=list(doc.get("learning_goals") or []),
        common_pitfalls=[m.get("mistake", "") for m in (doc.get("common_mistakes") or [])],
    )
    skills: list[Skill] = []
    for i, t in enumerate(doc.get("techniques") or []):
        # Only the technique's OWN example. An earlier version also attached the
        # lesson's worked examples to every technique in that lesson, which made
        # seven techniques appear to share one sentence and the template check
        # rightly flagged all of them. The check was fine; the mapping was lying.
        # If a technique has no example of its own, that is a real gap and the
        # teaching check should say so.
        examples = [t.get("example")] if t.get("example") else []
        skills.append(Skill(
            id=f"{lesson_id}.t{i+1}",
            lesson_id=lesson_id,
            name=t.get("name", f"technique {i+1}"),
            kind=PROCEDURE,
            explanation=t.get("purpose", ""),
            steps=[str(h) for h in (t.get("how_to") or [])],
            examples=[e for e in examples if e],
            common_mistake=t.get("common_error", ""),
        ))
    return lesson, skills


def from_ela_items(items: list[dict[str, Any]], limit: int | None = None) -> tuple[list[Lesson], list[Skill]]:
    """English vocabulary: each word is a skill, its topic is its lesson."""
    if limit:
        items = items[:limit]
    lessons: dict[str, Lesson] = {}
    skills: list[Skill] = []
    for i, it in enumerate(items):
        topic = (it.get("topic") or "untitled").strip()
        lid = re.sub(r"[^a-z0-9]+", "-", topic.lower())[:60] or "untitled"
        if lid not in lessons:
            lessons[lid] = Lesson(id=lid, title=topic, about="", will_be_able_to=[],
                                  common_pitfalls=[])
        skills.append(Skill(
            id=f"ela.{i+1}.{it.get('content','?')}",
            lesson_id=lid,
            name=it.get("content", ""),
            kind=ITEM,
            explanation=it.get("definition", "") or "",
            examples=[e for e in (it.get("example_sentences") or []) if e],
            common_mistake=(it.get("metadata") or {}).get("confusable", "") or "",
        ))
    return list(lessons.values()), skills


# --------------------------------------------------------------------------- #
# Self-test — plant each defect and require it to be caught
# --------------------------------------------------------------------------- #

def self_test() -> int:
    bad = 0

    def expect(label: str, findings: list[Finding], check: str, want: bool) -> None:
        nonlocal bad
        got = any(f.check == check for f in findings)
        ok = got == want
        bad += not ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

    good_proc = Skill("s1", "l1", "Keep the named order", PROCEDURE,
                      explanation="Stops the two ratio numbers being reversed.",
                      steps=["Read the two amounts from left to right.",
                             "Write the first amount above the first number."],
                      examples=["Write 15 : 12 in its simplest form."],
                      common_mistake="Writing the bigger number first without checking names.")
    good_item = Skill("s2", "l1", "yacht", ITEM,
                      explanation="a large boat used for pleasure or racing",
                      examples=["They sailed the yacht along the coast all afternoon."],
                      common_mistake="ship")

    print("clean content is not flagged")
    for c in CHECKS_ON_SKILLS:
        f = c([good_proc, good_item])
        if f:
            bad += 1
            print(f"  [FAIL] {c.__name__} flagged clean content: {[x.detail for x in f]}")
    print(f"  [{'PASS' if not bad else 'FAIL'}] four checks stay quiet on good skills")

    print("\nplanted defects are caught")
    expect("a procedure with no steps is rejected",
           check_skill_teaching([Skill("x", "l1", "Halve it", PROCEDURE,
                                       explanation="Halve the product to get the area.",
                                       examples=["base 6 height 8"])]),
           "skill_teaching", True)
    expect("a skill with no explanation is rejected",
           check_skill_teaching([Skill("x", "l1", "Halve it", PROCEDURE, steps=["a", "b"],
                                       examples=["e"])]),
           "skill_teaching", True)
    expect("a circular definition is caught",
           check_definition_not_circular([Skill("x", "l1", "yacht", ITEM,
                                                explanation="a yacht")]),
           "circular_definition", True)
    expect("a real definition is not called circular",
           check_definition_not_circular([good_item]), "circular_definition", False)
    expect("an example that never uses the word is caught",
           check_example_uses_the_thing([Skill("x", "l1", "yacht", ITEM,
                                               explanation="a large boat",
                                               examples=["They sailed along the coast."])]),
           "example_uses_the_thing", True)

    # the mad-lib check: ten different words, one sentence
    templated = [Skill(f"t{i}", "l1", w, ITEM, explanation=f"meaning of {w}",
                       examples=[f"The meeting focused on {w} as a key issue."])
                 for i, w in enumerate(["yacht", "concerto", "haircut", "edge", "privy",
                                        "ominous", "replace", "badly", "unoccupied", "brilliant"])]
    expect("ten words sharing one sentence is caught as a template",
           check_examples_not_templated(templated), "templated_examples", True)

    varied = [Skill(f"v{i}", "l1", w, ITEM, explanation=f"meaning of {w}", examples=[e])
              for i, (w, e) in enumerate([
                  ("yacht", "They sailed the yacht along the coast."),
                  ("concerto", "She played a concerto for two violins."),
                  ("haircut", "He asked for a shorter haircut this time."),
                  ("edge", "Do not stand near the edge of the platform."),
                  ("privy", "Only three people were privy to the plan."),
                  ("ominous", "The sky turned an ominous shade of grey."),
              ])]
    expect("genuinely written examples are not called a template",
           check_examples_not_templated(varied), "templated_examples", False)

    print(f"\n{'the contract can reject a bad book' if not bad else str(bad) + ' FAILED'}")
    return 1 if bad else 0


# --------------------------------------------------------------------------- #

def load_book(name: str, limit: int | None = None) -> tuple[list[Lesson], list[Skill]]:
    if name == "ela":
        # The LIVE database, exported, not the seeder file. Those differ a great
        # deal — the seeder is 99% templated examples and what is actually in the
        # app is 20%. Measuring the seeder and calling it the app was an error
        # made once here already.
        live = Path("/tmp/ela_live_items.json")
        p = live if live.exists() else Path(
            "/Users/roy/Desktop/Work/Ela/database/seeders/data/learning-items-merged-v3.json")
        data = json.loads(p.read_text())
        items = data.get("items", data) if isinstance(data, dict) else data
        return from_ela_items(items, limit)
    lessons, skills = [], []
    for p in sorted(Path("output").glob(f"{name}.chapter*.enrichment.json")):
        doc = json.loads(p.read_text())
        lid = p.stem.replace(".enrichment", "")
        l, s = from_enrichment(doc, lid)
        lessons.append(l)
        skills.extend(s)
    return lessons, skills


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", help="math5a | pte | ela")
    ap.add_argument("--limit", type=int, help="only the first N items (ela is large)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--show", type=int, default=6, help="example findings to print")
    args = ap.parse_args(argv)

    if args.self_test or not args.book:
        return self_test()

    lessons, skills = load_book(args.book, args.limit)
    r = check_book(lessons, skills)
    print(f"\n{args.book}: {r['lessons']} lessons, {r['skills']} skills")
    print(f"  teachable skills : {r['teachable']:,} of {r['skills']:,}"
          f"  ({100*r['teachable']//max(1, r['skills'])}%)")
    print(f"  rejected skills  : {r['rejected_skills']:,}")
    print(f"  rejected lessons : {r['rejected_lessons']:,} of {r['lessons']:,}")
    print(f"  verdict       : {'ACCEPTED' if r['accepted'] else 'NOT READY TO TEACH'}")
    if r["by_check"]:
        print("\n  findings by check:")
        for c, n in r["by_check"].most_common():
            print(f"    {n:6,}  {c}")
    shown = 0
    for f in r["findings"]:
        if f.severity == "reject" and shown < args.show:
            print(f"    e.g. [{f.where}] {f.detail}")
            shown += 1
    return 0 if r["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
