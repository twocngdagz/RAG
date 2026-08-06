"""The transform stage, run per concept, with a fake browser and no network.

The three sentences B20.1 is judged by, proven without sending a request:

  1. A concept with no class lesson gets one — and one REQUEST PER CONCEPT, not
     one per chapter, because a chapter in a single prompt is the thing this
     stage was split up to avoid.
  2. The same concept run again comes back expanded, with its previous content
     intact and VISIBLE IN THE PROMPT. A generator that cannot see what exists
     writes the same lesson twice.
  3. Nothing is deleted across runs. A reply that quietly drops half the lesson
     cannot take it away: the merge starts from what is stored.

And the run that adds nothing is refused rather than recorded, because a pass is
meant to expand the lesson and a pass that repeats it is a wasted request.

    python test_class_lesson_runner.py
"""
from __future__ import annotations

import copy
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

import class_lesson_contract as contract
import run_class_lessons as R

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


SLUG = "math5a"
CHAPTER = 1
KEYS = [f"{SLUG}:ch{CHAPTER:02d}:concept-{n}" for n in ("one", "two", "three")]

# Shouted nonsense on purpose: a fixture that read like teaching would be
# teaching this batch wrote, and this batch writes none.
MANIFEST = {
    "manifest_schema_version": "lesson.export_manifest.v2",
    "approved": True,
    "authored_by": "test",
    "lesson": {"stable_key": f"{SLUG}:ch{CHAPTER:02d}", "title": "CHAPTER ONE", "domain": "math"},
    "concepts": [
        {"stable_key": key, "statement": f"STATEMENT FOR {key.rsplit(':', 1)[1].upper()}."}
        for key in KEYS
    ],
}

MATERIAL = {
    "schema_version": "pte_lesson_enrichment.v1",
    "lesson_title": "CHAPTER ONE",
    "source_label": f"{SLUG}:ch{CHAPTER:02d}",
    "overview": {"what_it_is": "WHAT THE CHAPTER IS", "critical_rules": ["RULE ONE"]},
    "learning_goals": ["CHAPTER GOAL ONE"],
    "core_method": {"name": "CHAPTER METHOD", "summary": "SUMMARY",
                    "steps": [{"step": "METHOD STEP", "detail": "METHOD DETAIL"}]},
    "techniques": [{"name": "MATERIAL TECHNIQUE", "purpose": "PURPOSE",
                    "how_to": ["HOW TO ONE"], "example": "EXAMPLE",
                    "why_it_matters": "WHY", "common_error": "ERROR"}],
    "worked_examples": [{"title": "MATERIAL WORKED", "input": "INPUT", "decoding": "DECODING",
                         "plan": "PLAN", "model_answer": "ANSWER",
                         "annotations": [{"part": "PART", "comment": "COMMENT"}]}],
    "common_mistakes": [{"mistake": "MISTAKE", "why_it_hurts": "HURTS", "fix": "FIX"}],
    "mastery_checklist": ["CHECK ONE"],
}


def technique(name: str) -> dict:
    return {
        "name": name,
        "purpose": f"PURPOSE OF {name}",
        "steps": [{"step": "STEP A", "detail": "DETAIL A"}, {"step": "STEP B", "detail": "DETAIL B"}],
        "example": f"EXAMPLE OF {name}",
        "why_it_matters": "WHY IT MATTERS",
        "common_error": "THE COMMON ERROR",
    }


def worked(title: str) -> dict:
    return {
        "title": title,
        "input": f"INPUT OF {title}",
        "decoding": "WHAT IT ASKS",
        "plan": "WHICH TECHNIQUE AND WHY",
        "model_answer": "THE WORKING, THEN THE ANSWER",
        "annotations": [{"part": "THE STEP", "comment": "WHY THAT STEP"}],
    }


def lesson_for(key: str, *, techniques: list[str], examples: list[str], goal: str = "") -> dict:
    statement = next(c["statement"] for c in MANIFEST["concepts"] if c["stable_key"] == key)
    return {
        "schema_version": contract.SCHEMA_VERSION,
        "concept_key": key,
        "concept_statement": statement,
        "goal": goal or f"GOAL FOR {key}.",
        "techniques": [technique(name) for name in techniques],
        "worked_examples": [worked(title) for title in examples],
    }


class FakeDriver:
    """Stands in for the browser: one scripted reply per concept, per turn.

    It reads the concept out of the prompt rather than counting sends, which is
    also the assertion that every request names exactly one concept.
    """

    def __init__(self, replies: dict[str, list]):
        self.replies = {key: list(value) for key, value in replies.items()}
        self.prompts: list[tuple[str, str]] = []   # (concept key, prompt)
        self.page = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    @property
    def asked(self) -> list[str]:
        return [key for key, _ in self.prompts]

    def prompt_for(self, key: str) -> str:
        return next(prompt for asked, prompt in self.prompts if asked == key)

    def send_and_wait(self, url, prompt, timeout_s=0):
        keys = re.findall(r"^concept_key: (.+)$", prompt, flags=re.M)

        if len(keys) != 1:
            raise AssertionError(f"a request must name exactly one concept; this named {keys}")

        key = keys[0].strip()
        self.prompts.append((key, prompt))
        queued = self.replies.get(key) or []
        answer = queued.pop(0) if len(queued) > 1 else (queued[0] if queued else {})

        if isinstance(answer, BaseException):
            raise answer

        return json.dumps(answer)

    def restriction_notice(self):
        return None


