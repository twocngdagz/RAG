# Lesson Enrichment — Domain Pack: PTE Academic

Fills the `{{SLOTS}}` in `docs/enrichment-engine.md`. Engine + this pack reproduces
`docs/enrichment-prompt.md` (the live ChatGPT project Instructions). To enrich a
different book, copy this file, change the values below, and reassemble — the
engine stays untouched.

---

## `{{APP_NAME}}`
PTE Academic

## `{{SUBJECT}}`
PTE

## `{{DOMAIN_EXPERT}}`
PTE coach

## `{{AUDIENCE}}`
Non-native English speakers preparing for PTE Academic (roughly CEFR B1–C1). Everything must be understandable to a B1 learner and genuinely improve their score.

## `{{TASK_TYPE_LIST}}`
Write Essay, Summarize Written Text, Answer Short Question, Read Aloud, Repeat Sentence, Describe Image, Re-tell Lecture, Re-order Paragraphs, Reading Fill in the Blanks, Reading/Listening Multiple Choice, Summarize Spoken Text, Highlight Correct Summary, Highlight Incorrect Words, Select Missing Word, Write from Dictation, or a Recap/Review lesson

## `{{DOMAIN}}`
PTE

## `{{ADDABLE_FACTS}}`
word counts, time limits, scoring factors, structure

## `{{TASK_TYPE_EXAMPLES}}`
"write_essay", "answer_short_question", "read_aloud", "recap_review"

## `{{TASK_TYPE_ADAPTATION}}`
- Writing (Write Essay, Summarize Written Text): worked_examples.model_answer = a COMPLETE model text of realistic length, with paragraph-level annotations; useful_language = sentence frames + linking words; core_method = decode → plan → write → edit; include the word count and a paragraph/word budget in overview/practice_plan.
- Speaking (Read Aloud, Repeat Sentence, Describe Image, Re-tell Lecture, Answer Short Question): worked_examples.model_answer = a model spoken script marked with chunking "/" and stressed WORDS; useful_language = chunking/stress/intonation patterns and templates; practice_plan.drills = timed speaking + record-and-compare; note timing (e.g. 10-second answers, 40-second describe image).
- Reading (Fill in the Blanks, Multiple Choice, Re-order Paragraphs): techniques = grammar/collocation/cohesion cues and elimination; worked_examples = one item solved step-by-step with the reasoning that finds the answer.
- Listening (Summarize Spoken Text, MCQ, Write from Dictation, Fill in the Blanks, Highlight Correct Summary): techniques = prediction + note-taking + signposting; worked_examples = a worked item showing notes → answer.
- Recap/Review lessons: consolidate the tasks it reviews; techniques = cross-task strategies; mastery_checklist spans those tasks.

## `{{DOMAIN_EXAMPLE}}`
Input: a Write Essay base lesson.
Output (a json code block containing an object like):
{
  "schema_version": "pte_lesson_enrichment.v1",
  "task_type": "write_essay",
  "lesson_title": "Write Essay: Planning, Paragraphing, and Editing",
  "source_label": "pte:ch07",
  "modality": "writing",
  "overview": {
    "what_it_is": "A 20-minute argumentative/persuasive essay of 200–300 words on a given prompt.",
    "format_facts": [ {"label":"Time","value":"20 minutes"}, {"label":"Word count","value":"200–300"}, {"label":"Paragraphs","value":"4 (intro, 2 body, conclusion)"} ],
    "scoring_factors": [ {"name":"Content","what_it_measures":"addresses all parts of the prompt"}, {"name":"Form","what_it_measures":"is a 200–300 word essay"}, {"name":"Development & coherence","what_it_measures":"ideas developed and logically linked"} ],
    "critical_rules": [ "Off-topic essays can score zero across all traits.", "Under 200 or over 300 words is penalised." ]
  },
  "learning_goals": [ "Decode any prompt into a position and two reasons.", "Write a 4-paragraph, 220–260 word essay within 20 minutes." ],
  "core_method": { "name":"Decode → Plan → Write → Edit", "summary":"Turn the prompt into a decision, then a paragraph plan, then prose.", "steps":[ {"step":"Decode","detail":"Mark task words, topic words, limits, and the opinion required."}, {"step":"Plan","detail":"One position + two distinct, explainable reasons."} ], "formula":"TASK WORDS + TOPIC + LIMITS → PLAN" },
  "techniques": [ {"name":"PIE paragraphs","purpose":"stop list-paragraphs","how_to":["State the point","Illustrate with a concrete example","Explain why it supports your position"],"example":"Point: public housing pays off long-term → Illustration: fewer emergency costs → Explanation: so initial cost is justified.","why_it_matters":"scores Development & coherence","common_error":"giving an example with no explanation"} ],
  "worked_examples": [ {"title":"Agree/disagree model","input":"Some people think online learning is better than classroom learning. To what extent do you agree?","decoding":"Task: to what extent → choose a degree; topic: online vs classroom learning.","plan":"Position: partly agree. Reason 1: flexibility/access. Reason 2: classroom social/discipline.","model_answer":"<a complete 220–260 word 4-paragraph essay goes here in real output>","annotations":[ {"part":"Introduction","comment":"context → issue → clear partial position"} ]} ],
  "useful_language": [ {"category":"Position","items":[ {"item":"I partly agree with this view because …","when_to_use":"a qualified stance"} ]}, {"category":"Linking words","items":[ {"item":"however / furthermore / consequently","when_to_use":"contrast / addition / result"} ]} ],
  "common_mistakes": [ {"mistake":"no clear position","why_it_hurts":"hurts Content and coherence","fix":"state a degree or side in the intro that predicts the body"} ],
  "practice_plan": { "time_budget":[ {"phase":"Decode + plan","minutes":"3","focus":"position + 2 reasons"}, {"phase":"Write","minutes":"14","focus":"4 paragraphs"}, {"phase":"Edit","minutes":"3","focus":"content, then form, then language"} ], "drills":[ {"name":"Prompt decoding","instructions":"For 5 prompts, write only the position + 2 reasons in 2 minutes each."} ], "routine":"One full timed essay, then self-mark against the scoring factors." },
  "mastery_checklist": [ "I can decode a prompt into a position and two reasons.", "I can write 200–300 words in 20 minutes." ],
  "strategy_notes": [ "Aim for 220–260 words so small edits don't push you outside the limit." ],
  "metadata": { "difficulty":"advanced", "estimated_study_time":"2 hours", "tags":["writing","argumentative essay","planning"], "provenance_note":"Word count, timing, and scoring-factor names are standard PTE facts added beyond the base lesson." }
}

## Reusing for a different book

Copy this file to `enrichment-domain-<book>.md` and rewrite each slot for the new
domain:
- `{{SUBJECT}}` / `{{DOMAIN_EXPERT}}` / `{{AUDIENCE}}` — who it's for and who "teaches".
- `{{TASK_TYPE_LIST}}` / `{{TASK_TYPE_EXAMPLES}}` — that book's kinds of items/skills.
- `{{TASK_TYPE_ADAPTATION}}` — how content should differ per task type (the part
  that gives the output its authority; write it from real domain expertise).
- `{{DOMAIN}}` / `{{ADDABLE_FACTS}}` — which authoritative facts the model may add.
- `{{DOMAIN_EXAMPLE}}` — one full example in the new domain.

Leave the engine and `schema_version` unchanged so the pipeline, DB, API, and
frontend keep working without code edits.
