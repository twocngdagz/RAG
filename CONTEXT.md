# Context — the learning domain

The shared language for RAG (the content factory) and Ela (the learning runtime).
A term here beats any other name for the same thing; if code or plan disagrees
with this file, one of them is wrong and it gets fixed, not ignored.

## Glossary

- **Book** — one source course (math5a, pte). In Ela, a book is what a learner
  enrols in — **enrolment targets the book, never the subject** (decided
  2026-08-03: two maths books must not blur into one "maths"). Ordered
  lessons. The subject-level tracks from B15 remain the defaults layer
  (session length, caps, wording), applied through the book's subject.
- **Lesson** — one chapter of a book: the *taught* thing. A teaching pass
  (method, concepts explained, worked examples) plus the group of concepts it
  introduces. Delivered one block at a time through the wizard.
- **Concept** — one masterable ability inside a lesson ("add unlike
  fractions"). **The concept is the schedulable card** (decided 2026-08-03,
  grilling session): it has its own comeback date, its own
  mastered/learning/new state, and it is what mastery is claimed about. Maps
  to an Ela learning item, aligned to its learning objective.
- **Exercise** — one question serving a concept ("work out 1/3 + 3/10").
  Exercises form a concept's **question bank**; a returning card asks a
  different exercise each time, so the learner practises the method rather
  than memorising one answer. Maps to activities under the concept's item.
- **Teaching pass** — the lesson's classroom explanation, run in the
  **teach-try rhythm** (decided 2026-08-03): each concept goes through
  explain → worked example in detail → try with help available → try alone,
  before the next concept begins. I-do, we-do, you-do per concept, the arc
  the native fractions lesson already walks. First time through a lesson,
  and again on Redo. Not repeated when a card returns.
- **Lesson completion** — a lesson counts as completed when its teaching pass
  has been walked to the end (every concept through the arc). Mastery is a
  different thing: it lives per concept and keeps evolving through the
  schedule long after the lesson is "done".
- **Question bank rotation** — the rule that a concept card's returning
  sessions draw different exercises from its bank.

## Decisions

- **A concept IS an objective — one thing, one name** (2026-08-03). The card
  in your schedule, the "what you'll be able to do" line, and the mastery
  tick are the same entity. The manifest writes its statement once. Where
  real pedagogy needs an exercise to feed several objectives (a capstone),
  the existing alignment machinery expresses it as the deliberate exception —
  never as a second standing vocabulary. Two names for one idea is the
  one-value-two-meanings disease Phase 1 spent itself curing.
- **Friendly images are generated in RAG at authoring time — never live**
  (2026-08-03, Roy's own words: "it will not happen simultaneously or live as
  the page is loading"). A hosted image model may draw at enrichment time,
  and the author may upload their own; both pass the same approval gate and
  enter the package sealed, labelled `generated` or `authored`. A learner
  never waits on or connects to an image service — the picture was made once,
  approved once, and lives in the package. Which service draws is a batch
  pick, swappable, invisible to learners.
- **A package is one self-contained file, fingerprinted whole** (2026-08-03).
  Computed diagrams ride as SVG text in their blocks; raster images ride in
  an assets section as base64; the content hash covers every byte of all of
  it. A lesson can never arrive without its pictures, and the enrichment
  rule's "N added, 0 removed" covers images because they are inside the thing
  compared. Big media (video, audio) gets its own decision the day it exists.
- **The package format breaks cleanly to v2** (2026-08-03). Concepts,
  question banks, and assets change the package's shape; v2 carries them and
  the importer refuses v1 thereafter (the major-version machinery already
  does this). The one existing v1 package — chapter 3 — is re-exported and
  re-imported in v2 form. One format forever beats a dual importer path kept
  alive for a single historical file we can regenerate ourselves.

- **Card = concept, not lesson, not exercise** (2026-08-03). One card per
  lesson cannot say "regrouping tomorrow, adding in two weeks"; one card per
  exercise invites memorising answers instead of methods. Concept cards match
  vocabulary (card = word) and native fractions (card = skill), so the
  engine — scheduling, evidence, objective mastery — is unchanged.
- **A returning card goes straight to a question, help on struggle**
  (2026-08-03). The full teaching pass runs on the first walk of a lesson and
  on an explicit Redo, never automatically before a returning card. A
  returning card asks one exercise from the bank; repeated struggle offers the
  concept's worked example as assistance, and using it classifies the attempt
  as assisted — the same rule help already follows everywhere else.
- **A review lesson is an on-demand mixed quiz, not a taught lesson**
  (2026-08-03). REVIEW A/B/C keep their places in the book list; opening one
  starts a practice-only session drawing exercises from the concepts of the
  lessons it reviews, due or not. No teaching pass, no cards of its own; its
  answers are real evidence and reschedule weak concepts sooner. The paper
  book's review chapter is what a scheduler is for — this keeps the book's
  shape while the engine does the reviewing.
- **The subject's preset decides what a session is** (2026-08-03). One rules
  card per subject in the B15 preset table: a maths session is ~10 quick
  questions; a PTE session is one writing task. Heavy and light exercises are
  never balanced by per-exercise minute estimates — those would be invented
  numbers wearing a data costume. The session builder obeys the preset of the
  book's subject.
- **Enrichment flows through RAG only, and it is additive by proof**
  (2026-08-03). One source of truth for imported books: more examples, more
  explanation, illustrations — generated or hand-written — enter RAG's source
  materials, pass the audit, and arrive in Ela as a new revision via
  re-import. Ela-side editing of imported lessons is not a door (a re-import
  would silently overwrite it). "Enrichment never erases" is checked, not
  hoped: re-export compares the new package to the old by element identity
  and prints "N added, 0 removed" — anything removed refuses to export as an
  enrichment and must be a named edit instead. Ela's frozen revisions
  guarantee no learner's history changes either way.
- **Illustrations: both kinds, this phase — with a human gate**
  (2026-08-03, Roy overrode the defer-friendly-art recommendation). Kind 1:
  teaching diagrams computed from the maths itself (bar models, area models,
  step layouts) — deterministic SVG, drawn the same way every time. Kind 2:
  friendly generated images. Conditions that ride the decision: every
  generated image is author-approved before it ships (a cartoon cutting
  pizzas into thirds when the problem says quarters teaches wrong — pictures
  in maths always carry mathematical content); every image carries honest
  provenance, caption, and alt-text; B17 gives packages an asset channel
  (inline SVG for diagrams, files for raster images).
- **A new book ships when** (2026-08-03, subject-agnostic checklist): its RAG
  domain pack exists; its manifests are authored and approved; every activity
  type it uses is either registered in Ela's runtime or refused by name. The
  book→lesson→concept→exercise model never changes per subject — only task
  types, marking, and modality do. Books without a source PDF (an authored
  interview course) are legitimate: provenance says authored, the package
  does not care.
- **Lessons are open, with the next one signposted** (2026-08-03). No locks:
  any lesson is clickable, the book page highlights where the learner is and
  suggests the next in sequence. The app invents no prerequisites the book
  never declared; real prerequisite hints can come later from the imported
  objective graph (`requires`, `builds_on`) as its own decided batch.
