import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Info, Loader2, RotateCcw, Send, Sparkles, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { MathPracticeFeedback, MathPracticeItem, MathProgress } from '../lib/types'
import { MathText } from './MathText'
import { AttemptModal, HistorySection } from './EssayPractice'

const TASK = 'math_practice'

/** The first slice of the V2 study tool: maths practice where the answer is
 * computed by code and checked exactly, and a spaced-repetition scheduler (the
 * deterministic Learning Engine) chooses which item to study next. */
export function MathPractice({ slug, number }: { slug: string; number: number }) {
  const [item, setItem] = useState<MathPracticeItem | null>(null)
  const [reason, setReason] = useState<string>('new')
  const [progress, setProgress] = useState<MathProgress | null>(null)
  const [answer, setAnswer] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingNext, setLoadingNext] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<MathPracticeFeedback | null>(null)

  const [historyVersion, setHistoryVersion] = useState(0)
  const history = useAsync(() => api.essayAttempts(slug, TASK), [slug, historyVersion])
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null)

  // running tally for this sitting
  const [seen, setSeen] = useState(0)
  const [right, setRight] = useState(0)

  // Ask the scheduler for the next item to study.
  const loadNext = useCallback(
    async (after?: string) => {
      setLoadingNext(true)
      setError(null)
      try {
        const n = await api.mathPracticeNext(slug, after)
        setItem(n.item)
        setReason(n.reason)
        setProgress(n.progress)
        setAnswer('')
        setResult(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoadingNext(false)
      }
    },
    [slug],
  )

  useEffect(() => {
    loadNext()
  }, [loadNext])

  async function submit() {
    if (!item || !answer.trim()) return
    setLoading(true)
    setError(null)
    try {
      const fb = await api.mathPracticeAnswer(slug, number, item.id, answer.trim())
      setResult(fb)
      if (fb.progress) setProgress(fb.progress)
      setSeen((s) => s + 1)
      if (fb.correct) setRight((r) => r + 1)
      setHistoryVersion((v) => v + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function next() {
    loadNext(item?.id)
  }
  function retry() {
    setResult(null)
    setAnswer('')
    setError(null)
  }

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
          <CheckCircle2 className="size-3.5" aria-hidden="true" /> Practise &amp; get it marked
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold text-slate-900 sm:text-3xl">Practice</h1>
        <p className="mt-2 text-slate-600">
          Work it out, type your answer, and it&rsquo;s checked straight away.
        </p>
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-slate-100 p-3 text-xs text-slate-600">
          <Info className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
          <span>
            Every answer here is worked out by the computer, so it&rsquo;s always right. Type fractions
            like <code className="rounded bg-white/70 px-1">3/4</code> or{' '}
            <code className="rounded bg-white/70 px-1">2 1/2</code>. Give the answer in its simplest form.
          </span>
        </p>
      </header>

      {progress && <ProgressBar progress={progress} />}

      {loadingNext && !item && <p className="mt-6 text-sm text-slate-400">Loading…</p>}

      {!loadingNext && !item && (
        <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-6 text-center">
          <Sparkles className="mx-auto size-6 text-emerald-600" aria-hidden="true" />
          <p className="mt-2 font-display text-lg font-semibold text-emerald-800">
            {progress && progress.total === 0
              ? 'No practice questions yet.'
              : 'You’ve mastered every question here!'}
          </p>
          <p className="mt-1 text-sm text-emerald-700">
            {progress && progress.total === 0
              ? 'Generate them with python math_practice_items.py.'
              : 'Come back later — they’ll return for review to keep them fresh.'}
          </p>
        </div>
      )}

      {item && (
        <div className="mt-5 space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span className="flex items-center gap-2">
              <span className="rounded-full bg-slate-100 px-2.5 py-1 font-medium">{item.skill_title}</span>
              <ReasonChip reason={reason} />
            </span>
            {seen > 0 && (
              <span className="tabular-nums">
                {right}/{seen} correct this session
              </span>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6 text-center">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Work this out</p>
            <div className="mt-3 text-2xl text-slate-900">
              <MathText>{item.prompt}</MathText>
            </div>
          </div>

          {!result ? (
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="text"
                inputMode="text"
                autoFocus
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && submit()}
                placeholder="your answer, e.g. 3/4"
                className="w-44 rounded-lg border border-slate-300 px-3 py-2.5 text-lg tabular-nums focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
              <button
                onClick={submit}
                disabled={!answer.trim() || loading}
                className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {loading ? (
                  <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Send className="size-4" aria-hidden="true" />
                )}
                {loading ? 'Checking…' : 'Check'}
              </button>
            </div>
          ) : (
            <Marked result={result} onNext={next} onRetry={retry} />
          )}

          {error && (
            <p className="flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}
        </div>
      )}

      <HistorySection attempts={history.data ?? []} onSelect={setSelectedAttempt} />
      {selectedAttempt != null && (
        <AttemptModal slug={slug} id={selectedAttempt} onClose={() => setSelectedAttempt(null)} />
      )}
    </div>
  )
}

/** The spaced-repetition progress: how much is mastered, in progress, and new. */
function ProgressBar({ progress }: { progress: MathProgress }) {
  const { total, mastered, in_progress, due } = progress
  if (total === 0) return null
  const pct = (n: number) => `${(100 * n) / total}%`
  return (
    <div className="mt-5">
      <div className="mb-1.5 flex items-center justify-between text-xs text-slate-500">
        <span>
          <strong className="text-emerald-700">{mastered}</strong> mastered · {in_progress} learning ·{' '}
          {total - mastered - in_progress} new
        </span>
        {due > 0 && <span className="text-amber-600">{due} due now</span>}
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="bg-emerald-500" style={{ width: pct(mastered) }} />
        <div className="bg-brand-400" style={{ width: pct(in_progress) }} />
      </div>
    </div>
  )
}

/** Why the scheduler chose this item — a small, honest window into the engine. */
function ReasonChip({ reason }: { reason: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    new: { label: 'new', cls: 'bg-brand-50 text-brand-700 ring-brand-100' },
    due: { label: 'review — due', cls: 'bg-amber-50 text-amber-700 ring-amber-200' },
    review: { label: 'review', cls: 'bg-amber-50 text-amber-700 ring-amber-200' },
  }
  const m = map[reason]
  if (!m) return null
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${m.cls}`}>{m.label}</span>
}

function Marked({
  result,
  onNext,
  onRetry,
}: {
  result: MathPracticeFeedback
  onNext: () => void
  onRetry: () => void
}) {
  const tone = result.correct
    ? 'border-emerald-200 bg-emerald-50'
    : result.not_simplest
      ? 'border-amber-200 bg-amber-50'
      : 'border-rose-200 bg-rose-50'
  const Icon = result.correct ? CheckCircle2 : result.not_simplest ? AlertTriangle : XCircle
  const iconColor = result.correct ? 'text-emerald-600' : result.not_simplest ? 'text-amber-600' : 'text-rose-500'

  return (
    <div className={`rounded-xl border p-5 ${tone}`}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 size-6 shrink-0 ${iconColor}`} aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-slate-800">{result.message}</p>
          {!result.correct && (
            <p className="mt-1.5 text-sm text-slate-600">
              Answer: <span className="text-base"><MathText>{result.answer_tex}</MathText></span>
            </p>
          )}
        </div>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={onNext}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          Next question
        </button>
        {!result.correct && (
          <button
            onClick={onRetry}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            <RotateCcw className="size-4" aria-hidden="true" /> Try again
          </button>
        )}
      </div>
    </div>
  )
}
