import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
test('bootstrap defaults to light until account identity and preference are loaded', () => {
  for (const enabled of [true, false])
    for (const stored of ['dark', 'light', 'invalid']) {
      const exports = {}
      vm.runInNewContext(
        ts.transpileModule(readFileSync('plugins/themeBootstrap.ts', 'utf8'), {
          compilerOptions: { module: ts.ModuleKind.CommonJS },
        }).outputText,
        {
          exports,
          require: () => ({
            COLOR_THEME_SWITCHING_ENABLED: enabled,
            DEFAULT_THEME: 'light',
            THEME_STORAGE_KEY: 'shuzhi-theme-mode',
          }),
        }
      )
      const plugin = exports.themeBootstrapPlugin()
      assert.equal(plugin.transformIndexHtml.order, 'pre')
      const tags = plugin.transformIndexHtml.handler()
      const root = { dataset: {}, classList: { add() {} }, style: {} }
      vm.runInNewContext(tags.find((t) => t.tag === 'script').children, {
        document: { documentElement: root },
        localStorage: { getItem: () => stored },
      })
      assert.equal(root.dataset.theme, 'light')
      assert.ok(tags.every((t) => t.injectTo === 'head-prepend'))
    }
})
