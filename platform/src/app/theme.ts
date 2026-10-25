import { useSyncExternalStore } from 'react'
import type { ThemeMode } from './settings'

export type Theme = 'light' | 'dark'

const systemDark = window.matchMedia('(prefers-color-scheme: dark)')
const listeners = new Set<() => void>()
let mode: ThemeMode = 'auto'
let current: Theme | undefined

const resolve = (): Theme => (mode !== 'auto' ? mode : systemDark.matches ? 'dark' : 'light')

function apply() {
  const next = resolve()
  if (next === current) return
  current = next
  document.documentElement.dataset.theme = next
  for (const listener of listeners) listener()
}

// 'auto' follows the operating system, also when it changes while the page is open.
systemDark.addEventListener('change', apply)

/** From the settings; call before the first render so the page never flashes the wrong theme. */
export function setThemeMode(next: ThemeMode) {
  mode = next
  apply()
}

const getTheme = (): Theme => current ?? 'light'

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export const useTheme = () => useSyncExternalStore(subscribe, getTheme)
