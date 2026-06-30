<script setup lang="ts">
import { computed, ref, nextTick, toRefs, type PropType, onMounted, getCurrentInstance } from 'vue'
import _ from 'lodash'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard'
import { type CanvasCoord, type CanvasItem } from '@/utils/canvas.ts'
import CanvasShape from './CanvasShape.vue'
import { findComponent } from '@/views/dashboard/components/component-list.ts'
import { storeToRefs } from 'pinia'
import { useEmitt, useEmittLazy } from '@/utils/useEmitt.ts'
import html2canvas from 'html2canvas'
import EmptyBackground from '@/views/dashboard/common/EmptyBackgroundSvgMain.vue'
import { useI18n } from 'vue-i18n'
import { isMainCanvas } from '@/views/dashboard/utils/canvasUtils.ts'
import DashboardSqlEditor from '@/views/dashboard/common/DashboardSqlEditor.vue'

const { t } = useI18n()
const dashboardStore = dashboardStoreWithOut()
const canvasLocked = ref(false) // Is the canvas movement locked， Default false
const emits = defineEmits(['parentAddItemBox'])
const { curComponentId, curComponent, fullscreenFlag } = storeToRefs(dashboardStore)
let currentInstance: any
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
    default: () => {},
  },
  canvasStyleData: {
    type: Object,
    required: false,
    default: () => {},
  },
  canvasViewInfo: {
    type: Object,
    required: false,
    default: () => {},
  },
  canvasComponentData: {
    type: Array as PropType<CanvasItem[]>,
    required: true,
  },
  baseWidth: {
    type: Number,
    default: 100,
  },
  baseHeight: {
    type: Number,
    default: 50,
  },
  baseMarginLeft: {
    type: Number,
    default: 20,
  },
  baseMarginTop: {
    type: Number,
    default: 20,
  },
  draggable: {
    type: Boolean,
    default: true,
  },
  dragStart: {
    type: Function,
    default: () => {
      return {}
    },
  },
  dragging: {
    type: Function,
    default: () => {
      return {}
    },
  },
  dragEnd: {
    type: Function,
    default: () => {
      return {}
    },
  },
  resizable: {
    type: Boolean,
    default: true,
  },
  showComponentBar: {
    type: Boolean,
    default: true,
  },
  canEditSql: {
    type: Boolean,
    default: true,
  },
  platformTemplate: {
    type: Boolean,
    default: false,
  },
  resizeStart: {
    type: Function,
    default: () => {
      return {}
    },
  },
  resizing: {
    type: Function,
    default: () => {
      return {}
    },
  },
  resizeEnd: {
    type: Function,
    default: () => {
      return {}
    },
  },
})

const sqlEditorVisible = ref(false)
const editingViewId = ref<string | null>(null)
const editingViewInfo = computed(() => {
  if (!editingViewId.value) {
    return null
  }
  return props.canvasViewInfo?.[editingViewId.value] || null
})
const dashboardCanEdit = computed(() => {
  const value = props.dashboardInfo?.canEdit ?? dashboardStore.dashboardInfo?.canEdit
  return value !== false
})
const dashboardCanShare = computed(() => {
  const value =
    props.dashboardInfo?.canShare ??
    dashboardStore.dashboardInfo?.canShare ??
    props.dashboardInfo?.canEdit ??
    dashboardStore.dashboardInfo?.canEdit
  return value === true
})

const editSql = (id: string) => {
  editingViewId.value = id
  sqlEditorVisible.value = true
}

const onSqlApplied = (viewInfo: any) => {
  nextTick(() => {
    if (viewInfo?.id) {
      useEmitt().emitter.emit(`view-render-${viewInfo.id}`)
      return
    }
    useEmitt().emitter.emit('view-render-all')
  })
}

const {
  canvasComponentData,
  baseWidth,
  baseHeight,
  baseMarginLeft,
  baseMarginTop,
  draggable,
  resizable,
} = toRefs(props)

// DOM ref
const containerRef = ref<HTMLElement | null>(null)
const renderOk = ref(false)
const moveAnimate = ref(false)
const cellWidth = ref(0)
const cellHeight = ref(0)
const maxCell = ref(0)
const positionBox = ref<Array<Array<{ el: boolean }>>>([])
const coordinates = ref<CanvasCoord[]>([])
const infoBox = ref()

// Position data (non-reactive)
let lastTask: (() => void) | undefined = undefined
let isOverlay = false
let itemMaxX = 0
let itemMaxY = 0
const moveTime = 80

const tabMoveInYOffset = 30
const tabMoveOutXOffset = 30
const tabMoveOutYOffset = 30
// Effective area of collision depth
const collisionGap = 10
const insertDropMinOverlapRatio = 0.25

type GridFrame = { x: number; y: number; sizeX: number; sizeY: number }
type LayoutSnapshot = Array<{ item: CanvasItem; frame: GridFrame }>
type MoveDropMode = 'place' | 'insert' | 'invalid'
type LayoutFramePlan = Map<CanvasItem, GridFrame>

function debounce(func: () => void, time: number) {
  if (!isOverlay) {
    isOverlay = true
    setTimeout(() => {
      func()
      setTimeout(() => {
        isOverlay = false
        if (lastTask !== undefined) {
          const nextTask = lastTask
          lastTask = undefined
          debounce(nextTask, time)
        }
      }, moveTime)
    }, time)
    lastTask = undefined
  } else {
    lastTask = func
  }
}

function scrollScreen(e: MouseEvent) {
  const scrollStep = 20
  const bufferBottom = 50
  const bufferTop = 150
  if (e.clientY + bufferBottom >= window.innerHeight) {
    document.documentElement.scrollTop += scrollStep
  } else if (e.clientY <= bufferTop) {
    document.documentElement.scrollTop -= scrollStep
  }
}

/**
 * Reset Position Box
 */
function resetPositionBox() {
  itemMaxX = maxCell.value
  const rows = 1 // Set only one line initially
  for (let i = 0; i < rows; i++) {
    const row = []
    for (let j = 0; j < maxCell.value; j++) {
      row.push({ el: false })
    }
    positionBox.value.push(row)
  }
}

/**
 * Fill Position Box
 *
 * @param {CanvasItem} item
 */
function addItemToPositionBox(item: CanvasItem) {
  const pb = positionBox.value
  if (item.x <= 0 || item.y <= 0) return
  // Traverse the grid at the target location and add the item to it
  for (let i = item.x - 1; i < item.x - 1 + item.sizeX; i++) {
    for (let j = item.y - 1; j < item.y - 1 + item.sizeY; j++) {
      if (pb[j] && pb[j][i]) {
        // Ensure the target location is valid & Place the item in the corresponding position
        // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
        pb[j][i].el = item
      }
    }
  }
}

