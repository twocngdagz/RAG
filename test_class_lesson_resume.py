"""A chapter of nine concepts that stops at the fifth resumes at the fifth.

The sentence B20.1 states, tested as a story rather than as a flag: a chapter is
run, it dies in the middle, it is run again, and the four concepts that finished
are never asked for a second time. That is not a resume feature — it is the same
rule that stops a chapter run twice from duplicating anything: a concept with a
class lesson is not re-run unless somebody asks for it.

Two ways of stopping, because they fail differently. A concept that keeps coming
back wrong exhausts its attempts and the chapter stops on it; a person closing the
laptop kills the process where it stands. Neither may cost the concepts already
done, which is why the file is written after every one of them.

    python test_class_lesson_resume.py
"""
from __future__ import annotations

import copy
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

import run_class_lessons as R

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


SLUG = "math5a"
CHAPTER = 2
# Nine, the number the batch's own sentence names.
KEYS = [f"{SLUG}:ch{CHAPTER:02d}:concept-{n}" for n in range(1, 10)]

MANIFEST = {
    "manifest_schema_version": "lesson.export_manifest.v2",
    "approved": True,
    "authored_by": "test",
    "lesson": {"stable_key": f"{SLUG}:ch{CHAPTER:02d}", "title": "CHAPTER TWO", "domain": "math"},
    "concepts": [{"stable_key": key, "statement": f"STATEMENT FOR {key}."} for key in KEYS],
}

MATERIAL = {
    "schema_version": "pte_lesson_enrichment.v1",
    "lesson_title": "CHAPTER TWO",
    "source_label": f"{SLUG}:ch{CHAPTER:02d}",
    "overview": {"what_it_is": "WHAT THE CHAPTER IS"},
    "learning_goals": ["CHAPTER GOAL"],
    "core_method": {"name": "CHAPTER METHOD", "summary": "SUMMARY",
                    "steps": [{"step": "STEP", "detail": "DETAIL"}]},
    "techniques": [{"name": "MATERIAL TECHNIQUE", "purpose": "PURPOSE", "how_to": ["HOW TO"],
                    "example": "EXAMPLE", "why_it_matters": "WHY", "common_error": "ERROR"}],
    "worked_examples": [{"title": "MATERIAL WORKED", "input": "INPUT", "decoding": "DECODING",
                         "plan": "PLAN", "model_answer": "ANSWER",
                         "annotations": [{"part": "PART", "comment": "COMMENT"}]}],
    "mastery_checklist": ["CHECK"],
}


def lesson_for(key: str, *, run: int = 1) -> dict:
    return {
        "schema_version": "class_lesson.v1",
        "concept_key": key,
        "concept_statement": f"STATEMENT FOR {key}.",
        "goal": f"GOAL FOR {key}.",
        "techniques": [{
            "name": f"TECHNIQUE {run} FOR {key}",
            "purpose": "PURPOSE", "example": "EXAMPLE", "why_it_matters": "WHY",
            "common_error": "COMMON ERROR",
            "steps": [{"step": "STEP A", "detail": "DETAIL A"},
                      {"step": "STEP B", "detail": "DETAIL B"}],
        }],
        "worked_examples": [
            {"title": f"WORKED {run}{letter} FOR {key}", "input": "INPUT", "decoding": "DECODING",
             "plan": "PLAN", "model_answer": "ANSWER",
             "annotations": [{"part": "PART", "comment": "COMMENT"}]}
            for letter in ("A", "B")
        ],
    }


class FakeDriver:
    """One scripted turn per concept; an exception where the run is to die."""

    def __init__(self, dies_on: dict[str, BaseException] | None = None, run: int = 1):
        self.dies_on = dies_on or {}
        self.run = run
        self.asked: list[str] = []
        self.page = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def send_and_wait(self, url, prompt, timeout_s=0):
        keys = re.findall(r"^concept_key: (.+)$", prompt, flags=re.M)

        if len(keys) != 1:
            raise AssertionError(f"a request must name exactly one concept; this named {keys}")

        key = keys[0].strip()
        self.asked.append(key)

        if key in self.dies_on:
            raise self.dies_on[key]

        return json.dumps(lesson_for(key, run=self.run))

    def restriction_notice(self):
        return None


WORK = Path(tempfile.mkdtemp(prefix="class-lessons-resume-"))
MANIFEST_FILE = WORK / "manifest.json"
MATERIAL_FILE = WORK / "enrichment.json"
STORE = WORK / "class_lessons.json"
MANIFEST_FILE.write_text(json.dumps(MANIFEST), encoding="utf-8")
MATERIAL_FILE.write_text(json.dumps(MATERIAL), encoding="utf-8")


