<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus-secondary'
import { useRoiDashboardStore } from '@/stores/roiDashboard'
import { roiCustomErrorRequestConfig, roiDashboardApi } from '@/api/roiDashboard'
import type { ChartTypes } from '@/views/chat/component/BaseChart'
import type { RoiChart, RoiChartPreviewResponse, RoiChartUpdate } from './types'
import {
  createEmptyRoiChartForm,
  createRoiEditorRequestGuard,
  getRoiChartSaveErrorMessage,
  replaceRoiChartForm,
  roiChartFormSignature,
  serializeRoiChartForm,
  type RoiChartForm,
} from './roiChartConfig'
import {
  createRoiChartPreviewRunner,
  ROI_CHART_PREVIEW_ERROR_MESSAGE,
} from './roiChartPreviewRunner'

const props = defineProps<{
  modelValue: boolean
  dashboardId: string
  chart: RoiChart | null
  canEdit: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: [chart: RoiChart]
  cancelled: []
}>()

const roiDashboardStore = useRoiDashboardStore()
const { config } = storeToRefs(roiDashboardStore)
const form = reactive<RoiChartForm>(createEmptyRoiChartForm())
const activeTab = ref('config')
const previewing = ref(false)
const saving = ref(false)
const preview = reactive<RoiChartPreviewResponse>({
  status: '',
  fields: [],
  data: [],
  message: '',
})
const requestGuard = createRoiEditorRequestGuard()
const previewRunner = createRoiChartPreviewRunner({
  guard: requestGuard,
  request: (payload: ReturnType<typeof previewPayload>) =>
    roiDashboardApi.previewChart(props.dashboardId, payload, roiCustomErrorRequestConfig),
  getCurrentSignature: () => currentSignature.value,
  onSuccess: (result) => {
    preview.status = result.status
    preview.fields = [...result.fields]
    preview.data = [...result.data]
    preview.message = ''
  },
  onError: () => {
    resetPreview()
    preview.status = 'failed'
    preview.message = ROI_CHART_PREVIEW_ERROR_MESSAGE
    ElMessage.error(ROI_CHART_PREVIEW_ERROR_MESSAGE)
  },
  onLoading: (value) => {
    previewing.value = value
  },
})

const chartTypes: Array<{ label: string; value: ChartTypes }> = [
  { label: '表格', value: 'table' },
  { label: '指标', value: 'metric' },
  { label: '柱状图', value: 'column' },
  { label: '条形图', value: 'bar' },
  { label: '折线图', value: 'line' },
  { label: '面积图', value: 'area' },
  { label: '饼图', value: 'pie' },
  { label: '漏斗图', value: 'funnel' },
  { label: '热力图', value: 'heatmap' },
  { label: '散点图', value: 'scatter' },
  { label: '桑基图', value: 'sankey' },
  { label: '矩形树图', value: 'treemap' },
]
const insightComparisonOptions = [
  { label: '变化量', value: 'change' },
  { label: '变化率', value: 'changeRate' },
]
const insightAggregateOptions = [
  { label: '合计', value: 'sum' },
  { label: '平均值', value: 'avg' },
  { label: '最大值', value: 'max' },
  { label: '最小值', value: 'min' },
]

const isEdit = computed(() => Boolean(props.chart))
const currentSignature = computed(() => roiChartFormSignature(form))
const canSave = computed(
  () =>
    props.canEdit &&
    !previewing.value &&
    !saving.value &&
    requestGuard.canSave(currentSignature.value)
)

function resetPreview() {
  preview.status = ''
  preview.fields = []
  preview.data = []
  preview.message = ''
}

function ensureConfigSections() {
  form.pivot.metric_fields ||= []
  form.pivot.time_field ||= ''
  form.pivot.group_field ||= ''
  form.pivot.granularity ||= 'day'
  form.insight.comparison ||= { enabled: true, metrics: ['change', 'changeRate'] }
  form.insight.aggregate ||= { enabled: true, metrics: ['sum', 'avg'] }
}

function openSession() {
  previewRunner.invalidate()
  replaceRoiChartForm(form, props.chart)
  ensureConfigSections()
  activeTab.value = 'config'
  previewing.value = false
  saving.value = false
  resetPreview()
  requestGuard.beginSession()
}

function closeSession(cancelled: boolean) {
  previewRunner.invalidate()
  requestGuard.closeSession()
  previewing.value = false
  saving.value = false
  resetPreview()
  emit('update:modelValue', false)
  if (cancelled) emit('cancelled')
}

function requestClose(done?: () => void) {
  closeSession(true)
  done?.()
}

function previewPayload() {
  const payload = serializeRoiChartForm(form)
  const { version: _version, ...request } = payload as RoiChartUpdate
  void _version
  return request
}

