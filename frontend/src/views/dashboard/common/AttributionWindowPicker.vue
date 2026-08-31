<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  maxAttributionWindowValue,
  normalizeAttributionWindow,
  type AttributionWindowConfig,
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
    value: Number.isInteger(numericValue) ? numericValue : 1,
  }))
}

function updateUnit(unit: AttributionWindowUnit) {
  const current = normalizedValue.value
  emits('update:modelValue', {
    mode: 'custom',
    value: Math.min(current.value, maxAttributionWindowValue(unit)),
    unit,
  })
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
    <el-select class="attribution-window-mode" model-value="custom" :disabled="disabled">
      <el-option label="自定义" value="custom" />
    </el-select>
    <el-input-number
      class="attribution-window-value"
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
  display: grid;
  grid-template-columns: 64px 100px 68px 82px;
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
  width: 100%;
}

:deep(.ed-input__wrapper),
:deep(.el-input__wrapper) {
  min-height: 32px;
  border-radius: 6px;
}

@media (max-width: 540px) {
  .attribution-window-picker {
    grid-template-columns: 64px minmax(92px, 1fr) 68px 76px;
    width: 100%;
  }
}
</style>
