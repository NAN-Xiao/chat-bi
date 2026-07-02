<script setup lang="ts">
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import { ChatLineSquare, Close, RefreshRight } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { useRouter } from 'vue-router'
import { analysisAssistantApi, type AnalysisAssistantMessage } from '@/api/analysisAssistant'
import { parseSseChunk } from '@/utils/sse'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import icon_send_filled from '@/assets/svg/icon_send_filled.svg'
import {
  resolveReportPopoverStyle,
  type ReportPopoverStyle,
} from '@/views/dashboard/preview/reportPopoverPosition'
const { t } = useI18n()
const router = useRouter()

const edit = () => {
  router.push({
    path: '/canvas',
    query: props.platformTemplate
      ? { platformTemplateId: props.dashboardInfo.id }
      : { resourceId: props.dashboardInfo.id },
  })
}
const props = defineProps({
  dashboardInfo: {
    type: Object,
    required: false,
    default: () => ({}),
  },
  componentData: {
    type: Array,
    required: false,
    default: () => [],
  },
  canvasViewInfo: {
    type: Object,
    required: false,
    default: () => ({}),
  },
  platformTemplate: {
    type: Boolean,
    default: false,
  },
  getReportContextSnapshots: {
    type: Function,
    required: false,
    default: null,
  },
})
const canEdit = computed(() => props.dashboardInfo?.canEdit === true)
const canInterpretDashboard = computed(() => !!props.dashboardInfo?.id && !props.platformTemplate)
const titleText = computed(() => props.dashboardInfo?.name || t('dashboard.dashboard'))
const reportPromptText = ref('')
const reportPromptVisible = ref(false)
const reportGenerating = ref(false)
const reportAnswer = ref('')
const reportProgress = ref('')
const reportStopped = ref(false)
const reportSubmittedQuestion = ref('')
const reportController = ref<AbortController | null>(null)
const reportPanelRef = ref<HTMLElement | null>(null)
const reportTriggerRef = ref<HTMLElement | null>(null)
const reportPopoverStyle = ref<ReportPopoverStyle | null>(null)
let reportStreamBuffer = ''

const reportPromptTitle = computed(() =>
  t('dashboard.dashboard_report_interpret_prompt', [titleText.value])
)
const reportDialogTitle = computed(() => reportSubmittedQuestion.value || reportPromptTitle.value)
const reportTargetContext = computed(() =>
  t('dashboard.dashboard_report_target_context', [titleText.value])
)
const reportHasConversation = computed(
  () =>
    reportGenerating.value ||
    reportStopped.value ||
    Boolean(reportAnswer.value.trim()) ||
    Boolean(reportProgress.value.trim())
)

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

function normalizeReportGroupValue(value: any) {
  if (value === undefined || value === null) {
    return ''
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? '' : value.toISOString()
  }
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch (_error) {
      return `${value}`
    }
  }
  return `${value}`.trim()
}

function rowsAfterStoredPivotFilters(viewInfo: any, rows: Record<string, any>[]) {
  const pivot = viewInfo?.pivot || {}
  const groupField = `${pivot.group_field || ''}`.trim()
  const groupValues = Array.isArray(pivot.group_values)
    ? unique(pivot.group_values.map(normalizeReportGroupValue))
    : []
  if (
    pivot.enabled !== true ||
    pivot.group_enabled === false ||
    !groupField ||
    groupValues.length === 0
  ) {
    return rows
  }
  const allowed = new Set(groupValues)
  return rows.filter((row) => allowed.has(normalizeReportGroupValue(row?.[groupField])))
}

