<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Close, FolderOpened, Minus, Operation, Plus, Search } from '@element-plus/icons-vue'
import BuilderFieldPicker from './BuilderFieldPicker.vue'
import { fieldOptionDisplayName } from './builderFieldPickerOptions'
import type { PathAnalysisEvent } from './pathAnalysis'

const props = defineProps<{
  modelValue: PathAnalysisEvent[]
  eventOptions: Array<any>
  propertyOptions: (event: string) => Array<any>
  loading?: boolean
  maxEvents?: number
}>()

const emits = defineEmits<{
  'update:modelValue': [value: PathAnalysisEvent[]]
}>()

const maxEvents = computed(() => props.maxEvents || 30)
const eventPickerVisible = ref(false)
const draftSplitVisible = ref(false)
const keyword = ref('')
const activeEventCategory = ref('')

const selectedEventValues = computed(() =>
  props.modelValue.map((item) => item.event).filter(Boolean)
)

const selectedEventCount = computed(() => selectedEventValues.value.length)

const splitItems = computed(() =>
  props.modelValue.filter((item) => item.event && item.splitProperties.length > 0)
)

const configuredSplitEvents = computed(() => new Set(splitItems.value.map((item) => item.event)))

const availableSplitEventOptions = computed(() =>
  props.eventOptions.filter(
    (option) =>
      selectedEventValues.value.includes(option.value) &&
      !configuredSplitEvents.value.has(option.value)
  )
)

const filteredEventOptions = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return props.eventOptions
  return props.eventOptions.filter((option) =>
    [option.value, option.field, option.label, option.displayName, option.eventName].some((value) =>
      String(value || '')
        .toLowerCase()
        .includes(query)
    )
  )
})

const eventGroups = computed(() => {
  const groups = new Map<string, Array<any>>()
  filteredEventOptions.value.forEach((option) => {
    const category = option.eventCategory || option.category || '默认分组'
    if (!groups.has(category)) groups.set(category, [])
    groups.get(category)?.push(option)
  })
  return Array.from(groups.entries()).map(([name, items]) => ({
    name,
    items: items.sort((a, b) =>
      fieldOptionDisplayName(a, a.value).localeCompare(
        fieldOptionDisplayName(b, b.value),
        undefined,
        { numeric: true, sensitivity: 'base' }
      )
    ),
  }))
})

const activeEventGroup = computed(
  () =>
    eventGroups.value.find((group) => group.name === activeEventCategory.value) ||
    eventGroups.value[0]
)

const activeEventItems = computed(() => activeEventGroup.value?.items || [])

const filteredEventValues = computed(() => filteredEventOptions.value.map((option) => option.value))
const selectedFilteredEventCount = computed(
  () => filteredEventValues.value.filter((value) => isEventSelected(value)).length
)
const allFilteredEventsSelected = computed(
  () =>
    filteredEventValues.value.length > 0 &&
    selectedFilteredEventCount.value === filteredEventValues.value.length
)
const someFilteredEventsSelected = computed(
  () => selectedFilteredEventCount.value > 0 && !allFilteredEventsSelected.value
)
const filteredSelectionValues = computed(() =>
  Array.from(new Set([...selectedEventValues.value, ...filteredEventValues.value]))
)
const selectingAllWouldExceedLimit = computed(
  () => !allFilteredEventsSelected.value && filteredSelectionValues.value.length > maxEvents.value
)

watch(availableSplitEventOptions, (options) => {
  if (!options.length) draftSplitVisible.value = false
})

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

function isEventSelected(value: string) {
  return selectedEventValues.value.includes(value)
}

function emptyEvent(): PathAnalysisEvent {
  return { id: `path-event-${Date.now()}`, event: '', splitProperties: [] }
}

function updateSelectedEvents(values: string[]) {
  const previousByEvent = new Map(
    props.modelValue.filter((item) => item.event).map((item) => [item.event, item])
  )
  const next = values.map((event, index) => {
    const previous = previousByEvent.get(event)
    return (
      previous || {
        id: `path-event-${Date.now()}-${index}`,
        event,
        splitProperties: [],
      }
    )
  })
  emits('update:modelValue', next.length ? next : [emptyEvent()])
}

function toggleEvent(value: string) {
  const nextValues = isEventSelected(value)
    ? selectedEventValues.value.filter((event) => event !== value)
    : [...selectedEventValues.value, value]
  updateSelectedEvents(nextValues)
}

