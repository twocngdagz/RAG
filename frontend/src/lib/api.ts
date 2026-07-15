import type { BookInfo, ChapterDocument, ChapterIndexItem, LessonEnrichment } from './types'

// Same-origin /api in dev (Vite proxies to FastAPI:8000). Override for prod.
const BASE = import.meta.env.VITE_API_BASE ?? '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} for ${path}`)
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
}
