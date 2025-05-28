<script setup lang="ts">
import {type CanvasItem} from '@/utils/canvas.ts'
import {ref, toRefs, type PropType} from 'vue'
import ResizeHandle from "@/views/dashboard/canvas/ResizeHandle.vue";

const shapeRef = ref(null)
// Props
const props = defineProps({
  configItem: {
    type: Object as PropType<CanvasItem>,
    required: true
  },
  itemIndex: {
    type: Number,
    required: true
  },
  moveAnimate: {
    type: Boolean,
    required: true
  },
  draggable: {
    type: Boolean,
    required: true
  },
  startMove: {
    type: Function,
    default: () => {
      return {}
    }
  },
  startResize: {
    type: Function,
    default: () => {
      return {}
    }
  }
})

const { draggable } = toRefs(props)
</script>

<template>
  <div :class="{
        item: true,
        itemCursorDefault: configItem.component === 'SQTab',
        moveAnimation: moveAnimate,
        movingItem: configItem.isPlayer,
        canNotDrag: !draggable
    }" @mousedown="startMove($event, configItem, itemIndex)" ref="shapeRef">
    <slot></slot>
    <resize-handle
        :start-resize="(event : MouseEvent, point: string) => startResize(event, point, configItem, itemIndex)">
    </resize-handle>
  </div>
</template>

<style scoped lang="less">
@import '../css/CanvasStyle.less';
</style>