function visibleValueWhitelist(rows: Record<string, any>[], preferredFields: string[]) {
  const fields = unique([
    ...preferredFields,
    ...rows.slice(0, 20).flatMap((row) => Object.keys(row || {})),
  ]).slice(0, 12)
  const lines = fields
    .map((field) => {
      const values = unique(
        rows
          .map((row) => normalizeReportGroupValue(row?.[field]))
          .filter((value) => value !== '')
      ).slice(0, 30)
      return values.length ? `${field}: ${values.join(', ')}` : ''
    })
    .filter(Boolean)
  return lines.length ? lines.join('\n') : '-'
}

function collectDashboardChartEntries(
  items: any[],
  path: string[] = [],
  entries: Array<{ component: any; viewInfo: any; path: string[] }> = []
) {
  if (!Array.isArray(items)) {
    return entries
  }
  items.forEach((item) => {
    if (item?.component === 'SQView') {
      entries.push({
        component: item,
        viewInfo: props.canvasViewInfo?.[item.id] || {},
        path,
      })
      return
    }
    if (item?.component === 'SQTab') {
      const tabs = Array.isArray(item.propValue) ? item.propValue : []
      tabs.forEach((tab: any) => {
        const title = tab?.title || tab?.name || item?.name || t('dashboard.view')
        collectDashboardChartEntries(tab?.componentData || [], [...path, title], entries)
      })
      return
    }
    if (Array.isArray(item?.componentData)) {
      collectDashboardChartEntries(
        item.componentData,
        [...path, item?.name || item?.component || t('dashboard.view')],
        entries
      )
    }
  })
  return entries
}

function getDashboardChartEntries() {
  return collectDashboardChartEntries(props.componentData as any[])
}

function getEntryTitle(entry: { component: any; viewInfo: any; path: string[] }, index: number) {
  return (
    entry.viewInfo?.chart?.title ||
    entry.viewInfo?.title ||
    entry.component?.name ||
    `${t('dashboard.view')} ${index + 1}`
  )
}

function getDashboardDatasourceId() {
  const dashboardDatasource = normalizeDatasourceId(props.dashboardInfo?.datasource)
  if (dashboardDatasource) {
    return dashboardDatasource
  }
  const datasource = getDashboardChartEntries().find((entry) =>
    normalizeDatasourceId(entry.viewInfo?.datasource)
  )?.viewInfo?.datasource
  return normalizeDatasourceId(datasource)
}

function getRuntimeReportContextSnapshots() {
  const snapshots = props.getReportContextSnapshots?.()
  return snapshots && typeof snapshots === 'object' ? snapshots : {}
}

