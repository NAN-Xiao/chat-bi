<script setup lang="ts">
import { ref, toRefs, computed, nextTick, onBeforeUnmount } from 'vue'
import { findComponent } from '@/views/dashboard/components/component-list.ts'
import { ChatLineSquare, Close, Download, RefreshRight } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { analysisAssistantApi, type AnalysisAssistantMessage } from '@/api/analysisAssistant'
import { parseSseChunk } from '@/utils/sse'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import icon_send_filled from '@/assets/svg/icon_send_filled.svg'

const componentWrapperInnerRef = ref(null)
const { t } = useI18n()

const props = defineProps({
  active: {
    type: Boolean,
    default: false,
  },
  configItem: {
    type: Object,
    required: true,
  },
  canvasViewInfo: {
    type: Object,
    required: true,
  },
  showPosition: {
    required: false,
    type: String,
    default: 'preview',
  },
  canvasId: {
    type: String,
    default: 'canvas-main',
  },
  frameless: {
    type: Boolean,
    default: false,
  },
})
const { configItem, showPosition } = toRefs(props)
const component = ref(null)
const wrapperRef = ref<HTMLElement | null>(null)
const reportPromptRef = ref<HTMLElement | null>(null)
const wrapperId = 'wrapper-outer-id-' + configItem.value.id
const viewDemoInnerId = computed(() => 'enlarge-inner-content-' + configItem.value.id)
const reportPromptVisible = ref(false)
const reportPromptText = ref('')
const reportGenerating = ref(false)
const reportAnswer = ref('')
const reportProgress = ref('')
const reportStopped = ref(false)
const reportController = ref<AbortController | null>(null)
let reportStreamBuffer = ''
const isPreviewChart = computed(
  () => props.showPosition === 'preview' && props.configItem?.component === 'SQView' && !props.frameless
)
const currentViewInfo = computed(() => props.canvasViewInfo?.[props.configItem.id] || {})
const chartTitle = computed(
  () => currentViewInfo.value?.chart?.title || t('dashboard.view')
)
const reportPromptTitle = computed(() =>
  t('dashboard.chart_report_interpret_prompt', [chartTitle.value])
)
const reportHasConversation = computed(
  () =>
    reportGenerating.value ||
    reportStopped.value ||
    Boolean(reportAnswer.value.trim()) ||
    Boolean(reportProgress.value.trim())
)

function resetReportConversation() {
  reportAnswer.value = ''
  reportProgress.value = ''
  reportStopped.value = false
  reportStreamBuffer = ''
}

function abortReportGeneration(markStopped = false) {
  if (!reportGenerating.value && !reportController.value) {
    return
  }
  reportController.value?.abort()
  reportController.value = null
  reportGenerating.value = false
  reportProgress.value = ''
  if (markStopped) {
    reportStopped.value = true
    if (!reportAnswer.value.trim()) {
      reportAnswer.value = t('dashboard.chart_report_stopped')
    }
  }
}

function closeReportPrompt() {
  abortReportGeneration(false)
  reportPromptVisible.value = false
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
}

function handleDocumentMouseDown(event: MouseEvent) {
  const target = event.target as Node | null
  if (!target) {
    closeReportPrompt()
    return
  }
  if (reportPromptRef.value?.contains(target)) {
    return
  }
  if (wrapperRef.value?.querySelector('.preview-chart-actions')?.contains(target)) {
    return
  }
  closeReportPrompt()
}

function openReportPrompt() {
  abortReportGeneration(false)
  resetReportConversation()
  reportPromptText.value = ''
  reportPromptVisible.value = true
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
  nextTick(() => {
    document.addEventListener('mousedown', handleDocumentMouseDown, true)
  })
}

function unique(values: Array<string | undefined | null>) {
  return Array.from(
    new Set(
      values
        .filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '')
        .map((value) => `${value}`)
    )
  )
}

function normalizeDatasourceId(value: any) {
  const datasourceId = Number(value)
  return Number.isFinite(datasourceId) && datasourceId > 0 ? datasourceId : undefined
}

function getAxisFields(items: any) {
  if (!Array.isArray(items)) {
    return []
  }
  return items.map((item) => item?.name || item?.value)
}

