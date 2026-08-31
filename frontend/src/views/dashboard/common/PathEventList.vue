<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, FolderOpened, Operation, Search } from '@element-plus/icons-vue'
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
const splitPickerVisible = ref(false)
const keyword = ref('')

const selectedEventValues = computed(() => props.modelValue
  .map((item) => item.event)
  .filter(Boolean))

const selectedEventCount = computed(() => selectedEventValues.value.length)

const selectedEvents = computed(() => props.modelValue.filter((item) => item.event))

const filteredEventOptions = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return props.eventOptions
  return props.eventOptions.filter((option) => [
    option.value,
    option.field,
    option.label,
    option.displayName,
    option.eventName,
  ].some((value) => String(value || '').toLowerCase().includes(query)))
})

function eventLabel(value: string) {
  const option = props.eventOptions.find((item) => item.value === value)
  return fieldOptionDisplayName(option, value)
}

function isEventSelected(value: string) {
  return selectedEventValues.value.includes(value)
}

function emptyEvent(): PathAnalysisEvent {
  return { id: `path-event-${Date.now()}`, event: '', splitProperties: [] }
}

function updateSelectedEvents(values: string[]) {
  const previousByEvent = new Map(
    props.modelValue
      .filter((item) => item.event)
      .map((item) => [item.event, item]),
  )
  const next = values.map((event, index) => {
    const previous = previousByEvent.get(event)
    return previous || {
      id: `path-event-${Date.now()}-${index}`,
      event,
      splitProperties: [],
    }
  })
  emits('update:modelValue', next.length ? next : [emptyEvent()])
}

function toggleEvent(value: string) {
  const nextValues = isEventSelected(value)
    ? selectedEventValues.value.filter((event) => event !== value)
    : [...selectedEventValues.value, value]
  updateSelectedEvents(nextValues)
}

function updateSplitProperties(event: string, values: string[]) {
  emits('update:modelValue', props.modelValue.map((item) => item.event === event
    ? { ...item, splitProperties: [...values] }
    : item))
}
</script>

<template>
  <div class="path-event-list">
    <el-popover
      v-model:visible="eventPickerVisible"
      width="360"
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
          <input v-model="keyword" placeholder="搜索事件" />
        </div>
        <div v-if="loading" class="path-event-picker-empty">加载中...</div>
        <div v-else-if="filteredEventOptions.length === 0" class="path-event-picker-empty">暂无事件</div>
        <div v-else class="path-event-picker-options">
          <button
            v-for="option in filteredEventOptions"
            :key="option.value"
            type="button"
            class="path-event-picker-option"
            :disabled="!isEventSelected(option.value) && selectedEventCount >= maxEvents"
            @click="toggleEvent(option.value)"
          >
            <span class="path-event-picker-check" :class="{ 'is-selected': isEventSelected(option.value) }">
              <el-icon v-if="isEventSelected(option.value)"><Check /></el-icon>
            </span>
            <span class="path-event-picker-option-text">
              <span>{{ fieldOptionDisplayName(option, option.value) }}</span>
              <small v-if="option.eventName">{{ option.eventName }}</small>
            </span>
          </button>
        </div>
        <p v-if="selectedEventCount >= maxEvents" class="path-event-limit-hint">
          最多选择 {{ maxEvents }} 个事件
        </p>
      </div>
    </el-popover>

    <el-popover
      v-model:visible="splitPickerVisible"
      width="440"
      trigger="click"
      placement="bottom-start"
      popper-class="path-event-split-popper"
      :popper-style="{ zIndex: 5001 }"
    >
      <template #reference>
        <button
          type="button"
          class="path-split-trigger"
          :class="{ 'is-active': splitPickerVisible }"
          :aria-expanded="splitPickerVisible"
          aria-label="设置事件拆分"
        >
          <el-icon><Operation /></el-icon>
          <span>事件拆分</span>
        </button>
      </template>

      <div class="path-event-split-picker">
        <div v-if="selectedEvents.length === 0" class="path-event-picker-empty">
          请先选择参与分析的事件
        </div>
        <div v-for="item in selectedEvents" :key="item.id" class="path-event-split-row">
          <span class="path-event-split-event">
            <el-icon><FolderOpened /></el-icon>
            <span>{{ eventLabel(item.event) }}</span>
          </span>
          <span class="path-event-split-word">按</span>
          <el-select
            :model-value="item.splitProperties"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            clearable
            class="path-event-property-select"
            :disabled="!propertyOptions(item.event).length"
            :placeholder="propertyOptions(item.event).length ? '选择属性' : '暂无属性'"
            @update:modelValue="updateSplitProperties(item.event, $event)"
          >
            <el-option
              v-for="option in propertyOptions(item.event)"
              :key="option.value"
              :label="option.label || option.displayName || option.field"
              :value="option.value"
            />
          </el-select>
        </div>
      </div>
    </el-popover>
  </div>
</template>

<style scoped>
.path-event-list {
  display: inline-flex;
  align-items: center;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.path-event-trigger,
.path-split-trigger {
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
.path-event-trigger[aria-expanded='true'],
.path-split-trigger:hover,
.path-split-trigger.is-active {
  color: #315cff;
  background: #eef3ff;
}

.path-split-trigger {
  padding: 0 4px;
  color: #315cff;
  background: transparent;
}

.path-event-picker,
.path-event-split-picker {
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

.path-event-picker-options {
  max-height: 280px;
  overflow-y: auto;
  padding: 6px;
}

.path-event-picker-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  padding: 5px 8px;
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

.path-event-split-picker {
  display: grid;
  gap: 8px;
  max-height: 320px;
  overflow-y: auto;
  padding: 2px;
}

.path-event-split-row {
  display: grid;
  grid-template-columns: minmax(100px, 1fr) auto minmax(150px, 1.4fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.path-event-split-event {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  color: #374151;
  background: #f4f6fa;
  border-radius: 6px;
  line-height: 26px;
}

.path-event-split-event span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.path-event-split-word {
  color: #8a93a3;
  white-space: nowrap;
}

.path-event-property-select {
  min-width: 0;
}

.path-event-property-select :deep(.el-select__wrapper) {
  min-height: 26px;
  border-radius: 6px;
  box-shadow: none;
  background: #f3f5fa;
}

@media (max-width: 720px) {
  .path-event-list {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .path-event-split-row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .path-event-property-select {
    grid-column: 1 / -1;
  }
}
</style>
