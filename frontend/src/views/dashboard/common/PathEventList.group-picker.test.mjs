import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const source = readFileSync(new URL('./PathEventList.vue', import.meta.url), 'utf8')

assert.match(source, /width="440"/, '路径事件下拉需要为双栏浏览提供足够宽度')
assert.match(source, /class="path-event-picker-search"/, '事件选择器需要保留搜索入口')
assert.match(source, /placeholder="请输入搜索"/, '搜索占位文案需要与事件选择器样式一致')
assert.match(source, /class="path-event-picker-select-all"/, '事件选择器需要提供全选入口')
assert.match(source, /someFilteredEventsSelected/, '全选入口需要展示部分选中的中间态')
assert.match(source, /function toggleAllFilteredEvents()/, '全选入口需要更新当前搜索结果中的事件')
assert.match(source, /selectingAllWouldExceedLimit/, '完整全选超过路径事件上限时需要禁用全选')
assert.match(
  source,
  /filteredEventOptions\.length === 0 \|\| selectingAllWouldExceedLimit/,
  '全选按钮不能静默截断超过上限的事件'
)

assert.match(source, /const eventGroups = computed/, '事件选项需要按目录分组')
assert.match(
  source,
  /option\.eventCategory \|\| option\.category \|\| '默认分组'/,
  '事件分组应优先采用事件目录分类'
)
assert.match(source, /class="path-event-picker-columns"/, '事件选择器应使用左右双栏结构')
assert.match(source, /class="path-event-category-list"/, '左栏需要展示事件分组')
assert.match(source, /v-for="group in eventGroups"/, '左栏需要渲染全部可见事件分组')
assert.match(source, /class="path-event-picker-group-title"/, '右栏需要标明当前事件分组')
assert.match(source, /v-for="option in activeEventItems"/, '右栏只渲染当前分组的事件')
assert.match(source, /@click="toggleEvent\(option\.value\)"/, '右栏事件需要支持复选切换')
assert.match(source, /selectedEventCount >= maxEvents/, '单项选择仍需遵守路径事件数量上限')

assert.match(source, /class="path-split-list"/, '分组事件选择器不能破坏路径拆分项')
assert.match(source, /function updateSplitProperty/, '路径拆分属性更新能力需要保留')
assert.doesNotMatch(source, /\bmultiple\b/, '路径事件选择不能退化为普通下拉多选')

console.log('path event grouped picker tests passed')
