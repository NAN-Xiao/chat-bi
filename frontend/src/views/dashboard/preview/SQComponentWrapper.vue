<script setup lang="ts">
import { ref, toRefs, computed, nextTick, reactive, onBeforeUnmount } from 'vue'
import { findComponent } from '@/views/dashboard/components/component-list.ts'
import {
  ChatLineSquare,
  Close,
  Download,
  FullScreen,
  MoreFilled,
  Position,
  PriceTag,
  RefreshRight,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { analysisAssistantApi, type AnalysisAssistantMessage } from '@/api/analysisAssistant'
import { dashboardApi } from '@/api/dashboard.ts'
import { parseSseChunk } from '@/utils/sse'
import { useEmitt } from '@/utils/useEmitt.ts'
import { guid } from '@/utils/canvas.ts'
import cloneDeep from 'lodash/cloneDeep'
import MdComponent from '@/views/chat/component/MdComponent.vue'
import icon_send_filled from '@/assets/svg/icon_send_filled.svg'
import ChartFullscreenDialog from '@/views/dashboard/preview/ChartFullscreenDialog.vue'
import {
  resolveReportPopoverStyle,
  type ReportPopoverStyle,
} from '@/views/dashboard/preview/reportPopoverPosition'

const componentWrapperInnerRef = ref(null)
const { t } = useI18n()
const { emitter } = useEmitt()
const CHART_REFRESH_CONCURRENCY = 2

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
  componentData: {
    type: Array,
    required: false,
    default: () => [],
  },
  canvasStyleData: {
    type: Object,
    required: false,
    default: () => ({}),
  },
  dashboardInfo: {
    type: Object,
    required: false,
    default: () => ({}),
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
  readonlyTemplate: {
    type: Boolean,
    default: false,
  },
})
const emit = defineEmits(['chartMoved'])
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
const chartFullscreenVisible = ref(false)
const chartShowLabel = ref(false)
const moveDialogVisible = ref(false)
const moveLoading = ref(false)
const targetDashboardLoading = ref(false)
const targetDashboardList = ref<any[]>([])
const moveFormRef = ref()
const moveForm = reactive({
  dashboardId: '',
})
let reportStreamBuffer = ''
const isPreviewSingleChart = computed(
  () => props.showPosition === 'preview' && props.configItem?.component === 'SQView' && !props.frameless
)
const currentViewInfo = computed(() => props.canvasViewInfo?.[props.configItem.id] || {})
const currentChartType = computed(() => {
  const chart = currentViewInfo.value?.chart || {}
  return chart.type || chart.sourceType || 'table'
})
const canToggleChartLabel = computed(
  () =>
    isPreviewSingleChart.value &&
    !['table', 'metric'].includes(String(currentChartType.value || '').toLowerCase()) &&
    currentViewInfo.value?.status !== 'failed'
)
const isPreviewReportTarget = computed(
  () =>
    props.showPosition === 'preview' &&
    ['SQView', 'SQTab'].includes(props.configItem?.component) &&
    !props.frameless
)
const canShowReportInterpret = computed(() => isPreviewReportTarget.value)
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
const reportTargetContext = computed(() =>
  t('dashboard.chart_report_target_context', [reportScopeTitle.value])
)
const componentExtraProps = computed(() =>
  props.configItem?.component === 'SQView' ? { showLabel: chartShowLabel.value } : {}
)
const reportHasConversation = computed(
  () =>
    reportGenerating.value ||
    reportStopped.value ||
    Boolean(reportAnswer.value.trim()) ||
    Boolean(reportProgress.value.trim())
)
const canMoveChart = computed(
  () =>
    isPreviewSingleChart.value &&
    props.dashboardInfo?.id &&
    props.dashboardInfo?.dashboardMode !== 'default' &&
    props.dashboardInfo?.canEdit !== false
)
const moveFormRules = computed(() => ({
  dashboardId: [
    {
      required: true,
      message: t('dashboard.select_dashboard'),
      trigger: 'change',
    },
  ],
}))

function flattenDashboardOptions(nodes: any[] = [], level = 0, result: any[] = []) {
  nodes.forEach((node) => {
    if (node?.node_type === 'leaf' || node?.leaf === true) {
      if (
        String(node.id) !== String(props.dashboardInfo?.id) &&
        node.can_edit !== false &&
        node.is_default !== true
      ) {
        result.push({
          id: node.id,
          name: node.name,
          level,
        })
      }
      return
    }
    flattenDashboardOptions(node?.children || [], level + 1, result)
  })
  return result
}

