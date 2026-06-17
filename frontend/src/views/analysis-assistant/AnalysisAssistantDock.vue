<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import type { ChartAxis, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import {
  analysisAssistantApi,
  type AnalysisAssistantMessage,
  type AnalysisAssistantRole,
} from '@/api/analysisAssistant'
import icon_new_chat_outlined from '@/assets/svg/icon_new_chat_outlined.svg'
import icon_send_filled from '@/assets/svg/icon_send_filled.svg'
import icon_side_expand_outlined from '@/assets/svg/icon_side-expand_outlined.svg'
import icon_side_fold_outlined from '@/assets/svg/icon_side-fold_outlined.svg'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { promptApi } from '@/api/prompt'

interface DockMessage extends AnalysisAssistantMessage {
  id: number
  loading?: boolean
  error?: boolean
  plan?: AnalysisPlan
  planText?: string
  progress?: string
  traces?: string[]
  blocks?: AnalysisBlock[]
  final?: string
}

interface AnalysisPlan {
  intro: string
  steps: string[]
}

interface AnalysisChartConfig {
  type: ChartTypes
  title?: string
  columns?: ChartAxis[]
  axis?: {
    x?: ChartAxis
    y?: ChartAxis | ChartAxis[]
    series?: ChartAxis
    'multi-quota'?: {
      name?: string
      value?: string[]
    }
  }
}

interface AnalysisBlock {
  id: string
  title: string
  purpose?: string
  sql?: string
  fields?: string[]
  data?: Record<string, any>[]
  chart?: AnalysisChartConfig
  summary?: string
  error?: string
}

const props = defineProps<{
  expanded: boolean
}>()

const emits = defineEmits<{
  'update:expanded': [value: boolean]
}>()

const route = useRoute()
const analysisContext = useDatasourceContextStore()
const messages = ref<DockMessage[]>([])
const inputMessage = ref('')
const selectedCustomPromptId = ref<string | number | null>(null)
const customPromptOptions = ref<any[]>([])
const scrollRef = ref()
const inputRef = ref()
const isStreaming = ref(false)
const streamController = ref<AbortController>()
const dockWidth = ref(360)
let messageId = 0
let streamBuffer = ''
let streamFinished = false

const MIN_DOCK_WIDTH = 320
const MAX_DOCK_WIDTH = 680
const DOCK_TAB_HEIGHT = 112
const DOCK_TAB_VERTICAL_MARGIN = 16
const DOCK_TAB_DRAG_THRESHOLD = 4
const DOCK_TAB_SNAP_ANIMATION_MS = 420
const DOCK_TAB_INERTIA_FRICTION = 0.9
const DOCK_TAB_INERTIA_START_VELOCITY = 0.08
const DOCK_TAB_INERTIA_STOP_VELOCITY = 0.025
const DOCK_TAB_MAX_INERTIA_MS = 700
const DOCK_TAB_VELOCITY_SMOOTHING = 0.55
const DOCK_TAB_POSITION_KEY = 'analysis-assistant-dock-tab-top'

const getDefaultDockTabTop = () =>
  typeof window === 'undefined'
    ? DOCK_TAB_VERTICAL_MARGIN
    : Math.max(DOCK_TAB_VERTICAL_MARGIN, Math.round((window.innerHeight - DOCK_TAB_HEIGHT) / 2))

const getMaxDockTabTop = () =>
  Math.max(DOCK_TAB_VERTICAL_MARGIN, window.innerHeight - DOCK_TAB_HEIGHT - DOCK_TAB_VERTICAL_MARGIN)

const clampDockTabTop = (top: number) =>
  Math.min(getMaxDockTabTop(), Math.max(DOCK_TAB_VERTICAL_MARGIN, Math.round(top)))

const readDockTabTop = () => {
  if (typeof window === 'undefined') return getDefaultDockTabTop()

  const savedTopText = window.localStorage.getItem(DOCK_TAB_POSITION_KEY)
  if (savedTopText === null) return getDefaultDockTabTop()

  const savedTop = Number(savedTopText)
  return Number.isFinite(savedTop) ? clampDockTabTop(savedTop) : getDefaultDockTabTop()
}

const dockTabTop = ref(readDockTabTop())
const resizing = ref(false)
const draggingDockTab = ref(false)
const settlingDockTab = ref(false)
const inertialDockTab = ref(false)
let resizeStartX = 0
let resizeStartWidth = 0
let dockTabPointerActive = false
let dockTabStartY = 0
let dockTabStartTop = 0
let dockTabLastMoveY = 0
let dockTabLastMoveTime = 0
let dockTabVelocityY = 0
let suppressDockTabClick = false
let dockTabSettleTimer: number | undefined
let dockTabInertiaFrame: number | undefined

const hasMessages = computed(() => messages.value.length > 0)

const dockStyle = computed(() => (props.expanded ? { width: `${dockWidth.value}px` } : undefined))

const dockTabStyle = computed(() => ({ top: `${dockTabTop.value}px` }))

const loadCustomPromptOptions = () => {
  const datasourceId = analysisContext.datasourceId
  promptApi
    .options({
      target_scope: 'ANALYSIS_ASSISTANT',
      ...(datasourceId ? { datasource_id: datasourceId } : {}),
    })
    .then((res: any) => {
      customPromptOptions.value = res || []
      if (
        selectedCustomPromptId.value &&
        !customPromptOptions.value.some((item) => String(item.id) === String(selectedCustomPromptId.value))
      ) {
        selectedCustomPromptId.value = null
      }
    })
    .catch((e: any) => {
      console.error(e)
      customPromptOptions.value = []
    })
}

const getDockTabTime = () =>
  typeof performance !== 'undefined' ? performance.now() : Date.now()

const startDockTabSettle = (duration = DOCK_TAB_SNAP_ANIMATION_MS) => {
  if (dockTabSettleTimer !== undefined) {
    window.clearTimeout(dockTabSettleTimer)
  }

  settlingDockTab.value = true
  dockTabSettleTimer = window.setTimeout(() => {
    settlingDockTab.value = false
    dockTabSettleTimer = undefined
  }, duration)
}

const cancelDockTabInertia = () => {
  if (dockTabInertiaFrame !== undefined) {
    window.cancelAnimationFrame(dockTabInertiaFrame)
    dockTabInertiaFrame = undefined
  }
  inertialDockTab.value = false
}

const finishDockTabInertia = () => {
  cancelDockTabInertia()
  dockTabTop.value = clampDockTabTop(dockTabTop.value)
  startDockTabSettle()
  persistDockTabTop()
}

const startDockTabInertia = () => {
  const initialVelocity = dockTabVelocityY
  if (Math.abs(initialVelocity) < DOCK_TAB_INERTIA_START_VELOCITY) {
    dockTabTop.value = clampDockTabTop(dockTabTop.value)
    startDockTabSettle()
    persistDockTabTop()
    return
  }

  cancelDockTabInertia()
  settlingDockTab.value = false
  inertialDockTab.value = true

  let velocity = initialVelocity
  let lastTime = getDockTabTime()
  const startTime = lastTime

  const step = (time: number) => {
    const deltaTime = Math.min(Math.max(time - lastTime, 8), 32)
    lastTime = time

    const minTop = DOCK_TAB_VERTICAL_MARGIN
    const maxTop = getMaxDockTabTop()
    const nextTop = dockTabTop.value + velocity * deltaTime

    if (nextTop <= minTop || nextTop >= maxTop) {
      dockTabTop.value = Math.min(maxTop, Math.max(minTop, nextTop))
      finishDockTabInertia()
      return
    }

    dockTabTop.value = nextTop
    velocity *= Math.pow(DOCK_TAB_INERTIA_FRICTION, deltaTime / 16.67)

    if (
      Math.abs(velocity) <= DOCK_TAB_INERTIA_STOP_VELOCITY ||
      time - startTime >= DOCK_TAB_MAX_INERTIA_MS
    ) {
      finishDockTabInertia()
      return
    }

    dockTabInertiaFrame = window.requestAnimationFrame(step)
  }

  dockTabInertiaFrame = window.requestAnimationFrame(step)
}

const pageContext = computed(() => {
  const title = route.meta?.title
  const page = title ? `当前页面：${title}` : `当前路径：${route.path}`
  const datasource = analysisContext.datasourceName
    ? `当前项目：${analysisContext.datasourceName}`
    : ''
  return [page, datasource].filter(Boolean).join('\n')
})

const setExpanded = (value: boolean) => {
  emits('update:expanded', value)
}

const getMaxDockWidth = () => Math.max(MIN_DOCK_WIDTH, Math.min(MAX_DOCK_WIDTH, window.innerWidth - 48))

const clampDockWidth = (width: number) =>
  Math.min(getMaxDockWidth(), Math.max(MIN_DOCK_WIDTH, Math.round(width)))

const persistDockTabTop = () => {
  window.localStorage.setItem(DOCK_TAB_POSITION_KEY, String(dockTabTop.value))
}

const stopResize = () => {
  if (!resizing.value) return
  resizing.value = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleResize)
  window.removeEventListener('pointerup', stopResize)
}

