import { NavLink } from 'react-router-dom'
import { GraduationCap, X } from 'lucide-react'
import type { ChapterIndexItem } from '../lib/types'

/** Lesson navigation. Persistent rail on desktop, dismissible drawer on mobile.
 * The current lesson is highlighted (nav-state-active) and every item is a
 * deep-linkable route (deep-linking). */
export function Sidebar({
  slug,
  chapters,
  activeNumber,
  open,
  onClose,
}: {
  slug: string
  chapters: ChapterIndexItem[]
  activeNumber?: number
  open: boolean
  onClose: () => void
}) {
  return (
    <>
      {/* Mobile scrim */}
      {open && (
        <div
          className="fixed inset-0 z-30 bg-slate-900/40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-200 bg-white transition-transform duration-200 lg:sticky lg:top-0 lg:h-dvh lg:translate-x-0 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Lessons"
      >
        <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-5 py-4">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="flex size-8 items-center justify-center rounded-lg bg-brand-700 text-white">
              <GraduationCap className="size-5" aria-hidden="true" />
            </span>
            <span className="font-display text-base font-semibold text-slate-900">
              PTE&nbsp;Learn
            </span>
          </NavLink>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-500 hover:bg-slate-100 lg:hidden"
            aria-label="Close lessons"
          >
            <X className="size-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            {chapters.length} lessons
          </p>
          <ul className="space-y-0.5">
            {chapters.map((c) => (
              <li key={c.id}>
                <NavLink
                  to={`/books/${slug}/lessons/${c.chapter_number}`}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `flex items-start gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                      isActive || c.chapter_number === activeNumber
                        ? 'bg-brand-50 text-brand-800'
                        : 'text-slate-600 hover:bg-slate-100'
                    }`
                  }
                >
                  <span
                    className={`mt-px flex size-5 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold tabular-nums ${
                      c.chapter_number === activeNumber
                        ? 'bg-brand-700 text-white'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {c.chapter_number}
                  </span>
                  <span className="leading-snug">{c.chapter_title}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
    </>
  )
}
