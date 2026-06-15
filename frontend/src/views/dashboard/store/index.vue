<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import iconFilter from '@/assets/svg/icon-filter_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_dashboard from '@/assets/svg/dashboard.svg'
import icon_chart_preview from '@/assets/svg/icon_chart_preview.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import Card from './Card.vue'
import { dashboardApi } from '@/api/dashboard'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const loading = ref(false)
const usingId = ref('')
const previewDialogVisible = ref(false)
const previewLoading = ref(false)
const keywords = ref('')
const currentTypeFilter = ref('')
const state = reactive({
  list: [] as any[],
  previewInfo: null as any,
  previewComponentId: '',
  previewCanvasViewInfo: {} as Record<string, any>,
})

const typeOptions = computed(() => [
  {
    label: t('dashboard.shared_dashboard'),
    value: 'dashboard',
  },
  {
    label: t('dashboard.shared_chart'),
    value: 'chart',
  },
])

const parseJson = (value: any, fallback: any) => {
  if (!value) return fallback
  try {
    return JSON.parse(value)
  } catch (error) {
    console.error(error)
    return fallback
  }
}

const filteredList = computed(() => {
  if (!currentTypeFilter.value) return state.list
  return state.list.filter((item: any) => item.share_type === currentTypeFilter.value)
})
const previewChartInfo = computed(() => {
  if (!state.previewComponentId) return null
  return state.previewCanvasViewInfo?.[state.previewComponentId] || null
})

const loadList = async () => {
  loading.value = true
  try {
    const list = await dashboardApi.share_list(
      { keyword: keywords.value },
      { requestOptions: { silent: true } }
    )
    state.list = Array.isArray(list) ? list : []
  } catch (error) {
    console.error(error)
    state.list = []
  } finally {
    loading.value = false
  }
}

const openPreview = async (item: any) => {
  previewLoading.value = true
  previewDialogVisible.value = true
  state.previewInfo = null
  state.previewComponentId = ''
  state.previewCanvasViewInfo = {}
  try {
    const res = await dashboardApi.share_load({ id: item.id })
    const componentData = parseJson(res.component_data, [])
    state.previewInfo = {
      id: res.id,
      name: res.name,
      datasourceName: item.datasource_name,
      shareType: res.share_type,
      canUse: res.can_use,
    }
    state.previewComponentId = componentData[0]?.id || res.source_view_id || item.source_view_id || ''
    state.previewCanvasViewInfo = parseJson(res.canvas_view_info, {})
  } finally {
    previewLoading.value = false
  }
}

const useSharedItem = async (item: any) => {
  if (!item.can_use || usingId.value) return
  usingId.value = item.id
  try {
    const res = await dashboardApi.share_use({ id: item.id })
    ElMessage.success(t('dashboard.store_use_success'))
    window.open(`#/canvas?resourceId=${res.id}`, '_self')
  } finally {
    usingId.value = ''
  }
}

const toggleTypeFilter = (value: string) => {
  currentTypeFilter.value = currentTypeFilter.value === value ? '' : value
}

onMounted(() => {
  loadList()
})
</script>

