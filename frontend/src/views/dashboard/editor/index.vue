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

const dashboardStore = dashboardStoreWithOut()
const { componentData, canvasViewInfo } = storeToRefs(dashboardStore)

const dataInitState = ref(false)
const state = reactive({
  routerPid: null,
  resourceId: null,
  opt: null,
})

const dashboardEditorRef = ref(null)
const addComponent = (componentType: string, viewInfo?: any) => {
  const component = cloneDeep(findNewComponentFromList(componentType))
  if (component && dashboardEditorRef.value) {
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
    dashboardEditorRef.value.addItemToBox(component)
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
      name: 'New Dashboard',
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
  <div class="editor-main">
    <Toolbar :base-params="baseParams" @add-component="addComponent"></Toolbar>
    <DashboardEditor
      v-if="dataInitState"
      ref="dashboardEditorRef"
      :canvas-component-data="componentData"
      :canvas-view-info="canvasViewInfo"
    >
    </DashboardEditor>
  </div>
</template>

<style scoped lang="less">
.editor-main {
  position: relative;
  width: 100vw;
  height: 100vh;
  background: #f5f6f7;
}
</style>