function fillPositionBox(maxY: number) {
  const pb = positionBox.value
  maxY += 2
  for (let j = 0; j < maxY; j++) {
    if (pb[j] === undefined) {
      const row = []
      for (let i = 0; i < itemMaxX; i++) {
        row.push({ el: false })
      }
      pb.push(row)
    }
  }
  itemMaxY = maxY
  // Update container height
  if (containerRef.value) {
    containerRef.value.style.height = `${(itemMaxY + 2) * cellHeight.value}px`
  }
}

/**
 * Remove item from positionBox
 * @param item
 */
function removeItemFromPositionBox(item: CanvasItem) {
  const pb = positionBox.value
  if (item.x <= 0 || item.y <= 0) return
  // Traverse the area occupied by the item and remove it
  for (let i = item.x - 1; i < item.x - 1 + item.sizeX; i++) {
    for (let j = item.y - 1; j < item.y - 1 + item.sizeY; j++) {
      if (pb[j] && pb[j][i]) {
        // Ensure the target location is valid
        pb[j][i].el = false // Remove item and set it to false or null
      }
    }
  }
}

function rebuildPositionBox() {
  positionBox.value = []
  resetPositionBox()

  const maxBottom = canvasComponentData.value.reduce((max, item) => {
    return Math.max(max, item.y + item.sizeY)
  }, 1)

  fillPositionBox(maxBottom)
  canvasComponentData.value.forEach((item) => addItemToPositionBox(item))
}

function getItemGridFrame(item: CanvasItem): GridFrame {
  return {
    x: item.x,
    y: item.y,
    sizeX: item.sizeX,
    sizeY: item.sizeY,
  }
}

function normalizeGridFrame(frame: GridFrame): GridFrame {
  const safeMaxCell = Math.max(itemMaxX, 1)
  const sizeX = Math.max(1, Math.min(Math.round(frame.sizeX), safeMaxCell))
  const sizeY = Math.max(1, Math.round(frame.sizeY))
  const x = Math.min(Math.max(Math.round(frame.x), 1), Math.max(1, safeMaxCell - sizeX + 1))
  const y = Math.max(Math.round(frame.y), 1)

  return { x, y, sizeX, sizeY }
}

function isSameCanvasItem(a: CanvasItem, b: CanvasItem) {
  return (
    a === b ||
    (a._dragId !== undefined && a._dragId === b._dragId) ||
    (a.id !== undefined && a.id === b.id)
  )
}

function isGridFrameOverlap(
  a: GridFrame,
  b: GridFrame
) {
  return (
    a.x < b.x + b.sizeX &&
    a.x + a.sizeX > b.x &&
    a.y < b.y + b.sizeY &&
    a.y + a.sizeY > b.y
  )
}

function getGridFrameOverlapArea(a: GridFrame, b: GridFrame) {
  const overlapWidth = Math.max(0, Math.min(a.x + a.sizeX, b.x + b.sizeX) - Math.max(a.x, b.x))
  const overlapHeight = Math.max(0, Math.min(a.y + a.sizeY, b.y + b.sizeY) - Math.max(a.y, b.y))
  return overlapWidth * overlapHeight
}

function getDisplacedItemOverlapRatio(itemFrame: GridFrame, displacedFrame: GridFrame) {
  const displacedArea = displacedFrame.sizeX * displacedFrame.sizeY
  if (displacedArea <= 0) {
    return 0
  }

  return getGridFrameOverlapArea(itemFrame, displacedFrame) / displacedArea
}

function canPlaceGridFrame(item: CanvasItem, frame: GridFrame) {
  return !canvasComponentData.value.some((otherItem) => {
    if (isSameCanvasItem(item, otherItem)) {
      return false
    }
    return isGridFrameOverlap(frame, getItemGridFrame(otherItem))
  })
}

function getOverlappingGridItems(item: CanvasItem, frame: GridFrame) {
  return canvasComponentData.value.filter((otherItem) => {
    if (isSameCanvasItem(item, otherItem)) {
      return false
    }
    return isGridFrameOverlap(frame, getItemGridFrame(otherItem))
  })
}

function getDisplaceableGridItems(item: CanvasItem, frame: GridFrame) {
  const overlappingItems = getOverlappingGridItems(item, frame)

  return overlappingItems.filter((otherItem) => {
    return getDisplacedItemOverlapRatio(frame, getItemGridFrame(otherItem)) >= insertDropMinOverlapRatio
  })
}

function getMoveDropMode(item: CanvasItem, frame: GridFrame): MoveDropMode {
  if (canPlaceGridFrame(item, frame)) {
    return 'place'
  }

  const overlappingItems = getOverlappingGridItems(item, frame)
  const displaceableItems = getDisplaceableGridItems(item, frame)

  return overlappingItems.length > 0 && overlappingItems.length === displaceableItems.length
    ? 'insert'
    : 'invalid'
}

function createLayoutSnapshot(): LayoutSnapshot {
  return canvasComponentData.value.map((item) => ({
    item,
    frame: getItemGridFrame(item),
  }))
}

function restoreLayoutSnapshot(snapshot: LayoutSnapshot) {
  snapshot.forEach(({ item, frame }) => {
    item.x = frame.x
    item.y = frame.y
    item.sizeX = frame.sizeX
    item.sizeY = frame.sizeY
  })
  rebuildPositionBox()
  snapshot.forEach(({ item }) => changeItemCoord(item))
}

function isGridFrameWithinCanvas(frame: GridFrame) {
  return (
    frame.x >= 1 &&
    frame.y >= 1 &&
    frame.sizeX >= 1 &&
    frame.sizeY >= 1 &&
    frame.x + frame.sizeX - 1 <= itemMaxX
  )
}

function getPlannedGridFrame(item: CanvasItem, plan: LayoutFramePlan) {
  return plan.get(item) || getItemGridFrame(item)
}

function canApplyLayoutFramePlan(plan: LayoutFramePlan) {
  const items = canvasComponentData.value

  for (const item of items) {
    if (!isGridFrameWithinCanvas(getPlannedGridFrame(item, plan))) {
      return false
    }
  }

  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      if (
        isGridFrameOverlap(getPlannedGridFrame(items[i], plan), getPlannedGridFrame(items[j], plan))
      ) {
        return false
      }
    }
  }

  return true
}

function applyLayoutFramePlan(plan: LayoutFramePlan) {
  plan.forEach((frame, item) => {
    item.x = frame.x
    item.y = frame.y
    item.sizeX = frame.sizeX
    item.sizeY = frame.sizeY
  })
  rebuildPositionBox()
  plan.forEach((_frame, item) => changeItemCoord(item))
}

