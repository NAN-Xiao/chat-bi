<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, Search } from '@element-plus/icons-vue'
import {
  fieldOptionDisplayName,
  isEventPublicPropertyOption,
  isNumericFieldOption,
  isSelectableFieldOption,
  isTimeFieldOption,
  isTrackingEventPropertyOption,
} from './builderFieldPickerOptions'
import type { FieldOption } from './builderFieldPickerOptions'

type PickerMode = 'field' | 'property' | 'metric' | 'time' | 'tracking-event' | 'filter-property'
type FilterPropertyTab = 'all' | 'event' | 'user'

defineOptions({ name: 'BuilderFieldPicker' })

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: FieldOption[]
    mode?: PickerMode
    placeholder?: string
    disabled?: boolean
    loading?: boolean
    filterPropertyTabs?: FilterPropertyTab[]
  }>(),
  {
    mode: 'property',
    placeholder: '字段',
    disabled: false,
    loading: false,
    filterPropertyTabs: () => [],
  }
)

const emits = defineEmits<{
  'update:modelValue': [value: string]
}>()

const visible = ref(false)
const keyword = ref('')
const activeTab = ref('all')
const activeEventCategory = ref('')
const TABLE_TAB_PREFIX = 'table:'

const selectedOption = computed(() =>
  props.options.find((item) => item.value === props.modelValue)
  || props.options.find((item) => item.field === props.modelValue)
)

const selectedLabel = computed(() => fieldOptionDisplayName(selectedOption.value, props.modelValue))

const selectableOptions = computed(() => props.options.filter(isSelectableFieldOption))
const isTrackingEventMode = computed(() => props.mode === 'tracking-event')
const isFilterPropertyMode = computed(() => props.mode === 'filter-property')

function shortTableLabel(value = '') {
  const firstLine = String(value || '').split(/\r?\n/).find((line) => line.trim()) || ''
  return firstLine
    .split(/[。；;，,]/)[0]
    .trim()
}

function tableTabLabel(tableName: string, label = '', referenceLabel = '') {
  const shortLabel = shortTableLabel(label)
  const shortReferenceLabel = shortTableLabel(referenceLabel)
  const baseLabel = !shortLabel || shortLabel.toLowerCase() === tableName.toLowerCase()
    ? tableName
    : `${shortLabel}(${tableName})`
  if (!shortReferenceLabel || shortReferenceLabel === shortLabel || shortReferenceLabel.toLowerCase() === tableName.toLowerCase()) {
    return baseLabel
  }
  return `${baseLabel} · ${shortReferenceLabel}`
}

function optionTableReferenceLabel(option: FieldOption) {
  const label = shortTableLabel(option.tableReferenceLabel || '')
  if (!label || label.toLowerCase() === String(option.table || '').toLowerCase()) {
    return ''
  }
  return label
}

function fieldReferenceLabel(option: FieldOption) {
  const label = optionTableReferenceLabel(option)
  if (!label) {
    return ''
  }
  const tableName = option.eventTable || option.table
  return tableName ? `${label}(${tableName})` : label
}

const tableTabs = computed(() => {
  const tableLabels = new Map<string, { label: string; referenceLabel: string }>()
  selectableOptions.value.forEach((item) => {
    if (item.table) {
      const currentLabel = tableLabels.get(item.table)
      const nextLabel = shortTableLabel(item.tableLabel || item.tableComment)
      const nextReferenceLabel = optionTableReferenceLabel(item)
      if (!currentLabel || nextLabel || nextReferenceLabel) {
        tableLabels.set(item.table, {
          label: nextLabel || currentLabel?.label || '',
          referenceLabel: nextReferenceLabel || currentLabel?.referenceLabel || '',
        })
      }
    }
  })
  return Array.from(tableLabels.entries())
    .sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true, sensitivity: 'base' }))
    .map(([tableName, meta]) => ({
      label: tableTabLabel(tableName, meta.label, meta.referenceLabel),
      value: `${TABLE_TAB_PREFIX}${tableName}`,
    }))
})
const filterPropertyTabOptions: Array<{ label: string; value: FilterPropertyTab }> = [
  { label: '全部', value: 'all' },
  { label: '事件属性', value: 'event' },
  { label: '公共属性', value: 'user' },
]
const filterPropertyGroupOrder: FilterPropertyTab[] = ['event', 'user']