function buildReportContext() {
  const viewInfo = currentViewInfo.value || {}
  const chart = viewInfo.chart || {}
  const rows = Array.isArray(viewInfo.data?.data) ? viewInfo.data.data.slice(0, 50) : []
  const fields = unique([
    ...(Array.isArray(viewInfo.data?.fields) ? viewInfo.data.fields : []),
    ...(Array.isArray(viewInfo.fields) ? viewInfo.fields : []),
    ...getAxisFields(chart.columns),
    ...getAxisFields(chart.xAxis),
    ...getAxisFields(chart.yAxis),
    ...getAxisFields(chart.series),
    ...rows.flatMap((row: Record<string, any>) => Object.keys(row || {})),
  ])

  return [
    `Current dashboard chart: ${chartTitle.value}`,
    `Chart type: ${chart.type || chart.sourceType || 'unknown'}`,
    `Fields: ${fields.join(', ') || '-'}`,
    `SQL:\n${viewInfo.sql || '-'}`,
    `Visible chart data sample, up to 50 rows:\n${JSON.stringify(rows, null, 2).slice(0, 12000)}`,
    'Interpret only this dashboard chart. Use the shown data first, keep the answer concise, and do not change dashboard configuration.',
  ].join('\n\n')
}

function appendReportText(content?: string, withSpacer = false) {
  if (!content) {
    return
  }
  if (withSpacer && reportAnswer.value.trim()) {
    reportAnswer.value += '\n\n'
  }
  reportAnswer.value += content
}

function processReportPayload(payload: string) {
  if (!payload || payload === '[DONE]') {
    return
  }
  try {
    const data = JSON.parse(payload)
    if (data.type === 'answer' || data.type === 'plan_delta') {
      appendReportText(data.content || '')
    }
    if (data.type === 'trace' || data.type === 'progress') {
      reportProgress.value = data.content || ''
    }
    if (data.type === 'block' && data.block?.summary) {
      const title = data.block?.title ? `### ${data.block.title}\n` : ''
      appendReportText(`${title}${data.block.summary}`, true)
      reportProgress.value = ''
    }
    if (data.type === 'final_delta') {
      appendReportText(data.content || '')
      reportProgress.value = ''
    }
    if (data.type === 'final' && !reportAnswer.value.trim()) {
      appendReportText(data.content || '')
      reportProgress.value = ''
    }
    if (data.type === 'error') {
      appendReportText(data.content || t('dashboard.chart_report_error'), true)
      reportProgress.value = ''
    }
  } catch (error) {
    console.error(error)
  }
}

function appendReportStreamText(text: string) {
  const { buffer, payloads } = parseSseChunk(reportStreamBuffer, text)
  reportStreamBuffer = buffer
  payloads.forEach(processReportPayload)
}

function stopReportGeneration() {
  abortReportGeneration(true)
}

async function submitReportPrompt() {
  if (reportGenerating.value) {
    return
  }
  const datasourceId = normalizeDatasourceId(currentViewInfo.value?.datasource)
  if (!datasourceId) {
    resetReportConversation()
    reportAnswer.value = t('dashboard.chart_report_no_datasource')
    return
  }

  resetReportConversation()
  reportGenerating.value = true
  const controller = new AbortController()
  reportController.value = controller
  const question = [
    reportPromptText.value.trim() || reportPromptTitle.value,
    'Please interpret the current dashboard chart. Focus on key findings, anomalies, possible causes, and suggested follow-up actions.',
  ].join('\n')
  const messages: AnalysisAssistantMessage[] = [{ role: 'user', content: question }]

  try {
    const response = await analysisAssistantApi.chat(
      messages,
      buildReportContext(),
      datasourceId,
      null,
      null,
      controller
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
      if (done) {
        break
      }
      appendReportStreamText(decoder.decode(value, { stream: true }))
    }
    appendReportStreamText(decoder.decode())
    if (reportStreamBuffer.trim()) {
      appendReportStreamText('\n\n')
    }
  } catch (error: any) {
    if (error?.name !== 'AbortError') {
      appendReportText(error?.message || t('dashboard.chart_report_error'), true)
    }
  } finally {
    if (!reportStopped.value && !reportAnswer.value.trim()) {
      reportAnswer.value = t('dashboard.chart_report_empty')
    }
    reportGenerating.value = false
    reportController.value = null
    reportProgress.value = ''
  }
}

function refreshChartData() {
  ;(component.value as any)?.refreshData?.()
}