function toggleAllFilteredEvents() {
  const visibleValues = filteredEventValues.value
  if (!visibleValues.length) return
  if (allFilteredEventsSelected.value) {
    updateSelectedEvents(
      selectedEventValues.value.filter((event) => !visibleValues.includes(event))
    )
    return
  }
  if (selectingAllWouldExceedLimit.value) return
  updateSelectedEvents(filteredSelectionValues.value)
}

function splitEventOptions(currentEvent: string) {
  return props.eventOptions.filter(
    (option) =>
      selectedEventValues.value.includes(option.value) &&
      (option.value === currentEvent || !configuredSplitEvents.value.has(option.value))
  )
}

function addSplitEvent(event: string) {
  if (!event || configuredSplitEvents.value.has(event)) return
  emits(
    'update:modelValue',
    props.modelValue.map((item) =>
      item.event === event ? { ...item, splitProperties: [''] } : item
    )
  )
  draftSplitVisible.value = false
}

function updateSplitEvent(currentEvent: string, nextEvent: string) {
  if (!nextEvent || nextEvent === currentEvent || configuredSplitEvents.value.has(nextEvent)) return
  emits(
    'update:modelValue',
    props.modelValue.map((item) => {
      if (item.event === currentEvent) return { ...item, splitProperties: [] }
      if (item.event === nextEvent) return { ...item, splitProperties: [''] }
      return item
    })
  )
}

function updateSplitProperty(event: string, value: string) {
  emits(
    'update:modelValue',
    props.modelValue.map((item) =>
      item.event === event ? { ...item, splitProperties: [value] } : item
    )
  )
}

function removeSplitItem(event: string) {
  emits(
    'update:modelValue',
    props.modelValue.map((item) => (item.event === event ? { ...item, splitProperties: [] } : item))
  )
}
</script>

