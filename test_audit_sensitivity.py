"""Regression test for the enrichment fact audit.

The audit exists to catch invented facts, and twice it has quietly failed to do
that: once by truncating the guide evidence it claimed to be using, once by
manufacturing a stronger claim than the lesson actually made. Both times it kept
printing a confident report.

So the audit needs its own check. This plants claims whose truth we already know
against the real guide and asserts the verdicts. A run where everything comes
back clean is only meaningful if this test passes on the same day.

    python test_audit_sensitivity.py

Costs a handful of model calls (one per task_type below).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import audit_enrichment_facts as a  # noqa: E402

SUPPORTED, CONTRADICTED = "SUPPORTED", "CONTRADICTED"

# (task_type, [(expected_verdict, kind, claim_text), ...])
# Every claim is checkable against the real Score Guide. False ones invert a
# figure or add a trait the guide's enumeration excludes.
CASES: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "summarize_spoken_text_and_highlight_correct_summary",
        [
            # Guide p.42: Form 2 = 50-70 words; 0 = under 40 or over 100.
            (SUPPORTED, "format_fact",
             "Summarize spoken text length: the summary should be 50-70 words."),
            (CONTRADICTED, "critical_rule",
             "A summary of 35 words still scores 2 for Form."),
            # Traits are Content/Form/Grammar/Vocabulary/Spelling — a closed list.
        ],
    ),
    (
        "write_essay",
        [
            # Guide pp.34-39.
            (SUPPORTED, "scoring_factor",
             "Scoring for this task takes into account Spelling: correct spelling "
             "of the words used."),
            (CONTRADICTED, "format_fact",
             "Essay length: the essay must be 500-600 words."),
        ],
    ),
]


# Borrowing an official trait name that the guide does not list for the task.
# Checked in code, not by the judge — the judge would not treat the guide's
# "Traits scored" list as closed, and forcing it via the prompt destabilised
# every other verdict.
TRAIT_CASES: list[tuple[str, str, bool]] = [
    # (task_type, scoring factor name, should_be_flagged)
    ("summarize_spoken_text_and_highlight_correct_summary", "Pronunciation", True),
    ("write_essay", "Oral Fluency", True),
    ("write_essay", "Spelling", False),        # genuinely scored on Write Essay
    ("write_essay", "Main-idea coverage", False),  # teaching paraphrase, not official
]


# The lesson must STATE the word range the guide gates Form on. Lesson 15 shipped
# without any number at all, so a check that only compares stated numbers would
# have passed it — the bug was an absence, not a wrong value.
RANGE_CASES: list[tuple[str, dict, bool]] = [
    ("summarize_spoken_text_and_highlight_correct_summary",
     {"overview": {"critical_rules": ["Verify content, word-count compliance, and spelling."]}},
     True),   # names no range -> must flag
    ("summarize_spoken_text_and_highlight_correct_summary",
     {"overview": {"critical_rules": ["Keep the summary between 50 and 70 words."]}},
     False),
    ("write_essay",
     {"overview": {"format_facts": [{"label": "Target length",
                                     "value": "the required 200-to-300-word range"}]}},
     False),  # hyphenated wording still counts
    ("summarize_written_text",
     {"overview": {"critical_rules": ["One sentence only."]}},
     False),  # guide sets no Form word range here -> must stay silent
]


def check_ranges(pages) -> list[str]:
    failures = []
    print("\nword range (deterministic)")
    for task_type, doc, want_flag in RANGE_CASES:
        evidence, _, matched = a.guide_text_for(task_type, pages, rubric_only=True)
        if not matched:
            failures.append(f"{task_type}: guide section not located")
            continue
        flagged = bool(a.check_word_range(doc, evidence))
        ok = flagged == want_flag
        if not ok:
            failures.append(f"{task_type}: word-range case should"
                            f"{'' if want_flag else ' not'} be flagged")
        print(f"  [{'PASS' if ok else 'FAIL'}] {task_type[:34]:36} "
              f"flagged={flagged} want={want_flag}")
    return failures


def check_traits(pages) -> list[str]:
    failures = []
    print("\ntrait vocabulary (deterministic)")
    for task_type, factor, want_flag in TRAIT_CASES:
        evidence, _, matched = a.guide_text_for(task_type, pages, rubric_only=True)
        if not matched:
            failures.append(f"{task_type}: guide section not located")
            continue
        doc = {"overview": {"scoring_factors": [{"name": factor, "what_it_measures": "x"}]}}
        flagged = bool(a.check_trait_vocabulary(doc, evidence))
        ok = flagged == want_flag
        if not ok:
            failures.append(
                f"{task_type}: '{factor}' should{'' if want_flag else ' not'} be flagged"
            )
        print(f"  [{'PASS' if ok else 'FAIL'}] {task_type[:34]:36} {factor:20} "
              f"flagged={flagged} want={want_flag}")
    return failures


def main() -> int:
    pages = a.load_guide_pages(a.DEFAULT_GUIDE)
    failures: list[str] = []
    checked = 0

    # The judge is measured-unreliable on numeric contradictions: at temperature 0
    # it returned NOT_IN_GUIDE for a plainly contradicted word range in 3 of 4
    # runs, on a different case each time. Those verdicts are reported but do not
    # decide the exit code — check_word_range covers the same error in code and
    # caught it 5/5. Everything the judge is relied on for stays a hard failure.
    advisory: list[str] = []

    for task_type, cases in CASES:
        evidence, guide_pages, matched = a.guide_text_for(task_type, pages)
        if not matched:
            failures.append(f"{task_type}: could not locate the guide section")
            continue

        claims = [{"kind": kind, "text": text} for _, kind, text in cases]
        verdicts = a.judge(claims, evidence, model=a.DEFAULT_MODEL)

        print(f"\n{task_type}  (guide pp.{guide_pages})")
        for (want, _kind, text), got in zip(cases, verdicts):
            checked += 1
            verdict = got.get("verdict")
            ok = verdict == want
            if not ok:
                bucket = advisory if want == CONTRADICTED else failures
                bucket.append(f"{task_type}: want {want}, got {verdict} — {text[:70]}")
            print(f"  [{'PASS' if ok else 'FAIL'}] want={want:13} got={str(verdict):13} | {text[:58]}")
            if got.get("quote"):
                print(f"         guide: {got['quote'][:84]}")

    failures.extend(check_traits(pages))
    checked += len(TRAIT_CASES)
    failures.extend(check_ranges(pages))
    checked += len(RANGE_CASES)

    print("\n" + "=" * 60)
    if advisory:
        print(f"{len(advisory)} advisory (judge nondeterminism, covered in code):")
        for x in advisory:
            print("  ~", x)
        print()
    if failures:
        print(f"{len(failures)} of {checked} checks FAILED — the audit is not reliable:")
        for f in failures:
            print("  -", f)
        print("\nA clean audit report cannot be trusted while this test fails.")
        return 1
    print(f"All {checked} checks passed — the audit can still detect planted errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