def run(driver: FakeDriver, *extra: str) -> int:
    args = R.parse_args([
        "run", "--book", SLUG, "--chapter", str(CHAPTER),
        "--manifest", str(MANIFEST_FILE), "--enrichment", str(MATERIAL_FILE),
        "--out", str(STORE), "--project-url", "https://x/project", "--cooldown", "0",
        *extra,
    ])

    with mock.patch.object(R, "ChatGPTDriver", lambda *a, **k: driver), \
            mock.patch.object(R, "scrape_reply_json", lambda page: None), \
            mock.patch.object(R.time, "sleep", lambda s: None):
        return R.cmd_run(args)


def stored() -> dict:
    return json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"concepts": {}}


def done() -> list[str]:
    return list(stored()["concepts"])


print("a chapter of nine that keeps failing at the fifth stops there")
driver = FakeDriver(dies_on={KEYS[4]: TimeoutError("no progress for 900s")})
code = run(driver, "--stop-on-error")
check("the run reports failure", code == 1, str(code))
check("the four before it are done", done() == KEYS[:4], str(done()))
check("the fifth was asked for, and re-asked, before the chapter stopped",
      driver.asked == KEYS[:4] + [KEYS[4]] * 3, str(driver.asked))
check("and the chapter stopped there rather than skipping ahead",
      KEYS[5] not in driver.asked)
check("what was written is on disk, not only in memory",
      all(stored()["concepts"][key]["class_lesson"]["concept_key"] == key for key in KEYS[:4]))

print("\nre-running resumes at the fifth and never re-runs the four completed")
completed = copy.deepcopy({key: stored()["concepts"][key] for key in KEYS[:4]})
driver = FakeDriver(dies_on={KEYS[6]: KeyboardInterrupt()})
interrupted = False

try:
    run(driver)
except KeyboardInterrupt:
    interrupted = True

check("it asked only for the concepts that had no lesson",
      driver.asked == KEYS[4:7], str(driver.asked))
check("none of the four completed was asked again",
      not set(driver.asked) & set(KEYS[:4]), str(driver.asked))
check("a person closing the laptop stops the run where it stands", interrupted)

print("\nand an interruption costs only the concept it was on")
check("the fifth and sixth survived the interrupt", done() == KEYS[:6], str(done()))
check("the four from the first run are byte-identical",
      {key: stored()["concepts"][key] for key in KEYS[:4]} == completed)
check("the file left behind is whole, not half-written",
      json.loads(STORE.read_text(encoding="utf-8"))["schema_version"] == R.STORE_SCHEMA_VERSION)

print("\nthe next run finishes the chapter, asking only for what is left")
before = copy.deepcopy(stored()["concepts"])
driver = FakeDriver()
code = run(driver)
check("the run succeeded", code == 0, str(code))
check("it asked only for the seventh, eighth and ninth", driver.asked == KEYS[6:], str(driver.asked))
check("every concept now has a class lesson", done() == KEYS, str(done()))
check("one lesson per concept, no duplicates", len(stored()["concepts"]) == 9)
check("each was generated by exactly one run",
      [entry["runs"] for entry in stored()["concepts"].values()] == [["4 added, 0 removed"]] * 9,
      str([entry["runs"] for entry in stored()["concepts"].values()]))
check("nothing already written was touched",
      {key: stored()["concepts"][key] for key in before} == before)

print("\na finished chapter run again sends no request at all")
after = STORE.read_bytes()
driver = FakeDriver()
code = run(driver)
check("no request was sent", driver.asked == [], str(driver.asked))
check("the run succeeded", code == 0, str(code))
check("the file did not move", STORE.read_bytes() == after)

print("\nand asking for another pass is deliberate, not automatic")
driver = FakeDriver(run=2)
code = run(driver, "--expand")
check("--expand asks for every concept again", driver.asked == KEYS, str(driver.asked))
check("the run succeeded", code == 0, str(code))
check("each lesson now records two runs",
      all(len(entry["runs"]) == 2 for entry in stored()["concepts"].values()))
check("and each grew rather than being replaced",
      all(len(entry["class_lesson"]["techniques"]) == 2
          and len(entry["class_lesson"]["worked_examples"]) == 4
          for entry in stored()["concepts"].values()))
check("still one lesson per concept", done() == KEYS, str(done()))

print("\none concept can be re-run on its own")
driver = FakeDriver(run=3)
code = run(driver, "--expand", "--concept", KEYS[2])
check("only that concept was asked", driver.asked == [KEYS[2]], str(driver.asked))
check("only that concept moved",
      len(stored()["concepts"][KEYS[2]]["runs"]) == 3
      and all(len(stored()["concepts"][key]["runs"]) == 2 for key in KEYS if key != KEYS[2]))

print("\nand a concept this lesson does not have is refused before any request is sent")
driver = FakeDriver()
try:
    run(driver, "--concept", f"{SLUG}:ch{CHAPTER:02d}:concept-ten")
    check("an unknown concept is refused", False, "it ran")
except R.RunRefused as error:
    check("an unknown concept is refused", "concept-ten" in str(error))
    check("and nothing was sent", driver.asked == [], str(driver.asked))

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "an interrupted chapter resumes where it stopped")
raise SystemExit(1 if fails else 0)