<template>
  <div class="path-event-list">
    <el-popover
      v-model:visible="eventPickerVisible"
      width="440"
      trigger="click"
      placement="bottom-start"
      popper-class="path-event-picker-popper"
      :popper-style="{ zIndex: 5001 }"
    >
      <template #reference>
        <button
          type="button"
          class="path-event-trigger"
          :aria-expanded="eventPickerVisible"
          aria-label="选择参与分析的事件"
        >
          <el-icon><FolderOpened /></el-icon>
          <span>事件({{ selectedEventCount }})</span>
        </button>
      </template>

      <div class="path-event-picker">
        <div class="path-event-picker-search">
          <el-icon><Search /></el-icon>
          <input v-model="keyword" placeholder="请输入搜索" />
        </div>
        <button
          type="button"
          class="path-event-picker-select-all"
          :aria-pressed="allFilteredEventsSelected"
          :disabled="filteredEventOptions.length === 0 || selectingAllWouldExceedLimit"
          @click="toggleAllFilteredEvents"
        >
          <span
            class="path-event-picker-check"
            :class="{ 'is-selected': allFilteredEventsSelected || someFilteredEventsSelected }"
          >
            <el-icon v-if="allFilteredEventsSelected"><Check /></el-icon>
            <el-icon v-else-if="someFilteredEventsSelected"><Minus /></el-icon>
          </span>
          <span>全选</span>
        </button>
        <div class="path-event-picker-tabs">
          <button type="button" class="active">事件</button>
        </div>
        <div v-if="loading" class="path-event-picker-empty">加载中...</div>
        <div v-else-if="eventGroups.length === 0" class="path-event-picker-empty">暂无事件</div>
        <div v-else class="path-event-picker-columns">
          <div class="path-event-category-list">
            <button
              v-for="group in eventGroups"
              :key="group.name"
              type="button"
              :class="{ active: activeEventCategory === group.name }"
              :aria-pressed="activeEventCategory === group.name"
              @click="activeEventCategory = group.name"
            >
              {{ group.name }}
            </button>
          </div>
          <div class="path-event-picker-options">
            <div class="path-event-picker-group-title">{{ activeEventGroup?.name }}</div>
            <button
              v-for="option in activeEventItems"
              :key="option.value"
              type="button"
              class="path-event-picker-option"
              :class="{ active: isEventSelected(option.value) }"
              :aria-pressed="isEventSelected(option.value)"
              :disabled="!isEventSelected(option.value) && selectedEventCount >= maxEvents"
              @click="toggleEvent(option.value)"
            >
              <span
                class="path-event-picker-check"
                :class="{ 'is-selected': isEventSelected(option.value) }"
              >
                <el-icon v-if="isEventSelected(option.value)"><Check /></el-icon>
              </span>
              <span class="path-event-picker-option-text">
                <span>{{ fieldOptionDisplayName(option, option.value) }}</span>
                <small v-if="option.eventName">{{ option.eventName }}</small>
              </span>
            </button>
          </div>
        </div>
        <p v-if="selectedEventCount >= maxEvents" class="path-event-limit-hint">
          最多选择 {{ maxEvents }} 个事件
        </p>
      </div>
    </el-popover>

    <div v-if="splitItems.length || draftSplitVisible" class="path-split-list">
      <div v-for="item in splitItems" :key="item.id" class="path-split-row">
        <span class="path-split-picker path-split-event-picker">
          <el-icon><FolderOpened /></el-icon>
          <BuilderFieldPicker
            :model-value="item.event"
            :options="splitEventOptions(item.event)"
            :loading="loading"
            mode="tracking-event"
            placeholder="选择事件"
            @update:model-value="updateSplitEvent(item.event, $event)"
          />
        </span>
        <span class="path-split-word">按</span>
        <span class="path-split-picker path-split-property-picker">
          <el-icon><Operation /></el-icon>
          <BuilderFieldPicker
            :model-value="item.splitProperties[0] || ''"
            :options="propertyOptions(item.event)"
            :loading="loading"
            mode="property"
            placeholder="选择属性"
            @update:model-value="updateSplitProperty(item.event, $event)"
          />
        </span>
        <span class="path-split-word">拆分</span>
        <button
          type="button"
          class="path-split-remove"
          title="删除拆分项"
          aria-label="删除拆分项"
          @click="removeSplitItem(item.event)"
        >
          <el-icon><Close /></el-icon>
        </button>
      </div>

      <div v-if="draftSplitVisible" class="path-split-row path-split-draft-row">
        <span class="path-split-picker path-split-event-picker">
          <el-icon><FolderOpened /></el-icon>
          <BuilderFieldPicker
            model-value=""
            :options="availableSplitEventOptions"
            :loading="loading"
            mode="tracking-event"
            placeholder="选择事件"
            @update:model-value="addSplitEvent"
          />
        </span>
        <span class="path-split-word">按</span>
        <span class="path-split-picker path-split-property-picker is-disabled">
          <el-icon><Operation /></el-icon>
          <span>选择属性</span>
        </span>
        <span class="path-split-word">拆分</span>
        <button
          type="button"
          class="path-split-remove"
          title="取消新增拆分项"
          aria-label="取消新增拆分项"
          @click="draftSplitVisible = false"
        >
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </div>

    <button
      type="button"
      class="path-add-split"
      :disabled="!availableSplitEventOptions.length || draftSplitVisible"
      @click="draftSplitVisible = true"
    >
      <el-icon><Plus /></el-icon>
      <span>拆分项</span>
    </button>
  </div>
</template>

<style scoped>
.path-event-list {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  flex-direction: column;
  gap: 8px;
}

.path-event-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 26px;
  padding: 0 9px;
  border: 0;
  border-radius: 6px;
  color: #374151;
  background: #f0f2f6;
  cursor: pointer;
  font-size: 12px;
  line-height: 24px;
  white-space: nowrap;
}

.path-event-trigger:hover,
.path-event-trigger[aria-expanded='true'] {
  color: #315cff;
  background: #eef3ff;
}

.path-event-picker {
  min-height: 330px;
  color: #1f2633;
  font-size: 12px;
}

.path-event-picker-search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 9px;
  border-bottom: 1px solid #edf0f5;
  color: #8b93a3;
}

.path-event-picker-search input {
  width: 100%;
  border: 0;
  outline: 0;
  color: #1f2633;
  font-size: 12px;
}

.path-event-picker-select-all {
  display: flex;
  width: 100%;
  height: 36px;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border: 0;
  border-bottom: 1px solid #edf0f5;
  color: #1f2633;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  text-align: left;
}

.path-event-picker-select-all:hover:not(:disabled) {
  background: #f4f6fa;
}

.path-event-picker-select-all:disabled {
  color: #b5bbc6;
  cursor: not-allowed;
}

.path-event-picker-tabs {
  display: flex;
  height: 38px;
  align-items: flex-end;
  padding: 0 12px;
  border-bottom: 1px solid #edf0f5;
}

.path-event-picker-tabs button {
  height: 38px;
  padding: 0;
  border: 0;
  border-bottom: 2px solid transparent;
  color: #5f687a;
  background: transparent;
  font-size: 12px;
}

