<script setup lang="ts">
import {ref} from 'vue'
import Toolbar from "@/views/dashboard/editor/Toolbar.vue";
import DashboardEditor from "@/views/dashboard/editor/DashboardEditor.vue";
import {findNewComponentFromList} from "@/views/dashboard/components/component-list.ts";
import {guid} from "@/utils/canvas.ts";
import cloneDeep from 'lodash/cloneDeep';
import {storeToRefs} from "pinia";
import {dashboardStoreWithOut} from "@/stores/dashboard/dashboard.ts";

const dashboardStore = dashboardStoreWithOut()
const {componentData} = storeToRefs(dashboardStore)


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

</script>

<template>
  <div class="editor-main">
    <Toolbar @add-component="addComponent"></Toolbar>
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