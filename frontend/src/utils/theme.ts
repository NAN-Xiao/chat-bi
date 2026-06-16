export type ThemeMode = 'dark' | 'light'

export const THEME_STORAGE_KEY = 'zhishu-theme-mode'
export const THEME_CHANGE_EVENT = 'zhishu-theme-change'
export const DEFAULT_THEME: ThemeMode = 'dark'

export const isThemeMode = (value: string | null): value is ThemeMode => {
  return value === 'dark' || value === 'light'
}

export const getInitialTheme = (): ThemeMode => {
  if (typeof window === 'undefined') {
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

  const root = document.documentElement
  root.dataset.theme = value
  root.classList.toggle('dark', value === 'dark')
  root.classList.toggle('light', value === 'light')
  root.style.colorScheme = value

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, value)
  } catch {
    // Current page still updates when storage is unavailable.
  }

  window.dispatchEvent(new CustomEvent<ThemeMode>(THEME_CHANGE_EVENT, { detail: value }))
}

export const applyInitialTheme = () => {
  applyTheme(getInitialTheme())
}

export const getNextTheme = (theme: ThemeMode): ThemeMode => {
  return theme === 'dark' ? 'light' : 'dark'
}