function buildSingleChartContext(
  entry: { component: any; viewInfo: any; path: string[] },
  index: number,
  snapshots: Record<string, any> = {}
) {
  const viewInfo = entry.viewInfo || {}
  const chart = viewInfo.chart || {}
  const snapshot = snapshots?.[entry.component?.id] || null
  const snapshotRows = Array.isArray(snapshot?.data) ? snapshot.data : null
  const storedRows = Array.isArray(viewInfo.data?.data) ? viewInfo.data.data : []
  const rows = snapshotRows || rowsAfterStoredPivotFilters(viewInfo, storedRows)
  const sampleRows = rows.slice(0, 50)
  const fields = unique([
    ...(Array.isArray(snapshot?.fields) ? snapshot.fields : []),
    ...(Array.isArray(viewInfo.data?.fields) ? viewInfo.data.fields : []),
    ...(Array.isArray(viewInfo.fields) ? viewInfo.fields : []),
    ...getAxisFields(chart.columns),
    ...getAxisFields(chart.xAxis),
    ...getAxisFields(chart.yAxis),
    ...getAxisFields(chart.series),
    ...sampleRows.flatMap((row: Record<string, any>) => Object.keys(row || {})),
  ])
  const pivot = snapshot?.pivot || viewInfo.pivot || {}
  const selectedGroupValues = Array.isArray(pivot?.selected_group_values)
    ? pivot.selected_group_values
    : Array.isArray(pivot?.group_values)
      ? unique(pivot.group_values.map(normalizeReportGroupValue))
      : []
  const visibleRowsLabel = snapshotRows
    ? `${snapshot.totalRows ?? rows.length} current visible rows after chart UI filters`
    : `${rows.length} rows after stored chart filters`
  const whitelist = visibleValueWhitelist(sampleRows, fields)
  const filterContext = snapshotRows
    ? [
        `Current visible row scope: ${visibleRowsLabel}; source rows before UI filters: ${snapshot?.sourceRows ?? '-'}.`,
        pivot?.enabled
          ? `Current pivot/filter state: group field=${pivot.group_field || '-'}, group enabled=${pivot.group_enabled ? 'true' : 'false'}, selected groups=${selectedGroupValues.length ? selectedGroupValues.join(', ') : 'all/none'}, selected group count=${pivot.selected_group_count ?? '-'} of ${pivot.total_group_count ?? '-'}.`
          : 'Current pivot/filter state: pivot disabled.',
      ]
    : [
        `Current visible row scope: ${visibleRowsLabel}; stored source rows before filters: ${storedRows.length}.`,
        pivot?.enabled
          ? `Stored pivot/filter state: group field=${pivot.group_field || '-'}, group enabled=${pivot.group_enabled !== false ? 'true' : 'false'}, allowed groups=${selectedGroupValues.length ? selectedGroupValues.join(', ') : 'all/none'}.`
          : 'Stored pivot/filter state: pivot disabled.',
      ]

  return [
    `Chart ${index + 1}: ${getEntryTitle(entry, index)}`,
    `Container path: ${entry.path.join(' / ') || '-'}`,
    `Chart type: ${chart.type || chart.sourceType || 'unknown'}`,
    `Datasource ID: ${viewInfo.datasource || '-'}`,
    `Fields: ${fields.join(', ') || '-'}`,
    ...filterContext,
    `Visible dimension/value whitelist. Do not mention any dimension value that is absent from this whitelist or the current visible sample:\n${whitelist}`,
    `Current visible chart data sample, up to 50 rows:\n${JSON.stringify(sampleRows, null, 2).slice(0, 8000)}`,
  ].join('\n')
}

function buildDashboardReportContext() {
  const entries = getDashboardChartEntries()
  const snapshots = getRuntimeReportContextSnapshots()
  const chartContexts = entries
    .map((entry, index) => buildSingleChartContext(entry, index, snapshots))
    .join('\n\n---\n\n')

  return [
    `Current dashboard report target: ${titleText.value}`,
    'Target component type: DASHBOARD',
    `Charts included in this dashboard: ${entries.length}`,
    chartContexts || 'No chart data was found in the current dashboard.',
    'Interpret the whole dashboard. Include all charts listed above, including charts inside tabs or containers. Use only each chart current visible data sample and visible dimension/value whitelist as data facts; do not cite countries, channels, dates, or other dimension values that are not listed there. Synthesize cross-chart findings, keep the answer concise, and do not change dashboard configuration.',
  ].join('\n\n')
}

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

function handleDocumentMouseDown(event: MouseEvent) {
  if (reportHasConversation.value) {
    return
  }
  const target = event.target as Node | null
  if (!target) {
    closeReportPanel()
    return
  }
  if (reportPanelRef.value?.contains(target)) {
    return
  }
  if (reportTriggerRef.value?.contains(target)) {
    return
  }
  closeReportPanel()
}

function openReportPanel(event?: MouseEvent) {
  if (reportPromptVisible.value && reportHasConversation.value) {
    return
  }
  abortReportGeneration(false)
  resetReportConversation()
  reportPromptText.value = ''
  reportSubmittedQuestion.value = ''
  reportTriggerRef.value = (event?.currentTarget as HTMLElement | null) || null
  reportPopoverStyle.value = resolveReportPopoverStyle(reportTriggerRef.value, {
    width: 480,
    height: 220,
  })
  reportPromptVisible.value = true
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
  nextTick(() => {
    document.addEventListener('mousedown', handleDocumentMouseDown, true)
  })
}

