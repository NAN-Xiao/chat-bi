import {
  COLOR_THEME_SWITCHING_ENABLED,
  DEFAULT_THEME,
  THEME_CHANGE_EVENT,
  type ThemeMode,
} from './themeConfig'
export * from './themeConfig'
let currentTheme: ThemeMode | undefined
let initialized = false
export const isThemeMode = (value: unknown): value is ThemeMode =>
  value === 'dark' || value === 'light'
export function getInitialTheme(): ThemeMode {
  if (!COLOR_THEME_SWITCHING_ENABLED) return DEFAULT_THEME
  if (currentTheme) return currentTheme
  // Until identity is verified, never restore another account's browser preference.
  return DEFAULT_THEME
}
export const getCurrentTheme = (): ThemeMode => currentTheme ?? getInitialTheme()
function updateTheme(value: ThemeMode) {
  if (typeof document === 'undefined') return
  const next = COLOR_THEME_SWITCHING_ENABLED && isThemeMode(value) ? value : DEFAULT_THEME
  const previous = currentTheme ?? getInitialTheme()
  currentTheme = next
  const root = document.documentElement
  root.dataset.theme = next
  root.classList.toggle('dark', next === 'dark')
  root.classList.toggle('light', next === 'light')
  root.style.colorScheme = next
  if (previous === next) return
  window.dispatchEvent(new CustomEvent<ThemeMode>(THEME_CHANGE_EVENT, { detail: next }))
}
export const applyTheme = (value: ThemeMode): void => updateTheme(value)
export function applyInitialTheme(): void {
  if (typeof window === 'undefined' || initialized) return
  updateTheme(getInitialTheme())
  initialized = true
}
export function subscribeTheme(listener: (theme: ThemeMode) => void): () => void {
  if (typeof window === 'undefined') return () => {}
  const handle = () => listener(getCurrentTheme())
  window.addEventListener(THEME_CHANGE_EVENT, handle)
  return () => window.removeEventListener(THEME_CHANGE_EVENT, handle)
}
export const getNextTheme = (theme: ThemeMode): ThemeMode =>
  COLOR_THEME_SWITCHING_ENABLED && theme === 'light' ? 'dark' : DEFAULT_THEME
