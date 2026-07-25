import { useState } from 'react'
import { BookOpenCheck, ChevronDown, Sparkles } from 'lucide-react'
import type { Grounded } from '../lib/types'
import { MathText } from './MathText'

/**
 * Renders one grounded leaf and surfaces WHERE it came from — the whole point of
 * the grounding pipeline, made visible to the learner. Source-backed text gets a
 * quiet "From the book" control that reveals the exact supporting quote; content
 * the model composed for teaching gets a subtle "Practice" tag. Insufficient /
 * empty items render nothing.
 */
export function GroundedText({
  g,
  as: Tag = 'p',
  className = '',
  showGeneratedTag = false,
}: {
  g: Grounded | undefined
  as?: 'p' | 'span' | 'div'
  className?: string
  showGeneratedTag?: boolean
}) {
  const [open, setOpen] = useState(false)
  if (!g?.text) return null

  const sourced = g.origin === 'source_grounded' && g.evidence_spans.length > 0

  return (
    <div className={className}>
      <Tag className="text-slate-700"><MathText>{g.text}</MathText></Tag>

      {sourced && (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="group mt-2 inline-flex cursor-pointer items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-emerald-200/70 transition-colors hover:bg-emerald-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
          >
            <BookOpenCheck className="size-3.5" aria-hidden="true" />
            From the book
            <ChevronDown
              className={`size-3.5 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
              aria-hidden="true"
            />
          </button>
          {open && (
            <div className="animate-rise mt-2 space-y-2 border-l-2 border-emerald-300 pl-3">
              {g.evidence_spans.map((span, i) => (
                <blockquote key={i} className="text-sm italic text-slate-600">
                  “{span.quote.replace(/\s+/g, ' ').trim()}”
                </blockquote>
              ))}
            </div>
          )}
        </>
      )}

      {showGeneratedTag && g.origin === 'pedagogical_generation' && (
        <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 ring-1 ring-amber-200/70">
          <Sparkles className="size-3" aria-hidden="true" />
          Practice
        </span>
      )}
    </div>
  )
}
