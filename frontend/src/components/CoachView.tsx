import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  Info,
  LayoutTemplate,
  Lightbulb,
  ListChecks,
  MessageSquareQuote,
  PenLine,
  ShieldCheck,
  Target,
  Timer,
} from 'lucide-react'
import type { LangCategory, LessonEnrichment } from '../lib/types'
import { Section } from './Section'

/** Safe-array: tolerate fields the model sometimes omits or shapes differently,
 * so a single lesson can never crash the view. */
const A = <T,>(x: T[] | undefined | null): T[] => (Array.isArray(x) ? x : [])

/** Render a model answer: "/" marks chunk pauses; ALL-CAPS words are the stressed
 * words (shown bold, not shouting). A small key explains the convention. */
function ModelAnswer({ text }: { text: string }) {
  const chunks = text.split('/').map((c) => c.trim()).filter(Boolean)
  return (
    <span className="font-medium text-slate-800">
      {chunks.map((chunk, ci) => (
        <span key={ci}>
          {ci > 0 && <span className="mx-1.5 text-brand-400" aria-hidden="true">·</span>}
          {chunk.split(/(\s+)/).map((tok, ti) =>
            /^[A-Z][A-Z'’-]{1,}[.?!,]?$/.test(tok.trim()) ? (
              <strong key={ti} className="font-semibold text-brand-800">{tok}</strong>
            ) : (
              <span key={ti}>{tok}</span>
            ),
          )}
        </span>
      ))}
    </span>
  )
}

/** Keep only well-formed useful_language categories (a category object with items). */
const validLangCats = (cats: LangCategory[] | undefined) =>
  A(cats).filter((c) => c && typeof c === 'object' && A(c.items).length > 0)