function parseJson(value: any, fallback: any) {
  if (value === null || value === undefined || value === '') {
    return fallback
  }
  if (typeof value !== 'string') {
    return value
  }
  try {
    return JSON.parse(value)
  } catch {
    return fallback
  }
}

function maxDashboardBottom(items: any[]) {
  if (!Array.isArray(items) || !items.length) {
    return 1
  }
  return items.reduce((max, item) => {
    const y = Number(item?.y || 1)
    const sizeY = Number(item?.sizeY || 0)
    return Math.max(max, y + sizeY)
  }, 1)
}

function prepareMovedChartPayload() {
  const nextComponentId = guid()
  const componentPayload = cloneDeep(props.configItem || {})
  const viewPayload = cloneDeep(currentViewInfo.value || {})
  componentPayload.id = nextComponentId
  delete componentPayload._dragId
  componentPayload.x = 1
  viewPayload.id = nextComponentId
  if (viewPayload.chart && typeof viewPayload.chart === 'object') {
    viewPayload.chart.id = nextComponentId
  }
  if (!viewPayload.data || typeof viewPayload.data !== 'object') {
    viewPayload.data = {}
  }
  viewPayload.data.data = []
  viewPayload.data.fields = []
  viewPayload.fields = []
  viewPayload.status = 'loading'
  viewPayload.dataState = 'loading'
  viewPayload.loadingProgress = 0
  viewPayload.snapshotRefreshedAt = 0
  viewPayload.data.snapshotRefreshedAt = 0
  viewPayload.message = ''
  return {
    nextComponentId,
    componentPayload,
    viewPayload,
  }
}

function removeComponentById(items: any[] = [], componentId: any) {
  if (!Array.isArray(items)) {
    return []
  }
  return items
    .filter((item) => String(item?.id) !== String(componentId))
    .map((item) => {
      if (Array.isArray(item?.componentData)) {
        item.componentData = removeComponentById(item.componentData, componentId)
      }
      if (Array.isArray(item?.propValue)) {
        item.propValue = item.propValue.map((tab: any) => ({
          ...tab,
          componentData: removeComponentById(tab?.componentData || [], componentId),
        }))
      }
      return item
    })
}

function buildUpdateParams(dashboardInfo: any) {
  return {
    id: dashboardInfo.id,
    name: dashboardInfo.name,
    pid: dashboardInfo.pid || 'root',
    datasource: dashboardInfo.datasource,
    node_type: 'leaf',
    type: dashboardInfo.type || 'dashboard',
    opt: 'updateLeaf',
  }
}

async function loadTargetDashboard(dashboardId: string | number) {
  const result: any = await dashboardApi.load_resource({ id: dashboardId, include_data: false })
  return {
    dashboardInfo: result,
    componentData: parseJson(result?.component_data, []),
    canvasStyleData: parseJson(result?.canvas_style_data, {}),
    canvasViewInfo: parseJson(result?.canvas_view_info, {}),
  }
}

async function updateDashboardCanvas(
  dashboardInfo: any,
  componentData: any[],
  canvasStyleData: Record<string, any>,
  canvasViewInfo: Record<string, any>
) {
  await dashboardApi.update_canvas({
    ...buildUpdateParams(dashboardInfo),
    component_data: JSON.stringify(componentData || []),
    canvas_style_data: JSON.stringify(canvasStyleData || {}),
    canvas_view_info: JSON.stringify(canvasViewInfo || {}),
  })
}

async function loadMoveTargets() {
  const datasourceId =
    currentViewInfo.value?.datasource || props.dashboardInfo?.datasource || undefined
  if (!datasourceId) {
    targetDashboardList.value = []
    return
  }
  targetDashboardLoading.value = true
  try {
    const res: any = await dashboardApi.list_resource({ datasource: datasourceId })
    targetDashboardList.value = flattenDashboardOptions(res || [])
  } finally {
    targetDashboardLoading.value = false
  }
}

async function openMoveDialog() {
  if (!canMoveChart.value) {
    ElMessage.warning(t('dashboard.chart_move_no_permission'))
    return
  }
  moveForm.dashboardId = ''
  moveDialogVisible.value = true
  await loadMoveTargets()
}

function closeMoveDialog() {
  if (moveLoading.value) return
  moveDialogVisible.value = false
  moveForm.dashboardId = ''
}

