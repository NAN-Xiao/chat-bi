<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
const draftUnit = ref<DurationUnit>('hour')
const draftValue = ref(1)
const presets = [
  { label: '1小时', value: 3600 },
  { label: '3小时', value: 10800 },
  { label: '12小时', value: 43200 },
]
const unitOptions: Array<{ label: string; value: DurationUnit; seconds: number }> = [
  { label: '天（即24小时）', value: 'day', seconds: 86400 },
  { label: '小时', value: 'hour', seconds: 3600 },
  { label: '分钟', value: 'minute', seconds: 60 },
]

const activeLabel = computed(() => formatIntervalLimit(props.modelValue || DEFAULT_INTERVAL_LIMIT_SECONDS))
const draftSeconds = computed(() => {
  const unit = unitOptions.find((item) => item.value === draftUnit.value) || unitOptions[1]
  return Number(draftValue.value) * unit.seconds
})
const maxDraftValue = computed(() => {
  const unit = unitOptions.find((item) => item.value === draftUnit.value) || unitOptions[1]
  return Math.floor(INTERVAL_LIMIT_MAX_SECONDS / unit.seconds)
})

function resetDraft() {
  const seconds = clampIntervalLimitSeconds(props.modelValue)
  if (seconds % 86400 === 0) {
    draftUnit.value = 'day'
    draftValue.value = seconds / 86400
  } else if (seconds % 3600 === 0) {
    draftUnit.value = 'hour'
    draftValue.value = seconds / 3600
  } else {
    draftUnit.value = 'minute'
    draftValue.value = Math.max(1, Math.round(seconds / 60))
  }
}

watch(visible, (next) => {
  if (next) resetDraft()
})

function selectPreset(value: number) {
  emits('update:modelValue', value)
  visible.value = false
}

function applyCustomLimit() {
  if (!Number.isFinite(draftSeconds.value)
    || draftSeconds.value < INTERVAL_LIMIT_MIN_SECONDS
    || draftSeconds.value > INTERVAL_LIMIT_MAX_SECONDS) {
    ElMessage.warning('间隔上限必须在 1 分钟到 180 天之间。')
    return
  }
  emits('update:modelValue', clampIntervalLimitSeconds(draftSeconds.value))
  visible.value = false
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="360"
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
      <div class="interval-limit-title">间隔上限</div>
      <div class="interval-limit-presets" aria-label="快捷间隔上限">
        <button
          v-for="preset in presets"
          :key="preset.value"
          type="button"
          :class="{ 'is-active': modelValue === preset.value }"
          @click="selectPreset(preset.value)"
        >
          {{ preset.label }}
        </button>
      </div>
      <div class="interval-limit-custom">
        <el-input-number
          v-model="draftValue"
          :min="1"
          :max="maxDraftValue"
          :precision="0"
          controls-position="right"
          aria-label="自定义间隔数值"
          @keydown.stop
        />
        <el-select v-model="draftUnit" aria-label="自定义间隔单位">
          <el-option
            v-for="unit in unitOptions"
            :key="unit.value"
            :label="unit.label"
            :value="unit.value"
          />
        </el-select>
      </div>
      <p>可设置 1 分钟到 180 天，超过上限的间隔不参与统计。</p>
      <div class="interval-limit-actions">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="applyCustomLimit">应用</el-button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.interval-limit-trigger {
  min-width: 64px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #3154e8;
  background: #f3f5fb;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}

.interval-limit-trigger:hover,
.interval-limit-trigger:focus-visible {
  border-color: #3154e8;
  background: #fff;
}

.interval-limit-trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.interval-limit-panel {
  color: #303643;
}

.interval-limit-title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
}

.interval-limit-presets {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.interval-limit-presets button {
  height: 32px;
  border: 1px solid #e2e5ea;
  border-radius: 5px;
  color: #4b5563;
  background: #fff;
  cursor: pointer;
}

.interval-limit-presets button:hover,
.interval-limit-presets button.is-active {
  border-color: #3154e8;
  color: #3154e8;
  background: #f5f7ff;
}

.interval-limit-custom {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(130px, 1fr);
  gap: 8px;
  margin-top: 14px;
}

.interval-limit-custom :deep(.el-input-number),
.interval-limit-custom :deep(.el-select) {
  width: 100%;
}

.interval-limit-panel p {
  margin: 10px 0 0;
  color: #8a93a3;
  font-size: 12px;
  line-height: 1.6;
}

.interval-limit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

:global(.interval-limit-popper) {
  max-width: calc(100vw - 24px);
}

@media (max-width: 480px) {
  .interval-limit-custom {
    grid-template-columns: 1fr;
  }
}
</style>