const handleResize = (event: PointerEvent) => {
  if (!resizing.value) return
  dockWidth.value = clampDockWidth(resizeStartWidth + resizeStartX - event.clientX)
}

const startResize = (event: PointerEvent) => {
  event.preventDefault()
  resizing.value = true
  resizeStartX = event.clientX
  resizeStartWidth = dockWidth.value
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleResize)
  window.addEventListener('pointerup', stopResize)
}

const stopDockTabDrag = () => {
  if (!dockTabPointerActive) return
  dockTabPointerActive = false
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleDockTabDrag)
  window.removeEventListener('pointerup', stopDockTabDrag)
  window.removeEventListener('pointercancel', stopDockTabDrag)

  if (draggingDockTab.value) {
    draggingDockTab.value = false
    startDockTabInertia()
    suppressDockTabClick = true
    window.setTimeout(() => {
      suppressDockTabClick = false
    }, 0)
  } else {
    draggingDockTab.value = false
  }
}

const handleDockTabDrag = (event: PointerEvent) => {
  if (!dockTabPointerActive) return

  const now = getDockTabTime()
  const moveDistance = event.clientY - dockTabLastMoveY
  const moveTime = Math.max(now - dockTabLastMoveTime, 16)
  const instantVelocity = moveDistance / moveTime
  dockTabVelocityY =
    dockTabVelocityY * (1 - DOCK_TAB_VELOCITY_SMOOTHING) +
    instantVelocity * DOCK_TAB_VELOCITY_SMOOTHING
  dockTabLastMoveY = event.clientY
  dockTabLastMoveTime = now

  const deltaY = event.clientY - dockTabStartY
  if (!draggingDockTab.value && Math.abs(deltaY) < DOCK_TAB_DRAG_THRESHOLD) {
    return
  }

  draggingDockTab.value = true
  dockTabTop.value = clampDockTabTop(dockTabStartTop + deltaY)
}