async function moveChartToDashboard() {
  if (moveLoading.value) return
  const valid = await moveFormRef.value?.validate?.().catch(() => false)
  if (!valid) return
  moveLoading.value = true
  let targetSnapshot: any = null
  try {
    const target = await loadTargetDashboard(moveForm.dashboardId)
    targetSnapshot = cloneDeep(target)
    const { nextComponentId, componentPayload, viewPayload } = prepareMovedChartPayload()
    componentPayload.y = maxDashboardBottom(target.componentData)
    target.componentData.push(componentPayload)
    target.canvasViewInfo[nextComponentId] = viewPayload
    await updateDashboardCanvas(
      target.dashboardInfo,
      target.componentData,
      target.canvasStyleData,
      target.canvasViewInfo
    )

    const sourceComponentData = removeComponentById(
      cloneDeep(props.componentData || []),
      props.configItem?.id
    )
    const sourceCanvasViewInfo = cloneDeep(props.canvasViewInfo || {})
    if (props.configItem?.id !== undefined && props.configItem?.id !== null) {
      delete sourceCanvasViewInfo[props.configItem.id]
    }
    await updateDashboardCanvas(
      props.dashboardInfo,
      sourceComponentData,
      cloneDeep(props.canvasStyleData || {}),
      sourceCanvasViewInfo
    )

    ElMessage.success(t('dashboard.chart_move_success'))
    moveDialogVisible.value = false
    emit('chartMoved', { targetDashboardId: moveForm.dashboardId })
  } catch (error) {
    if (targetSnapshot) {
      try {
        await updateDashboardCanvas(
          targetSnapshot.dashboardInfo,
          targetSnapshot.componentData,
          targetSnapshot.canvasStyleData,
          targetSnapshot.canvasViewInfo
        )
      } catch (rollbackError) {
        console.error('rollback moved chart target dashboard failed', rollbackError)
      }
    }
    console.error('move chart failed', error)
    ElMessage.error(t('dashboard.chart_move_failed'))
  } finally {
    moveLoading.value = false
  }
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

function hasChartSnapshot(viewInfo: any) {
  const rows = viewInfo?.data?.data
  return Array.isArray(rows) && rows.length > 0
}

function markChartSnapshotRefreshed(viewInfo: any, refreshedAt = Date.now()) {
  if (!viewInfo || typeof viewInfo !== 'object') {
    return
  }
  if (!viewInfo.data || typeof viewInfo.data !== 'object') {
    viewInfo.data = {}
  }
  viewInfo.snapshotRefreshedAt = refreshedAt
  viewInfo.data.snapshotRefreshedAt = refreshedAt
}

function isDashboardCacheMiss(result: any) {
  return result?.status === 'failed' && result?.error_type === 'dashboard_cache_miss'
}

async function previewChartSql(viewInfo: any, config?: any) {
  const payload = {
    datasource: viewInfo.datasource,
    sql: viewInfo.sql.trim(),
    pivot: viewInfo.pivot?.enabled === true ? viewInfo.pivot : undefined,
  }
  const cachedResult = await dashboardApi.preview_sql(
    {
      ...payload,
      cache_only: true,
    },
    config
  )
  if (!isDashboardCacheMiss(cachedResult)) {
    return cachedResult
  }
  return dashboardApi.preview_sql(payload, config)
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
  let nextIndex = 0
  const runNext = async (): Promise<void> => {
    while (nextIndex < entries.length) {
      const currentIndex = nextIndex
      nextIndex += 1
      const entry = entries[currentIndex]
      const viewInfo = entry?.viewInfo
      if (!viewInfo?.datasource || !viewInfo?.sql?.trim()) {
        failedCount += 1
        continue
      }
      try {
        const previousData = Array.isArray(viewInfo.data?.data) ? [...viewInfo.data.data] : []
        const previousDataFields = Array.isArray(viewInfo.data?.fields) ? [...viewInfo.data.fields] : []
        const previousFields = Array.isArray(viewInfo.fields) ? [...viewInfo.fields] : []
        const hasPreviousSnapshot = hasChartSnapshot(viewInfo)
        const result = await previewChartSql(viewInfo)
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
          if (hasPreviousSnapshot) {
            viewInfo.data.fields = previousDataFields
            viewInfo.data.data = previousData
            viewInfo.fields = previousFields
            viewInfo.status = 'success'
          }
          failedCount += 1
        } else {
          markChartSnapshotRefreshed(viewInfo)
          successCount += 1
        }
        emitter.emit(`view-render-${viewInfo.id || entry?.component?.id}`)
      } catch (error: any) {
        viewInfo.message = error?.message || t('dashboard.chart_refresh_failed')
        if (hasChartSnapshot(viewInfo)) {
          viewInfo.status = 'success'
        } else {
          viewInfo.status = 'failed'
        }
        failedCount += 1
      }
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(CHART_REFRESH_CONCURRENCY, entries.length) }, () => runNext())
  )
  if (successCount > 0 && failedCount === 0) {
    ElMessage.success(t('dashboard.chart_refresh_success'))
  } else if (successCount > 0) {
    ElMessage.warning(`${t('dashboard.chart_refresh_success')} (${successCount}/${entries.length})`)
  } else {
    ElMessage.error(t('dashboard.chart_refresh_failed'))
  }
}

