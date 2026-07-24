# Lesson Enrichment — Domain Pack: Primary Mathematics 5A

Fills the `{{SLOTS}}` in `docs/enrichment-engine.md` for the Singapore Math
Primary Mathematics 5A book. Engine + this pack = the full prompt for maths.

Source text must come from LlamaParse (`output/singapore-math-5a.parsed.md`),
which preserves fractions as LaTeX. Generic OCR destroys them — see
`docs/evaluator-mcp.md`.

## `{{APP_NAME}}`

maths

## `{{SUBJECT}}`

maths

## `{{DOMAIN_EXPERT}}`

primary maths teacher

## `{{AUDIENCE}}`

Year 5 / Grade 5 pupils, about 10–11 years old, and the teachers and parents helping them. Write for a child: short sentences, everyday words, one idea at a time. Never assume algebra. Explain *why* a method works, not just the steps.

READING LEVEL — this is measured and enforced. Match the source textbook, which reads at US grade 4:
- About **10 words per sentence**. One idea per sentence.
- About **1.33 syllables per word**. This is the part that usually fails.
- **Do not repeat technical terms.** The real 94-page textbook uses the word "denominator" TWICE in the entire book, and never writes "numerator" or "simplify" at all — it says "simplest form". Name a term once when you introduce it, then use everyday words ("the bottom number", "the top number") or simply show the maths.
- Prefer the short word every time: *use* not *utilise*, *change* not *convert*, *work out* not *calculate*, *same* not *equivalent*, *make it simpler* not *simplify*.

## `{{TASK_TYPE_LIST}}`

whole numbers, multiplication and division, fractions, area and perimeter, ratio, decimals, word problems, bar models

## `{{DOMAIN}}`

maths

## `{{ADDABLE_FACTS}}`

standard definitions, alternative solution methods, and everyday real-world contexts

## `{{TASK_TYPE_EXAMPLES}}`

"fractions", "word_problems", "area_and_perimeter"

## `{{TASK_TYPE_ADAPTATION}}`

- Every calculation you write MUST be arithmetically correct. This is checked automatically; a wrong sum is a defect, not a typo.
- Show the full working, every step, the way a pupil should write it — not just the answer.
- **At least FOUR worked examples**, and this is checked. Simple language is not a reason to give fewer — write four demonstrations AND keep the words easy. Vary them: one straightforward, one with a twist, one word problem, one showing a common mistake being corrected.
- Write maths in LaTeX: `$\frac{3}{4}$`, `$2\frac{1}{2}$`, `$\times$`, `$\div$`. Never write a fraction as loose digits.
- For word problems, show the **bar model** in words before the arithmetic — this book teaches through bar models.
- `worked_examples.model_answer` is the complete solution with working and the final answer stated in a sentence ("There are 22 stamps altogether.").
- `useful_language` is the maths vocabulary a pupil needs (numerator, denominator, product, remainder) with when to use each.
- `common_mistakes` are the real errors children make: adding denominators, forgetting to simplify, misreading "how many more".
- `practice_plan` drills are short, concrete exercises a pupil can do alone.
- `modality` is "reading" for a maths lesson unless the lesson is clearly oral.

## `{{DOMAIN_EXAMPLE}}`

```json
{
  "schema_version": "pte_lesson_enrichment.v1",
  "task_type": "fractions",
  "lesson_title": "Adding Unlike Fractions",
  "source_label": "math5a:ch03",
  "modality": "reading",
  "overview": {
    "what_it_is": "Adding two fractions when the bottom numbers are not the same.",
    "format_facts": [{"label": "Skill", "value": "Add fractions when the bottoms differ"}],
    "scoring_factors": [{"name": "Correct answer", "what_it_measures": "Whether the arithmetic is right"}],
    "critical_rules": ["You can only add fractions when the bottom numbers match."]
  },
  "learning_goals": ["You will be able to add two fractions when the bottoms differ."],
  "core_method": {
    "name": "Same Bottom → Add Tops → Make It Simpler",
    "summary": "Make the bottoms match. Add the tops. Then make it simpler.",
    "steps": [{"step": "Same bottom", "detail": "Find a bottom number they both share."}],
    "formula": "a/b + c/d → (ad + cb) / bd"
  },
  "techniques": [{
    "name": "Find the smallest bottom they share",
    "purpose": "Keeps the numbers small.",
    "how_to": ["Count up in each bottom number.", "Take the first one they both hit."],
    "example": "For $\\frac{1}{4}$ and $\\frac{1}{6}$ the shared bottom is 12.",
    "why_it_matters": "Smaller numbers mean fewer mistakes.",
    "common_error": "Times the two bottoms together every time."
  }],
  "worked_examples": [{
    "title": "Add one half and one quarter",
    "input": "Work out $\\frac{1}{2} + \\frac{1}{4}$.",
    "decoding": "The bottoms are not the same. Make them match first.",
    "plan": "Change halves into quarters, then add the tops.",
    "model_answer": "$$\\frac{1}{2} + \\frac{1}{4} = \\frac{2}{4} + \\frac{1}{4} = \\frac{3}{4}$$ The answer is $\\frac{3}{4}$.",
    "annotations": [{"part": "\\frac{2}{4}", "comment": "One half is the same as two quarters."}]
  }],
  "useful_language": [{"category": "Fraction words",
    "items": [{"item": "denominator", "when_to_use": "The bottom number. Say it once, then just say bottom number."}]}],
  "common_mistakes": [{"mistake": "Adding the bottoms as well as the tops.",
    "why_it_hurts": "It gives a completely wrong answer.",
    "fix": "Add only the tops. The bottom stays the same."}],
  "practice_plan": {
    "time_budget": [{"phase": "Warm up", "minutes": "5", "focus": "Times tables"}],
    "drills": [{"name": "Ten quick adds", "instructions": "Add ten pairs of fractions. The bottoms differ."}],
    "routine": "Ten minutes a day, checking each answer."
  },
  "mastery_checklist": ["I can find a bottom number that both fractions share."],
  "strategy_notes": ["Always check if the answer can be made simpler."],
  "metadata": {
    "difficulty": "beginner",
    "estimated_study_time": "30 minutes",
    "tags": ["fractions"],
    "provenance_note": "Method and examples follow the base lesson."
  }
}
```
