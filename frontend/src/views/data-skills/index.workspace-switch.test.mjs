import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const source = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')

test('Skills 页面在工作空间切换完成后刷新，并清理旧空间数据', () => {
  assert.match(source, /WORKSPACE_CONTEXT_CHANGE_EVENT/)
  const handler = source.slice(source.indexOf('name: WORKSPACE_CONTEXT_CHANGE_EVENT'))
  assert.match(handler, /event\?\.phase === 'changing'/)
  assert.match(handler, /skillList\.value = \[\]/)
  assert.match(handler, /event\?\.phase !== 'changed'/)
  assert.match(handler, /loadSkills\(\)/)
})

test('Skills 列表忽略工作空间切换期间完成的旧请求', () => {
  assert.match(source, /let skillLoadGeneration = 0/)
  assert.match(source, /const generation = \+\+skillLoadGeneration/)
  assert.match(source, /if \(generation !== skillLoadGeneration\) return/)
})
