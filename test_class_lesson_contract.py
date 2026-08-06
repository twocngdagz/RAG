"""The contract is a document, and a reply either satisfies it or is refused.

B20.1 contracts the class lesson out. That only works if the brief is complete
enough to hand over with nothing else attached — so this asserts the document
states all five things it promises (what a class lesson contains, the structure,
the format, the length, and the context supplied) and that the floors it prints
are the floors the code enforces, not two numbers that agree today.

The second half is the refusal. A generator that returns nine tenths of a class
lesson has not produced one: a technique with a single step is a sentence, an
example without its decoding shows what to write and not how the method got
there, and a lesson filed under the wrong concept teaches one ability under
another's name. Every one of those is refused by name, because the run that
retries needs to be told what to fix.

And nothing here draws. Illustrations attach afterwards through the asset
channel; a reply carrying one is refused, which is what makes "no illustration is
generated here" a check instead of a hope.

    python test_class_lesson_contract.py
"""
from __future__ import annotations

import copy

import class_lesson_contract as contract
import domain_packs

fails: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}{'' if cond else '  <- ' + detail}")
    if not cond:
        fails.append(label)


CONCEPT_KEY = "book:ch01:concept-one"
CONCEPT_STATEMENT = "CONCEPT ONE STATEMENT."

# Deliberately shouted nonsense. A fixture that read like teaching would be
# teaching this batch wrote, and this batch writes none.
LESSON = {
    "schema_version": "class_lesson.v1",
    "concept_key": CONCEPT_KEY,
    "concept_statement": CONCEPT_STATEMENT,
    "goal": "GOAL SENTENCE.",
    "techniques": [
        {
            "name": "TECHNIQUE ONE",
            "purpose": "PURPOSE ONE",
            "steps": [
                {"step": "STEP A", "detail": "DETAIL A"},
                {"step": "STEP B", "detail": "DETAIL B"},
            ],
            "example": "EXAMPLE ONE",
            "why_it_matters": "WHY ONE",
            "common_error": "ERROR ONE",
        }
    ],
    "worked_examples": [
        {
            "title": "WORKED ONE",
            "input": "INPUT ONE",
            "decoding": "DECODING ONE",
            "plan": "PLAN ONE",
            "model_answer": "ANSWER ONE",
            "annotations": [{"part": "PART ONE", "comment": "COMMENT ONE"}],
        },
        {
            "title": "WORKED TWO",
            "input": "INPUT TWO",
            "decoding": "DECODING TWO",
            "plan": "PLAN TWO",
            "model_answer": "ANSWER TWO",
            "annotations": [{"part": "PART TWO", "comment": "COMMENT TWO"}],
        },
    ],
}

MATERIAL = {
    "schema_version": "pte_lesson_enrichment.v1",
    "lesson_title": "CHAPTER TITLE",
    "source_label": "book:ch01",
    "overview": {"what_it_is": "WHAT THE CHAPTER IS", "critical_rules": ["RULE ONE"]},
    "learning_goals": ["CHAPTER GOAL ONE"],
    "core_method": {
        "name": "CHAPTER METHOD",
        "summary": "METHOD SUMMARY",
        "steps": [{"step": "METHOD STEP", "detail": "METHOD DETAIL"}],
        "formula": "",
    },
    "techniques": [
        {
            "name": "MATERIAL TECHNIQUE",
            "purpose": "MATERIAL PURPOSE",
            "how_to": ["MATERIAL HOW TO"],
            "example": "MATERIAL EXAMPLE",
            "why_it_matters": "MATERIAL WHY",
            "common_error": "MATERIAL ERROR",
        }
    ],
    "worked_examples": [
        {
            "title": "MATERIAL WORKED",
            "input": "MATERIAL INPUT",
            "decoding": "MATERIAL DECODING",
            "plan": "MATERIAL PLAN",
            "model_answer": "MATERIAL ANSWER",
            "annotations": [{"part": "MATERIAL PART", "comment": "MATERIAL COMMENT"}],
        }
    ],
    "useful_language": [{"category": "WORDS", "items": [{"item": "TERM", "when_to_use": "WHEN"}]}],
    "common_mistakes": [{"mistake": "MISTAKE", "why_it_hurts": "HURTS", "fix": "FIX"}],
    "mastery_checklist": ["CHECK ONE"],
    "strategy_notes": ["NOTE ONE"],
}


