import { useState } from 'react'
import { Navigate, Route, Routes, useParams } from 'react-router-dom'
import { GraduationCap, Menu } from 'lucide-react'
import { api } from './lib/api'
import { useAsync } from './lib/useAsync'
import { Sidebar } from './components/Sidebar'
import { Home } from './pages/Home'
import { ChapterReader } from './pages/ChapterReader'

export default function App() {
  const books = useAsync(() => api.books(), [])
  const slug = books.data?.[0]?.slug

  if (books.loading) return <FullScreen>Loading…</FullScreen>
  if (books.error || !slug)
    return (
      <FullScreen>
        <p className="font-medium text-slate-700">Can’t reach the learning API.</p>
        <p className="mt-1 text-sm text-slate-400">
          Start it with <code className="rounded bg-slate-100 px-1.5 py-0.5">uvicorn learning_materials_api:app</code>
        </p>
      </FullScreen>
    )

  return <Shell slug={slug} />
}

function Shell({ slug }: { slug: string }) {
  const chapters = useAsync(() => api.chapterIndex(slug), [slug])
  const [navOpen, setNavOpen] = useState(false)

  if (chapters.loading) return <FullScreen>Loading lessons…</FullScreen>
  const list = chapters.data ?? []

  return (
    <div className="min-h-dvh lg:flex">
      <Routes>
        {/* Sidebar shares the active-lesson highlight via the route param. */}
        <Route
          path="/books/:slug/lessons/:n"
          element={
            <SidebarWithActive slug={slug} chapters={list} open={navOpen} onClose={() => setNavOpen(false)} />
          }
        />
        <Route
          path="*"
          element={
            <Sidebar slug={slug} chapters={list} open={navOpen} onClose={() => setNavOpen(false)} />
          }
        />
      </Routes>

      <div className="flex min-w-0 flex-1 flex-col">
        <MobileBar onMenu={() => setNavOpen(true)} />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Navigate to={`/books/${slug}`} replace />} />
            <Route path="/books/:slug" element={<Home slug={slug} chapters={list} />} />
            <Route path="/books/:slug/lessons/:n" element={<ChapterReader chapters={list} />} />
            <Route path="*" element={<Navigate to={`/books/${slug}`} replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

function SidebarWithActive(props: {
  slug: string
  chapters: React.ComponentProps<typeof Sidebar>['chapters']
  open: boolean
  onClose: () => void
}) {
  const { n } = useParams()
  return <Sidebar {...props} activeNumber={Number(n)} />
}

function MobileBar({ onMenu }: { onMenu: () => void }) {
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
        PTE Learn
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
