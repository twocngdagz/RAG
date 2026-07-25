# Learning guideline

The rules this app teaches by, and where each one is enforced.

**Source:** *A Mind for Numbers*, Barbara Oakley (Penguin, 2014). Page numbers
below refer to the PDF in `input/pdfs/` — which is gitignored and never
committed, like every other source book here. What follows is the method
restated in our own words so it can be acted on; the book's text is not
reproduced.

**Why this document is short and bossy.** A guideline written as advice gets
ignored the first time it is inconvenient. Every rule below is written as three
things: what the app must *do*, what a book must *supply*, and how it is
*checked*. Where a rule is mechanical it becomes a real check with a
planted-error self-test, because a check that cannot be made to fail is not
checking anything. Where it is not mechanical, that is said plainly rather than
pretended otherwise.

---

## 1. Recall beats reading. Reading feels like learning and mostly is not

Reading something again makes it *fluent* — easy for the mind to process — and we
mistake that ease for knowledge. Oakley calls this the illusion of competence and
returns to it more than any other idea in the book (pp. 14, 68). Karpicke's work,
which she cites, found most students reread and few test themselves. Trying to
retrieve something is far more effective than looking at it again.

- **App:** the explanation and the worked example are **off the screen** when the
  question is asked. Never side by side, never a peek button.
- **Book:** nothing extra.
- **Check:** the practice screen must not render teaching content for the skill
  being asked. Enforced in code, not by convention.

## 2. Teach before you test

Understanding alone does not build a chunk, but neither does practice without it
(p. 83). A question about something never explained is not assessment, it is
guessing.

- **App:** a question may only be served for a skill this learner has been taught
  — in this session, or in an earlier one on record.
- **Book:** every skill supplies a plain explanation, at least one worked example
  showing the steps, and the common mistake.
- **Check:** contract check rejects a skill with no teaching card. The engine
  refuses to compose a question for an untaught skill.

## 3. A chunk needs four things, in order

Focused attention, then understanding the basic idea, then practice for context,
then recall without looking (p. 83). Skip the third and it stays theory; skip the
fourth and it stays an illusion.

- **App:** the session order is fixed — prime, teach, practise, recall unaided.
  Not configurable, because the order is the method.
- **Check:** session composition test asserts the phases appear in this order for
  any new skill.

## 4. Blocked first, then mixed — and the switch matters

Interleaving means practising a mixture of problems needing different methods
(pp. 80–81). But Oakley is specific about *when*: get the basic idea of a
technique down first, then start mixing. Training wheels, then no training wheels.

- **App:** new material is taught and practised one skill at a time. Review mixes
  skills deliberately.
- **Check:** no more than two consecutive review questions from the same skill
  when an alternative exists.

## 5. If the page tells you which method to use, you are not really practising

This one indicts what we built. Oakley notes that a book section devoted to one
technique means you already know which technique to apply before you read the
question (p. 81).

Our practice is scoped to the lesson you are standing in. Open Ratio, get ratio
questions. The child never has to decide *what kind of problem this is* — which
is most of the difficulty in a real exam.

- **App:** teaching and first practice stay lesson-scoped, which is correct. But
  **review must cross lessons** and must not announce the skill. The skill label
  currently shown above each question has to go during review.
- **Check:** review entries in a composed session must span more than one lesson
  once the learner has more than one lesson in progress.
- **Status:** not yet done. The lesson filter added on 25 July 2026 made teaching
  correct and review worse; only half of it has been fixed.

## 6. Spacing across days, not repetition within one sitting

Putting a day between attempts is what moves things into long-term memory
(p. 52). Cramming the same item five times in one session does not.

- **App:** the scheduler already does this — growing intervals, and an item that
  lapses comes back sooner.
- **Check:** covered by `test_spaced_repetition.py`.

## 7. Stay on the hard parts. Easy success is a trap

Continuing to practise something you can already do — because it is easy and
succeeding feels good — is named as an illusion of competence (p. 82).
Deliberately staying on the difficult parts is what Oakley calls deliberate
practice (p. 113).

- **App:** session composition weights weak and due material above new easy
  material, and mastered items must not fill a session.
- **Check:** a composed session must not consist mostly of items already
  mastered.
- **Status:** partly true today. The scheduler prefers due and weak items, but
  nothing stops a session being pleasant and useless.

## 8. Prime before studying

A quick look over what is coming — headings, structure, what it is for — before
studying it properly. This is the step ELA already took from the book and built.

- **App:** a priming screen of about a minute opens every session: what today
  covers, what you will be able to do, what usually goes wrong.
- **Book:** every lesson supplies those three things.
- **Check:** contract check rejects a lesson that cannot fill a priming screen.

## 9. Explaining it is the test of understanding

Retelling what you are learning, and explaining to others, is repeatedly given as
both a learning act and a way of finding out whether you actually understand
(pp. 84, 210).

- **App:** after practising a new skill, the learner explains it in their own
  words. Code marks what is computable — did they reach the answer, did they show
  the working. A model may comment on the wording, and that comment is advice
  that scores nothing.
- **Book:** the skill supplies a worked explanation to compare against, shown
  only after the learner has written theirs.
- **Check:** existing — `test_math_reasoning.py` proves the model's opinion
  cannot move the mark or the schedule.

## 10. Name the common mistake, out loud

An idea already in mind can block a better one — the Einstellung effect (p. 31).
A learner who has locked onto a wrong method will entrench it with practice
rather than escape it.

- **App:** the teaching card names the usual wrong approach and why it is wrong,
  not only the right one.
- **Book:** every skill supplies its common mistake.
- **Check:** contract check requires the field; a "spot the mistake" question type
  where the misconception is planted deliberately.

## 11. Checking your work is part of the work

Confident, focused effort produces confident errors; going back over it with
fresh eyes catches them (p. 210).

- **App:** where a method has a checking step, the teaching card shows it as a
  step, not an afterthought.
- **Status:** the maths lessons already name checking inside their methods. The
  practice flow does not ask for it. Open.

---

## What this rules out

Things that would be easy to build, feel productive, and work against the method:

- **A "show me the lesson" button on the practice screen.** It converts recall
  into reading. If the learner is stuck, the answer is a hint or an easier
  question, never the text.
- **Highlighting, or anything that feels like marking up a page.** Oakley is
  blunt that the movement of the hand fools you into thinking the idea has landed
  (pp. 69, 120).
- **Endless practice.** A session must end. An infinite queue is a slot machine.
- **Streaks that reward turning up over learning.** Not in the book; adjacent to
  everything it says about fooling yourself.
- **Announcing the skill during review.** See rule 5.

## Where the rules live

| Rule | Enforced by |
|---|---|
| 1, 2, 3, 4, 5, 7 | the engine — session composition and the runtime |
| 2, 8, 10 | the content contract — a book that cannot supply it is rejected |
| 6 | `spaced_repetition.py`, already tested |
| 9 | already built for maths reasoning |
| 11 | open |

Rules 5, 7 and 11 are not satisfied today and are written here as open, rather
than described as if they were done.