function closeReportPanel() {
  abortReportGeneration(false)
  reportPromptVisible.value = false
  reportPopoverStyle.value = null
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
}

function updateReportPopoverForConversation() {
  reportPopoverStyle.value = resolveReportPopoverStyle(reportTriggerRef.value, {
    width: 500,
    height: 610,
  })
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
  const rawQuestion = reportPromptText.value.trim()
  const nextQuestion = rawQuestion || (!reportHasConversation.value ? reportPromptTitle.value : reportSubmittedQuestion.value)
  if (!nextQuestion) {
    return
  }
  reportSubmittedQuestion.value = nextQuestion
  const datasourceId = getDashboardDatasourceId()
  if (!datasourceId) {
    resetReportConversation()
    reportAnswer.value = t('dashboard.dashboard_report_no_datasource')
    reportPromptText.value = ''
    return
  }

  resetReportConversation()
  updateReportPopoverForConversation()
  reportGenerating.value = true
  const controller = new AbortController()
  reportController.value = controller
  const question = [
    nextQuestion,
    '请对当前整张看板做综合解读，覆盖看板内所有图表。少复述数据，多给判断：每条结论都要说明这个信号意味着什么、有什么风险、图表间是否相互印证或矛盾，以及当前还不能判断什么；建议必须对应可见数据里的具体信号。回答要保持简洁。',
  ].join('\n')
  reportPromptText.value = ''
  const messages: AnalysisAssistantMessage[] = [{ role: 'user', content: question }]

  try {
    const response = await analysisAssistantApi.reportInterpretation(
      messages,
      buildDashboardReportContext(),
      datasourceId,
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

onBeforeUnmount(() => {
  abortReportGeneration(false)
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
})
</script>

<template>
  <div class="preview-head flex-align-center">
    <div class="canvas-name ellipsis" :class="{ 'is-placeholder': !dashboardInfo?.name }">
      {{ titleText }}
    </div>
    <div class="canvas-opt-button">
      <el-button v-if="canInterpretDashboard" secondary @click.stop="openReportPanel($event)">
        <template #icon>
          <el-icon size="16"><ChatLineSquare /></el-icon>
        </template>
        {{ t('dashboard.dashboard_report_interpret') }}
      </el-button>
      <el-button v-if="canEdit" class="custom-button" type="primary" @click="edit">
        <template #icon>
          <Icon name="icon_edit_outlined">
            <icon_edit_outlined class="svg-icon" />
          </Icon>
        </template>
        {{ t('dashboard.edit') }}
      </el-button>
    </div>
    <div
      v-if="reportPromptVisible"
      ref="reportPanelRef"
      class="dashboard-report-popover"
      :class="{ 'is-conversation': reportHasConversation }"
      :style="reportPopoverStyle || {}"
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
          <div class="report-dialog-title">
            <span>{{ reportDialogTitle }}</span>
          </div>
          <el-button class="report-close-btn" text circle @click="closeReportPanel">
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
        <div class="report-answer-tip">
          {{ t('dashboard.chart_report_ai_tip') }}
        </div>
        <div class="report-target-context" :title="reportTargetContext">
          {{ reportTargetContext }}
        </div>
        <div class="report-conversation-tools">
          <el-button class="report-icon-tool" text circle @click="submitReportPrompt">
            <el-icon size="15"><RefreshRight /></el-icon>
          </el-button>
        </div>
        <div class="report-chat-input">
          <el-input
            v-model="reportPromptText"
            class="report-followup-input"
            :placeholder="t('dashboard.chart_report_followup_placeholder')"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            :disabled="reportGenerating"
            @keydown.enter.exact.prevent="submitReportPrompt"
            @keydown.stop
            @keyup.stop
          />
          <el-button
            v-if="reportGenerating"
            class="report-stop-circle"
            circle
            :aria-label="t('dashboard.chart_report_stop')"
            @click="stopReportGeneration"
          >
            <span class="stop-square"></span>
          </el-button>
          <el-button
            v-else
            class="report-prompt-send"
            circle
            type="primary"
            :disabled="!reportPromptText.trim()"
            @click="submitReportPrompt"
          >
            <el-icon size="16">
              <icon_send_filled />
            </el-icon>
          </el-button>
        </div>
      </template>
    </div>
  </div>
</template>

<style lang="less">
.pad12 {
  .ed-dropdown-menu__item {
    padding: 5px 36px 5px 12px !important;

    .ed-icon {
      margin-right: 8px;
    }

    .arrow-right_icon {
      position: absolute;
      right: 12px;
      margin-right: 0;
    }

    &:has(.arrow-right_icon) {
      width: 100%;
    }
  }
}

.preview-head {
  position: relative;
  display: flex;
  width: 100%;
  min-width: 300px;
  height: 50px;
  padding: 14px 16px 0;
  border-bottom: 0;
  background: transparent;

  .canvas-name {
    max-width: 280px;
    font-size: 17px;
    font-weight: 600;
    color: var(--workspace-text-primary, #1b2a41);

    &.is-placeholder {
      color: var(--workspace-text-secondary, #66758f);
      font-weight: 500;
    }
  }

  .canvas-have-update {
    background-color: rgba(52, 199, 36, 0.2);
    color: rgba(44, 169, 31, 1);
    font-weight: 400;
    font-size: 12px;
    line-height: 20px;
    vertical-align: middle;
    padding: 0 4px;
    margin-left: 8px;
  }

  .custom-icon {
    cursor: pointer;
    margin-left: 8px;
  }

  .create-area {
    color: var(--workspace-text-secondary, #66758f);
    font-weight: 400;
    font-size: 14px;
  }

  .canvas-opt-button {
    display: flex;
    justify-content: right;
    align-items: center;
    flex: 1;
    transform: translateY(-7px);

    .head-more-icon {
      color: var(--workspace-text-primary, #1b2a41);
      margin-left: 12px;
      cursor: pointer;
      font-size: 20px;
      border-radius: 8px;
      position: relative;

      &:hover {
        &::after {
          content: '';
          position: absolute;
          top: -4px;
          left: -4px;
          border-radius: 6px;
          height: 28px;
          width: 28px;
          background: #1f23291a;
        }
      }
    }
  }
}

.info-tips {
  margin-left: 4px;
  font-size: 16px;
  color: var(--workspace-text-secondary, #66758f);
}

.custom-button {
  margin-left: 10px;
}

.dashboard-report-popover {
  position: fixed;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 16px;
  border: 2px solid #4f7df3;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 18px 42px rgba(47, 107, 255, 0.16);
  max-height: var(--report-popover-max-height, calc(100vh - 32px));
  overflow: auto;
}

.dashboard-report-popover:not(.is-conversation) {
  min-height: 0;
}

.dashboard-report-popover.is-conversation {
  width: min(500px, calc(100vw - 32px));
  height: min(610px, var(--report-popover-max-height, calc(100vh - 32px)));
  min-height: 0;
  max-height: min(610px, var(--report-popover-max-height, calc(100vh - 32px)));
  overflow: hidden;
}

.report-prompt-input {
  .ed-textarea__inner,
  .el-textarea__inner {
    min-height: 82px !important;
    max-height: 104px !important;
    padding: 8px 0;
    border: 0;
    border-radius: 0;
    box-shadow: none !important;
    background: transparent;
    color: #1f2329;
    resize: none;
    overflow-y: auto;

    &:hover,
    &:focus {
      border: 0;
      box-shadow: none !important;
      background: transparent;
    }
  }
}

.report-prompt-footer,
.report-dialog-header,
.report-conversation-tools {
  display: flex;
  align-items: center;
}

.report-prompt-footer {
  gap: 12px;
  margin-top: 10px;
}

.report-prompt-title,
.report-dialog-title {
  min-width: 0;
  flex: 1;
  color: #1f2329;
  font-weight: 600;

  span {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

.report-prompt-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  line-height: 22px;
  font-weight: 500;
}

.dashboard-report-popover .report-prompt-send,
.dashboard-report-popover .report-stop-circle {
  width: 32px !important;
  min-width: 32px !important;
  max-width: 32px !important;
  height: 32px !important;
  min-height: 32px !important;
  max-height: 32px !important;
  padding: 0 !important;
  border-radius: 50% !important;
  background: #4f7df3;
  border-color: #4f7df3;
  flex: 0 0 32px;
  line-height: 32px;

  &:hover,
  &:focus {
    background: #2f6bff;
    border-color: #2f6bff;
  }
}

.report-chat-input .report-prompt-send {
  position: absolute;
  right: 14px;
  top: 50%;
  bottom: auto;
  transform: translateY(-50%);
}

.report-dialog-header {
  flex: 0 0 auto;
  gap: 12px;
  margin-bottom: 6px;
}

.report-dialog-title {
  font-size: 18px;
  line-height: 28px;
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
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow: auto;
  color: #1f2329;
  font-size: 13px;
  line-height: 1.65;

  .markdown-body {
    color: inherit;
    font-size: inherit;
    line-height: inherit;
    background: transparent;
  }

  .markdown-body > :first-child {
    margin-top: 0;
  }

  .markdown-body > :last-child {
    margin-bottom: 0;
  }
}

.report-answer-empty,
.report-progress,
.report-answer-tip,
.report-target-context {
  color: #74849a;
  font-size: 13px;
}

.report-answer-tip {
  flex: 0 0 auto;
  margin-top: 6px;
  font-size: 12px;
  line-height: 20px;
  color: #9aa8bb;
}

.report-target-context {
  flex: 0 0 auto;
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #74849a;
  font-size: 12px;
  line-height: 20px;
}

.report-progress {
  margin-top: 10px;
}

.report-conversation-tools {
  flex: 0 0 auto;
  gap: 8px;
  margin-top: 8px;
}

.report-icon-tool {
  width: 28px;
  min-width: 0;
  height: 28px;
  padding: 0;
  border-radius: 8px;
  color: #394b63;

  &:hover,
  &:focus {
    color: #2f6bff;
    background: rgba(47, 107, 255, 0.1);
  }
}

.report-chat-input {
  position: relative;
  flex: 0 0 54px;
  height: 54px;
  min-height: 54px;
  margin-top: 12px;
  border: 1px solid #e3e9f2;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}

.report-followup-input {
  display: block;
  width: 100%;
  height: 100%;
}

.report-followup-input.ed-textarea,
.report-followup-input.el-textarea {
  height: 100%;
}

.report-followup-input {
  .ed-textarea__inner,
  .el-textarea__inner {
    display: block;
    width: 100%;
    height: 52px !important;
    min-height: 52px !important;
    max-height: 52px !important;
    padding: 15px 54px 13px 16px;
    border: 0 !important;
    border-radius: 8px;
    box-shadow: none !important;
    outline: 0 !important;
    resize: none;
    line-height: 20px;
    color: #1f2329;
    background: transparent;
    overflow-y: hidden;

    &:hover,
    &:focus {
      border: 0 !important;
      box-shadow: none !important;
      outline: 0 !important;
      background: transparent;
    }
  }
}

.report-stop-circle {
  position: absolute;
  right: 14px;
  top: 50%;
  bottom: auto;
  transform: translateY(-50%);
  border-color: #a7b9d6;
  color: #ffffff;
}

.stop-square {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 2px;
  background: currentColor;
}

.flex-align-center {
  & + & {
    margin-left: 4px;
  }
}
</style>
