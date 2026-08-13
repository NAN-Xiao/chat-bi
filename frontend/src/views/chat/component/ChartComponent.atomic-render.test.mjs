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
  /function renderAtomicChart\(retry = 0\) \{[\s\S]*?getChartInstance\(params\.type, stagingMount\)[\s\S]*?Promise\.resolve\(renderInstance\.render\(\)\)[\s\S]*?commitStagedChart\(renderInstance, stagingLayer, token\)/,
  '新图必须在隐藏层完成异步绘制后再提交为可见图表'
)
assert.match(
  component,
  /function commitStagedChart\([\s\S]*?stagingLayer\.classList\.replace\('chart-render-layer--staging', 'chart-render-layer--active'\)[\s\S]*?destroyChartInstance\(previousInstance\)[\s\S]*?previousLayer\?\.remove\(\)/,
  '提交新图时必须切换完整挂载层后再销毁旧实例，不能搬运 G2 持有的内部 DOM'
)
assert.match(
  component,
  /const emit = defineEmits<[\s\S]*?'render-ready'[\s\S]*?>\(\)/,
  '图表组件需要声明首帧提交事件'
)
assert.match(
  component,
  /function hasActiveRenderedLayer\(\) \{[\s\S]*?activeLayerRef\.value[\s\S]*?!stagingLayerRef\.value[\s\S]*?hasRenderedOutput\(activeLayerRef\.value\)/,
  '首帧通知需要以已提交且已有输出的 active layer 作为完成条件'
)
assert.match(
  component,
  /function scheduleRenderReady\(\) \{[\s\S]*?window\.requestAnimationFrame[\s\S]*?hasActiveRenderedLayer\(\)[\s\S]*?emit\('render-ready'\)/,
  '首帧通知只要已有可显示 active layer 就必须发出，不能被后续 resize 调度无限饿死'
)
assert.doesNotMatch(
  component,
  /function scheduleRenderReady\(\) \{[\s\S]*?!renderTimer[\s\S]*?emit\('render-ready'\)/,
  '首帧 ready 不能等待 renderTimer 清空，否则连续 resize/watch 会让看板完整遮罩持续显示'
)
assert.match(
  component,
  /function scheduleRenderChart\([\s\S]*?if \(!hasActiveRenderedLayer\(\)\) \{\s*cancelPendingRenderReady\(\)\s*\}/,
  '有已提交 active layer 时，新重绘请求不能取消尚未发出的首帧通知'
)
assert.doesNotMatch(
  component,
  /function scheduleRenderChart\(delay = 0, retry = 0, invalidate = false\) \{\s*cancelPendingRenderReady\(\)/,
  'scheduleRenderChart 不能无条件取消首帧 ready'
)
assert.match(
  component,
  /function commitStagedChart\([\s\S]*?showInitialLoading\.value = false[\s\S]*?if \(!rerenderAfterStaging\) \{\s*scheduleRenderReady\(\)\s*\}[\s\S]*?drainPendingRender\(\)/,
  '只有新图原子提交且没有待合并重绘时才能开始稳定首帧确认'
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
  /function renderAtomicChart\(retry = 0\) \{[\s\S]*?let nextInstance: BaseChart \| undefined[\s\S]*?try \{[\s\S]*?nextInstance = getChartInstance\(params\.type, stagingMount\)[\s\S]*?const renderInstance = nextInstance[\s\S]*?configureChart\(renderInstance\)[\s\S]*?Promise\.resolve\(renderInstance\.render\(\)\)/,
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
assert.doesNotMatch(
  component,
  /function scheduleRenderChart\(delay = 0, retry = 0\) \{\s*renderToken \+= 1/,
  '尺寸和全局重绘通知不能无条件作废正在完成的首次 staging，否则持续通知会让加载态永不结束'
)
assert.match(
  component,
  /function scheduleRenderChart\(delay = 0, retry = 0, invalidate = false\) \{[\s\S]*?if \(invalidate\) \{\s*renderToken \+= 1/,
  '调度器必须只在内容变化时作废旧 staging'
)
assert.match(
  component,
  /function scheduleRenderChart\(delay = 0, retry = 0, invalidate = false\) \{[\s\S]*?if \(invalidate && stagingLayerRef\.value && !activeLayerRef\.value\) \{[\s\S]*?rerenderAfterStaging = true[\s\S]*?pendingRenderRetry = retry[\s\S]*?return[\s\S]*?if \(invalidate\) \{\s*renderToken \+= 1/,
  '首次 staging 尚无可见图表时，内容更新必须先保住首帧并合并最新重绘，不能延长加载圆环'
)
assert.match(
  component,
  /watch\([\s\S]*?\(\) => \{\s*scheduleRenderChart\(0, 0, true\)\s*\}/,
  '数据、轴和类型变化必须作废旧 staging，不能提交过期图表'
)
assert.match(
  component,
  /function renderAtomicChart\(retry = 0\) \{[\s\S]*?if \(stagingLayerRef\.value\) \{[\s\S]*?rerenderAfterStaging = true[\s\S]*?return/,
  '已有 staging 渲染时必须把后续请求合并为一次重绘，不能并发启动并互相取消'
)
assert.match(
  component,
  /function drainPendingRender\(\) \{[\s\S]*?rerenderAfterStaging[\s\S]*?scheduleRenderChart/,
  'staging 完成或失效后必须执行合并后的最新重绘'
)
assert.doesNotMatch(
  component,
  /function renderChart\(retry = 0\) \{[\s\S]*?destroyChart\(false\)[\s\S]*?chartInstance = getChartInstance/,
  '可见容器不能先销毁再异步绘制，否则会露出空坐标轴中间帧'
)
assert.match(
  component,
  /<div\s+v-if="showInitialLoading && params\.surface !== 'dashboard'"\s+class="chart-component-loading"/,
  '看板首绘必须只由卡片完整遮罩负责，其他独立图表仍保留组件加载态'
)
assert.doesNotMatch(
  component,
  /chart-component-loading-reveal/,
  '统一生命周期后不能再依赖延迟显示圆环掩盖状态交接'
)
assert.doesNotMatch(
  component,
  /\.chart-component-loading\s*\{[^}]*visibility:\s*hidden/s,
  '独立图表的组件加载态不应再靠隐藏计时器控制可见性'
)
assert.match(
  component,
  /const stagingMount = document\.createElement\('div'\)[\s\S]*?stagingMount\.className = 'chart-render-mount'[\s\S]*?stagingLayer\.appendChild\(stagingMount\)[\s\S]*?getChartInstance\(params\.type, stagingMount\)/,
  '图表库必须挂载到独立内层，不能改写组件拥有的绝对定位渲染层并引发布局闪烁'
)
assert.doesNotMatch(
  component,
  /getChartInstance\(params\.type, stagingLayer\)/,
  '组件拥有的 staging layer 不能直接交给图表库'
)

const mountedMatch = component.match(/onMounted\(\(\) => \{([\s\S]*?)\r?\n\}\)/)
assert.ok(mountedMatch, '图表组件需要保留挂载初始化')
assert.match(mountedMatch[1], /scheduleRenderChart\(\)/, '挂载后必须立即调度首绘')
assert.doesNotMatch(
  mountedMatch[1],
  /scheduleRenderChart\(160\)/,
  '不能用第二次延迟调度取消立即首绘并人为延长首次加载'
)

console.log('ChartComponent atomic render tests passed')
