<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, computed, reactive, watch, nextTick } from 'vue'
import Toolbar from '@/views/dashboard/editor/Toolbar.vue'
import DashboardEditor from '@/views/dashboard/editor/DashboardEditor.vue'
import { findNewComponentFromList } from '@/views/dashboard/components/component-list.ts'
import { guid } from '@/utils/canvas.ts'
import cloneDeep from 'lodash/cloneDeep'
import { storeToRefs } from 'pinia'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import router from '@/router'
import { load_resource_prepare } from '@/views/dashboard/utils/canvasUtils.ts'
import { useI18n } from 'vue-i18n'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import {
  getCreateCanvasSourceKey,
  getDashboardCanvasSourceKey,
  loadDashboardCanvasDraft,
  saveDashboardCanvasDraft,
} from '@/views/dashboard/utils/canvasDraft.ts'
import { applyRecommendedChartComponentSize } from '@/views/dashboard/utils/chartSizing.ts'

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const datasourceContext = useDatasourceContextStore()
const { dashboardInfo, componentData, canvasStyleData, canvasViewInfo, fullscreenFlag, baseMatrixCount } =
  storeToRefs(dashboardStore)

const dataInitState = ref(true)
const state = reactive({
  routerPid: null as string | null,
  resourceId: null as string | null,
  opt: null as string | null,
  datasource: null as number | string | null | undefined,
})

const dashboardEditorInnerRef = ref(null)
let canvasStateReady = false
let applyingCanvasState = false
let draftSaveTimer: number | null = null
let routeLoadVersion = 0

const loadCanvasResource = (id: string | number) =>
  new Promise<any>((resolve) => {
    load_resource_prepare({ id }, function (result: any) {
      resolve(result)
    })
  })

const firstQueryValue = (value: unknown) => {
  if (Array.isArray(value)) {
    return value[0] ? String(value[0]) : null
  }
  return value ? String(value) : null
}

const syncRouteState = () => {
  const query = router.currentRoute.value.query
  state.opt = firstQueryValue(query.opt)
  state.resourceId = firstQueryValue(query.resourceId)
  state.routerPid = firstQueryValue(query.pid)
  state.datasource = firstQueryValue(query.datasource) || datasourceContext.datasourceId
}

const applyLoadedCanvasResource = async (
  resourceId: string | number,
  result: any,
  sourceKeyOverride?: string | null
) => {
  if (
    result?.dashboardInfo?.datasource &&
    String(datasourceContext.datasourceId || '') !== String(result.dashboardInfo.datasource)
  ) {
    await datasourceContext.activateDatasourceById(result.dashboardInfo.datasource, false)
  }
  await pauseCanvasStateWatch(() => {
    dashboardStore.setDashboardInfo(result?.dashboardInfo)
    dashboardStore.setCanvasStyleData(result?.canvasStyleResult || {})
    dashboardStore.setComponentData(result?.canvasDataResult || [])
    dashboardStore.setCanvasViewInfo(result?.canvasViewInfoPreview || {})
    dashboardStore.setCanvasEditingSourceKey(
      sourceKeyOverride || getDashboardCanvasSourceKey(result?.dashboardInfo?.id || resourceId)
    )
  })
}

