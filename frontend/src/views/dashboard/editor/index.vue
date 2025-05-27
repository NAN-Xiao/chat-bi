<script setup lang="ts">
import {ref} from 'vue'
import Toolbar from "@/views/dashboard/editor/Toolbar.vue";
import DashboardEditor from "@/views/dashboard/editor/DashboardEditor.vue";
import {findNewComponentFromList} from "@/views/dashboard/components/component-list.ts";
import {guid} from "@/utils/canvas.ts";
import cloneDeep from 'lodash/cloneDeep';


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

const componentData = ref([
  {
    id: 4,
    x: 1,
    y: 1,
    sizeX: 20,
    sizeY: 10,
    _dragId: 0
  },
  {
    id: 10,
    x: 2,
    y: 1,
    sizeX: 20,
    sizeY: 10,
    _dragId: 1
  },
  {
    id: 7,
    x: 1,
    y: 2,
    sizeX: 20,
    sizeY: 10,
    _dragId: 2
  }
])

</script>

<template>
  <div class="editor-main">
    <Toolbar @add-component="addComponent"></Toolbar>
    <DashboardEditor ref="dashboardEditorRef" :canvas-component-data="componentData"></DashboardEditor>
  </div>
</template>

<style scoped lang="less">
.editor-main {
  position: relative;
  width: 100vw;
  height: calc(100vh - 61px);
}
</style>