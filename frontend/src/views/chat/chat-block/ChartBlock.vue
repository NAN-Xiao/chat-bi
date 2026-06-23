<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'
import DisplayChartBlock from '@/views/chat/component/DisplayChartBlock.vue'
import ChartPopover from '@/views/chat/chat-block/ChartPopover.vue'
import { computed, ref, watch } from 'vue'
import { useClipboard } from '@vueuse/core'
import { concat } from 'lodash-es'
import type { ChartAxis, ChartTypes } from '@/views/chat/component/BaseChart.ts'
import {
  DataAnalysis,
  DataBoard,
  Document,
  Download,
  Fold,
  FullScreen,
  Grid,
  Histogram,
  PieChart,
  PriceTag,
  ScaleToOriginal,
  TrendCharts,
} from '@element-plus/icons-vue'
import icon_file_image_colorful from '@/assets/svg/icon_file-image_colorful.svg'
import icon_file_excel_colorful from '@/assets/svg/icon_file-excel_colorful.svg'
import icon_copy_outlined from '@/assets/svg/icon_copy_outlined.svg'
import { useI18n } from 'vue-i18n'
import SQLComponent from '@/views/chat/component/SQLComponent.vue'
import { useAssistantStore } from '@/stores/assistant'
import AddViewDashboard from '@/views/dashboard/common/AddViewDashboard.vue'
import html2canvas from 'html2canvas'
import { chatApi } from '@/api/chat'
import { useChatConfigStore } from '@/stores/chatConfig.ts'
import { useDatasourceContextStore } from '@/stores/datasourceContext'

const chatConfig = useChatConfigStore()
const showSQLBtn = chatConfig.getShowSQL
const props = withDefaults(
  defineProps<{
    recordId?: number
    message: ChatMessage
    isPredict?: boolean
    chatType?: ChartTypes
    enlarge?: boolean
    loadingData?: boolean
  }>(),
  {
    recordId: undefined,
    isPredict: false,
    chatType: undefined,
    enlarge: false,
    loadingData: false,
  }
)

const { copy } = useClipboard({ legacy: true })
const loading = ref<boolean>(false)
const { t } = useI18n()
const addViewRef = ref(null)
const emits = defineEmits(['exitFullScreen'])

const dataObject = computed<{
  status?: string
  error_type?: string
  message?: string
  reason?: string
  fields: Array<string>
  data: Array<{ [key: string]: any }>
  limit: number | undefined
  datasource: number | undefined
  sql: string | undefined
}>(() => {
  if (props.message?.record?.data) {
    if (typeof props.message?.record?.data === 'string') {
      return JSON.parse(props.message.record.data)
    } else {
      return props.message.record.data
    }
  }
  return {}
})
const assistantStore = useAssistantStore()
const datasourceContext = useDatasourceContextStore()
const isCompletePage = computed(() => !assistantStore.getAssistant || assistantStore.getEmbedded)

const isAssistant = computed(() => assistantStore.getAssistant)

const chartId = computed(() => props.message?.record?.id + (props.enlarge ? '-fullscreen' : ''))
const dataPermissionDenied = computed(
  () => dataObject.value?.status === 'failed' && dataObject.value?.error_type === 'permission_denied'
)
const dataFailureMessage = computed(() => dataObject.value?.message || dataObject.value?.reason || '')
const chartDatasourceId = computed(
  () => props.message?.record?.datasource || dataObject.value?.datasource || datasourceContext.datasourceId
)
const canAddToDashboard = computed(() => {
  const datasourceId = chartDatasourceId.value
  if (!datasourceId) return false
  const datasource = datasourceContext.datasources.find(
    (item) => String(item.id) === String(datasourceId)
  )
  if (datasource) return datasource.can_create_dashboard === true
  return (
    String(datasourceContext.datasourceId || '') === String(datasourceId) &&
    datasourceContext.canCreateDashboard === true
  )
})