const tabOptions = computed(() => {
  if (isFilterPropertyMode.value) {
    return filterPropertyTabOptions.filter((item) => props.filterPropertyTabs.includes(item.value))
  }
  return [
    { label: '全部', value: 'all' },
    ...tableTabs.value,
  ]
})

watch(
  () => [props.mode, tabOptions.value.map((item) => item.value).join('|')],
  () => {
    if (!tabOptions.value.some((item) => item.value === activeTab.value)) {
      activeTab.value = tabOptions.value[0]?.value || 'all'
    }
  },
  { immediate: true }
)

function optionCategory(item: FieldOption) {
  return item.category || 'other'
}

function isIdentifierField(item: FieldOption) {
  const text = `${item.field} ${item.value} ${item.type || ''}`.toLowerCase()
  return /(^|[._\s-])(id|uid|uuid|user_id|userid|player_id|playerid|account_id|accountid)([._\s-]|$)/.test(text)
}

function matchesTab(item: FieldOption, tab: string) {
  if (isFilterPropertyMode.value && tab === 'all') {
    return isTrackingEventPropertyOption(item) || isEventPublicPropertyOption(item)
  }
  if (isFilterPropertyMode.value && tab === 'event') {
    return isTrackingEventPropertyOption(item)
  }
  if (isFilterPropertyMode.value && tab === 'user') {
    return isEventPublicPropertyOption(item)
  }
  if (tab === 'all') {
    return true
  }
  if (tab.startsWith(TABLE_TAB_PREFIX)) {
    return item.table === tab.slice(TABLE_TAB_PREFIX.length)
  }
  return optionCategory(item) === tab
}

function matchesKeyword(item: FieldOption, q: string) {
  if (!q) {
    return true
  }
  const text = [
    item.field,
    item.displayName,
    item.label,
    item.value,
    item.comment,
    item.table,
    item.type,
  ].join(' ').toLowerCase()
  return text.includes(q)
}

const groupedOptions = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  const tab = activeTab.value
  const keywordRows = selectableOptions.value.filter((item) => matchesKeyword(item, q))
  const tabRows = keywordRows.filter((item) => matchesTab(item, tab))
  const rows = isFilterPropertyMode.value
    ? tabRows
    : tabRows.length > 0 || tab === 'all' || tab.startsWith(TABLE_TAB_PREFIX)
      ? tabRows
      : keywordRows
  const sortItems = (items: FieldOption[]) => items.sort((a, b) => {
      const aSource = a.sourceField || a.field
      const bSource = b.sourceField || b.field
      const sourceCompare = aSource.localeCompare(bSource, undefined, { numeric: true, sensitivity: 'base' })
      if (sourceCompare !== 0) return sourceCompare
      if (a.isJsonSubfield !== b.isJsonSubfield) return a.isJsonSubfield ? 1 : -1
      return a.field.localeCompare(b.field, undefined, { numeric: true, sensitivity: 'base' })
    })
  if (isFilterPropertyMode.value) {
    const groups: Array<{ name: string; items: FieldOption[] }> = []
    const groupTabs = tab === 'all' ? filterPropertyGroupOrder : [tab as FilterPropertyTab]
    groupTabs.forEach((groupTab) => {
      const items = rows.filter((item) => matchesTab(item, groupTab))
      if (!items.length) return
      groups.push({
        name: filterPropertyTabOptions.find((item) => item.value === groupTab)?.label || '筛选属性',
        items: sortItems(items),
      })
    })
    return groups
  }
  const groups = new Map<string, FieldOption[]>()
  rows.forEach((item) => {
    const key = tableTabLabel(item.table || '字段', item.tableLabel || item.tableComment, optionTableReferenceLabel(item))
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)?.push(item)
  })
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items: sortItems(items) }))
})

const propertyEmptyText = computed(() => (
  activeTab.value === 'all' ? '暂无筛选属性' : activeTab.value === 'event' ? '暂无事件属性' : '暂无公共属性'
))

