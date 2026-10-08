import { COLOR_THEME_SWITCHING_ENABLED, DEFAULT_THEME, THEME_STORAGE_KEY, type ThemeMode } from './themeConfig'

interface AccountThemeDependencies {
  load: (accountId: string) => Promise<{ theme: ThemeMode }>
  save: (theme: ThemeMode, accountId: string) => Promise<{ theme: ThemeMode }>
  apply: (theme: ThemeMode) => void
  publish: (key: string) => void
  status: (state: { ready: boolean; saving: boolean }) => void
}

export function createAccountTheme(deps: AccountThemeDependencies) {
  let accountId = ''
  let generation = 0
  let revision = 0
  let confirmed: ThemeMode = DEFAULT_THEME
  let ready = false
  let saving = false
  let syncWhileSaving = false
  const status = () => deps.status({ ready, saving })
  const valid = (value: unknown): value is ThemeMode => value === 'light' || value === 'dark'
  const reset = () => {
    generation++
    revision++
    accountId = ''
    ready = false
    saving = false
    syncWhileSaving = false
    confirmed = DEFAULT_THEME
    deps.apply(DEFAULT_THEME)
    status()
  }
  return {
    reset,
    async bind(id: string, accountSession = true) {
      if (!accountSession) { reset(); return }
      if (id === accountId && ready) return
      reset()
      if (!id || !COLOR_THEME_SWITCHING_ENABLED) return
      accountId = id
      const session = generation
      const requestRevision = revision
      try {
        const result = await deps.load(id)
        if (session !== generation || requestRevision !== revision) return
        if (!valid(result.theme)) throw new Error('账户配色设置无效')
        confirmed = result.theme
        ready = true
        deps.apply(confirmed)
        status()
      } catch (error) {
        if (session !== generation || requestRevision !== revision) return
        throw error
      }
    },
    async choose(theme: ThemeMode) {
      if (!COLOR_THEME_SWITCHING_ENABLED || !accountId || !ready || saving) return
      if (!valid(theme)) throw new Error('配色只能是浅色或深色')
      if (theme === confirmed) return
      const session = generation
      const owner = accountId
      revision++
      saving = true
      deps.apply(theme)
      status()
      try {
        const result = await deps.save(theme, owner)
        if (session !== generation) return
        if (result.theme !== theme) throw new Error('账户配色保存结果不一致')
        confirmed = theme
        deps.publish(`${THEME_STORAGE_KEY}:${owner}`)
      } catch (error) {
        if (session !== generation) return
        deps.apply(confirmed)
        throw error
      } finally {
        if (session === generation) {
          while (syncWhileSaving && session === generation) {
            // A second tab committed while this save was in flight. Reconcile
            // with the database rather than trusting response/event arrival order.
            syncWhileSaving = false
            try {
              const result = await deps.load(owner)
              if (session === generation) {
                if (!valid(result.theme)) throw new Error('账户配色设置无效')
                confirmed = result.theme
                deps.apply(confirmed)
              }
            } catch (error) {
              if (session === generation) {
                ready = false
                saving = false
                status()
                throw error
              }
            }
          }
        }
        if (session !== generation) return
        if (session === generation) {
          saving = false
          status()
        }
      }
    },
    async acceptStorage(key: string | null, value: string | null) {
      if (!COLOR_THEME_SWITCHING_ENABLED || !accountId ||
          key !== `${THEME_STORAGE_KEY}:${accountId}` || !value) return
      if (saving) { syncWhileSaving = true; return }
      // Storage is an invalidation signal, never a source of preference values:
      // network responses and browser events can arrive in a different order.
      const session = generation
      const requestRevision = ++revision
      try {
        const result = await deps.load(accountId)
        if (session !== generation || requestRevision !== revision) return
        if (!valid(result.theme)) throw new Error('账户配色设置无效')
        confirmed = result.theme
        ready = true
        deps.apply(confirmed)
        status()
      } catch (error) {
        if (session !== generation || requestRevision !== revision) return
        ready = false
        status()
        throw error
      }
    },
  }
}
