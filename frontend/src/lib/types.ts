// Types mirror book_learning_materials_contract.py — the single source of truth.
// Kept to what the UI renders; the API validates the full shape on write.

export type Origin =
  | 'source_grounded'
  | 'pedagogical_generation'
  | 'insufficient_source_evidence'

export interface EvidenceSpan {
  node_id: string
  quote: string
}

/** A leaf of content: text plus where it came from and its supporting quotes. */
export interface Grounded {
  text: string | null
  claim_kind: string
  origin: Origin
  source_chunk_ids: string[]
  grounded_in_source_chunk_ids: string[]
  evidence_spans: EvidenceSpan[]
  reason: string | null
}

export interface KeyTerm {
  term: string
  meaning: Grounded
}
export interface CoreLesson {
  title: string
  explanation: Grounded
}
export interface WorkedExample {
  title: string
  example: Grounded
  explanation: Grounded
}
export interface Misconception {
  misconception: Grounded
  correction: Grounded
}
export interface PracticeQuestion {
  question: Grounded
  answer: Grounded
}

export interface Chapter {
  chapter_number: number
  chapter_title: string
  estimated_study_time?: Grounded | string | null
  chapter_summary?: Grounded
  learning_objectives: Grounded[]
  key_terms: KeyTerm[]
  core_lessons: CoreLesson[]
  worked_examples: WorkedExample[]
  common_misconceptions: Misconception[]
  practice_questions: PracticeQuestion[]
  review_checklist: Grounded[]
}

export interface ChapterDocument {
  book: { slug: string; title: string; source_pdf: string }
  generation: { backend?: string | null; model?: string | null }
  learning_materials: { chapters: Chapter[] }
}

export interface ChapterIndexItem {
  id: string
  book_slug: string
  chapter_number: number
  chapter_title: string
  backend?: string | null
  model?: string | null
  contract_status: string
  has_enrichment?: boolean
}

// ---- Enrichment (teaching layer) — mirrors pte_lesson_enrichment.v1 ----------

export interface FactPair { label: string; value: string }
export interface ScoringFactor { name: string; what_it_measures: string }
export interface MethodStep { step: string; detail: string }
export interface Technique {
  name: string; purpose: string; how_to: string[]
  example: string; why_it_matters: string; common_error: string
}
export interface Annotation { part: string; comment: string }
export interface WorkedExample {
  title: string; input: string; decoding: string; plan: string
  model_answer: string; annotations: Annotation[]
}
export interface LangItem { item: string; when_to_use: string }
export interface LangCategory { category: string; items: LangItem[] }
export interface CommonMistake { mistake: string; why_it_hurts: string; fix: string }
export interface TimeBudgetPhase { phase: string; minutes: string; focus: string }
export interface Drill { name: string; instructions: string }

export interface LessonEnrichment {
  schema_version: string
  task_type: string
  lesson_title: string
  source_label: string
  modality: string
  overview: {
    what_it_is: string
    format_facts: FactPair[]
    scoring_factors: ScoringFactor[]
    critical_rules: string[]
  }
  learning_goals: string[]
  core_method: { name: string; summary: string; steps: MethodStep[]; formula: string | null }
  techniques: Technique[]
  worked_examples: WorkedExample[]
  useful_language: LangCategory[]
  common_mistakes: CommonMistake[]
  practice_plan: { time_budget: TimeBudgetPhase[]; drills: Drill[]; routine: string }
  mastery_checklist: string[]
  strategy_notes: string[]
  metadata: {
    difficulty: string
    estimated_study_time: string
    tags: string[]
    provenance_note: string
  }
}

export interface BookInfo {
  slug: string
  chapter_count: number
}

// ---- Essay feedback (live scoring against the PTE Write Essay rubric) --------

export interface EssayTrait {
  name: string
  score: number
  max: number
  evidence: string
  fix: string
}

export interface EssayFeedback {
  word_count: number
  gating_applied: boolean
  traits: EssayTrait[]
  raw_total: number
  max_raw_total: number
  top_priorities: string[]
  one_line_verdict: string
}

export interface EssayPrompt {
  id: string
  type: string
  topic: string
  statement: string
  directive: string
  instruction: string
  time_minutes: number
  word_range: [number, number]
}

/** Read the text of a field that is a grounded object or (legacy) a bare string. */
export function textOf(value: Grounded | string | null | undefined): string | null {
  if (value == null) return null
  if (typeof value === 'string') return value
  return value.text
}
