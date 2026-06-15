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
const scrollRef = ref()
const inputRef = ref()
const isStreaming = ref(false)
const streamController = ref<AbortController>()
const dockWidth = ref(400)
const resizing = ref(false)
let messageId = 0
let streamBuffer = ''
let streamFinished = false
let resizeStartX = 0
let resizeStartWidth = 0

const MIN_DOCK_WIDTH = 360
const MAX_DOCK_WIDTH = 760

const hasMessages = computed(() => messages.value.length > 0)

const dockStyle = computed(() => (props.expanded ? { width: `${dockWidth.value}px` } : undefined))

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

onBeforeUnmount(() => {
  stopResize()
})

onMounted(() => {
  analysisContext.loadDatasources().catch((e) => console.error(e))
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
    <button v-if="!expanded" class="dock-tab" type="button" @click="setExpanded(true)">
      <el-icon size="18">
        <icon_side_expand_outlined />
      </el-icon>
      <span>助手</span>
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
  position: fixed;
  top: 8px;
  right: 8px;
  bottom: 8px;
  z-index: 1200;
  width: 44px;
  height: auto;
  transition:
    width 0.18s ease,
    transform 0.18s ease;

  &.expanded {
    width: 400px;
    max-width: calc(100vw - 32px);
    background: #fff;
    border: 1px solid #dee0e3;
    border-radius: 8px;
    box-shadow: 0 8px 24px 0 #1f232926;
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
  top: 50%;
  right: 0;
  transform: translateY(-50%);
  width: 36px;
  height: 104px;
  padding: 10px 0;
  border: 1px solid #dee0e3;
  border-radius: 8px 0 0 8px;
  background: #fff;
  box-shadow: 0 2px 4px 0 #1f23291f;
  color: #1f2329;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 8px;

  span {
    writing-mode: vertical-rl;
    font-size: 13px;
    line-height: 16px;
  }

  &:hover {
    background: #f5f6f7;
  }
}

.dock-header {
  min-height: 58px;
  padding: 8px 12px 8px 16px;
  border-bottom: 1px solid #eff0f1;
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
    color: #1f2329;
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
    background: #f5f6f7;
    color: #646a73;
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
    color: var(--workspace-text-secondary, var(--theme-text-secondary));

    &:hover {
      background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
      color: var(--workspace-text-primary, var(--theme-text-primary));
    }
  }
}

.dock-body {
  flex: 1;
  min-height: 0;
  background: #fbfbfc;

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
    color: #1f2329;
  }
}

.message-row {
  display: flex;
  margin-bottom: 14px;

  &.user {
    justify-content: flex-end;

    .message-bubble {
      background: var(--ed-color-primary-1a, #1cba901a);
      border-color: var(--ed-color-primary-33, #1cba9033);
      color: #1f2329;
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
  border: 1px solid #eff0f1;
  border-radius: 8px;
  background: #fff;
  font-size: 14px;
  line-height: 22px;
  word-break: break-word;

  &.error {
    border-color: #f5c2c7;
    background: #fff5f5;
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
  background: #fff;
}

.analysis-trace {
  padding: 12px;
  margin-bottom: 10px;

  .trace-title {
    margin-bottom: 8px;
    font-size: 13px;
    font-weight: 600;
    color: #1f2329;
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
    color: #646a73;
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
    color: #1f2329;
  }

  .plan-steps {
    margin: 8px 0 0;
    padding-left: 20px;
    color: #4e5969;

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
    color: #1f2329;
  }

  .block-purpose {
    margin-top: 3px;
    font-size: 12px;
    line-height: 18px;
    color: #646a73;
  }

  .chart-type {
    flex-shrink: 0;
    height: 20px;
    padding: 0 6px;
    border-radius: 4px;
    background: #f2f3f5;
    color: #4e5969;
    font-size: 12px;
    line-height: 20px;
  }
}

.chart-frame {
  height: 240px;
  min-height: 240px;
  margin-bottom: 10px;
  border: 1px solid #eef0f2;
  border-radius: 6px;
  background: #fff;
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
  color: #8f959e;
  text-align: center;
}

.block-summary {
  display: block;
  margin-top: 4px;
}

.block-details {
  margin-top: 8px;
  border-top: 1px solid #f0f1f2;
  padding-top: 8px;

  summary {
    width: fit-content;
    cursor: pointer;
    color: #4e5969;
    font-size: 13px;
    line-height: 20px;
  }

  pre {
    max-height: 180px;
    margin: 8px 0 0;
    padding: 10px;
    border-radius: 6px;
    background: #f7f8fa;
    color: #1f2329;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
}

.preview-table-wrap {
  max-height: 220px;
  margin-top: 8px;
  overflow: auto;
  border: 1px solid #eef0f2;
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
    border-bottom: 1px solid #eef0f2;
    text-align: left;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  th {
    position: sticky;
    top: 0;
    z-index: 1;
    background: #f7f8fa;
    color: #4e5969;
    font-weight: 600;
  }

  td {
    color: #1f2329;
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
  background: #fbfbfc;

  .input-shell {
    position: relative;
  }

  :deep(.ed-textarea__inner) {
    height: 96px;
    min-height: 96px !important;
    max-height: 96px;
    padding: 10px 48px 36px 12px;
    border-radius: 8px;
    line-height: 22px;
    background: #f8f9fa;
    overflow-y: auto;
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