const eventRows = computed(() => {
  const q = keyword.value.trim().toLowerCase()
  return selectableOptions.value
    .filter((item) => item.kind === 'tracking-event')
    .filter((item) => matchesKeyword(item, q))
})

const eventGroups = computed(() => {
  const groups = new Map<string, FieldOption[]>()
  eventRows.value.forEach((item) => {
    const key = item.eventCategory || item.category || '默认分组'
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)?.push(item)
  })
  return Array.from(groups.entries()).map(([name, items]) => ({
    name,
    items: items.sort((a, b) => fieldOptionDisplayName(a).localeCompare(fieldOptionDisplayName(b), undefined, { numeric: true, sensitivity: 'base' })),
  }))
})

const activeEventItems = computed(() => {
  const firstGroup = eventGroups.value[0]
  const currentGroup = eventGroups.value.find((group) => group.name === activeEventCategory.value) || firstGroup
  return currentGroup?.items || []
})

function fieldTypeLabel(option: FieldOption) {
  if (option.kind === 'tracking-event') return '事件'
  if (option.isJsonSubfield) {
    const referenceLabel = fieldReferenceLabel(option)
    return referenceLabel ? `${referenceLabel} · JSON字段` : 'JSON字段'
  }
  if (option.type) return option.type
  if (isIdentifierField(option)) return '标识'
  if (isTimeFieldOption(option)) return '时间'
  if (isNumericFieldOption(option)) return '数值'
  if (option.category === 'text') return '文本'
  return '字段'
}

function selectField(option: FieldOption) {
  emits('update:modelValue', option.value)
  visible.value = false
}

watch(
  eventGroups,
  (groups) => {
    if (!groups.length) {
      activeEventCategory.value = ''
      return
    }
    if (!groups.some((group) => group.name === activeEventCategory.value)) {
      activeEventCategory.value = groups[0].name
    }
  },
  { immediate: true }
)
</script>

