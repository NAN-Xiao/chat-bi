<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus-secondary'
import {
  formatFunnelWindow,
  maxFunnelWindowValue,
  normalizeFunnelWindow,
  type FunnelWindowConfig,
  type FunnelWindowUnit,
} from './funnelAnalysis'

const props = defineProps<{
  modelValue: FunnelWindowConfig
  disabled?: boolean
}>()

const emits = defineEmits<{
  'update:modelValue': [value: FunnelWindowConfig]
}>()

const visible = ref(false)
const selectedUnit = ref<FunnelWindowUnit>('day')
const draftValue = ref(1)
const unitOptions: Array<{ label: string; value: FunnelWindowUnit }> = [
  { label: '天（即24小时）', value: 'day' },
  { label: '小时', value: 'hour' },
  { label: '分钟', value: 'minute' },
]
const presets: Record<FunnelWindowUnit, number[]> = {
  day: [1, 7, 14],
  hour: [1, 6, 12],
  minute: [1, 15, 30],
}

const normalizedValue = computed(() => normalizeFunnelWindow(props.modelValue))
const activeLabel = computed(() => formatFunnelWindow(normalizedValue.value))
const maxDraftValue = computed(() => maxFunnelWindowValue(selectedUnit.value))

function syncDraft() {
  const current = normalizedValue.value
  if (current.mode === 'duration') {
    selectedUnit.value = current.unit
    draftValue.value = current.value
  } else {
    selectedUnit.value = 'day'
    draftValue.value = 1
  }
}

watch(visible, (next) => {
  if (next) syncDraft()
})

function selectSameDay() {
  emits('update:modelValue', { mode: 'same_day', value: 1, unit: 'day' })
  visible.value = false
}

function selectUnit(unit: FunnelWindowUnit) {
  selectedUnit.value = unit
  const current = normalizedValue.value
  draftValue.value = current.mode === 'duration' && current.unit === unit ? current.value : presets[unit][0]
}

function selectPreset(value: number) {
  emits('update:modelValue', { mode: 'duration', value, unit: selectedUnit.value })
  visible.value = false
}

function applyCustomValue() {
  const value = Number(draftValue.value)
  if (!Number.isInteger(value) || value < 1 || value > maxDraftValue.value) {
    ElMessage.warning('漏斗分析窗口期必须在 1 分钟到 365 天之间。')
    syncDraft()
    return
  }
  emits('update:modelValue', { mode: 'duration', value, unit: selectedUnit.value })
}

function isPresetActive(value: number) {
  const current = normalizedValue.value
  return current.mode === 'duration' && current.unit === selectedUnit.value && current.value === value
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="304"
    trigger="click"
    popper-class="funnel-window-popper"
    :teleported="false"
  >
    <template #reference>
      <button
        type="button"
        class="funnel-window-trigger"
        :disabled="disabled"
        aria-label="设置漏斗分析窗口期"
        title="设置漏斗分析窗口期"
      >
        <span>{{ activeLabel }}</span>
        <el-icon><ArrowDown /></el-icon>
      </button>
    </template>

    <div class="funnel-window-panel">
      <div class="funnel-window-menu">
        <div class="funnel-window-current">
          <span>{{ activeLabel }}</span>
          <el-tooltip content="限制同一分析主体完成全部漏斗步骤的最长时间。" placement="top">
            <el-icon aria-label="分析窗口期说明"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
        <button
          type="button"
          :class="{ 'is-active': normalizedValue.mode === 'same_day' }"
          @click="selectSameDay"
        >
          <span>当天</span>
        </button>
        <button
          v-for="unit in unitOptions"
          :key="unit.value"
          type="button"
          :class="{ 'is-active': normalizedValue.mode === 'duration' && selectedUnit === unit.value }"
          @click="selectUnit(unit.value)"
        >
          <span>{{ unit.label }}</span>
          <el-icon><ArrowRight /></el-icon>
        </button>
      </div>

      <div class="funnel-window-values">
        <button
          v-for="value in presets[selectedUnit]"
          :key="value"
          type="button"
          :class="{ 'is-active': isPresetActive(value) }"
          @click="selectPreset(value)"
        >
          {{ value }}{{ selectedUnit === 'day' ? '天' : selectedUnit === 'hour' ? '小时' : '分钟' }}
        </button>
        <div class="funnel-window-custom">
          <el-input-number
            v-model="draftValue"
            :min="1"
            :max="maxDraftValue"
            :precision="0"
            :controls="false"
            aria-label="自定义漏斗分析窗口数值"
            @change="applyCustomValue"
            @keydown.enter.stop="applyCustomValue"
          />
          <span>{{ selectedUnit === 'day' ? '天' : selectedUnit === 'hour' ? '小时' : '分钟' }}</span>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.funnel-window-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 7px;
  min-width: 58px;
  height: 30px;
  padding: 0 9px;
  border: 1px solid #8aa0ff;
  border-radius: 6px;
  color: #3154e8;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.funnel-window-trigger:hover,
.funnel-window-trigger:focus-visible {
  border-color: #3154e8;
  outline: none;
}

.funnel-window-trigger:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.funnel-window-panel {
  display: grid;
  grid-template-columns: 142px 1fr;
  min-height: 188px;
  color: #303643;
}

.funnel-window-menu {
  padding: 6px;
  border-right: 1px solid #edf0f5;
}

.funnel-window-current {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  padding: 0 8px;
  color: #3154e8;
  font-weight: 600;
}

.funnel-window-current .el-icon {
  color: #6f7785;
  cursor: help;
}

.funnel-window-menu button,
.funnel-window-values button {
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

.funnel-window-menu button {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.funnel-window-menu button:hover,
.funnel-window-menu button.is-active,
.funnel-window-values button:hover,
.funnel-window-values button.is-active {
  color: #3154e8;
  background: #f0f2f8;
}

.funnel-window-values {
  padding: 38px 8px 8px;
}

.funnel-window-custom {
  display: grid;
  grid-template-columns: 64px auto;
  align-items: center;
  justify-content: start;
  gap: 8px;
  margin: 5px 8px 0;
  color: #4b515c;
  font-size: 13px;
}

.funnel-window-custom :deep(.ed-input-number),
.funnel-window-custom :deep(.el-input-number) {
  width: 64px;
  min-width: 0;
}

.funnel-window-custom :deep(.ed-input__wrapper),
.funnel-window-custom :deep(.el-input__wrapper) {
  min-height: 28px;
  border-radius: 6px;
  box-shadow: 0 0 0 1px #dfe3ea inset;
}

:global(.funnel-window-popper) {
  max-width: calc(100vw - 24px);
  padding: 0 !important;
  overflow: hidden;
}

@media (max-width: 420px) {
  .funnel-window-panel {
    grid-template-columns: 132px minmax(120px, 1fr);
  }
}
</style>
