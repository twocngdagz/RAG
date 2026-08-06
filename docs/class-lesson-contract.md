# The class-lesson contract

You are being asked to write **one class lesson for one concept**. This document
is the whole brief. Anything that satisfies it is acceptable — a chat model, a
model behind an API, or a person doing the work by hand. Nothing else about this
project needs to be known to do the job.

A **concept** is one masterable ability inside a chapter: "add two fractions with
unlike bottom numbers", "find the area of a triangle". A chapter has several. You
are given exactly one of them per request, and you write the classroom teaching
for that one.

Extraction gave the book's topics. Enrichment gave detail about the chapter. What
neither produced is the thing a teacher stands up and delivers for one ability:
a goal, a method with its steps, and examples worked in front of the class. That
is what a class lesson is, and that is what you return.

---

## 1. What a class lesson must contain

Three things, for the one concept you were given, and nothing else.

**A goal.** One sentence, addressed to the learner, saying what they will be able
to do when the lesson is over. It is not a description of the lesson ("this
lesson covers…"); it is the ability, in words a learner would use about
themselves.

**At least one technique** — the method the learner is being taught. A technique
carries:

- a **name** short enough to say out loud and refer back to;
- a **purpose**: when a learner reaches for this method rather than another;
- **steps**, in order, at least two of them. Each step has a short name and one
  instruction telling the learner what to do. A method with one step is a
  sentence, not a method;
- an **example**: one short line showing the technique used once, so the name
  means something before the worked examples arrive;
- **why it matters**: what goes right for a learner who uses it;
- a **common error**: the mistake learners actually make at this step. Not a
  warning invented to fill the field — the specific wrong move this technique
  exists to prevent.

**At least two worked examples** — the teaching demonstrated end to end. Two,
because one example teaches the example and a second teaches the method. Each
worked example carries:

- a **title**;
- the **input**: the question exactly as a learner would meet it;
- the **decoding**: what the question is actually asking, put in the learner's
  words before any work starts;
- the **plan**: which technique is being used and why that one;
- the **model answer**: the complete solution — every step of the working, then
  the answer stated in a sentence. Never the answer alone. A worked example that
  shows what to write and not how the method got there is the one thing a worked
  example is not for;
- **annotations**: at least one. Each points at one part of the working and says
  why that part is done. This is the teacher's voice beside the working.

## 2. The structure you return

One JSON object, exactly this shape. Use these key names exactly — do not rename
them, nest them differently, or add keys of your own.

```json
{
  "schema_version": "class_lesson.v1",
  "concept_key": "<the concept's key, copied exactly from THE CONCEPT below>",
  "concept_statement": "<the concept's statement, copied exactly from THE CONCEPT below>",
  "goal": "<one sentence to the learner: what they will be able to do>",
  "techniques": [
    {
      "name": "<short name for the method>",
      "purpose": "<when a learner reaches for it>",
      "steps": [
        {"step": "<short name for the step>", "detail": "<one instruction: what to do>"}
      ],
      "example": "<one short line showing the technique used once>",
      "why_it_matters": "<what goes right for a learner who uses it>",
      "common_error": "<the mistake learners actually make here>"
    }
  ],
  "worked_examples": [
    {
      "title": "<short name for this example>",
      "input": "<the question, exactly as a learner would meet it>",
      "decoding": "<what the question is asking, in the learner's words>",
      "plan": "<which technique, and why that one>",
      "model_answer": "<the complete working, step by step, then the answer in a sentence>",
      "annotations": [
        {"part": "<the step being pointed at>", "comment": "<why that step is done>"}
      ]
    }
  ]
}
```

`concept_key` and `concept_statement` are copied, not composed. They are how the
reply is filed; a reply that renames either is a lesson for a concept nobody
asked about, and it is refused.

## 3. The format

- Reply with **one fenced ` ```json ` code block**, and nothing before it. No
  preamble, no markdown tables, no commentary inside the JSON.
- Nothing after it either, with one exception: the note sections 5 and 7 ask for
  — that something already in the lesson is wrong, or that the concept statement
  is. That goes in plain text *after* the block. A person reads it; the run reads
  only the JSON.
- It must be **valid JSON**: double quotes, no trailing commas, no comments.
- Every field is a **string** unless the shape above shows a list or an object.
  Nothing is null, and nothing is left empty.
- The book block below (section 6) carries **this book's own format rules** —
  how to write its maths, which words its learners know, how long a sentence may
  run. Those apply on top of these and never against them. Write in the voice
  that block asks for.

## 4. The length

**The reply.** There is no word count to hit, and no ceiling to stay under — a
class lesson is as long as the teaching takes, and it grows every time it is run
again. What is fixed is the floor, because a lesson under it cannot be taught
from:

| part            | at least                                            |
| --------------- | --------------------------------------------------- |
| goal            | one sentence, and no more than one                   |
| techniques      | 1, each with at least 2 steps                        |
| worked examples | 2, each with at least 1 annotation                   |

Every field named in section 1 must be present and non-empty in every technique
and every worked example. A reply missing any of them is refused and asked for
again — the run does not keep the good half.

**The goal is one sentence.** It is a single ability, stated once. If it needs a
semicolon and two clauses to say, it is two concepts and only one of them is
yours.

**The run.** One request is one concept. A chapter is run one concept at a time,
never all at once, and there is no limit on how many times a concept is run: a
lesson that leaves learners stuck is run again and comes back bigger. Take the
time the work needs — the run waits for a complete answer rather than a fast one.

## 5. Expanding a class lesson that already exists

From the second run onwards you are given the concept's **current class lesson**,
in full, in the context below. It exists. It has been kept.

Your job on those runs is to **make the lesson bigger**, not to write it again:

- **Repeat what is there, unchanged.** Copy every existing technique and worked
  example into your reply exactly as they appear, with the same `name` and the
  same `title`. Repeat the goal as it stands.
- **Then add.** New techniques for the same concept, new worked examples that
  meet the learner where the existing ones did not — a different kind of number,
  a word problem, the case that always trips people up.
- **Never delete, replace, reword, or renumber anything already there.** Content
  is only ever added. If something already in the lesson is wrong, say so in
  plain text *after* returning the JSON block; a person will decide, and fixing
  it is an edit somebody signs, not a silent overwrite.
- **A reply that adds nothing new is refused.** Repeating the current lesson back
  unchanged is a wasted run.

Items are matched by name: a technique is the same technique if it has the same
`name`, and a worked example is the same example if it has the same `title`. So
give a genuinely new technique a genuinely new name, and never reuse an existing
name for different teaching.

## 6. The context you are given

Below this contract, each run supplies these blocks, in this order:

```
=== THE BOOK ===                          which book, who its learners are, how to write for them
=== THE CONCEPT ===                       the one concept: its key, and its statement
=== THE OTHER CONCEPTS IN THIS LESSON === the chapter's other concepts, by name
=== THE CHAPTER'S ENRICHED MATERIAL ===   the whole chapter's enrichment, as teaching notes
=== THE CONCEPT'S CURRENT CLASS LESSON === what already exists, or "none yet"
```

The enriched material is the **whole chapter**, not a slice of it. Which
technique and which example serve which concept is a teaching judgement, and it
is yours to make: read the chapter's material, take what serves the concept you
were given, and leave the rest.

The other concepts are listed so you do not teach them. They have their own runs
and their own lessons. Mention one in passing if the working needs it; do not
explain it here.

## 7. What is not yours to write

**Illustrations.** No pictures, no diagrams, no image descriptions, no image
prompts, no SVG, no markdown image links. Pictures are made separately and
attached afterwards. A reply containing one is refused.

**Exercises.** The questions a learner practises on are generated elsewhere and
already exist. Worked examples are demonstrations you do in front of the class,
not questions you leave for the learner to answer.

**The concept itself.** Its key and its statement are decided and approved
before you are called. If the statement is wrong, say so in plain text after the
JSON block; do not fix it in the reply.

## 8. What is refused

A reply is refused, and asked for again, if it:

- is not a single valid JSON object of `class_lesson.v1`;
- names a different concept than the one it was given;
- is missing any required part, or leaves one empty;
- has fewer than 1 technique, fewer than 2 steps in a technique, fewer than 2
  worked examples, or a worked example without an annotation;
- gives two techniques the same `name`, or two worked examples the same `title`
  — items are matched by name, so the lesson could only keep one of them;
- carries a key this contract does not list;
- contains a picture: image markup, a data URI, an image link, or an image file
  name, anywhere in any field;
- adds nothing to the current class lesson.

Refusal costs a run, not the lesson: what already exists is kept, and the request
is made again.
