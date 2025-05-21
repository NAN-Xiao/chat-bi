<script setup lang="ts">
import CanvasCore from '@/views/dashboard/canvas/CanvasCore.vue'
import {nextTick, onMounted, ref} from 'vue'
import type {CanvasItem} from "@/utils/canvas.ts";

const canvasCoreRef = ref(null)
const dashboardEditorRef = ref(null)
const baseWidth = ref(0)
const baseHeight = ref(0)
const baseMarginLeft = ref(0)
const baseMarginTop = ref(0)
const baseMatrixCount = {
  x: 72,
  y: 36
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

const canvasSizeInit = () => {
  sizeInit()
  if (canvasCoreRef.value) {
     //@ts-ignore
    canvasCoreRef.value.sizeInit()
  }
}

const sizeInit = () => {
  if (dashboardEditorRef.value) {
    //@ts-ignore
    const screenWidth = dashboardEditorRef.value.offsetWidth
    //@ts-ignore
    const screenHeight = dashboardEditorRef.value.offsetHeight
    baseMarginLeft.value = 10
    baseMarginTop.value = 10
    baseWidth.value = (screenWidth - baseMarginLeft.value) / baseMatrixCount.x - baseMarginLeft.value
    baseHeight.value = (screenHeight - baseMarginTop.value) / baseMatrixCount.y - baseMarginTop.value
  }
}

const addItemToBox = (item: CanvasItem) => {
  // @ts-ignore
  console.log(componentData.value.length + '===' + JSON.stringify(componentData.value))
  // @ts-ignore
  canvasCoreRef.value.addItemBox(item)
}

defineExpose({
  canvasSizeInit,
  addItemToBox
})

onMounted(() => {
  window.addEventListener('resize', canvasSizeInit)
  nextTick(() => {
    if (dashboardEditorRef.value) {
      sizeInit()
      // @ts-ignore
      nextTick(() => {
        if (canvasCoreRef.value) {
          // @ts-ignore
          canvasCoreRef.value.init()
        }
      })
    }
  })
})
</script>

<template>
  <div class='dashboard-editor-main' ref="dashboardEditorRef">
    <CanvasCore
        ref="canvasCoreRef"
        :base-width="baseWidth"
        :base-height="baseHeight"
        :base-margin-left="baseMarginLeft"
        :base-margin-top="baseMarginTop"
        :canvas-component-data="componentData"
    ></CanvasCore>
  </div>

</template>

<style scoped lang="less">
.dashboard-editor-main {
  width: 100%;
  height: calc(100% - 56px);
  overflow-y: auto;
}
</style>
