export type ThemeMode = 'dark' | 'light'

export const THEME_STORAGE_KEY = 'shuzhi-theme-mode'
export const THEME_CHANGE_EVENT = 'shuzhi-theme-change'
// Dark mode is not production-ready yet. Keep the implementation for future restoration,
// but force the running app to light mode while the public switch is disabled.
export const COLOR_THEME_SWITCHING_ENABLED = false
export const DEFAULT_THEME: ThemeMode = 'light'

export const isThemeMode = (value: string | null): value is ThemeMode => {
  return value === 'dark' || value === 'light'
}

export const getInitialTheme = (): ThemeMode => {
  if (typeof window === 'undefined') {
    return DEFAULT_THEME
  }

  if (!COLOR_THEME_SWITCHING_ENABLED) {
    return DEFAULT_THEME
  }

  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
    if (isThemeMode(storedTheme)) {
      return storedTheme
    }
  } catch {
    // Restricted browser contexts can skip persistence and use the default theme.
  }

  return DEFAULT_THEME
}

export const applyTheme = (value: ThemeMode) => {
  if (typeof document === 'undefined') {
    return
  }

  const nextValue = COLOR_THEME_SWITCHING_ENABLED ? value : DEFAULT_THEME
  const root = document.documentElement
  root.dataset.theme = nextValue
  root.classList.toggle('dark', nextValue === 'dark')
  root.classList.toggle('light', nextValue === 'light')
  root.style.colorScheme = nextValue

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, nextValue)
  } catch {
    // Current page still updates when storage is unavailable.
  }

  window.dispatchEvent(new CustomEvent<ThemeMode>(THEME_CHANGE_EVENT, { detail: nextValue }))
}

export const applyInitialTheme = () => {
  applyTheme(getInitialTheme())
}

export const getNextTheme = (theme: ThemeMode): ThemeMode => {
  if (!COLOR_THEME_SWITCHING_ENABLED) {
    return DEFAULT_THEME
  }
  return theme === 'dark' ? 'light' : 'dark'
}