def reply(**over) -> dict:
    document = copy.deepcopy(LESSON)
    document.update(copy.deepcopy(over))
    return document


def accepted(document: dict) -> dict:
    return contract.validate(
        document, concept_key=CONCEPT_KEY, concept_statement=CONCEPT_STATEMENT
    )


def refused(label: str, document, *, naming: str = "") -> None:
    try:
        accepted(document)
    except contract.ClassLessonRefused as error:
        check(label, not naming or naming in str(error), f"said {str(error)[:120]!r}")
        return
    check(label, False, "accepted it")


DOC = contract.contract_text()

print("the contract is a document, and it states all five things it promises")
for what, heading in (
    ("what a class lesson must contain", "## 1. What a class lesson must contain"),
    ("the structure it returns in", "## 2. The structure you return"),
    ("the format", "## 3. The format"),
    ("the length", "## 4. The length"),
    ("the context it is given", "## 6. The context you are given"),
):
    check(f"it states {what}", heading in DOC, heading)

check("it says a run is one concept, never a chapter", "One request is one concept" in DOC)
check("it says runs are unlimited", "no limit on how many times a concept is run" in DOC)
check("it says nothing already there may be deleted",
      "Never delete, replace, reword, or renumber anything already there" in DOC)
check("it says a reply is one fenced json block", "```json ` code block" in DOC)
check("and that only a note to a person may follow it",
      "Nothing after it either, with one exception" in DOC)

print("\nand it describes exactly the shape the code enforces")
for key in contract.REQUIRED_KEYS + contract.TECHNIQUE_FIELDS + contract.WORKED_EXAMPLE_FIELDS:
    if key not in DOC:
        check(f"the document names {key}", False, "the generator is never told about it")
check("the document names every field the code requires",
      all(key in DOC for key in
          contract.REQUIRED_KEYS + contract.TECHNIQUE_FIELDS + contract.WORKED_EXAMPLE_FIELDS))
check("the document prints the same floors the code enforces",
      f"at least {contract.MIN_STEPS} steps" in DOC
      and f"at least {contract.MIN_ANNOTATIONS} annotation" in DOC
      and f"| worked examples | {contract.MIN_WORKED_EXAMPLES}," in DOC,
      "the document and the checks disagree about the floor")
check("the document names every context block the run appends",
      all(heading in DOC for heading in (
          contract.BOOK_HEADING, contract.CONCEPT_HEADING, contract.OTHER_CONCEPTS_HEADING,
          contract.MATERIAL_HEADING, contract.CURRENT_HEADING)))

print("\nthe prompt hands that document over, byte for byte")
prompt = contract.build_prompt(
    pack=domain_packs.get("math5a"),
    concept_key=CONCEPT_KEY,
    concept_statement=CONCEPT_STATEMENT,
    other_concepts=[{"stable_key": "book:ch01:concept-two", "statement": "CONCEPT TWO STATEMENT."}],
    material=MATERIAL,
    current=None,
)
check("the contract document is in the prompt, unaltered", DOC in prompt)
check("the concept it is for is named", CONCEPT_KEY in prompt and CONCEPT_STATEMENT in prompt)
check("the other concepts are named, so they are not taught here",
      "book:ch01:concept-two" in prompt and "Do not teach them here" in prompt)
check("the chapter's material is carried",
      "MATERIAL TECHNIQUE" in prompt and "MATERIAL WORKED" in prompt and "MATERIAL DECODING" in prompt)
check("the book and its learners are named",
      "Singapore Math Primary Mathematics 5A" in prompt and "10-11 years old" in prompt)

book_block = prompt.split(contract.BOOK_HEADING)[-1].split(contract.CONCEPT_HEADING)[0]
check("the book's own wording rules come through",
      "Write EVERY calculation in LaTeX" in book_block
      and "Write for a 10-year-old" in book_block, book_block)
