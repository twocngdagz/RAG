import type {
  BookInfo,
  ChapterDocument,
  ChapterIndexItem,
  EssayAttempt,
  EssayAttemptDetail,
  EssayFeedback,
  EssayPrompt,
  LessonEnrichment,
} from './types'

// Same-origin /api in dev (Vite proxies to FastAPI:8000). Override for prod.
const BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${path}`)
  }
  return res.json() as Promise<T>
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    // Surface the API's detail message (e.g. missing key, model error) if present.
    let detail = `${res.status} ${res.statusText}`
    try {
      const j = await res.json()
      if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  books: () => get<BookInfo[]>('/books'),
  chapterIndex: (slug: string) => get<ChapterIndexItem[]>(`/books/${slug}/chapters`),
  chapter: (slug: string, n: number) =>
    get<ChapterDocument>(`/books/${slug}/chapters/${n}`),
  enrichment: (slug: string, n: number) =>
    get<LessonEnrichment>(`/books/${slug}/chapters/${n}/enrichment`),
  essayFeedback: (slug: string, n: number, prompt: string, essay: string, promptType?: string) =>
    post<EssayFeedback>(`/books/${slug}/chapters/${n}/essay-feedback`, {
      prompt,
      essay,
      prompt_type: promptType ?? null,
    }),
  essayPrompts: () => get<EssayPrompt[]>('/essay-prompts'),
  essayAttempts: (slug: string) => get<EssayAttempt[]>(`/books/${slug}/essay-attempts`),
  essayAttempt: (slug: string, id: number) =>
    get<EssayAttemptDetail>(`/books/${slug}/essay-attempts/${id}`),
}
