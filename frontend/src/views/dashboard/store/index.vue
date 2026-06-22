<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import iconFilter from '@/assets/svg/icon-filter_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import iconDashboardUrl from '@/assets/svg/dashboard.svg?url'
import iconChartPreviewUrl from '@/assets/svg/icon_chart_preview.svg?url'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import SQPreview from '@/views/dashboard/preview/SQPreview.vue'
import AddViewDashboard from '@/views/dashboard/common/AddViewDashboard.vue'
import Card from './Card.vue'
import { dashboardApi } from '@/api/dashboard'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const userStore = useUserStore()

const loading = ref(false)
const usingId = ref('')
const addViewRef = ref()
const previewDialogVisible = ref(false)
const previewLoading = ref(false)
const keywords = ref('')
const currentTypeFilter = ref('')
const currentWorkspaceId = computed(() => userStore.getTenantId)
let listRequestSeq = 0
const state = reactive({
  list: [] as any[],
  previewInfo: null as any,
  previewComponentId: '',
  previewComponentData: [] as any[],
  previewCanvasStyleData: {} as Record<string, any>,
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
const showDashboardPreview = computed(() => {
  return (
    state.previewInfo?.shareType === 'dashboard' &&
    Array.isArray(state.previewComponentData) &&
    state.previewComponentData.length > 0
  )
})

const resetPreview = () => {
  previewDialogVisible.value = false
  previewLoading.value = false
  state.previewInfo = null
  state.previewComponentId = ''
  state.previewComponentData = []
  state.previewCanvasStyleData = {}
  state.previewCanvasViewInfo = {}
}

const loadList = async () => {
  const requestSeq = ++listRequestSeq
  const requestWorkspaceId = currentWorkspaceId.value
  loading.value = true
  try {
    const list = await dashboardApi.share_list(
      { keyword: keywords.value },
      { requestOptions: { silent: true } }
    )
    if (requestSeq !== listRequestSeq || requestWorkspaceId !== currentWorkspaceId.value) {
      return
    }
    state.list = Array.isArray(list) ? list : []
  } catch (error) {
    console.error(error)
    if (requestSeq !== listRequestSeq || requestWorkspaceId !== currentWorkspaceId.value) {
      return
    }
    state.list = []
  } finally {
    if (requestSeq === listRequestSeq && requestWorkspaceId === currentWorkspaceId.value) {
      loading.value = false
    }
  }
}

const openPreview = async (item: any) => {
  previewLoading.value = true
  previewDialogVisible.value = true
  state.previewInfo = null
  state.previewComponentId = ''
  state.previewComponentData = []
  state.previewCanvasStyleData = {}
  state.previewCanvasViewInfo = {}
  try {
    const res = await dashboardApi.share_load({ id: item.id })
    const componentData = parseJson(res.component_data, [])
    const canvasStyleData = parseJson(res.canvas_style_data, {})
    const canvasViewInfo = parseJson(res.canvas_view_info, {})
    state.previewInfo = {
      id: res.id,
      name: res.name,
      datasource: res.datasource,
      datasourceName: item.datasource_name,
      shareType: res.share_type,
      canUse: res.can_use,
      previewImage: res.preview_image || item.preview_image || '',
    }
    state.previewComponentId = componentData[0]?.id || res.source_view_id || item.source_view_id || ''
    state.previewComponentData = componentData
    state.previewCanvasStyleData = canvasStyleData
    state.previewCanvasViewInfo = canvasViewInfo
  } finally {
    previewLoading.value = false
  }
}

const useSharedItem = async (item: any) => {
  if (!item.can_use || usingId.value) return
  usingId.value = item.id
  try {
    if (item.share_type === 'chart') {
      const res = await dashboardApi.share_load({ id: item.id })
      const componentData = parseJson(res.component_data, [])
      const canvasViewInfo = parseJson(res.canvas_view_info, {})
      const componentId = componentData[0]?.id || res.source_view_id || item.source_view_id
      const viewInfo = componentId ? canvasViewInfo?.[componentId] : null
      if (!viewInfo) {
        ElMessage.warning(t('dashboard.store_chart_preview_empty'))
        return
      }
      addViewRef.value?.optInit({
        ...viewInfo,
        datasource: viewInfo.datasource || res.datasource || item.datasource,
      })
      return
    }
    const confirmed = await ElMessageBox.confirm(t('dashboard.store_add_dashboard_confirm'), {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning',
      autofocus: false,
      showClose: false,
    }).catch(() => false)
    if (!confirmed) return
    await dashboardApi.share_use({ id: item.id })
    ElMessage.success(t('dashboard.store_use_success'))
  } finally {
    usingId.value = ''
  }
}

const deleteSharedItem = async (item: any) => {
  if (!item.can_delete) return
  ElMessageBox.confirm(t('dashboard.cancel_share_warn', [item.name]), {
    confirmButtonType: 'danger',
    type: 'warning',
    autofocus: false,
    showClose: false,
  }).then(async () => {
    await dashboardApi.share_delete({ id: item.id })
    ElMessage.success(t('dashboard.cancel_share_success'))
    if (state.previewInfo?.id === item.id) {
      previewDialogVisible.value = false
      state.previewInfo = null
    }
    await loadList()
  })
}

const toggleTypeFilter = (value: string) => {
  currentTypeFilter.value = currentTypeFilter.value === value ? '' : value
}

onMounted(() => {
  loadList()
})

watch(currentWorkspaceId, () => {
  listRequestSeq++
  state.list = []
  resetPreview()
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
      <div class="card-grid">
        <Card
          v-for="item in filteredList"
          :key="item.id"
          :item="item"
          :use-loading="usingId === item.id"
          @preview="openPreview"
          @use="useSharedItem"
          @delete="deleteSharedItem"
        />
      </div>
    </div>

    <el-dialog
      v-model="previewDialogVisible"
      width="88%"
      top="4vh"
      :title="state.previewInfo?.name || t('dashboard.preview')"
      class="store-preview-dialog"
    >
      <div v-loading="previewLoading" class="dialog-preview-wrap">
        <div v-if="state.previewInfo?.previewImage" class="dialog-image-preview">
          <img :src="state.previewInfo.previewImage" :alt="state.previewInfo?.name" />
        </div>
        <div v-else-if="showDashboardPreview" class="dialog-dashboard-preview">
          <SQPreview
            :key="`store-preview-${state.previewInfo?.id}`"
            :canvas-id="`store-preview-${state.previewInfo?.id}`"
            :dashboard-info="state.previewInfo"
            :component-data="state.previewComponentData"
            :canvas-style-data="state.previewCanvasStyleData"
            :canvas-view-info="state.previewCanvasViewInfo"
            show-position="preview"
          />
        </div>
        <div
          v-else-if="state.previewInfo?.shareType === 'chart' && previewChartInfo?.chart"
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
          <img :src="iconChartPreviewUrl" width="64" height="64" />
          <div class="cover-title">
            {{
              state.previewInfo?.canUse
                ? t('dashboard.store_chart_preview_empty')
                : t('dashboard.store_no_preview_permission')
            }}
          </div>
        </div>
        <div v-else class="dialog-dashboard-cover">
          <img :src="iconDashboardUrl" width="72" height="72" />
          <div class="cover-title">{{ t('dashboard.shared_dashboard') }}</div>
          <div class="cover-desc">{{ state.previewInfo?.datasourceName || '-' }}</div>
        </div>
      </div>
    </el-dialog>
    <AddViewDashboard ref="addViewRef" />
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
    padding: 0 32px 32px 24px;

    .card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, 272px);
      align-items: start;
      gap: 18px;
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

.dialog-dashboard-preview {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  background: var(--workspace-panel-bg, #fff);
}

.dialog-image-preview {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--workspace-panel-bg, #f6f9fd);

  img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    display: block;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(31, 35, 41, 0.12);
  }
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
