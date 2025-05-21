<script setup lang="ts">
import {ref} from 'vue'
import Toolbar from "@/views/dashboard/editor/Toolbar.vue";
import DashboardEditor from "@/views/dashboard/editor/DashboardEditor.vue";
import {findNewComponentFromList} from "@/views/dashboard/components/component-list.ts";
import {guid} from "@/utils/canvas.ts";
import cloneDeep from 'lodash/cloneDeep';


const dashboardEditorRef = ref(null);
const addComponent = (componentType : string) => {
  const component = cloneDeep(findNewComponentFromList(componentType))
  if (component && dashboardEditorRef.value) {
    component.id = guid()
    //@ts-ignore
    dashboardEditorRef.value.addItemToBox(component)
  }
}
</script>

<template>
  <div class="editor-main">
    <Toolbar @add-component="addComponent"></Toolbar>
    <DashboardEditor ref="dashboardEditorRef"></DashboardEditor>
  </div>
</template>

<style scoped lang="less">
.editor-main {
  position: relative;
  width: 100vw;
  height: calc(100vh - 61px);
}
</style>