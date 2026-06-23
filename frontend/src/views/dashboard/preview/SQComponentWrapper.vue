<script setup lang="ts">
import { ref, toRefs, computed, nextTick, onBeforeUnmount } from 'vue'
import { findComponent } from '@/views/dashboard/components/component-list.ts'
import { ChatLineSquare, Close, Download, RefreshRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { analysisAssistantApi, type AnalysisAssistantMessage } from '@/api/analysisAssistant'
import { dashboardApi } from '@/api/dashboard.ts'
import { parseSseChunk } from '@/utils/sse'
import { useEmitt } from '@/utils/useEmitt.ts'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import icon_send_filled from '@/assets/svg/icon_send_filled.svg'
import {
  resolveReportPopoverStyle,
  type ReportPopoverStyle,
} from '@/views/dashboard/preview/reportPopoverPosition'

const componentWrapperInnerRef = ref(null)
const { t } = useI18n()
const { emitter } = useEmitt()

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
const reportTriggerRef = ref<HTMLElement | null>(null)
const reportPopoverStyle = ref<ReportPopoverStyle | null>(null)
const wrapperId = 'wrapper-outer-id-' + configItem.value.id
const viewDemoInnerId = computed(() => 'enlarge-inner-content-' + configItem.value.id)
const reportPromptVisible = ref(false)
const reportPromptText = ref('')
const reportGenerating = ref(false)
const reportAnswer = ref('')
const reportProgress = ref('')
const reportStopped = ref(false)
const reportSubmittedQuestion = ref('')
const reportController = ref<AbortController | null>(null)
let reportStreamBuffer = ''
const isPreviewSingleChart = computed(
  () => props.showPosition === 'preview' && props.configItem?.component === 'SQView' && !props.frameless
)
const isPreviewReportTarget = computed(
  () =>
    props.showPosition === 'preview' &&
    ['SQView', 'SQTab'].includes(props.configItem?.component) &&
    !props.frameless
)
const currentViewInfo = computed(() => props.canvasViewInfo?.[props.configItem.id] || {})
const reportScopeTitle = computed(() => {
  if (props.configItem?.component === 'SQTab') {
    const activeTab = getActiveTabItem(props.configItem)
    return activeTab?.title || props.configItem?.name || t('dashboard.view')
  }
  return currentViewInfo.value?.chart?.title || t('dashboard.view')
})
const reportPromptTitle = computed(() =>
  t('dashboard.chart_report_interpret_prompt', [reportScopeTitle.value])
)
const reportDialogTitle = computed(() => reportSubmittedQuestion.value || reportPromptTitle.value)
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
  reportPopoverStyle.value = null
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
}

function handleDocumentMouseDown(event: MouseEvent) {
  if (reportHasConversation.value) {
    return
  }
  const target = event.target as Node | null
  if (!target) {
    closeReportPrompt()
    return
  }
  if (reportPromptRef.value?.contains(target)) {
    return
  }
  if (reportTriggerRef.value?.contains(target)) {
    return
  }
  if (wrapperRef.value?.querySelector('.preview-chart-actions')?.contains(target)) {
    return
  }
  closeReportPrompt()
}

function prepareReportPrompt(event?: MouseEvent) {
  abortReportGeneration(false)
  resetReportConversation()
  reportPromptText.value = ''
  reportSubmittedQuestion.value = ''
  reportTriggerRef.value = (event?.currentTarget as HTMLElement | null) || reportTriggerRef.value
  reportPopoverStyle.value = resolveReportPopoverStyle(reportTriggerRef.value, {
    width: 420,
    height: 170,
  })
  document.removeEventListener('mousedown', handleDocumentMouseDown, true)
  nextTick(() => {
    document.addEventListener('mousedown', handleDocumentMouseDown, true)
  })
}

function toggleReportPrompt(event?: MouseEvent) {
  if (reportPromptVisible.value) {
    if (reportHasConversation.value) {
      return
    }
    closeReportPrompt()
    return
  }
  prepareReportPrompt(event)
  reportPromptVisible.value = true
}

