<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_delete from '@/assets/svg/icon_delete.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import icon_dashboard from '@/assets/permission/icon_dashboard.svg'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import EmptyBackgroundSvg from '@/views/dashboard/common/EmptyBackgroundSvg.vue'
import HandleMore from '@/views/dashboard/common/HandleMore.vue'
import SQPreview from '@/views/dashboard/preview/SQPreview.vue'
import SQPreviewHead from '@/views/dashboard/preview/SQPreviewHead.vue'
import { dashboardApi } from '@/api/dashboard'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const loading = ref(false)
const deletingId = ref('')
const keyword = ref('')
const list = ref<any[]>([])
const selectedId = ref('')
const previewKey = ref(0)
const refreshingTemplateId = ref('')
const pendingRefreshTemplateId = ref('')
const preview = reactive({
  dashboardInfo: {} as Record<string, any>,
  componentData: [] as any[],
  canvasStyleData: {} as Record<string, any>,
  canvasViewInfo: {} as Record<string, any>,
})
let previewRequestSeq = 0
const TEMPLATE_ROUTE_PATH = '/system/dashboard-template'

const isTemplateRoute = () => route.path === TEMPLATE_ROUTE_PATH

const invalidatePreviewRequests = () => {
  previewRequestSeq += 1
  pendingRefreshTemplateId.value = ''
  refreshingTemplateId.value = ''
}

const isActiveTemplateRequest = (id: string, requestSeq: number) =>
  isTemplateRoute() &&
  requestSeq === previewRequestSeq &&
  String(selectedId.value) === String(id)

const hasPreview = computed(() => Boolean(preview.dashboardInfo?.id))
const hasCanvasPreview = computed(() => hasPreview.value && preview.componentData.length > 0)
const isCurrentTemplateRefreshing = computed(
  () =>
    Boolean(refreshingTemplateId.value) &&
    String(refreshingTemplateId.value) === String(selectedId.value)
)
const templateMenuList = computed(() => [
  {
    label: t('dashboard.delete'),
    command: 'delete',
    svgName: icon_delete,
  },
])
const filteredList = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return list.value
  return list.value.filter((item) =>
    [
      item.name,
      item.id,
      item.source_datasource_name,
      item.source_tenant_name,
      item.source_dashboard_name,
      templateSourceSpaceId(item),
      templateSourceDashboardId(item),
    ].some((field) => String(field || '').toLowerCase().includes(value))
  )
})
const templateRemarkValue = (item: any, key: string) => {
  const prefix = `${key}=`
  return String(item?.remark || '')
    .split(';')
    .find((part) => part.startsWith(prefix))
    ?.slice(prefix.length)
    ?.trim()
}
const templateSourceSpaceId = (item: any) =>
  item?.source_tenant_id || templateRemarkValue(item, 'source_tenant_id')
const templateSourceDashboardId = (item: any) =>
  item?.source_dashboard_id || templateRemarkValue(item, 'source_dashboard_id')
const templateSourceSpaceName = (item: any) =>
  item?.source_tenant_name ||
  (templateSourceSpaceId(item) ? `${t('dashboard.platform_template_source_workspace')} ${templateSourceSpaceId(item)}` : '') ||
  t('dashboard.platform_template_unknown_source_workspace')
const templateSourceProjectName = (item: any) =>
  item?.source_datasource_name ||
  (item?.source_datasource_id ? `${t('dashboard.platform_template_source_project')} ${item.source_datasource_id}` : '')
const groupedFilteredList = computed(() => {
  const groups = new Map<string, { key: string; label: string; items: any[] }>()
  filteredList.value.forEach((item) => {
    const label = templateSourceSpaceName(item)
    const key = String(templateSourceSpaceId(item) || label)
    if (!groups.has(key)) {
      groups.set(key, { key, label, items: [] })
    }
    groups.get(key)?.items.push(item)
  })
  return Array.from(groups.values())
})

const templateMetaText = (item: any) => {
  if (!item?.id) return '-'
  const sourceText = [
    templateSourceProjectName(item),
    item.source_dashboard_name || templateSourceDashboardId(item),
  ]
    .filter(Boolean)
    .join(' / ')
  return sourceText ? sourceText : `ID ${item.id}`
}