WORK = Path(tempfile.mkdtemp(prefix="class-lessons-"))
MANIFEST_FILE = WORK / "manifest.json"
MATERIAL_FILE = WORK / "enrichment.json"
STORE = WORK / "class_lessons.json"
MANIFEST_FILE.write_text(json.dumps(MANIFEST), encoding="utf-8")
MATERIAL_FILE.write_text(json.dumps(MATERIAL), encoding="utf-8")


def run(replies: dict[str, list], *extra: str) -> tuple[int, FakeDriver, list[int]]:
    sleeps: list[int] = []
    args = R.parse_args([
        "run", "--book", SLUG, "--chapter", str(CHAPTER),
        "--manifest", str(MANIFEST_FILE), "--enrichment", str(MATERIAL_FILE),
        "--out", str(STORE), "--project-url", "https://x/project", "--cooldown", "0",
        *extra,
    ])
    driver = FakeDriver(replies)

    with mock.patch.object(R, "ChatGPTDriver", lambda *a, **k: driver), \
            mock.patch.object(R, "scrape_reply_json", lambda page: None), \
            mock.patch.object(R.time, "sleep", lambda s: sleeps.append(int(s))):
        code = R.cmd_run(args)

    return code, driver, sleeps


def stored() -> dict:
    return json.loads(STORE.read_text(encoding="utf-8"))


print("a concept with no class lesson gets one — one request per concept")
first = {key: [lesson_for(key, techniques=["TECHNIQUE ONE"], examples=["WORKED ONE", "WORKED TWO"])]
         for key in KEYS}
code, driver, sleeps = run(first)
check("the run succeeded", code == 0, str(code))
check("one request per concept, not one per chapter", driver.asked == KEYS, str(driver.asked))
check("every concept has a class lesson", sorted(stored()["concepts"]) == sorted(KEYS))
check("each lesson is filed under the concept it is for",
      all(entry["class_lesson"]["concept_key"] == key
          for key, entry in stored()["concepts"].items()))
check("the first run is all addition, and takes nothing away",
      [entry["runs"] for entry in stored()["concepts"].values()]
      == [["4 added, 0 removed"]] * 3,
      str([entry["runs"] for entry in stored()["concepts"].values()]))
check("nothing waited, because nothing was paced", sleeps == [], str(sleeps))

print("\nthe first request says there is nothing yet, and carries the chapter's material")
check("it says the concept has no lesson yet",
      "none yet — this is the first run" in driver.prompt_for(KEYS[0]))
check("it carries the chapter's enriched material",
      "MATERIAL TECHNIQUE" in driver.prompt_for(KEYS[0]))
check("it names the other concepts so they are not taught here",
      KEYS[1] in driver.prompt_for(KEYS[0]) and KEYS[2] in driver.prompt_for(KEYS[0]))
check("and it hands over the contract itself",
      contract.contract_text() in driver.prompt_for(KEYS[0]))

print("\nrunning the chapter again asks for nothing: a lesson that exists is not re-run")
before = STORE.read_bytes()
code, driver, _ = run(first)
check("no request was sent", driver.asked == [], str(driver.asked))
check("the run succeeded", code == 0, str(code))
check("no concept's lesson was duplicated", len(stored()["concepts"]) == 3)
check("the file did not move", STORE.read_bytes() == before)

print("\nrun two sends run one's lesson back, and expands it")
expanded = {
    key: [lesson_for(key, techniques=["TECHNIQUE ONE", "TECHNIQUE TWO"],
                     examples=["WORKED ONE", "WORKED TWO", "WORKED THREE"])]
    for key in KEYS
}
was = copy.deepcopy(stored()["concepts"][KEYS[0]]["class_lesson"])
code, driver, _ = run(expanded, "--expand")
prompt = driver.prompt_for(KEYS[0])
check("the run succeeded", code == 0, str(code))
check("every concept was asked again", driver.asked == KEYS, str(driver.asked))
check("the prompt contains the lesson run one produced",
      "TECHNIQUE ONE" in prompt and "WORKED TWO" in prompt and was["goal"] in prompt)
check("and says it exists and must not be deleted",
      "This already exists and has been kept" in prompt
      and "Nothing here may be deleted" in prompt)
check("the prompt no longer says this is the first run",
      "none yet — this is the first run" not in prompt)

