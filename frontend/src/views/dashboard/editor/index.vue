<script setup lang="ts">
import {onMounted, ref, computed, reactive} from 'vue'
import Toolbar from "@/views/dashboard/editor/Toolbar.vue";
import DashboardEditor from "@/views/dashboard/editor/DashboardEditor.vue";
import {findNewComponentFromList} from "@/views/dashboard/components/component-list.ts";
import {guid} from "@/utils/canvas.ts";
import cloneDeep from 'lodash/cloneDeep';
import {storeToRefs} from "pinia";
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";
import router from '@/router'
import {initCanvasData} from "@/views/dashboard/utils/canvasUtils.ts";

const dashboardStore = dashboardStoreWithOut()
const {componentData} = storeToRefs(dashboardStore)

const dataInitState = ref(false)
const state = reactive({
  routerPid: null,
  resourceId: null,
  opt: null
})

const dashboardEditorRef = ref(null);
const addComponent = (componentType: string) => {
  const component = cloneDeep(findNewComponentFromList(componentType))
  if (component && dashboardEditorRef.value) {
    // @ts-ignore
    component.id = guid()
    if (component.component === 'SQTab') {
      const subTabName = guid('tab')
      // @ts-ignore
      component.propValue[0].name = subTabName
      component.activeTabName = subTabName
    }
    //@ts-ignore
    dashboardEditorRef.value.addItemToBox(component)
  }
}

onMounted(() => {
  //@ts-ignore
  state.opt = router.currentRoute.value.query.opt
  //@ts-ignore
  state.resourceId = router.currentRoute.value.query.resourceId
  //@ts-ignore
  state.routerPid = router.currentRoute.value.query.pid
  if (state.opt === 'create') {
    dashboardStore.updateDashboardInfo({dataState: 'prepare', name: 'New Dashboard', pid: state.routerPid})
  } else if (state.resourceId) {
    dataInitState.value = false
    initCanvasData({id: state.resourceId}, function () {
      dataInitState.value = true
    })
  }
})

const baseParams = computed(() => {
  return {
    opt: state.opt,
    resourceId: state.resourceId,
    pid: state.routerPid
  }
})


</script>

<template>
  <div class="editor-main">
    <Toolbar :base-params="baseParams" @add-component="addComponent"></Toolbar>
    <DashboardEditor
        ref="dashboardEditorRef"
        :canvas-component-data="componentData">
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