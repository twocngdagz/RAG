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
}

export interface BookInfo {
  slug: string
  chapter_count: number
}

/** Read the text of a field that is a grounded object or (legacy) a bare string. */
export function textOf(value: Grounded | string | null | undefined): string | null {
  if (value == null) return null
  if (typeof value === 'string') return value
  return value.text
}
