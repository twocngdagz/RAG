import { useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock,
  History,
  Loader2,
  Minus,
  PenLine,
  RotateCcw,
  Send,
  ShieldCheck,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import { api } from '../lib/api'
import { useAsync } from '../lib/useAsync'
import type { EssayAttempt, EssayError, EssayFeedback, EssayTrait } from '../lib/types'

// Covers both writing tasks; names are unique across rubrics.
export const TRAIT_LABEL: Record<string, string> = {
  content: 'Content',
  form: 'Form',
  development_structure_coherence: 'Development, structure & coherence',
  grammar: 'Grammar',
  general_linguistic_range: 'General linguistic range',
  vocabulary_range: 'Vocabulary range',
  vocabulary: 'Vocabulary',
  spelling: 'Spelling',
  // Reading multiple choice reports the reading skill the question tested,
  // so progress shows which kind of question is still costing marks.
  'main idea': 'Main idea',
  detail: 'Detail',
  inference: 'Inference',
  "author's purpose": "Author's purpose",
  tone: 'Tone',
  reading: 'Reading',
  // Maths reasoning: the first two are checked by code and carry the mark; the
  // rest are the AI coach's advisory read on the explanation (flagged per trait).
  right_answer: 'Right answer',
  working_shown: 'Working shown',
  explains_why: 'Says why (advice)',
  clear_steps: 'Clear steps (advice)',
  maths_language: 'Maths words (advice)',
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

  // Draft persistence: while writing (before feedback) the essay lives in
  // localStorage, so a refresh never loses it. Cleared once it's scored + saved.
  const draftKey = `essay-draft:${slug}:${number}`
  const draft0 = (() => {
    try {
      return JSON.parse(localStorage.getItem(draftKey) || '{}')
    } catch {
      return {}
    }
  })()

  const [choice, setChoice] = useState<string>(draft0.choice || '') // prompt id, or CUSTOM
  const [customPrompt, setCustomPrompt] = useState<string>(draft0.customPrompt || '')
  const [essay, setEssay] = useState<string>(draft0.essay || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<EssayFeedback | null>(null)

  // History (scored attempts, DB-backed). Re-fetched after each new score.
  const [historyVersion, setHistoryVersion] = useState(0)
  const history = useAsync(() => api.essayAttempts(slug, 'write_essay'), [slug, historyVersion])
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null)

  const [seconds, setSeconds] = useState(EXAM_SECONDS)
  const [running, setRunning] = useState(false)
  const timer = useRef<ReturnType<typeof setInterval> | null>(null)

  // Default to the first prompt once the bank loads.
  useEffect(() => {
    if (prompts.length && !choice) setChoice(prompts[0].id)
  }, [prompts, choice])

  // Persist the draft while writing (debounced). Stops once a result is shown.
  useEffect(() => {
    if (result) return
    const t = setTimeout(() => {
      localStorage.setItem(draftKey, JSON.stringify({ choice, customPrompt, essay }))
    }, 400)
    return () => clearTimeout(t)
  }, [draftKey, choice, customPrompt, essay, result])

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
      const fb = await api.essayFeedback(slug, number, promptText, essay.trim(), selected?.type)
      setResult(fb)
      localStorage.removeItem(draftKey) // it's a saved attempt now, not a draft
      setHistoryVersion((v) => v + 1) // pull the new attempt into history
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
    localStorage.removeItem(draftKey)
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

      {result && <FeedbackReport r={result} essay={essay} onRetry={reset} />}

      <HistorySection attempts={history.data ?? []} onSelect={setSelectedAttempt} />
      {selectedAttempt != null && (
        <AttemptModal slug={slug} id={selectedAttempt} onClose={() => setSelectedAttempt(null)} />
      )}
    </div>
  )
}

const shortDate = (iso: string) => {
  // created_at is ISO; show a compact local date-time without pulling in a lib.
  const d = iso.replace('T', ' ').slice(0, 16)
  return d || iso
}