function exportChartTableData() {
  ;(component.value as any)?.exportTableData?.()
}

onBeforeUnmount(() => {
  abortReportGeneration(false)
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
})
</script>

<template>
  <div
    :id="wrapperId"
    ref="wrapperRef"
    class="wrapper-outer"
    :class="{ 'is-frameless': frameless }"
  >
    <div :id="viewDemoInnerId" ref="componentWrapperInnerRef" class="wrapper-inner">
      <div class="wrapper-inner-adaptor">
        <component
          :is="findComponent(configItem['component'])"
          ref="component"
          class="component"
          :canvas-view-info="canvasViewInfo"
          :view-info="canvasViewInfo[configItem.id]"
          :config-item="configItem"
          :show-position="showPosition"
          :disabled="true"
          :active="active"
        />
      </div>
    </div>
    <div v-if="isPreviewChart" class="preview-chart-actions" @click.stop @mousedown.stop>
      <el-tooltip effect="dark" :content="t('dashboard.chart_report_interpret')" placement="top">
        <el-button class="preview-action-btn" text @click="openReportPrompt">
          <el-icon size="16"><ChatLineSquare /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip effect="dark" :content="t('dashboard.chart_refresh_data')" placement="top">
        <el-button class="preview-action-btn" text @click="refreshChartData">
          <el-icon size="16"><RefreshRight /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip effect="dark" :content="t('dashboard.chart_export_table')" placement="top">
        <el-button class="preview-action-btn" text @click="exportChartTableData">
          <el-icon size="16"><Download /></el-icon>
        </el-button>
      </el-tooltip>
    </div>
    <div
      v-if="reportPromptVisible"
      ref="reportPromptRef"
      class="report-prompt-popover"
      @click.stop
      @mousedown.stop
    >
      <template v-if="!reportHasConversation">
        <el-input
          v-model="reportPromptText"
          class="report-prompt-input"
          :placeholder="t('dashboard.chart_report_interpret_placeholder')"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          @keydown.stop
          @keyup.stop
        />
        <div class="report-prompt-footer">
          <div class="report-prompt-title">
            <el-icon size="15"><ChatLineSquare /></el-icon>
            <span>{{ reportPromptTitle }}</span>
          </div>
          <el-button
            class="report-prompt-send"
            circle
            type="primary"
            @click="submitReportPrompt"
          >
            <el-icon size="16">
              <icon_send_filled />
            </el-icon>
          </el-button>
        </div>
      </template>
      <template v-else>
        <div class="report-dialog-header">
          <div class="report-prompt-title">
            <el-icon size="15"><ChatLineSquare /></el-icon>
            <span>{{ reportPromptTitle }}</span>
          </div>
          <el-button class="report-close-btn" text circle @click="closeReportPrompt">
            <el-icon size="16"><Close /></el-icon>
          </el-button>
        </div>
        <div class="report-answer-panel">
          <MdComponent v-if="reportAnswer.trim()" :message="reportAnswer" />
          <div v-else class="report-answer-empty">
            {{ reportProgress || t('dashboard.chart_report_generating') }}
          </div>
          <div v-if="reportProgress && reportAnswer.trim()" class="report-progress">
            {{ reportProgress }}
          </div>
        </div>
        <div class="report-conversation-footer">
          <span class="report-status">
            {{
              reportGenerating
                ? t('dashboard.chart_report_generating')
                : reportStopped
                  ? t('dashboard.chart_report_stopped')
                  : ''
            }}
          </span>
          <el-button
            v-if="reportGenerating"
            class="report-stop-btn"
            round
            @click="stopReportGeneration"
          >
            <span class="stop-square"></span>
            <span>{{ t('dashboard.chart_report_stop') }}</span>
          </el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<style lang="less" scoped>
