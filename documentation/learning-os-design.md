# Learning OS — system design

One app that teaches three subjects, using the method from *A Mind for Numbers*
(Barbara Oakley, 2014), with a content contract any future book must satisfy.

Status: design, not yet built. Written 25 July 2026.

---

## 1. What it has to do

**Teach, not test.** The current app asks a child a question cold, marks it, and
moves on. There is no explanation and no worked example anywhere in the practice
flow. It is an exam with no lesson in front of it.

**Three subjects, one flow.** Maths, PTE, and English vocabulary. The flow lives
in the engine; the subject is a plug-in. Adding book four must not mean editing
the flow.

**Mobile is the target.** Web first, but shaped for a phone from the start: one
thing per screen, a session that fits a bus ride.

### Non-negotiables, from the book

| Principle | What it forces |
|---|---|
| Priming before study | a 1–2 minute preview before any question |
| Teach before you test | nothing is marked until it has been taught in this session |
| Active recall, closed book | the explanation is off the screen when the question is asked |
| Chunking | practise one skill until it runs smoothly, then move on |
| Interleaving | review mixes skills; it never runs five of the same in a row |
| Spacing | the same thing returns days later, when it is half-forgotten |
| Avoid the illusion of competence | reading a worked example is not evidence; only unaided recall is |

The last one is the reason for the whole shape. A child who reads a worked
example *feels* they understand it. That feeling is false until they have
produced it themselves with the example gone.

### Constraints

- one developer, evenings; one learner today, multi-user later
- marking must be instant and free wherever it is computable — no model call at
  practice time
- the flow must work with no AI available at all
- free-tier model access, usage-capped

---

## 2. Shape

```
   Content (per book)            Engine (shared, deterministic)      Subject adapter
   ------------------            ------------------------------      ---------------
   lessons                       session composition                 how to mark
   skills                        scheduling / spacing                which capabilities
   teaching cards                mastery                             what a question looks like
   questions                     the flow: prime -> teach ->
        |                        practise -> explain -> review
        v
   CONTRACT CHECK  <-- content a learner never sees until it passes
```

Three rules that decide where anything goes:

1. **The engine never knows what subject it is teaching.** If a change needs an
   `if subject == "maths"` in the engine, it belongs in the adapter.
2. **Content is inert data.** It is checked on the way in, not trusted at runtime.
3. **Code owns the flow, the schedule, and the state.** A model may write
   explanations and judge open wording. It never decides what comes next.

---

## 3. The contract — what a book must supply

This is the part that makes book four cheap, so it is designed before any screen.

**Per lesson** (for priming)
- what this lesson is about, one sentence
- what you will be able to do afterwards
- what usually goes wrong

**Per skill** (for the teaching card)
- a plain explanation
- at least one worked example: the question, the steps, the answer
- the common mistake
- what must be learned first

**Per question**
- a checkable answer
- the skill it practises

### Presence is not enough — the check has to judge usefulness

ELA's library was measured before writing this, and it is the reason this section
exists:

- 17,631 vocabulary items, every one carrying a definition, usage note, and
  example sentences. A presence check passes all of them.
- Those items share **34,923 example sentences built from 385 distinct
  skeletons**. 99% come from a template reused five or more times. The most
  common — "Her notes explain ___ in a practical context" — appears 6,765 times.
- The results include "The meeting focused on yacht as a key issue", "The final
  result was privy and easy to understand", and "She badly reviews her notes
  before class".

The fields are all there. The teaching is not. A contract that only checks for
presence would wave through a library that teaches a child nonsense.

So the contract carries deterministic quality checks, not just required fields:

| Check | Catches |
|---|---|
| template reuse — strip the item from its example, cluster the skeletons | mad-lib examples |
| the example must actually contain the item, used as its stated part of speech | "aback" used as a verb |
| the explanation must not repeat the item's own words as its definition | circular definitions |
| worked examples must show steps, not just an answer | teaching by assertion |
| reading level within range of the source audience | a Year-5 lesson written for adults |

Each ships with a planted-error self-test, per the discipline already in this
repo: a check that cannot be made to fail is not checking anything.

---

## 4. Data

