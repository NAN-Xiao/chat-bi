<script setup lang="ts">
import { onMounted, ref, computed, reactive } from 'vue'
import Toolbar from '@/views/dashboard/editor/Toolbar.vue'
import DashboardEditor from '@/views/dashboard/editor/DashboardEditor.vue'
import { findNewComponentFromList } from '@/views/dashboard/components/component-list.ts'
import { guid } from '@/utils/canvas.ts'
import cloneDeep from 'lodash/cloneDeep'
import { storeToRefs } from 'pinia'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import router from '@/router'
import { initCanvasData } from '@/views/dashboard/utils/canvasUtils.ts'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const { componentData, canvasViewInfo } = storeToRefs(dashboardStore)

const dataInitState = ref(true)
const state = reactive({
  routerPid: null,
  resourceId: null,
  opt: null,
})

const dashboardEditorInnerRef = ref(null)
const addComponent = (componentType: string, viewInfo?: any) => {
  const component = cloneDeep(findNewComponentFromList(componentType))
  if (component && dashboardEditorInnerRef.value) {
    component.id = guid()
    // add view
    if (component?.component === 'SQView' && !!viewInfo) {
      viewInfo['sourceId'] = viewInfo['id']
      viewInfo['id'] = component.id
      dashboardStore.addCanvasViewInfo(viewInfo)
    }
    if (component.component === 'SQTab') {
      const subTabName = guid('tab')
      // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
      component.propValue[0].name = subTabName
      component.activeTabName = subTabName
    }
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    dashboardEditorInnerRef.value.addItemToBox(component)
  }
}

onMounted(() => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  state.opt = router.currentRoute.value.query.opt
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  state.resourceId = router.currentRoute.value.query.resourceId
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  state.routerPid = router.currentRoute.value.query.pid
  if (state.opt === 'create') {
    dashboardStore.updateDashboardInfo({
      dataState: 'prepare',
      name: t('dashboard.new_dashboard'),
      pid: state.routerPid,
    })
  } else if (state.resourceId) {
    dataInitState.value = false
    initCanvasData({ id: state.resourceId }, function () {
      dataInitState.value = true
    })
  }
})

const baseParams = computed(() => {
  return {
    opt: state.opt,
    resourceId: state.resourceId,
    pid: state.routerPid,
  }
})
</script>

<template>
  <div class="editor-content">
    <div class="editor-main">
      <Toolbar :base-params="baseParams" @add-component="addComponent"></Toolbar>
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
  padding: 12px;
  width: 100vw;
  height: 100vh;
  background: #fff;
  overflow: hidden;
}
.editor-main {
  border-radius: 12px;
  position: relative;
  background: #f5f6f7;
  box-shadow: 0px 4px 8px 0px rgba(31, 35, 41, 0.1);
  overflow: hidden;
  width: 100%;
  height: 100%;
}
</style>
