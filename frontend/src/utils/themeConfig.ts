export type ThemeMode = 'dark' | 'light'
export const THEME_STORAGE_KEY = 'shuzhi-theme-mode'
export const THEME_CHANGE_EVENT = 'shuzhi-theme-change'
// Shared gate for bootstrap, runtime and switcher. Set false to force light mode.
export const COLOR_THEME_SWITCHING_ENABLED = true
export const DEFAULT_THEME: ThemeMode = 'light'
