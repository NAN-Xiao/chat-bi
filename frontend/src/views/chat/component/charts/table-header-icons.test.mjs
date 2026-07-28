import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const tableSource = readFileSync('src/views/chat/component/charts/Table.ts', 'utf8')
const headerActionsSource = readFileSync(
  'src/views/chat/component/charts/tableHeaderActions.ts',
  'utf8'
)

assert.match(
  tableSource,
  /import \{ CaretBottom, CaretTop, DCaret, Filter \} from '@element-plus\/icons-vue'/,
  '表头操作图标必须复用项目已有的 Element Plus 图标库'
)
assert.match(
  tableSource,
  /import \{ h, render, type Component \} from 'vue'/,
  '表头图标必须通过 Vue 渲染器适配为 S2 SVG 字符串'
)
assert.match(
  tableSource,
  /const tableFilterIconSvg = renderTableIconSvg\(Filter\)/,
  '筛选状态必须使用填充漏斗图标'
)
assert.match(
  tableSource,
  /const tableSortNoneIconSvg = renderTableIconSvg\(DCaret\)/,
  '未排序状态必须使用上下双三角形图标'
)
assert.match(
  tableSource,
  /const tableSortAscIconSvg = renderTableIconSvg\(CaretTop\)/,
  '升序状态必须使用图标库向上填充三角形'
)
assert.match(
  tableSource,
  /const tableSortDescIconSvg = renderTableIconSvg\(CaretBottom\)/,
  '降序状态必须使用图标库向下填充三角形'
)
assert.doesNotMatch(
  tableSource,
  /const TABLE_(?:FILTER|SORT_(?:NONE|ASC|DESC))_ICON_SVG\s*=\s*`/,
  'Table.ts 不应继续手写表头 SVG Path'
)
assert.match(
  tableSource,
  /\{ name: TABLE_FILTER_ICON, src: tableFilterIconSvg \}/,
  'S2 必须注册项目筛选 SVG'
)
assert.match(
  tableSource,
  /\{ name: TABLE_SORT_NONE_ICON, src: tableSortNoneIconSvg \}/,
  'S2 必须注册上下双三角形 SVG'
)
assert.match(
  tableSource,
  /\{ name: TABLE_SORT_ASC_ICON, src: tableSortAscIconSvg \}/,
  'S2 必须注册项目升序 SVG'
)
assert.match(
  tableSource,
  /\{ name: TABLE_SORT_DESC_ICON, src: tableSortDescIconSvg \}/,
  'S2 必须注册项目降序 SVG'
)
assert.doesNotMatch(
  tableSource,
  /@\/assets\/svg\/(?:icon-filter_outlined|dv-sort-(?:asc|desc))\.svg\?raw/,
  '表头图标不应再依赖旧的独立 SVG 资源'
)
assert.match(
  headerActionsSource,
  /TABLE_HEADER_ACTION_ICON_THEME\s*=\s*\{[\s\S]*?size:\s*16,/,
  '表头操作图标必须使用适合 32px 表头的 16px 尺寸'
)
assert.match(
  headerActionsSource,
  /margin:\s*\{\s*left:\s*6,\s*right:\s*2,\s*\}/,
  '列名与图标之间必须保留 6px 间距，图标组内部保持紧凑'
)

console.log('Table header icon source tests passed')
