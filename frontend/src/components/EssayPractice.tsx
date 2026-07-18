import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Loader2,
  PenLine,
  RotateCcw,
  Send,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { EssayFeedback } from '../lib/types'

const TRAIT_LABEL: Record<string, string> = {
  content: 'Content',
  form: 'Form',
  development_structure_coherence: 'Development, structure & coherence',
  grammar: 'Grammar',
  general_linguistic_range: 'General linguistic range',
  vocabulary_range: 'Vocabulary range',
  spelling: 'Spelling',
}

const TYPE_LABEL: Record<string, string> = {
  agree_disagree: 'Agree / Disagree',
  advantages_disadvantages: 'Advantages / Disadvantages',
  problem_solution: 'Problem / Solution',
  positive_negative: 'Positive / Negative',
  discuss_two_views: 'Discuss both views',
}

const CUSTOM = '__custom__'
const EXAM_SECONDS = 20 * 60

const countWords = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0)

/** Word-count colour: green in the 200-300 band, amber in the 1-point bands,
 * red outside 120-380 (where Form scores 0). Mirrors the code-side Form rule. */
function wordClass(n: number) {
  if (n === 0) return 'text-slate-400'
  if (n >= 200 && n <= 300) return 'text-emerald-600'
  if (n < 120 || n > 380) return 'text-rose-600'
  return 'text-amber-600'
}