const data = computed(() => {
  if (props.isPredict) {
    let _list = []
    if (
      props.message?.record?.predict_data &&
      typeof props.message?.record?.predict_data === 'string'
    ) {
      if (
        props.message?.record?.predict_data.length > 0 &&
        props.message?.record?.predict_data.trim().startsWith('[') &&
        props.message?.record?.predict_data.trim().endsWith(']')
      ) {
        try {
          _list = JSON.parse(props.message?.record?.predict_data)
        } catch (e) {
          console.error(e)
        }
      }
    } else {
      if (props.message?.record?.predict_data?.length > 0) {
        _list = props.message?.record?.predict_data
      }
    }
    if (_list.length == 0) {
      return _list
    }

    if (dataObject.value.data && dataObject.value.data?.length > 0) {
      return concat(dataObject.value.data, _list)
    }
    return _list
  } else {
    return dataObject.value.data
  }
})

const chartRef = ref()

const chartObject = computed<{
  type: ChartTypes
  title: string
  axis: {
    x: ChartAxis
    y: ChartAxis | ChartAxis[]
    series: ChartAxis
  }
  columns: Array<ChartAxis>
}>(() => {
  if (props.message?.record?.chart) {
    return JSON.parse(props.message.record.chart)
  }
  return {}
})

const currentChartType = ref<ChartTypes | undefined>(
  props.chatType ?? chartObject.value.type ?? 'table'
)

const chartType = computed<ChartTypes>({
  get() {
    if (currentChartType.value) {
      return currentChartType.value
    }
    return props.chatType ?? chartObject.value.type ?? 'table'
  },
  set(v) {
    currentChartType.value = v
  },
})

const isTableChart = computed(() => chartType.value === 'table')
const chatTableBlockHeight = computed(() => {
  const rowCount = Math.max(data.value?.length || 0, 1)
  const tableContentHeight = 32 + rowCount * 30
  const displayBlockPadding = 18
  const chartBlockPadding = 30
  const minHeight = 248
  const maxHeight = 356

  return Math.min(
    maxHeight,
    Math.max(minHeight, tableContentHeight + displayBlockPadding + chartBlockPadding)
  )
})
const chartBlockStyle = computed(() => {
  if (props.enlarge) {
    return undefined
  }
  if (!isTableChart.value) {
    return {
      height: '430px',
    }
  }
  return {
    height: `${chatTableBlockHeight.value}px`,
  }
})

const chartTypeList = computed(() => {
  const _list = []
  const pushChartType = (value: ChartTypes, icon: any) => {
    _list.push({
      value,
      name: t(`chat.chart_type.${value}`),
      icon,
    })
  }
  if (chartObject.value) {
    switch (chartObject.value.type) {
      case 'table':
        break
      case 'column':
      case 'bar':
      case 'line':
        _list.push({
          value: 'column',
          name: t('chat.chart_type.column'),
          icon: Histogram,
        })
        _list.push({
          value: 'bar',
          name: t('chat.chart_type.bar'),
          icon: DataAnalysis,
        })
        _list.push({
          value: 'line',
          name: t('chat.chart_type.line'),
          icon: TrendCharts,
        })
        break
      case 'pie':
        pushChartType('pie', PieChart)
        break
      case 'metric':
        pushChartType('metric', DataBoard)
        break
      case 'funnel':
        pushChartType('funnel', DataAnalysis)
        break
      case 'heatmap':
        pushChartType('heatmap', Grid)
        break
      case 'scatter':
        pushChartType('scatter', TrendCharts)
        break
      case 'sankey':
        pushChartType('sankey', DataAnalysis)
        break
      case 'treemap':
        pushChartType('treemap', PieChart)
        break
    }
  }

  return _list
})

function changeTable() {
  onTypeChange('table')
}

function onTypeChange(val: any) {
  chartType.value = val
  chartRef.value?.onTypeChange()
}

function reloadChart() {
  chartRef.value?.onTypeChange()
}

const dialogVisible = ref(false)

function setHiddenSidebarBtnZIndex(value: string) {
  const sidebarBtns = document.querySelectorAll('.hidden-sidebar-btn')
  sidebarBtns.forEach((btn) => {
    ;(btn as HTMLElement).style.zIndex = value
  })
}

