<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  maxAttributionWindowValue,
  normalizeAttributionWindow,
  type AttributionWindowConfig,
  type AttributionWindowMode,
  type AttributionWindowUnit,
} from './attributionAnalysis'

const props = defineProps<{
  modelValue: AttributionWindowConfig
  disabled?: boolean
}>()

const emits = defineEmits<{
  'update:modelValue': [value: AttributionWindowConfig]
}>()

const normalizedValue = computed(() => normalizeAttributionWindow(props.modelValue))
const maxValue = computed(() => maxAttributionWindowValue(normalizedValue.value.unit))

const unitOptions: Array<{ label: string; value: AttributionWindowUnit }> = [
  { label: '天', value: 'day' },
  { label: '小时', value: 'hour' },
  { label: '分钟', value: 'minute' },
]

function updateValue(value: number | undefined) {
  const numericValue = Number(value)
  emits('update:modelValue', normalizeAttributionWindow({
    ...normalizedValue.value,
    mode: 'duration',
    value: Number.isInteger(numericValue) ? numericValue : 1,
  }))
}

function updateUnit(unit: AttributionWindowUnit) {
  const current = normalizedValue.value
  emits('update:modelValue', {
    mode: 'duration',
    value: Math.min(current.value, maxAttributionWindowValue(unit)),
    unit,
  })
}

function updateMode(mode: AttributionWindowMode) {
  if (mode === 'same_day') {
    emits('update:modelValue', { mode: 'same_day', value: 1, unit: 'day' })
    return
  }
  const current = normalizedValue.value
  emits('update:modelValue', { mode: 'duration', value: current.value || 1, unit: current.unit || 'day' })
}
</script>

<template>
  <div class="attribution-window-picker">
    <span class="attribution-window-label">
      窗口期
      <el-tooltip content="归因事件必须发生在目标事件之前且位于此时间窗口内。" placement="top">
        <el-icon aria-label="归因窗口期说明"><InfoFilled /></el-icon>
      </el-tooltip>
    </span>
    <el-select
      class="attribution-window-mode"
      :model-value="normalizedValue.mode"
      :disabled="disabled"
      aria-label="归因窗口期模式"
      @update:modelValue="updateMode"
    >
      <el-option label="当天" value="same_day" />
      <el-option label="自定义" value="duration" />
    </el-select>
    <el-input-number
      class="attribution-window-value"
      v-if="normalizedValue.mode === 'duration'"
      :model-value="normalizedValue.value"
      :min="1"
      :max="maxValue"
      :precision="0"
      :controls="false"
      :disabled="disabled"
      aria-label="自定义归因窗口数值"
      @update:modelValue="updateValue"
    />
    <el-select
      class="attribution-window-unit"
      :model-value="normalizedValue.unit"
      v-if="normalizedValue.mode === 'duration'"
      :disabled="disabled"
      aria-label="归因窗口单位"
      @update:modelValue="updateUnit"
    >
      <el-option
        v-for="option in unitOptions"
        :key="option.value"
        :label="option.label"
        :value="option.value"
      />
    </el-select>
  </div>
</template>

<style scoped>
.attribution-window-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #505968;
  font-size: 13px;
}

.attribution-window-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.attribution-window-label .el-icon {
  color: #8d96a5;
  cursor: help;
}

.attribution-window-mode,
.attribution-window-value,
.attribution-window-unit {
  width: 126px;
  max-width: 126px;
  flex: 0 1 126px;
}

:deep(.ed-input__wrapper),
:deep(.el-input__wrapper) {
  min-height: 32px;
  border-radius: 6px;
}

@media (max-width: 540px) {
  .attribution-window-picker {
    flex-wrap: wrap;
    width: 100%;
  }
}
</style>
