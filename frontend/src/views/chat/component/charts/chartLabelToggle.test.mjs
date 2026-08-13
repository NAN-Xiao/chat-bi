import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const chartFiles = [
  'Line.ts',
  'Area.ts',
  'Column.ts',
  'Bar.ts',
  'Scatter.ts',
  'Heatmap.ts',
  'Funnel.ts',
  'RadialPartitionChart.ts',
  'Treemap.ts',
]

for (const file of chartFiles) {
  const source = readFileSync(`src/views/chat/component/charts/${file}`, 'utf8')
  assert.match(
    source,
    /(?:labels:\s*|areaLabels\s*=\s*)this\.showLabel/,
    `${file} 必须由显式标签开关控制标签`
  )
  assert.doesNotMatch(
    source,
    /this\.showLabel\s*&&\s*responsive\./,
    `${file} 不能用卡片尺寸策略覆盖用户的显式标签选择`
  )
}

const sankeySource = readFileSync('src/views/chat/component/charts/Sankey.ts', 'utf8')
assert.match(
  sankeySource,
  /labelText:\s*this\.showLabel\s*\?.*:\s*\(\)\s*=>\s*''/,
  'Sankey 的默认节点文字也必须由显式标签开关控制'
)

const responsiveSource = readFileSync('src/views/chat/component/charts/g2Responsive.ts', 'utf8')
assert.doesNotMatch(
  responsiveSource,
  /showPointLabels/,
  '响应式样式只能调整布局，不能决定用户显式控制的标签显隐'
)

const wrapperSource = readFileSync(
  'src/views/dashboard/preview/SQComponentWrapper.vue',
  'utf8'
)
assert.match(
  wrapperSource,
  /showLabel:\s*chartShowLabel\.value/,
  '看板卡片必须把标签开关状态传给图表视图'
)
assert.match(
  wrapperSource,
  /@click="chartShowLabel = !chartShowLabel"/,
  '看板卡片标签按钮必须同时支持显示和取消显示'
)

const chartComponentSource = readFileSync(
  'src/views/chat/component/ChartComponent.vue',
  'utf8'
)
assert.match(
  chartComponentSource,
  /showLabel:\s*params\.showLabel/,
  '共享图表组件必须监听标签开关并触发重绘'
)

console.log('Chart label toggle tests passed')