<template>
  <el-popover
    v-model:visible="visible"
    width="460"
    trigger="manual"
    placement="bottom-start"
    popper-class="builder-field-picker-popper"
    :popper-style="{ zIndex: 5001 }"
    :disabled="disabled"
  >
    <template #reference>
      <button
        type="button"
        class="builder-field-picker-trigger"
        :class="{ 'is-empty': !selectedLabel }"
        :disabled="disabled"
        @click.stop="visible = !visible"
      >
        <span>{{ selectedLabel || placeholder }}</span>
        <span class="builder-field-picker-arrow" aria-hidden="true">
          <el-icon><ArrowDown /></el-icon>
        </span>
      </button>
    </template>

    <div class="builder-field-picker">
      <div class="builder-field-picker-search">
        <el-icon><Search /></el-icon>
        <input v-model="keyword" placeholder="请输入搜索" />
      </div>
      <template v-if="isTrackingEventMode">
        <div class="builder-field-picker-tabs builder-field-picker-tabs-static">
          <button type="button" class="active">事件</button>
        </div>
        <div v-if="loading" class="builder-field-picker-empty">加载中...</div>
        <div v-else-if="eventGroups.length === 0" class="builder-field-picker-empty">暂无事件</div>
        <div v-else class="builder-event-picker-columns">
          <div class="builder-event-category-list">
            <button
              v-for="group in eventGroups"
              :key="group.name"
              type="button"
              :class="{ active: activeEventCategory === group.name }"
              @click="activeEventCategory = group.name"
            >
              {{ group.name }}
            </button>
          </div>
          <div class="builder-event-option-list">
            <el-popover
              v-for="item in activeEventItems"
              :key="item.value"
              trigger="hover"
              placement="right"
              :show-after="120"
              :hide-after="0"
              width="260"
              popper-class="builder-field-hover-popper"
              :popper-style="{ zIndex: 5002 }"
            >
              <template #reference>
                <button
                  type="button"
                  class="builder-event-option"
                  :class="{ active: item.value === modelValue }"
                  @click="selectField(item)"
                >
                  <span class="event-title">{{ fieldOptionDisplayName(item) }}</span>
                  <span class="event-code">{{ item.eventName }}</span>
                </button>
              </template>
              <div class="builder-field-hover-card">
                <div class="hover-title">{{ fieldOptionDisplayName(item) }}</div>
                <div class="hover-subtitle">{{ item.eventName }}</div>
                <div class="hover-comment">{{ item.eventDescription || item.comment || '暂无备注' }}</div>
                <div class="hover-footer">
                  <span>{{ item.eventCategory || item.category || '默认分组' }}</span>
                  <span>{{ item.collectSide || '事件' }}</span>
                </div>
              </div>
            </el-popover>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="builder-field-picker-tabs">
        <button
          v-for="tab in tabOptions"
          :key="tab.value"
          type="button"
          :class="{ active: activeTab === tab.value }"
          @click="activeTab = tab.value"
        >
          {{ tab.label }}
        </button>
        </div>
        <div v-if="loading" class="builder-field-picker-empty">加载中...</div>
        <div v-else-if="groupedOptions.length === 0" class="builder-field-picker-empty">
          {{ isFilterPropertyMode ? propertyEmptyText : '暂无数据' }}
        </div>
        <div v-else class="builder-field-picker-body">
          <div class="builder-field-picker-list">
            <template v-for="group in groupedOptions" :key="group.name">
              <div class="builder-field-picker-group">{{ group.name }}</div>
              <div class="builder-field-picker-options">
                <el-popover
                  v-for="item in group.items"
                  :key="item.value"
                  trigger="hover"
                  placement="right"
                  :show-after="120"
                  :hide-after="0"
                  width="260"
                  popper-class="builder-field-hover-popper"
                  :popper-style="{ zIndex: 5002 }"
                >
                  <template #reference>
                    <button
                      type="button"
                      class="builder-field-picker-option"
                      :class="{ active: item.value === modelValue, 'is-json-subfield': item.isJsonSubfield }"
                      @click="selectField(item)"
                    >
                      <span class="field-name">{{ fieldOptionDisplayName(item) }}</span>
                      <span class="field-type">{{ fieldTypeLabel(item) }}</span>
                    </button>
                  </template>
                  <div class="builder-field-hover-card">
                    <div class="hover-title">{{ fieldOptionDisplayName(item) }}</div>
                    <div class="hover-subtitle">{{ item.value }}</div>
                    <div v-if="item.isJsonSubfield" class="hover-json-meta">
                      <template v-if="fieldReferenceLabel(item)">事件明细：{{ fieldReferenceLabel(item) }} · </template>
                      {{ item.sourceField }} · {{ item.jsonPath }}
                    </div>
                    <div v-if="item.expression" class="hover-expression">{{ item.expression }}</div>
                    <div class="hover-comment">{{ item.comment || '暂无备注' }}</div>
                    <div class="hover-footer">
                      <span>{{ item.table || '当前结果' }}</span>
                      <span>{{ fieldTypeLabel(item) }}</span>
                    </div>
                  </div>
                </el-popover>
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>
  </el-popover>
</template>

<style scoped lang="less">
.builder-field-picker-trigger {
  display: inline-flex;
  width: auto;
  max-width: 100%;
  min-height: 26px;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: #f3f5fa;
  color: #1f2633;
  cursor: pointer;
  font-size: 12px;
  line-height: 24px;
  vertical-align: middle;
}

.builder-field-picker-trigger span:first-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.builder-field-picker-trigger.is-empty {
  color: #8b93a3;
}

.builder-field-picker-trigger:hover {
  background: #eceff6;
}

.builder-field-picker-arrow {
  display: inline-flex;
  width: 16px;
  height: 16px;
  align-items: center;
  justify-content: center;
  flex: 0 0 16px;
  color: #5f687a;
  font-size: 12px;
  line-height: 1;
}

.builder-field-picker {
  min-height: 248px;
  color: #1f2633;
  font-size: 12px;
}

.builder-field-picker-search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 9px;
  border-bottom: 1px solid #edf0f5;
  color: #8b93a3;
}

.builder-field-picker-search input {
  width: 100%;
  border: 0;
  outline: 0;
  color: #1f2633;
  font-size: 12px;
}