/** Progress history — hidden by default; expands to a score trend + attempt list.
 * Each attempt opens its full evaluation in a modal. */
export function HistorySection({
  attempts,
  onSelect,
}: {
  attempts: EssayAttempt[]
  onSelect: (id: number) => void
}) {
  const [open, setOpen] = useState(false)
  if (attempts.length === 0) return null

  // Oldest -> newest for the trend line.
  const series = [...attempts].reverse()
  const max = series[0]?.max_raw_total || 26
  const best = Math.max(...attempts.map((a) => a.raw_total))
  const latest = attempts[0]

  return (
    <div className="mt-8 border-t border-slate-200 pt-5">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between rounded-lg px-1 py-1 text-left hover:bg-slate-50"
        aria-expanded={open}
      >
        <span className="inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
          <History className="size-4 text-slate-400" aria-hidden="true" />
          Your history
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
            {attempts.length}
          </span>
        </span>
        <span className="inline-flex items-center gap-3 text-xs text-slate-400">
          <span>latest {latest.raw_total}/{latest.max_raw_total} · best {best}/{max}</span>
          <ChevronDown className={`size-4 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
        </span>
      </button>

      {open && (
        <div className="mt-4 space-y-4">
          {series.length > 1 && <Sparkline series={series.map((a) => a.raw_total)} max={max} />}
          <TraitProgress attempts={attempts} />
          <ul className="space-y-2">
            {attempts.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onSelect(a.id)}
                  className="flex w-full items-center gap-3 rounded-lg border border-slate-200 bg-white p-3 text-left transition-colors hover:border-brand-300 hover:bg-brand-50/40"
                >
                  <span className="flex w-12 shrink-0 flex-col items-center rounded-md bg-brand-50 py-1 text-brand-700">
                    <span className="text-sm font-bold tabular-nums">{a.raw_total}</span>
                    <span className="text-[10px] text-brand-400">/{a.max_raw_total}</span>
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-slate-700">{a.prompt_excerpt}</span>
                    <span className="text-xs text-slate-400">
                      {shortDate(a.created_at)} · {a.word_count} words
                      {a.prompt_type ? ` · ${a.prompt_type.replace(/_/g, ' ')}` : ''}
                    </span>
                  </span>
                  <ChevronDown className="size-4 shrink-0 -rotate-90 text-slate-300" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Tiny inline score-trend line, no charting library. */
function Sparkline({ series, max }: { series: number[]; max: number }) {
  const w = 100
  const h = 28
  const n = series.length
  const pts = series
    .map((v, i) => {
      const x = n === 1 ? 0 : (i / (n - 1)) * w
      const y = h - (Math.max(0, Math.min(v, max)) / max) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <div className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200/60">
      <p className="mb-1 text-xs font-medium text-slate-500">Score trend (oldest → newest)</p>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-10 w-full" preserveAspectRatio="none" aria-hidden="true">
        <polyline points={pts} fill="none" stroke="currentColor" className="text-brand-500" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

/** Per-trait progress: for each trait, a mini trend + latest score + direction,
 * so a learner sees which specific weakness is improving or stuck. Trait order
 * and maxima are read from the data, so this works for any task type. */
function TraitProgress({ attempts }: { attempts: EssayAttempt[] }) {
  const series = [...attempts].reverse() // oldest -> newest
  const template = attempts[0]?.traits ?? []
  const rows = template
    .map((t) => {
      const scores = series
        .map((a) => a.traits.find((x) => x.name === t.name)?.score)
        .filter((v): v is number => typeof v === 'number')
      return { name: t.name, scores, max: t.max || 1 }
    })
    .filter((r) => r.scores.length > 0)

  if (rows.length === 0) return null

  return (
    <div className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200/60">
      <p className="mb-2 text-xs font-medium text-slate-500">Progress by trait</p>
      <div className="space-y-1.5">
        {rows.map((r) => {
          const latest = r.scores[r.scores.length - 1]
          const delta = latest - r.scores[0]
          return (
            <div key={r.name} className="flex items-center gap-3">
              <span className="w-44 shrink-0 truncate text-xs text-slate-600">
                {TRAIT_LABEL[r.name] ?? r.name}
              </span>
              <div className="h-4 min-w-0 flex-1">
                {r.scores.length > 1 && <MiniSpark scores={r.scores} max={r.max} />}
              </div>
              <span className="inline-flex w-16 shrink-0 items-center justify-end gap-1 text-xs tabular-nums">
                <span className="font-semibold text-slate-700">
                  {latest}/{r.max}
                </span>
                {r.scores.length > 1 && <TrendArrow delta={delta} />}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function MiniSpark({ scores, max }: { scores: number[]; max: number }) {
  const w = 100
  const hgt = 16
  const n = scores.length
  const pts = scores
    .map((v, i) => {
      const x = n === 1 ? 0 : (i / (n - 1)) * w
      const y = hgt - (Math.max(0, Math.min(v, max)) / max) * hgt
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${hgt}`} className="h-4 w-full text-brand-400" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={pts} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  )
}