/** The reusable sentence-stem toolkit, grouped by category. */
function LanguageGrid({ cats }: { cats: LangCategory[] }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {cats.map((cat, i) => (
        <div key={i} className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="font-display text-sm font-semibold text-slate-900">{cat.category}</h3>
          <ul className="mt-2 space-y-2">
            {A(cat.items).map((it, ii) => (
              <li key={ii} className="text-sm">
                <span className="font-medium text-slate-800">{it.item}</span>
                <span className="block text-xs text-slate-500">{it.when_to_use}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

/** Render the core_method.formula as a memorisable pattern: split on its → or +
 * separators into ordered slots, and highlight any [bracketed] fill-in blanks. */
function TemplatePattern({ formula }: { formula: string }) {
  const arrow = formula.includes('→')
  const parts = (arrow ? formula.split('→') : formula.includes(' + ') ? formula.split(' + ') : [formula])
    .map((p) => p.trim())
    .filter(Boolean)

  const renderSlots = (text: string) =>
    text.split(/(\[[^\]]+\])/).map((tok, i) =>
      /^\[[^\]]+\]$/.test(tok) ? (
        <span key={i} className="mx-0.5 rounded bg-brand-100 px-1.5 py-0.5 text-sm font-semibold text-brand-800">
          {tok.slice(1, -1)}
        </span>
      ) : (
        <span key={i}>{tok}</span>
      ),
    )

  if (parts.length === 1) {
    return <p className="text-[15px] leading-relaxed text-slate-800">{renderSlots(parts[0])}</p>
  }
  return (
    <ol className="space-y-2">
      {parts.map((p, i) => (
        <li key={i} className="flex gap-3">
          <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-brand-700 text-xs font-bold text-white tabular-nums">
            {i + 1}
          </span>
          <span className="text-[15px] leading-snug text-slate-800">{renderSlots(p)}</span>
        </li>
      ))}
    </ol>
  )
}

export function CoachView({ e }: { e: LessonEnrichment }) {
  const formula = e.core_method?.formula?.trim() || ''
  const langCats = validLangCats(e.useful_language)
  // Productive tasks have a reusable scaffold: surface it as one consolidated
  // "template" block (pattern + fill-in phrases) instead of splitting the pattern
  // (hero) from the phrases (a section far below).
  const hasTemplate = formula.length > 0

  return (
    <article className="reading mx-auto max-w-3xl px-5 py-8 sm:px-8">
      {/* Method hero */}
      <header className="animate-rise rounded-2xl bg-gradient-to-br from-brand-700 to-brand-900 p-6 text-white sm:p-8">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-white/15 px-3 py-1 text-xs font-medium">
          <Compass className="size-3.5" aria-hidden="true" /> The method
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold sm:text-3xl">{e.core_method?.name}</h1>
        <p className="mt-2 max-w-xl text-brand-50/90">{e.core_method?.summary}</p>
        {formula && !hasTemplate && (
          <div className="mt-4 rounded-lg bg-white/10 px-4 py-3 text-center text-sm font-semibold tracking-wide ring-1 ring-white/15">
            {formula}
          </div>
        )}
        {A(e.core_method?.steps).length > 0 && (
          <ol className="mt-5 grid gap-2.5 sm:grid-cols-2">
            {A(e.core_method?.steps).map((s, i) => (
              <li key={i} className="flex gap-3 rounded-lg bg-white/10 p-3">
                <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-white/20 text-xs font-bold tabular-nums">
                  {i + 1}
                </span>
                <span>
                  <span className="font-semibold">{s.step}</span>
                  <span className="block text-sm text-brand-50/85">{s.detail}</span>
                </span>
              </li>
            ))}
          </ol>
        )}
      </header>

      <div className="mt-8 space-y-8">
        {/* Reusable template — the highest-leverage, memorisable scaffold, kept
            with the phrases that fill it. Only for tasks that have a formula. */}
        {hasTemplate && (
          <Section
            icon={LayoutTemplate}
            title="Your reusable template"
            purpose="Memorise this shape and drop any prompt into it — the pattern stays the same, only the details change."
          >
            <div className="rounded-xl border border-brand-200 bg-brand-50/60 p-4 sm:p-5">
              <p className="mb-2.5 text-xs font-semibold uppercase tracking-wide text-brand-700">The pattern</p>
              <TemplatePattern formula={formula} />
            </div>
            {langCats.length > 0 && (
              <div className="mt-5">
                <p className="mb-2 text-sm font-semibold text-slate-700">
                  Phrases to fill it
                  <span className="ml-2 font-normal text-slate-400">— drop these into the slots above</span>
                </p>
                <LanguageGrid cats={langCats} />
              </div>
            )}
          </Section>
        )}

        {/* Overview */}
        <Section icon={Info} title="What this task is" purpose="Format, scoring, and the rules that matter.">
          <p>{e.overview?.what_it_is}</p>
          {A(e.overview?.format_facts).length > 0 && (
            <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {A(e.overview?.format_facts).map((f, i) => (
                <div key={i} className="rounded-xl bg-white p-3 ring-1 ring-slate-200/70">
                  <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{f.label}</dt>
                  <dd className="mt-0.5 text-sm font-semibold text-slate-800">{f.value}</dd>
                </div>
              ))}
            </dl>
          )}
          {A(e.overview?.scoring_factors).length > 0 && (
            <div className="mt-4">
              <h3 className="mb-1.5 text-sm font-semibold text-slate-700">How it's scored</h3>
              <ul className="space-y-1.5">
                {A(e.overview?.scoring_factors).map((s, i) => (
                  <li key={i} className="text-sm text-slate-600">
                    <span className="font-medium text-slate-800">{s.name}:</span> {s.what_it_measures}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {A(e.overview?.critical_rules).length > 0 && (
            <ul className="mt-4 space-y-2 rounded-xl border-l-3 border-amber-400 bg-amber-50/60 p-4">
              {A(e.overview?.critical_rules).map((r, i) => (
                <li key={i} className="flex gap-2 text-sm text-amber-900">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" aria-hidden="true" />
                  {r}
                </li>
              ))}
            </ul>
          )}
        </Section>

        {A(e.learning_goals).length > 0 && (
          <Section icon={Target} title="What you'll be able to do" purpose="Goals for this lesson.">
            <ul className="space-y-2">
              {A(e.learning_goals).map((g, i) => (
                <li key={i} className="flex gap-3">
                  <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-brand-600" aria-hidden="true" />
                  <span>{g}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {/* Techniques */}
        {A(e.techniques).length > 0 && (
          <Section icon={Lightbulb} title="Techniques" purpose="The how-to, step by step.">
            <div className="space-y-4">
              {A(e.techniques).map((t, i) => (
                <details key={i} className="group rounded-xl border border-slate-200 bg-white" open={i === 0}>
                  <summary className="flex cursor-pointer items-start gap-3 p-4 [&::-webkit-details-marker]:hidden">
                    <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-brand-50 text-xs font-bold text-brand-700 tabular-nums">
                      {i + 1}
                    </span>
                    <span className="flex-1">
                      <span className="font-display font-semibold text-slate-900">{t.name}</span>
                      <span className="block text-sm text-slate-500">{t.purpose}</span>
                    </span>
                  </summary>
                  <div className="space-y-3 border-t border-slate-100 px-4 pb-4 pt-3 text-sm">
                    {A(t.how_to).length > 0 && (
                      <ol className="ml-1 space-y-1.5">
                        {A(t.how_to).map((h, hi) => (
                          <li key={hi} className="flex gap-2">
                            <span className="mt-1 size-1.5 shrink-0 rounded-full bg-brand-400" />
                            <span>{h}</span>
                          </li>
                        ))}
                      </ol>
                    )}
                    {t.example && (
                      <p className="rounded-lg bg-slate-50 p-3 text-slate-700 ring-1 ring-slate-200/60">
                        <span className="font-medium text-slate-500">Example — </span>{t.example}
                      </p>
                    )}
                    {t.why_it_matters && <p className="text-slate-600"><span className="font-medium text-brand-700">Why it matters:</span> {t.why_it_matters}</p>}
                    {t.common_error && <p className="text-slate-600"><span className="font-medium text-rose-600">Watch out:</span> {t.common_error}</p>}
                  </div>
                </details>
              ))}
            </div>
          </Section>
        )}

        {/* Worked examples */}
        {A(e.worked_examples).length > 0 && (
          <Section icon={PenLine} title="Worked examples" purpose="See the method applied.">
            <p className="mb-3 inline-flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg bg-white px-3 py-2 text-xs text-slate-500 ring-1 ring-slate-200/70">
              <span className="font-medium text-slate-600">Model answers:</span>
              <span><span className="text-brand-400">·</span> = short pause between chunks</span>
              <span><strong className="text-brand-800">bold</strong> = stressed word</span>
            </p>
            <div className="space-y-4">
              {A(e.worked_examples).map((w, i) => (
                <div key={i} className="rounded-xl border border-slate-200 bg-white p-5">
                  <h3 className="font-display text-base font-semibold text-slate-900">{w.title}</h3>
                  <div className="mt-2 rounded-lg bg-slate-50 p-3 text-[15px] text-slate-700 ring-1 ring-slate-200/60">
                    <span className="text-xs font-medium uppercase tracking-wide text-slate-400">Question</span>
                    <p className="mt-0.5">{w.input}</p>
                  </div>
                  {w.decoding && <p className="mt-3 text-sm text-slate-600"><span className="font-medium text-slate-700">Decode: </span>{w.decoding}</p>}
                  {w.plan && <p className="mt-1.5 text-sm text-slate-600"><span className="font-medium text-slate-700">Plan: </span>{w.plan}</p>}
                  {typeof w.model_answer === 'string' && w.model_answer && (
                    <div className="mt-3 flex items-center gap-2 rounded-lg bg-emerald-50/70 px-3 py-2.5 ring-1 ring-emerald-200/60">
                      <MessageSquareQuote className="size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                      <ModelAnswer text={w.model_answer} />
                    </div>
                  )}
                  {A(w.annotations).length > 0 && (
                    <ul className="mt-3 grid gap-2 sm:grid-cols-3">
                      {A(w.annotations).map((a, ai) => (
                        <li key={ai} className="rounded-lg bg-slate-50 p-2.5 text-xs ring-1 ring-slate-200/50">
                          <span className="font-semibold text-brand-700">{a.part}</span>
                          <span className="mt-0.5 block text-slate-500">{a.comment}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Useful language */}
        {/* When there is no template, the phrases stand alone; otherwise they're
            shown inside the template block above. */}
        {!hasTemplate && langCats.length > 0 && (
          <Section icon={MessageSquareQuote} title="Useful language" purpose="A toolkit you can reuse.">
            <LanguageGrid cats={langCats} />
          </Section>
        )}

        {/* Common mistakes */}
        {A(e.common_mistakes).length > 0 && (
          <Section icon={AlertTriangle} title="Common mistakes" purpose="What to avoid, and how to fix it.">
            <div className="space-y-3">
              {A(e.common_mistakes).map((m, i) => (
                <div key={i} className="overflow-hidden rounded-xl ring-1 ring-slate-200">
                  <div className="flex gap-3 bg-rose-50/70 p-3.5">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-500" aria-hidden="true" />
                    <div>
                      <p className="font-medium text-slate-800">{m.mistake}</p>
                      <p className="mt-0.5 text-sm text-slate-500">{m.why_it_hurts}</p>
                    </div>
                  </div>
                  <div className="flex gap-3 border-t border-slate-200 bg-emerald-50/60 p-3.5">
                    <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                    <p className="text-sm text-slate-700"><span className="font-medium text-emerald-700">Fix: </span>{m.fix}</p>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Practice plan */}
        {(A(e.practice_plan?.time_budget).length > 0 || A(e.practice_plan?.drills).length > 0 || e.practice_plan?.routine) && (
        <Section icon={Timer} title="Practice plan" purpose="Turn the method into a routine.">
          {A(e.practice_plan?.time_budget).length > 0 && (
            <ol className="space-y-2">
              {A(e.practice_plan?.time_budget).map((p, i) => (
                <li key={i} className="flex items-center gap-3 rounded-lg bg-white p-3 ring-1 ring-slate-200/60">
                  <span className="flex w-14 shrink-0 items-center justify-center rounded-md bg-brand-50 py-1 text-xs font-semibold text-brand-700 tabular-nums">
                    {p.minutes} min
                  </span>
                  <span>
                    <span className="font-medium text-slate-800">{p.phase}</span>
                    <span className="block text-sm text-slate-500">{p.focus}</span>
                  </span>
                </li>
              ))}
            </ol>
          )}
          {A(e.practice_plan?.drills).length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">Drills</h3>
              <div className="space-y-2">
                {A(e.practice_plan?.drills).map((d, i) => (
                  <details key={i} className="rounded-lg border border-slate-200 bg-white">
                    <summary className="cursor-pointer p-3 text-sm font-medium text-slate-800 [&::-webkit-details-marker]:hidden">
                      {d.name}
                    </summary>
                    <p className="border-t border-slate-100 p-3 pt-2 text-sm text-slate-600">{d.instructions}</p>
                  </details>
                ))}
              </div>
            </div>
          )}
          {e.practice_plan?.routine && (
            <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600 ring-1 ring-slate-200/60">
              <span className="font-medium text-slate-700">Routine: </span>{e.practice_plan.routine}
            </p>
          )}
        </Section>
        )}

        {A(e.mastery_checklist).length > 0 && (
          <Section icon={ShieldCheck} title="Check yourself" purpose="Can you do each of these?">
            <ul className="space-y-2">
              {A(e.mastery_checklist).map((c, i) => (
                <CheckItem key={i} text={c} />
              ))}
            </ul>
          </Section>
        )}

        {A(e.strategy_notes).length > 0 && (
          <Section icon={ClipboardCheck} title="Exam strategy" purpose="Tips for test day.">
            <ul className="space-y-2">
              {A(e.strategy_notes).map((s, i) => (
                <li key={i} className="flex gap-3 text-slate-600">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand-400" />
                  <span>{s}</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {e.metadata?.provenance_note && (
          <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4 text-xs leading-relaxed text-slate-500">
            <span className="font-medium text-slate-600">How this was made: </span>{e.metadata.provenance_note}
          </p>
        )}
      </div>
    </article>
  )
}

function CheckItem({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <li>
      <button
        type="button"
        onClick={() => setDone((v) => !v)}
        aria-pressed={done}
        className="flex w-full cursor-pointer items-start gap-3 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-slate-100"
      >
        <span className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors ${done ? 'border-brand-600 bg-brand-600 text-white' : 'border-slate-300 bg-white'}`}>
          {done && <ListChecks className="size-3.5" aria-hidden="true" />}
        </span>
        <span className={done ? 'text-slate-400 line-through' : 'text-slate-700'}>{text}</span>
      </button>
    </li>
  )
}
