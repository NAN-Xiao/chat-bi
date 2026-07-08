import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const componentPath = resolve(
  __dirname,
  '../src/views/dashboard/canvas/ComponentBar.vue'
)
const source = readFileSync(componentPath, 'utf8')

function assertIncludes(pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(message)
  }
}

assertIncludes(
  /const\s+curDropdown\s*=\s*ref/,
  'ComponentBar 应持有 el-dropdown 引用，以便菜单动作后主动关闭下拉层'
)

assertIncludes(
  /function\s+closeComponentDropdown|const\s+closeComponentDropdown\s*=/,
  'ComponentBar 应提供关闭下拉层的统一方法'
)

assertIncludes(
  /const\s+doEditSql[\s\S]*?closeComponentDropdown\(\)[\s\S]*?emits\('editSql'\)/,
  '点击“编辑 SQL”应先关闭下拉层，再发出 editSql 事件'
)

console.log('ComponentBar dropdown close regression test passed')
