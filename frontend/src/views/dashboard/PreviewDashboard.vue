<script setup lang="ts">
import DsCanvasCore from '@/views/dashboard/canvas/DsCanvasCore.vue'
import { nextTick, onMounted, ref } from 'vue'
const cyGridster = ref(null)
const baseWidth = ref(0)
const baseHeight = ref(0)
const baseMarginLeft = ref(0)
const baseMarginTop = ref(0)
const componentData = ref([
  {
    id: 4,
    x: 1,
    y: 1,
    sizeX: 2,
    sizeY: 2,
    _dragId: 0
  },
  {
    id: 10,
    x: 2,
    y: 1,
    sizeX: 2,
    sizeY: 2,
    _dragId: 1
  },
  {
    id: 7,
    x: 1,
    y: 2,
    sizeX: 2,
    sizeY: 3,
    _dragId: 2
  }
])

onMounted(() => {
  const screenWidth = window.innerWidth
  const screenHeight = window.innerHeight
  baseWidth.value = 90.8333 * (screenWidth / 1366)
  baseHeight.value = 100 * (screenHeight / 638)
  baseMarginLeft.value = 20 * (screenWidth / 1366)
  baseMarginTop.value = 20 * (screenHeight / 638)
  nextTick(() => {
    if (cyGridster.value) {
      // @ts-ignore
      cyGridster.value.init()
    }
  })
})
</script>

<template>
  <DsCanvasCore ref="cyGridster" :canvas-component-data="componentData"></DsCanvasCore>
</template>

<style scoped lang="less"></style>