function openChartFullscreen() {
  if (!isPreviewSingleChart.value) {
    return
  }
  chartFullscreenVisible.value = true
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
          :readonly-template="readonlyTemplate"
          v-bind="componentExtraProps"
        />
      </div>
    </div>
    <div v-if="isPreviewReportTarget && !readonlyTemplate" class="preview-chart-actions" @click.stop @mousedown.stop>
      <el-button
        v-if="canShowReportInterpret"
        class="preview-action-btn"
        text
        :title="t('dashboard.chart_report_interpret')"
        :aria-label="t('dashboard.chart_report_interpret')"
        @click.stop="toggleReportPrompt($event)"
      >
        <el-icon size="16"><ChatLineSquare /></el-icon>
      </el-button>
      <el-tooltip
        v-if="canToggleChartLabel"
        effect="dark"
        :content="chartShowLabel ? t('chat.hide_label') : t('chat.show_label')"
        placement="top"
      >
        <el-button
          class="preview-action-btn"
          :class="{ 'is-active': chartShowLabel }"
          text
          :aria-label="chartShowLabel ? t('chat.hide_label') : t('chat.show_label')"
          @click="chartShowLabel = !chartShowLabel"
        >
          <el-icon size="16"><PriceTag /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip effect="dark" :content="t('dashboard.chart_refresh_data')" placement="top">
        <el-button class="preview-action-btn" text @click="refreshChartData">
          <el-icon size="16"><RefreshRight /></el-icon>
        </el-button>
      </el-tooltip>
      <el-tooltip
        v-if="isPreviewSingleChart"
        effect="dark"
        :content="t('dashboard.chart_fullscreen')"
        placement="top"
      >
        <el-button class="preview-action-btn" text @click="openChartFullscreen">
          <el-icon size="16"><FullScreen /></el-icon>
        </el-button>
      </el-tooltip>
      <el-dropdown trigger="click" placement="bottom-end" popper-class="preview-action-more-popper">
        <el-button
          class="preview-action-btn"
          text
          :title="t('dashboard.chart_more_actions')"
          :aria-label="t('dashboard.chart_more_actions')"
          @click.stop
        >
          <el-icon size="16"><MoreFilled /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="exportChartTableData">
              <el-icon size="15"><Download /></el-icon>
              <span>{{ t('dashboard.chart_export_table') }}</span>
            </el-dropdown-item>
            <el-dropdown-item v-if="canMoveChart" @click="openMoveDialog">
              <el-icon size="15"><Position /></el-icon>
              <span>{{ t('dashboard.chart_move_to') }}</span>
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <ChartFullscreenDialog
      v-if="isPreviewSingleChart"
      v-model="chartFullscreenVisible"
      :view-info="currentViewInfo"
      :show-label="chartShowLabel"
    />
    <el-dialog
      v-model="moveDialogVisible"
      class="chart-move-dialog"
      :title="t('dashboard.chart_move_to')"
      width="420px"
      append-to-body
      :before-close="closeMoveDialog"
    >
      <el-form
        ref="moveFormRef"
        v-loading="targetDashboardLoading"
        :model="moveForm"
        :rules="moveFormRules"
        label-position="top"
        @submit.prevent
      >
        <el-form-item :label="t('dashboard.dashboard')" prop="dashboardId" required>
          <el-select
            v-model="moveForm.dashboardId"
            class="chart-move-select"
            filterable
            :placeholder="t('dashboard.select_dashboard')"
            :empty-text="t('dashboard.chart_move_no_target')"
          >
            <el-option
              v-for="item in targetDashboardList"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            >
              <span class="chart-move-option" :style="{ paddingLeft: `${item.level * 14}px` }">
                {{ item.name }}
              </span>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button :disabled="moveLoading" @click="closeMoveDialog">
          {{ t('common.cancel') }}
        </el-button>
        <el-button
          type="primary"
          :loading="moveLoading"
          :disabled="!targetDashboardList.length"
          @click="moveChartToDashboard"
        >
          {{ t('common.confirm') }}
        </el-button>
      </template>
    </el-dialog>
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

  &.is-active {
    color: #2f6bff;
    background: rgba(47, 107, 255, 0.12);
  }
}

.chart-move-select {
  width: 100%;
}

.chart-move-option {
  display: inline-flex;
  align-items: center;
  max-width: 320px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

</style>
