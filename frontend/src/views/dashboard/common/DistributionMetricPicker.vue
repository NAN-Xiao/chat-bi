<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FieldOption } from './builderFieldPickerOptions'
import { fieldOptionDisplayName } from './builderFieldPickerOptions'
import type {
  DistributionMetricConfig,
  DistributionMetricKind,
  DistributionPropertyAggregation,
} from './distributionAnalysis'

const props = withDefaults(defineProps<{
  modelValue: DistributionMetricConfig
  eventLabel?: string
  propertyOptions: FieldOption[]
  loading?: boolean
  disabled?: boolean
}>(), {
  eventLabel: '参与事件',
  loading: false,
  disabled: false,
})

const emits = defineEmits<{
  'update:modelValue': [value: DistributionMetricConfig]
}>()

const visible = ref(false)
const draft = ref<DistributionMetricConfig>({ kind: 'count', field: '', aggregation: 'sum' })

const presetOptions = [
  { label: '次数', value: 'count' as DistributionMetricKind },
  { label: '天数', value: 'days' as DistributionMetricKind },
  { label: '小时数', value: 'hours' as DistributionMetricKind },
]

const aggregationOptions: Array<{ label: string; value: DistributionPropertyAggregation }> = [
  { label: '总和', value: 'sum' },
  { label: '均值', value: 'avg' },
  { label: '中位数', value: 'median' },
  { label: '最大值', value: 'max' },
  { label: '最小值', value: 'min' },
  { label: '去重数', value: 'count_distinct' },
  { label: '方差', value: 'variance' },
  { label: '标准差', value: 'stddev' },
  { label: '99分位数', value: 'percentile_99' },
  { label: '95分位数', value: 'percentile_95' },
  { label: '90分位数', value: 'percentile_90' },
  { label: '80分位数', value: 'percentile_80' },
  { label: '75分位数', value: 'percentile_75' },
  { label: '70分位数', value: 'percentile_70' },
  { label: '60分位数', value: 'percentile_60' },
  { label: '40分位数', value: 'percentile_40' },
  { label: '30分位数', value: 'percentile_30' },
  { label: '25分位数', value: 'percentile_25' },
  { label: '20分位数', value: 'percentile_20' },
  { label: '10分位数', value: 'percentile_10' },
  { label: '5分位数', value: 'percentile_05' },
]

const selectableProperties = computed(() => props.propertyOptions.filter((item) => item.value && item.kind !== 'tracking-event'))
const selectedProperty = computed(() => selectableProperties.value.find((item) => item.value === props.modelValue.field))
const selectedAggregationLabel = computed(() => (
  aggregationOptions.find((item) => item.value === props.modelValue.aggregation)?.label || '总和'
))
const displayLabel = computed(() => {
  const preset = presetOptions.find((item) => item.value === props.modelValue.kind)
  if (preset) return preset.label
  const fieldLabel = fieldOptionDisplayName(selectedProperty.value, props.modelValue.field) || '选择事件属性'
  return `${fieldLabel}.${selectedAggregationLabel.value}`
})

watch(visible, (next) => {
  if (!next) return
  draft.value = {
    kind: props.modelValue.kind || 'count',
    field: props.modelValue.field || '',
    aggregation: props.modelValue.aggregation || 'sum',
  }
})

function choosePreset(kind: DistributionMetricKind) {
  emits('update:modelValue', { kind, field: '', aggregation: 'sum' })
  visible.value = false
}

function applyPropertyMetric() {
  if (!draft.value.field) return
  emits('update:modelValue', {
    kind: 'property',
    field: draft.value.field,
    aggregation: draft.value.aggregation,
  })
  visible.value = false
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="440"
    trigger="click"
    popper-class="distribution-metric-popper"
  >
    <template #reference>
      <button
        type="button"
        class="distribution-metric-trigger"
        :disabled="disabled"
        :title="displayLabel"
        aria-label="选择分布指标"
      >
        <span>{{ displayLabel }}</span>
      </button>
    </template>

    <div class="distribution-metric-panel">
      <div class="distribution-metric-sentence">
        <span>将</span>
        <strong>{{ eventLabel }}</strong>
        <span>的</span>
      </div>
      <div class="distribution-preset-list" aria-label="预置计算方法">
        <span class="distribution-option-heading">预置计算方法</span>
        <button
          v-for="option in presetOptions"
          :key="option.value"
          type="button"
          class="distribution-preset-option"
          :class="{ 'is-active': modelValue.kind === option.value }"
          @click="choosePreset(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
      <div class="distribution-property-metric">
        <span class="distribution-option-heading">事件属性指标</span>
        <div class="distribution-property-flow">
          <el-select
            v-model="draft.field"
            filterable
            clearable
            :teleported="false"
            :loading="loading"
            placeholder="选择事件属性"
            aria-label="分布事件属性"
          >
            <el-option
              v-for="option in selectableProperties"
              :key="option.value"
              :label="fieldOptionDisplayName(option)"
              :value="option.value"
            />
          </el-select>
          <span>的</span>
          <el-select
            v-model="draft.aggregation"
            filterable
            :teleported="false"
            aria-label="分布属性聚合方式"
          >
            <el-option
              v-for="option in aggregationOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <span>作为指标</span>
        </div>
      </div>
      <div class="distribution-metric-actions">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :disabled="!draft.field" @click="applyPropertyMetric">应用</el-button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.distribution-metric-trigger {
  max-width: 260px;
  min-height: 30px;
  padding: 4px 10px;
  overflow: hidden;
  border: 1px solid #e1e4ea;
  border-radius: 6px;
  color: #303643;
  background: #f5f6f8;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.distribution-metric-trigger:hover,
.distribution-metric-trigger:focus-visible {
  border-color: #3154e8;
  background: #fff;
}

.distribution-metric-trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.distribution-metric-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: #303643;
}

.distribution-metric-sentence {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.distribution-preset-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.distribution-option-heading {
  grid-column: 1 / -1;
  color: #8a93a3;
  font-size: 12px;
}

.distribution-preset-option {
  min-height: 34px;
  border: 1px solid #e1e4ea;
  border-radius: 6px;
  color: #505968;
  background: #fff;
  cursor: pointer;
}

.distribution-preset-option:hover,
.distribution-preset-option.is-active {
  border-color: #3154e8;
  color: #3154e8;
  background: #f4f6ff;
}

.distribution-property-metric {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.distribution-property-flow {
  display: grid;
  grid-template-columns: minmax(140px, 1.2fr) auto minmax(120px, 0.8fr) auto;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.distribution-metric-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

:global(.distribution-metric-popper) {
  max-width: calc(100vw - 24px);
}

@media (max-width: 520px) {
  .distribution-property-flow {
    grid-template-columns: 1fr;
  }
}
</style>
