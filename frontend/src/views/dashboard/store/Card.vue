<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import iconDashboardUrl from '@/assets/svg/dashboard.svg?url'
import iconChartPreviewUrl from '@/assets/svg/icon_chart_preview.svg?url'
import icon_delete from '@/assets/svg/icon_delete.svg'
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
  (e: 'delete', item: Record<string, any>): void
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
  if (props.item.preview_image || props.item.share_type !== 'chart' || !props.item.can_use) return
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
    !props.item.preview_image &&
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
      <img
        v-if="item.preview_image"
        class="preview-image"
        :src="item.preview_image"
        :alt="item.name"
      />
      <template v-else-if="item.share_type === 'chart'">
        <div v-if="chartLoading" class="preview-placeholder">
          <img :src="iconChartPreviewUrl" width="44" height="44" />
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
          <img :src="iconChartPreviewUrl" width="44" height="44" />
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
        <img :src="iconDashboardUrl" width="60" height="60" />
        <div class="cover-title">{{ t('dashboard.shared_dashboard') }}</div>
      </div>
    </div>

    <div class="card-body">
      <div class="meta-row">
        <span class="type-tag">{{ typeText }}</span>
        <el-tooltip
          v-if="item.can_delete"
          :content="t('dashboard.cancel_share')"
          placement="top"
        >
          <button
            type="button"
            class="delete-action"
            @click.stop="emits('delete', item)"
          >
            <icon_delete />
          </button>
        </el-tooltip>
      </div>

      <div class="name ellipsis" :title="item.name">{{ item.name }}</div>

      <div class="info-row">
        <span class="label">{{ t('dashboard.store_datasource') }}</span>
        <span class="value ellipsis" :title="item.datasource_name || '-'">
          {{ item.datasource_name || '-' }}
        </span>
        <span class="status-pill">
          <span class="status-dot" :class="item.can_use ? 'status-green' : 'status-red'"></span>
          {{ statusText }}
        </span>
      </div>
    </div>

    <div class="card-actions">
      <div class="primary-actions">
        <el-tooltip :content="t('dashboard.preview')" placement="top">
          <el-button class="preview-action" secondary @click="emits('preview', item)">
            <template #icon>
              <icon_window_max_outlined />
            </template>
          </el-button>
        </el-tooltip>
        <el-button
          class="use-action"
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
  </div>
</template>

<style scoped lang="less">
.card {
  width: 100%;
  border: 1px solid #dee0e3;
  border-radius: 8px;
  background: #fff;
  overflow: hidden;
  box-shadow: 1px 5px 14px rgba(31, 35, 41, 0.08);
  transition: box-shadow 0.12s ease, transform 0.12s ease;

  &:hover {
    box-shadow: 3px 8px 24px rgba(31, 35, 41, 0.13);
    transform: translateY(-2px) scale(1.012);
  }
}

.preview-shell {
  position: relative;
  height: 204px;
  padding: 12px;
  border-bottom: 1px solid #eff0f1;
  background: linear-gradient(180deg, #f7f9fc 0%, #eef2f7 100%);
}

.preview-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  border-radius: 6px;
  background: #fff;
}

.delete-action.delete-action {
  width: 24px;
  height: 20px;
  padding: 0;
  border: none;
  outline: none;
  background: transparent;
  color: #646a73;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;

  :deep(svg) {
    width: 16px;
    height: 16px;
  }

  :deep(path) {
    fill: #a8b0bb;
  }

  &:hover {
    :deep(path) {
      fill: #d84b4b;
    }
  }
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
  margin-top: 8px;
  font-size: 13px;
  line-height: 20px;
}

.card-body {
  padding: 14px 14px 12px;
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
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  color: #2563eb;
  font-size: 12px;
  line-height: 18px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #646a73;
  font-size: 12px;
  line-height: 18px;
}

.status-dot {
  width: 7px;
  height: 7px;
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
  margin-top: 10px;
  font-weight: 500;
  font-size: 15px;
  line-height: 24px;
}

.info-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  line-height: 18px;

  .label {
    color: #646a73;
    flex: 0 0 auto;
  }

  .value {
    color: #1f2329;
    flex: 1 1 auto;
    min-width: 0;
  }

  .status-pill {
    margin-left: auto;
    flex: 0 0 auto;
  }
}

.card-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 14px 14px;

  .ed-button {
    min-width: 0;
    margin-left: 0;
    padding-left: 10px;
    padding-right: 10px;
  }
}

.primary-actions {
  display: flex;
  gap: 10px;
}

.preview-action {
  flex: 0 0 40px;
  width: 40px;
  padding-left: 0 !important;
  padding-right: 0 !important;
}

.use-action {
  flex: 1;
}
</style>
