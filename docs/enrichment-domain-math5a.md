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
    "what_it_is": "Adding two fractions whose bottom numbers are different.",
    "format_facts": [{"label": "Skill", "value": "Add fractions with unlike denominators"}],
    "scoring_factors": [{"name": "Correct answer", "what_it_measures": "Whether the arithmetic is right"}],
    "critical_rules": ["You can only add fractions when the denominators are the same."]
  },
  "learning_goals": ["You will be able to add two fractions with different denominators."],
  "core_method": {
    "name": "Same Bottom → Add Tops → Simplify",
    "summary": "Make the denominators match, add the numerators, then simplify.",
    "steps": [{"step": "Same bottom", "detail": "Find a common denominator."}],
    "formula": "a/b + c/d → (ad + cb) / bd"
  },
  "techniques": [{
    "name": "Find the smallest common denominator",
    "purpose": "Keeps the numbers small.",
    "how_to": ["List multiples of each denominator.", "Take the first one they share."],
    "example": "For $\\frac{1}{4}$ and $\\frac{1}{6}$ the common denominator is 12.",
    "why_it_matters": "Smaller numbers mean fewer mistakes.",
    "common_error": "Multiplying the denominators together every time."
  }],
  "worked_examples": [{
    "title": "Add one half and one quarter",
    "input": "Work out $\\frac{1}{2} + \\frac{1}{4}$.",
    "decoding": "The bottoms are different, so they must be made the same first.",
    "plan": "Change halves into quarters, then add the tops.",
    "model_answer": "$$\\frac{1}{2} + \\frac{1}{4} = \\frac{2}{4} + \\frac{1}{4} = \\frac{3}{4}$$ The answer is $\\frac{3}{4}$.",
    "annotations": [{"part": "\\frac{2}{4}", "comment": "One half is the same as two quarters."}]
  }],
  "useful_language": [{"category": "Fraction words",
    "items": [{"item": "denominator", "when_to_use": "The bottom number, how many equal parts there are."}]}],
  "common_mistakes": [{"mistake": "Adding the bottoms as well as the tops.",
    "why_it_hurts": "It gives a completely wrong answer.",
    "fix": "Only the top numbers are added; the bottom stays the same once matched."}],
  "practice_plan": {
    "time_budget": [{"phase": "Warm up", "minutes": "5", "focus": "Times tables"}],
    "drills": [{"name": "Ten quick adds", "instructions": "Add ten pairs of fractions with unlike bottoms."}],
    "routine": "Ten minutes a day, checking each answer."
  },
  "mastery_checklist": ["I can find a common denominator."],
  "strategy_notes": ["Always check whether the answer can be simplified."],
  "metadata": {
    "difficulty": "beginner",
    "estimated_study_time": "30 minutes",
    "tags": ["fractions"],
    "provenance_note": "Method and examples follow the base lesson."
  }
}
```
