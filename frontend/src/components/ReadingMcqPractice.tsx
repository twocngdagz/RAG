import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Info,
  Loader2,
  RotateCcw,
  Send,
  XCircle,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { ReadingMcqFeedback, ReadingMcqItem } from '../lib/types'
import { AttemptModal, HistorySection } from './EssayPractice'

const TASK = 'reading_multiple_choice'

export function ReadingMcqPractice({ slug, number }: { slug: string; number: number }) {
  const bank = useAsync(() => api.readingMcqItems(), [])
  const items = bank.data ?? []

  const draftKey = `rmc-draft:${slug}:${number}`
  const draft0 = (() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) || '{}')
    } catch {
      return {}
    }
  })()

  const [choice, setChoice] = useState<string>(draft0.choice || '')
  const [picked, setPicked] = useState<string[]>(draft0.picked || [])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ReadingMcqFeedback | null>(null)

  const [historyVersion, setHistoryVersion] = useState(0)
  const history = useAsync(() => api.essayAttempts(slug, TASK), [slug, historyVersion])
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null)

  const selected: ReadingMcqItem | undefined = items.find((i) => i.id === choice)

  useEffect(() => {
    if (items.length && !choice) setChoice(items[0].id)
  }, [items, choice])

  // Keep the unsubmitted answer, so a reload doesn't lose it.
  useEffect(() => {
    if (result) return
    const t = setTimeout(
      () => localStorage.setItem(draftKey, JSON.stringify({ choice, picked })),
      300,
    )
    return () => clearTimeout(t)
  }, [draftKey, choice, picked, result])

  function toggle(key: string) {
    if (result) return
    if (selected?.mode === 'single') {
      setPicked([key])
      return
    }
    setPicked((p) => (p.includes(key) ? p.filter((k) => k !== key) : [...p, key]))
  }

  async function submit() {
    if (!selected) return
    setLoading(true)
    setError(null)
    try {
      const fb = await api.readingMcqAnswer(slug, number, selected.id, picked)
      setResult(fb)
      localStorage.removeItem(draftKey)
      setHistoryVersion((v) => v + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  function next() {
    const i = items.findIndex((x) => x.id === choice)
    const nxt = items[(i + 1) % Math.max(items.length, 1)]
    setResult(null)
    setError(null)
    setPicked([])
    if (nxt) setChoice(nxt.id)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function retry() {
    setResult(null)
    setError(null)
    setPicked([])
  }

  const canSubmit = !!selected && picked.length > 0 && !loading && !result

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
      <header className="animate-rise">
        <span className="inline-flex items-center gap-1.5 rounded-full bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100">
          <ClipboardCheck className="size-3.5" aria-hidden="true" /> Practice &amp; get marked
        </span>
        <h1 className="mt-3 font-display text-2xl font-bold text-slate-900 sm:text-3xl">
          Reading multiple choice
        </h1>
        <p className="mt-2 text-slate-600">
          Read the passage, answer the question. Marked instantly against the official rules.
        </p>
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-slate-100 p-3 text-xs text-slate-600">
          <Info className="mt-0.5 size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
          <span>
            Every answer here was checked before it reached you: it only appears if independent
            readers, who never saw the answer key, all picked the same option from the passage.
          </span>
        </p>
      </header>

      {bank.loading && <p className="mt-6 text-sm text-slate-400">Loading questions…</p>}
      {!bank.loading && !items.length && (
        <p className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          No questions yet. Generate the bank with{' '}
          <code className="rounded bg-white/70 px-1">python reading_mcq_items.py</code>.
        </p>
      )}

      {selected && (
        <div className="mt-6 space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <label
              htmlFor="rmc-item"
              className="text-xs font-semibold uppercase tracking-wide text-slate-400"
            >
              Question
            </label>
            <select
              id="rmc-item"
              value={choice}
              onChange={(e) => {
                setChoice(e.target.value)
                setPicked([])
                setResult(null)
                setError(null)
              }}
              className="mt-1.5 w-full cursor-pointer rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            >
              {items.map((i, n) => (
                <option key={i.id} value={i.id}>
                  {n + 1}. {i.title} — {i.mode === 'single' ? 'one answer' : 'more than one answer'}
                </option>
              ))}
            </select>
          </div>

          <article className="rounded-xl border border-slate-200 bg-white p-5">
            <h2 className="font-display text-lg font-semibold text-slate-900">{selected.title}</h2>
            <p className="mt-3 whitespace-pre-wrap leading-relaxed text-slate-700">
              {selected.passage}
            </p>
            <p className="mt-3 text-xs text-slate-400">{selected.word_count} words</p>
          </article>

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <p className="font-medium text-slate-900">{selected.question}</p>
            <p className="mt-1 text-xs text-slate-500">
              {selected.mode === 'single'
                ? 'Choose one answer.'
                : 'Choose every answer that applies — a wrong tick cancels out a right one.'}
            </p>

            <ul className="mt-4 space-y-2">
              {selected.options.map((o) => (
                <OptionRow
                  key={o.key}
                  option={o}
                  mode={selected.mode}
                  checked={picked.includes(o.key)}
                  result={result}
                  onToggle={() => toggle(o.key)}
                />
              ))}
            </ul>
          </div>

          {error && (
            <p className="flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}

          {!result ? (
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {loading ? (
                <Loader2 className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <Send className="size-4" aria-hidden="true" />
              )}
              {loading ? 'Marking…' : 'Submit answer'}
            </button>
          ) : (
            <Marked result={result} onNext={next} onRetry={retry} />
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

/** One option. After marking it shows what was right, not just what you picked. */
function OptionRow({
  option,
  mode,
  checked,
  result,
  onToggle,
}: {
  option: { key: string; text: string }
  mode: string
  checked: boolean
  result: ReadingMcqFeedback | null
  onToggle: () => void
}) {
  const isKey = result?.correct_keys.includes(option.key) ?? false
  const chose = result?.chosen_keys.includes(option.key) ?? checked

  let tone = 'border-slate-200 bg-white hover:border-brand-300'
  if (result) {
    if (isKey) tone = 'border-emerald-300 bg-emerald-50'
    else if (chose) tone = 'border-rose-300 bg-rose-50'
    else tone = 'border-slate-200 bg-white opacity-70'
  } else if (checked) {
    tone = 'border-brand-400 bg-brand-50'
  }

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        disabled={!!result}
        className={`flex w-full gap-3 rounded-lg border p-3 text-left transition ${tone} ${
          result ? 'cursor-default' : 'cursor-pointer'
        }`}
      >
        <span
          className={`mt-0.5 flex size-5 shrink-0 items-center justify-center text-xs font-bold ${
            mode === 'single' ? 'rounded-full' : 'rounded'
          } ${
            result && isKey
              ? 'bg-emerald-600 text-white'
              : result && chose
                ? 'bg-rose-500 text-white'
                : chose
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-200 text-slate-600'
          }`}
        >
          {option.key}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm text-slate-800">{option.text}</span>
          {result && (
            <span className="mt-1.5 flex items-start gap-1.5 text-xs text-slate-600">
              {isKey ? (
                <CheckCircle2 className="mt-px size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
              ) : (
                <XCircle className="mt-px size-3.5 shrink-0 text-slate-400" aria-hidden="true" />
              )}
              {result.rationale?.[option.key]}
            </span>
          )}
        </span>
      </button>
    </li>
  )
}

function Marked({
  result,
  onNext,
  onRetry,
}: {
  result: ReadingMcqFeedback
  onNext: () => void
  onRetry: () => void
}) {
  const perfect = result.score === result.max_score
  return (
    <div
      className={`rounded-xl border p-5 ${
        perfect ? 'border-emerald-200 bg-emerald-50' : 'border-amber-200 bg-amber-50'
      }`}
    >
      <div className="flex items-center gap-3">
        <span
          className={`font-display text-3xl font-bold tabular-nums ${
            perfect ? 'text-emerald-700' : 'text-amber-700'
          }`}
        >
          {result.score}
          <span className="text-lg text-slate-400">/{result.max_score}</span>
        </span>
        <p className={`text-sm ${perfect ? 'text-emerald-800' : 'text-amber-900'}`}>
          {result.one_line_verdict}
        </p>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={onNext}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-700"
        >
          Next question
        </button>
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
        >
          <RotateCcw className="size-4" aria-hidden="true" /> Try this one again
        </button>
      </div>
    </div>
  )
}