const loadCanvasFromRoute = async () => {
  const loadVersion = ++routeLoadVersion
  persistCanvasDraft()
  canvasStateReady = false
  syncRouteState()
  await datasourceContext.loadDatasources()
  if (loadVersion !== routeLoadVersion) return

  const sourceKey =
    state.opt === 'create'
      ? getCreateCanvasSourceKey(state.datasource, state.routerPid)
      : getDashboardCanvasSourceKey(state.resourceId)
  if (
    sourceKey &&
    dashboardStore.canvasEditingSourceKey === sourceKey &&
    dashboardStore.hasUnsavedCanvasChanges
  ) {
    canvasStateReady = true
    return
  }

  dataInitState.value = false
  try {
    if (state.opt === 'create') {
      const createSourceKey = getCreateCanvasSourceKey(state.datasource, state.routerPid)
      await pauseCanvasStateWatch(() => {
        dashboardStore.canvasDataInit()
        dashboardStore.updateDashboardInfo({
          dataState: 'prepare',
          name: t('dashboard.new_dashboard'),
          pid: state.routerPid,
          datasource: state.datasource,
          canEdit: true,
          canShare: true,
        })
        dashboardStore.setCanvasEditingSourceKey(createSourceKey)
      })
      const restored = await restoreCanvasDraft(createSourceKey)
      if (!restored) {
        dashboardStore.markCanvasSaved()
      }
    } else if (state.resourceId && sourceKey) {
      const resourceId = state.resourceId
      const result = await loadCanvasResource(resourceId)
      if (loadVersion !== routeLoadVersion) return
      await applyLoadedCanvasResource(resourceId, result)
      const restored = await restoreCanvasDraft(sourceKey)
      if (!restored) {
        dashboardStore.markCanvasSaved()
      }
    } else {
      await pauseCanvasStateWatch(() => {
        dashboardStore.canvasDataInit()
      })
    }
  } finally {
    if (loadVersion === routeLoadVersion) {
      dataInitState.value = true
      canvasStateReady = true
    }
  }
}

const pauseCanvasStateWatch = async (task: () => void | Promise<void>) => {
  applyingCanvasState = true
  try {
    await task()
    await nextTick()
  } finally {
    applyingCanvasState = false
  }
}

const buildDraftDashboardInfo = (draftInfo: any) => {
  const latestInfo = cloneDeep(dashboardStore.dashboardInfo) || {}
  return {
    ...latestInfo,
    ...(draftInfo || {}),
    id: latestInfo.id ?? draftInfo?.id,
    pid: latestInfo.pid ?? draftInfo?.pid,
    datasource: latestInfo.datasource ?? draftInfo?.datasource,
    dataState: latestInfo.dataState ?? draftInfo?.dataState,
    contentId: latestInfo.contentId ?? draftInfo?.contentId,
    canEdit: latestInfo.canEdit ?? draftInfo?.canEdit,
    canShare: latestInfo.canShare ?? draftInfo?.canShare,
  }
}

const restoreCanvasDraft = async (sourceKey: string) => {
  const draft = loadDashboardCanvasDraft(sourceKey)
  if (!draft) return false
  await pauseCanvasStateWatch(() => {
    dashboardStore.setDashboardInfo(buildDraftDashboardInfo(draft.dashboardInfo))
    dashboardStore.setCanvasStyleData(cloneDeep(draft.canvasStyleData || {}))
    dashboardStore.setComponentData(cloneDeep(draft.componentData || []))
    dashboardStore.setCanvasViewInfo(cloneDeep(draft.canvasViewInfo || {}))
    dashboardStore.setCanvasEditingSourceKey(sourceKey)
  })
  dashboardStore.markCanvasChanged()
  return true
}

const persistCanvasDraft = () => {
  const sourceKey = dashboardStore.canvasEditingSourceKey
  if (!sourceKey || !dashboardStore.hasUnsavedCanvasChanges) return
  saveDashboardCanvasDraft(sourceKey, {
    sourceKey,
    savedAt: Date.now(),
    dashboardInfo: cloneDeep(dashboardInfo.value),
    componentData: cloneDeep(componentData.value),
    canvasStyleData: cloneDeep(canvasStyleData.value),
    canvasViewInfo: cloneDeep(canvasViewInfo.value),
  })
}

const scheduleCanvasDraftSave = () => {
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer)
  }
  draftSaveTimer = window.setTimeout(() => {
    draftSaveTimer = null
    persistCanvasDraft()
  }, 300)
}

const handleBeforeUnload = (event: BeforeUnloadEvent) => {
  persistCanvasDraft()
  if (!dashboardStore.hasUnsavedCanvasChanges) return
  event.preventDefault()
  event.returnValue = ''
}

