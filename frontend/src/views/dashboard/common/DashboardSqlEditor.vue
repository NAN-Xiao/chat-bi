<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { dashboardApi } from '@/api/dashboard.ts'
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import type { ChartAxis, ChartTypes } from '@/views/chat/component/BaseChart.ts'

const props = withDefaults(
  defineProps<{
    modelValue: boolean
    viewInfo?: any
  }>(),
  {
    modelValue: false,
    viewInfo: null,
  }
)

const emits = defineEmits(['update:modelValue', 'applied'])
const { t } = useI18n()

const visible = computed({
  get() {
    return props.modelValue
  },
  set(value: boolean) {
    emits('update:modelValue', value)
  },
})

const form = reactive({
  sql: '',
  title: '',
  chartType: 'table' as ChartTypes,
  columns: [] as string[],
  x: '',
  y: [] as string[],
  series: '',
  multiQuotaName: '',
})

const preview = reactive({
  fields: [] as string[],
  data: [] as Array<Record<string, any>>,
  status: 'success',
  message: '',
})

const loading = ref(false)
const previewVersion = ref(0)
const lastPreviewSql = ref('')

const chartTypes: Array<{ label: string; value: ChartTypes }> = [
  { label: 'table', value: 'table' },
  { label: 'metric', value: 'metric' },
  { label: 'column', value: 'column' },
  { label: 'bar', value: 'bar' },
  { label: 'line', value: 'line' },
  { label: 'pie', value: 'pie' },
  { label: 'funnel', value: 'funnel' },
  { label: 'heatmap', value: 'heatmap' },
  { label: 'scatter', value: 'scatter' },
  { label: 'sankey', value: 'sankey' },
  { label: 'treemap', value: 'treemap' },
]

const fieldOptions = computed(() => preview.fields.map((field) => ({ label: field, value: field })))
const hasPreviewData = computed(() => preview.status !== 'failed' && preview.data.length > 0)
const sqlChangedAfterPreview = computed(() => form.sql.trim() !== lastPreviewSql.value.trim())
const previewTableFields = computed(() => {
  if (form.columns.length > 0) {
    return form.columns.slice(0, 10)
  }
  return preview.fields.slice(0, 10)
})
const chartPreviewId = computed(() => `dashboard-sql-preview-${props.viewInfo?.id || 'new'}-${previewVersion.value}`)
const showXAxis = computed(() => !['table', 'metric', 'pie'].includes(form.chartType))
const showSeries = computed(() => !['table', 'metric', 'funnel', 'scatter'].includes(form.chartType))

function unique(values: Array<string | undefined | null>) {
  return Array.from(new Set(values.filter((value) => value !== undefined && value !== null && `${value}`.trim() !== '').map((value) => `${value}`)))
}

function toAxis(field: string): ChartAxis {
  return { name: field, value: field }
}

function toAxes(fields: string[]): ChartAxis[] {
  return unique(fields).map(toAxis)
}

function axisValues(axis?: Array<{ value?: string }>) {
  return (axis || []).map((item) => item.value).filter(Boolean) as string[]
}

function collectFields(viewInfo: any) {
  const fields: string[] = []
  const dataObj = viewInfo?.data || {}
  fields.push(...(Array.isArray(dataObj.fields) ? dataObj.fields : []))
  ;(dataObj.data || []).slice(0, 20).forEach((row: Record<string, any>) => {
    fields.push(...Object.keys(row || {}))
  })
  const chart = viewInfo?.chart || {}
  fields.push(...axisValues(chart.columns))
  fields.push(...axisValues(chart.xAxis))
  fields.push(...axisValues(chart.yAxis))
  fields.push(...axisValues(chart.series))
  return unique(fields)
}

function resetFieldSelections() {
  const fields = preview.fields
  if (!fields.length) {
    form.columns = []
    form.x = ''
    form.y = []
    form.series = ''
    return
  }
  form.columns = form.columns.filter((field) => fields.includes(field))
  form.y = form.y.filter((field) => fields.includes(field))
  if (form.columns.length === 0) form.columns = fields.slice(0, 8)
  if (!fields.includes(form.x)) form.x = fields[0] || ''
  if (!fields.includes(form.series)) form.series = ''
  if (form.y.length === 0) {
    const numericField = fields.find((field) =>
      preview.data.some((row) => typeof row?.[field] === 'number')
    )
    form.y = [numericField || fields[Math.min(1, fields.length - 1)] || fields[0]]
  }
}

function initEditor() {
  const viewInfo = props.viewInfo || {}
  const chart = viewInfo.chart || {}
  const fields = collectFields(viewInfo)
  form.sql = viewInfo.sql || ''
  form.title = chart.title || ''
  form.chartType = chart.sourceType || chart.type || 'table'
  form.columns = axisValues(chart.columns)
  form.x = axisValues(chart.xAxis)[0] || ''
  form.y = axisValues(chart.yAxis)
  form.series = axisValues(chart.series)[0] || ''
  form.multiQuotaName = chart.multiQuotaName || t('dashboard.metric_type')
  preview.fields = fields
  preview.data = viewInfo.data?.data || []
  preview.status = viewInfo.status || 'success'
  preview.message = viewInfo.message || ''
  lastPreviewSql.value = form.sql.trim()
  resetFieldSelections()
  previewVersion.value += 1
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      initEditor()
    }
  }
)

