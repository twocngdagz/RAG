import { useState } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { GraduationCap, Menu } from 'lucide-react'
import { api } from './lib/api'
import { useAsync } from './lib/useAsync'
import type { BookInfo } from './lib/types'
import { Sidebar, bookLabel } from './components/Sidebar'
import { Home } from './pages/Home'
import { ChapterReader } from './pages/ChapterReader'

export default function App() {
  const books = useAsync(() => api.books(), [])
  const fallback = books.data?.[0]?.slug

  if (books.loading) return <FullScreen>Loading…</FullScreen>
  if (books.error || !fallback)
    return (
      <FullScreen>
        <p className="font-medium text-slate-700">Can’t reach the learning API.</p>
        <p className="mt-1 text-sm text-slate-400">
          Start it with <code className="rounded bg-slate-100 px-1.5 py-0.5">uvicorn learning_materials_api:app</code>
        </p>
      </FullScreen>
    )

  return (
    <Routes>
      {/* The URL owns which book is open; "/" and unknown paths go to the first book. */}
      <Route path="/books/:slug/*" element={<Shell books={books.data!} />} />
      <Route path="*" element={<Navigate to={`/books/${fallback}`} replace />} />
    </Routes>
  )
}

function Shell({ books }: { books: BookInfo[] }) {
  const { slug = books[0].slug } = useParams()
  const chapters = useAsync(() => api.chapterIndex(slug), [slug])
  const [navOpen, setNavOpen] = useState(false)

  // Unknown book in the URL → bounce to the first one.
  if (!books.some((b) => b.slug === slug)) {
    return <Navigate to={`/books/${books[0].slug}`} replace />
  }
  if (chapters.loading) return <FullScreen>Loading lessons…</FullScreen>
  const list = chapters.data ?? []

  return (
    <div className="min-h-dvh lg:flex">
      <Routes>
        {/* Sidebar shares the active-lesson highlight via the route param. */}
        <Route
          path="lessons/:n"
          element={
            <SidebarWithActive slug={slug} books={books} chapters={list} open={navOpen} onClose={() => setNavOpen(false)} />
          }
        />
        <Route
          path="*"
          element={
            <Sidebar slug={slug} books={books} chapters={list} open={navOpen} onClose={() => setNavOpen(false)} />
          }
        />
      </Routes>

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar slug={slug} onMenu={() => setNavOpen(true)} />
        <main className="flex-1">
          <Routes>
            <Route index element={<Home slug={slug} chapters={list} />} />
            <Route path="lessons/:n" element={<ChapterReader chapters={list} />} />
            <Route path="*" element={<Navigate to={`/books/${slug}`} replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function SidebarWithActive(props: {
  slug: string
  books: BookInfo[]
  chapters: React.ComponentProps<typeof Sidebar>['chapters']
  open: boolean
  onClose: () => void
}) {
  const { n } = useParams()
  return <Sidebar {...props} activeNumber={Number(n)} />
}

function MobileBar({ slug, onMenu }: { slug: string; onMenu: () => void }) {
  return (
    <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
      <button
        type="button"
        onClick={onMenu}
        className="rounded-md p-1.5 text-slate-600 hover:bg-slate-100"
        aria-label="Open lessons"
      >
        <Menu className="size-5" />
      </button>
      <span className="flex items-center gap-2 font-display font-semibold text-slate-900">
        <span className="flex size-6 items-center justify-center rounded-md bg-brand-700 text-white">
          <GraduationCap className="size-4" aria-hidden="true" />
        </span>
        {bookLabel(slug)}&nbsp;Learn
      </span>
    </header>
  )
}

function FullScreen({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh items-center justify-center px-6 text-center">
      <div>{children}</div>
    </div>
  )
}