watch(
  () => ({
    dashboardInfo: dashboardInfo.value,
    componentData: componentData.value,
    canvasStyleData: canvasStyleData.value,
    canvasViewInfo: canvasViewInfo.value,
  }),
  () => {
    if (!canvasStateReady || applyingCanvasState || !dashboardStore.canvasEditingSourceKey) {
      return
    }
    dashboardStore.markCanvasChanged()
    scheduleCanvasDraftSave()
  },
  { deep: true, flush: 'sync' }
)

const addComponents = (componentType: string, views?: any) => {
  const component = cloneDeep(findNewComponentFromList(componentType))
  if (!component) {
    return
  }
  component.x = findPositionX(component.sizeX)
  const defaultSizeY = component.sizeY
  if (views) {
    const viewList = Array.isArray(views) ? views : [views]
    viewList.forEach((view: any, index: number) => {
      const target = cloneDeep(view)
      delete target.chart.sourceType
      if (index > 0) {
        component.x = ((component.x + component.sizeX - 1) % baseMatrixCount.value.x) + 1
      }
      component.sizeY = defaultSizeY
      applyRecommendedChartComponentSize(component, target)
      addComponent(component, target)
    })
  } else {
    addComponent(component)
  }
}
const addComponent = (componentSource: any, viewInfo?: any) => {
  const component = cloneDeep(componentSource)
  if (component && dashboardEditorInnerRef.value) {
    component.id = guid()
    // add view
    if (component?.component === 'SQView' && !!viewInfo) {
      viewInfo['sourceId'] = viewInfo['id']
      viewInfo['id'] = component.id
      dashboardStore.addCanvasViewInfo(viewInfo)
    } else if (component.component === 'SQTab') {
      const subTabName = guid('tab')
      component.propValue[0].name = subTabName
      component.propValue[0].title = t('dashboard.new_tab')
      component.activeTabName = subTabName
    }
    component.y = maxYComponentCount() + 2
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    dashboardEditorInnerRef.value.addItemToBox(component)
  }
}

const maxYComponentCount = () => {
  if (componentData.value.length === 0) {
    return 1
  } else {
    return componentData.value
      .filter((item) => item['y'])
      .map((item) => item['y'] + item['sizeY']) // Calculate the y+sizeY of each element
      .reduce((max, current) => Math.max(max, current), 0)
  }
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  await loadCanvasFromRoute()
})

watch(
  () => router.currentRoute.value.fullPath,
  () => {
    if (router.currentRoute.value.path === '/canvas') {
      loadCanvasFromRoute()
    }
  }
)

onBeforeUnmount(() => {
  persistCanvasDraft()
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer)
    draftSaveTimer = null
  }
  window.removeEventListener('beforeunload', handleBeforeUnload)
})

const baseParams = computed(() => {
  return {
    opt: state.opt,
    resourceId: state.resourceId,
    pid: state.routerPid,
    datasource: state.datasource,
  }
})
const findPositionX = (width: number) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  return dashboardEditorInnerRef.value.findPositionX(width)
}
</script>

<template>
  <div class="editor-content" :class="{ 'editor-content-fullscreen': fullscreenFlag }">
    <div class="editor-main">
      <Toolbar
        :base-params="baseParams"
        :find-position-x="findPositionX"
        @add-components="addComponents"
      ></Toolbar>
      <DashboardEditor
        v-if="dataInitState"
        ref="dashboardEditorInnerRef"
        :canvas-component-data="componentData"
        :canvas-view-info="canvasViewInfo"
      >
      </DashboardEditor>
    </div>
  </div>
</template>

<style scoped lang="less">
.editor-content {
  width: 100vw;
  height: 100vh;
  background: var(--workspace-panel-bg, #f6f9fd);
  overflow: hidden;
}

.editor-content-fullscreen {
  padding: 0 !important;
}
.editor-main {
  position: relative;
  background: var(--workspace-panel-bg, #f6f9fd);
  overflow: hidden;
  width: 100%;
  height: 100%;
}
</style>
