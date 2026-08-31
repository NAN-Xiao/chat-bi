<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Search } from '@element-plus/icons-vue'
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
const propertySearch = ref('')
const pendingProperty = ref('')

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

const selectableProperties = computed(() => props.propertyOptions.filter((item) => (
  item.value && item.kind !== 'tracking-event'
)))
const filteredProperties = computed(() => {
  const keyword = propertySearch.value.trim().toLocaleLowerCase()
  if (!keyword) return selectableProperties.value
  return selectableProperties.value.filter((item) => (
    fieldOptionDisplayName(item).toLocaleLowerCase().includes(keyword)
  ))
})
const selectedProperty = computed(() => selectableProperties.value.find((item) => item.value === props.modelValue.field))
const pendingPropertyOption = computed(() => selectableProperties.value.find((item) => item.value === pendingProperty.value))
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
  propertySearch.value = ''
  pendingProperty.value = props.modelValue.kind === 'property' ? props.modelValue.field : ''
})

function choosePreset(kind: DistributionMetricKind) {
  emits('update:modelValue', { kind, field: '', aggregation: 'sum' })
  visible.value = false
}

function chooseProperty(field: string) {
  pendingProperty.value = field
}

function chooseAggregation(aggregation: DistributionPropertyAggregation) {
  if (!pendingProperty.value) return
  emits('update:modelValue', {
    kind: 'property',
    field: pendingProperty.value,
    aggregation,
  })
  visible.value = false
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="320"
    trigger="click"
    popper-class="distribution-metric-popper"
    :teleported="false"
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

    <div class="distribution-metric-panel" :class="{ 'has-aggregation': pendingProperty }">
      <div class="distribution-metric-main">
        <div class="distribution-metric-sentence">
          <span>将</span>
          <strong>{{ eventLabel }}</strong>
          <span>的指标设为</span>
        </div>

        <el-input
          v-model="propertySearch"
          class="distribution-metric-search"
          clearable
          placeholder="请输入搜索"
          aria-label="搜索分布指标"
          @keydown.stop
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <div class="distribution-metric-scroll">
          <div class="distribution-metric-group">
            <span class="distribution-option-heading">预置计算方法</span>
            <button
              v-for="option in presetOptions"
              :key="option.value"
              type="button"
              class="distribution-menu-option"
              :class="{ 'is-active': modelValue.kind === option.value }"
              @click="choosePreset(option.value)"
            >
              <span>{{ option.label }}</span>
            </button>
          </div>

          <div class="distribution-metric-group distribution-property-group">
            <span class="distribution-option-heading">事件属性指标</span>
            <button
              v-for="option in filteredProperties"
              :key="option.value"
              type="button"
              class="distribution-menu-option"
              :class="{ 'is-active': pendingProperty === option.value }"
              @click="chooseProperty(option.value)"
            >
              <span>{{ fieldOptionDisplayName(option) }}</span>
              <el-icon><ArrowRight /></el-icon>
            </button>
            <span v-if="loading" class="distribution-menu-empty">正在加载属性...</span>
            <span v-else-if="!filteredProperties.length" class="distribution-menu-empty">暂无匹配属性</span>
          </div>
        </div>
      </div>

      <div v-if="pendingProperty" class="distribution-aggregation-panel">
        <span class="distribution-option-heading">{{ fieldOptionDisplayName(pendingPropertyOption) }}</span>
        <div class="distribution-aggregation-list">
          <button
            v-for="option in aggregationOptions"
            :key="option.value"
            type="button"
            class="distribution-menu-option"
            :class="{
              'is-active': modelValue.kind === 'property'
                && modelValue.field === pendingProperty
                && modelValue.aggregation === option.value,
            }"
            @click="chooseAggregation(option.value)"
          >
            <span>{{ option.label }}</span>
          </button>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.distribution-metric-trigger {
  max-width: 210px;
  min-height: 30px;
  padding: 3px 9px;
  overflow: hidden;
  border: 1px solid #8aa0ff;
  border-radius: 6px;
  color: #3154e8;
  background: #fff;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
}

.distribution-metric-trigger:hover,
.distribution-metric-trigger:focus-visible {
  border-color: #3154e8;
  outline: none;
  box-shadow: 0 0 0 2px rgb(49 84 232 / 10%);
}

.distribution-metric-trigger:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.distribution-metric-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  min-height: 250px;
  color: #303643;
}

.distribution-metric-panel.has-aggregation {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.distribution-metric-main {
  min-width: 0;
  padding: 10px 8px 8px;
}

.distribution-metric-sentence {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  padding: 0 4px 9px;
  color: #4b515c;
  font-size: 12px;
  white-space: nowrap;
}

.distribution-metric-sentence strong {
  max-width: 82px;
  overflow: hidden;
  color: #303643;
  font-weight: 600;
  text-overflow: ellipsis;
}

.distribution-metric-search :deep(.el-input__wrapper) {
  min-height: 28px;
  border-radius: 5px;
  box-shadow: 0 0 0 1px #e1e4ea inset;
}

.distribution-metric-search :deep(.el-input__inner) {
  font-size: 12px;
}

.distribution-metric-scroll {
  max-height: 302px;
  margin-top: 7px;
  overflow-y: auto;
}

.distribution-metric-group {
  display: flex;
  flex-direction: column;
  padding: 3px 0 6px;
}

.distribution-property-group {
  margin-top: 3px;
  padding-top: 9px;
  border-top: 1px solid #edf0f5;
}

.distribution-option-heading {
  display: block;
  padding: 4px 7px 5px;
  overflow: hidden;
  color: #8a93a3;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.distribution-menu-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  min-height: 34px;
  padding: 6px 8px;
  overflow: hidden;
  border: 0;
  border-radius: 5px;
  color: #303643;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}

.distribution-menu-option span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.distribution-menu-option:hover,
.distribution-menu-option.is-active {
  color: #3154e8;
  background: #f0f2f8;
}

.distribution-menu-empty {
  padding: 12px 8px;
  color: #a0a7b2;
  font-size: 12px;
  text-align: center;
}

.distribution-aggregation-panel {
  min-width: 0;
  padding: 10px 8px 8px;
  border-left: 1px solid #edf0f5;
}

.distribution-aggregation-list {
  max-height: 344px;
  overflow-y: auto;
}

:global(.distribution-metric-popper) {
  max-width: calc(100vw - 24px);
  padding: 0 !important;
  overflow: hidden;
}

</style>
