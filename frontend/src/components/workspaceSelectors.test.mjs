import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const agentSource = readFileSync(
  new URL('./custom-agent/AgentSelector.vue', import.meta.url),
  'utf8'
)
const skillSource = readFileSync(
  new URL('./data-skill/DataSkillSelector.vue', import.meta.url),
  'utf8'
)
const dedupeSource = readFileSync(new URL('../utils/requestDedupe.ts', import.meta.url), 'utf8')

test('Agent 和 Data Skills 仅在 ready 且有数据源时请求', () => {
  for (const source of [agentSource, skillSource]) {
    assert.match(source, /workspaceContextState\.phase !== 'ready'/)
    assert.match(source, /!datasourceIdValue\.value/)
    assert.match(source, /getEffectiveWorkspaceTenantId\(\)/)
  }
})

test('两个缓存键都包含租户、数据源和目标作用域', () => {
  assert.match(
    agentSource,
    /AGENT_SELECTOR_CACHE_PREFIX.*tenantId.*datasourceId.*targetScope/s
  )
  assert.match(
    skillSource,
    /DATA_SKILL_SELECTOR_CACHE_PREFIX.*tenantId.*datasourceId.*targetScope/s
  )
})

test('只有最新加载序号可以更新列表与 loading', () => {
  for (const source of [agentSource, skillSource]) {
    assert.match(source, /const loadId = \+\+loadSequence/)
    assert.match(source, /if \(loadId !== loadSequence\) return/)
    assert.match(source, /if \(loadId === loadSequence\) \{\s*loading\.value = false/)
  }
})

test('watcher 监听工作空间 phase 和活动租户', () => {
  for (const source of [agentSource, skillSource]) {
    assert.match(source, /workspaceContextState\.phase/)
    assert.match(source, /workspaceContextState\.activeTenantId/)
  }
})

test('切换事务可以统一清除两类短期缓存', () => {
  assert.match(dedupeSource, /export function clearWorkspaceSelectorCaches\(\)/)
  assert.match(dedupeSource, /clearRequestCache\('agent-selector:'\)/)
  assert.match(dedupeSource, /clearRequestCache\('data-skill-selector:'\)/)
})