check("but not its rules about fields this shape has not got",
      "useful_language" not in book_block,
      "the prompt asks for a key the contract refuses on arrival")
check("a first run says there is nothing yet", "none yet — this is the first run" in prompt)

print("\nand it asks for no picture of any kind")
check("no illustration is asked for, and none is smuggled in",
      contract._ILLUSTRATION_RE.search(prompt) is None,
      str(contract._ILLUSTRATION_RE.search(prompt)))
check("the prompt says pictures are attached afterwards, not drawn here",
      "No pictures, no diagrams" in prompt and "attached afterwards" in prompt)

print("\na complete reply is accepted, and stored as exactly the contract's shape")
clean = accepted(reply())
check("accepted", clean["concept_key"] == CONCEPT_KEY)
check("it carries nothing the contract does not list", set(clean) == set(contract.REQUIRED_KEYS))
check("the technique keeps its steps in order",
      [s["step"] for s in clean["techniques"][0]["steps"]] == ["STEP A", "STEP B"])
check("the worked example keeps its decoding, plan, model answer and annotations",
      clean["worked_examples"][0]["decoding"] == "DECODING ONE"
      and clean["worked_examples"][0]["plan"] == "PLAN ONE"
      and clean["worked_examples"][0]["model_answer"] == "ANSWER ONE"
      and clean["worked_examples"][0]["annotations"] == [{"part": "PART ONE", "comment": "COMMENT ONE"}])
check("whitespace in the copied statement is tolerated, not punished",
      accepted(reply(concept_statement="  CONCEPT ONE\n  STATEMENT.  "))["goal"] == "GOAL SENTENCE.")

print("\na reply missing any required part is refused, and told which part")
refused("not an object at all", "here is your lesson", naming="not a JSON object")
refused("a reply of another schema", reply(schema_version="lesson.v9"), naming="class_lesson.v1")
refused("a reply with no goal", reply(goal=""), naming="goal")
refused("a reply whose techniques are missing",
        {k: v for k, v in reply().items() if k != "techniques"}, naming="no techniques")
refused("a reply with no technique at all", reply(techniques=[]), naming="floor is 1")
refused("a technique that is not a list", reply(techniques={"name": "X"}), naming="not a list")

no_error = reply()
no_error["techniques"][0]["common_error"] = ""
refused("a technique with no common error", no_error, naming="common_error")

one_step = reply()
one_step["techniques"][0]["steps"] = [{"step": "STEP A", "detail": "DETAIL A"}]
refused("a technique with one step", one_step, naming="method with one step is a sentence")

bare_step = reply()
bare_step["techniques"][0]["steps"][1] = {"step": "STEP B"}
refused("a step with no instruction in it", bare_step, naming="steps[1] has no detail")

refused("a lesson with one worked example", reply(worked_examples=LESSON["worked_examples"][:1]),
        naming="floor is 2")

no_decoding = reply()
no_decoding["worked_examples"][1]["decoding"] = ""
refused("a worked example with no decoding", no_decoding, naming="worked_examples[1] has no decoding")

no_answer = reply()
no_answer["worked_examples"][0]["model_answer"] = ""
refused("a worked example with no model answer", no_answer, naming="model_answer")

no_notes = reply()
no_notes["worked_examples"][0]["annotations"] = []
refused("a worked example nobody annotated", no_notes, naming="worked_examples[0] has no annotations")

loose_notes = reply()
loose_notes["worked_examples"][0]["annotations"] = ["JUST A LINE OF TEXT"]
refused("annotations that are not the {part, comment} the contract asks for", loose_notes,
        naming="the teacher's voice")

bare_note = reply()
bare_note["worked_examples"][0]["annotations"] = [{"part": "PART ONE"}]
refused("an annotation that points at nothing", bare_note, naming="no comment")

print("\na reply for a different concept is refused, never filed under this one")
refused("another concept's key", reply(concept_key="book:ch01:concept-two"),
        naming="under another's name")
refused("a rewritten statement", reply(concept_statement="A BETTER STATEMENT I WROTE MYSELF."),
        naming="not the generator's to rewrite")