watch(
  () => [
    form.chartType,
    form.columns.join('|'),
    form.x,
    form.y.join('|'),
    form.series,
    form.multiQuotaName,
  ],
  () => {
    previewVersion.value += 1
  }
)

async function runPreview() {
  if (!props.viewInfo?.datasource) {
    ElMessage.warning(t('dashboard.sql_editor_no_datasource'))
    return
  }
  if (!form.sql.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return
  }
  loading.value = true
  try {
    const result = await dashboardApi.preview_sql({
      datasource: props.viewInfo.datasource,
      sql: form.sql.trim(),
    })
    preview.status = result?.status || 'success'
    preview.message = result?.message || ''
    preview.data = result?.data || []
    preview.fields = unique([
      ...(Array.isArray(result?.fields) ? result.fields : []),
      ...((result?.data || [])[0] ? Object.keys((result?.data || [])[0]) : []),
    ])
    lastPreviewSql.value = form.sql.trim()
    resetFieldSelections()
    previewVersion.value += 1
    if (preview.status === 'failed') {
      ElMessage.error(preview.message || t('dashboard.sql_editor_preview_failed'))
    } else {
      ElMessage.success(t('dashboard.sql_editor_preview_success'))
      await nextTick()
    }
  } finally {
    loading.value = false
  }
}

function buildChart() {
  const sourceChart = props.viewInfo?.chart || {}
  const chart: any = {
    ...sourceChart,
    type: form.chartType,
    sourceType: form.chartType,
    title: form.title || sourceChart.title || t('dashboard.view'),
    columns: [],
    xAxis: [],
    yAxis: [],
    series: [],
    multiQuotaName: undefined,
  }

  if (form.chartType === 'table') {
    chart.columns = toAxes(form.columns.length ? form.columns : preview.fields)
    return chart
  }

  if (form.chartType === 'metric') {
    chart.yAxis = toAxes(form.y)
    return chart
  }

  if (form.chartType === 'pie') {
    chart.yAxis = toAxes(form.y.slice(0, 1))
    chart.series = toAxes([form.series || form.x].filter(Boolean) as string[])
    return chart
  }

  chart.xAxis = toAxes([form.x].filter(Boolean) as string[])
  chart.yAxis = toAxes(form.series ? form.y.slice(0, 1) : form.y)
  chart.series = toAxes([form.series].filter(Boolean) as string[])
  if (chart.yAxis.length > 1 && chart.series.length === 0) {
    chart.multiQuotaName = form.multiQuotaName || t('dashboard.metric_type')
  }
  return chart
}

function validateBeforeApply() {
  if (!form.sql.trim()) {
    ElMessage.warning(t('dashboard.sql_editor_empty_sql'))
    return false
  }
  if (sqlChangedAfterPreview.value) {
    ElMessage.warning(t('dashboard.sql_editor_need_preview'))
    return false
  }
  if (preview.status === 'failed') {
    ElMessage.warning(preview.message || t('dashboard.sql_editor_preview_failed'))
    return false
  }
  if (form.chartType === 'table') {
    return true
  }
  if (!form.y.length) {
    ElMessage.warning(t('dashboard.sql_editor_select_y'))
    return false
  }
  if (form.chartType === 'metric') {
    return true
  }
  if (form.chartType === 'pie' && !(form.series || form.x)) {
    ElMessage.warning(t('dashboard.sql_editor_select_series'))
    return false
  }
  if (form.chartType !== 'pie' && !form.x) {
    ElMessage.warning(t('dashboard.sql_editor_select_x'))
    return false
  }
  if (['heatmap', 'sankey'].includes(form.chartType) && !form.series) {
    ElMessage.warning(t('dashboard.sql_editor_select_series'))
    return false
  }
  return true
}

function applyChange() {
  if (!props.viewInfo || !validateBeforeApply()) return
  props.viewInfo.sql = form.sql.trim()
  props.viewInfo.data = {
    ...(props.viewInfo.data || {}),
    fields: [...preview.fields],
    data: [...preview.data],
  }
  props.viewInfo.status = preview.status
  props.viewInfo.message = preview.message
  props.viewInfo.chart = buildChart()
  previewVersion.value += 1
  emits('applied', props.viewInfo)
  visible.value = false
  ElMessage.success(t('dashboard.sql_editor_applied'))
}

function closeDrawer() {
  visible.value = false
}
</script>

