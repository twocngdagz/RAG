"""How much can the PTE scores be trusted? Measured, so the disclosure can stop hedging.

The UI now tells a learner their essay was "scored by AI" and that "the same
response may not score the same twice". That second claim was written from
caution, not from evidence. This measures it, and measures the rest of what can
be established without a bank of human-marked responses:

  DISCRIMINATION  Can it rank known-quality responses correctly? A grader that
                  puts a repetitive essay level with a developed one is not
                  measuring writing, whatever numbers it prints.
  PLANTED DEFECTS Five misspellings and four invented chart figures were put
                  there on purpose, so "did it notice?" has an exact answer.
  GATING          Off-topic essays and two-sentence summaries must score 0. This
                  is the one part of the rubric with a defined right answer.
  REPEATABILITY   Score identical text N times and report the spread. This is the
                  number the disclosure should be quoting.

What this deliberately does NOT claim: that any score is *correct*. There are no
human-marked responses here, so absolute accuracy is unmeasurable and is not
asserted. See grader_agreement_corpus.py, where the authored judgements live.

Costs real model calls — NOT part of the regression.

    python test_grader_agreement.py                 # all three graders
    python test_grader_agreement.py --task essay --runs 5
"""
from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import describe_image_feedback as dif
import essay_feedback as ef
import grader_agreement_corpus as C
import swt_feedback as swt

failures: list[str] = []
advisory: list[str] = []
measurements: dict[str, Any] = {}
notes: list[str] = []   # measured context that is not a pass/fail claim


