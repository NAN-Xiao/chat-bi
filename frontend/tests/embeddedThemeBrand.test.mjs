import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
import colorFunctions from 'less/lib/less/functions/color.js'
import colorTree from 'less/lib/less/tree/color.js'

test('explicit embedded brand controls theme accents and buttons, then restores host styles', () => {
  const source = readFileSync('src/utils/utils.ts', 'utf8')
  const fn = source.slice(source.indexOf('export const setCurrentColor'), source.indexOf('export const getQueryString'))
  const exports = {}
  vm.runInNewContext(ts.transpileModule(fn, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText,
    { exports, colorStringToHex: value => value, colorFunctions: colorFunctions.default, colorTree: colorTree.default })
  const values = new Map([['--theme-accent-text', '#abcdef']])
  const element = { style: {
    getPropertyValue: key => values.get(key) || '', getPropertyPriority: () => '',
    setProperty: (key, value) => values.set(key, value), removeProperty: key => values.delete(key),
  } }
  const restore = exports.setCurrentColor('#1cba90', element)
  for (const key of ['--theme-accent-text', '--theme-button-primary-bg', '--ed-color-primary', '--el-color-primary']) {
    assert.equal(values.get(key), '#1cba90', key)
  }
  assert.equal(values.get('--workspace-primary-soft-bg'), '#1cba901a')
  restore()
  assert.deepEqual([...values], [['--theme-accent-text', '#abcdef']])
})

for (const page of ['index', 'page']) {
  test(`${page} ignores pending configuration and queued style updates after unmount`, () => {
    const source = readFileSync(`src/views/embedded/${page}.vue`, 'utf8')
    const config = source.slice(source.indexOf('let disposed = false'), source.indexOf('onBeforeMount(async'))
    const teardown = source.match(/onBeforeUnmount\(\(\) => \{[\s\S]*?\n\}\)/)[0]
    for (const phase of ['request', 'nextTick']) {
      let respond, tick, unmount
      let writes = 0
      const script = ts.transpileModule(config + '\n' + teardown + '\nloadAssistantConfig("fixture")', {
        compilerOptions: { module: ts.ModuleKind.CommonJS },
      }).outputText
      vm.runInNewContext(script, {
        request: { get: () => ({ then: fn => { respond = fn } }) },
        nextTick: fn => { tick = fn }, onBeforeUnmount: fn => { unmount = fn },
        window: { removeEventListener() {} }, communicationCb() {},
        customSet: { theme: '#1cba90' }, assistantStore: { setAutoDs() {} },
        setCurrentColor: () => { writes++; return () => {} },
        document: { querySelector: () => ({ style: { setProperty: () => { writes++ } } }) },
      })
      if (phase === 'request') unmount()
      respond({ configuration: '{"theme":"#1cba90"}' })
      if (phase === 'nextTick') { unmount(); tick() }
      assert.equal(writes, 0, phase)
    }
  })
}