now = stored()["concepts"][KEYS[0]]["class_lesson"]
check("the lesson came back expanded",
      [t["name"] for t in now["techniques"]] == ["TECHNIQUE ONE", "TECHNIQUE TWO"],
      str([t["name"] for t in now["techniques"]]))
check("its worked examples grew too",
      [w["title"] for w in now["worked_examples"]] == ["WORKED ONE", "WORKED TWO", "WORKED THREE"])
check("nothing run one produced was deleted",
      set(contract.elements(was)) <= set(contract.elements(now)),
      str(sorted(set(contract.elements(was)) - set(contract.elements(now)))))
check("and the run says so, in the enrichment rule's own words",
      stored()["concepts"][KEYS[0]]["runs"] == ["4 added, 0 removed", "2 added, 0 removed"],
      str(stored()["concepts"][KEYS[0]]["runs"]))
check("repeating what exists did not duplicate it",
      len(now["techniques"]) == 2 and len(now["worked_examples"]) == 3)

print("\na reply that drops what was there cannot take it away")
was = copy.deepcopy(stored()["concepts"][KEYS[0]]["class_lesson"])
forgetful = {
    key: [lesson_for(key, techniques=["TECHNIQUE FOUR"], examples=["WORKED FOUR", "WORKED FIVE"],
                     goal="A GOAL THIS RUN WROTE INSTEAD.")]
    for key in KEYS
}
code, driver, _ = run(forgetful, "--expand")
now = stored()["concepts"][KEYS[0]]["class_lesson"]
check("the run succeeded", code == 0, str(code))
check("everything the lesson had, it still has",
      set(contract.elements(was)) <= set(contract.elements(now)),
      str(sorted(set(contract.elements(was)) - set(contract.elements(now)))))
check("the dropped techniques are still taught",
      [t["name"] for t in now["techniques"]] == ["TECHNIQUE ONE", "TECHNIQUE TWO", "TECHNIQUE FOUR"],
      str([t["name"] for t in now["techniques"]]))
check("the goal the run tried to overwrite stands", now["goal"] == was["goal"], now["goal"])
check("and the report still reads 0 removed",
      stored()["concepts"][KEYS[0]]["runs"][-1] == "3 added, 0 removed",
      str(stored()["concepts"][KEYS[0]]["runs"]))

print("\na run that adds nothing is refused, and the lesson it repeated is untouched")
before = STORE.read_bytes()
repeat = {key: [copy.deepcopy(stored()["concepts"][key]["class_lesson"])] for key in KEYS}
code, driver, _ = run(repeat, "--expand", "--max-attempts", "2")
check("the run reports failure", code == 1, str(code))
check("it asked again before giving up", len(driver.asked) == 6, str(driver.asked))
check("nothing was written", STORE.read_bytes() == before)

print("\na reply that is off-contract is asked for again, and never stored")
before = STORE.read_bytes()
half = lesson_for(KEYS[0], techniques=["TECHNIQUE FIVE"], examples=["WORKED SIX", "WORKED SEVEN"])
half["worked_examples"][0]["model_answer"] = ""
good = lesson_for(KEYS[0], techniques=["TECHNIQUE FIVE"], examples=["WORKED SIX", "WORKED SEVEN"])
code, driver, _ = run({KEYS[0]: [half, good]}, "--expand", "--concept", KEYS[0])
check("only the named concept was asked", set(driver.asked) == {KEYS[0]}, str(driver.asked))
check("it was asked twice: once refused, once accepted", len(driver.asked) == 2)
check("the run succeeded", code == 0, str(code))
check("the accepted reply is what was kept",
      "TECHNIQUE FIVE" in [t["name"] for t in stored()["concepts"][KEYS[0]]["class_lesson"]["techniques"]])
check("the refused reply was written out for a person to read",
      (STORE.parent / f"_class_lesson.{R._slugged(KEYS[0])}.reply.txt").exists())
check("the other two concepts were not touched",
      stored()["concepts"][KEYS[1]] == json.loads(before)["concepts"][KEYS[1]])

print("\nthe store stays one lesson per concept, however many runs it took")
check("three concepts, three lessons", len(stored()["concepts"]) == 3)
check("no technique appears twice in any lesson",
      all(len({t["name"] for t in entry["class_lesson"]["techniques"]})
          == len(entry["class_lesson"]["techniques"])
          for entry in stored()["concepts"].values()))
check("no worked example appears twice in any lesson",
      all(len({w["title"] for w in entry["class_lesson"]["worked_examples"]})
          == len(entry["class_lesson"]["worked_examples"])
          for entry in stored()["concepts"].values()))
check("every stored lesson still satisfies the contract",
      all(contract.validate(entry["class_lesson"], concept_key=key,
                            concept_statement=entry["class_lesson"]["concept_statement"])
          for key, entry in stored()["concepts"].items()))

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "each pass expands the lesson, and none can shrink it")
raise SystemExit(1 if fails else 0)
