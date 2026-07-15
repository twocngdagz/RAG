import { Link } from 'react-router-dom'
import { ArrowRight, BookOpenCheck, ShieldCheck, Sparkles } from 'lucide-react'
import type { ChapterIndexItem } from '../lib/types'

/** Orientation screen: what this is, why it’s trustworthy, and a clear way in.
 * One primary action (Start), lessons listed for direct access. */
export function Home({ slug, chapters }: { slug: string; chapters: ChapterIndexItem[] }) {
  const first = chapters[0]
  return (
    <div className="mx-auto max-w-3xl px-5 py-12 sm:px-8 sm:py-16">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
          <BookOpenCheck className="size-3.5" aria-hidden="true" />
          Grounded study materials
        </span>
        <h1 className="mt-4 text-4xl font-bold leading-[1.1] tracking-tight text-slate-900 sm:text-5xl">
          Study PTE Academic with materials you can trust.
        </h1>
        <p className="mt-4 max-w-xl text-lg leading-relaxed text-slate-600">
          {chapters.length} lessons built from the official course — every explanation is traceable
          back to the source text, so you always know what’s fact and what’s practice.
        </p>
        {first && (
          <Link
            to={`/books/${slug}/lessons/${first.chapter_number}`}
            className="mt-7 inline-flex items-center gap-2 rounded-xl bg-brand-700 px-5 py-3 font-medium text-white shadow-sm transition-colors hover:bg-brand-800 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-700"
          >
            Start with Lesson 1
            <ArrowRight className="size-4.5" aria-hidden="true" />
          </Link>
        )}
      </header>

      <div className="mt-10 grid gap-4 sm:grid-cols-2">
        <Feature
          icon={ShieldCheck}
          title="Source-backed"
          body="Key facts show the exact quote they come from — one tap to verify."
        />
        <Feature
          icon={Sparkles}
          title="Built to practise"
          body="Worked examples and practice questions to actively train each skill."
        />
      </div>

      <section className="mt-12">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">All lessons</h2>
        <ol className="mt-3 divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 bg-white">
          {chapters.map((c) => (
            <li key={c.id}>
              <Link
                to={`/books/${slug}/lessons/${c.chapter_number}`}
                className="group flex items-center gap-4 px-4 py-3 transition-colors hover:bg-brand-50/40"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-sm font-semibold text-slate-500 tabular-nums group-hover:bg-brand-100 group-hover:text-brand-700">
                  {c.chapter_number}
                </span>
                <span className="flex-1 text-slate-700 group-hover:text-brand-800">
                  {c.chapter_title}
                </span>
                <ArrowRight
                  className="size-4 text-slate-300 transition-transform group-hover:translate-x-0.5 group-hover:text-brand-500"
                  aria-hidden="true"
                />
              </Link>
            </li>
          ))}
        </ol>
      </section>
    </div>
  )
}

function Feature({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof ShieldCheck
  title: string
  body: string
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <span className="flex size-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-100">
        <Icon className="size-5" aria-hidden="true" />
      </span>
      <h3 className="mt-3 font-display font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 text-sm leading-relaxed text-slate-600">{body}</p>
    </div>
  )
}
