import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import less from 'less'

test('editor card shell owns the same single themed outline as preview', async () => {
  const { css } = await less.render(readFileSync('src/views/dashboard/css/CanvasStyle.less', 'utf8'))
  const shell = css.match(/\.dragAndResize \.item \.item-content\s*\{([^}]+)\}/)?.[1]
  assert.ok(shell)
  assert.match(shell, /border: 1px solid var\(--theme-card-border\)/)
  assert.match(shell, /border-radius: var\(--theme-card-radius\)/)
  assert.match(shell, /background-color: var\(--workspace-card-bg\)/)
  assert.match(shell, /box-shadow: none/)
  assert.match(css, /\.item-content > :deep\(\.chart-base-container\)\s*\{[^}]*border: 0;/)
  assert.doesNotMatch(css, /\.item-content :deep\(\.chart-base-container\)/, 'nested Tab cards keep their own outline')
  assert.match(css, /\.itemActive\s*\{[^}]*outline: 1px solid/, 'selection outline stays separate from card chrome')
})