Already here: per-item review state, attempt history, question banks tagged by
lesson and skill.

Missing, and needed:

```
book            slug, title, audience, adapter
lesson          book, number, title, priming fields
skill           lesson, name, teaching card (explanation, worked example,
                common mistake), prerequisites
question        skill, prompt, answer, how to mark it
learner_skill   learner, skill, taught_at        <- gates marking
study_session   learner, book, minutes, status, composed entries
session_entry   session, phase, skill|question, order
```

`learner_skill.taught_at` is small and load-bearing: it is what lets the engine
refuse to mark a question for a skill this learner has never been taught.

`session_entry.phase` is one of prime / teach / practise / explain / review. The
session is composed once, in order, and the runtime just walks it. It does not
re-decide anything mid-session — that is what makes a session reproducible and
testable.

---

## 5. The flow

```
 PRIME     one screen, ~1 min      what today covers, what trips people up
    |
 TEACH     one skill               explanation + worked example, fully shown
    |
 PRACTISE  same skill, closed book the example is gone from the screen
    |
 EXPLAIN   in your own words       the only real test of understanding
    |
 (repeat teach->practise for the next new skill)
    |
 REVIEW    mixed, interleaved      due and weak items from earlier lessons
    |
 DONE      what you got, what returns tomorrow
```

New material is blocked — teach one thing, practise that one thing. Review is
interleaved. Both are correct at different moments: blocking builds the chunk,
interleaving teaches you when to reach for it.

Session length 10 / 15 / 20 minutes, easing up for a beginner.

### Marking, per subject

| Subject | Correct means | Decided by |
|---|---|---|
| Maths | the arithmetic | code, exactly |
| English vocabulary | you produced the right phrase | code, exactly |
| PTE writing | a judgement against a rubric | a model, disclosed as advice |

Two of three need no model at all. That is the point of the split, and it is why
the app still works with the internet off.

---

## 6. Trade-offs, stated plainly

**Composing the whole session up front, rather than deciding as you go.**
Reproducible, testable, and it survives a dropped connection. Costs some
adaptivity — a child who is clearly struggling still finishes the composed
session. Accepted; a session is 15 minutes.

**Blocked teaching then interleaved review, rather than interleaving throughout.**
Follows the book, and matches how a classroom runs. Risk is that blocked practice
inflates confidence within the session; the interleaved review is what corrects it.

**One repo, three subjects, rather than a service per subject.**
One learner, one developer. Splitting now would buy nothing and cost a boundary
to maintain.

**Python here rather than porting the flow to Laravel.**
ELA's PHP does not port. Its *design* does, and it is good — the loop below is
essentially ELA's, generalised. But building it twice is the real risk, and this
decision should be revisited before mobile work starts in earnest.

**Not importing ELA's 17,631 items as they stand.**
The word list is fine — it is Oxford/COCA. The teaching content around it is
template-generated and largely wrong. Importing it would put nonsense in front of
a learner and would also be the first thing to make the contract a lie. The
options are to regenerate the teaching content through the pipeline with the
checks turned on, or to start with a small verified subset. Either is honest;
importing as-is is not.

---

## 7. What I would revisit as it grows

- **Where the flow lives.** If mobile becomes real, one implementation has to
  win. Deciding late means writing it twice.
- **Prerequisites.** Skills have a `prerequisites` field in this design and
  nothing reads it yet. Sequencing a curriculum properly needs it.
- **Weak capabilities, not just weak items.** The engine tracks that a child is
  shaky on a question. It does not yet track that they can *do* it but cannot
  *explain* it, which is a different repair.
- **Audio.** Half of PTE is listening and speaking, and none of it is reachable
  without recording and playback.

---

## 8. Build order

1. The guideline document, from the book — the source of truth for everything above
2. The contract and its checks; run against maths, PTE, and ELA. Expect maths to
   mostly pass and the other two to fail loudly. That is the contract working.
3. The flow end to end on **one lesson** — Ratio, which has no teaching today
4. Walk it as a learner, then apply to the rest

Step 2 before step 3, deliberately. If the contract is derived from a flow that
already exists, it will only ever describe that flow.
