<script setup lang="ts">
import CanvasCore from '@/views/dashboard/canvas/CanvasCore.vue'
import { nextTick, onMounted, ref } from 'vue'
const cyGridster = ref(null)
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

onMounted(() => {
  const screenWidth = window.innerWidth
  const screenHeight = window.innerHeight
  baseMarginLeft.value = 10
  baseMarginTop.value = 10

  baseWidth.value = (screenWidth - baseMarginLeft.value) / baseMatrixCount.x - baseMarginLeft.value
  baseHeight.value = (screenHeight - baseMarginTop.value) / baseMatrixCount.y - baseMarginTop.value

  nextTick(() => {
    if (cyGridster.value) {
      // @ts-ignore
      cyGridster.value.init()
    }
  })
})
</script>

<template>
  <CanvasCore
    ref="cyGridster"
    :base-width="baseWidth"
    :base-height="baseHeight"
    :base-margin-left="baseMarginLeft"
    :base-margin-top="baseMarginTop"
    :canvas-component-data="componentData"
  ></CanvasCore>
</template>

<style scoped lang="less"></style>
