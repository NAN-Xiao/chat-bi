<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { DistributionIntervalConfig, DistributionIntervalMode } from './distributionAnalysis'

const props = defineProps<{
  modelValue: DistributionIntervalConfig
  disabled?: boolean
  discreteOnly?: boolean
}>()

const emits = defineEmits<{
  'update:modelValue': [value: DistributionIntervalConfig]
}>()

const visible = ref(false)
const draftMode = ref<DistributionIntervalMode>('auto')
const customBoundsText = ref('')

const tabs: Array<{ label: string; value: DistributionIntervalMode }> = [
  { label: '默认区间', value: 'auto' },
  { label: '离散数字', value: 'discrete' },
  { label: '自定义区间', value: 'custom' },
]

const visibleTabs = computed(() => (
  props.discreteOnly ? tabs.filter((item) => item.value === 'discrete') : tabs
))
const activeLabel = computed(() => (
  visibleTabs.value.find((item) => item.value === props.modelValue.mode)?.label
    || (props.discreteOnly ? '离散数字' : '默认区间')
))

function resetDraft() {
  draftMode.value = props.discreteOnly ? 'discrete' : (props.modelValue.mode || 'auto')
  customBoundsText.value = (props.modelValue.customBounds || []).join(', ')
}

watch(visible, (next) => {
  if (next) resetDraft()
})

function parseCustomBounds() {
  const tokens = customBoundsText.value
    .split(/[，,\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
  const bounds = tokens.map(Number)
  if (bounds.length < 2 || bounds.length > 20 || bounds.some((value) => !Number.isFinite(value))) {
    return null
  }
  if (bounds.some((value, index) => index > 0 && value <= bounds[index - 1])) {
    return null
  }
  return bounds
}

function applySettings() {
  const customBounds = draftMode.value === 'custom' ? parseCustomBounds() : []
  if (draftMode.value === 'custom' && !customBounds) {
    ElMessage.warning('请输入 2 到 20 个严格递增的数字边界。')
    return
  }
  emits('update:modelValue', {
    mode: draftMode.value,
    customBounds: customBounds || [],
  })
  visible.value = false
}
</script>

<template>
  <el-popover
    v-model:visible="visible"
    placement="bottom-start"
    :width="420"
    trigger="click"
    popper-class="distribution-interval-popper"
  >
    <template #reference>
      <button
        type="button"
        class="distribution-settings-trigger"
        :class="{ 'is-customized': modelValue.mode !== 'auto' }"
        :disabled="disabled"
        :title="`区间设置：${activeLabel}`"
        aria-label="设置分布区间"
      >
        <el-icon><Setting /></el-icon>
      </button>
    </template>

    <div class="distribution-interval-settings">
      <div class="distribution-interval-tabs" role="tablist" aria-label="分布区间模式">
        <button
          v-for="tab in visibleTabs"
          :key="tab.value"
          type="button"
          role="tab"
          class="distribution-interval-tab"
          :class="{ 'is-active': draftMode === tab.value }"
          :aria-selected="draftMode === tab.value"
          @click="draftMode = tab.value"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="distribution-interval-body">
        <template v-if="draftMode === 'auto'">
          <p>区间数根据最大值与最小值的差值而定：</p>
          <p>当差值 &lt; 12 时，自动转化为离散数字；</p>
          <p>当差值 ≥ 12 时，自动划分为 12 个等宽区间。</p>
        </template>
        <template v-else-if="draftMode === 'discrete'">
          <p>每个不同的聚合结果作为一个独立区间。</p>
          <p>适合取值数量较少、需要逐值查看主体数量和占比的场景。</p>
        </template>
        <template v-else>
          <label class="distribution-custom-label" for="distribution-custom-bounds">区间边界</label>
          <el-input
            id="distribution-custom-bounds"
            v-model="customBoundsText"
            placeholder="例如 0, 1, 5, 10, 50"
            clearable
            @keydown.stop
            @keyup.stop
          />
          <p>相邻数字组成一个区间，并自动保留低于首边界和高于末边界的数据。</p>
        </template>
      </div>

      <div class="distribution-interval-actions">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="applySettings">应用</el-button>
      </div>
    </div>
  </el-popover>
</template>

<style scoped>
.distribution-settings-trigger {
  width: 30px;
  height: 30px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #6b7280;
  background: #f5f6f8;
  cursor: pointer;
}

.distribution-settings-trigger:hover,
.distribution-settings-trigger:focus-visible,
.distribution-settings-trigger.is-customized {
  border-color: #3b5bff;
  color: #3154e8;
  background: #fff;
}

.distribution-settings-trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.distribution-interval-settings {
  color: #303643;
}

.distribution-interval-tabs {
  display: flex;
  gap: 22px;
  border-bottom: 1px solid #e5e7eb;
}

.distribution-interval-tab {
  position: relative;
  min-height: 40px;
  padding: 0;
  border: 0;
  color: #6b7280;
  background: transparent;
  font-size: 13px;
  cursor: pointer;
}

.distribution-interval-tab.is-active {
  color: #1f2937;
  font-weight: 600;
}

.distribution-interval-tab.is-active::after {
  position: absolute;
  right: 0;
  bottom: -1px;
  left: 0;
  height: 2px;
  background: #3154e8;
  content: '';
}

.distribution-interval-body {
  min-height: 112px;
  padding: 18px 16px;
  color: #7b8494;
  font-size: 12px;
  line-height: 1.75;
}

.distribution-interval-body p {
  margin: 0;
}

.distribution-custom-label {
  display: block;
  margin-bottom: 8px;
  color: #4b5563;
  font-weight: 600;
}

.distribution-interval-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
}

:global(.distribution-interval-popper) {
  max-width: calc(100vw - 24px);
}
</style>
