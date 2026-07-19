import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Clock, Loader2, PenLine, RotateCcw, Send } from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { EssayFeedback } from '../lib/types'
import { AttemptModal, FeedbackBody, HistorySection } from './EssayPractice'

const TASK = 'summarize_written_text'
const EXAM_SECONDS = 10 * 60 // SWT is 10 minutes per item
const MIN_WORDS = 5
const MAX_WORDS = 75

const countWords = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0)

/** Form is binary for SWT: 5-75 words in one sentence, or 0. So the counter is
 * green inside the band and red outside — no middle ground. */
function wordClass(n: number) {
  if (n === 0) return 'text-slate-400'
  return n >= MIN_WORDS && n <= MAX_WORDS ? 'text-emerald-600' : 'text-rose-600'
}

const sentenceCount = (s: string) =>
  s.trim() ? s.trim().split(/[.!?]+(?=\s|$)/).filter((p) => p.trim()).length : 0

function mmss(total: number) {
  const m = Math.floor(total / 60)
  const sec = total % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export function SwtPractice({ slug, number }: { slug: string; number: number }) {
  const bank = useAsync(() => api.swtPassages(), [])
  const passages = bank.data ?? []

  const draftKey = `swt-draft:${slug}:${number}`
  const draft0 = (() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) || '{}')
    } catch {
      return {}
    }
  })()

  const [choice, setChoice] = useState<string>(draft0.choice || '')
  const [summary, setSummary] = useState<string>(draft0.summary || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EssayFeedback | null>(null)

  const [historyVersion, setHistoryVersion] = useState(0)
  const history = useAsync(() => api.essayAttempts(slug, TASK), [slug, historyVersion])
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null)

  const [seconds, setSeconds] = useState(EXAM_SECONDS)
  const [running, setRunning] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (passages.length && !choice) setChoice(passages[0].id)
  }, [passages, choice])

  useEffect(() => {
    if (result) return
    const t = setTimeout(() => {
      localStorage.setItem(draftKey, JSON.stringify({ choice, summary }))
    }, 400)
    return () => clearTimeout(t)
  }, [draftKey, choice, summary, result])

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

  const selected = passages.find((p) => p.id === choice)
  const words = countWords(summary)
  const sentences = sentenceCount(summary)
  const canSubmit = !!selected && words > 0 && !loading

  async function submit() {
    if (!selected) return
    setLoading(true)
    setError(null)
    setResult(null)
    setRunning(false)
    try {
      const fb = await api.swtFeedback(slug, number, selected.passage, summary.trim(), selected.id)
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
    setSummary('')
    setSeconds(EXAM_SECONDS)
    setRunning(false)
    localStorage.removeItem(draftKey)
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
          <PenLine className="size-3.5" aria-hidden="true" /> Practice &amp; get feedback
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold text-slate-900 sm:text-3xl">
          Summarize the passage
        </h1>
        <p className="mt-2 text-slate-600">
          10 minutes. Write <strong>one single sentence</strong> of 5–75 words. Scored on Content,
          Form, Grammar and Vocabulary (9 points).
        </p>
      </header>

      {!result && (
        <div className="mt-6 space-y-4">
          {/* Passage */}
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <label htmlFor="passage" className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Source passage
            </label>
            {bank.loading ? (
              <p className="mt-2 text-sm text-slate-400">Loading passages…</p>
            ) : (
              <select
                id="passage"
                value={choice}
                onChange={(e) => setChoice(e.target.value)}
                className="mt-1.5 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              >
                {passages.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title} ({p.word_count} words)
                  </option>
                ))}
              </select>
            )}
            {selected && (
              <div className="mt-2 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 text-sm leading-relaxed text-slate-700 ring-1 ring-slate-200/60">
                {selected.passage}
              </div>
            )}
          </div>

          {/* Timer + counters */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-semibold tabular-nums ring-1 ${
                  seconds === 0
                    ? 'bg-rose-50 text-rose-600 ring-rose-200'
                    : 'bg-slate-100 text-slate-700 ring-slate-200'
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
            <span className="inline-flex items-center gap-3 text-sm tabular-nums">
              <span className={`font-semibold ${wordClass(words)}`}>{words} words</span>
              <span className={sentences > 1 ? 'font-semibold text-rose-600' : 'text-slate-400'}>
                {sentences} sentence{sentences === 1 ? '' : 's'}
              </span>
            </span>
          </div>

          {sentences > 1 && (
            <p className="flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-800 ring-1 ring-amber-200">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" aria-hidden="true" />
              More than one sentence scores <strong>0 for Form</strong> — join these into a single
              sentence using commas, semicolons or connectives.
            </p>
          )}

          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Write your one-sentence summary here…"
            className="min-h-[7rem] w-full rounded-xl border border-slate-200 p-4 leading-relaxed focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
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

      {result && (
        <div className="mt-6 space-y-5">
          <FeedbackBody r={result} essay={summary} />
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-300 px-5 py-2.5 font-medium text-slate-700 hover:bg-slate-100"
          >
            <RotateCcw className="size-4" aria-hidden="true" /> Summarize another
          </button>
        </div>
      )}

      <HistorySection attempts={history.data ?? []} onSelect={setSelectedAttempt} />
      {selectedAttempt != null && (
        <AttemptModal slug={slug} id={selectedAttempt} onClose={() => setSelectedAttempt(null)} />
      )}
    </div>
  )
}