const startDockTabDrag = (event: PointerEvent) => {
  if (props.expanded || event.button !== 0) return

  event.preventDefault()
  dockTabPointerActive = true
  draggingDockTab.value = false
  dockTabStartY = event.clientY
  dockTabStartTop = dockTabTop.value
  dockTabLastMoveY = event.clientY
  dockTabLastMoveTime = getDockTabTime()
  dockTabVelocityY = 0
  settlingDockTab.value = false
  cancelDockTabInertia()
  if (dockTabSettleTimer !== undefined) {
    window.clearTimeout(dockTabSettleTimer)
    dockTabSettleTimer = undefined
  }
  document.body.style.cursor = 'ns-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleDockTabDrag)
  window.addEventListener('pointerup', stopDockTabDrag)
  window.addEventListener('pointercancel', stopDockTabDrag)
}

const handleDockTabClick = (event: MouseEvent) => {
  if (suppressDockTabClick) {
    event.preventDefault()
    event.stopPropagation()
    return
  }

  setExpanded(true)
}

const handleWindowResize = () => {
  dockWidth.value = clampDockWidth(dockWidth.value)
  dockTabTop.value = clampDockTabTop(dockTabTop.value)
}

onBeforeUnmount(() => {
  stopResize()
  stopDockTabDrag()
  cancelDockTabInertia()
  if (dockTabSettleTimer !== undefined) {
    window.clearTimeout(dockTabSettleTimer)
  }
  window.removeEventListener('resize', handleWindowResize)
})

onMounted(() => {
  dockTabTop.value = readDockTabTop()
  window.addEventListener('resize', handleWindowResize)
  analysisContext
    .loadDatasources()
    .catch((e) => console.error(e))
    .finally(() => loadCustomPromptOptions())
})

const scrollToBottom = () => {
  nextTick(() => {
    const wrapRef = scrollRef.value?.wrapRef
    if (wrapRef) {
      scrollRef.value.setScrollTop(wrapRef.scrollHeight)
    }
  })
}

watch(
  () => props.expanded,
  (value) => {
    if (value) {
      nextTick(() => {
        inputRef.value?.focus()
        scrollToBottom()
      })
    }
  }
)

const pushMessage = (role: AnalysisAssistantRole, content: string, loading = false) => {
  const message: DockMessage = {
    id: ++messageId,
    role,
    content,
    loading,
    traces: role === 'assistant' ? [] : undefined,
    blocks: role === 'assistant' ? [] : undefined,
  }
  messages.value.push(message)
  scrollToBottom()
  return messages.value[messages.value.length - 1]
}

const hasStructuredContent = (message: DockMessage) =>
  Boolean(
    message.plan ||
      message.planText ||
      message.final ||
      message.progress ||
      message.blocks?.length
  )

const getMessageHistoryContent = (message: DockMessage) => {
  if (message.role === 'user') {
    return message.content
  }
  const parts = [
    message.content,
    message.planText,
    ...(message.traces || []),
    message.plan?.intro,
    ...(message.plan?.steps || []),
    ...(message.blocks || []).map((block) =>
      [block.title, block.purpose, block.summary].filter(Boolean).join('\n')
    ),
    message.final,
  ]
  return parts.filter(Boolean).join('\n')
}

const requestMessages = () =>
  messages.value
    .filter((message) => getMessageHistoryContent(message).trim() && !message.loading)
    .map((message) => ({
      role: message.role,
      content: getMessageHistoryContent(message),
    }))

const finishAssistantMessage = (assistantMessage: DockMessage) => {
  assistantMessage.loading = false
  assistantMessage.progress = ''
  isStreaming.value = false
}

const getChartXAxis = (chart?: AnalysisChartConfig) => (chart?.axis?.x ? [chart.axis.x] : [])

const getChartYAxis = (chart?: AnalysisChartConfig) => {
  const y = chart?.axis?.y
  if (!y) return []
  return Array.isArray(y) ? y : [y]
}

const getChartSeries = (chart?: AnalysisChartConfig) => {
  if (chart?.axis?.series) return [chart.axis.series]
  if (chart?.type === 'pie' && chart.axis?.x) return [chart.axis.x]
  return []
}

