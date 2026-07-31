import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const source = readFileSync(fileURLToPath(new URL('./Menu.vue', import.meta.url)), 'utf8')
const verticalMenuStart = source.indexOf('.ed-menu-vertical {')
const horizontalMenuStart = source.indexOf('.shuzhi-layout-menu-horizontal {')

assert.ok(verticalMenuStart >= 0, '应存在纵向菜单样式作用域')
assert.ok(horizontalMenuStart > verticalMenuStart, '横向菜单样式应位于纵向菜单样式之后')

const verticalMenuStyles = source.slice(verticalMenuStart, horizontalMenuStart)

assert.match(
  verticalMenuStyles,
  /\.ed-sub-menu \.ed-sub-menu__title\s*\{[\s\S]*?position:\s*relative\s*!important;/,
  '纵向侧栏子菜单标题应作为箭头的定位参照'
)

assert.match(
  verticalMenuStyles,
  /\.ed-sub-menu__icon-arrow\s*\{[\s\S]*?position:\s*absolute\s*!important;[\s\S]*?width:\s*12px\s*!important;[\s\S]*?right:\s*8px\s*!important;[\s\S]*?margin-right:\s*0\s*!important;[\s\S]*?margin-top:\s*-8px\s*!important;/,
  '纵向侧栏子菜单箭头应使用固定宽度和绝对定位，并精确停靠在菜单项右侧和垂直中心'
)