function getGridFrameGroupBounds(items: CanvasItem[]) {
  const frames = items.map((item) => getItemGridFrame(item))
  const minX = Math.min(...frames.map((frame) => frame.x))
  const minY = Math.min(...frames.map((frame) => frame.y))
  const maxX = Math.max(...frames.map((frame) => frame.x + frame.sizeX))
  const maxY = Math.max(...frames.map((frame) => frame.y + frame.sizeY))

  return {
    minX,
    minY,
    width: maxX - minX,
    height: maxY - minY,
  }
}

function buildTranslatedFramePlan(
  item: CanvasItem,
  targetFrame: GridFrame,
  displacedItems: CanvasItem[],
  deltaX: number,
  deltaY: number
) {
  const plan: LayoutFramePlan = new Map([[item, targetFrame]])

  displacedItems.forEach((displacedItem) => {
    const frame = getItemGridFrame(displacedItem)
    plan.set(displacedItem, {
      ...frame,
      x: frame.x + deltaX,
      y: frame.y + deltaY,
    })
  })

  return plan
}

function buildSwapMovePlan(item: CanvasItem, targetFrame: GridFrame, displacedItems: CanvasItem[]) {
  const sourceFrame = getItemGridFrame(item)
  const groupBounds = getGridFrameGroupBounds(displacedItems)

  if (groupBounds.width > sourceFrame.sizeX || groupBounds.height > sourceFrame.sizeY) {
    return null
  }

  return buildTranslatedFramePlan(
    item,
    targetFrame,
    displacedItems,
    sourceFrame.x - groupBounds.minX,
    sourceFrame.y - groupBounds.minY
  )
}

function buildSqueezeMovePlan(item: CanvasItem, targetFrame: GridFrame, displacedItems: CanvasItem[]) {
  const groupBounds = getGridFrameGroupBounds(displacedItems)

  return buildTranslatedFramePlan(
    item,
    targetFrame,
    displacedItems,
    0,
    targetFrame.y + targetFrame.sizeY - groupBounds.minY
  )
}

function buildLocalMovePlan(item: CanvasItem, frame: GridFrame, mode: MoveDropMode) {
  if (mode === 'invalid') {
    return null
  }

  if (mode === 'place') {
    const plan: LayoutFramePlan = new Map([[item, frame]])
    return canApplyLayoutFramePlan(plan) ? plan : null
  }

  const displacedItems = _.sortBy(getDisplaceableGridItems(item, frame), ['y', 'x'])
  if (displacedItems.length === 0) {
    return null
  }

  const swapPlan = buildSwapMovePlan(item, frame, displacedItems)
  if (swapPlan && canApplyLayoutFramePlan(swapPlan)) {
    return swapPlan
  }

  const squeezePlan = buildSqueezeMovePlan(item, frame, displacedItems)
  return canApplyLayoutFramePlan(squeezePlan) ? squeezePlan : null
}

/**
 * Recalculate the width so that the smallest cell can fill the entire container
 */
function recomputeCellWidth() {
  if (!containerRef.value) return
  maxCell.value = Math.floor(containerRef.value.offsetWidth / cellWidth.value)
}

function sizeInit() {
  cellsInit()
  recomputeCellWidth()
  itemMaxX = maxCell.value
}

function cellsInit() {
  cellWidth.value = baseWidth.value + baseMarginLeft.value
  cellHeight.value = baseHeight.value + baseMarginTop.value
}

function init() {
  cellsInit()

  positionBox.value = []
  coordinates.value = []

  lastTask = undefined
  isOverlay = false
  itemMaxX = 0
  itemMaxY = 0

  recomputeCellWidth()
  resetPositionBox()

  let i = 0
  const timeId = setInterval(() => {
    if (i >= canvasComponentData.value.length) {
      clearInterval(timeId)
      nextTick(() => {
        moveAnimate.value = true
      })
    } else {
      const item = canvasComponentData.value[i]
      addItem(item, i)
      i++
    }
  }, 1)
  renderOk.value = true
}

/**
 * Check the position of the movement, if it is illegal, it will be automatically modified
 *
 * @param {CanvasItem} item
 * @param {any} position
 */
function checkItemPosition(item: CanvasItem, position: Partial<{ x: number; y: number }> = {}) {
  position.x = position.x || item.x
  position.y = position.y || item.y

  // Limit minimum coordinates
  if (item.x < 1) item.x = 1
  if (item.y < 1) item.y = 1

  // Limit minimum size
  if (item.sizeX < 1) item.sizeX = 1
  if (item.sizeY < 1) item.sizeY = 1

  // Limit maximum width
  if (item.sizeX > itemMaxX) item.sizeX = itemMaxX

  // Limit the right side to not exceed the boundary
  if (item.x + item.sizeX - 1 > itemMaxX) {
    item.x = itemMaxX - item.sizeX + 1
    if (item.x < 1) item.x = 1
  }

  // If the height of the item exceeds the current maximum number of rows, fill the position table
  if (item.y + item.sizeY > itemMaxY - 1) {
    fillPositionBox(item.y + item.sizeY - 1)
  }
}

/**
 * Move the element being dragged
 *
 * @param {CanvasItem} item
 * @param {any} position
 */
function movePlayer(item: CanvasItem, position: any) {
  // Remove item location
  removeItemFromPositionBox(item)
  // Find the item below
  let belowItems = findBelowItems(item) as CanvasItem[]
  // Traverse the items below and move them
  belowItems.forEach((upItem) => {
    const canGoUpRows = canItemGoUp(upItem)
    if (canGoUpRows > 0) {
      moveItemUp(upItem, canGoUpRows)
    }
  })
  // Move the current item
  item.x = position.x
  item.y = position.y

  // Check and update the location of items
  checkItemPosition(item, position)
  // Clear the target cell
  emptyTargetCell(item)
  // Add items to the location box
  addItemToPositionBox(item)
  // Modify item coordinates
  changeItemCoord(item)
  // Recheck if the item can be moved up again
  const canGoUpRows = canItemGoUp(item)
  if (canGoUpRows > 0) {
    moveItemUp(item, canGoUpRows)
  }
}

function setPlayerGridFrame(
  item: CanvasItem,
  frame: Partial<{ x: number; y: number; sizeX: number; sizeY: number }>
) {
  const nextFrame = normalizeGridFrame({
    x: frame.x ?? item.x,
    y: frame.y ?? item.y,
    sizeX: frame.sizeX ?? item.sizeX,
    sizeY: frame.sizeY ?? item.sizeY,
  })

  if (!canPlaceGridFrame(item, nextFrame)) {
    return null
  }

  item.x = nextFrame.x
  item.y = nextFrame.y
  item.sizeX = nextFrame.sizeX
  item.sizeY = nextFrame.sizeY

  checkItemPosition(item, nextFrame)
  rebuildPositionBox()
  changeItemCoord(item)

  if (item.component === 'SQView') {
    useEmittLazy(`view-render-${item.id}`)
  }

  return getItemGridFrame(item)
}

