import { Component, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

/** Stops one bad lesson (or any render error) from blanking the whole app.
 * Renders a small fallback card instead of unmounting the tree. */
export class ErrorBoundary extends Component<
  { children: ReactNode; label?: string },
  { error: Error | null }
> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidUpdate(prev: { children: ReactNode }) {
    // Reset when the children change (e.g. navigating to another lesson).
    if (prev.children !== this.props.children && this.state.error) {
      this.setState({ error: null })
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8">
          <div className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-5 text-amber-900">
            <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-500" aria-hidden="true" />
            <div>
              <p className="font-semibold">This {this.props.label ?? 'view'} couldn't be displayed.</p>
              <p className="mt-1 text-sm text-amber-800">
                The content is stored but its shape doesn't match what this view expects. Try another
                lesson, or switch to the “From the book” tab.
              </p>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