const getMultiQuotaName = (chart?: AnalysisChartConfig) => chart?.axis?.['multi-quota']?.name

const getPreviewRows = (block: AnalysisBlock) => (block.data || []).slice(0, 6)

const isTableChart = (block: AnalysisBlock) => block.chart?.type === 'table'

const getTableRows = (block: AnalysisBlock) => block.data || []

const getChartTypeLabel = (type?: ChartTypes) => {
  const labels: Record<ChartTypes, string> = {
    table: '数据表',
    bar: '条形图',
    column: '柱图',
    line: '折线图',
    pie: '饼图',
    metric: '指标卡',
    funnel: '漏斗图',
    heatmap: '热力图',
    scatter: '散点图',
    sankey: '桑基图',
    treemap: '矩形树图',
  }
  return type ? labels[type] || type : ''
}

const getDisplayFields = (block: AnalysisBlock) => {
  if (block.fields?.length) return block.fields
  const firstRow = block.data?.[0]
  return firstRow ? Object.keys(firstRow) : []
}

const formatCell = (value: any) => {
  if (value === null || value === undefined || value === '') return '-'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const processStreamEvent = (chunk: string, assistantMessage: DockMessage) => {
  const payload = chunk
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.replace(/^data:\s?/, ''))
    .join('')

  if (!payload) return

  try {
    const data = JSON.parse(payload)
    if (data.type === 'answer') {
      assistantMessage.content += data.content || ''
    }
    if (data.type === 'plan_delta') {
      assistantMessage.planText = (assistantMessage.planText || '') + (data.content || '')
    }
    if (data.type === 'trace') {
      if (!assistantMessage.traces) assistantMessage.traces = []
      const trace = data.content || ''
      if (trace && assistantMessage.traces[assistantMessage.traces.length - 1] !== trace) {
        assistantMessage.traces.push(trace)
      }
    }
    if (data.type === 'plan') {
      assistantMessage.plan = {
        intro: data.intro || '',
        steps: Array.isArray(data.steps) ? data.steps : [],
      }
    }
    if (data.type === 'progress') {
      assistantMessage.progress = data.content || ''
    }
    if (data.type === 'block' && data.block) {
      if (!assistantMessage.blocks) assistantMessage.blocks = []
      assistantMessage.blocks.push(data.block)
      assistantMessage.progress = ''
    }
    if (data.type === 'final') {
      assistantMessage.final = data.content || ''
    }
    if (data.type === 'error') {
      assistantMessage.error = true
      assistantMessage.content = data.content || '综合分析助手暂时不可用'
    }
    if (data.type === 'finish' || data.type === 'error') {
      streamFinished = true
      finishAssistantMessage(assistantMessage)
    }
  } catch (e) {
    console.error(e)
  }
}

const appendStreamChunk = (text: string, assistantMessage: DockMessage) => {
  streamBuffer = (streamBuffer + text).replace(/\r\n/g, '\n')

  let boundary = streamBuffer.indexOf('\n\n')
  while (boundary >= 0) {
    const chunk = streamBuffer.slice(0, boundary)
    streamBuffer = streamBuffer.slice(boundary + 2)
    processStreamEvent(chunk, assistantMessage)
    boundary = streamBuffer.indexOf('\n\n')
  }

  scrollToBottom()
}

const sendMessage = async ($event: any = {}) => {
  if ($event?.isComposing || isStreaming.value) {
    return
  }
  const question = inputMessage.value.trim()
  if (!question) {
    return
  }

  try {
    await analysisContext.loadDatasources()
  } catch (e) {
    console.error(e)
  }

  inputMessage.value = ''
  pushMessage('user', question)
  const assistantMessage = pushMessage('assistant', '', true)

  isStreaming.value = true
  streamBuffer = ''
  streamFinished = false
  streamController.value = new AbortController()

  try {
    const response = await analysisAssistantApi.chat(
      requestMessages(),
      pageContext.value,
      analysisContext.datasourceId,
      selectedCustomPromptId.value,
      streamController.value
    )
    if (!response.ok) {
      throw new Error(await response.text())
    }
    const reader = response.body?.getReader()
    if (!reader) {
      throw new Error('Stream response is empty')
    }

    const decoder = new TextDecoder('utf-8')
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      appendStreamChunk(decoder.decode(value, { stream: true }), assistantMessage)
    }
    appendStreamChunk(decoder.decode(), assistantMessage)
    if (streamBuffer.trim()) {
      processStreamEvent(streamBuffer, assistantMessage)
      streamBuffer = ''
    }
  } catch (e: any) {
    if (e?.name !== 'AbortError') {
      assistantMessage.error = true
      assistantMessage.content = e?.message || '综合分析助手暂时不可用'
    }
  } finally {
    if (
      !streamFinished &&
      !assistantMessage.content.trim() &&
      !hasStructuredContent(assistantMessage) &&
      !assistantMessage.error
    ) {
      assistantMessage.content = '综合分析助手没有返回可展示内容，请换个问法再试。'
    }
    finishAssistantMessage(assistantMessage)
    isStreaming.value = false
    streamController.value = undefined
    scrollToBottom()
  }
}