<template>
  <div v-loading="loading" class="datasource-config">
    <div class="datasource-methods">
      <span class="title">{{ t('dashboard.store') }}</span>
      <div class="toolbar-actions">
        <el-input
          v-model="keywords"
          clearable
          style="width: 240px"
          :placeholder="t('dashboard.store_search')"
          @change="loadList"
          @keyup.enter="loadList"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined class="svg-icon" />
            </el-icon>
          </template>
        </el-input>

        <el-popover popper-class="dashboard-store-filter-popper" placement="bottom-end" trigger="click">
          <template #reference>
            <el-button secondary :class="{ active: !!currentTypeFilter }">
              <template #icon>
                <iconFilter />
              </template>
              {{ t('user.filter') }}
            </el-button>
          </template>
          <div class="popover">
            <div
              v-for="item in typeOptions"
              :key="item.value"
              class="popover-item"
              :class="currentTypeFilter === item.value && 'isActive'"
              @click="toggleTypeFilter(item.value)"
            >
              <div class="filter-name">{{ item.label }}</div>
              <el-icon size="16" class="done">
                <icon_done_outlined />
              </el-icon>
            </div>
          </div>
        </el-popover>
      </div>
    </div>

    <EmptyBackground
      v-if="!filteredList.length"
      :description="t('dashboard.store_empty')"
      class="store-empty"
      img-type="noneWhite"
    />

    <div v-else class="card-content">
      <el-row :gutter="16" class="w-full">
        <el-col
          v-for="item in filteredList"
          :key="item.id"
          :xs="24"
          :sm="12"
          :md="12"
          :lg="8"
          :xl="6"
          class="mb-16"
        >
          <Card
            :item="item"
            :use-loading="usingId === item.id"
            @preview="openPreview"
            @use="useSharedItem"
          />
        </el-col>
      </el-row>
    </div>

    <el-dialog
      v-model="previewDialogVisible"
      width="88%"
      top="4vh"
      :title="state.previewInfo?.name || t('dashboard.preview')"
      class="store-preview-dialog"
    >
      <div v-loading="previewLoading" class="dialog-preview-wrap">
        <div
          v-if="state.previewInfo?.shareType === 'chart' && previewChartInfo?.chart"
          class="dialog-chart-preview"
        >
          <ChartComponent
            :id="`dialog-${state.previewInfo?.id}`"
            :key="`dialog-${state.previewInfo?.id}`"
            :type="previewChartInfo?.chart?.type || 'table'"
            :columns="previewChartInfo?.chart?.columns || []"
            :x="previewChartInfo?.chart?.xAxis || []"
            :y="previewChartInfo?.chart?.yAxis || []"
            :series="previewChartInfo?.chart?.series || []"
            :data="previewChartInfo?.data?.data || []"
            :multi-quota-name="previewChartInfo?.chart?.multiQuotaName"
          />
        </div>
        <div
          v-else-if="state.previewInfo?.shareType === 'chart'"
          class="dialog-dashboard-cover dialog-chart-placeholder"
        >
          <img :src="icon_chart_preview" width="64" height="64" />
          <div class="cover-title">
            {{
              state.previewInfo?.canUse
                ? t('dashboard.store_chart_preview_empty')
                : t('dashboard.store_no_preview_permission')
            }}
          </div>
        </div>
        <div v-else class="dialog-dashboard-cover">
          <img :src="icon_dashboard" width="72" height="72" />
          <div class="cover-title">{{ t('dashboard.shared_dashboard') }}</div>
          <div class="cover-desc">{{ state.previewInfo?.datasourceName || '-' }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped lang="less">
.datasource-config {
  height: calc(100% - 16px);
  padding: 16px 0 16px 0;

  .datasource-methods {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
    padding: 0 24px 0 24px;

    .title {
      font-weight: 500;
      font-size: 20px;
      line-height: 28px;
    }
  }

  .toolbar-actions {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .card-content {
    max-height: calc(100% - 40px);
    overflow-y: auto;
    padding: 0 8px 0 24px;

    .w-full {
      width: 100%;
    }

    .mb-16 {
      margin-bottom: 16px;
    }
  }
}

.store-empty {
  padding-bottom: 0;
  height: auto;
  padding-top: 200px;
}

.dialog-preview-wrap {
  height: 72vh;
}

.dialog-chart-preview {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: #fff;
}

.dialog-dashboard-cover {
  width: 100%;
  height: 100%;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #f7f9fc 0%, #eef2f7 100%);
  color: #646a73;
}

.cover-title {
  margin-top: 16px;
  font-size: 16px;
  line-height: 24px;
}

.cover-desc {
  margin-top: 8px;
  font-size: 14px;
  line-height: 22px;
}
</style>

<style lang="less">
.dashboard-store-filter-popper.dashboard-store-filter-popper {
  padding: 4px 0;
  width: 180px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;

  .popover {
    padding: 4px;
  }

  .popover-item {
    height: 32px;
    display: flex;
    align-items: center;
    padding-left: 12px;
    padding-right: 8px;
    margin-bottom: 2px;
    position: relative;
    border-radius: 6px;
    cursor: pointer;

    &:hover {
      background: #1f23291a;
    }

    .filter-name {
      font-size: 14px;
      line-height: 22px;
    }

    .done {
      margin-left: auto;
      display: none;
    }

    &.isActive {
      color: var(--ed-color-primary);

      .done {
        display: block;
      }
    }
  }
}
</style>