async function runPreview() {
  if (!props.canEdit || saving.value) return
  if (!form.title.trim() || !form.sql.trim()) {
    ElMessage.warning('请填写图表标题和 SQL')
    return
  }
  const signature = currentSignature.value
  resetPreview()
  await previewRunner.run(previewPayload(), signature)
}

async function saveChart() {
  if (!props.canEdit || previewing.value || saving.value) return
  const signature = currentSignature.value
  const saveToken = requestGuard.beginSave(signature)
  if (!saveToken || !requestGuard.canSave(signature)) return
  saving.value = true
  try {
    const payload = serializeRoiChartForm(form)
    const saved = isEdit.value
      ? await roiDashboardApi.updateChart(
          props.dashboardId,
          String(props.chart?.id),
          payload as RoiChartUpdate,
          roiCustomErrorRequestConfig
        )
      : await roiDashboardApi.createChart(props.dashboardId, payload, roiCustomErrorRequestConfig)
    if (
      !props.canEdit ||
      signature !== currentSignature.value ||
      !requestGuard.markSaved(saveToken)
    )
      return
    emit('saved', saved)
    closeSession(false)
  } catch (error) {
    if (requestGuard.isCurrentSession(saveToken)) {
      requestGuard.markSaveFailed(saveToken)
      ElMessage.error(getRoiChartSaveErrorMessage(error))
    }
  } finally {
    if (requestGuard.isCurrentSession(saveToken)) saving.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) openSession()
    else {
      previewRunner.invalidate()
      requestGuard.closeSession()
    }
  },
  { immediate: true }
)

watch(
  () => [props.dashboardId, props.chart?.id, props.chart?.version],
  () => {
    if (props.modelValue) openSession()
  }
)

watch(
  form,
  () => {
    previewRunner.invalidate()
  },
  { deep: true }
)

