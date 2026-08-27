import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const currentDir = dirname(fileURLToPath(import.meta.url))
const componentPath = join(currentDir, 'BuilderFieldPicker.vue')
const optionsPath = join(currentDir, 'builderFieldPickerOptions.ts')
const source = readFileSync(componentPath, 'utf8')
const optionsSource = readFileSync(optionsPath, 'utf8')

const arrowStyleMatch = source.match(/\.builder-field-picker-arrow\s*\{([\s\S]*?)\n\}/)
const fieldTypeLabelMatch = source.match(/function fieldTypeLabel\(option: FieldOption\) \{([\s\S]*?)\n\}/)
const fieldTypeStyleMatch = source.match(/\.field-type\s*\{([\s\S]*?)\n\}/)
const selectedOptionMatch = source.match(/const selectedOption = computed\(\(\) =>[\s\S]*?\n\)/)
const tableTabsMatch = source.match(/const tableTabs = computed\(\(\) => \{([\s\S]*?)\n\}\)/)
const hoverJsonMetaMatch = source.match(/<div v-if="item\.isJsonSubfield" class="hover-json-meta">([\s\S]*?)<\/div>/)

assert.ok(arrowStyleMatch, '字段选择器箭头需要有独立样式')
assert.match(
  arrowStyleMatch[1],
  /display:\s*inline-flex/,
  '字段选择器箭头应使用 flex 布局，避免字符基线导致不居中'
)
assert.match(
  arrowStyleMatch[1],
  /align-items:\s*center/,
  '字段选择器箭头需要垂直居中'
)
assert.match(
  arrowStyleMatch[1],
  /justify-content:\s*center/,
  '字段选择器箭头需要水平居中'
)
assert.match(
  source,
  /class="builder-field-picker-arrow"[^>]*>[\s\S]*?<el-icon><ArrowDown\s*\/><\/el-icon>/,
  '字段选择器应使用标准下拉图标，避免字符字形基线造成视觉偏移'
)
assert.doesNotMatch(source, /builder-field-picker-arrow">⌄/, '字段选择器不应继续使用带基线偏移的字符箭头')

assert.match(
  optionsSource,
  /tableReferenceLabel\?: string/,
  '字段选择器 option 类型需要支持事件明细表 label 引用'
)
assert.ok(tableTabsMatch, '字段选择器需要保留表 tab 构建逻辑')
assert.match(
  tableTabsMatch[1],
  /optionTableReferenceLabel/,
  '字段选择器表 tab 需要展示事件参数所属事件明细表 label 引用'
)
assert.ok(hoverJsonMetaMatch, 'JSON 字段 hover 需要保留来源字段和 JSON 路径说明')
assert.match(
  hoverJsonMetaMatch[1],
  /fieldReferenceLabel\(item\)/,
  'JSON 字段 hover 需要展示事件明细表 label 引用'
)
assert.ok(fieldTypeLabelMatch, '字段选择器需要保留字段类型展示函数')
assert.match(
  fieldTypeLabelMatch[1],
  /fieldReferenceLabel\(option\)/,
  'JSON 字段行内类型需要直接展示事件明细表 label 引用，不能只显示 JSON字段'
)
assert.ok(selectedOptionMatch, '字段选择器需要保留已选项解析逻辑')
assert.match(
  selectedOptionMatch[0],
  /item\.field === props\.modelValue/,
  '字段选择器需要兼容 prod 这类旧字段值，避免已选计算字段只显示裸字段名'
)
assert.ok(fieldTypeStyleMatch, '字段类型标签需要保留样式')
assert.match(
  fieldTypeStyleMatch[1],
  /max-width:/,
  '字段类型标签展示事件明细引用后需要限制宽度，避免挤压字段名'
)
assert.match(
  fieldTypeStyleMatch[1],
  /text-overflow:\s*ellipsis/,
  '字段类型标签过长时应省略显示'
)