.wrapper-outer {
  position: absolute;
  overflow: hidden;
  background: var(--workspace-card-bg, #ffffff);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  box-shadow:
    0 2px 8px rgba(18, 34, 66, 0.035),
    0 1px 2px rgba(18, 34, 66, 0.025);
  transform-origin: center;
  transition:
    transform 0.14s ease,
    box-shadow 0.14s ease,
    border-color 0.14s ease;
  will-change: transform, box-shadow;

  &:hover {
    z-index: 20;
    border-color: rgba(47, 107, 255, 0.18);
    box-shadow:
      0 8px 20px rgba(18, 34, 66, 0.1),
      0 3px 8px rgba(18, 34, 66, 0.06);
    transform: translateY(-2px);
  }

  &:active {
    box-shadow:
      0 6px 16px rgba(18, 34, 66, 0.08),
      0 2px 6px rgba(18, 34, 66, 0.05);
    transform: translateY(0);
  }

  &.is-frameless {
    border: none;
    border-radius: 0;
    box-shadow: none;
    transition: none;
    will-change: auto;

    &:hover {
      z-index: auto;
      border-color: transparent;
      box-shadow: none;
      transform: none;
    }

    .wrapper-inner {
      border-radius: 0;
    }
  }

  .wrapper-inner {
    width: 100%;
    height: 100%;
    position: relative;
    background: var(--workspace-card-bg, #ffffff);
    background-size: 100% 100% !important;
    .wrapper-inner-adaptor {
      position: relative;
      transform-style: preserve-3d;
      width: 100%;
      height: 100%;
      .component {
        width: 100%;
        height: 100%;
      }
    }
  }
}

.preview-chart-actions {
  position: absolute;
  top: 18px;
  right: 24px;
  z-index: 25;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-2px);
  transition:
    opacity 0.14s ease,
    transform 0.14s ease;
}

.wrapper-outer:hover .preview-chart-actions,
.preview-chart-actions:hover,
.report-prompt-popover:hover + .preview-chart-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.preview-action-btn {
  width: 24px;
  min-width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  box-shadow: none;
  color: #394b63;

  &:hover,
  &:focus {
    color: #2f6bff;
    background: rgba(47, 107, 255, 0.1);
  }
}

.report-prompt-popover {
  position: absolute;
  top: 42px;
  right: 24px;
  z-index: 30;
  width: min(420px, calc(100% - 48px));
  padding: 16px;
  border: 2px solid #4f7df3;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 18px 42px rgba(47, 107, 255, 0.16);
}

.report-prompt-input {
  :deep(.ed-textarea__inner) {
    min-height: 42px !important;
    padding: 8px 0;
    border: 0;
    box-shadow: none;
    resize: none;
  }
}

.report-prompt-footer {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}

.report-prompt-title {
  display: flex;
  flex: 1;
  align-items: center;
  min-width: 0;
  gap: 6px;
  color: #1f2329;
  font-size: 14px;
  line-height: 22px;
  font-weight: 500;

  span {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.report-prompt-send {
  width: 32px;
  min-width: 32px;
  height: 32px;
  background: #4f7df3;
  border-color: #4f7df3;

  &:hover,
  &:focus {
    background: #2f6bff;
    border-color: #2f6bff;
  }
}

.report-dialog-header,
.report-conversation-footer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.report-dialog-header {
  margin-bottom: 12px;
}

.report-close-btn {
  width: 26px;
  min-width: 26px;
  height: 26px;
  margin-left: auto;
  color: #65758c;

  &:hover,
  &:focus {
    color: #2f6bff;
    background: rgba(47, 107, 255, 0.1);
  }
}

.report-answer-panel {
  min-height: 92px;
  max-height: 260px;
  overflow: auto;
  color: #1f2329;
  font-size: 13px;
  line-height: 1.65;

  :deep(.markdown-body) {
    color: inherit;
    font-size: inherit;
    line-height: inherit;
    background: transparent;
  }

  :deep(.markdown-body > :first-child) {
    margin-top: 0;
  }

  :deep(.markdown-body > :last-child) {
    margin-bottom: 0;
  }
}

.report-answer-empty,
.report-progress,
.report-status {
  color: #74849a;
  font-size: 13px;
}

.report-progress {
  margin-top: 10px;
}

.report-conversation-footer {
  justify-content: space-between;
  margin-top: 12px;
}

.report-status {
  min-height: 24px;
  line-height: 24px;
}

.report-stop-btn {
  height: 30px;
  padding: 0 12px;
  border-color: #d7e1ef;
  color: #394b63;
  background: #ffffff;

  &:hover,
  &:focus {
    border-color: #4f7df3;
    color: #2f6bff;
    background: rgba(79, 125, 243, 0.08);
  }
}

.stop-square {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 6px;
  border-radius: 2px;
  background: currentColor;
}
</style>