function applyMoveGridFrame(item: CanvasItem, frame: GridFrame, mode: MoveDropMode) {
  const plan = buildLocalMovePlan(item, frame, mode)

  if (!plan) {
    return null
  }

  applyLayoutFramePlan(plan)

  if (item.component === 'SQView') {
    useEmittLazy(`view-render-${item.id}`)
  }

  return getItemGridFrame(item)
}

function removeItemById(id: number) {
  const index = canvasComponentData.value.findIndex((item) => item.id === id)
  if (index >= 0) {
    removeItem(index)
    renderOk.value = false
    nextTick(() => {
      renderOk.value = true
    })
  }
}

function removeItem(index: number) {
  const item = canvasComponentData.value[index] as CanvasItem
  removeItemFromPositionBox(item)
  const belowItems = findBelowItems(item) as CanvasItem[]
  belowItems.forEach((upItem) => {
    const canGoUpRows = canItemGoUp(upItem)
    if (canGoUpRows > 0) {
      moveItemUp(upItem, canGoUpRows)
    }
  })
  canvasComponentData.value.splice(index, 1)
  if (item?.component === 'SQView' && item.id && props.canvasViewInfo?.[item.id]) {
    delete props.canvasViewInfo[item.id]
  }
}

function getNextDragId() {
  if (!canvasComponentData.value || canvasComponentData.value.length === 0) {
    return 0
  }
  const validIds = canvasComponentData.value
    .map((item) => item._dragId)
    .filter((id) => id != null && id !== '') // 过滤 null、undefined 和空字符串

  if (validIds.length === 0) {
    return 0
  }
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  const maxDragId = Math.max(...validIds)
  return maxDragId + 1
}

function addItem(item: CanvasItem, index: any) {
  if (index < 0) {
    index = canvasComponentData.value.length
  }
  item._dragId = item.id || getNextDragId()
  checkItemPosition(item, { x: item.x, y: item.y })
  emptyTargetCell(item)
  addItemToPositionBox(item)
  const canGoUpRows = canItemGoUp(item)
  if (canGoUpRows > 0) {
    moveItemUp(item, canGoUpRows)
  }
  // makeCoordinate(item) // If coordinate points need to be generated, untangle the annotations
}

function changeToCoord(left: number, top: number, width: number, height: number) {
  return {
    x1: left,
    x2: left + width,
    y1: top,
    y2: top + height,
    c1: left + width / 2,
    c2: top + height / 2,
  }
}

/**
 * Detect for collisions and take appropriate measures
 *
 * @param {CanvasItem} item comparison object
 * @param {CanvasCoord} tCoord compares the coordinates of the object
 */
function findClosetCoords(item: CanvasItem, tCoord: CanvasCoord) {
  if (isOverlay) return
  let collisionsItem: { centerDistance: number; coord: CanvasCoord }[] = []
  coordinates.value.forEach((nowCoord) => {
    // Avoid comparing yourself to others
    if (item._dragId === nowCoord.el._dragId) {
      return
    }
    // Determine whether a collision has occurred
    if (
      tCoord.x2 < nowCoord.x1 ||
      tCoord.x1 > nowCoord.x2 ||
      tCoord.y2 < nowCoord.y1 ||
      tCoord.y1 > nowCoord.y2
    ) {
      return
    } else {
      collisionsItem.push({
        centerDistance: Math.sqrt(
          Math.pow(tCoord.c1 - nowCoord.c1, 2) + Math.pow(tCoord.c2 - nowCoord.c2, 2)
        ),
        coord: nowCoord,
      })
    }
  })
  if (collisionsItem.length <= 0) {
    return
  }
  isOverlay = true
  collisionsItem = collisionsItem.sort((a, b) => a.centerDistance - b.centerDistance)
  movePlayer(item, {
    x: collisionsItem[0].coord.el.x,
    y: collisionsItem[0].coord.el.y,
  })

  setTimeout(() => {
    isOverlay = false
  }, 200)
}

/**
 * Generate coordinates
 * @param item
 */
function makeCoordinate(item: CanvasItem) {
  let width = cellWidth.value * item.sizeX - baseMarginLeft.value
  let height = cellHeight.value * item.sizeY - baseMarginTop.value
  let left = cellWidth.value * (item.x - 1) + baseMarginLeft.value
  let top = cellHeight.value * (item.y - 1) + baseMarginTop.value

  let coord = {
    x1: left,
    x2: left + width,
    y1: top,
    y2: top + height,
    c1: left + width / 2,
    c2: top + height / 2,
    el: item,
  }

  coordinates.value.push(coord)
}

/**
 * Change the coordinates of the item
 * @param item
 */
function changeItemCoord(item: CanvasItem) {
  let width = cellWidth.value * item.sizeX - baseMarginLeft.value
  let height = cellHeight.value * item.sizeY - baseMarginTop.value
  let left = cellWidth.value * (item.x - 1) + baseMarginLeft.value
  let top = cellHeight.value * (item.y - 1) + baseMarginTop.value

  let coord = {
    x1: left,
    x2: left + width,
    y1: top,
    y2: top + height,
    c1: left + width / 2,
    c2: top + height / 2,
    el: item,
  }

  // Find and update the corresponding coordinates
  const index = coordinates.value.findIndex((o) => o.el._dragId === item._dragId)
  if (index !== -1) {
    coordinates.value.splice(index, 1, coord)
  }
}

/**
 * Clear the elements at the target location
 * @param {any} item Target item
 */
function emptyTargetCell(item: CanvasItem) {
  let belowItems = findBelowItems(item) as CanvasItem[]

  belowItems.forEach((downItem) => {
    if (downItem._dragId === item._dragId) return
    let moveSize = item.y + item.sizeY - downItem.y
    if (moveSize > 0) {
      moveItemDown(downItem, moveSize)
    }
  })
}

/**
 * Can the item at the current location float up
 * @param {CanvasItem} item Current item
 */
function canItemGoUp(item: CanvasItem) {
  let upperRows = 0
  for (let row = item.y - 2; row >= 0; row--) {
    for (let cell = item.x - 1; cell < item.x - 1 + item.sizeX; cell++) {
      if (
        positionBox.value[row] &&
        positionBox.value[row][cell] &&
        positionBox.value[row][cell].el
      ) {
        return upperRows
      }
    }
    upperRows++
  }

  return upperRows
}

/**
 * Before moving, find the element below the currently moving element (recursively)
 *
 * @param {CanvasItem} item
 * @param {number} size
 */