function mmss(total: number) {
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function EssayPractice({ slug, number }: { slug: string; number: number }) {
  const bank = useAsync(() => api.essayPrompts(), [])
  const prompts = bank.data ?? []

  const [choice, setChoice] = useState('') // prompt id, or CUSTOM
  const [customPrompt, setCustomPrompt] = useState('')
  const [essay, setEssay] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EssayFeedback | null>(null)

  const [seconds, setSeconds] = useState(EXAM_SECONDS)
  const [running, setRunning] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  // Default to the first prompt once the bank loads.
  useEffect(() => {
    if (prompts.length && !choice) setChoice(prompts[0].id)
  }, [prompts, choice])

  useEffect(() => {
    if (!running) return
    timer.current = setInterval(() => {
      setSeconds((s) => {
        if (s <= 1) {
          setRunning(false)
          return 0
        }
        return s - 1
      })
    }, 1000)
    return () => {
      if (timer.current) clearInterval(timer.current)
    }
  }, [running])

  const selected = prompts.find((p) => p.id === choice)
  const promptText =
    choice === CUSTOM
      ? customPrompt.trim()
      : selected
        ? `${selected.statement} ${selected.directive} ${selected.instruction}`.trim()
        : ''
  const words = countWords(essay)
  const canSubmit = promptText.length > 0 && words > 0 && !loading

  async function submit() {
    setLoading(true)
    setError(null)
    setResult(null)
    setRunning(false)
    try {
      setResult(await api.essayFeedback(slug, number, promptText, essay.trim()))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setResult(null)
    setError(null)
    setEssay('')
    setSeconds(EXAM_SECONDS)
    setRunning(false)
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
          <PenLine className="size-3.5" aria-hidden="true" /> Practice &amp; get feedback
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold text-slate-900 sm:text-3xl">
          Write a timed essay
        </h1>
        <p className="mt-2 text-slate-600">
          20 minutes, 200–300 words. You’ll get a rubric breakdown scored against the seven PTE
          Write Essay traits, with a specific fix for each.
        </p>
      </header>

      {!result && (
        <div className="mt-6 space-y-4">
          {/* Prompt */}
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <label htmlFor="prompt" className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Essay prompt
            </label>
            {bank.loading ? (
              <p className="mt-2 text-sm text-slate-400">Loading prompts…</p>
            ) : (
              <select
                id="prompt"
                value={choice}
                onChange={(e) => setChoice(e.target.value)}
                className="mt-1.5 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              >
                {prompts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {(TYPE_LABEL[p.type] ?? p.type)} — {p.topic.replace(/_/g, ' ')}
                  </option>
                ))}
                <option value={CUSTOM}>Write my own prompt…</option>
              </select>
            )}

            {choice === CUSTOM ? (
              <textarea
                value={customPrompt}
                onChange={(e) => setCustomPrompt(e.target.value)}
                placeholder="Paste or type an essay prompt…"
                className="mt-2 w-full rounded-lg border border-slate-200 p-3 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
                rows={2}
              />
            ) : (
              selected && (
                <div className="mt-2 rounded-lg bg-slate-50 p-4 ring-1 ring-slate-200/60">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-100 px-2.5 py-0.5 text-xs font-medium text-brand-800">
                    {TYPE_LABEL[selected.type] ?? selected.type} · {selected.time_minutes} min ·{' '}
                    {selected.word_range[0]}–{selected.word_range[1]} words
                  </span>
                  <p className="mt-2 leading-relaxed text-slate-800">
                    {selected.statement} <strong className="text-slate-900">{selected.directive}</strong>{' '}
                    {selected.instruction}
                  </p>
                </div>
              )
            )}
          </div>

          {/* Timer + word count */}
          <div className="flex items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold tabular-nums ring-1 ${
                  seconds === 0 ? 'bg-rose-50 text-rose-600 ring-rose-200' : 'bg-slate-100 text-slate-700 ring-slate-200'
                }`}
              >
                <Clock className="size-4" aria-hidden="true" /> {mmss(seconds)}
              </span>
              <button
                type="button"
                onClick={() => setRunning((r) => !r)}
                className="rounded-lg px-3 py-1.5 text-sm font-medium text-brand-700 hover:bg-brand-50"
              >
                {running ? 'Pause' : seconds === EXAM_SECONDS ? 'Start timer' : 'Resume'}
              </button>
            </div>
            <span className={`text-sm font-semibold tabular-nums ${wordClass(words)}`}>{words} words</span>
          </div>

          {/* Essay */}
          <textarea
            value={essay}
            onChange={(e) => setEssay(e.target.value)}
            placeholder="Write your essay here…"
            className="min-h-[16rem] w-full rounded-xl border border-slate-200 p-4 leading-relaxed focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
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
                <Loader2 className="size-4.5 animate-spin" aria-hidden="true" /> Scoring… (~20–30s)
              </>
            ) : (
              <>
                <Send className="size-4.5" aria-hidden="true" /> Get feedback
              </>
            )}
          </button>
        </div>
      )}

      {result && <FeedbackReport r={result} onRetry={reset} />}
    </div>
  )
}

function FeedbackReport({ r, onRetry }: { r: EssayFeedback; onRetry: () => void }) {
  const pct = r.max_raw_total ? Math.round((100 * r.raw_total) / r.max_raw_total) : 0
  return (
    <div className="mt-6 space-y-5">
      {/* Score header */}
      <div className="rounded-2xl bg-gradient-to-br from-brand-700 to-brand-900 p-6 text-white">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-brand-100">Raw rubric total</p>
            <p className="mt-1 font-display text-4xl font-bold tabular-nums">
              {r.raw_total}
              <span className="text-2xl text-brand-100">/{r.max_raw_total}</span>
            </p>
            <p className="mt-1 text-sm text-brand-50/80">{pct}% of rubric · not an official PTE score</p>
          </div>
          <div className="text-right text-sm text-brand-50/85">{r.word_count} words</div>
        </div>
        <p className="mt-3 text-brand-50/95">{r.one_line_verdict}</p>
      </div>

      {r.gating_applied && (
        <p className="flex items-start gap-2 rounded-xl border-l-3 border-rose-400 bg-rose-50 p-4 text-sm text-rose-800">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-500" aria-hidden="true" />
          <span>
            <strong>Zero score:</strong> Content or Form scored 0, so under the real PTE gating rule the
            whole response scores 0. Fix that first — everything else only counts once this is cleared.
          </span>
        </p>
      )}

      {/* Traits */}
      <div className="space-y-3">
        {r.traits.map((t, i) => {
          const full = t.max > 0 && t.score === t.max
          return (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-display text-sm font-semibold text-slate-900">
                  {TRAIT_LABEL[t.name] ?? t.name}
                </h3>
                <span
                  className={`shrink-0 rounded-md px-2 py-0.5 text-sm font-bold tabular-nums ${
                    full ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-700'
                  }`}
                >
                  {t.score}/{t.max}
                </span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full ${full ? 'bg-emerald-500' : 'bg-brand-500'}`}
                  style={{ width: `${t.max ? (100 * t.score) / t.max : 0}%` }}
                />
              </div>
              {t.evidence && <p className="mt-2.5 text-sm text-slate-600">{t.evidence}</p>}
              {t.fix && (
                <p className="mt-1.5 flex gap-2 text-sm text-slate-700">
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand-600" aria-hidden="true" />
                  <span>
                    <span className="font-medium text-brand-700">Fix: </span>
                    {t.fix}
                  </span>
                </p>
              )}
            </div>
          )
        })}
      </div>

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

      <button
        type="button"
        onClick={onRetry}
        className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-100"
      >
        <RotateCcw className="size-4" aria-hidden="true" /> Write another
      </button>
    </div>
  )
}