function updateReportPopoverForConversation() {
  reportPopoverStyle.value = resolveReportPopoverStyle(reportTriggerRef.value, {
    width: 500,
    height: 610,
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

function cleanFilename(name?: string) {
  return (name || t('dashboard.view')).replace(/[\\/:*?"<>|]/g, '_').slice(0, 80)
}

function cleanSheetName(name?: string, fallback?: string) {
  return (name || fallback || t('dashboard.view'))
    .replace(/[\[\]:*?/\\]/g, '_')
    .slice(0, 31) || t('dashboard.view')
}

function normalizeDatasourceId(value: any) {
  const datasourceId = Number(value)
  return Number.isFinite(datasourceId) && datasourceId > 0 ? datasourceId : undefined
}

function getResultFields(result: any) {
  return unique([
    ...(Array.isArray(result?.fields) ? result.fields : []),
    ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
  ])
}

function getAxisFields(items: any) {
  if (!Array.isArray(items)) {
    return []
  }
  return items.map((item) => item?.name || item?.value)
}

function getActiveTabItem(tabConfig: any) {
  const tabs = Array.isArray(tabConfig?.propValue) ? tabConfig.propValue : []
  if (!tabs.length) {
    return null
  }
  return tabs.find((tab: any) => tab?.name === tabConfig?.activeTabName) || tabs[0]
}

function isReportChartComponent(item: any) {
  return item?.component === 'SQView'
}

function collectReportChartEntries(
  items: any[],
  path: string[] = [],
  entries: Array<{ component: any; viewInfo: any; path: string[] }> = []
) {
  if (!Array.isArray(items)) {
    return entries
  }
  items.forEach((item) => {
    if (isReportChartComponent(item)) {
      entries.push({
        component: item,
        viewInfo: props.canvasViewInfo?.[item.id] || {},
        path,
      })
      return
    }
    if (item?.component === 'SQTab') {
      const activeTab = getActiveTabItem(item)
      const title = activeTab?.title || item?.name || t('dashboard.view')
      collectReportChartEntries(activeTab?.componentData || [], [...path, title], entries)
    }
  })
  return entries
}

function getReportChartEntries() {
  if (props.configItem?.component === 'SQTab') {
    const activeTab = getActiveTabItem(props.configItem)
    const title = activeTab?.title || props.configItem?.name || t('dashboard.view')
    return collectReportChartEntries(activeTab?.componentData || [], [title])
  }
  return [
    {
      component: props.configItem,
      viewInfo: currentViewInfo.value || {},
      path: [],
    },
  ]
}

function getEntryTitle(entry: { component: any; viewInfo: any; path: string[] }, index: number) {
  return (
    entry.viewInfo?.chart?.title ||
    entry.viewInfo?.title ||
    entry.component?.name ||
    `${t('dashboard.view')} ${index + 1}`
  )
}

function getReportDatasourceId() {
  const entries = getReportChartEntries()
  const datasource = entries.find((entry) => normalizeDatasourceId(entry.viewInfo?.datasource))
    ?.viewInfo?.datasource
  return normalizeDatasourceId(datasource)
}

function buildSingleChartContext(
  entry: { component: any; viewInfo: any; path: string[] },
  index: number
) {
  const viewInfo = entry.viewInfo || {}
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
    `Chart ${index + 1}: ${getEntryTitle(entry, index)}`,
    `Container path: ${entry.path.join(' / ') || '-'}`,
    `Chart type: ${chart.type || chart.sourceType || 'unknown'}`,
    `Datasource ID: ${viewInfo.datasource || '-'}`,
    `Fields: ${fields.join(', ') || '-'}`,
    `SQL:\n${viewInfo.sql || '-'}`,
    `Visible chart data sample, up to 50 rows:\n${JSON.stringify(rows, null, 2).slice(0, 8000)}`,
  ].join('\n')
}

function buildReportContext() {
  const entries = getReportChartEntries()
  const chartContexts = entries
    .map((entry, index) => buildSingleChartContext(entry, index))
    .join('\n\n---\n\n')

  return [
    `Current dashboard report target: ${reportScopeTitle.value}`,
    `Target component type: ${props.configItem?.component || 'unknown'}`,
    `Charts included in this target: ${entries.length}`,
    chartContexts || 'No chart data was found in the current report target.',
    'Interpret only this dashboard report target. If it is a tab, use only the active tab charts listed above. Synthesize findings across all included charts, use the shown data first, keep the answer concise, and do not change dashboard configuration.',
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
  const rawQuestion = reportPromptText.value.trim()
  const nextQuestion = rawQuestion || (!reportHasConversation.value ? reportPromptTitle.value : reportSubmittedQuestion.value)
  if (!nextQuestion) {
    return
  }
  reportSubmittedQuestion.value = nextQuestion
  const datasourceId = getReportDatasourceId()
  if (!datasourceId) {
    resetReportConversation()
    reportAnswer.value = t('dashboard.chart_report_no_datasource')
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
    '请解读当前看板报表区域，重点说明关键发现、异常点、可能原因和后续建议。回答要综合当前区域内图表数据，保持简洁。',
  ].join('\n')
  reportPromptText.value = ''
  const messages: AnalysisAssistantMessage[] = [{ role: 'user', content: question }]

  try {
    const response = await analysisAssistantApi.reportInterpretation(
      messages,
      buildReportContext(),
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

function xmlText(value: any) {
  if (value === null || value === undefined) {
    return ''
  }
  const text = typeof value === 'object' ? JSON.stringify(value) : `${value}`
  const safeText = /^[=+\-@]/.test(text) ? `\t${text}` : text
  return safeText
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function collectExportFields(viewInfo: any) {
  const rows = Array.isArray(viewInfo?.data?.data) ? viewInfo.data.data : []
  const chart = viewInfo?.chart || {}
  return unique([
    ...(Array.isArray(viewInfo?.data?.fields) ? viewInfo.data.fields : []),
    ...(Array.isArray(viewInfo?.fields) ? viewInfo.fields : []),
    ...getAxisFields(chart.columns),
    ...getAxisFields(chart.xAxis),
    ...getAxisFields(chart.yAxis),
    ...getAxisFields(chart.series),
    ...rows.flatMap((row: Record<string, any>) => Object.keys(row || {})),
  ])
}

function uniqueSheetNames(names: string[]) {
  const used = new Map<string, number>()
  return names.map((name, index) => {
    const base = cleanSheetName(name, `${t('dashboard.view')} ${index + 1}`)
    const count = used.get(base) || 0
    used.set(base, count + 1)
    if (!count) {
      return base
    }
    const suffix = `_${count + 1}`
    return `${base.slice(0, 31 - suffix.length)}${suffix}`
  })
}

function buildWorksheetXml(sheetName: string, title: string, fields: string[], rows: Record<string, any>[]) {
  const headerRow = `<Row>${fields
    .map((field) => `<Cell><Data ss:Type="String">${xmlText(field)}</Data></Cell>`)
    .join('')}</Row>`
  const dataRows = rows
    .map(
      (row) =>
        `<Row>${fields
          .map((field) => `<Cell><Data ss:Type="String">${xmlText(row?.[field])}</Data></Cell>`)
          .join('')}</Row>`
    )
    .join('')
  return `<Worksheet ss:Name="${xmlText(sheetName)}"><Table><Row><Cell ss:MergeAcross="${Math.max(fields.length - 1, 0)}"><Data ss:Type="String">${xmlText(title)}</Data></Cell></Row>${headerRow}${dataRows}</Table></Worksheet>`
}

async function refreshChartData() {
  if (isPreviewSingleChart.value) {
    ;(component.value as any)?.refreshData?.()
    return
  }
  const entries = getReportChartEntries()
  if (!entries.length) {
    return
  }
  let successCount = 0
  let failedCount = 0
  await Promise.all(
    entries.map(async (entry) => {
      const viewInfo = entry.viewInfo
      if (!viewInfo?.datasource || !viewInfo?.sql?.trim()) {
        failedCount += 1
        return
      }
      try {
        const result = await dashboardApi.preview_sql({
          datasource: viewInfo.datasource,
          sql: viewInfo.sql.trim(),
        })
        const fields = getResultFields(result)
        const data = Array.isArray(result?.data) ? result.data : []
        if (!viewInfo.data || typeof viewInfo.data !== 'object') {
          viewInfo.data = {}
        }
        viewInfo.data.fields = fields
        viewInfo.data.data = data
        viewInfo.fields = fields
        viewInfo.status = result?.status || 'success'
        viewInfo.message = result?.message || ''
        if (viewInfo.status === 'failed') {
          failedCount += 1
        } else {
          successCount += 1
        }
        emitter.emit(`view-render-${viewInfo.id || entry.component?.id}`)
      } catch (error: any) {
        viewInfo.status = 'failed'
        viewInfo.message = error?.message || t('dashboard.chart_refresh_failed')
        failedCount += 1
      }
    })
  )
  if (successCount > 0 && failedCount === 0) {
    ElMessage.success(t('dashboard.chart_refresh_success'))
  } else if (successCount > 0) {
    ElMessage.warning(`${t('dashboard.chart_refresh_success')} (${successCount}/${entries.length})`)
  } else {
    ElMessage.error(t('dashboard.chart_refresh_failed'))
  }
}

function exportChartTableData() {
  if (isPreviewSingleChart.value) {
    ;(component.value as any)?.exportTableData?.()
    return
  }
  const rawSheets = getReportChartEntries()
    .map((entry, index) => {
      const rows = Array.isArray(entry.viewInfo?.data?.data) ? entry.viewInfo.data.data : []
      const fields = collectExportFields(entry.viewInfo)
      if (!rows.length || !fields.length) {
        return null
      }
      const title = getEntryTitle(entry, index)
      return {
        title,
        fields,
        rows,
      }
    })
    .filter(Boolean) as Array<{ title: string; fields: string[]; rows: Record<string, any>[] }>

  if (!rawSheets.length) {
    ElMessage.warning(t('dashboard.chart_export_no_data'))
    return
  }

  const sheetNames = uniqueSheetNames(rawSheets.map((sheet) => sheet.title))
  const worksheets = rawSheets
    .map((sheet, index) => buildWorksheetXml(sheetNames[index], sheet.title, sheet.fields, sheet.rows))
    .join('')
  const workbook = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:o="urn:schemas-microsoft-com:office:office"
  xmlns:x="urn:schemas-microsoft-com:office:excel"
  xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"
  xmlns:html="http://www.w3.org/TR/REC-html40">${worksheets}</Workbook>`
  const blob = new Blob(['\ufeff' + workbook], { type: 'application/vnd.ms-excel;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `${cleanFilename(reportScopeTitle.value)}.xls`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(link.href)
  ElMessage.success(t('dashboard.chart_export_success'))
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
    :class="{
      'is-frameless': frameless,
      'is-report-open': reportPromptVisible,
      'is-report-tab-target': configItem.component === 'SQTab',
      'is-report-chart-target': configItem.component === 'SQView',
    }"
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
    <div v-if="isPreviewReportTarget" class="preview-chart-actions" @click.stop @mousedown.stop>
      <el-button
        class="preview-action-btn"
        text
        :title="t('dashboard.chart_report_interpret')"
        :aria-label="t('dashboard.chart_report_interpret')"
        @click.stop="toggleReportPrompt($event)"
      >
        <el-icon size="16"><ChatLineSquare /></el-icon>
      </el-button>
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
    <Teleport to="body">
      <div
        v-if="reportPromptVisible"
        ref="reportPromptRef"
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
          <div class="report-answer-tip">
            {{ t('dashboard.chart_report_ai_tip') }}
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
    </Teleport>
  </div>
</template>

<style lang="less" scoped>
.wrapper-outer {
  position: absolute;
  overflow: hidden;
  --preview-action-top: 10px;
  --preview-action-right: 16px;
  --preview-action-gap: 4px;
  --report-popover-top: 38px;
  --report-popover-right: var(--preview-action-right);
  --report-popover-horizontal-gap: calc(var(--report-popover-right) * 2);
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

  &.is-report-open {
    z-index: 200;
    overflow: visible;
  }

  &.is-report-chart-target {
    --preview-action-top: 10px;
    --report-popover-top: 38px;
  }

  &.is-report-tab-target {
    --preview-action-top: 10px;
    --report-popover-top: 38px;
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
  top: var(--preview-action-top);
  right: var(--preview-action-right);
  z-index: 25;
  display: inline-flex;
  align-items: center;
  gap: var(--preview-action-gap);
  opacity: 0;
  pointer-events: none;
  transform: translateY(-2px);
  transition:
    opacity 0.14s ease,
    transform 0.14s ease;
}

.wrapper-outer:hover .preview-chart-actions,
.preview-chart-actions:hover,
.wrapper-outer.is-report-open .preview-chart-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0);
}

.preview-action-btn {
  width: 20px;
  min-width: 20px;
  height: 20px;
  margin-left: 0 !important;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  box-shadow: none;
  color: #394b63;
  line-height: 20px;

  &:hover,
  &:focus {
    color: #2f6bff;
    background: rgba(47, 107, 255, 0.1);
  }
}

</style>
