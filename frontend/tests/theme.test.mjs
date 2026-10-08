import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

function load(enabled, stored = null, blocked = false) {
  const listeners = new Map()
  const root = { dataset: {}, classList: { toggle() {} }, style: {} }
  let writes = 0
  const window = {
    localStorage: {
      getItem() {
        if (blocked) throw Error('denied')
        return stored
      },
      setItem(key, value) {
        if (blocked) throw Error('denied')
        writes++
        stored = value
      },
    },
    addEventListener(name, cb) {
      const set = listeners.get(name) || new Set()
      set.add(cb)
      listeners.set(name, set)
    },
    removeEventListener(name, cb) {
      listeners.get(name)?.delete(cb)
    },
    dispatchEvent(event) {
      listeners.get(event.type)?.forEach((cb) => cb(event))
    },
  }
  const exports = {}
  const config = {
    COLOR_THEME_SWITCHING_ENABLED: enabled,
    DEFAULT_THEME: 'light',
    THEME_STORAGE_KEY: 'shuzhi-theme-mode',
    THEME_CHANGE_EVENT: 'shuzhi-theme-change',
  }
  let source = readFileSync('src/utils/theme.ts', 'utf8')
  // Allow the baseline (constants were originally defined in theme.ts) to run the same behavior tests.
  source = source.replace(
    /export const COLOR_THEME_SWITCHING_ENABLED = (false|true)/,
    `export const COLOR_THEME_SWITCHING_ENABLED = ${enabled}`
  )
  vm.runInNewContext(
    ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    {
      exports,
      require: () => config,
      window,
      document: { documentElement: root },
      CustomEvent: class {
        constructor(type, options) {
          this.type = type
          this.detail = options.detail
        }
      },
    }
  )
  return { api: exports, root, window, listeners, writes: () => writes }
}

test('disabled gate rejects old dark preference and runtime calls', () => {
  const { api, root } = load(false, 'dark')
  api.applyInitialTheme()
  api.applyTheme('dark')
  assert.equal(root.dataset.theme, 'light')
})
test('unverified browser preference is never restored before account loading', () => {
  for (const [stored, expected] of [
    ['dark', 'light'],
    ['invalid', 'light'],
    [null, 'light'],
  ]) {
    const { api, root } = load(true, stored)
    api.applyInitialTheme()
    assert.equal(root.dataset.theme, expected)
  }
})
test('initialization and repeated application do not emit duplicate changes or rewrite preference', () => {
  const { api, window, writes } = load(true, 'light')
  let changes = 0
  window.addEventListener('shuzhi-theme-change', () => changes++)
  api.applyInitialTheme()
  api.applyInitialTheme()
  api.applyTheme('light')
  assert.equal(changes, 0)
  assert.equal(writes(), 0)
  api.applyTheme('dark')
  api.applyTheme('dark')
  assert.equal(changes, 1)
  assert.equal(writes(), 0)
})
test('blocked persistence retains the current runtime selection', () => {
  const { api, root } = load(true, null, true)
  api.applyInitialTheme()
  api.applyTheme('dark')
  assert.equal(api.getInitialTheme(), 'dark')
  assert.equal(root.dataset.theme, 'dark')
})
test('visual runtime ignores unscoped storage events and subscriptions dispose', () => {
  const { api, root, window, writes } = load(true)
  api.applyInitialTheme()
  let changes = 0
  const dispose = api.subscribeTheme(() => changes++)
  window.dispatchEvent({ type: 'storage', key: 'shuzhi-theme-mode', newValue: 'dark', storageArea: window.localStorage })
  assert.equal(root.dataset.theme, 'light')
  api.applyTheme('dark')
  assert.equal(changes, 1)
  assert.equal(writes(), 0)
  dispose()
  api.applyTheme('light')
  assert.equal(changes, 1)
})
