import { useEffect, useState } from 'react'

/** Returns `value`, but only after it has stopped changing for `delayMs`. */
export function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer) // a new keystroke cancels the pending update
  }, [value, delayMs])
  return debounced
}