function moveItemDown(item: CanvasItem, size: number) {
  removeItemFromPositionBox(item)

  const belowItems = findBelowItems(item) as CanvasItem[]

  for (const downItem of belowItems) {
    if (downItem._dragId === item._dragId) continue

    const moveSize = calcDiff(item, downItem, size)
    if (moveSize > 0) {
      moveItemDown(downItem, moveSize)
    }
  }

  const targetPosition = {
    y: item.y + size,
  }

  setPlayerPosition(item, targetPosition)
  checkItemPosition(item, targetPosition)

  addItemToPositionBox(item)
  changeItemCoord(item)
}

function setPlayerPosition(item: CanvasItem, position: { x?: number; y?: number } = {}) {
  const targetX = position.x || item.x
  const targetY = position.y || item.y

  item.x = targetX
  item.y = targetY

  if (item.y + item.sizeY > itemMaxY) {
    itemMaxY = item.y + item.sizeY
  }
}

/**
 * Find the maximum distance from a child element to its parent element
 *
 * @param {CanvasItem} parent
 * @param {CanvasItem} son
 * @param {number} size
 */
function calcDiff(parent: CanvasItem, son: CanvasItem, size: number) {
  const diffs = []

  for (let i = son.x - 1; i < son.x - 1 + son.sizeX; i++) {
    let temp_y = 0

    for (let j = parent.y - 1 + parent.sizeY; j < son.y - 1; j++) {
      if (positionBox.value[j][i] && positionBox.value[j][i].el === false) {
        temp_y++
      }
    }

    diffs.push(temp_y)
  }

  const max_diff = Math.max(...diffs)
  size = size - max_diff

  return size > 0 ? size : 0
}

function moveItemUp(item: CanvasItem, size: number) {
  removeItemFromPositionBox(item)

  const belowItems = findBelowItems(item) as CanvasItem[]

  setPlayerPosition(item, {
    y: item.y - size,
  })

  addItemToPositionBox(item)

  changeItemCoord(item)

  for (const upItem of belowItems) {
    const moveSize = canItemGoUp(upItem)
    if (moveSize > 0) {
      moveItemUp(upItem, moveSize)
    }
  }
}

function findBelowItems(item: CanvasItem) {
  const belowItems = {}

  for (let cell = item.x - 1; cell < item.x - 1 + item.sizeX; cell++) {
    for (let row = item.y - 1; row < positionBox.value.length; row++) {
      const target = positionBox.value[row][cell]
      if (target && target.el) {
        // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
        belowItems[target.el._dragId] = target.el
        break
      }
    }
  }

  return _.sortBy(Object.values(belowItems), 'y')
}

function startResize(e: MouseEvent, point: string, item: CanvasItem, index: number) {
  if (!resizable.value) return
  dashboardStore.setCurComponent(item)
  props.resizeStart(e, item, index)

  // Obtain the target element
  if (!infoBox.value) {
    infoBox.value = {} // Reinitialize
  }
  infoBox.value.resizeItem = item
  infoBox.value.resizeItemIndex = index
  // Drag and drop coordinate points
  infoBox.value.point = point
}

function containerClick() {
  // remove current component info
  dashboardStore.setCurComponent(null)
}

function containerMouseDown(e: MouseEvent) {
  if (!infoBox.value) {
    infoBox.value = {} // Reinitialize
  }
  infoBox.value.startX = e.pageX
  infoBox.value.startY = e.pageY
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  if (isMainCanvas(props.canvasId) && curComponent.value?.editing) {
    // do SQtext
  } else {
    e.preventDefault()
    e.stopPropagation()
  }
}

function getNowPosition(addSizeX: number, addSizeY: number, moveXSize: number, moveYSize: number) {
  const point = infoBox.value.point
  const hasT = /t/.test(point)
  const hasB = /b/.test(point)
  const hasL = /l/.test(point)
  const hasR = /r/.test(point)
  // Determine the resizing direction based on the coordinate points
  let nowSizeX = infoBox.value.oldSizeX
  let nowSizeY = infoBox.value.oldSizeY
  let nowX = infoBox.value.oldX
  let nowY = infoBox.value.oldY

  let nowOriginWidth = infoBox.value.originWidth
  let nowOriginHeight = infoBox.value.originHeight
  let nowOriginX = infoBox.value.originX
  let nowOriginY = infoBox.value.originY

  // Move the lowest position from point T
  const nowBottomOriginY = nowOriginY + nowOriginHeight - baseHeight.value
  // Move the lowest position from point L
  const nowLeftOrigin = nowOriginX + nowOriginWidth - baseWidth.value
  const nowBottomX = nowX + nowSizeX - 1
  if (hasR) {
    nowSizeX = Math.max(nowSizeX + addSizeX, 1)
    nowOriginWidth = Math.max(nowOriginWidth + moveXSize, baseWidth.value)
  }
  if (hasB) {
    nowSizeY = Math.max(nowSizeY + addSizeY, 1)
    nowOriginHeight = Math.max(nowOriginHeight + moveYSize, baseHeight.value)
  }

  if (hasL) {
    // Do not exceed the left boundary
    nowSizeX = Math.min(Math.max(nowSizeX - addSizeX, 1), nowBottomX)
    // Move the lowest position from point L
    nowX = Math.min(Math.max(nowX + addSizeX, 1), nowBottomX)

    nowOriginWidth = Math.min(Math.max(nowOriginWidth - moveXSize, baseWidth.value), nowLeftOrigin)
    // Move the lowest position from point L
    nowOriginX = Math.min(Math.max(nowOriginX + moveXSize, 1), nowLeftOrigin)
  }

  if (hasT) {
    nowSizeY = Math.max(nowSizeY - addSizeY, 1)
    nowY = Math.max(nowY + addSizeY, 1)
    nowOriginHeight = Math.max(nowOriginHeight - moveYSize, baseHeight.value)
    // Move the lowest position from point L
    nowOriginY = Math.min(Math.max(nowOriginY + moveYSize, 1), nowBottomOriginY)
  }
  return { nowSizeX, nowSizeY, nowX, nowY, nowOriginWidth, nowOriginHeight, nowOriginX, nowOriginY }
}

function snapDistanceToCell(distance: number, cellSize: number) {
  if (cellSize <= 0) return 0
  return Math.round(distance / cellSize)
}

function positionToCell(position: number, cellSize: number, margin: number) {
  if (cellSize <= 0) return 1
  return Math.max(1, Math.round((position - margin) / cellSize) + 1)
}

function getSnappedItemStyle(x: number, y: number, sizeX: number, sizeY: number) {
  return {
    left: cellWidth.value * (x - 1) + baseMarginLeft.value,
    top: cellHeight.value * (y - 1) + baseMarginTop.value,
    width: Math.max(baseWidth.value, cellWidth.value * sizeX - baseMarginLeft.value),
    height: Math.max(baseHeight.value, cellHeight.value * sizeY - baseMarginTop.value),
  }
}

