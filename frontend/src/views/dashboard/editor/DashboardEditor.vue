<script setup lang="ts">
import CanvasCore from '@/views/dashboard/canvas/CanvasCore.vue'
import { nextTick, onMounted, type PropType, ref } from 'vue'
import type { CanvasItem } from '@/utils/canvas.ts'

const canvasCoreRef = ref(null)
const dashboardEditorRef = ref(null)
const baseWidth = ref(0)
const baseHeight = ref(0)
const baseMarginLeft = ref(0)
const baseMarginTop = ref(0)

// Props
const props = defineProps({
  canvasId: {
    type: String,
    default: 'canvas-main',
  },
  parentConfigItem: {
    type: Object as PropType<CanvasItem>,
    required: false,
    default: null,
  },
  dashboardInfo: {
    type: Object,
    required: false,
    default: null,
  },
  canvasStyleData: {
    type: Object,
    required: false,
    default: null,
  },
  canvasComponentData: {
    type: Array as PropType<CanvasItem[]>,
    required: true,
  },
  baseMatrixCount: {
    type: Object,
    default: () => {
      return {
        x: 72,
        y: 36,
      }
    },
  },
  moveInActive: {
    type: Boolean,
    default: false,
  },
})

const canvasSizeInit = () => {
  sizeInit()
  if (canvasCoreRef.value) {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    canvasCoreRef.value.sizeInit()
  }
}

const sizeInit = () => {
  if (dashboardEditorRef.value) {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    const screenWidth = dashboardEditorRef.value.offsetWidth
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    const screenHeight = dashboardEditorRef.value.offsetHeight
    baseMarginLeft.value = 10
    baseMarginTop.value = 10
    baseWidth.value =
      (screenWidth - baseMarginLeft.value) / props.baseMatrixCount.x - baseMarginLeft.value
    baseHeight.value =
      (screenHeight - baseMarginTop.value) / props.baseMatrixCount.y - baseMarginTop.value
  }
}

const addItemToBox = (item: CanvasItem) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  canvasCoreRef.value.addItemBox(item)
}

defineExpose({
  canvasSizeInit,
  addItemToBox,
})

onMounted(() => {
  window.addEventListener('resize', canvasSizeInit)
  nextTick(() => {
    if (dashboardEditorRef.value) {
      sizeInit()
      nextTick(() => {
        if (canvasCoreRef.value) {
          // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
          canvasCoreRef.value.init()
        }
      })
    }
  })
})
const emits = defineEmits(['parentAddItemBox'])
</script>

<template>
  <div
    ref="dashboardEditorRef"
    class="dashboard-editor-main"
    :class="{ 'move-in-active': moveInActive }"
  >
    <CanvasCore
      ref="canvasCoreRef"
      :base-width="baseWidth"
      :base-height="baseHeight"
      :base-margin-left="baseMarginLeft"
      :base-margin-top="baseMarginTop"
      :canvas-component-data="canvasComponentData"
      :canvas-style-data="canvasStyleData"
      :dashboard-info="dashboardInfo"
      :parent-config-item="parentConfigItem"
      :canvas-id="canvasId"
      @parent-add-item-box="(item) => emits('parentAddItemBox', item)"
    ></CanvasCore>
  </div>
</template>

<style scoped lang="less">
.dashboard-editor-main {
  width: 100%;
  height: 100%;
  overflow-y: auto;
}

.move-in-active {
  border: 2px dotted blueviolet;
  margin: -2px;
}
</style>
