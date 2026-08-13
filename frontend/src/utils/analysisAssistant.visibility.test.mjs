import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')

test('comprehensive analysis assistant visibility is controlled by one disabled flag', () => {
  const featureSource = read('./analysisAssistant.ts')
  const layoutSource = read('../components/layout/LayoutDsl.vue')

  assert.match(featureSource, /ANALYSIS_ASSISTANT_ENABLED\s*=\s*false/)
  assert.match(layoutSource, /ANALYSIS_ASSISTANT_ENABLED && !showSysmenu/)
})

test('frontend-only hiding keeps the analysis assistant route and backend API untouched', () => {
  const dynamicRouterSource = read('../router/dynamic.ts')
  const routerWatchSource = read('../router/watch.ts')
  const layoutSource = read('../components/layout/LayoutDsl.vue')

  assert.match(dynamicRouterSource, /path: '\/as'/)
  assert.doesNotMatch(routerWatchSource, /ANALYSIS_ASSISTANT_ENABLED/)
  assert.match(layoutSource, /AnalysisAssistantDock/)
})
