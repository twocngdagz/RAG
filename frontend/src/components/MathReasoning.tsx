import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, Circle, Info, Lightbulb, Loader2,
  MessageCircleHeart, Send, Sparkles,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { MathAdvisory, MathProgress, MathReasoningFeedback, MathReasoningItem } from '../lib/types'
import { MathText } from './MathText'
import { AttemptModal, HistorySection } from './EssayPractice'

const TASK = 'math_reasoning'

const ADVISORY_LABEL: Record<string, string> = {
  explains_why: 'Says why',
  clear_steps: 'Clear steps',
  maths_language: 'Maths words',
}

/** Open-response maths practice — the V2 slice where the answer is an explanation.
 *
 * The screen has to make one thing obvious to a nine-year-old: the tick and the
 * cross come from the maths, and the coach's comments are only help. So the marked
 * part and the advisory part never share a panel, a colour, or a score. */
export function MathReasoning({ slug, number }: { slug: string; number: number }) {
  const [item, setItem] = useState<MathReasoningItem | null>(null)
  const [reason, setReason] = useState<string>('new')
  const [progress, setProgress] = useState<MathProgress | null>(null)
  const [response, setResponse] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingNext, setLoadingNext] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<MathReasoningFeedback | null>(null)

  const [historyVersion, setHistoryVersion] = useState(0)
  const history = useAsync(() => api.essayAttempts(slug, TASK), [slug, historyVersion])
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null)

  const loadNext = useCallback(
    async (after?: string) => {
      setLoadingNext(true)
      setError(null)
      try {
        const n = await api.mathReasoningNext(slug, number, after)
        setItem(n.item)
        setReason(n.reason)
        setProgress(n.progress)
        setResponse('')
        setResult(null)
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoadingNext(false)
      }
    },
    [slug, number],
  )

  useEffect(() => {
    loadNext()
  }, [loadNext])

  async function submit() {
    if (!item || !response.trim()) return
    setLoading(true)
    setError(null)
    try {
      const fb = await api.mathReasoningAnswer(slug, number, item.id, response.trim())
      setResult(fb)
      if (fb.progress) setProgress(fb.progress)
      setHistoryVersion((v) => v + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  const words = response.trim() ? response.trim().split(/\s+/).length : 0

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-3 py-1 text-xs font-medium text-violet-700 ring-1 ring-violet-100">
          <MessageCircleHeart className="size-3.5" aria-hidden="true" /> Explain your thinking
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold text-slate-900 sm:text-3xl">
          Show me how you know
        </h1>
        <p className="mt-2 text-slate-600">
          Here the answer on its own isn&rsquo;t enough &mdash; write how you worked it out, like
          you&rsquo;re explaining it to a friend.
        </p>
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-slate-100 p-3 text-xs text-slate-600">
          <Info className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
          <span>
            Two things get ticked by the computer: <strong>your final answer</strong> and{' '}
            <strong>whether you showed your steps</strong>. Write the numbers you used, like{' '}
            <code className="rounded bg-white/70 px-1">3/6</code>, so your working can be seen.
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
              ? 'No reasoning questions yet.'
              : 'You’ve mastered every question here!'}
          </p>
          <p className="mt-1 text-sm text-emerald-700">
            {progress && progress.total === 0
              ? 'Generate them with python math_reasoning_items.py.'
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
            <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11px] font-medium capitalize text-violet-700 ring-1 ring-violet-100">
              {item.capability}
            </span>
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">The question</p>
            <div className="mt-2 text-lg leading-relaxed text-slate-900">
              <MathText>{item.question}</MathText>
            </div>
          </div>

          {!result ? (
            <div className="space-y-3">
              <textarea
                autoFocus
                value={response}
                onChange={(e) => setResponse(e.target.value)}
                rows={7}
                placeholder="First I… Then I… So the answer is…"
                className="w-full rounded-lg border border-slate-300 p-3.5 text-[15px] leading-relaxed focus:border-violet-400 focus:outline-none focus:ring-2 focus:ring-violet-100"
              />
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={submit}
                  disabled={!response.trim() || loading}
                  className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {loading ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Send className="size-4" aria-hidden="true" />
                  )}
                  {loading ? 'Reading your answer…' : 'Check my explanation'}
                </button>
                <span className="text-xs tabular-nums text-slate-400">{words} words</span>
              </div>
            </div>
          ) : (
            <Marked result={result} onNext={() => loadNext(item.id)} />
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
        <div className="bg-violet-400" style={{ width: pct(in_progress) }} />
      </div>
    </div>
  )
}

function ReasonChip({ reason }: { reason: string }) {
  const map: Record<string, { label: string; cls: string }> = {
    new: { label: 'new', cls: 'bg-violet-50 text-violet-700 ring-violet-100' },
    due: { label: 'review — due', cls: 'bg-amber-50 text-amber-700 ring-amber-200' },
    review: { label: 'review', cls: 'bg-amber-50 text-amber-700 ring-amber-200' },
  }
  const m = map[reason]
  if (!m) return null
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ${m.cls}`}>{m.label}</span>
}

/** The marked panel (code) and the coach panel (model) — deliberately separate. */
function Marked({ result, onNext }: { result: MathReasoningFeedback; onNext: () => void }) {
  const tone = result.correct
    ? 'border-emerald-200 bg-emerald-50'
    : result.answer_shown || result.working_shown
      ? 'border-amber-200 bg-amber-50'
      : 'border-rose-200 bg-rose-50'

  return (
    <div className="space-y-4">
      {/* ---- what the computer checked: this is the mark ---- */}
      <div className={`rounded-xl border p-5 ${tone}`}>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          Checked by the computer
        </p>
        <p className="mt-1.5 font-medium text-slate-800">{result.message}</p>
        <ul className="mt-3 space-y-1.5 text-sm">
          <Tick on={result.answer_shown} label="You gave the right answer" />
          <Tick on={result.working_shown} label="You showed your working" />
        </ul>
        {!result.correct && (
          <p className="mt-3 text-sm text-slate-600">
            The answer is <strong>{result.answer_plain}</strong>.
          </p>
        )}
      </div>

      {/* ---- what the coach thinks: help, never a mark ---- */}
      {result.advisory && <Coach advisory={result.advisory} />}
      {result.advisory_error && (
        <p className="flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500">
          <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {result.advisory_error}
        </p>
      )}

      {/* ---- one good answer, revealed now they've had a go ---- */}
      {result.model_answer && (
        <details className="rounded-xl border border-slate-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-700">
            See one good way to explain it
          </summary>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">{result.model_answer}</p>
          {result.rubric?.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-slate-500">
              {result.rubric.map((r) => (
                <li key={r} className="flex gap-2">
                  <span aria-hidden="true">·</span>
                  {r}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 text-xs italic text-slate-400">
            Yours doesn&rsquo;t have to match this — a different good explanation is just as right.
          </p>
        </details>
      )}

      <button
        onClick={onNext}
        className="inline-flex items-center gap-2 rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-violet-700"
      >
        Next question
      </button>
    </div>
  )
}

function Tick({ on, label }: { on: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      {on ? (
        <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-hidden="true" />
      ) : (
        <Circle className="size-4 shrink-0 text-slate-300" aria-hidden="true" />
      )}
      <span className={on ? 'text-slate-700' : 'text-slate-500'}>{label}</span>
    </li>
  )
}

/** Advisory feedback. Styled as a note from a helper, never as a score: no total,
 * no percentage, and an explicit line saying it doesn't count. */
function Coach({ advisory }: { advisory: MathAdvisory }) {
  return (
    <div className="rounded-xl border border-dashed border-violet-300 bg-violet-50/50 p-5">
      <div className="flex items-center gap-2">
        <MessageCircleHeart className="size-4 text-violet-600" aria-hidden="true" />
        <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">
          A note on your explaining
        </p>
      </div>
      <p className="mt-0.5 text-[11px] text-violet-500">
        Written by an AI helper. It&rsquo;s advice, not a mark — it doesn&rsquo;t change your score.
      </p>

      <p className="mt-3 flex items-start gap-2 text-sm text-slate-700">
        <Sparkles className="mt-0.5 size-4 shrink-0 text-amber-500" aria-hidden="true" />
        <span>{advisory.strength}</span>
      </p>
      <p className="mt-2 flex items-start gap-2 text-sm text-slate-700">
        <Lightbulb className="mt-0.5 size-4 shrink-0 text-violet-500" aria-hidden="true" />
        <span>{advisory.next_step}</span>
      </p>

      <div className="mt-4 space-y-2.5">
        {advisory.traits.map((t) => (
          <div key={t.name}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-slate-600">{ADVISORY_LABEL[t.name] ?? t.name}</span>
              <span className="text-slate-400">
                {'●'.repeat(t.score)}
                {'○'.repeat(Math.max(0, t.max - t.score))}
              </span>
            </div>
            {t.fix && <p className="mt-0.5 text-xs text-slate-500">{t.fix}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}