const parseJson = (value: any, fallback: any) => {
  if (!value) return fallback
  if (typeof value !== 'string') return value
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

const cloneJson = (value: any, fallback: any) => {
  try {
    return JSON.parse(JSON.stringify(value ?? fallback))
  } catch {
    return fallback
  }
}

const applyTemplatePreviewPayload = (res: any) => {
  preview.dashboardInfo = {
    id: res.id,
    name: res.name,
    pid: res.pid,
    datasource: res.datasource,
    status: res.status,
    source: res.source,
    contentId: res.content_id,
    type: res.type,
    createName: res.create_name,
    updateName: res.update_name,
    sourceDashboardId: res.source_dashboard_id,
    sourceDashboardName: res.source_dashboard_name,
    sourceTenantId: res.source_tenant_id,
    sourceTenantName: res.source_tenant_name,
    sourceDatasourceId: res.source_datasource_id,
    sourceDatasourceName: res.source_datasource_name,
    createTime: res.create_time,
    updateTime: res.update_time,
    canEdit: res.can_edit === true,
    canShare: false,
    isDefault: false,
  }
  preview.componentData = parseJson(res.component_data, [])
  preview.canvasStyleData = parseJson(res.canvas_style_data, {})
  preview.canvasViewInfo = parseJson(res.canvas_view_info, {})
}

const syncTemplateListItem = (res: any) => {
  const index = list.value.findIndex((item) => String(item.id) === String(res?.id))
  if (index < 0) return
  list.value[index] = {
    ...list.value[index],
    ...res,
    source_dashboard_id: res.source_dashboard_id,
    source_dashboard_name: res.source_dashboard_name,
    source_tenant_id: res.source_tenant_id,
    source_tenant_name: res.source_tenant_name,
    source_datasource_id: res.source_datasource_id,
    source_datasource_name: res.source_datasource_name,
  }
}

const snapshotRefreshedAt = (item: any) => {
  const timestamp = Number(item?.snapshotRefreshedAt || item?.data?.snapshotRefreshedAt || 0)
  return Number.isFinite(timestamp) && timestamp > 0 ? timestamp : 0
}

const chartHasRows = (item: any) => Array.isArray(item?.data?.data) && item.data.data.length > 0

const chartNeedsSnapshotRefresh = (item: any) => {
  if (!item || typeof item !== 'object') return false
  if (!String(item.sql || '').trim()) return false
  return !snapshotRefreshedAt(item) && !chartHasRows(item)
}

const previewNeedsChartRefresh = () =>
  Object.values(preview.canvasViewInfo || {}).some((item: any) => chartNeedsSnapshotRefresh(item))

const markPreviewChartsRefreshing = (refreshState = 'loading') => {
  Object.values(preview.canvasViewInfo || {}).forEach((item: any) => {
    if (!item || typeof item !== 'object') return
    if (item.sql === undefined && !item.chart) return
    item.status = 'loading'
    item.dataState = 'loading'
    item.refreshState = refreshState
    item.loadingProgress = 0
  })
}

const clearPreview = () => {
  preview.dashboardInfo = {}
  preview.componentData = []
  preview.canvasStyleData = {}
  preview.canvasViewInfo = {}
  previewKey.value += 1
}

const loadTemplatePreview = async (id: string) => {
  if (!isTemplateRoute()) return
  if (!id) {
    clearPreview()
    return
  }
  const requestSeq = ++previewRequestSeq
  const res = await dashboardApi.platform_template_admin_load(
    { id, include_data: false },
    { requestOptions: { silent: true } }
  )
  if (!isActiveTemplateRequest(id, requestSeq)) {
    return
  }
  applyTemplatePreviewPayload(res)
  previewKey.value += 1
  if (previewNeedsChartRefresh()) {
    await nextTick()
    if (!isActiveTemplateRequest(id, requestSeq)) return
    void refreshTemplateCharts({ silent: true, refreshState: 'waiting', expectedId: id })
  }
}

const refreshTemplateCharts = async (
  options: { silent?: boolean; refreshState?: 'loading' | 'waiting'; expectedId?: string } = {}
) => {
  const id = options.expectedId || selectedId.value
  if (!id || !isTemplateRoute()) return
  const requestSeq = previewRequestSeq
  if (refreshingTemplateId.value) {
    if (isActiveTemplateRequest(id, requestSeq)) {
      pendingRefreshTemplateId.value = id
      markPreviewChartsRefreshing(options.refreshState || 'waiting')
    }
    return
  }
  refreshingTemplateId.value = id
  const previousCanvasViewInfo = cloneJson(preview.canvasViewInfo, {})
  markPreviewChartsRefreshing(options.refreshState || 'loading')
  try {
    const res = await dashboardApi.platform_template_admin_refresh(
      { id, include_data: false },
      { requestOptions: { silent: true } }
    )
    if (!isActiveTemplateRequest(id, requestSeq)) {
      return
    }
    applyTemplatePreviewPayload(res)
    syncTemplateListItem(res)
    previewKey.value += 1
    if (!options.silent) {
      ElMessage.success(t('dashboard.chart_refresh_success'))
    }
  } catch (error: any) {
    if (!isActiveTemplateRequest(id, requestSeq)) {
      return
    }
    preview.canvasViewInfo = previousCanvasViewInfo
    previewKey.value += 1
    if (!options.silent) {
      ElMessage.error(error?.message || t('dashboard.chart_refresh_failed'))
    }
  } finally {
    if (String(refreshingTemplateId.value) === String(id)) {
      refreshingTemplateId.value = ''
    }
    if (!isTemplateRoute() || requestSeq !== previewRequestSeq) {
      pendingRefreshTemplateId.value = ''
      return
    }
    const nextId = pendingRefreshTemplateId.value
    pendingRefreshTemplateId.value = ''
    if (
      nextId &&
      String(selectedId.value) === String(nextId) &&
      previewNeedsChartRefresh()
    ) {
      void refreshTemplateCharts({
        silent: true,
        refreshState: 'waiting',
        expectedId: nextId,
      })
    }
  }
}

const selectTemplate = async (item: any, syncRoute = true) => {
  if (!item?.id || selectedId.value === item.id || !isTemplateRoute()) return
  selectedId.value = item.id
  if (syncRoute) {
    await router.replace({
      path: TEMPLATE_ROUTE_PATH,
      query: { ...route.query, templateId: item.id },
    })
    if (!isTemplateRoute()) return
  }
  await loadTemplatePreview(item.id)
}

const loadList = async () => {
  if (!isTemplateRoute()) return
  loading.value = true
  let nextSelected: any
  try {
    const res = await dashboardApi.platform_template_admin_list({
      requestOptions: { silent: true },
    })
    list.value = Array.isArray(res) ? res : []
    const routeTemplateId = Array.isArray(route.query.templateId)
      ? route.query.templateId[0]
      : route.query.templateId
    nextSelected =
      list.value.find((item) => String(item.id) === String(routeTemplateId || selectedId.value)) ||
      list.value[0]
  } finally {
    loading.value = false
  }
  if (!isTemplateRoute()) return
  if (nextSelected) {
    await selectTemplate(nextSelected, false)
  } else {
    selectedId.value = ''
    clearPreview()
  }
}

const deleteTemplate = async (item?: any) => {
  const id = item?.id || selectedId.value
  const name = item?.name || preview.dashboardInfo?.name || ''
  if (!id || deletingId.value) return
  const confirmed = await ElMessageBox.confirm(
    t('dashboard.platform_template_delete_confirm', { name }),
    {
      confirmButtonText: t('dashboard.delete'),
      cancelButtonText: t('common.cancel'),
      confirmButtonType: 'danger',
      type: 'warning',
      autofocus: false,
      showClose: false,
    }
  ).catch(() => false)
  if (!confirmed) return
  deletingId.value = id
  try {
    await dashboardApi.platform_template_admin_delete({ id, name })
    ElMessage.success(t('dashboard.delete_success'))
    if (String(id) === String(selectedId.value)) {
      const nextQuery = { ...route.query }
      delete nextQuery.templateId
      selectedId.value = ''
      clearPreview()
      await router.replace({
        path: TEMPLATE_ROUTE_PATH,
        query: nextQuery,
      })
    }
    await loadList()
  } finally {
    deletingId.value = ''
  }
}

const handleTemplateCommand = (command: string, item: any) => {
  if (command === 'delete') {
    deleteTemplate(item)
  }
}

watch(
  () => filteredList.value.map((item) => item.id).join(','),
  async () => {
    await nextTick()
    if (!isTemplateRoute()) return
    if (selectedId.value && filteredList.value.some((item) => item.id === selectedId.value)) return
    if (filteredList.value[0]) {
      await selectTemplate(filteredList.value[0])
    }
  }
)

onMounted(() => {
  loadList()
})

watch(
  () => route.path,
  (path) => {
    if (path !== TEMPLATE_ROUTE_PATH) {
      invalidatePreviewRequests()
    }
  }
)

onBeforeUnmount(() => {
  invalidatePreviewRequests()
})
</script>

<template>
  <div class="platform-template-workbench no-padding">
    <aside v-loading="loading" class="template-sidebar">
      <div class="sidebar-head">
        <div class="title">{{ t('dashboard.platform_template_library') }}</div>
        <div class="subtitle">{{ t('dashboard.platform_template_library_desc') }}</div>
      </div>
      <el-input
        v-model="keyword"
        clearable
        class="search-input"
        :placeholder="t('dashboard.platform_template_search')"
      >
        <template #prefix>
          <el-icon>
            <icon_searchOutline_outlined class="svg-icon" />
          </el-icon>
        </template>
      </el-input>

      <div v-if="filteredList.length" class="template-list">
        <div v-for="group in groupedFilteredList" :key="group.key" class="template-group">
          <div class="template-group-title ellipsis" :title="group.label">{{ group.label }}</div>
          <div
            v-for="item in group.items"
            :key="item.id"
            role="button"
            tabindex="0"
            class="template-row"
            :class="{ active: selectedId === item.id }"
            @click="selectTemplate(item)"
            @keydown.enter.prevent="selectTemplate(item)"
            @keydown.space.prevent="selectTemplate(item)"
          >
            <span class="row-icon"><icon_dashboard /></span>
            <span class="row-body">
              <span class="row-name ellipsis" :title="item.name">{{ item.name }}</span>
              <span class="row-meta ellipsis" :title="templateMetaText(item)">{{ templateMetaText(item) }}</span>
            </span>
            <span class="row-actions" @click.stop>
              <HandleMore
                :menu-list="templateMenuList"
                :icon-name="icon_more_outlined"
                placement="bottom-end"
                @handle-command="(command: string) => handleTemplateCommand(command, item)"
              />
            </span>
          </div>
        </div>
      </div>

      <EmptyBackground
        v-else
        :description="t('dashboard.platform_template_empty')"
        class="template-empty"
        img-type="noneWhite"
      />
    </aside>

    <main
      class="template-preview-area"
      :class="{ 'is-empty': !hasPreview }"
    >
      <div class="preview-stage">
        <SQPreviewHead
          :dashboard-info="hasPreview ? preview.dashboardInfo : {}"
          :component-data="preview.componentData"
          :canvas-view-info="preview.canvasViewInfo"
          platform-template
        />
        <div
          class="content"
          :class="{ 'content--empty': !hasCanvasPreview }"
        >
          <SQPreview
            v-if="hasCanvasPreview"
            :key="`platform-template-${selectedId}-${previewKey}`"
            :canvas-id="`platform-template-${selectedId}`"
            :dashboard-info="preview.dashboardInfo"
            :component-data="preview.componentData"
            :canvas-style-data="preview.canvasStyleData"
            :canvas-view-info="preview.canvasViewInfo"
            show-position="preview"
            readonly-template
            platform-template
          />
          <EmptyBackgroundSvg
            v-else-if="hasPreview"
            :description="t('dashboard.no_dashboard_info')"
          />
          <EmptyBackgroundSvg
            v-else-if="filteredList.length"
            :description="t('dashboard.select_dashboard_tips')"
          />
          <EmptyBackground
            v-else
            :description="t('dashboard.platform_template_empty')"
            img-type="none"
          />
        </div>
        <div class="template-head-actions">
          <el-button
            secondary
            :loading="isCurrentTemplateRefreshing"
            :disabled="!hasPreview || Boolean(refreshingTemplateId)"
            @click="refreshTemplateCharts()"
          >
            {{ t('common.refresh') }}
          </el-button>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped lang="less">
.platform-template-workbench {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
  color: var(--workspace-text-primary, #1f2329);
}

.template-sidebar {
  min-height: 0;
  border-right: 1px solid var(--workspace-border, #e2eaf4);
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
  display: flex;
  flex-direction: column;
}

.sidebar-head {
  padding: 16px 16px 12px;
}

.title {
  color: var(--workspace-text-primary, #1f2329);
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
}

.subtitle {
  margin-top: 4px;
  color: var(--workspace-text-secondary, #667085);
  font-size: 12px;
  line-height: 18px;
}

.search-input {
  width: calc(100% - 32px);
  margin: 0 16px 12px;
}

.template-list {
  min-height: 0;
  overflow: auto;
  padding: 0 8px 12px;
}

.template-group + .template-group {
  margin-top: 10px;
}

.template-group-title {
  padding: 8px 8px 5px;
  color: var(--workspace-text-secondary, #667085);
  font-size: 12px;
  line-height: 18px;
  font-weight: 600;
}

.template-row {
  width: 100%;
  min-height: 54px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px;
  text-align: left;
  cursor: pointer;

  &:hover,
  &.active {
    background: var(--ed-color-primary-1a, rgba(51, 112, 255, 0.1));
  }

  &:hover .row-actions,
  &.active .row-actions {
    display: inline-flex;
  }

  &.active .row-name {
    color: var(--ed-color-primary, #3370ff);
  }
}

.row-icon {
  flex: 0 0 auto;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--workspace-text-secondary, #667085);
}

.row-body {
  min-width: 0;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.row-name {
  color: var(--workspace-text-primary, #1f2329);
  font-size: 13px;
  line-height: 20px;
  font-weight: 500;
}

.row-meta {
  margin-top: 2px;
  color: var(--workspace-text-secondary, #667085);
  font-size: 12px;
  line-height: 18px;
}

.row-actions {
  flex: 0 0 auto;
  margin-left: auto;
  display: none;
  align-items: center;
  justify-content: center;
  color: var(--workspace-text-tertiary, #8f959e);
}

.row-actions :deep(.hover-icon) {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.row-actions :deep(.hover-icon:hover) {
  background: rgba(31, 35, 41, 0.1);
  color: var(--workspace-text-primary, #1f2329);
}

.template-empty {
  padding-top: 96px;
}

.template-preview-area {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: flex;
  overflow-x: hidden;
  overflow-y: auto;
  background: var(--workspace-panel-bg, var(--theme-panel-bg));
}

.preview-stage {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
}

.content {
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow-x: hidden;
  overflow-y: auto;
  padding: 0;
  align-items: stretch;

  &.content--empty {
    align-items: center;
    justify-content: center;
  }
}

.template-head-actions {
  position: absolute;
  top: 14px;
  right: 16px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
}

.template-preview-area :deep(.preview-head .canvas-opt-button) {
  padding-right: 96px;
}

.template-preview-area :deep(.preview-head .canvas-name) {
  max-width: 520px;
}

.template-preview-area .content.content--empty {
  :deep(.empty-info),
  :deep(.ed-empty) {
    width: 100%;
    height: 100%;
    padding-top: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    background: var(--workspace-panel-bg, var(--theme-panel-bg));
  }

  :deep(.ed-empty__description) {
    color: var(--workspace-text-secondary, #66758f);
  }
}

@media (max-width: 900px) {
  .platform-template-workbench {
    grid-template-columns: 1fr;
  }

  .template-sidebar {
    min-height: 260px;
    border-right: 0;
    border-bottom: 1px solid var(--workspace-border, #e2eaf4);
  }

  .template-head-actions {
    position: static;
    justify-content: flex-end;
    padding: 10px 12px;
    border-bottom: 1px solid var(--workspace-border, #e2eaf4);
  }

  .template-preview-area :deep(.preview-head .canvas-opt-button) {
    padding-right: 0;
  }
}
</style>
