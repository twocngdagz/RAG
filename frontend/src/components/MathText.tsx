import katex from 'katex'
import 'katex/dist/katex.min.css'
import type { ReactNode } from 'react'

/**
 * Render a string that may contain LaTeX maths, splitting it into plain text and
 * `$…$` / `$$…$$` maths spans and rendering each span with KaTeX.
 *
 * A hand-written tokenizer, NOT a regex, because `$` is overloaded: it delimits
 * maths, but `\$` inside a span is an escaped dollar (currency), e.g. `$\$35$`.
 * A naive `\$([^$]+)\$` breaks on the first `\$` and mis-pairs the delimiters.
 * The scanner treats `\$` as a literal dollar and only bare `$`/`$$` as delimiters.
 *
 * PTE lessons contain no `$`, so the fast path returns the string untouched.
 */

type Token = { kind: 'text' | 'inline' | 'display'; value: string }

function tokenize(text: string): Token[] {
  const tokens: Token[] = []
  let buf = ''
  let i = 0
  const n = text.length

  const flush = () => {
    if (buf) tokens.push({ kind: 'text', value: buf })
    buf = ''
  }

  while (i < n) {
    // Escaped dollar -> a literal '$' in the surrounding text.
    if (text[i] === '\\' && text[i + 1] === '$') {
      buf += '$'
      i += 2
      continue
    }
    if (text[i] === '$') {
      const display = text[i + 1] === '$'
      const delimLen = display ? 2 : 1
      let j = i + delimLen
      let inner = ''
      let closed = false
      while (j < n) {
        // Keep an escaped dollar inside the span; KaTeX renders \$ as '$'.
        if (text[j] === '\\' && text[j + 1] === '$') {
          inner += '\\$'
          j += 2
          continue
        }
        if (display && text[j] === '$' && text[j + 1] === '$') {
          closed = true
          break
        }
        if (!display && text[j] === '$') {
          closed = true
          break
        }
        inner += text[j]
        j += 1
      }
      if (closed && inner.trim()) {
        flush()
        tokens.push({ kind: display ? 'display' : 'inline', value: inner })
        i = j + delimLen
        continue
      }
      // No closing delimiter (or empty span): treat the '$' as ordinary text.
      buf += text[i]
      i += 1
      continue
    }
    buf += text[i]
    i += 1
  }
  flush()
  return tokens
}

function renderTex(tex: string, display: boolean): string {
  // throwOnError:false makes KaTeX emit a red error node rather than throw, so a
  // malformed expression degrades to visible-but-contained instead of a crash.
  return katex.renderToString(tex, { throwOnError: false, displayMode: display })
}

export function MathText({ children }: { children?: string | null }): ReactNode {
  const text = children ?? ''
  if (!text.includes('$')) return text // fast path: no maths (all PTE content)

  const tokens = tokenize(text)
  return (
    <>
      {tokens.map((t, i) =>
        t.kind === 'text' ? (
          <span key={i}>{t.value}</span>
        ) : (
          <span
            key={i}
            className={t.kind === 'display' ? 'katex-display-inline' : undefined}
            dangerouslySetInnerHTML={{ __html: renderTex(t.value, t.kind === 'display') }}
          />
        ),
      )}
    </>
  )
}
