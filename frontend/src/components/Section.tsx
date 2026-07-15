import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/** One learning section: a labelled region with an icon, title, and one-line
 * purpose. Plain layout, not a card — the frontend-skill's app restraint. */
export function Section({
  icon: Icon,
  title,
  purpose,
  children,
}: {
  icon: LucideIcon
  title: string
  purpose?: string
  children: ReactNode
}) {
  return (
    <section className="animate-rise scroll-mt-24 border-t border-slate-200 pt-8">
      <div className="mb-4 flex items-start gap-3">
        <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-brand-700 ring-1 ring-brand-100">
          <Icon className="size-4.5" aria-hidden="true" />
        </span>
        <div>
          <h2 className="text-lg font-semibold leading-tight">{title}</h2>
          {purpose && <p className="mt-0.5 text-sm text-slate-500">{purpose}</p>}
        </div>
      </div>
      {children}
    </section>
  )
}
