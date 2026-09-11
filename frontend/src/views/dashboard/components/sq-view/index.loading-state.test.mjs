import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { computed, ref } from 'vue'

const source = readFileSync(new URL('./index.vue', import.meta.url), 'utf8')

function componentComputed(name, dependencies) {
  const declaration = source.match(new RegExp(`const ${name} = computed\\(([\\s\\S]*?)\\r?\\n\\)`))
  assert.ok(declaration, `${name} must be defined by the chart component`)
  return new Function('computed', ...Object.keys(dependencies), `return computed(${declaration[1]})`)(
    computed,
    ...Object.values(dependencies)
  )
}

function loadingState() {
  const state = {
    chartLoading: ref(false),
    chartResultPending: ref(false),
    blockingRefreshLoading: ref(false),
    hasRenderedChartData: ref(false),
    showChartContent: ref(false),
    chartFrameReady: ref(false),
  }
  state.chartDataLoading = componentComputed('chartDataLoading', state)
  state.showFullChartLoading = componentComputed('showFullChartLoading', state)
  return state
}

for (const hasData of [false, true]) {
  for (const trigger of ['chartLoading', 'chartResultPending', 'blockingRefreshLoading']) {
    test(`${trigger} stays centered ${hasData ? 'with cached rows' : 'without rows'}`, () => {
      const state = loadingState()
      state.hasRenderedChartData.value = hasData
      state.showChartContent.value = hasData
      state.chartFrameReady.value = hasData
      assert.equal(state.showFullChartLoading.value, false)

      state[trigger].value = true
      assert.equal(state.showFullChartLoading.value, true)
      assert.equal(state.showChartContent.value, hasData, 'Refreshing must retain existing content')

      state[trigger].value = false
      assert.equal(state.showFullChartLoading.value, false, 'Completed requests must stop loading')
    })
  }
}

test('data arrival keeps the same loading state until the chart commits its first frame', () => {
  const state = loadingState()
  state.chartLoading.value = true
  assert.equal(state.showFullChartLoading.value, true)

  state.hasRenderedChartData.value = true
  state.showChartContent.value = true
  state.chartLoading.value = false
  assert.equal(state.showFullChartLoading.value, true)

  state.chartFrameReady.value = true
  assert.equal(state.showFullChartLoading.value, false)
})