const stopStreaming = () => {
  streamController.value?.abort()
  isStreaming.value = false
  const lastMessage = messages.value[messages.value.length - 1]
  if (lastMessage?.role === 'assistant' && lastMessage.loading) {
    lastMessage.loading = false
    lastMessage.progress = ''
    if (!lastMessage.content.trim()) {
      lastMessage.content = '已停止生成。'
    }
  }
}

const clearMessages = () => {
  stopStreaming()
  messages.value = []
  inputMessage.value = ''
}

watch(
  () => analysisContext.datasourceId,
  (value, oldValue) => {
    if (oldValue && value !== oldValue) {
      clearMessages()
    }
    loadCustomPromptOptions()
  }
)

const handleCtrlEnter = (e: KeyboardEvent) => {
  const textarea = e.target as HTMLTextAreaElement
  const start = textarea.selectionStart
  const end = textarea.selectionEnd
  const value = textarea.value
  inputMessage.value = value.substring(0, start) + '\n' + value.substring(end)
  nextTick(() => {
    textarea.selectionStart = textarea.selectionEnd = start + 1
  })
}
</script>

<template>
  <aside class="analysis-assistant-dock" :class="{ expanded, resizing }" :style="dockStyle">
    <button
      v-if="!expanded"
      class="dock-tab"
      :class="{ dragging: draggingDockTab, inertial: inertialDockTab, settling: settlingDockTab }"
      :style="dockTabStyle"
      type="button"
      @pointerdown="startDockTabDrag"
      @click="handleDockTabClick"
    >
      <el-icon size="18">
        <icon_side_expand_outlined />
      </el-icon>
      <span class="dock-tab-text">
        <span>助</span>
        <span>手</span>
      </span>
    </button>

    <template v-else>
      <div
        class="dock-resize-handle"
        role="separator"
        aria-orientation="vertical"
        aria-label="调整助手宽度"
        @pointerdown="startResize"
      />
      <header class="dock-header">
        <div class="dock-heading">
          <div class="dock-title">综合分析助手</div>
          <div v-if="analysisContext.datasourceName" class="datasource-pill">
            {{ analysisContext.datasourceName }}
          </div>
        </div>
        <div class="dock-actions">
          <el-tooltip effect="dark" content="新对话" placement="bottom">
            <el-button link class="icon-btn" :disabled="isStreaming" @click="clearMessages">
              <el-icon size="18">
                <icon_new_chat_outlined />
              </el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip effect="dark" content="收起" placement="bottom">
            <el-button link class="icon-btn" @click="setExpanded(false)">
              <el-icon size="18">
                <icon_side_fold_outlined />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </header>

      <el-scrollbar ref="scrollRef" class="dock-body">
        <div v-if="!hasMessages" class="empty-state">
          <div class="empty-title">今天想分析什么？</div>
        </div>

        <div v-for="message in messages" :key="message.id" class="message-row" :class="message.role">
          <div
            class="message-bubble"
            :class="{
              error: message.error,
              structured: message.role === 'assistant' && hasStructuredContent(message),
            }"
          >
            <template v-if="message.role === 'assistant'">
              <template v-if="hasStructuredContent(message)">
                <MdComponent v-if="message.content.trim()" :message="message.content" />

                <section v-if="message.planText" class="analysis-plan">
                  <MdComponent :message="message.planText" />
                </section>

                <section v-else-if="message.plan" class="analysis-plan">
                  <div class="plan-intro">{{ message.plan.intro }}</div>
                  <ol v-if="message.plan.steps.length" class="plan-steps">
                    <li v-for="step in message.plan.steps" :key="step">{{ step }}</li>
                  </ol>
                </section>

                <section v-if="(message.planText || message.plan) && message.traces?.length" class="analysis-trace">
                  <div class="trace-title">具体执行步骤</div>
                  <ul class="trace-list">
                    <li
                      v-for="(trace, traceIndex) in message.traces"
                      :key="`${traceIndex}-${trace}`"
                      :class="{ active: message.loading && traceIndex === message.traces.length - 1 }"
                    >
                      <span class="trace-dot"></span>
                      <span>{{ trace }}</span>
                    </li>
                  </ul>
                </section>

                <div v-if="message.progress" class="analysis-progress">
                  {{ message.progress }}
                </div>

                <section
                  v-for="block in message.blocks"
                  :key="block.id"
                  class="analysis-block"
                  :class="{ failed: block.error }"
                >
                  <header class="block-header">
                    <div>
                      <div class="block-title">{{ block.title }}</div>
                      <div v-if="block.purpose" class="block-purpose">{{ block.purpose }}</div>
                    </div>
                    <span v-if="block.chart" class="chart-type">{{ getChartTypeLabel(block.chart.type) }}</span>
                  </header>

                  <div
                    v-if="block.chart && block.data?.length"
                    class="chart-frame"
                    :class="{ table: isTableChart(block) }"
                  >
                    <div v-if="isTableChart(block)" class="chart-table-wrap">
                      <table class="preview-table">
                        <thead>
                          <tr>
                            <th v-for="field in getDisplayFields(block)" :key="field">{{ field }}</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="(row, rowIndex) in getTableRows(block)" :key="rowIndex">
                            <td v-for="field in getDisplayFields(block)" :key="field">
                              {{ formatCell(row[field]) }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                    <ChartComponent
                      v-else
                      :id="`analysis-${message.id}-${block.id}-${block.chart.type}`"
                      :type="block.chart.type"
                      :columns="block.chart.columns || []"
                      :x="getChartXAxis(block.chart)"
                      :y="getChartYAxis(block.chart)"
                      :series="getChartSeries(block.chart)"
                      :data="block.data"
                      :multi-quota-name="getMultiQuotaName(block.chart)"
                    />
                  </div>
                  <div v-else-if="!block.error" class="empty-data">暂无可展示数据</div>

                  <MdComponent v-if="block.summary" class="block-summary" :message="block.summary" />

                  <details v-if="block.sql" class="block-details">
                    <summary>SQL</summary>
                    <pre>{{ block.sql }}</pre>
                  </details>

                  <details v-if="block.data?.length && !isTableChart(block)" class="block-details">
                    <summary>数据预览</summary>
                    <div class="preview-table-wrap">
                      <table class="preview-table">
                        <thead>
                          <tr>
                            <th v-for="field in getDisplayFields(block)" :key="field">{{ field }}</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="(row, rowIndex) in getPreviewRows(block)" :key="rowIndex">
                            <td v-for="field in getDisplayFields(block)" :key="field">
                              {{ formatCell(row[field]) }}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </details>
                </section>

                <section v-if="message.final" class="final-answer">
                  <MdComponent :message="message.final" />
                </section>
              </template>
              <MdComponent v-else :message="message.content || (message.loading ? '正在思考...' : '')" />
            </template>
            <template v-else>
              {{ message.content }}
            </template>
          </div>
        </div>
      </el-scrollbar>

      <footer class="dock-footer">
        <div class="input-shell">
          <el-input
            ref="inputRef"
            v-model="inputMessage"
            :disabled="isStreaming"
            type="textarea"
            :rows="3"
            placeholder="输入问题"
            resize="none"
            @keydown.enter.exact.prevent="($event: any) => sendMessage($event)"
            @keydown.ctrl.enter.exact.prevent="handleCtrlEnter"
          />
          <el-select
            v-model="selectedCustomPromptId"
            class="agent-select"
            clearable
            filterable
            :disabled="isStreaming"
            placeholder="默认 Agent"
            @click.stop
          >
            <el-option label="默认 Agent" :value="null" />
            <el-option
              v-for="agent in customPromptOptions"
              :key="agent.id"
              :label="agent.name"
              :value="agent.id"
            />
          </el-select>
          <el-button
            v-if="!isStreaming"
            circle
            type="primary"
            class="send-btn"
            :disabled="!inputMessage.trim()"
            @click.stop="($event: any) => sendMessage($event)"
          >
            <el-icon size="16">
              <icon_send_filled />
            </el-icon>
          </el-button>
          <el-button v-else class="stop-btn" @click="stopStreaming">停止</el-button>
        </div>
      </footer>
    </template>
  </aside>
</template>

<style scoped lang="less">
.analysis-assistant-dock {
  --assistant-dock-bg: #ffffff;
  --assistant-dock-body-bg: #f6f8fc;
  --assistant-dock-control-bg: #f1f5fb;
  --assistant-dock-control-hover-bg: #e8f0ff;
  --assistant-dock-pill-bg: #edf3ff;
  --assistant-dock-border: #d7e1ef;
  --assistant-dock-border-soft: #e6edf6;
  --assistant-dock-text-primary: #15233b;
  --assistant-dock-text-secondary: #6b7a90;
  --assistant-dock-text-tertiary: #8a97aa;
  --assistant-dock-input-bg: #ffffff;
  --assistant-dock-primary-soft-bg: rgba(47, 107, 255, 0.1);
  --assistant-dock-danger-soft-bg: #fff5f5;
  --assistant-tab-bg: #ffffff;
  --assistant-tab-hover-bg: #edf3ff;
  --assistant-tab-border: #d7e1ef;
  --assistant-tab-text: #15233b;
  --assistant-tab-shadow: 0 8px 20px rgba(24, 46, 86, 0.12);
  --assistant-tab-hover-shadow: 0 10px 24px rgba(24, 46, 86, 0.16);

  position: fixed;
  top: 0;
  right: 0;
  z-index: 1200;
  width: 44px;
  height: 0;
  transition:
    width 0.18s ease,
    transform 0.18s ease;

  &.expanded {
    top: 0;
    right: 0;
    bottom: 0;
    width: 360px;
    height: auto;
    max-width: calc(100vw - 32px);
    background: var(--assistant-dock-bg);
    border: 1px solid var(--assistant-dock-border);
    border-right: 0;
    border-radius: 12px 0 0 12px;
    box-shadow: 0 18px 44px rgba(17, 37, 73, 0.16);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  &.resizing {
    transition: none;
  }
}

.dock-resize-handle {
  position: absolute;
  top: 0;
  left: -4px;
  bottom: 0;
  z-index: 2;
  width: 8px;
  cursor: ew-resize;
  touch-action: none;

  &::after {
    content: '';
    position: absolute;
    top: 12px;
    bottom: 12px;
    left: 3px;
    width: 2px;
    border-radius: 2px;
    background: transparent;
    transition: background 0.16s ease;
  }

  &:hover::after,
  .resizing &::after {
    background: var(--ed-color-primary, #1cba90);
  }
}

.dock-tab {
  position: absolute;
  right: 0;
  width: 40px;
  height: 112px;
  padding: 10px 0;
  border: 1px solid var(--assistant-tab-border);
  border-right: 0;
  border-radius: 6px 0 0 6px;
  background: var(--assistant-tab-bg);
  box-shadow: var(--assistant-tab-shadow);
  color: var(--assistant-tab-text);
  cursor: pointer;
  touch-action: none;
  user-select: none;
  transition:
    top 0.16s ease,
    background 0.16s ease,
    box-shadow 0.16s ease,
    transform 0.16s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;

  .ed-icon {
    width: 20px;
    height: 20px;
    color: currentColor;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  :deep(svg),
  :deep(svg path) {
    color: currentColor;
    fill: currentColor !important;
  }

  span {
    line-height: 16px;
  }

  .dock-tab-text {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    font-size: 13px;
    font-weight: 500;
    letter-spacing: 0;
  }

  &:hover {
    background: var(--assistant-tab-hover-bg);
    border-color: var(--assistant-tab-border);
    box-shadow: var(--assistant-tab-hover-shadow);
  }

  &.dragging,
  &.inertial {
    cursor: ns-resize;
    transition: none;
  }

  &.settling {
    transition:
      top 0.36s cubic-bezier(0.2, 0.8, 0.2, 1),
      background 0.16s ease,
      box-shadow 0.16s ease;
  }
}

.dock-header {
  min-height: 58px;
  padding: 8px 12px 8px 16px;
  border-bottom: 1px solid var(--assistant-dock-border-soft);
  background: var(--assistant-dock-bg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;

  .dock-heading {
    min-width: 0;
    flex: 1;
  }

  .dock-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--assistant-dock-text-primary);
    line-height: 22px;
  }

  .datasource-pill {
    display: inline-flex;
    align-items: center;
    max-width: 220px;
    height: 22px;
    margin-top: 4px;
    padding: 0 8px;
    border-radius: 6px;
    background: var(--assistant-dock-pill-bg);
    color: var(--assistant-dock-text-secondary);
    font-size: 12px;
    line-height: 22px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .dock-actions {
    display: flex;
    align-items: center;
    gap: 4px;
  }

  .icon-btn {
    width: 28px;
    height: 28px;
    min-width: 28px;
    color: var(--assistant-dock-text-secondary);

    &:hover {
      background: var(--assistant-dock-control-hover-bg);
      color: var(--assistant-dock-text-primary);
    }
  }
}

.dock-body {
  flex: 1;
  min-height: 0;
  background: var(--assistant-dock-body-bg);

  :deep(.ed-scrollbar__view) {
    min-height: 100%;
    padding: 16px 14px;
  }
}

.empty-state {
  height: calc(100vh - 190px);
  min-height: 240px;
  display: flex;
  align-items: center;
  justify-content: center;

  .empty-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--assistant-dock-text-primary);
  }
}

.message-row {
  display: flex;
  margin-bottom: 14px;

  &.user {
    justify-content: flex-end;

    .message-bubble {
      background: var(--assistant-dock-primary-soft-bg);
      border-color: rgba(47, 107, 255, 0.22);
      color: var(--assistant-dock-text-primary);
      white-space: pre-wrap;
    }
  }

  &.assistant {
    justify-content: flex-start;
  }
}

.message-bubble {
  max-width: 92%;
  padding: 10px 12px;
  border: 1px solid var(--assistant-dock-border-soft);
  border-radius: 8px;
  background: var(--assistant-dock-bg);
  color: var(--assistant-dock-text-primary);
  font-size: 14px;
  line-height: 22px;
  word-break: break-word;

  &.error {
    border-color: #f5c2c7;
    background: var(--assistant-dock-danger-soft-bg);
    color: #a61b29;
  }

  &.structured {
    width: 100%;
    max-width: 100%;
    padding: 12px;
  }

  :deep(.markdown-body) {
    font-size: 14px;
    line-height: 22px;
    background: transparent;

    p {
      margin: 0 0 8px;

      &:last-child {
        margin-bottom: 0;
      }
    }

    ul,
    ol {
      padding-left: 18px;
      margin-top: 4px;
      margin-bottom: 8px;
    }

    pre {
      margin: 8px 0;
      border-radius: 6px;
    }
  }
}

.analysis-trace,
.analysis-plan,
.analysis-block,
.final-answer {
  border: 1px solid #e6e8eb;
  border-radius: 8px;
  background: var(--assistant-dock-bg);
}

.analysis-trace {
  padding: 12px;
  margin-bottom: 10px;

  .trace-title {
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--assistant-dock-text-primary);
  }

  .trace-list {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    min-height: 22px;
    margin: 6px 0;
    color: var(--assistant-dock-text-secondary);
    font-size: 13px;
    line-height: 20px;

    &.active {
      color: #168f70;

      .trace-dot {
        background: var(--ed-color-primary, #1cba90);
        box-shadow: 0 0 0 4px #1cba901a;
      }
    }
  }

  .trace-dot {
    flex-shrink: 0;
    width: 7px;
    height: 7px;
    margin-top: 7px;
    border-radius: 50%;
    background: #c9cdd4;
  }
}

.analysis-plan {
  padding: 12px;
  margin-bottom: 10px;

  .plan-intro {
    font-size: 14px;
    line-height: 22px;
    color: var(--assistant-dock-text-primary);
  }

  .plan-steps {
    margin: 8px 0 0;
    padding-left: 20px;
    color: var(--assistant-dock-text-secondary);

    li {
      margin: 4px 0;
    }
  }
}

.analysis-progress {
  margin: 10px 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #f1f8f6;
  color: #168f70;
  font-size: 13px;
}

.analysis-block {
  margin-top: 10px;
  padding: 12px;

  &.failed {
    border-color: #f5c2c7;
    background: #fffafa;
  }

  .block-header {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 10px;
  }

  .block-title {
    font-size: 14px;
    font-weight: 600;
    line-height: 20px;
    color: var(--assistant-dock-text-primary);
  }

  .block-purpose {
    margin-top: 3px;
    font-size: 12px;
    line-height: 18px;
    color: var(--assistant-dock-text-secondary);
  }

  .chart-type {
    flex-shrink: 0;
    height: 20px;
    padding: 0 6px;
    border-radius: 4px;
    background: var(--assistant-dock-control-bg);
    color: var(--assistant-dock-text-secondary);
    font-size: 12px;
    line-height: 20px;
  }
}

.chart-frame {
  height: 240px;
  min-height: 240px;
  margin-bottom: 10px;
  border: 1px solid var(--assistant-dock-border-soft);
  border-radius: 6px;
  background: var(--assistant-dock-bg);
  overflow: hidden;

  &.table {
    height: 280px;
    min-height: 280px;
  }
}

.chart-table-wrap {
  height: 100%;
  overflow: auto;
}

.empty-data {
  margin-bottom: 10px;
  padding: 24px 0;
  border: 1px dashed #d8dbe0;
  border-radius: 6px;
  color: var(--assistant-dock-text-tertiary);
  text-align: center;
}

.block-summary {
  display: block;
  margin-top: 4px;
}

.block-details {
  margin-top: 8px;
  border-top: 1px solid var(--assistant-dock-border-soft);
  padding-top: 8px;

  summary {
    width: fit-content;
    cursor: pointer;
    color: var(--assistant-dock-text-secondary);
    font-size: 13px;
    line-height: 20px;
  }

  pre {
    max-height: 180px;
    margin: 8px 0 0;
    padding: 10px;
    border-radius: 6px;
    background: var(--assistant-dock-control-bg);
    color: var(--assistant-dock-text-primary);
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

.preview-table-wrap {
  max-height: 220px;
  margin-top: 8px;
  overflow: auto;
  border: 1px solid var(--assistant-dock-border-soft);
  border-radius: 6px;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;

  th,
  td {
    max-width: 160px;
    padding: 7px 8px;
    border-bottom: 1px solid var(--assistant-dock-border-soft);
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--assistant-dock-control-bg);
    color: var(--assistant-dock-text-secondary);
    font-weight: 600;
  }

  td {
    color: var(--assistant-dock-text-primary);
  }
}

.final-answer {
  margin-top: 10px;
  padding: 12px;
  border-color: #c8eee4;
  background: #f8fffc;
}

.dock-footer {
  flex-shrink: 0;
  padding: 10px 14px 14px;
  border-top: 1px solid var(--assistant-dock-border-soft);
  background: var(--assistant-dock-body-bg);

  .input-shell {
    position: relative;
  }

  :deep(.ed-textarea__inner) {
    height: 96px;
    min-height: 96px !important;
    max-height: 96px;
    padding: 10px 48px 38px 12px;
    border-radius: 8px;
    line-height: 22px;
    background: var(--assistant-dock-input-bg);
    overflow-y: auto;
  }

  .agent-select {
    position: absolute;
    left: 10px;
    bottom: 8px;
    z-index: 2;
    width: 116px;

    :deep(.ed-select__wrapper) {
      min-height: 28px;
      height: 28px;
      border-radius: 6px;
      background: var(--assistant-dock-control-bg);
      box-shadow: 0 0 0 1px var(--assistant-dock-border) inset;
    }

    :deep(.ed-select__selected-item),
    :deep(.ed-select__placeholder) {
      font-size: 12px;
    }
  }

  .send-btn {
    position: absolute;
    right: 10px;
    bottom: 8px;
    min-width: 0;
  }

  .stop-btn {
    position: absolute;
    right: 10px;
    bottom: 8px;
    height: 28px;
    padding: 0 10px;
  }
}
</style>
