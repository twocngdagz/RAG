import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Info,
  Loader2,
  MinusCircle,
  PenLine,
  RotateCcw,
  Send,
  XCircle,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { DescribeImageFeedback } from '../lib/types'
import { AttemptModal, HistorySection, ScoredByNote } from './EssayPractice'

const TASK = 'describe_image'
/** A full 40-second spoken answer is roughly this many words. */
const TARGET_WORDS = [80, 120]

const countWords = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0)

function wordClass(n: number) {
  if (n === 0) return 'text-slate-400'
  if (n >= TARGET_WORDS[0] && n <= TARGET_WORDS[1]) return 'text-emerald-600'
  if (n < 40) return 'text-rose-600'
  return 'text-amber-600'
}

const mmss = (t: number) => `${Math.floor(t / 60)}:${(t % 60).toString().padStart(2, '0')}`

export function DescribeImagePractice({ slug, number }: { slug: string; number: number }) {
  const bank = useAsync(() => api.describeImageItems(), [])
  const items = bank.data ?? []

  const draftKey = `di-draft:${slug}:${number}`
  const draft0 = (() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) || '{}')
    } catch {
      return {}
    }
  })()

  const [choice, setChoice] = useState<string>(draft0.choice || '')
  const [text, setText] = useState<string>(draft0.text || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<DescribeImageFeedback | null>(null)

  const [historyVersion, setHistoryVersion] = useState(0)
  const history = useAsync(() => api.essayAttempts(slug, TASK), [slug, historyVersion])
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null)

  // Two-phase timer, like the real task: prepare, then respond.
  const [phase, setPhase] = useState<'idle' | 'prep' | 'respond'>('idle')
  const [seconds, setSeconds] = useState(0)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  const selected = items.find((i) => i.id === choice)

  useEffect(() => {
    if (items.length && !choice) setChoice(items[0].id)
  }, [items, choice])

  useEffect(() => {
    if (result) return
    const t = setTimeout(() => localStorage.setItem(draftKey, JSON.stringify({ choice, text })), 400)
    return () => clearTimeout(t)
  }, [draftKey, choice, text, result])

  useEffect(() => {
    if (phase === 'idle') return
    timer.current = setInterval(() => {
      setSeconds((s) => {
        if (s > 1) return s - 1
        // Planning rolls straight into the response window, as in the real test;
        // the response window just ends.
        if (phase === 'prep') {
          setPhase('respond')
          return selected?.speak_seconds ?? 40
        }
        setPhase('idle')
        return 0
      })
    }, 1000)
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [phase, selected])

  function startPrep() {
    setPhase('prep')
    setSeconds(selected?.prep_seconds ?? 25)
  }

  const words = countWords(text)
  const canSubmit = !!selected && words > 0 && !loading

  async function submit() {
    if (!selected) return
    setLoading(true)
    setError(null)
    setResult(null)
    setPhase('idle')
    try {
      const fb = await api.describeImageFeedback(slug, number, selected.id, text.trim())
      setResult(fb)
      localStorage.removeItem(draftKey)
      setHistoryVersion((v) => v + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setResult(null)
    setError(null)
    setText('')
    setPhase('idle')
    setSeconds(0)
    localStorage.removeItem(draftKey)
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
          <PenLine className="size-3.5" aria-hidden="true" /> Practice &amp; get feedback
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold text-slate-900 sm:text-3xl">
          Describe the image
        </h1>
        <p className="mt-2 text-slate-600">
          25 seconds to plan, then 40 seconds to describe it. Scored on{' '}
          <strong>Content&nbsp;0–6</strong> against the chart’s real data.
        </p>
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-slate-100 p-3 text-xs text-slate-600">
          <Info className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
          <span>
            Type your answer for now — speak it aloud and transcribe what you said, so the timing
            stays realistic. Oral fluency and pronunciation aren’t scored yet (they need audio).
          </span>
        </p>
      </header>

      {!result && (
        <div className="mt-6 space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <label htmlFor="di-item" className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Image
            </label>
            {bank.loading ? (
              <p className="mt-2 text-sm text-slate-400">Loading images…</p>
            ) : (
              <select
                id="di-item"
                value={choice}
                onChange={(e) => {
                  setChoice(e.target.value)
                  setPhase('idle')
                }}
                className="mt-1.5 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              >
                {items.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.chart_type} — {i.title}
                  </option>
                ))}
              </select>
            )}
            {selected && (
              <div
                className="mt-3 overflow-hidden rounded-lg ring-1 ring-slate-200/70"
                // SVG comes from our own generator, built from the item's data.
                dangerouslySetInnerHTML={{ __html: selected.svg }}
              />
            )}
          </div>

          {/* Two-phase timer */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold tabular-nums ring-1 ${
                  phase === 'respond'
                    ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
                    : phase === 'prep'
                      ? 'bg-amber-50 text-amber-700 ring-amber-200'
                      : 'bg-slate-100 text-slate-700 ring-slate-200'
                }`}
              >
                <Clock className="size-4" aria-hidden="true" />
                {phase === 'idle' ? 'ready' : `${phase === 'prep' ? 'plan' : 'speak'} ${mmss(seconds)}`}
              </span>
              <button
                type="button"
                onClick={phase === 'idle' ? startPrep : () => setPhase('idle')}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50"
              >
                {phase === 'idle' ? 'Start 25s planning' : 'Stop'}
              </button>
            </div>
            <span className={`text-sm font-semibold tabular-nums ${wordClass(words)}`}>
              {words} words
            </span>
          </div>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Describe the chart: overview, key features with values, a comparison or trend, then a closing observation…"
            className="min-h-[11rem] w-full rounded-xl border border-slate-200 p-4 leading-relaxed focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />

          {error && (
            <p className="flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700 ring-1 ring-rose-200">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}

          <button
            type="button"
            onClick={submit}
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-700 px-5 py-3 font-medium text-white shadow-sm transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? (
              <>
                <Loader2 className="size-4.5 animate-spin" aria-hidden="true" /> Scoring… (~15–25s)
              </>
            ) : (
              <>
                <Send className="size-4.5" aria-hidden="true" /> Get feedback
              </>
            )}
          </button>
        </div>
      )}

      {result && <DescribeImageReport r={result} onRetry={reset} />}

      <HistorySection attempts={history.data ?? []} onSelect={setSelectedAttempt} />
      {selectedAttempt != null && (
        <AttemptModal slug={slug} id={selectedAttempt} onClose={() => setSelectedAttempt(null)} />
      )}
    </div>
  )
}

const COVER_ICON: Record<string, typeof CheckCircle2> = {
  yes: CheckCircle2,
  partial: MinusCircle,
  no: XCircle,
}
const COVER_CLASS: Record<string, string> = {
  yes: 'text-emerald-600',
  partial: 'text-amber-500',
  no: 'text-rose-400',
}

function DescribeImageReport({ r, onRetry }: { r: DescribeImageFeedback; onRetry: () => void }) {
  const pct = r.max_content ? Math.round((100 * r.content_score) / r.max_content) : 0
  return (
    <div className="mt-6 space-y-5">
      <div className="rounded-2xl bg-gradient-to-br from-brand-700 to-brand-900 p-6 text-white">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-brand-100">Content</p>
            <p className="mt-1 font-display text-4xl font-bold tabular-nums">
              {r.content_score}
              <span className="text-2xl text-brand-100">/{r.max_content}</span>
            </p>
            <p className="mt-1 text-sm text-brand-50/80">{pct}% · not an official PTE score</p>
          </div>
          <div className="text-right text-sm text-brand-50/85">{r.word_count} words</div>
        </div>
        {r.band_reason && <p className="mt-3 text-sm text-brand-50/90">{r.band_reason}</p>}
        <p className="mt-2 text-brand-50/95">{r.one_line_verdict}</p>
      </div>

      <ScoredByNote scoredBy={r.scored_by} />

      {r.gating_applied && (
        <p className="flex items-start gap-2 rounded-xl border-l-3 border-rose-400 bg-rose-50 p-4 text-sm text-rose-800">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-500" aria-hidden="true" />
          <span>
            <strong>Content scored 0</strong>, so in the real test no further scoring happens for this
            question.
          </span>
        </p>
      )}

      {/* Fact coverage */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="font-display text-sm font-semibold text-slate-900">What you covered</h3>
          <span className="text-xs text-slate-500 tabular-nums">
            {r.coverage.essential_covered}/{r.coverage.essential_total} essential ·{' '}
            {r.coverage.supporting_covered}/{r.coverage.supporting_total} supporting
          </span>
        </div>
        <ul className="mt-3 space-y-2">
          {r.facts.map((f) => {
            const Icon = COVER_ICON[f.covered] ?? XCircle
            return (
              <li key={f.key} className="flex gap-2.5 text-sm">
                <Icon className={`mt-0.5 size-4 shrink-0 ${COVER_CLASS[f.covered] ?? ''}`} aria-hidden="true" />
                <span>
                  <span className={f.importance === 'essential' ? 'text-slate-800' : 'text-slate-500'}>
                    {f.text}
                  </span>
                  {f.importance === 'supporting' && (
                    <span className="ml-1.5 rounded bg-slate-100 px-1 text-[10px] uppercase text-slate-400">
                      bonus
                    </span>
                  )}
                  {f.note && <span className="block text-xs text-slate-400">{f.note}</span>}
                </span>
              </li>
            )
          })}
        </ul>
      </div>

      {/* Structure */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="font-display text-sm font-semibold text-slate-900">Structure</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {Object.entries(r.structure).map(([k, ok]) => (
            <span
              key={k}
              className={`inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-xs font-medium ${
                ok ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-slate-100 text-slate-400'
              }`}
            >
              {ok ? <CheckCircle2 className="size-3.5" /> : <XCircle className="size-3.5" />}
              {k.replace(/_/g, ' ')}
            </span>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-400">
          Bands 5–6 need <strong>relationships</strong> between features, not just a list of values.
        </p>
      </div>

      {(r.accuracy?.unsupported?.length > 0 || (r.inaccuracies?.length ?? 0) > 0) && (
        <div className="rounded-xl border border-amber-300 bg-amber-50/60 p-4">
          <h3 className="text-sm font-semibold text-amber-900">Check these figures</h3>
          {r.accuracy?.unsupported?.length > 0 && (
            <p className="mt-1 text-sm text-amber-900">
              These numbers don’t match the chart: <strong>{r.accuracy.unsupported.join(', ')}</strong>
            </p>
          )}
          {(r.inaccuracies ?? []).map((x, i) => (
            <p key={i} className="mt-1 text-sm text-amber-900">
              {x}
            </p>
          ))}
        </div>
      )}

      {r.errors && r.errors.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="font-display text-sm font-semibold text-slate-900">Corrections</h3>
          <ul className="mt-2 flex flex-wrap gap-2">
            {r.errors.map((e, i) => (
              <li
                key={i}
                className="inline-flex items-center gap-1 rounded-lg bg-slate-50 px-2 py-1 text-xs ring-1 ring-slate-200/70"
              >
                <span className="text-rose-600 line-through">{e.wrong}</span>
                <span className="text-slate-400">→</span>
                <span className="font-medium text-emerald-700">{e.correct}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {r.top_priorities?.length > 0 && (
        <div className="rounded-xl border border-amber-300 bg-amber-50/60 p-4">
          <h3 className="text-sm font-semibold text-amber-900">Fix these first</h3>
          <ol className="mt-2 space-y-1.5">
            {r.top_priorities.map((p, i) => (
              <li key={i} className="flex gap-2 text-sm text-amber-900">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md bg-amber-200 text-xs font-bold tabular-nums">
                  {i + 1}
                </span>
                {p}
              </li>
            ))}
          </ol>
        </div>
      )}

      {r.not_scored?.length > 0 && (
        <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-3 text-xs text-slate-500">
          <strong>Not scored:</strong> {r.not_scored.join(', ')} — these need the audio signal, so they
          aren’t assessed here rather than being guessed at.
        </p>
      )}

      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-100"
      >
        <RotateCcw className="size-4" aria-hidden="true" /> Describe another
      </button>
    </div>
  )
}
