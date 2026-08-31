<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDown, Search } from '@element-plus/icons-vue'
import {
  REVENUE_METRIC_OPTIONS,
  revenueMetricLabel,
  type RevenueMetricConfig,
  type RevenueMetricMethod,
} from './revenueAnalysis'

const props = defineProps<{
  modelValue: RevenueMetricConfig
  disabled?: boolean
}>()

const emits = defineEmits<{
  'update:modelValue': [value: RevenueMetricConfig]
}>()

const visible = ref(false)
const keyword = ref('')
const activeLabel = computed(() => revenueMetricLabel(props.modelValue.method))
const filteredOptions = computed(() => {
  const normalized = keyword.value.trim().toLowerCase()
  return normalized
    ? REVENUE_METRIC_OPTIONS.filter((option) => option.label.toLowerCase().includes(normalized))
    : REVENUE_METRIC_OPTIONS
})

watch(visible, (next) => {
  if (!next) keyword.value = ''
})

function chooseMethod(method: RevenueMetricMethod) {
  emits('update:modelValue', {
    method,
    field: method === 'property_sum' || method === 'property_avg' ? props.modelValue.field : '',
  })
  visible.value = false
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="286"
    trigger="click"
    popper-class="revenue-metric-popper"
    :teleported="false"
  >
    <template #reference>
      <button
        type="button"
        class="revenue-metric-trigger"
        :disabled="disabled"
        aria-label="选择收入口径"
        title="选择收入口径"
      >
        <span>{{ activeLabel }}</span>
        <el-icon><ArrowDown /></el-icon>
      </button>
    </template>

    <div class="revenue-metric-panel">
      <div class="revenue-metric-search">
        <el-icon><Search /></el-icon>
        <input v-model="keyword" type="search" placeholder="请输入搜索" aria-label="搜索收入口径" />
      </div>
      <div class="revenue-metric-group-title">预置计算方法</div>
      <div class="revenue-metric-list">
        <button
          v-for="option in filteredOptions"
          :key="option.value"
          type="button"
          :class="{ 'is-active': option.value === modelValue.method }"
          @click="chooseMethod(option.value)"
        >
          {{ option.label }}
        </button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.revenue-metric-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 82px;
  max-width: 230px;
  height: 30px;
  padding: 0 9px;
  border: 1px solid #8aa0ff;
  border-radius: 6px;
  color: #3154e8;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}

.revenue-metric-trigger span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.revenue-metric-trigger:hover,
.revenue-metric-trigger:focus-visible {
  border-color: #3154e8;
  outline: none;
}

.revenue-metric-trigger:disabled {
  opacity: .45;
  cursor: not-allowed;
}

.revenue-metric-panel {
  color: #303643;
}

.revenue-metric-search {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: center;
  gap: 4px;
  height: 38px;
  padding: 0 10px;
  border-bottom: 1px solid #edf0f5;
  color: #8b94a2;
}

.revenue-metric-search input {
  min-width: 0;
  border: 0;
  outline: 0;
  color: #303643;
  background: transparent;
  font: inherit;
}

.revenue-metric-search input::placeholder {
  color: #b3bac5;
}

.revenue-metric-group-title {
  padding: 9px 12px 5px;
  color: #8b94a2;
  font-size: 12px;
}

.revenue-metric-list {
  max-height: 248px;
  padding: 0 6px 6px;
  overflow: auto;
}

.revenue-metric-list button {
  width: 100%;
  min-height: 36px;
  padding: 7px 10px;
  border: 0;
  border-radius: 6px;
  color: #3e4653;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  text-align: left;
}

.revenue-metric-list button:hover,
.revenue-metric-list button.is-active {
  color: #273eac;
  background: #f0f2f8;
}

:global(.revenue-metric-popper) {
  max-width: calc(100vw - 24px);
  padding: 0 !important;
  overflow: hidden;
}
</style>
