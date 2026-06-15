<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import icon_dashboard from '@/assets/svg/dashboard.svg'
import icon_chart_preview from '@/assets/svg/icon_chart_preview.svg'
import icon_into_item_outlined from '@/assets/svg/icon_into-item_outlined.svg'
import icon_window_max_outlined from '@/assets/svg/icon_window-max_outlined.svg'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import { dashboardApi } from '@/api/dashboard'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  item: Record<string, any>
  useLoading?: boolean
}>()

const emits = defineEmits<{
  (e: 'preview', item: Record<string, any>): void
  (e: 'use', item: Record<string, any>): void
}>()

const { t } = useI18n()

const chartLoading = ref(false)
const chartInfo = ref<Record<string, any> | null>(null)

const parseJson = (value: any, fallback: any) => {
  if (!value) return fallback
  try {
    return JSON.parse(value)
  } catch (error) {
    console.error(error)
    return fallback
  }
}

const loadChartPreview = async () => {
  if (props.item.share_type !== 'chart' || !props.item.can_use) return
  chartLoading.value = true
  try {
    const res = await dashboardApi.share_load({ id: props.item.id })
    const componentData = parseJson(res.component_data, [])
    const canvasViewInfo = parseJson(res.canvas_view_info, {})
    const componentId = componentData[0]?.id || res.source_view_id || props.item.source_view_id
    chartInfo.value = componentId ? canvasViewInfo?.[componentId] || null : null
  } finally {
    chartLoading.value = false
  }
}

const typeText = computed(() =>
  props.item.share_type === 'chart' ? t('dashboard.shared_chart') : t('dashboard.shared_dashboard')
)

const statusText = computed(() =>
  props.item.can_use
    ? t('dashboard.store_status_available_short')
    : t('dashboard.store_status_restricted_short')
)

const showChartPreview = computed(() => {
  return (
    props.item.share_type === 'chart' &&
    !!chartInfo.value?.chart &&
    Array.isArray(chartInfo.value?.data?.data)
  )
})

onMounted(() => {
  loadChartPreview()
})
</script>

<template>
  <div class="card">
    <div class="preview-shell">
      <template v-if="item.share_type === 'chart'">
        <div v-if="chartLoading" class="preview-placeholder">
          <img :src="icon_chart_preview" width="44" height="44" />
          <div class="placeholder-text">{{ t('qa.loading') }}</div>
        </div>
        <ChartComponent
          v-else-if="showChartPreview"
          :id="`store-${item.id}`"
          :key="`store-${item.id}`"
          :type="chartInfo?.chart?.type || 'table'"
          :columns="chartInfo?.chart?.columns || []"
          :x="chartInfo?.chart?.xAxis || []"
          :y="chartInfo?.chart?.yAxis || []"
          :series="chartInfo?.chart?.series || []"
          :data="chartInfo?.data?.data || []"
          :multi-quota-name="chartInfo?.chart?.multiQuotaName"
        />
        <div v-else class="preview-placeholder">
          <img :src="icon_chart_preview" width="44" height="44" />
          <div class="placeholder-text">
            {{
              item.can_use
                ? t('dashboard.store_chart_preview_empty')
                : t('dashboard.store_no_preview_permission')
            }}
          </div>
        </div>
      </template>
      <div v-else class="dashboard-cover">
        <img :src="icon_dashboard" width="60" height="60" />
        <div class="cover-title">{{ t('dashboard.shared_dashboard') }}</div>
      </div>
    </div>

    <div class="card-body">
      <div class="meta-row">
        <span class="type-tag">{{ typeText }}</span>
        <span class="status-pill">
          <span class="status-dot" :class="item.can_use ? 'status-green' : 'status-red'"></span>
          {{ statusText }}
        </span>
      </div>

      <div class="name ellipsis" :title="item.name">{{ item.name }}</div>

      <div class="info-row">
        <span class="label">{{ t('dashboard.store_datasource') }}</span>
        <span class="value ellipsis" :title="item.datasource_name || '-'">
          {{ item.datasource_name || '-' }}
        </span>
      </div>
    </div>

    <div class="card-actions">
      <el-button secondary @click="emits('preview', item)">
        <template #icon>
          <icon_window_max_outlined />
        </template>
        {{ t('dashboard.preview') }}
      </el-button>
      <el-button
        type="primary"
        :disabled="!item.can_use"
        :loading="useLoading"
        @click="emits('use', item)"
      >
        <template #icon>
          <icon_into_item_outlined />
        </template>
        {{ t('dashboard.store_add') }}
      </el-button>
    </div>
  </div>
</template>

<style scoped lang="less">
.card {
  width: 100%;
  border: 1px solid #dee0e3;
  border-radius: 12px;
  background: #fff;
  overflow: hidden;

  &:hover {
    box-shadow: 0px 6px 24px 0px #1f232914;
  }
}

.preview-shell {
  height: 216px;
  padding: 12px;
  border-bottom: 1px solid #eff0f1;
  background: linear-gradient(180deg, #f7f9fc 0%, #eef2f7 100%);
}

.dashboard-cover,
.preview-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #646a73;
  text-align: center;
}

.cover-title,
.placeholder-text {
  margin-top: 12px;
  font-size: 14px;
  line-height: 22px;
}

.card-body {
  padding: 16px 16px 12px;
}

.meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.type-tag {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: #2563eb;
  font-size: 12px;
  line-height: 20px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #646a73;
  font-size: 12px;
  line-height: 20px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.status-green {
  background: #22c55e;
}

.status-red {
  background: #ef4444;
}

.name {
  margin-top: 12px;
  font-weight: 500;
  font-size: 16px;
  line-height: 24px;
}

.info-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  line-height: 20px;

  .label {
    color: #646a73;
    flex: 0 0 auto;
  }

  .value {
    color: #1f2329;
    min-width: 0;
  }
}

.card-actions {
  display: flex;
  gap: 12px;
  padding: 0 16px 16px;

  .ed-button {
    flex: 1;
  }
}
</style>
