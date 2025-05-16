<script setup lang="ts">
import { type CanvasItem } from '../utils/CanvasUtils'
import { ref, toRefs, type PropType } from 'vue'
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
    baseWidth: {
        type: Number,
        default: 100
    },
    baseHeight: {
        type: Number,
        default: 50
    },
    baseMarginLeft: {
        type: Number,
        default: 20
    },
    baseMarginTop: {
        type: Number,
        default: 20
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

const {
  baseWidth,
  baseHeight,
  baseMarginLeft,
  baseMarginTop,
  draggable,
} = toRefs(props)

const cursors = {
  lt: 'nw',
  t: 'n',
  rt: 'ne',
  r: 'e',
  rb: 'se',
  b: 's',
  lb: 'sw',
  l: 'w'
}

function getPointStyle(point: string) {
  const hasT = /t/.test(point)
  const hasB = /b/.test(point)
  const hasL = /l/.test(point)
  const hasR = /r/.test(point)
  let newLeft = '0px'
  let newTop = '0px'

  // Points at the four corners
  if (point.length === 2) {
    newLeft = hasL ? '0px' : '100%'
    newTop = hasT ? '0px' : '100%'
  } else {
    // The point between the upper and lower points, with a width centered
    if (hasT || hasB) {
      newLeft = '50%'
      newTop = hasT ? '0px' : '100%'
    }

    // The points on both sides are centered in height
    if (hasL || hasR) {
      newLeft = hasL ? '0px' : '100%'
      newTop ='50%'
    }
  }

  return {
    marginLeft: '-4px',
    marginTop: '-4px',
    left: `${newLeft}`,
    top: `${newTop}`,
    // @ts-expect-error
    cursor: `${cursors[point]}-resize`
  }
}

const pointList = ['lt', 't', 'rt', 'r', 'rb', 'b', 'lb', 'l']
</script>

<template>
    <div :class="{
        item: true,
        moveAnimation: moveAnimate,
        movingItem: configItem.isPlayer,
        canNotDrag: !draggable
    }" @mousedown="startMove($event, configItem, itemIndex)" ref="shapeRef">
        <slot></slot>
        <div v-for="point in pointList" :key="point" class="resizeHandle" :style="getPointStyle(point, configItem)"
            @mousedown="startResize($event, point, configItem, itemIndex)"></div>
    </div>
</template>

<style scoped lang="less">
@import '../css/CanvasStyle.less';
</style>