function limitItemX(x: number, sizeX: number) {
  return Math.min(Math.max(x, 1), Math.max(1, itemMaxX - sizeX + 1))
}

function normalizeResizeFrame(x: number, y: number, sizeX: number, sizeY: number) {
  const normalizedX = Math.max(x, 1)
  const normalizedSizeX = Math.max(1, Math.min(sizeX, itemMaxX - normalizedX + 1))

  return {
    x: normalizedX,
    y: Math.max(y, 1),
    sizeX: normalizedSizeX,
    sizeY: Math.max(sizeY, 1),
  }
}

function isInteractiveDragTarget(target: Element) {
  return Boolean(
    target.closest(
      [
        '.component-bar-main',
        '.bar-more',
        '.ed-dropdown',
        '.ed-dropdown-menu',
        '.ed-button',
        '.ed-input',
        '.ed-select',
        '.ed-tabs__nav',
        '.tox',
        'button',
        'input',
        'textarea',
        'select',
        'a',
        '[contenteditable="true"]',
      ].join(',')
    )
  )
}

function startMove(e: MouseEvent, item: CanvasItem, index: number) {
  canvasLocked.value = false // Reset canvas lock status
  if (!draggable.value) return
  dashboardStore.setCurComponent(item)
  if (!infoBox.value) {
    infoBox.value = {} // Reinitialize
  }

  const target = e.target
  if (!(target instanceof Element)) {
    return
  }
  const targetElement = target
  const className =
    typeof targetElement.className === 'string'
      ? targetElement.className
      : targetElement.getAttribute('class') || ''
  const itemNode = targetElement.closest('.item') as HTMLElement | null
  const isResizeTarget = Boolean(targetElement.closest('.resizeHandle'))

  if (!itemNode || (!isResizeTarget && isInteractiveDragTarget(targetElement))) {
    return
  }

  if (isResizeTarget || className.includes('resizeHandle')) {
    // Handle resize (optional)
  } else if (draggable.value) {
    props.dragStart(e, item, index)
    infoBox.value.moveItem = item
    infoBox.value.moveItemIndex = index
  }
  infoBox.value.cloneItem = null
  infoBox.value.nowItemNode = null
  infoBox.value.nowItemNode = itemNode
  infoBox.value.cloneItem = itemNode.cloneNode(true)
  infoBox.value.cloneItem.classList.add('cloneNode')
  const img = new Image()
  img.classList.add('clone_img')
  const clonedSlot =
    infoBox.value.nowItemNode.querySelector('.item-content') ||
    infoBox.value.nowItemNode.querySelector('.slot-component')

  if (clonedSlot) {
    html2canvas(clonedSlot).then((canvas) => {
      img.src = canvas.toDataURL()
      infoBox.value.cloneItem?.appendChild(img)
    })
  }

  if (containerRef.value) {
    containerRef.value.append(infoBox.value.cloneItem)
  }

  infoBox.value.originX = infoBox.value.cloneItem.offsetLeft
  infoBox.value.originY = infoBox.value.cloneItem.offsetTop
  infoBox.value.oldX = item.x
  infoBox.value.oldY = item.y
  infoBox.value.oldSizeX = item.sizeX
  infoBox.value.oldSizeY = item.sizeY
  infoBox.value.lastValidFrame = getItemGridFrame(item)
  infoBox.value.originalLayoutSnapshot = createLayoutSnapshot()
  infoBox.value.originWidth = infoBox.value.cloneItem.offsetWidth
  infoBox.value.originHeight = infoBox.value.cloneItem.offsetHeight
  const itemMouseMove = (e: MouseEvent) => {
    const moveItem = _.get(infoBox.value, 'moveItem')
    const resizeItem = _.get(infoBox.value, 'resizeItem')

    if (resizeItem) {
      props.resizing(e, resizeItem, resizeItem._dragId)
      infoBox.value.resizeItem.isPlayer = true

      const moveXSize = e.pageX - infoBox.value.startX
      const moveYSize = e.pageY - infoBox.value.startY

      const addSizeX = snapDistanceToCell(moveXSize, cellWidth.value)
      const addSizeY = snapDistanceToCell(moveYSize, cellHeight.value)
      // Determine the resizing direction based on the coordinate points
      const {
        nowSizeX,
        nowSizeY,
        nowX,
        nowY,
      } = getNowPosition(addSizeX, addSizeY, moveXSize, moveYSize)

      const candidateFrame = normalizeGridFrame(
        normalizeResizeFrame(nowX, nowY, nowSizeX, nowSizeY)
      )
      const canPlaceFrame = canPlaceGridFrame(resizeItem, candidateFrame)
      const previewFrame = canPlaceFrame
        ? candidateFrame
        : infoBox.value.lastValidFrame || getItemGridFrame(resizeItem)

      if (canPlaceFrame) {
        infoBox.value.lastValidFrame = candidateFrame
        debounce(() => {
          setPlayerGridFrame(resizeItem, candidateFrame)
        }, 10)
      }

      const snappedStyle = getSnappedItemStyle(
        previewFrame.x,
        previewFrame.y,
        previewFrame.sizeX,
        previewFrame.sizeY
      )
      infoBox.value.cloneItem.style.width = `${snappedStyle.width}px`
      infoBox.value.cloneItem.style.height = `${snappedStyle.height}px`
      infoBox.value.cloneItem.style.left = `${snappedStyle.left}px`
      infoBox.value.cloneItem.style.top = `${snappedStyle.top}px`
    } else if (moveItem) {
      scrollScreen(e)
      if (!draggable.value) return

      props.dragging(e, moveItem, moveItem._dragId)
      moveItem.isPlayer = true
      const moveXSize = e.pageX - infoBox.value.startX
      const moveYSize = e.pageY - infoBox.value.startY

      let nowCloneItemX = infoBox.value.originX + moveXSize
      let nowCloneItemY = infoBox.value.originY + moveYSize
      const candidateX = limitItemX(
        positionToCell(nowCloneItemX, cellWidth.value, baseMarginLeft.value),
        moveItem.sizeX
      )
      const candidateY = positionToCell(nowCloneItemY, cellHeight.value, baseMarginTop.value)
      let newX = candidateX
      let newY = candidateY
      newX = newX > 0 ? newX : 1
      newY = newY > 0 ? newY : 1
      const candidateFrame = normalizeGridFrame({
        x: newX,
        y: newY,
        sizeX: moveItem.sizeX,
        sizeY: moveItem.sizeY,
      })
      infoBox.value.dropFrame = candidateFrame
      const dropMode = getMoveDropMode(moveItem, candidateFrame)
      infoBox.value.dropMode = dropMode
      if (dropMode !== 'invalid') {
        infoBox.value.lastValidFrame = candidateFrame
      }
      infoBox.value.cloneItem.classList.toggle('invalidDrop', dropMode === 'invalid')
      infoBox.value.cloneItem.classList.toggle('insertDrop', dropMode === 'insert')
      const validStyle = getSnappedItemStyle(
        candidateFrame.x,
        candidateFrame.y,
        candidateFrame.sizeX,
        candidateFrame.sizeY
      )
      infoBox.value.cloneItem.style.left = `${validStyle.left}px`
      infoBox.value.cloneItem.style.top = `${validStyle.top}px`
      tabMoveInCheckSQ()
      tabMoveOutCheckSQ()

      //If the current canvas is locked, no component movement will be performed
      if (canvasLocked.value) return
    }
  }

  window.addEventListener('mousemove', itemMouseMove)

  // Need to execute before mouseup
  const itemCanvasChange = () => {
    // The current canvas movement is in a locked state, indicating that there are components that require canvas switching
    if (canvasLocked.value) {
      const moveItem = infoBox.value.moveItem
      // Get the SQTab currently being moved in
      const curActiveMoveInSQTab = canvasComponentData?.value.find(
        (item) => item.component === 'SQTab' && item.collisionActive === true
      )
      if (curActiveMoveInSQTab) {
        if (curActiveMoveInSQTab.moveInActive) {
          const refTabInstance =
            currentInstance.refs['shape_component_' + curActiveMoveInSQTab.id][0]
          refTabInstance.addTabItem(moveItem)
          removeItemById(moveItem.id)
        }
        curActiveMoveInSQTab.collisionActive = false
        curActiveMoveInSQTab.moveInActive = false
      }

      // move out
      if (props.parentConfigItem && props.parentConfigItem.moveOutActive) {
        emits('parentAddItemBox', _.cloneDeep(moveItem))
        removeItemById(moveItem.id)
        // eslint-disable-next-line vue/no-mutating-props
        props.parentConfigItem.moveOutActive = false
      }
    }
    canvasLocked.value = false
  }

  const itemMouseUp = () => {
    if (_.isEmpty(infoBox.value)) return
    if (infoBox.value.cloneItem) {
      infoBox.value.cloneItem.remove()
    }
    if (infoBox.value.resizeItem) {
      if (infoBox.value.lastValidFrame) {
        setPlayerGridFrame(infoBox.value.resizeItem, infoBox.value.lastValidFrame)
      }
      delete infoBox.value.resizeItem.isPlayer
      props.resizeEnd(e, infoBox.value.resizeItem, infoBox.value.resizeItem._dragId)

      if (infoBox.value.resizeItem.component === 'SQTab') {
        const refTabInstance =
          currentInstance.refs['shape_component_' + infoBox.value.resizeItem.id][0]
        refTabInstance.outResizeEnd()
      }
    }
    if (infoBox.value.moveItem) {
      const dropFrame = infoBox.value.dropFrame
      const dropMode = infoBox.value.dropMode || 'invalid'
      const originalLayoutSnapshot = infoBox.value.originalLayoutSnapshot
      const appliedFrame =
        dropFrame && dropMode !== 'invalid'
          ? applyMoveGridFrame(infoBox.value.moveItem, dropFrame, dropMode)
          : null
      if (!appliedFrame && originalLayoutSnapshot) {
        restoreLayoutSnapshot(originalLayoutSnapshot)
      }
      props.dragEnd(e, infoBox.value.moveItem, infoBox.value.moveItem._dragId)
      infoBox.value.moveItem.show = true
      delete infoBox.value.moveItem.isPlayer
    }
    itemCanvasChange()
    infoBox.value = {}

    window.removeEventListener('mousemove', itemMouseMove)
    window.removeEventListener('mouseup', itemMouseUp)
  }

  // This will prevent click events from being passed to the parent level
  window.addEventListener('mouseup', itemMouseUp)
}

