import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ClipboardCheck,
  Clock,
  ListChecks,
  Lightbulb,
  PenLine,
  ShieldCheck,
  Target,
} from 'lucide-react'
import { BookOpen, Sparkles } from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import { textOf, type ChapterIndexItem } from '../lib/types'
import { Section } from '../components/Section'
import { GroundedText } from '../components/GroundedText'
import { CoachView } from '../components/CoachView'

export function ChapterReader({ chapters }: { chapters: ChapterIndexItem[] }) {
  const { slug = 'pte', n } = useParams()
  const number = Number(n)
  const { data, loading, error } = useAsync(() => api.chapter(slug, number), [slug, number])

  // A lesson with a teaching layer gets a "Coach" view; default to it.
  const idxItem = chapters.find((c) => c.chapter_number === number)
  const hasCoach = !!idxItem?.has_enrichment
  const enrich = useAsync(
    () => (hasCoach ? api.enrichment(slug, number) : Promise.resolve(null)),
    [slug, number, hasCoach],
  )
  const [view, setView] = useState<'lesson' | 'coach'>('lesson')
  useEffect(() => {
    setView(hasCoach ? 'coach' : 'lesson')
  }, [number, hasCoach])

  // Scroll to top on lesson change (state-preservation / predictable nav).
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [slug, number, view])

  if (loading) return <ReaderSkeleton />
  if (error || !data)
    return (
      <Centered>
        <p className="text-slate-600">Couldn’t load this lesson.</p>
        <p className="mt-1 text-sm text-slate-400">{error}</p>
      </Centered>
    )

  const chapter = data.learning_materials.chapters[0]
  const idx = chapters.findIndex((c) => c.chapter_number === number)
  const prev = idx > 0 ? chapters[idx - 1] : undefined
  const next = idx >= 0 && idx < chapters.length - 1 ? chapters[idx + 1] : undefined
  const studyTime = textOf(chapter.estimated_study_time)

  const tabs = hasCoach ? (
    <div className="sticky top-0 z-10 border-b border-slate-200 bg-slate-50/90 backdrop-blur lg:top-0">
      <div className="mx-auto flex max-w-3xl gap-1 px-5 py-2 sm:px-8">
        <ViewTab active={view === 'coach'} onClick={() => setView('coach')} icon={Sparkles} label="Coach" />
        <ViewTab active={view === 'lesson'} onClick={() => setView('lesson')} icon={BookOpen} label="From the book" />
      </div>
    </div>
  ) : null

  if (view === 'coach') {
    return (
      <>
        {tabs}
        {enrich.loading ? <ReaderSkeleton /> : enrich.data ? <CoachView e={enrich.data} /> : <ReaderSkeleton />}
      </>
    )
  }

  return (
    <>
    {tabs}
    <article className="reading mx-auto max-w-3xl px-5 py-8 sm:px-8">
      {/* Lesson header */}
      <header className="animate-rise">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
          <span className="font-medium text-brand-700">
            Lesson {number} of {chapters.length}
          </span>
          {studyTime && (
            <span className="inline-flex items-center gap-1.5">
              <Clock className="size-4" aria-hidden="true" />
              {studyTime}
            </span>
          )}
        </div>
        <h1 className="mt-2 text-3xl font-bold leading-tight tracking-tight sm:text-4xl">
          {chapter.chapter_title}
        </h1>
        {chapter.chapter_summary?.text && (
          <p className="mt-4 text-lg leading-relaxed text-slate-600">
            {chapter.chapter_summary.text}
          </p>
        )}
        <GroundingLegend />
      </header>

      <div className="mt-6 space-y-8">
        {chapter.learning_objectives.length > 0 && (
          <Section icon={Target} title="What you’ll learn" purpose="Goals for this lesson.">
            <ul className="space-y-2.5">
              {chapter.learning_objectives.map((o, i) =>
                o.text ? (
                  <li key={i} className="flex gap-3">
                    <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-brand-600" aria-hidden="true" />
                    <GroundedText g={o} as="span" className="flex-1" />
                  </li>
                ) : null,
              )}
            </ul>
          </Section>
        )}

        {chapter.key_terms.length > 0 && (
          <Section icon={ListChecks} title="Key terms" purpose="The vocabulary this lesson uses.">
            <dl className="space-y-5">
              {chapter.key_terms.map((t, i) => (
                <div key={i} className="rounded-xl bg-white p-4 ring-1 ring-slate-200/70">
                  <dt className="font-display font-semibold text-slate-900">{t.term}</dt>
                  <dd className="mt-1">
                    <GroundedText g={t.meaning} />
                  </dd>
                </div>
              ))}
            </dl>
          </Section>
        )}

        {chapter.core_lessons.length > 0 && (
          <Section icon={Lightbulb} title="Core lessons" purpose="The main teaching, step by step.">
            <div className="space-y-6">
              {chapter.core_lessons.map((l, i) =>
                l.explanation?.text ? (
                  <div key={i}>
                    <h3 className="mb-1.5 font-display text-base font-semibold text-slate-900">
                      {l.title}
                    </h3>
                    <GroundedText g={l.explanation} />
                  </div>
                ) : null,
              )}
            </div>
          </Section>
        )}

        {chapter.worked_examples.length > 0 && (
          <Section icon={PenLine} title="Worked examples" purpose="See the strategy applied.">
            <div className="space-y-5">
              {chapter.worked_examples.map((w, i) => (
                <div key={i} className="rounded-xl border border-slate-200 bg-white p-5">
                  <h3 className="mb-2 font-display text-base font-semibold text-slate-900">
                    {w.title}
                  </h3>
                  {w.example?.text && (
                    <div className="rounded-lg bg-slate-50 p-3 text-[15px] text-slate-700 ring-1 ring-slate-200/60">
                      <GroundedText g={w.example} />
                    </div>
                  )}
                  {w.explanation?.text && (
                    <div className="mt-3">
                      <GroundedText g={w.explanation} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {chapter.common_misconceptions.some((m) => m.misconception?.text || m.correction?.text) && (
          <Section icon={AlertTriangle} title="Common mistakes" purpose="What to avoid, and what’s true instead.">
            <div className="space-y-4">
              {chapter.common_misconceptions.map((m, i) =>
                m.misconception?.text || m.correction?.text ? (
                  <div key={i} className="overflow-hidden rounded-xl ring-1 ring-slate-200">
                    {m.misconception?.text && (
                      <div className="flex gap-3 bg-rose-50/70 p-4">
                        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-rose-500" aria-hidden="true" />
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-wide text-rose-600">
                            Common mistake
                          </p>
                          <p className="mt-0.5 text-slate-700">{m.misconception.text}</p>
                        </div>
                      </div>
                    )}
                    {m.correction?.text && (
                      <div className="flex gap-3 border-t border-slate-200 bg-emerald-50/60 p-4">
                        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-emerald-600" aria-hidden="true" />
                        <div className="flex-1">
                          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
                            What’s true
                          </p>
                          <GroundedText g={m.correction} className="mt-0.5" />
                        </div>
                      </div>
                    )}
                  </div>
                ) : null,
              )}
            </div>
          </Section>
        )}

        {chapter.practice_questions.some((p) => p.question?.text) && (
          <Section icon={ClipboardCheck} title="Practice" purpose="Try it, then reveal the answer.">
            <ol className="space-y-3">
              {chapter.practice_questions.map((p, i) =>
                p.question?.text ? <PracticeItem key={i} index={i + 1} q={p} /> : null,
              )}
            </ol>
          </Section>
        )}

        {chapter.review_checklist.some((r) => r.text) && (
          <Section icon={ShieldCheck} title="Check yourself" purpose="Can you do each of these?">
            <ul className="space-y-2">
              {chapter.review_checklist.map((r, i) =>
                r.text ? <ChecklistItem key={i} text={r.text} /> : null,
              )}
            </ul>
          </Section>
        )}
      </div>

      {/* Prev / next */}
      <nav className="mt-12 flex items-stretch justify-between gap-3 border-t border-slate-200 pt-6">
        {prev ? (
          <PagerLink to={`/books/${slug}/lessons/${prev.chapter_number}`} dir="prev" item={prev} />
        ) : (
          <span />
        )}
        {next ? (
          <PagerLink to={`/books/${slug}/lessons/${next.chapter_number}`} dir="next" item={next} />
        ) : (
          <span />
        )}
      </nav>
    </article>
    </>
  )
}

function ViewTab({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: typeof Sparkles
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
        active ? 'bg-brand-700 text-white' : 'text-slate-500 hover:bg-slate-200/60'
      }`}
    >
      <Icon className="size-4" aria-hidden="true" />
      {label}
    </button>
  )
}

function GroundingLegend() {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-lg bg-white px-3.5 py-2.5 text-xs text-slate-500 ring-1 ring-slate-200/70">
      <span className="font-medium text-slate-600">How to read this:</span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-full bg-emerald-500" />
        <span className="text-emerald-700">“From the book”</span> = traceable to the source
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-full bg-amber-400" />
        <span className="text-amber-700">Practice</span> = written for you to train with
      </span>
    </div>
  )
}

function PracticeItem({ index, q }: { index: number; q: { question: any; answer: any } }) {
  const [show, setShow] = useState(false)
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex gap-3">
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-brand-50 text-xs font-semibold text-brand-700 tabular-nums">
          {index}
        </span>
        <p className="flex-1 text-slate-800">{q.question.text}</p>
      </div>
      {q.answer?.text && (
        <div className="mt-3 pl-9">
          {show ? (
            <div className="animate-rise rounded-lg bg-emerald-50/70 p-3 ring-1 ring-emerald-200/60">
              <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Answer</p>
              <GroundedText g={q.answer} className="mt-0.5" />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShow(true)}
              className="cursor-pointer rounded-lg px-3 py-1.5 text-sm font-medium text-brand-700 ring-1 ring-brand-200 transition-colors hover:bg-brand-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
            >
              Show answer
            </button>
          )}
        </div>
      )}
    </li>
  )
}

function ChecklistItem({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <li>
      <button
        type="button"
        onClick={() => setDone((v) => !v)}
        className="flex w-full cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-slate-100"
        aria-pressed={done}
      >
        <span
          className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
            done ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white'
          }`}
        >
          {done && <CheckCircle2 className="size-4" aria-hidden="true" />}
        </span>
        <span className={done ? 'text-slate-400 line-through' : 'text-slate-700'}>{text}</span>
      </button>
    </li>
  )
}

function PagerLink({
  to,
  dir,
  item,
}: {
  to: string
  dir: 'prev' | 'next'
  item: ChapterIndexItem
}) {
  const isNext = dir === 'next'
  return (
    <Link
      to={to}
      className={`group flex max-w-[46%] flex-col gap-0.5 rounded-xl border border-slate-200 bg-white px-4 py-3 transition-colors hover:border-brand-300 hover:bg-brand-50/40 ${
        isNext ? 'items-end text-right' : 'items-start'
      }`}
    >
      <span className="inline-flex items-center gap-1 text-xs text-slate-400">
        {!isNext && <ArrowLeft className="size-3.5" aria-hidden="true" />}
        {isNext ? 'Next' : 'Previous'}
        {isNext && <ArrowRight className="size-3.5" aria-hidden="true" />}
      </span>
      <span className="line-clamp-1 text-sm font-medium text-slate-700 group-hover:text-brand-800">
        {item.chapter_title}
      </span>
    </Link>
  )
}

function ReaderSkeleton() {
  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <div className="h-4 w-28 animate-pulse rounded bg-slate-200" />
      <div className="mt-3 h-9 w-3/4 animate-pulse rounded bg-slate-200" />
      <div className="mt-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-4 w-full animate-pulse rounded bg-slate-100" />
        ))}
      </div>
    </div>
  )
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-3xl px-5 py-20 text-center">{children}</div>
}