function TrendArrow({ delta }: { delta: number }) {
  if (delta > 0) return <TrendingUp className="size-3.5 text-emerald-600" aria-label={`up ${delta}`} />
  if (delta < 0) return <TrendingDown className="size-3.5 text-rose-500" aria-label={`down ${delta}`} />
  return <Minus className="size-3.5 text-slate-300" aria-label="no change" />
}

/** Full evaluation of a past attempt, shown in a modal: prompt, the essay you
 * wrote, and the complete trait breakdown. */
export function AttemptModal({ slug, id, onClose }: { slug: string; id: number; onClose: () => void }) {
  const detail = useAsync(() => api.essayAttempt(slug, id), [slug, id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4 sm:p-8"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="my-4 w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <h2 className="font-display text-lg font-bold text-slate-900">Your evaluation</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <X className="size-5" />
          </button>
        </div>

        {detail.loading ? (
          <div className="flex items-center gap-2 py-10 text-slate-400">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading…
          </div>
        ) : detail.data ? (
          <div className="mt-4 space-y-5">
            <div className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200/60">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Prompt</p>
              <p className="mt-1 text-sm text-slate-700">{detail.data.prompt_text}</p>
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Your essay
              </p>
              <div className="max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-3 text-sm leading-relaxed text-slate-700">
                {detail.data.essay_text}
              </div>
            </div>
            <FeedbackBody r={detail.data.feedback} essay={detail.data.essay_text} />
          </div>
        ) : (
          <p className="py-10 text-sm text-rose-600">Couldn’t load this attempt. {detail.error}</p>
        )}
      </div>
    </div>
  )
}

function FeedbackReport({ r, essay, onRetry }: { r: EssayFeedback; essay?: string; onRetry: () => void }) {
  return (
    <div className="mt-6 space-y-5">
      <FeedbackBody r={r} essay={essay} />
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

/** How far a score moved when identical text was re-scored, keyed by rubric max
 * (26 Write Essay, 9 Summarize Written Text, 6 Describe Image Content).
 *
 * Measured by test_grader_agreement.py against gpt-oss:120b, --runs 6, July 2026.
 * `moved` is the WORST range observed across measurement sessions, not the latest
 * — the spread estimate itself varied (essay came out 1, then 3, then 1), so the
 * cautious figure is the honest one to show. Re-run the test before editing these
 * numbers: what a learner reads must come from a measurement, never a guess. */
const REPEATABILITY: Record<number, { moved: number; runs: number }> = {
  26: { moved: 3, runs: 6 },
  9: { moved: 1, runs: 6 },
  6: { moved: 1, runs: 6 },
}

/** The two traits that judge what the writer actually argued. Everything else in
 * these rubrics judges the English it was written in, and rewards neat, correct,
 * on-length prose whatever it says. */
const IDEA_TRAITS = new Set(['content', 'development_structure_coherence'])

type ScorePart = { score: number; max: number }

/** Split a rubric into "what you said" and "how you wrote it". Returns null when
 * the task has only one kind of trait (maths, reading) and the split is meaningless.
 * Advisory traits are excluded — they score nothing. */
function splitScore(traits: EssayTrait[]): { ideas: ScorePart; language: ScorePart } | null {
  const counted = (traits ?? []).filter((t) => !t.advisory)
  const add = (list: EssayTrait[]): ScorePart => ({
    score: list.reduce((a, t) => a + (t.score ?? 0), 0),
    max: list.reduce((a, t) => a + (t.max ?? 0), 0),
  })
  const ideas = add(counted.filter((t) => IDEA_TRAITS.has(t.name)))
  const language = add(counted.filter((t) => !IDEA_TRAITS.has(t.name)))
  if (!ideas.max || !language.max) return null
  return { ideas, language }
}

/** True when neat writing is doing the work: ideas below half, and well behind
 * the language marks. Not fired on a zero score — the gating banner covers that. */
function carriedByWriting(s: { ideas: ScorePart; language: ScorePart }): boolean {
  const ideasPct = s.ideas.score / s.ideas.max
  const langPct = s.language.score / s.language.max
  return s.language.score > 0 && ideasPct < 0.5 && langPct - ideasPct >= 0.25
}

function SplitBar({ label, part }: { label: string; part: ScorePart }) {
  const pct = part.max ? (100 * part.score) / part.max : 0
  const thin = pct < 50
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className="text-brand-50/90">{label}</span>
        <span className="tabular-nums font-semibold">
          {part.score}
          <span className="text-brand-100/80">/{part.max}</span>
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-white/20">
        <div
          className={`h-full rounded-full ${thin ? 'bg-amber-300' : 'bg-white'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

/** Who decided this score. A rubric mark and a machine's opinion look identical
 * on screen, so any task where a model sets the numbers has to say so — otherwise
 * the confidence of the layout does the arguing. */
export function ScoredByNote({ scoredBy, outOf }: { scoredBy?: 'model' | 'code'; outOf?: number }) {
  const rep = outOf ? REPEATABILITY[outOf] : undefined
  if (scoredBy === 'code') {
    return (
      <p className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50/70 p-3 text-xs text-emerald-800">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
        <span>
          <strong>Marked by code.</strong> This was checked against the official rules, so the same
          answer always gets the same mark.
        </span>
      </p>
    )
  }
  if (scoredBy !== 'model') return null
  return (
    <p className="flex items-start gap-2 rounded-xl border border-violet-200 bg-violet-50/70 p-3 text-xs text-violet-900">
      <Bot className="mt-0.5 size-4 shrink-0 text-violet-600" aria-hidden="true" />
      <span>
        <strong>Scored by AI.</strong> An AI marked this against the rubric. It&rsquo;s a practice
        estimate to work from, not an official result &mdash; a human examiner can score
        differently.{' '}
        {rep && (
          <>
            When we scored the same response {rep.runs} times, the total moved by up to{' '}
            <strong>
              {rep.moved} of {outOf}
            </strong>
            .{' '}
          </>
        )}
        Traits marked <em>checked by code</em> below are measured, not judged.
      </span>
    </p>
  )
}

/** Per-trait provenance, so the measured parts of a model-scored rubric stand out. */
function TraitSource({ scoredBy, advisory }: { scoredBy?: 'model' | 'code'; advisory?: boolean }) {
  if (advisory) {
    return (
      <span className="rounded-full bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium text-violet-700 ring-1 ring-violet-200">
        advice only · doesn’t count
      </span>
    )
  }
  if (scoredBy === 'code') {
    return (
      <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 ring-1 ring-emerald-200">
        checked by code
      </span>
    )
  }
  if (scoredBy === 'model') {
    return (
      <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
        AI judgement
      </span>
    )
  }
  return null
}

/** The score header + trait breakdown + inline corrections + priorities, reused
 * by the live result and the history-detail modal. */
export function FeedbackBody({ r, essay }: { r: EssayFeedback; essay?: string }) {
  const pct = r.max_raw_total ? Math.round((100 * r.raw_total) / r.max_raw_total) : 0
  const split = splitScore(r.traits)
  return (
    <div className="space-y-5">
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

        {/* One total hides two very different things: what you said, and how
         * neatly you wrote it. A tidy essay about nothing keeps most of the
         * language marks, so the total alone reads far kinder than it should. */}
        {split && (
          <div className="mt-4 space-y-2 border-t border-white/15 pt-4">
            <SplitBar label="What you said" part={split.ideas} />
            <SplitBar label="How you wrote it" part={split.language} />
          </div>
        )}
      </div>

      {split && carriedByWriting(split) && (
        <p className="flex items-start gap-2 rounded-xl border-l-3 border-amber-400 bg-amber-50 p-4 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" aria-hidden="true" />
          <span>
            <strong>Most of your marks came from how you wrote, not what you said.</strong> Your
            spelling, grammar and sentences scored {split.language.score} out of {split.language.max},
            but your ideas only scored {split.ideas.score} out of {split.ideas.max}. Neat writing
            carries a score a long way. The marks you&rsquo;re missing are for taking a clear position
            and giving real reasons for it &mdash; add an example or a consequence to each reason.
          </span>
        </p>
      )}

      <ScoredByNote scoredBy={r.scored_by} outOf={r.max_raw_total} />

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
                <h3 className="flex flex-wrap items-center gap-2 font-display text-sm font-semibold text-slate-900">
                  {TRAIT_LABEL[t.name] ?? t.name}
                  <TraitSource scoredBy={t.scored_by} advisory={t.advisory} />
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

      {essay && r.errors && r.errors.length > 0 && <Corrections essay={essay} errors={r.errors} />}
    </div>
  )
}

/** Inline error corrections: the essay is shown with each flagged span struck
 * through and its fix beside it, plus a scannable list grouped by type. */
function Corrections({ essay, errors }: { essay: string; errors: EssayError[] }) {
  // Walk the essay, wrapping each error's exact span in place (errors arrive in
  // order of appearance). Spans that can't be located are still listed below.
  const nodes: React.ReactNode[] = []
  let cursor = 0
  errors.forEach((e, i) => {
    if (!e.wrong) return
    const idx = essay.indexOf(e.wrong, cursor)
    if (idx === -1) return
    if (idx > cursor) nodes.push(<span key={`t${i}`}>{essay.slice(cursor, idx)}</span>)
    nodes.push(
      <span key={`e${i}`}>
        <span className="rounded-sm bg-rose-100 px-0.5 text-rose-700 line-through decoration-rose-400">
          {e.wrong}
        </span>
        <span className="rounded-sm bg-emerald-100 px-0.5 font-medium text-emerald-800">{e.correct}</span>
      </span>,
    )
    cursor = idx + e.wrong.length
  })
  if (cursor < essay.length) nodes.push(<span key="tail">{essay.slice(cursor)}</span>)

  return (
    <div>
      <div className="mb-2 flex items-center gap-3">
        <h3 className="font-display text-sm font-semibold text-slate-900">Corrections</h3>
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
          {errors.length}
        </span>
        <span className="ml-auto text-xs text-slate-400">
          <span className="text-rose-600 line-through">as written</span> ·{' '}
          <span className="text-emerald-700">suggested</span>
        </span>
      </div>
      <p className="whitespace-pre-wrap rounded-xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-700">
        {nodes}
      </p>
      <ul className="mt-3 flex flex-wrap gap-2">
        {errors.map((e, i) => (
          <li
            key={i}
            className="inline-flex items-center gap-1 rounded-lg bg-slate-50 px-2 py-1 text-xs ring-1 ring-slate-200/70"
            title={e.type.replace(/_/g, ' ')}
          >
            <span className="text-rose-600 line-through">{e.wrong}</span>
            <span className="text-slate-400">→</span>
            <span className="font-medium text-emerald-700">{e.correct}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