function openFullScreen() {
  setHiddenSidebarBtnZIndex('0')
  dialogVisible.value = true
}

function closeFullScreen() {
  emits('exitFullScreen')
}

function onExitFullScreen() {
  dialogVisible.value = false
  setHiddenSidebarBtnZIndex('11')
}

const sqlShow = ref(false)

function showSql() {
  sqlShow.value = true
}

const showLabel = ref(false)

function addToDashboard() {
  if (!canAddToDashboard.value) return
  const recordeInfo = {
    id: '1-1',
    data: {
      data: data.value,
    },
    sql: props.message?.record?.sql,
    datasource: chartDatasourceId.value,
    chart: {},
  }
  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  const chartBaseInfo = JSON.parse(props.message?.record?.chart)
  if (chartBaseInfo) {
    let yAxis = []
    const axis = chartBaseInfo?.axis
    if (!axis?.y) {
      yAxis = []
    } else {
      const y = axis.y
      const multiQuotaValues = axis['multi-quota']?.value || []

      // 统一处理为数组
      const yArray = Array.isArray(y) ? [...y] : [{ ...y }]

      // 标记 multi-quota
      yAxis = yArray.map((item) => ({
        ...item,
        'multi-quota': multiQuotaValues.includes(item.value),
      }))
    }

    recordeInfo['chart'] = {
      type: chartBaseInfo?.type,
      title: chartBaseInfo?.title,
      columns: chartBaseInfo?.columns,
      xAxis: axis?.x ? [axis?.x] : [],
      yAxis: yAxis,
      series: axis?.series ? [axis?.series] : [],
    }
  }

  // @ts-expect-error eslint-disable-next-line @typescript-eslint/ban-ts-comment
  addViewRef.value?.optInit(recordeInfo)
}

function copyText() {
  if (props.message?.record?.sql) {
    copy(props.message.record.sql).then(() => {
      ElMessage.success(t('embedded.copy_successful'))
    })
  }
}

const exportRef = ref()

