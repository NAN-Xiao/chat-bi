import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const component = readFileSync('src/views/chat/component/ChartComponent.vue', 'utf8')

assert.match(
  component,
  /const activeLayerRef = ref<HTMLElement>\(\)/,
  '非表格图表需要独立的当前可见层'
)
assert.match(
  component,
  /const stagingLayerRef = ref<HTMLElement>\(\)/,
  '非表格图表需要独立的后台绘制层'
)
assert.match(
  component,
  /function renderAtomicChart\(retry = 0\) \{[\s\S]*?getChartInstance\(params\.type, stagingLayer\)[\s\S]*?Promise\.resolve\(renderInstance\.render\(\)\)[\s\S]*?commitStagedChart\(renderInstance, stagingLayer, token\)/,
  '新图必须在隐藏层完成异步绘制后再提交为可见图表'
)
assert.match(
  component,
  /function commitStagedChart\([\s\S]*?stagingLayer\.classList\.replace\('chart-render-layer--staging', 'chart-render-layer--active'\)[\s\S]*?destroyChartInstance\(previousInstance\)[\s\S]*?previousLayer\?\.remove\(\)/,
  '提交新图时必须切换完整挂载层后再销毁旧实例，不能搬运 G2 持有的内部 DOM'
)
assert.match(
  component,
  /if \(token !== renderToken\) \{[\s\S]*?cleanupStagedChart\(nextInstance, stagingLayer\)[\s\S]*?return/,
  '过期绘制只能清理隐藏层，不能清空当前图表'
)
assert.match(
  component,
  /function handleAtomicRenderError\([\s\S]*?cleanupStagedChart\(nextInstance, stagingLayer\)/,
  '绘制失败只能清理隐藏层，必须保留当前图表'
)
assert.match(
  component,
  /const destroyedChartInstances = new WeakSet<BaseChart>\(\)[\s\S]*?function destroyChartInstance\(instance: BaseChart \| undefined\) \{[\s\S]*?destroyedChartInstances\.has\(instance\)[\s\S]*?destroyedChartInstances\.add\(instance\)[\s\S]*?instance\.destroy\(\)/,
  '过期、失败和卸载回调可能重复清理同一实例，销毁操作必须幂等'
)
assert.match(
  component,
  /function renderAtomicChart\(retry = 0\) \{[\s\S]*?let nextInstance: BaseChart \| undefined[\s\S]*?try \{[\s\S]*?nextInstance = getChartInstance\(params\.type, stagingLayer\)[\s\S]*?const renderInstance = nextInstance[\s\S]*?configureChart\(renderInstance\)[\s\S]*?Promise\.resolve\(renderInstance\.render\(\)\)/,
  '实例构造、初始化和 render 都必须处于同一异常清理边界内'
)
assert.doesNotMatch(
  component,
  /function renderTableChart\(/,
  '异步 S2 表格不能走先清空旧图再 render 的非原子分支'
)
assert.match(
  component,
  /function renderChart\(retry = 0\) \{[\s\S]*?renderAtomicChart\(retry\)/,
  '所有图表类型都应通过完整层交换提交，table 只在 resize 时保留原地调整'
)
assert.match(
  component,
  /function scheduleRenderChart\(delay = 0, retry = 0\) \{[\s\S]*?renderToken \+= 1[\s\S]*?window\.setTimeout/,
  '新渲染一旦排队就必须让旧 staging token 失效，避免旧数据抢先提交'
)
assert.doesNotMatch(
  component,
  /function renderChart\(retry = 0\) \{[\s\S]*?destroyChart\(false\)[\s\S]*?chartInstance = getChartInstance/,
  '可见容器不能先销毁再异步绘制，否则会露出空坐标轴中间帧'
)
assert.match(
  component,
  /<div v-if="showInitialLoading" class="chart-component-loading"/,
  '首次没有旧图时应显示组件加载态，不能暴露隐藏层的绘制中间帧'
)

console.log('ChartComponent atomic render tests passed')
