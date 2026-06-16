<script setup lang="ts">
import CanvasCore from '@/views/dashboard/canvas/CanvasCore.vue'
import { computed, nextTick, onMounted, type PropType, ref } from 'vue'
import type { CanvasItem } from '@/utils/canvas.ts'
import { useEmitt, useEmittLazy } from '@/utils/useEmitt.ts'

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
  canvasViewInfo: {
    type: Object,
    required: false,
    default: () => {},
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
  inTab: {
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
    baseMarginLeft.value = 0
    baseMarginTop.value = 0
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    const screenWidth = dashboardEditorRef.value.offsetWidth
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    const screenHeight = dashboardEditorRef.value.offsetHeight
    baseWidth.value =
      (screenWidth - baseMarginLeft.value) / props.baseMatrixCount.x - baseMarginLeft.value
    baseHeight.value =
      (screenHeight - baseMarginTop.value) / props.baseMatrixCount.y - baseMarginTop.value
    useEmittLazy('view-render-all')
  }
}

const addItemToBox = (item: CanvasItem) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  canvasCoreRef.value.addItemBox(item)
}

const findPositionX = (width: number) => {
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  return canvasCoreRef.value.findPositionX(width)
}

const gridStyle = computed(() => {
  const gridStepX = baseWidth.value + baseMarginLeft.value
  const gridStepY = baseHeight.value + baseMarginTop.value
  if (gridStepX <= 0 || gridStepY <= 0) {
    return {}
  }

  return {
    '--dashboard-grid-step-x': `${gridStepX}px`,
    '--dashboard-grid-step-y': `${gridStepY}px`,
    '--dashboard-grid-offset-x': `${baseMarginLeft.value}px`,
    '--dashboard-grid-offset-y': `${baseMarginTop.value}px`,
  }
})

useEmitt({
  name: 'custom-canvas-resize',
  callback: canvasSizeInit,
})

defineExpose({
  canvasSizeInit,
  addItemToBox,
  findPositionX,
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
    :class="{ 'move-in-active': moveInActive, 'is-tab-editor': inTab }"
    :style="gridStyle"
  >
    <CanvasCore
      ref="canvasCoreRef"
      :base-width="baseWidth"
      :base-height="baseHeight"
      :base-margin-left="baseMarginLeft"
      :base-margin-top="baseMarginTop"
      :canvas-component-data="canvasComponentData"
      :canvas-style-data="canvasStyleData"
      :canvas-view-info="canvasViewInfo"
      :dashboard-info="dashboardInfo"
      :parent-config-item="parentConfigItem"
      :canvas-id="canvasId"
      @parent-add-item-box="(item) => emits('parentAddItemBox', item)"
    ></CanvasCore>
  </div>
</template>

<style scoped lang="less">
.dashboard-editor-main {
  --dashboard-grid-line-color: rgba(31, 35, 41, 0.08);
  --dashboard-grid-bg: #f7f9fb;
  width: 100%;
  height: 100%;
  overflow-y: auto;
  background-color: var(--dashboard-grid-bg);

  :deep(.dragAndResize) {
    background-color: var(--dashboard-grid-bg);
    background-image:
      linear-gradient(var(--dashboard-grid-line-color) 1px, transparent 1px),
      linear-gradient(90deg, var(--dashboard-grid-line-color) 1px, transparent 1px);
    background-position: var(--dashboard-grid-offset-x, 16px) var(--dashboard-grid-offset-y, 16px);
    background-size:
      var(--dashboard-grid-step-x, 16px) var(--dashboard-grid-step-y, 16px),
      var(--dashboard-grid-step-x, 16px) var(--dashboard-grid-step-y, 16px);
  }

  &::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
  }
  :deep(.ed-empty__description) {
    width: 240px !important;
  }
}

.move-in-active {
  border: 2px dotted blueviolet;
  margin: -2px;
}

.is-tab-editor {
  --dashboard-grid-bg: #ffffff;
  --dashboard-item-gap: 8px;
  background-color: #ffffff !important;

  :deep(.dragAndResize) {
    background-color: #ffffff !important;
    background-image: none !important;
  }

  :deep(.item) {
    background-color: #ffffff;
  }
}
</style>