function nowItemStyle(item: CanvasItem) {
  return {
    width: cellWidth.value * item.sizeX - baseMarginLeft.value + 'px',
    height: cellHeight.value * item.sizeY - baseMarginTop.value + 'px',
    left: cellWidth.value * (item.x - 1) + baseMarginLeft.value + 'px',
    top: cellHeight.value * (item.y - 1) + baseMarginTop.value + 'px',
  }
}

function getList() {
  let returnList = _.sortBy(_.cloneDeep(canvasComponentData.value), 'y')
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  let finalList = []
  _.forEach(returnList, function (item) {
    if (_.isEmpty(item)) return
    // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
    delete item['_dragId']
    delete item['show']
    finalList.push(item)
  })
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  return finalList
}

function getMaxCell() {
  return maxCell.value
}

function getRenderState() {
  return moveAnimate.value
}

// @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
function afterInitOk(func) {
  let timeId = setInterval(() => {
    if (moveAnimate.value) {
      clearInterval(timeId)
      func()
    }
  }, 100)
}

const forceComputed = () => {
  // Force the trigger of copy-add calculation here, as the position calculation uses a method and there is no change in internal style attributes
  // In some cases, recalculation may not be triggered, resulting in a positional offset. The cellHeight property is being monitored, and forced recalculation is performed here
  cellHeight.value = cellHeight.value + 0.001
  nextTick(function () {
    cellHeight.value = cellHeight.value - 0.001
  })
}

function addItemBox(item: CanvasItem) {
  canvasComponentData.value.push(item)
  forceComputed()
  nextTick(() => {
    addItem(item, canvasComponentData.value.length - 1)
  })
}

function endMove() {
  // do endMove
}

function moving() {
  // do moving
}

// Obtain matrix position
function getItemMatrixPosition(item: CanvasItem) {
  return {
    tw: item.sizeX,
    th: item.sizeY,
    tl: item.x - 1,
    tr: item.sizeX + item.x - 1,
    tt: item.y - 1,
    tb: item.sizeY + item.y - 1,
  }
}

// Get style location
function getItemStylePosition(item: CanvasItem) {
  const { tw, th, tl, tr, tt, tb } = getItemMatrixPosition(item)
  return {
    tw: tw * cellWidth.value - baseMarginLeft.value,
    tl: cellWidth.value * tl + baseMarginLeft.value,
    tr: cellWidth.value * tr + baseMarginLeft.value,
    th: th * cellHeight.value - baseMarginTop.value,
    tt: cellHeight.value * tt + baseMarginTop.value,
    tb: cellHeight.value * tb + baseMarginTop.value,
  }
}

function tabMoveOutCheckSQ() {
  const { cloneItem, moveItem } = infoBox.value
  if (cloneItem && moveItem && props.canvasId.includes('tab') && props.parentConfigItem) {
    const left = cloneItem.offsetLeft
    const width = cloneItem.offsetWidth
    const top = cloneItem.offsetTop
    const { tw } = getItemStylePosition(props.parentConfigItem)
    // eslint-disable-next-line vue/no-mutating-props
    props.parentConfigItem.moveOutActive =
      left < -tabMoveOutXOffset || top < -tabMoveOutYOffset || left + width - tw > tabMoveOutXOffset
    canvasLocked.value = props.parentConfigItem.moveOutActive
  }
}