print("\na key the contract does not list is refused rather than stored")
refused("an invented field", reply(difficulty="easy"), naming="difficulty")
refused("an illustrations field", reply(illustrations=[{"svg": "<svg/>"}]),
        naming="attached afterwards, never generated here")

print("\nand no picture reaches the lesson by any other route")
drawn = reply()
drawn["worked_examples"][0]["model_answer"] = "ANSWER ONE\n\n![bar model](bar-model.png)"
refused("a markdown image in the working", drawn, naming="illustration")

svg = reply()
svg["techniques"][0]["example"] = "<svg width='10'><rect/></svg>"
refused("svg markup in a technique", svg, naming="illustration")

uri = reply()
uri["goal"] = "GOAL SENTENCE. data:image/png;base64,AAAA"
refused("an image smuggled into the goal as a data uri", uri, naming="illustration")

check("but telling a learner to draw is teaching, and is kept",
      accepted(reply(goal="Draw a bar model and label each part."))["goal"].startswith("Draw"))

print("\ntwo pieces of teaching under one name are refused, because a merge keeps one")
twice = reply()
twice["techniques"] = [LESSON["techniques"][0], {**LESSON["techniques"][0], "purpose": "OTHER"}]
refused("the same technique name twice", twice, naming="names 'TECHNIQUE ONE' twice")

twice_worked = reply()
twice_worked["worked_examples"] = [LESSON["worked_examples"][0], LESSON["worked_examples"][0]]
refused("the same worked example title twice", twice_worked, naming="twice")

print("\nidentity is the name, insensitive to case and spacing")
first = accepted(reply())
same_name = accepted(reply(techniques=[{**LESSON["techniques"][0], "name": "technique   one"}]))
merged, report = contract.merge(first, same_name)
check("a repeat under a different case is not a second copy",
      len(merged["techniques"]) == 1 and report["added"] == [], str(report))

print("\na merge only ever adds")
second = accepted(reply(
    goal="A DIFFERENT GOAL.",
    techniques=[{**LESSON["techniques"][0], "name": "TECHNIQUE TWO"}],
    worked_examples=[LESSON["worked_examples"][0], {**LESSON["worked_examples"][1], "title": "WORKED THREE"}],
))
merged, report = contract.merge(first, second)
check("what was there is still there",
      [t["name"] for t in merged["techniques"]] == ["TECHNIQUE ONE", "TECHNIQUE TWO"])
check("the worked examples that existed are kept and the new one is appended",
      [w["title"] for w in merged["worked_examples"]] == ["WORKED ONE", "WORKED TWO", "WORKED THREE"])
check("the goal a run tried to replace is not replaced", merged["goal"] == "GOAL SENTENCE.")
check("the report says what was added, and that nothing went",
      contract.summary(report) == "2 added, 0 removed", contract.summary(report))
check("and it names them",
      report["added"] == ["technique 'TECHNIQUE TWO'", "worked example 'WORKED THREE'"],
      str(report["added"]))
check("nothing the stored lesson had was lost",
      contract.assert_nothing_lost(first, merged) is None)

print("\na run that adds nothing is refused")
merged, report = contract.merge(first, accepted(reply()))
try:
    contract.assert_expanded(report)
    check("a repeat of the current lesson is refused", False, "accepted it")
except contract.ClassLessonAddedNothing as error:
    check("a repeat of the current lesson is refused", "expand it" in str(error))

check("a first run is all addition",
      len(contract.merge(None, first)[1]["added"]) == 4,
      str(contract.merge(None, first)[1]["added"]))

print("\na merge that lost something would be caught, not shipped")
try:
    contract.assert_nothing_lost(first, {**first, "techniques": []})
    check("a lesson that lost a technique is caught", False, "accepted it")
except contract.ClassLessonLostContent as error:
    check("a lesson that lost a technique is caught", "TECHNIQUE ONE" in str(error))

print("\n" + "=" * 58)
print(f"{len(fails)} FAILED: {fails}" if fails else "the contract is handable, and it is enforced")
raise SystemExit(1 if fails else 0)
