import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

/** Keep UI state (tabs, filters, the open request) in the URL so it can be deep-linked,
 * shared, and survives refresh / back-forward. */
export function useUrlState<T extends string>(key: string, fallback: T) {
  const [params, setParams] = useSearchParams()
  const value = (params.get(key) as T | null) ?? fallback
  const set = useCallback(
    (next: T | null) =>
      setParams(
        (p) => {
          const n = new URLSearchParams(p)
          if (next === null || next === fallback) n.delete(key)
          else n.set(key, next)
          return n
        },
        { replace: true },
      ),
    [key, fallback, setParams],
  )
  return [value, set] as const
}

/** The request sheet: `?request=42` opens request #42 on any page. */
export function useOpenRequest() {
  const [raw, set] = useUrlState<string>('request', '')
  const id = raw ? Number(raw) : null
  return [
    Number.isFinite(id) && id ? id : null,
    (next: number | null) => set(next ? String(next) : null),
  ] as const
}
