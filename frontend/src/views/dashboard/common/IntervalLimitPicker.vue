<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus-secondary'
import {
  DEFAULT_INTERVAL_LIMIT_SECONDS,
  INTERVAL_LIMIT_MAX_SECONDS,
  INTERVAL_LIMIT_MIN_SECONDS,
  clampIntervalLimitSeconds,
  formatIntervalLimit,
} from './intervalAnalysis'

const props = defineProps<{
  modelValue: number
  disabled?: boolean
}>()

const emits = defineEmits<{
  'update:modelValue': [value: number]
}>()

type DurationUnit = 'day' | 'hour' | 'minute'

const visible = ref(false)
const selectedUnit = ref<DurationUnit>('hour')
const draftValue = ref(1)
const unitOptions: Array<{ label: string; value: DurationUnit; seconds: number }> = [
  { label: '天（即24小时）', value: 'day', seconds: 86400 },
  { label: '小时', value: 'hour', seconds: 3600 },
  { label: '分钟', value: 'minute', seconds: 60 },
]
const presets: Record<DurationUnit, number[]> = {
  day: [1, 7, 14],
  hour: [1, 3, 12],
  minute: [1, 15, 30],
}

const activeLabel = computed(() =>
  formatIntervalLimit(props.modelValue || DEFAULT_INTERVAL_LIMIT_SECONDS)
)
const draftSeconds = computed(() => {
  const unit = unitOptions.find((item) => item.value === selectedUnit.value) || unitOptions[1]
  return Number(draftValue.value) * unit.seconds
})
const maxDraftValue = computed(() => {
  const unit = unitOptions.find((item) => item.value === selectedUnit.value) || unitOptions[1]
  return Math.floor(INTERVAL_LIMIT_MAX_SECONDS / unit.seconds)
})

function resetDraft() {
  const seconds = clampIntervalLimitSeconds(props.modelValue)
  if (seconds % 86400 === 0) {
    selectedUnit.value = 'day'
    draftValue.value = seconds / 86400
  } else if (seconds % 3600 === 0) {
    selectedUnit.value = 'hour'
    draftValue.value = seconds / 3600
  } else {
    selectedUnit.value = 'minute'
    draftValue.value = Math.max(1, Math.round(seconds / 60))
  }
}

watch(visible, (next) => {
  if (next) resetDraft()
})

function selectUnit(unit: DurationUnit) {
  selectedUnit.value = unit
  const seconds = clampIntervalLimitSeconds(props.modelValue)
  const unitSeconds = unitOptions.find((item) => item.value === unit)?.seconds || 3600
  draftValue.value =
    seconds % unitSeconds === 0
      ? Math.min(seconds / unitSeconds, maxDraftValue.value)
      : presets[unit][0]
}

function selectPreset(value: number) {
  const unitSeconds = unitOptions.find((item) => item.value === selectedUnit.value)?.seconds || 3600
  emits('update:modelValue', value * unitSeconds)
  visible.value = false
}

function applyCustomLimit() {
  if (
    !Number.isFinite(draftSeconds.value) ||
    draftSeconds.value < INTERVAL_LIMIT_MIN_SECONDS ||
    draftSeconds.value > INTERVAL_LIMIT_MAX_SECONDS
  ) {
    ElMessage.warning('间隔上限必须在 1 分钟到 180 天之间。')
    resetDraft()
    return
  }
  emits('update:modelValue', clampIntervalLimitSeconds(draftSeconds.value))
}

function isPresetActive(value: number) {
  const unitSeconds = unitOptions.find((item) => item.value === selectedUnit.value)?.seconds || 3600
  return props.modelValue === value * unitSeconds
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="304"
    trigger="click"
    popper-class="interval-limit-popper"
    :teleported="false"
  >
    <template #reference>
      <button
        type="button"
        class="interval-limit-trigger"
        :disabled="disabled"
        title="设置间隔上限"
        aria-label="设置间隔上限"
      >
        {{ activeLabel }}
      </button>
    </template>

    <div class="interval-limit-panel">
      <div class="interval-limit-menu">
        <div class="interval-limit-current">
          <span>{{ activeLabel }}</span>
          <el-tooltip content="限制起点事件到终点事件之间可参与统计的最长时间。" placement="top">
            <el-icon aria-label="间隔上限说明"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <button
          v-for="unit in unitOptions"
          :key="unit.value"
          type="button"
          :class="{ 'is-active': selectedUnit === unit.value }"
          @click="selectUnit(unit.value)"
        >
          <span>{{ unit.label }}</span>
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>

      <div class="interval-limit-values" aria-label="快捷间隔上限">
        <button
          v-for="value in presets[selectedUnit]"
          :key="value"
          type="button"
          :class="{ 'is-active': isPresetActive(value) }"
          @click="selectPreset(value)"
        >
          {{ value }}{{ selectedUnit === 'day' ? '天' : selectedUnit === 'hour' ? '小时' : '分钟' }}
        </button>
        <div class="interval-limit-custom">
          <el-input-number
            v-model="draftValue"
            :min="1"
            :max="maxDraftValue"
            :precision="0"
            :controls="false"
            aria-label="自定义间隔数值"
            @change="applyCustomLimit"
            @keydown.enter.stop="applyCustomLimit"
          />
          <span>{{
            selectedUnit === 'day' ? '天' : selectedUnit === 'hour' ? '小时' : '分钟'
          }}</span>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.interval-limit-trigger {
  min-width: 58px;
  height: 30px;
  padding: 0 9px;
  border: 1px solid #8aa0ff;
  border-radius: 6px;
  color: #3154e8;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.interval-limit-trigger:hover,
.interval-limit-trigger:focus-visible {
  border-color: #3154e8;
  outline: none;
}

.interval-limit-trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.interval-limit-panel {
  display: grid;
  grid-template-columns: 142px 1fr;
  min-height: 170px;
  color: #303643;
}

.interval-limit-menu {
  padding: 6px;
  border-right: 1px solid #edf0f5;
}

.interval-limit-current {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 8px;
  color: #3154e8;
  font-weight: 600;
}

.interval-limit-current .el-icon {
  color: #6f7785;
  cursor: help;
}

.interval-limit-menu button,
.interval-limit-values button {
  width: 100%;
  height: 34px;
  padding: 0 8px;
  border: 0;
  border-radius: 5px;
  color: #4b515c;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}

.interval-limit-menu button {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.interval-limit-menu button:hover,
.interval-limit-menu button.is-active,
.interval-limit-values button:hover,
.interval-limit-values button.is-active {
  border-color: #3154e8;
  color: #3154e8;
  background: #f0f2f8;
}

.interval-limit-values {
  padding: 38px 8px 8px;
}

.interval-limit-custom {
  display: grid;
  grid-template-columns: 64px auto;
  align-items: center;
  justify-content: start;
  gap: 8px;
  margin: 5px 8px 0;
  color: #4b515c;
  font-size: 13px;
}

.interval-limit-custom :deep(.ed-input-number),
.interval-limit-custom :deep(.el-input-number) {
  width: 64px;
  min-width: 0;
}

.interval-limit-custom :deep(.ed-input__wrapper),
.interval-limit-custom :deep(.el-input__wrapper) {
  min-height: 28px;
  border-radius: 6px;
  box-shadow: 0 0 0 1px #dfe3ea inset;
}

:global(.interval-limit-popper) {
  max-width: calc(100vw - 24px);
  padding: 0 !important;
  overflow: hidden;
}

@media (max-width: 420px) {
  .interval-limit-panel {
    grid-template-columns: 132px minmax(120px, 1fr);
  }
}
</style>
