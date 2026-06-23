<script setup lang="ts">
import elementResizeDetectorMaker from 'element-resize-detector'

const dashboardStore = dashboardStoreWithOut()
const { curComponent } = storeToRefs(dashboardStore)

import { onMounted, toRefs, ref, computed, reactive, onBeforeUnmount } from 'vue'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard.ts'
import { storeToRefs } from 'pinia'
import SQComponentWrapper from '@/views/dashboard/preview/SQComponentWrapper.vue'
import type { CanvasItem } from '@/utils/canvas.ts'
import { useEmittLazy } from '@/utils/useEmitt.ts'
import { getPreviewComponentSizeY } from '@/views/dashboard/utils/chartSizing.ts'

const props = defineProps({
  canvasStyleData: {
    type: Object,
    required: false,
    default: () => {},
  },
  componentData: {
    type: Object,
    required: true,
  },
  canvasViewInfo: {
    type: Object,
    required: true,
  },
  dashboardInfo: {
    type: Object,
    required: false,
    default: () => {},
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
  canvasId: {
    type: String,
    required: false,
    default: 'canvas-main',
  },
  showPosition: {
    required: false,
    type: String,
    default: 'preview',
  },
  inTab: {
    type: Boolean,
    default: false,
  },
})

const { showPosition, canvasId } = toRefs(props)
const domId = 'preview-' + canvasId.value
const previewCanvas = ref(null)
const renderReady = ref(true)
const state = reactive({
  initState: true,
  scrollMain: 0,
})

const cellWidth = ref(0)
const cellHeight = ref(0)
const baseWidth = ref(0)
const baseHeight = ref(0)
const baseMarginLeft = ref(0)
const baseMarginTop = ref(0)
const PREVIEW_GRID_GAP = 10
const TAB_PREVIEW_GRID_GAP = 6
let resizeObserver: ResizeObserver | undefined
const canvasStyle = computed(() => {
  if (props.inTab) {
    return { background: '#ffffff' }
  }
  return { background: 'var(--workspace-panel-bg, var(--theme-panel-bg))' }
})
const displayComponentData = computed(() =>
  Array.isArray(props.componentData) ? props.componentData : []
)

const restore = () => {}

function nowItemStyle(item: CanvasItem) {
  const sizeY = getPreviewComponentSizeY(item, props.canvasViewInfo?.[item.id])
  return {
    width: cellWidth.value * item.sizeX - baseMarginLeft.value + 'px',
    height: cellHeight.value * sizeY - baseMarginTop.value + 'px',
    left: cellWidth.value * (item.x - 1) + baseMarginLeft.value + 'px',
    top: cellHeight.value * (item.y - 1) + baseMarginTop.value + 'px',
  }
}

const sizeInit = () => {
  if (previewCanvas.value) {
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    const screenWidth = previewCanvas.value.offsetWidth
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    const screenHeight = previewCanvas.value.offsetHeight
    const gridGap = props.inTab ? TAB_PREVIEW_GRID_GAP : PREVIEW_GRID_GAP
    baseMarginLeft.value = gridGap
    baseMarginTop.value = gridGap
    baseWidth.value =
      (screenWidth - baseMarginLeft.value) / props.baseMatrixCount.x - baseMarginLeft.value
    baseHeight.value =
      (screenHeight - baseMarginTop.value) / props.baseMatrixCount.y - baseMarginTop.value
    cellWidth.value = baseWidth.value + baseMarginLeft.value
    cellHeight.value = baseHeight.value + baseMarginTop.value
  }
  useEmittLazy('view-render-all')
}

onMounted(() => {
  sizeInit()
  if (previewCanvas.value) {
    resizeObserver = new ResizeObserver(sizeInit)
    resizeObserver.observe(previewCanvas.value)
  }
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  elementResizeDetectorMaker().listenTo(document.getElementById(domId), sizeInit)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
})

defineExpose({
  restore,
})
</script>

<template>
  <div
    v-if="state.initState"
    :id="domId"
    ref="previewCanvas"
    class="canvas-container"
    :class="{ 'is-tab-preview': inTab }"
    :style="canvasStyle"
  >
    <template v-if="renderReady">
      <SQComponentWrapper
        v-for="(item, index) in displayComponentData"
        :key="index"
        :active="!!curComponent && item.id === curComponent['id']"
        :config-item="item"
        :canvas-view-info="canvasViewInfo"
        :show-position="showPosition"
        :canvas-id="canvasId"
        :style="nowItemStyle(item)"
        :index="index"
        :frameless="inTab"
      />
    </template>
  </div>
</template>

<style lang="less" scoped>
.canvas-container {
  background-size: 100% 100% !important;
  width: 100%;
  height: 100%;
  padding: 0;
  overflow-x: hidden;
  overflow-y: auto;
  position: relative;
  &::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
  }

  div::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
  }

  div {
    -ms-overflow-style: none; /* IE and Edge */
    scrollbar-width: none; /* Firefox */
  }
}

.is-tab-preview {
  background: #ffffff !important;

  :deep(.wrapper-outer),
  :deep(.wrapper-inner) {
    background: #ffffff !important;
  }
}

.fix-button {
  position: fixed !important;
}

.datav-preview {
  overflow-y: hidden !important;
}

.datav-preview-unpublish {
  background-color: inherit !important;
}
</style>