<template>
  <el-drawer
    v-model="visible"
    class="dashboard-sql-editor"
    direction="rtl"
    size="720px"
    :title="t('dashboard.sql_editor_title')"
    append-to-body
    :destroy-on-close="true"
  >
    <div v-loading="loading" class="sql-editor-body">
      <el-form label-position="top">
        <el-form-item :label="t('dashboard.sql_editor_sql')">
          <el-input
            v-model="form.sql"
            type="textarea"
            :autosize="{ minRows: 8, maxRows: 16 }"
            spellcheck="false"
            @keydown.stop
            @keyup.stop
          />
        </el-form-item>
        <div class="action-row">
          <el-button type="primary" @click="runPreview">{{ t('dashboard.sql_editor_run_preview') }}</el-button>
          <span v-if="sqlChangedAfterPreview" class="muted">{{ t('dashboard.sql_editor_changed') }}</span>
        </div>
        <el-alert
          v-if="preview.status === 'failed' && preview.message"
          class="editor-alert"
          type="error"
          :title="preview.message"
          :closable="false"
        />
        <div class="config-grid">
          <el-form-item :label="t('dashboard.sql_editor_chart_title')">
            <el-input v-model="form.title" @keydown.stop @keyup.stop />
          </el-form-item>
          <el-form-item :label="t('dashboard.sql_editor_chart_type')">
            <el-select v-model="form.chartType">
              <el-option
                v-for="item in chartTypes"
                :key="item.value"
                :label="t(`chat.chart_type.${item.label}`)"
                :value="item.value"
              />
            </el-select>
          </el-form-item>
        </div>
        <el-form-item v-if="form.chartType === 'table'" :label="t('dashboard.sql_editor_columns')">
          <el-select v-model="form.columns" multiple filterable>
            <el-option
              v-for="field in fieldOptions"
              :key="field.value"
              :label="field.label"
              :value="field.value"
            />
          </el-select>
        </el-form-item>
        <div v-else class="config-grid">
          <el-form-item v-if="showXAxis" :label="t('dashboard.sql_editor_x')">
            <el-select v-model="form.x" filterable clearable>
              <el-option
                v-for="field in fieldOptions"
                :key="field.value"
                :label="field.label"
                :value="field.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('dashboard.sql_editor_y')">
            <el-select v-model="form.y" multiple filterable>
              <el-option
                v-for="field in fieldOptions"
                :key="field.value"
                :label="field.label"
                :value="field.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item v-if="showSeries" :label="t('dashboard.sql_editor_series')">
            <el-select v-model="form.series" filterable clearable>
              <el-option
                v-for="field in fieldOptions"
                :key="field.value"
                :label="field.label"
                :value="field.value"
              />
            </el-select>
          </el-form-item>
          <el-form-item
            v-if="form.y.length > 1 && !form.series && ['column', 'bar', 'line'].includes(form.chartType)"
            :label="t('dashboard.sql_editor_metric_group')"
          >
            <el-input v-model="form.multiQuotaName" @keydown.stop @keyup.stop />
          </el-form-item>
        </div>
      </el-form>

      <div class="preview-title">{{ t('dashboard.sql_editor_chart_preview') }}</div>
      <div class="chart-preview">
        <ChartComponent
          v-if="hasPreviewData"
          :key="chartPreviewId"
          :id="chartPreviewId"
          :type="form.chartType"
          :columns="form.chartType === 'table' ? toAxes(form.columns.length ? form.columns : preview.fields) : []"
          :x="form.chartType !== 'table' && form.chartType !== 'metric' && form.chartType !== 'pie' ? toAxes([form.x]) : []"
          :y="form.chartType === 'table' ? [] : toAxes(form.series ? form.y.slice(0, 1) : form.y)"
          :series="form.chartType === 'pie' ? toAxes([form.series || form.x]) : toAxes([form.series])"
          :data="preview.data"
          :multi-quota-name="form.y.length > 1 && !form.series ? form.multiQuotaName : undefined"
        />
        <div v-else class="empty-preview">{{ t('dashboard.sql_editor_no_preview_data') }}</div>
      </div>

      <div class="preview-title">{{ t('dashboard.sql_editor_data_preview') }}</div>
      <el-table
        v-if="preview.data.length"
        class="data-preview-table"
        :data="preview.data.slice(0, 8)"
        size="small"
        border
      >
        <el-table-column
          v-for="field in previewTableFields"
          :key="field"
          :prop="field"
          :label="field"
          min-width="120"
          show-overflow-tooltip
        />
      </el-table>
      <div v-else class="empty-preview">{{ t('dashboard.sql_editor_no_preview_data') }}</div>
    </div>
    <template #footer>
      <el-button secondary @click="closeDrawer">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" @click="applyChange">{{ t('dashboard.sql_editor_apply') }}</el-button>
    </template>
  </el-drawer>
</template>

<style scoped lang="less">
.sql-editor-body {
  padding-right: 4px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.muted {
  color: #8f959e;
  font-size: 13px;
}

.editor-alert {
  margin-bottom: 16px;
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 16px;
}

.preview-title {
  color: #1f2329;
  font-size: 14px;
  font-weight: 500;
  line-height: 22px;
  margin: 18px 0 8px;
}

.chart-preview {
  height: 300px;
  border: 1px solid #dee0e3;
  border-radius: 6px;
  padding: 12px;
  background: #fff;
}

.empty-preview {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8f959e;
}

.data-preview-table {
  width: 100%;
}
</style>