watch(
  () => props.canEdit,
  (allowed) => {
    if (!allowed) {
      previewRunner.invalidate()
      requestGuard.invalidateRequests()
      previewing.value = false
      saving.value = false
    }
  }
)
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="isEdit ? '编辑 ROI 图表' : '添加 ROI 图表'"
    size="min(760px, 96vw)"
    destroy-on-close
    :close-on-click-modal="false"
    :before-close="requestClose"
  >
    <div class="roi-sql-editor">
      <div class="roi-sql-editor__topline">
        <el-input
          v-model="form.title"
          maxlength="120"
          placeholder="图表标题"
          :disabled="!canEdit || saving"
        />
        <el-input :model-value="config?.datasource_name || ''" placeholder="数据源" disabled />
      </div>

      <el-tabs v-model="activeTab" class="roi-sql-editor__tabs">
        <el-tab-pane label="图表配置" name="config">
          <el-form label-position="top" class="roi-sql-editor__form">
            <div class="roi-sql-editor__grid">
              <el-form-item label="图表类型">
                <el-select v-model="form.chartType" :disabled="!canEdit || saving">
                  <el-option
                    v-for="item in chartTypes"
                    :key="item.value"
                    :label="item.label"
                    :value="item.value"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="宽度">
                <el-radio-group v-model="form.layoutSpan" :disabled="!canEdit || saving">
                  <el-radio-button value="full">整行</el-radio-button>
                  <el-radio-button value="half">半行</el-radio-button>
                  <el-radio-button value="third">三分之一</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="X 轴字段">
                <el-select v-model="form.x" clearable filterable :disabled="!canEdit || saving">
                  <el-option
                    v-for="field in preview.fields"
                    :key="field"
                    :label="field"
                    :value="field"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="系列字段">
                <el-select
                  v-model="form.series"
                  clearable
                  filterable
                  :disabled="!canEdit || saving"
                >
                  <el-option
                    v-for="field in preview.fields"
                    :key="field"
                    :label="field"
                    :value="field"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="Y 轴字段" class="is-wide">
                <el-select
                  v-model="form.y"
                  multiple
                  filterable
                  collapse-tags
                  :disabled="!canEdit || saving"
                >
                  <el-option
                    v-for="field in preview.fields"
                    :key="field"
                    :label="field"
                    :value="field"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="表格列" class="is-wide">
                <el-select
                  v-model="form.columns"
                  multiple
                  filterable
                  collapse-tags
                  :disabled="!canEdit || saving"
                >
                  <el-option
                    v-for="field in preview.fields"
                    :key="field"
                    :label="field"
                    :value="field"
                  />
                </el-select>
              </el-form-item>
            </div>

            <div class="roi-sql-editor__section">
              <el-switch v-model="form.pivotEnabled" :disabled="!canEdit || saving" />
              <span>透视</span>
              <div v-if="form.pivotEnabled" class="roi-sql-editor__grid is-nested">
                <el-form-item label="时间字段">
                  <el-select
                    v-model="form.pivot.time_field"
                    clearable
                    filterable
                    :disabled="!canEdit || saving"
                  >
                    <el-option
                      v-for="field in preview.fields"
                      :key="field"
                      :label="field"
                      :value="field"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="分组字段">
                  <el-select
                    v-model="form.pivot.group_field"
                    clearable
                    filterable
                    :disabled="!canEdit || saving"
                  >
                    <el-option
                      v-for="field in preview.fields"
                      :key="field"
                      :label="field"
                      :value="field"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="指标字段" class="is-wide">
                  <el-select
                    v-model="form.pivot.metric_fields"
                    multiple
                    filterable
                    collapse-tags
                    :disabled="!canEdit || saving"
                  >
                    <el-option
                      v-for="field in preview.fields"
                      :key="field"
                      :label="field"
                      :value="field"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="启用分组">
                  <el-switch
                    v-model="form.pivot.group_enabled"
                    :disabled="!canEdit || saving || !form.pivot.group_field"
                  />
                </el-form-item>
                <el-form-item label="时间粒度">
                  <el-select v-model="form.pivot.granularity" :disabled="!canEdit || saving">
                    <el-option label="按天" value="day" />
                    <el-option label="按周" value="week" />
                    <el-option label="按月" value="month" />
                  </el-select>
                </el-form-item>
              </div>
            </div>

            <div class="roi-sql-editor__section">
              <el-switch v-model="form.insightEnabled" :disabled="!canEdit || saving" />
              <span>洞察</span>
              <div v-if="form.insightEnabled" class="roi-sql-editor__grid is-nested">
                <el-form-item label="对比指标">
                  <el-switch
                    v-model="form.insight.comparison.enabled"
                    :disabled="!canEdit || saving"
                  />
                  <el-select
                    v-model="form.insight.comparison.metrics"
                    multiple
                    :disabled="!canEdit || saving || !form.insight.comparison.enabled"
                  >
                    <el-option
                      v-for="item in insightComparisonOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
                <el-form-item label="汇总指标">
                  <el-switch
                    v-model="form.insight.aggregate.enabled"
                    :disabled="!canEdit || saving"
                  />
                  <el-select
                    v-model="form.insight.aggregate.metrics"
                    multiple
                    :disabled="!canEdit || saving || !form.insight.aggregate.enabled"
                  >
                    <el-option
                      v-for="item in insightAggregateOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                    />
                  </el-select>
                </el-form-item>
              </div>
            </div>
          </el-form>
        </el-tab-pane>

        <el-tab-pane label="SQL 明细" name="sql">
          <el-input
            v-model="form.sql"
            type="textarea"
            :rows="14"
            resize="vertical"
            spellcheck="false"
            placeholder="SELECT ..."
            :disabled="!canEdit || saving"
            class="roi-sql-editor__sql"
          />
          <el-table
            v-if="preview.status === 'success'"
            :data="preview.data"
            height="240"
            class="roi-sql-editor__preview"
          >
            <el-table-column
              v-for="field in preview.fields"
              :key="field"
              :prop="field"
              :label="field"
              min-width="120"
              show-overflow-tooltip
            />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <template #footer>
      <div class="roi-sql-editor__footer">
        <el-button @click="requestClose()">取消</el-button>
        <el-button :disabled="!canEdit || saving" @click="runPreview">
          {{ previewing ? '重新预览' : '预览' }}
        </el-button>
        <el-button type="primary" :loading="saving" :disabled="!canSave" @click="saveChart"
          >保存</el-button
        >
      </div>
    </template>
  </el-drawer>
</template>

<style scoped lang="less">
.roi-sql-editor {
  min-width: 0;
}

.roi-sql-editor__topline,
.roi-sql-editor__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.roi-sql-editor__topline {
  margin-bottom: 10px;
}

.roi-sql-editor__tabs,
.roi-sql-editor__form,
.roi-sql-editor__grid > *,
.roi-sql-editor__topline > * {
  min-width: 0;
}

.roi-sql-editor__grid :deep(.el-form-item__content),
.roi-sql-editor__grid :deep(.el-select) {
  width: 100%;
  min-width: 0;
}

.roi-sql-editor__grid .is-wide {
  grid-column: 1 / -1;
}

.roi-sql-editor__section {
  padding: 12px 0;
  border-top: 1px solid var(--ed-border-color-lighter);

  > span {
    margin-left: 8px;
    color: var(--ed-text-color-primary);
    font-size: 14px;
  }
}

.roi-sql-editor__grid.is-nested {
  margin-top: 10px;
}

.roi-sql-editor__sql :deep(textarea) {
  font-family: Consolas, 'Courier New', monospace;
  line-height: 1.55;
}

.roi-sql-editor__preview {
  width: 100%;
  margin-top: 12px;
}

.roi-sql-editor__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 640px) {
  .roi-sql-editor__topline,
  .roi-sql-editor__grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .roi-sql-editor__grid .is-wide {
    grid-column: auto;
  }
}
</style>