function exportToExcel() {
  if (chartRef.value && props.recordId) {
    loading.value = true
    chatApi
      .export2Excel(props.recordId, props.message?.record?.chat_id || 0)
      .then((res) => {
        const blob = new Blob([res], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = `${chartObject.value.title ?? 'Excel'}.xlsx`
        document.body.appendChild(link)
        link.click()
        document.body.removeChild(link)
      })
      .catch(async (error) => {
        if (error.response) {
          try {
            let text = await error.response.data.text()
            try {
              text = JSON.parse(text)
            } finally {
              ElMessage({
                message: text,
                type: 'error',
                showClose: true,
              })
            }
          } catch (e) {
            console.error('Error processing error response:', e)
          }
        } else {
          console.error('Other error:', error)
          ElMessage({
            message: error,
            type: 'error',
            showClose: true,
          })
        }
      })
      .finally(() => {
        loading.value = false
      })
    exportRef.value?.hide()
  }
}

function exportToImage() {
  const obj = document.getElementById('chart-component-' + chartId.value)
  if (obj) {
    html2canvas(obj).then((canvas) => {
      canvas.toBlob(function (blob) {
        if (blob) {
          const link = document.createElement('a')
          link.download = (chartObject.value.title ?? 'chart') + '.png' // Specify filename
          link.href = URL.createObjectURL(blob)
          document.body.appendChild(link) // Append to body to make it clickable
          link.click() // Programmatically click the link
          document.body.removeChild(link) // Clean up
          URL.revokeObjectURL(link.href) // Release the object URL
        }
      }, 'image/png')
    })
  }
  exportRef.value?.hide()
}

defineExpose({
  reloadChart,
})

watch(
  () => chartObject.value?.type,
  (val) => {
    if (val) {
      currentChartType.value = val
    }
  }
)
</script>

<template>
  <div
    v-if="
      !message.isTyping &&
      ((!isPredict && (message?.record?.sql || message?.record?.chart)) ||
        (isPredict && message?.record?.chart && data.length > 0))
    "
    v-loading.fullscreen.lock="loading"
    class="chart-component-container smart-chart-answer"
    :class="{ 'full-screen': enlarge }"
  >
    <div class="header-bar">
      <div class="title">
        {{ chartObject.title || message.record?.question }}
      </div>
      <div class="buttons-bar">
        <div v-if="!dataPermissionDenied" class="chart-select-container">
          <el-tooltip effect="dark" :offset="8" :content="t('chat.type')" placement="top">
            <ChartPopover
              v-if="chartTypeList.length > 0"
              :chart-type-list="chartTypeList"
              :chart-type="chartType"
              :title="t('chat.type')"
              @type-change="onTypeChange"
            ></ChartPopover>
          </el-tooltip>

          <el-tooltip
            effect="dark"
            :offset="8"
            :content="t('chat.chart_type.table')"
            placement="top"
          >
            <el-button
              class="tool-btn"
              :class="{ 'chart-active': currentChartType === 'table' }"
              text
              @click="changeTable"
            >
              <el-icon size="17">
                <Grid />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>

        <div
          v-if="!dataPermissionDenied && currentChartType !== 'table' && currentChartType !== 'metric'"
          class="chart-select-container"
        >
          <el-tooltip
            effect="dark"
            :offset="8"
            :content="showLabel ? t('chat.hide_label') : t('chat.show_label')"
            placement="top"
          >
            <el-button
              class="tool-btn"
              :class="{ 'chart-active': showLabel }"
              text
              @click="showLabel = !showLabel"
            >
              <el-icon size="17">
                <PriceTag />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>

        <div v-if="message?.record?.sql && showSQLBtn">
          <el-tooltip effect="dark" :offset="8" :content="t('chat.show_sql')" placement="top">
            <el-button class="tool-btn" text @click="showSql">
              <el-icon size="17">
                <Document />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div v-if="message?.record?.chart && !dataPermissionDenied">
          <el-popover
            ref="exportRef"
            trigger="click"
            popper-class="export_to_select"
            placement="bottom"
          >
            <template #reference>
              <div>
                <el-tooltip
                  effect="dark"
                  :offset="8"
                  :content="t('chat.export_to')"
                  placement="top"
                >
                  <el-button class="tool-btn" text>
                    <el-icon size="17">
                      <Download />
                    </el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </template>
            <div class="popover">
              <div class="popover-content">
                <div class="title">{{ t('chat.export_to') }}</div>
                <div class="popover-item" @click="exportToExcel">
                  <el-icon size="16">
                    <icon_file_excel_colorful />
                  </el-icon>
                  <div class="model-name">{{ t('chat.excel') }}</div>
                </div>
                <div
                  v-if="currentChartType !== 'table'"
                  class="popover-item"
                  @click="exportToImage"
                >
                  <el-icon size="16">
                    <icon_file_image_colorful />
                  </el-icon>
                  <div class="model-name">{{ t('chat.picture') }}</div>
                </div>
              </div>
            </div>
          </el-popover>
        </div>
        <div v-if="message?.record?.chart && !isAssistant && !dataPermissionDenied">
          <el-tooltip
            effect="dark"
            :content="
              canAddToDashboard ? t('chat.add_to_dashboard') : t('chat.no_dashboard_create_permission')
            "
            placement="top"
          >
            <el-button
              class="tool-btn"
              text
              :disabled="!canAddToDashboard"
              @click="addToDashboard"
            >
              <el-icon size="17">
                <DataBoard />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div class="divider" />
        <div v-if="!enlarge && !dataPermissionDenied">
          <el-tooltip
            effect="dark"
            :offset="8"
            :content="!isCompletePage ? $t('common.zoom_in') : t('chat.full_screen')"
            placement="top"
          >
            <el-button class="tool-btn" text @click="openFullScreen">
              <el-icon size="17">
                <FullScreen v-if="isCompletePage" />
                <ScaleToOriginal v-else />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <div v-else-if="!dataPermissionDenied">
          <el-tooltip
            effect="dark"
            :offset="8"
            :content="!isCompletePage ? $t('common.zoom_out') : t('chat.exit_full_screen')"
            placement="top"
          >
            <el-button class="tool-btn" text @click="closeFullScreen">
              <el-icon size="17">
                <Fold />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </div>
    </div>

    <div v-if="dataPermissionDenied" class="data-permission-warning">
      {{ dataFailureMessage }}
    </div>

    <template v-else-if="message?.record?.chart">
      <div class="chart-block" :class="{ 'is-table-chart': isTableChart }" :style="chartBlockStyle">
        <DisplayChartBlock
          :id="chartId"
          ref="chartRef"
          :chart-type="chartType"
          :message="message"
          :data="data"
          :loading-data="loadingData"
          :show-label="showLabel"
        />
      </div>
      <div v-if="dataObject.limit" class="over-limit-hint">
        {{ t('chat.data_over_limit', [dataObject.limit]) }}
      </div>
    </template>

    <AddViewDashboard ref="addViewRef"></AddViewDashboard>
    <el-dialog
      v-if="!enlarge"
      v-model="dialogVisible"
      fullscreen
      :show-close="false"
      class="chart-fullscreen-dialog"
      header-class="chart-fullscreen-dialog-header"
      body-class="chart-fullscreen-dialog-body"
    >
      <ChartBlock
        v-if="dialogVisible"
        :message="message"
        :record-id="recordId"
        :is-predict="isPredict"
        :chat-type="chartType"
        :loading-data="loadingData"
        enlarge
        @exit-full-screen="onExitFullScreen"
      />
    </el-dialog>

    <el-drawer
      v-model="sqlShow"
      :size="!isCompletePage ? '100%' : '600px'"
      :title="t('chat.show_sql')"
      direction="rtl"
      body-class="chart-sql-drawer-body"
    >
      <div class="sql-block">
        <SQLComponent
          v-if="message.record?.sql"
          :sql="message.record?.sql"
          style="margin-top: 12px"
        />
        <el-button v-if="message.record?.sql" circle class="input-icon" @click="copyText">
          <el-icon size="16">
            <icon_copy_outlined />
          </el-icon>
        </el-button>
      </div>
    </el-drawer>
  </div>
</template>

<style lang="less">
.chart-fullscreen-dialog {
  padding: 0;
}

.chart-fullscreen-dialog-header {
  display: none;
}

.chart-fullscreen-dialog-body {
  padding: 0;
  height: 100%;
}

.chart-sql-drawer-body {
  padding: 24px;
}

.smart-chart-answer {
  .chart-base-container {
    border: 0;
    box-shadow: none;
    background: #ffffff;
  }

  .chart-select-container {
    border-color: #e4ebf4 !important;
    background: #ffffff !important;
  }

  .buttons-bar .divider {
    border-color: #e1e8f2 !important;
  }

  .chart-active,
  .chat-select_type.active {
    background: #f2f7ff !important;
    color: #3f73e6 !important;
  }
}

.export_to_select.export_to_select {
  padding: 4px 0;
  width: 120px !important;
  min-width: 120px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;

  .popover {
    .popover-content {
      padding: 0 4px;
      max-height: 300px;
      overflow-y: auto;

      .title {
        width: 100%;
        height: 32px;
        margin-bottom: 2px;
        display: flex;
        align-items: center;
        padding-left: 8px;
        color: #8f959e;
      }
    }

    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 6px;
      cursor: pointer;

      &:last-child {
        margin-bottom: 0;
      }

      &:hover {
        background: #1f23291a;
      }

      .model-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        max-width: 220px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }
  }
}
</style>
<style scoped lang="less">
.chart-component-container {
  width: 100%;
  padding: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid #dce6f2;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 10px 28px rgba(36, 64, 102, 0.05);
  color: #18263a;
  font-family: Inter, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;

  &.full-screen {
    border: unset;
    border-radius: unset;
    padding: 0;
    height: 100%;

    .header-bar {
      height: 56px;
      padding: 14px 24px;
      border-bottom: 1px solid #e4ebf4;
    }

    .chart-block {
      margin: unset;
      padding: 16px 20px 20px;
      height: calc(100% - 56px);
    }
  }

  .header-bar {
    min-height: 34px;
    padding: 12px 16px;
    display: flex;
    align-items: center;
    flex-direction: row;
    gap: 12px;
    border-bottom: 1px solid #e6edf6;
    border-radius: 8px 8px 0 0;
    background: #ffffff;

    .tool-btn {
      width: 30px;
      min-width: 30px;
      height: 30px;
      padding: 0;
      font-size: 17px;
      font-weight: 400;
      line-height: 30px;
      border-radius: 7px;
      border: 1px solid transparent;
      background: transparent;
      color: #5f7088;
      transition:
        background-color 0.16s ease,
        border-color 0.16s ease,
        color 0.16s ease,
        box-shadow 0.16s ease;

      .tool-btn-inner {
        display: flex;
        flex-direction: row;
        align-items: center;
      }

      &:hover {
        background: #f5f8fd;
        border-color: #dce6f2;
        color: #34516f;
      }

      &:active {
        background: #ecf3ff;
      }
    }

    .chart-active {
      background: #edf4ff;
      color: #346fe8;
      border-color: rgba(79, 125, 243, 0.28);
      border-radius: 7px;
      box-shadow: 0 2px 6px rgba(79, 125, 243, 0.1);

      :deep(.ed-select__wrapper) {
        background: transparent;
      }

      :deep(.ed-select__input) {
        color: #346fe8;
      }

      :deep(.ed-select__placeholder) {
        color: #346fe8;
      }

      :deep(.ed-select__caret) {
        color: #346fe8;
      }
    }

    .title {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;

      color: #132238;
      font-weight: 600;
      font-size: 15px;
      line-height: 22px;
      letter-spacing: 0;
      padding-left: 10px;
      border-left: 3px solid #4f7df3;
    }

    .buttons-bar {
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 8px;
      flex: 0 0 auto;

      .divider {
        width: 1px;
        height: 18px;
        margin: 0 2px;
        border-left: 1px solid #e1e8f2;
      }
    }

    .chart-select-container {
      padding: 2px;
      display: flex;
      flex-direction: row;
      gap: 4px;
      border-radius: 9px;
      border: 1px solid #e4ebf4;
      background: #ffffff;
      box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.75);

      .chart-select {
        min-width: 44px;
        width: 44px;
        height: 30px;

        :deep(.ed-select__wrapper) {
          padding: 4px;
          min-height: 30px;
          box-shadow: unset;
          border-radius: 7px;

          &:hover {
            background: #f6f9fd;
          }

          &:active {
            background: #e8f0fb;
          }
        }

        :deep(.ed-select__caret) {
          font-size: 12px !important;
        }
      }
    }
  }

  .chart-block {
    height: 356px;
    width: 100%;
    padding: 14px 16px 16px;
    background: #ffffff;
  }

  .data-permission-warning {
    margin: 16px;
    padding: 12px 14px;
    border: 1px solid #f3d19e;
    border-radius: 6px;
    background: #fdf6ec;
    color: #9a5b00;
    font-size: 14px;
    line-height: 22px;
  }

  .over-limit-hint {
    padding: 0 16px 12px;
    min-height: 24px;
    line-height: 24px;
    font-size: 14px;
  }
}

.sql-block {
  position: relative;

  .input-icon {
    min-width: unset;
    position: absolute;
    top: 12px;
    right: 12px;
    color: #1f2329;
    display: none;
    background-color: transparent !important;

    border-color: #dee0e3;
    box-shadow: 0px 4px 8px 0px #1f23291a;

    &:hover,
    &:focus {
      color: var(--ed-color-primary);
    }

    &:active {
      color: var(--ed-color-primary-dark-2);
    }
  }

  &:hover {
    .input-icon {
      display: flex;
    }
  }
}
</style>
