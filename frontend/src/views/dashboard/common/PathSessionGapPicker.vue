<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus-secondary'
import {
  DEFAULT_PATH_SESSION_GAP_SECONDS,
  PATH_SESSION_GAP_MAX_SECONDS,
  PATH_SESSION_GAP_MIN_SECONDS,
  clampPathSessionGapSeconds,
} from './pathAnalysis'

const props = defineProps<{ modelValue: number; disabled?: boolean }>()
const emits = defineEmits<{ 'update:modelValue': [value: number] }>()

type DurationUnit = 'second' | 'minute' | 'hour'
const units: Array<{ label: string; value: DurationUnit; seconds: number }> = [
  { label: '秒', value: 'second', seconds: 1 },
  { label: '分钟', value: 'minute', seconds: 60 },
  { label: '小时', value: 'hour', seconds: 3600 },
]
const selectedUnit = ref<DurationUnit>('minute')
const inputValue = ref(30)

const currentUnit = computed(() => units.find((item) => item.value === selectedUnit.value) || units[1])
const maxInputValue = computed(() => Math.floor(PATH_SESSION_GAP_MAX_SECONDS / currentUnit.value.seconds))

function syncFromSeconds(value: unknown) {
  const seconds = clampPathSessionGapSeconds(value || DEFAULT_PATH_SESSION_GAP_SECONDS)
  if (seconds % 3600 === 0) {
    selectedUnit.value = 'hour'
    inputValue.value = seconds / 3600
  } else if (seconds % 60 === 0) {
    selectedUnit.value = 'minute'
    inputValue.value = seconds / 60
  } else {
    selectedUnit.value = 'second'
    inputValue.value = seconds
  }
}

watch(() => props.modelValue, syncFromSeconds, { immediate: true })

function emitCurrentValue() {
  const seconds = Number(inputValue.value) * currentUnit.value.seconds
  if (!Number.isFinite(seconds)
    || seconds < PATH_SESSION_GAP_MIN_SECONDS
    || seconds > PATH_SESSION_GAP_MAX_SECONDS) {
    ElMessage.warning('路径分析会话间隔必须在 1 秒到 24 小时之间。')
    syncFromSeconds(props.modelValue)
    return
  }
  emits('update:modelValue', clampPathSessionGapSeconds(seconds))
}

function handleUnitChange(value: DurationUnit) {
  selectedUnit.value = value
  const unit = units.find((item) => item.value === value) || units[1]
  inputValue.value = Math.max(1, Math.round(clampPathSessionGapSeconds(props.modelValue) / unit.seconds))
  emitCurrentValue()
}
</script>

<template>
  <div class="path-session-gap-picker" :class="{ 'is-disabled': disabled }">
    <el-input-number
      v-model="inputValue"
      class="path-session-gap-value"
      :min="1"
      :max="maxInputValue"
      :precision="0"
      :disabled="disabled"
      controls-position="right"
      aria-label="会话间隔数值"
      @change="emitCurrentValue"
    />
    <el-select
      :model-value="selectedUnit"
      class="path-session-gap-unit"
      :disabled="disabled"
      aria-label="会话间隔单位"
      @update:modelValue="handleUnitChange"
    >
      <el-option v-for="unit in units" :key="unit.value" :label="unit.label" :value="unit.value" />
    </el-select>
    <el-tooltip content="会话间隔范围为 1 秒到 24 小时，超过间隔会断开当前会话。" placement="top">
      <span class="path-session-gap-info" aria-label="会话间隔说明">i</span>
    </el-tooltip>
  </div>
</template>

<style scoped>
.path-session-gap-picker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}

.path-session-gap-value { width: 52px; }
.path-session-gap-unit { width: 58px; }

.path-session-gap-value :deep(.el-input__wrapper),
.path-session-gap-unit :deep(.el-select__wrapper) {
  min-height: 28px;
  border-radius: 6px;
  box-shadow: none;
  background: #f3f5fb;
}

.path-session-gap-value :deep(.el-input__inner) { text-align: center; }
.path-session-gap-value :deep(.el-input-number__decrease),
.path-session-gap-value :deep(.el-input-number__increase) { display: none; }
.path-session-gap-unit :deep(.el-select__selected-item) { color: #303643; }

.path-session-gap-info {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  border: 1px solid #4b515c;
  border-radius: 50%;
  color: #4b515c;
  font-size: 10px;
  line-height: 1;
  cursor: help;
}

.path-session-gap-picker.is-disabled { opacity: .55; }
</style>