function tabMoveInCheckSQ() {
  const { cloneItem, moveItem } = infoBox.value
  if (cloneItem && moveItem && moveItem.component !== 'SQTab') {
    const width = cloneItem.offsetWidth
    const height = cloneItem.offsetHeight
    const left = cloneItem.offsetLeft
    const top = cloneItem.offsetTop
    canvasComponentData.value.forEach((item) => {
      if (item.id !== moveItem.id && item.component === 'SQTab') {
        const { tw, th, tl, tt } = getItemStylePosition(item)
        // Collision effective area inspection
        const collisionT = tt + tabMoveInYOffset
        const collisionL = tl + collisionGap - width
        const collisionW = tw + 2 * width - collisionGap
        const collisionH = th + height - tabMoveInYOffset
        // Near the upper left corner area
        const tfAndTf = collisionT <= top && collisionL <= left
        // Near the lower left corner area
        const bfAndBf = collisionT + collisionH >= top + height && collisionL <= left
        // Near the upper right corner area
        const trAndTr = collisionT <= top && collisionL + collisionW >= left + width
        // Near the lower right corner area
        const brAndBr =
          collisionT + collisionH >= top + height && collisionL + collisionW >= left + width
        item.collisionActive = tfAndTf && bfAndBf && trAndTr && brAndBr
        canvasLocked.value = item.collisionActive // Contains collision move in operation, locking canvas

        //Move into effective area for inspection
        //Collision effective area inspection
        const activeT = tt + tabMoveInYOffset
        const activeL = tl + collisionGap * 10 - width
        const activeW = tw + 2 * width - collisionGap * 20
        const activeH = th + height - 2 * tabMoveInYOffset

        // Near the upper left corner area
        const activeTfAndTf = activeT <= top && activeL <= left
        // Near the lower left corner area
        const activeBfAndBf = activeT + activeH >= top + height && activeL <= left
        // Near the upper right corner area
        const activeTrAndTr = activeT <= top && activeL + activeW >= left + width
        // Near the lower right corner area
        const activeBrAndBr = activeT + activeH >= top + height && activeL + activeW >= left + width

        item.moveInActive = activeTfAndTf && activeBfAndBf && activeTrAndTr && activeBrAndBr
      }
    })
  }
}

/**
 * Find position box
 */
function findPositionX(width: number) {
  let resultX = 1
  let checkPointYIndex = -1 // -1 means not occupying any Y-direction canvas
  // Component width
  let pb = positionBox.value
  if (width <= 0) return
  // Find the highest position index of the component. Component rule: the latest y is 1.
  canvasComponentData.value.forEach((component) => {
    const componentYIndex = component.y + component.sizeY - 2
    if (checkPointYIndex < componentYIndex) {
      checkPointYIndex = componentYIndex
    }
  })
  // Start checking from index i in the X direction;
  const pbX = pb[checkPointYIndex]
  // Get the last column array in the X direction
  if (checkPointYIndex < 0 || !pbX) {
    return 1
  } else {
    // The width to check is the component width. The end index of the check is checkEndIndex = i + width - 1;
    // The exit condition for the check is when the end index checkEndIndex is out of bounds (exceeds the end index of pbX).
    for (let i = 0, checkEndIndex = width - 1; checkEndIndex < pbX.length; i++, checkEndIndex++) {
      let adaptorCount = 0
      // Locate the occupied position in the last column
      for (let k = 0; k < width; k++) {
        // pbX[i + k].el === false indicates that the current matrix point is not occupied. When the width of consecutive unoccupied matrix points equals the component width, the starting point i is available.
        if (!pbX[i + k].el) {
          adaptorCount++
        }
      }
      if (adaptorCount === width) {
        resultX = i + 1
        break
      }
    }
    return resultX
  }
}

useEmitt({
  name: `editor-delete-${props.canvasId}`,
  callback: removeItemById,
})

onMounted(() => {
  currentInstance = getCurrentInstance()
})

const enlargeView = (itemId: string) => {
  const refTabInstance = currentInstance.refs['shape_component_' + itemId][0]
  refTabInstance.enlargeView()
}

defineExpose({
  getRenderState,
  init,
  sizeInit,
  afterInitOk,
  addItemBox,
  getMaxCell,
  getList,
  startMove,
  containerMouseDown,
  changeToCoord,
  removeItem,
  findClosetCoords,
  makeCoordinate,
  findPositionX,
})
</script>

<template>
  <div
    ref="containerRef"
    class="dragAndResize"
    @click="containerClick"
    @mousedown="containerMouseDown($event)"
    @mouseup="endMove()"
    @mousemove="moving()"
  >
    <EmptyBackground
      v-if="!canvasComponentData.length && isMainCanvas(canvasId)"
      :description="t('dashboard.add_component_tips')"
    />
    <template v-if="renderOk">
      <CanvasShape
        v-for="(item, index) in canvasComponentData"
        :key="'item' + index"
        :can-edit="!fullscreenFlag && dashboardCanEdit"
        :can-share="!fullscreenFlag && dashboardCanShare"
        :active="curComponentId === item.id"
        :config-item="item"
        :draggable="draggable"
        :item-index="index"
        :move-animate="moveAnimate"
        :start-move="startMove"
        :start-resize="startResize"
        :canvas-id="canvasId"
        :show-component-bar="showComponentBar"
        :can-edit-sql="canEditSql"
        :style="nowItemStyle(item)"
        @enlarge-view="() => enlargeView(item.id)"
        @edit-sql="() => editSql(item.id)"
      >
        <component
          :is="findComponent(item.component)"
          :ref="'shape_component_' + item.id"
          class="sq-component slot-component"
          :class="{ 'sq-component-hidden': item.component !== 'SQTab' }"
          :config-item="item"
          :view-info="canvasViewInfo[item.id]"
          :canvas-view-info="canvasViewInfo"
          :show-position="item.component === 'SQView' ? 'editor' : 'canvas'"
          :disabled="fullscreenFlag"
          :can-edit-sql="canEditSql"
          :show-component-bar="showComponentBar"
          :platform-template="platformTemplate"
          @parent-add-item-box="(subItem: any) => addItemBox(subItem)"
        >
        </component>
      </CanvasShape>
    </template>
    <DashboardSqlEditor
      v-model="sqlEditorVisible"
      :view-info="editingViewInfo"
      :allow-static-apply="platformTemplate"
      @applied="onSqlApplied"
    />
  </div>
</template>

<style scoped lang="less">
@import '../css/CanvasStyle.less';
</style>
