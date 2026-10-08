import assert from 'node:assert/strict'
import { test } from 'node:test'
import { existsSync, readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'
test('preserved guide refresh keeps selected appearance and replaces restoration colors', () => {
  const file = 'src/views/chat/component/g2ThemeGuides.ts'
  assert.ok(existsSync(file), 'preserved guides require state-aware repaint')
  const exports = {}
  vm.runInNewContext(
    ts.transpileModule(readFileSync(file, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText,
    { exports }
  )
  const marker = {
    __states__: ['unselected'],
    __ordinal__: { fill: '#4f7df3' },
    style: { fill: '#aaa' },
    children: [],
    attr(k, v) {
      this.style[k] = v
    },
  }
  const guide = {
    children: [marker],
    update() {
      marker.style.fill = '#79a6ff'
    },
  }
  exports.refreshStatefulGuide(guide, {})
  assert.equal(marker.style.fill, '#aaa')
  assert.equal(marker.__ordinal__.fill, '#79a6ff')
  // G2 restoring its original state must now restore the new theme.
  marker.attr('fill', marker.__ordinal__.fill)
  assert.equal(marker.style.fill, '#79a6ff')
})
