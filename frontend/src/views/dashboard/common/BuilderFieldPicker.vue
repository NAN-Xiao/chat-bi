<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'

type PickerMode = 'event' | 'property' | 'metric' | 'time'

type FieldOption = {
  label: string
  value: string
  table: string
  tableLabel?: string
  field: string
  displayName?: string
  type?: string
  comment?: string
  tableComment?: string
  category?: string
  sourceField?: string
  jsonPath?: string
  expression?: string
  isJsonSubfield?: boolean
}

defineOptions({ name: 'BuilderFieldPicker' })

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: FieldOption[]
    mode?: PickerMode
    placeholder?: string
    disabled?: boolean
    loading?: boolean
  }>(),
  {
    mode: 'property',
    placeholder: '字段',
    disabled: false,
    loading: false,
  }
)

const emits = defineEmits<{
  'update:modelValue': [value: string]
}>()

const visible = ref(false)
const keyword = ref('')
const activeTab = ref('all')
const TABLE_TAB_PREFIX = 'table:'

const selectedOption = computed(() =>
  props.options.find((item) => item.value === props.modelValue)
)

const selectedLabel = computed(() =>
  selectedOption.value?.displayName || selectedOption.value?.label || selectedOption.value?.field || props.modelValue?.split('.').pop() || ''
)

function shortTableLabel(value = '') {
  const firstLine = String(value || '').split(/\r?\n/).find((line) => line.trim()) || ''
  return firstLine
    .split(/[。；;，,]/)[0]
    .trim()
}

function tableTabLabel(tableName: string, label = '') {
  const shortLabel = shortTableLabel(label)
  if (!shortLabel || shortLabel.toLowerCase() === tableName.toLowerCase()) {
    return tableName
  }
  return `${shortLabel}(${tableName})`
}

const tableTabs = computed(() => {
  const tableLabels = new Map<string, string>()
  props.options.forEach((item) => {
    if (item.table) {
      const currentLabel = tableLabels.get(item.table)
      const nextLabel = shortTableLabel(item.tableLabel || item.tableComment)
      if (!currentLabel || nextLabel) {
        tableLabels.set(item.table, nextLabel || currentLabel || '')
      }
    }
  })
  return Array.from(tableLabels.entries())
    .sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true, sensitivity: 'base' }))
    .map(([tableName, label]) => ({
      label: tableTabLabel(tableName, label),
      value: `${TABLE_TAB_PREFIX}${tableName}`,
    }))
})

const tabOptions = computed(() => {
  return [
    { label: '全部', value: 'all' },
    ...tableTabs.value,
  ]
})

watch(
  () => [props.mode, tabOptions.value.map((item) => item.value).join('|')],
  () => {
    if (!tabOptions.value.some((item) => item.value === activeTab.value)) {
      activeTab.value = 'all'
    }
  }
)

function optionCategory(item: FieldOption) {
  return item.category || 'other'
}

function isIdentifierField(item: FieldOption) {
  const text = `${item.field} ${item.value} ${item.type || ''}`.toLowerCase()
  return /(^|[._\s-])(id|uid|uuid|user_id|userid|player_id|playerid|account_id|accountid)([._\s-]|$)/.test(text)
}

function matchesTab(item: FieldOption, tab: string) {
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
  const keywordRows = props.options.filter((item) => matchesKeyword(item, q))
  const tabRows = keywordRows.filter((item) => matchesTab(item, tab))
  const rows = tabRows.length > 0 || tab === 'all' || tab.startsWith(TABLE_TAB_PREFIX)
    ? tabRows
    : keywordRows
  const groups = new Map<string, FieldOption[]>()
  rows.forEach((item) => {
    const key = tableTabLabel(item.table || '字段', item.tableLabel || item.tableComment)
    if (!groups.has(key)) {
      groups.set(key, [])
    }
    groups.get(key)?.push(item)
  })
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }))
})

function fieldTypeLabel(option: FieldOption) {
  if (option.isJsonSubfield) return 'JSON字段'
  if (option.type) return option.type
  if (isIdentifierField(option)) return '标识'
  if (option.category === 'time') return '时间'
  if (option.category === 'number') return '数值'
  if (option.category === 'text') return '文本'
  return '字段'
}

function displayFieldName(option: FieldOption) {
  return option.displayName || option.label || option.field
}

function selectField(option: FieldOption) {
  emits('update:modelValue', option.value)
  visible.value = false
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    width="460"
    trigger="click"
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
      >
        <span>{{ selectedLabel || placeholder }}</span>
        <span class="builder-field-picker-arrow">⌄</span>
      </button>
    </template>

    <div class="builder-field-picker">
      <div class="builder-field-picker-search">
        <el-icon><Search /></el-icon>
        <input v-model="keyword" placeholder="请输入搜索" />
      </div>
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
      <div v-else-if="groupedOptions.length === 0" class="builder-field-picker-empty">暂无数据</div>
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
                    :class="{ active: item.value === modelValue }"
                    @click="selectField(item)"
                  >
                    <span class="field-name">{{ displayFieldName(item) }}</span>
                    <span class="field-type">{{ fieldTypeLabel(item) }}</span>
                  </button>
                </template>
                <div class="builder-field-hover-card">
                  <div class="hover-title">{{ displayFieldName(item) }}</div>
                  <div class="hover-subtitle">{{ item.value }}</div>
                  <div v-if="item.isJsonSubfield" class="hover-json-meta">
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
  color: #5f687a;
  font-size: 14px;
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
  color: #315cff;
  font-weight: 600;
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

.field-name {
  min-width: 0;
  overflow: hidden;
  color: #1f2633;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-type {
  flex: 0 0 auto;
  color: #8b93a3;
  font-size: 11px;
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
