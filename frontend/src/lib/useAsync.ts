import { useEffect, useState } from 'react'

type State<T> = { data?: T; error?: string; loading: boolean }

/** Minimal fetch-on-mount hook. Reruns when any dep changes. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): State<T> {
  const [state, setState] = useState<State<T>>({ loading: true })
  useEffect(() => {
    let alive = true
    setState({ loading: true })
    fn()
      .then((data) => alive && setState({ data, loading: false }))
      .catch((e) => alive && setState({ error: String(e), loading: false }))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}
