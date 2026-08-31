<script setup lang="ts">
import { computed } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import BuilderFieldPicker from './BuilderFieldPicker.vue'
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

function updateEvent(index: number, event: string) {
  const next = props.modelValue.map((item, itemIndex) => itemIndex === index
    ? { ...item, event, splitProperties: [] }
    : item)
  emits('update:modelValue', next)
}

function updateSplitProperties(index: number, values: string[]) {
  const next = props.modelValue.map((item, itemIndex) => itemIndex === index
    ? { ...item, splitProperties: [...values] }
    : item)
  emits('update:modelValue', next)
}

function addEvent() {
  if (props.modelValue.length >= maxEvents.value) return
  emits('update:modelValue', [
    ...props.modelValue,
    { id: `path-event-${Date.now()}-${props.modelValue.length}`, event: '', splitProperties: [] },
  ])
}

function removeEvent(index: number) {
  if (props.modelValue.length <= 1) {
    emits('update:modelValue', [{ id: `path-event-${Date.now()}`, event: '', splitProperties: [] }])
    return
  }
  emits('update:modelValue', props.modelValue.filter((_, itemIndex) => itemIndex !== index))
}
</script>

<template>
  <div class="path-event-list">
    <div
      v-for="(item, index) in modelValue"
      :key="item.id"
      class="path-event-row"
    >
      <span class="path-event-index">{{ index + 1 }}</span>
      <BuilderFieldPicker
        :model-value="item.event"
        :options="eventOptions"
        :loading="loading"
        mode="tracking-event"
        :placeholder="`选择第${index + 1}个事件`"
        @update:modelValue="updateEvent(index, $event)"
      />
      <span class="path-event-split-label">按</span>
      <el-select
        :model-value="item.splitProperties"
        multiple
        filterable
        collapse-tags
        collapse-tags-tooltip
        clearable
        class="path-event-property-select"
        :disabled="!item.event"
        :placeholder="item.event ? '选择拆分属性' : '先选事件'"
        @update:modelValue="updateSplitProperties(index, $event)"
      >
        <el-option
          v-for="option in propertyOptions(item.event)"
          :key="option.value"
          :label="option.label"
          :value="option.value"
        />
      </el-select>
      <span class="path-event-split-label">拆分</span>
      <button
        type="button"
        class="path-event-remove"
        :disabled="modelValue.length <= 1"
        title="移除参与事件"
        aria-label="移除参与事件"
        @click="removeEvent(index)"
      >
        <el-icon><Delete /></el-icon>
      </button>
    </div>

    <button
      type="button"
      class="path-add-event"
      :disabled="modelValue.length >= maxEvents"
      @click="addEvent"
    >
      <el-icon><Plus /></el-icon>
      <span>拆分项</span>
    </button>
    <p v-if="modelValue.length >= maxEvents" class="path-event-limit-hint">最多选择 {{ maxEvents }} 个参与事件。</p>
  </div>
</template>

<style scoped>
.path-event-list {
  display: grid;
  gap: 9px;
  min-width: 0;
}

.path-event-row {
  display: grid;
  grid-template-columns: 24px minmax(170px, 280px) auto minmax(150px, 260px) auto 28px;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.path-event-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  color: #fff;
  background: #4d63c7;
  font-size: 12px;
}

.path-event-split-label {
  color: #7b8494;
  font-size: 12px;
  white-space: nowrap;
}

.path-event-property-select {
  min-width: 0;
}

.path-event-remove {
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  color: #9aa2af;
  background: transparent;
  cursor: pointer;
}

.path-event-remove:hover:not(:disabled) {
  color: #d14343;
}

.path-event-remove:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.path-add-event {
  display: inline-flex;
  align-items: center;
  justify-self: start;
  gap: 5px;
  padding: 2px 5px;
  border: 0;
  color: #4e6cf3;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
}

.path-add-event:hover:not(:disabled) {
  color: #244de0;
}

.path-add-event:disabled {
  color: #a8b0be;
  cursor: not-allowed;
}

.path-event-limit-hint {
  margin: 0;
  color: #a8b0be;
  font-size: 12px;
}

@media (max-width: 720px) {
  .path-event-row {
    grid-template-columns: 24px minmax(0, 1fr) 28px;
  }

  .path-event-row .path-event-split-label,
  .path-event-property-select {
    grid-column: 2;
  }

  .path-event-row .path-event-split-label:last-of-type {
    display: none;
  }

  .path-event-remove {
    grid-column: 3;
    grid-row: 1 / span 2;
  }
}
</style>