.builder-field-picker-tabs {
  display: flex;
  gap: 12px;
  max-width: 100%;
  overflow-x: auto;
  padding: 8px 9px 0;
  border-bottom: 1px solid #edf0f5;
}

.builder-field-picker-tabs::-webkit-scrollbar {
  height: 4px;
}

.builder-field-picker-tabs::-webkit-scrollbar-thumb {
  border-radius: 8px;
  background: #d2d8e4;
}

.builder-field-picker-tabs button {
  flex: 0 0 auto;
  max-width: 180px;
  padding: 0 0 7px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: #5f687a;
  cursor: pointer;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.builder-field-picker-tabs button.active {
  border-color: #315cff;
  color: #1f2633;
  font-weight: 600;
}

.builder-field-picker-tabs-static {
  gap: 18px;
}

.builder-event-picker-columns {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  min-height: 274px;
}

.builder-event-category-list {
  max-height: 274px;
  overflow-y: auto;
  padding: 8px 6px;
  border-right: 1px solid #edf0f5;
}

.builder-event-category-list button {
  display: block;
  width: 100%;
  height: 28px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #374151;
  cursor: pointer;
  font-size: 12px;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.builder-event-category-list button:hover,
.builder-event-category-list button.active {
  background: #eef1f7;
  color: #315cff;
  font-weight: 600;
}

.builder-event-option-list {
  max-height: 274px;
  overflow-y: auto;
  padding: 8px;
}

.builder-event-option {
  display: flex;
  width: 100%;
  min-height: 34px;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 2px;
  padding: 5px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #1f2633;
  cursor: pointer;
  text-align: left;
}

.builder-event-option:hover,
.builder-event-option.active {
  background: #eef1f7;
}

.event-title,
.event-code {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.event-title {
  font-size: 12px;
  font-weight: 600;
}

.event-code {
  color: #8b93a3;
  font-size: 11px;
}

.builder-field-picker-body {
  min-height: 216px;
}

.builder-field-picker-list {
  max-height: 274px;
  overflow-y: auto;
  padding: 6px 7px;
}

.builder-field-picker-group {
  padding: 7px 6px 4px;
  color: #8b93a3;
  font-size: 11px;
}

.builder-field-picker-option {
  display: flex;
  width: 100%;
  height: 28px;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.builder-field-picker-option:hover,
.builder-field-picker-option.active {
  background: #eef1f7;
}

.builder-field-picker-option.is-json-subfield {
  padding-left: 20px;
}

.builder-field-picker-option.is-json-subfield .field-name {
  color: #31415f;
}

.field-name {
  min-width: 0;
  overflow: hidden;
  color: #1f2633;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-type {
  flex: 0 0 auto;
  max-width: 190px;
  overflow: hidden;
  color: #8b93a3;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.builder-field-hover-card {
  color: #1f2633;
}

.hover-title {
  color: #1f2633;
  font-size: 13px;
  font-weight: 600;
}

.hover-subtitle {
  margin-top: 4px;
  color: #8b93a3;
  font-size: 11px;
  word-break: break-all;
}

.hover-json-meta,
.hover-expression {
  margin-top: 8px;
  color: #69758a;
  font-size: 11px;
  line-height: 17px;
  word-break: break-all;
}

.hover-expression {
  padding: 6px 8px;
  border-radius: 6px;
  background: #f5f7fb;
  color: #4f5b70;
  font-family: Consolas, Monaco, 'Courier New', monospace;
}

.hover-comment {
  margin-top: 12px;
  color: #4f5869;
  font-size: 12px;
  line-height: 18px;
}

.hover-footer {
  display: flex;
  justify-content: space-between;
  margin-top: 18px;
  color: #8b93a3;
  font-size: 11px;
}

.builder-field-picker-empty {
  display: flex;
  height: 198px;
  align-items: center;
  justify-content: center;
  color: #8b93a3;
  font-size: 12px;
}

:global(.builder-field-picker-popper),
:global(.builder-field-hover-popper) {
  z-index: 5001 !important;
}

:global(.builder-field-hover-popper) {
  z-index: 5002 !important;
}
</style>