def hard(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        failures.append(label)


def soft(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'warn'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        advisory.append(label)


def run_all(jobs: dict[str, Callable[[], Any]], workers: int = 4) -> dict[str, Any]:
    """Fan the model calls out — they are independent and each takes many seconds."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {k: pool.submit(fn) for k, fn in jobs.items()}
        return {k: f.result() for k, f in futures.items()}


def spread(values: list[float]) -> dict[str, float]:
    return {
        "runs": len(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
        "mean": round(statistics.mean(values), 2),
        "stdev": round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
    }


def trait_map(result: dict[str, Any]) -> dict[str, int]:
    return {t["name"]: t["score"] for t in result.get("traits", [])}


# --------------------------------------------------------------------------- #
# Corpus integrity — free, and it must hold before any model call is worth making
# --------------------------------------------------------------------------- #

def check_corpus(item: dict[str, Any]) -> None:
    print("corpus integrity (code only — the ladder must not be confounded)")
    forms = {e["key"]: ef.form_score(e["text"])[0] for e in C.ESSAYS}
    hard("every essay scores Form 2, so Form cannot explain the ranking",
         set(forms.values()) == {2}, str(forms))
    hard("all five misspellings are actually planted in the middling essay",
         all(m in C.ESSAY_MIDDLING for m in C.PLANTED_MISSPELLINGS))
    hard("no planted misspelling leaked into the strong essay",
         not any(m in C.ESSAY_STRONG for m in C.PLANTED_MISSPELLINGS))

    swt_forms = {s["key"]: swt.form_score(s["text"])[0] for s in C.SUMMARIES}
    hard("the two-sentence summary breaks Form, the others do not",
         swt_forms["two_sentences"] == 0 and swt_forms["good"] == 1, str(swt_forms))

    # This one needs no model at all: the numeric check is pure code.
    wrong = next(d for d in C.DESCRIPTIONS if d["key"] == "wrong_numbers")
    got = dif.check_numbers(wrong["text"], item)["unsupported"]
    hard("code catches all four invented chart figures",
         sorted(got) == sorted(C.PLANTED_WRONG_NUMBERS), f"got {got}")
    for clean in ("full", "vague"):
        d = next(x for x in C.DESCRIPTIONS if x["key"] == clean)
        hard(f"...and flags nothing in the {clean} description",
             dif.check_numbers(d["text"], item)["unsupported"] == [], clean)


# --------------------------------------------------------------------------- #
# Write Essay
# --------------------------------------------------------------------------- #

def check_essay(model: str, runs: int) -> None:
    print(f"\nWrite Essay — {runs + 4} calls")
    jobs: dict[str, Callable[[], Any]] = {
        f"strong#{i}": (lambda i=i: ef.score_essay(C.ESSAY_PROMPT, C.ESSAY_STRONG, model=model))
        for i in range(runs)
    }
    for e in C.ESSAYS:
        if e["key"] != "strong":
            jobs[e["key"]] = lambda t=e["text"]: ef.score_essay(C.ESSAY_PROMPT, t, model=model)
    jobs["empty"] = lambda: ef.score_essay(C.ESSAY_PROMPT, C.ESSAY_PROBE_EMPTY["text"], model=model)
    r = run_all(jobs)

    totals = [r[f"strong#{i}"]["raw_total"] for i in range(runs)]
    strong = r["strong#0"]
    scores = {"strong": strong["raw_total"], "middling": r["middling"]["raw_total"],
              "weak": r["weak"]["raw_total"], "off_topic": r["off_topic"]["raw_total"],
              "fluent_but_empty": r["empty"]["raw_total"]}
    print(f"  scores /26: {scores}")

    print("\n  ranking known-quality essays")
    # Raw totals are only comparable between essays that differ on ONE dimension.
    # The strong, weak and empty essays are all mechanically clean, so their totals
    # can be ranked directly. The middling essay cannot join them: it carries five
    # planted misspellings that cost it Spelling and Vocabulary, which is a
    # different axis from how well it argues. Comparing its total against the
    # others' would be measuring the plant, not the grader — an earlier version of
    # this test did exactly that and passed only because the two happened to tie.
    hard("a developed essay beats a repetitive one", scores["strong"] > scores["weak"],
         f"strong={scores['strong']} weak={scores['weak']}")
    hard("the gap is a real gap, not a rounding difference",
         scores["strong"] - scores["weak"] >= 3, f"gap={scores['strong'] - scores['weak']}")
    hard("mechanically clean essays rank by argument quality",
         scores["strong"] > scores["weak"] > scores["fluent_but_empty"], str(scores))

    # The corpus levels describe argument quality, so the ladder is asserted on the
    # two traits that judge the argument. This is where the middling essay belongs.
    argument = {
        k: trait_map(res).get("content", 0) + trait_map(res).get("development_structure_coherence", 0)
        for k, res in (("strong", strong), ("middling", r["middling"]),
                       ("weak", r["weak"]), ("empty", r["empty"]))
    }
    print(f"    content + development, out of 12: {argument}")
    hard("the argument-trait ladder is monotonic across all four levels",
         argument["strong"] >= argument["middling"] >= argument["weak"] > argument["empty"],
         str(argument))

    print("\n  gating (the one rule with a defined right answer)")
    hard("an off-topic essay scores 0", scores["off_topic"] == 0, str(scores["off_topic"]))
    hard("...and says the gate was applied", r["off_topic"]["gating_applied"] is True)
    hard("an on-topic essay is not gated", strong["gating_applied"] is False)

    print("\n  planted misspellings")
    reported = " ".join(e.get("wrong", "") for e in r["middling"].get("errors", [])).lower()
    caught = [m for m in C.PLANTED_MISSPELLINGS if m.lower() in reported]
    print(f"    caught {len(caught)}/5: {caught}")
    hard("catches at least three of the five planted misspellings", len(caught) >= 3, str(caught))
    hard("and does not award full marks for spelling",
         trait_map(r["middling"]).get("spelling", 2) < ef.TRAIT_MAX["spelling"],
         str(trait_map(r["middling"]).get("spelling")))
    hard("while the clean strong essay keeps full spelling marks",
         trait_map(strong).get("spelling") == ef.TRAIT_MAX["spelling"],
         str(trait_map(strong).get("spelling")))

    print(f"\n  repeatability — identical text scored {runs} times")
    s = spread(totals)
    measurements["essay"] = {"scale": 26, "totals": totals, **s}
    print(f"    totals {totals} -> range {s['range']}/26, mean {s['mean']}, sd {s['stdev']}")
    per_trait = {}
    for name in ef.TRAIT_MAX:
        vals = [trait_map(r[f"strong#{i}"]).get(name, 0) for i in range(runs)]
        per_trait[name] = max(vals) - min(vals)
    measurements["essay"]["trait_range"] = per_trait
    print(f"    per-trait movement: { {k: v for k, v in per_trait.items() if v} or 'none' }")
    hard("the same essay does not swing wildly (range <= 6 of 26)", s["range"] <= 6, str(s))
    soft("scoring is tight (range <= 3 of 26)", s["range"] <= 3, str(s["range"]))
    hard("Form is identical every run — it is computed in code",
         per_trait["form"] == 0, str(per_trait["form"]))

    print("\n  fluency must not substitute for content")
    empty_traits = trait_map(r["empty"])
    empty_dsc = empty_traits.get("development_structure_coherence", 6)
    hard("an essay with no argument scores below one that has a thin argument",
         scores["fluent_but_empty"] < scores["weak"],
         f"empty={scores['fluent_but_empty']} weak={scores['weak']}")
    # The specific defect this trait was rewritten for: cohesive phrasing being
    # read as development. Scored directly, so a regression names itself.
    hard("...and is not credited with development it does not have",
         empty_dsc <= 3, f"development/structure/coherence = {empty_dsc}/6")
    soft("the separation is clear rather than marginal",
         scores["weak"] - scores["fluent_but_empty"] >= 2,
         f"gap={scores['weak'] - scores['fluent_but_empty']}")

    # Context, not a verdict. Form, Grammar, Vocabulary, Spelling and Linguistic
    # Range all reward fluent, well-formed, on-length prose whatever it argues, so
    # a contentless essay keeps a floor no grader fix can remove. That floor is
    # the rubric's, and the honest place to address it is how the score is
    # presented, not by teaching the rater to mark language it can see.
    mech = ["form", "grammar", "vocabulary_range", "spelling", "general_linguistic_range"]
    floor = sum(empty_traits.get(n, 0) for n in mech)
    notes.append(
        f"a contentless but fluent essay still scores {scores['fluent_but_empty']}/26 "
        f"({round(100 * scores['fluent_but_empty'] / 26)}%), of which {floor} comes from "
        f"language traits that do not look at content at all — a rubric floor, not a grader fault"
    )
    print(f"    language-only floor: {floor}/18 of a {scores['fluent_but_empty']}/26 total")


# --------------------------------------------------------------------------- #
# Summarize Written Text
# --------------------------------------------------------------------------- #

def check_swt(model: str, runs: int) -> None:
    print(f"\nSummarize Written Text — {runs + 3} calls")
    jobs: dict[str, Callable[[], Any]] = {
        f"good#{i}": (lambda i=i: swt.score_summary(C.SWT_PASSAGE, C.SUMMARIES[0]["text"], model=model))
        for i in range(runs)
    }
    for s in C.SUMMARIES[1:]:
        jobs[s["key"]] = lambda t=s["text"]: swt.score_summary(C.SWT_PASSAGE, t, model=model)
    r = run_all(jobs)

    totals = [r[f"good#{i}"]["raw_total"] for i in range(runs)]
    scores = {"good": r["good#0"]["raw_total"], "partial": r["partial"]["raw_total"],
              "two_sentences": r["two_sentences"]["raw_total"], "off_topic": r["off_topic"]["raw_total"]}
    print(f"  scores /9: {scores}")

    print("\n  ranking and gating")
    hard("a complete summary beats a partial one", scores["good"] >= scores["partial"], str(scores))
    # A summary that carries half the central claim scoring within a point of one
    # that carries all of it means Content is barely discriminating on this scale.
    soft("a partial summary is clearly separated, not just edged out",
         scores["good"] - scores["partial"] >= 2,
         f"good={scores['good']} partial={scores['partial']} — gap of "
         f"{scores['good'] - scores['partial']} of 9")
    hard("a two-sentence response scores 0 (Form rule)", scores["two_sentences"] == 0)
    hard("an off-topic summary scores 0", scores["off_topic"] == 0)
    hard("a good summary is not gated", r["good#0"]["gating_applied"] is False)

    print(f"\n  repeatability — identical text scored {runs} times")
    s = spread(totals)
    measurements["swt"] = {"scale": 9, "totals": totals, **s}
    print(f"    totals {totals} -> range {s['range']}/9, mean {s['mean']}, sd {s['stdev']}")
    hard("the same summary does not swing wildly (range <= 3 of 9)", s["range"] <= 3, str(s))
    soft("scoring is tight (range <= 1 of 9)", s["range"] <= 1, str(s["range"]))


# --------------------------------------------------------------------------- #
# Describe Image
# --------------------------------------------------------------------------- #

def check_describe_image(model: str, runs: int, item: dict[str, Any]) -> None:
    print(f"\nDescribe Image — {runs + 2} calls")
    jobs: dict[str, Callable[[], Any]] = {
        f"full#{i}": (lambda i=i: dif.score_response(item, C.DESCRIPTIONS[0]["text"], model=model))
        for i in range(runs)
    }
    for d in C.DESCRIPTIONS[1:]:
        jobs[d["key"]] = lambda t=d["text"]: dif.score_response(item, t, model=model)
    r = run_all(jobs)

    totals = [r[f"full#{i}"]["content_score"] for i in range(runs)]
    scores = {"full": r["full#0"]["content_score"], "vague": r["vague"]["content_score"],
              "wrong_numbers": r["wrong_numbers"]["content_score"]}
    print(f"  Content /6: {scores}")

    print("\n  ranking")
    hard("an accurate description beats a vague one", scores["full"] > scores["vague"], str(scores))
    hard("inventing every figure does not score as well as stating them correctly",
         scores["wrong_numbers"] < scores["full"], str(scores))

    print("\n  the code-side numeric check is carried through to the payload")
    hard("the invented figures are reported on the attempt",
         sorted(r["wrong_numbers"]["accuracy"]["unsupported"]) == sorted(C.PLANTED_WRONG_NUMBERS),
         str(r["wrong_numbers"]["accuracy"]["unsupported"]))
    hard("nothing is flagged on the accurate description",
         r["full#0"]["accuracy"]["unsupported"] == [])

    print(f"\n  repeatability — identical text scored {runs} times")
    s = spread(totals)
    measurements["describe_image"] = {"scale": 6, "totals": totals, **s}
    print(f"    Content {totals} -> range {s['range']}/6, mean {s['mean']}, sd {s['stdev']}")
    hard("the same description does not swing wildly (range <= 2 of 6)", s["range"] <= 2, str(s))
    soft("scoring is tight (range <= 1 of 6)", s["range"] <= 1, str(s["range"]))


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", default="all", choices=["all", "essay", "swt", "describe_image"])
    ap.add_argument("--runs", type=int, default=3, help="repeatability samples per grader")
    ap.add_argument("--model", default=ef.DEFAULT_MODEL)
    ap.add_argument("--json", help="write the measurements to this path")
    args = ap.parse_args(argv)

    path = Path("output/describe_image_items.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    bank = data.get("items", data) if isinstance(data, dict) else data
    item = next(i for i in bank if i["id"] == C.DESCRIBE_ITEM_ID)

    check_corpus(item)
    if args.task in ("all", "essay"):
        check_essay(args.model, args.runs)
    if args.task in ("all", "swt"):
        check_swt(args.model, args.runs)
    if args.task in ("all", "describe_image"):
        check_describe_image(args.model, args.runs, item)

    print("\n" + "=" * 66)
    print("MEASURED — what the score disclosure can honestly say:")
    for name, m in measurements.items():
        print(f"  {name:15} identical text, {m['runs']} runs: total moved {m['range']} "
              f"of {m['scale']} (mean {m['mean']}, sd {m['stdev']})")
    if not measurements:
        print("  (no repeatability measured for this task selection)")

    if notes:
        print("\nalso measured (context, not a verdict):")
        for n in notes:
            print(f"  · {n}")
    if advisory:
        print(f"\nadvisory ({len(advisory)}) — reported, does not decide the exit code:")
        for a in advisory:
            print(f"  · {a}")
    if args.json:
        Path(args.json).write_text(json.dumps(measurements, indent=2) + "\n")
        print(f"\nmeasurements -> {args.json}")

    if failures:
        print(f"\n{len(failures)} FAILED: {failures}")
        print("These scores are shown to learners as marks. They must not be shown while this fails.")
    else:
        print("\nthe graders rank, catch planted defects, gate correctly, and repeat within tolerance")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