.path-event-picker-tabs button.active {
  border-color: #315cff;
  color: #1f2633;
  font-weight: 600;
}

.path-event-picker-columns {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  min-height: 224px;
}

.path-event-category-list {
  max-height: 280px;
  overflow-y: auto;
  padding: 7px 6px;
  border-right: 1px solid #edf0f5;
}

.path-event-category-list button {
  display: block;
  width: 100%;
  height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  color: #374151;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-event-category-list button:hover,
.path-event-category-list button.active {
  color: #315cff;
  background: #eef1f7;
  font-weight: 600;
}

.path-event-picker-options {
  max-height: 280px;
  overflow-y: auto;
  padding: 7px 8px;
}

.path-event-picker-group-title {
  height: 28px;
  padding: 0 8px;
  color: #5f687a;
  font-size: 12px;
  font-weight: 600;
  line-height: 28px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-event-picker-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 4px 8px;
  border: 0;
  border-radius: 6px;
  color: #1f2633;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.path-event-picker-option:hover:not(:disabled) {
  background: #f4f6fa;
}

.path-event-picker-option.active {
  background: #eef1f7;
}

.path-event-picker-option:disabled {
  color: #b5bbc6;
  cursor: not-allowed;
}

.path-event-picker-check {
  display: inline-flex;
  width: 16px;
  height: 16px;
  align-items: center;
  justify-content: center;
  flex: 0 0 16px;
  border: 1px solid #c8ced9;
  border-radius: 4px;
  color: #fff;
  background: #fff;
  font-size: 12px;
}

.path-event-picker-check.is-selected {
  border-color: #315cff;
  background: #315cff;
}

.path-event-picker-option-text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 1px;
}

.path-event-picker-option-text > span,
.path-event-picker-option-text > small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-event-picker-option-text small {
  color: #9aa2af;
  font-size: 11px;
}

.path-event-picker-empty {
  display: flex;
  min-height: 224px;
  align-items: center;
  justify-content: center;
  padding: 22px 12px;
  color: #9aa2af;
  text-align: center;
}

.path-event-limit-hint {
  margin: 0;
  padding: 0 12px 8px;
  color: #a8b0be;
  font-size: 12px;
}

.path-split-list {
  display: grid;
  gap: 7px;
  max-width: 100%;
  margin-left: 12px;
  padding-left: 10px;
  border-left: 1px solid #e4e8f0;
}

.path-split-row {
  display: grid;
  grid-template-columns: minmax(110px, 160px) auto minmax(120px, 180px) auto 24px;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.path-split-picker {
  display: flex;
  min-width: 0;
  min-height: 26px;
  align-items: center;
  gap: 4px;
  padding-left: 7px;
  border-radius: 6px;
  color: #4d5666;
  background: #f3f5fa;
}

.path-split-picker > .el-icon {
  flex: 0 0 14px;
}

.path-split-picker :deep(.builder-field-picker) {
  min-width: 0;
}

.path-split-picker :deep(.builder-field-picker-trigger) {
  width: 100%;
  min-width: 0;
  padding-left: 0;
}

.path-split-picker.is-disabled {
  padding-right: 8px;
  color: #a6adba;
  font-size: 12px;
}

.path-split-word {
  color: #8a93a3;
  font-size: 12px;
  white-space: nowrap;
}

.path-split-remove {
  display: inline-flex;
  width: 24px;
  height: 24px;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
  border-radius: 4px;
  color: #a2a9b5;
  background: transparent;
  cursor: pointer;
}

.path-split-remove:hover {
  color: #d14343;
  background: #fff0f0;
}

.path-add-split {
  display: inline-flex;
  min-height: 26px;
  align-items: center;
  gap: 4px;
  padding: 0 4px;
  border: 0;
  color: #315cff;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}

.path-add-split:hover:not(:disabled) {
  color: #244de0;
}

.path-add-split:disabled {
  color: #b2b8c3;
  cursor: not-allowed;
}

@media (max-width: 720px) {
  .path-split-row {
    grid-template-columns: minmax(0, 1fr) auto 24px;
  }

  .path-split-property-picker {
    grid-column: 1;
    grid-row: 2;
  }

  .path-split-row > .path-split-word:nth-of-type(2) {
    grid-column: 2;
    grid-row: 2;
  }

  .path-split-remove {
    grid-column: 3;
    grid-row: 1 / span 2;
  }
}
</style>
