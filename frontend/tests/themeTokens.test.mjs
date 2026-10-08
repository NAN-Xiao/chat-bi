import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import less from 'less'
test('dark workspace and canvas tokens match graphite surfaces', async () => {
  const { css } = await less.render(readFileSync('src/style.less', 'utf8'), {
    filename: 'src/style.less',
  })
  const blocks = [...css.matchAll(/:root\[data-theme='dark'\]\s*\{([^}]+)\}/g)]
  const vars = Object.fromEntries(
    blocks.flatMap((m) =>
      [...m[1].matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((v) => [v[1], v[2].trim().toLowerCase()])
    )
  )
  assert.equal(vars['--workspace-card-bg'], '#202733')
  assert.equal(vars['--theme-shell-bg'], '#141b25')
  assert.equal(vars['--theme-chart-grid'], '#384658')
  assert.equal(vars['--theme-text-tertiary'], '#8b9cb2')
  assert.equal(vars['--theme-chart-blue'], '#79a6ff')
})

test('dark accent and ownership labels stay readable on their surfaces', async () => {
  const { css } = await less.render(readFileSync('src/styles/theme-tokens.less', 'utf8'))
  const vars = {}
  for (const m of css.matchAll(/:root(?:\[data-theme='dark'\])?\s*\{([^}]+)\}/g)) {
    for (const v of m[1].matchAll(/(--[\w-]+):\s*([^;]+);/g)) vars[v[1]] = v[2].trim()
  }
  const resolve = key => {
    assert.ok(vars[key], `missing paired theme token ${key}`)
    const reference = vars[key].match(/^var\((--[\w-]+)\)$/)
    return reference ? resolve(reference[1]) : vars[key]
  }
  const luminance = hex => {
    assert.match(hex, /^#[\da-f]{6}$/i)
    const rgb = hex.slice(1).match(/../g).map(v => parseInt(v, 16) / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    return .2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2]
  }
  for (const [text, bg] of [['--ed-color-primary','--workspace-card-bg'], ['--ed-color-primary','--ed-color-primary-80'], ['--el-color-primary','--workspace-card-bg'], ...['platform','workspace','personal'].map(scope => [`--theme-${scope}-text`,`--theme-${scope}-bg`])]) {
    const a=luminance(resolve(text)),b=luminance(resolve(bg))
    assert.ok((Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5, `${text} is unreadable on ${bg}`)
  }
})
