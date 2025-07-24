<script setup lang="ts">
import ChartComponent from '@/views/chat/component/ChartComponent.vue'
import icon_window_mini_outlined from '@/assets/svg/icon_window-mini_outlined.svg'
import SqViewDisplay from '@/views/dashboard/components/sq-view/index.vue'
defineProps({
  viewInfo: {
    type: Object,
    required: true,
  },
  outerId: {
    type: String,
    required: false,
    default: null,
  },
})

import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
const chartRef = ref(null)
const renderChart = () => {
  //@ts-expect-error eslint-disable-next-line @typescript-eslint/no-unused-expressions
  // eslint-disable-next-line @typescript-eslint/no-unused-expressions
  chartRef.value?.renderChart
}
const enlargeDialogVisible = ref(false)

const enlargeView = () => {
  enlargeDialogVisible.value = true
}
defineExpose({
  renderChart,
  enlargeView,
})
</script>

<template>
  <div class="chart-base-container">
    <div class="header-bar">
      <div class="title">
        {{ viewInfo.chart.title }}
      </div>
    </div>
    <div class="chart-show-area">
      <ChartComponent
        v-if="viewInfo.id"
        :id="outerId || viewInfo.id"
        ref="chartRef"
        :type="viewInfo.chart.type"
        :columns="viewInfo.chart.columns"
        :x="viewInfo.chart?.xAxis"
        :y="viewInfo.chart?.yAxis"
        :series="viewInfo.chart?.series"
        :data="viewInfo.data?.data"
      />
    </div>
    <el-dialog
      v-if="enlargeDialogVisible"
      v-model="enlargeDialogVisible"
      fullscreen
      :show-close="false"
      class="chart-fullscreen-dialog-view"
      header-class="chart-fullscreen-dialog-header-view"
      body-class="chart-fullscreen-dialog-body-view"
    >
      <div style="position: absolute; right: 15px; top: 15px; cursor: pointer">
        <el-tooltip effect="dark" :content="t('dashboard.exit_preview')" placement="top">
          <el-button
            class="tool-btn"
            style="width: 26px"
            text
            @click="() => (enlargeDialogVisible = false)"
          >
            <el-icon size="16">
              <icon_window_mini_outlined />
            </el-icon>
          </el-button>
        </el-tooltip>
      </div>
      <SqViewDisplay :view-info="viewInfo" :outer-id="'enlarge-' + viewInfo.id" />
    </el-dialog>
  </div>
</template>

<style lang="less">
.chart-fullscreen-dialog-view {
  padding: 0;
}
.chart-fullscreen-dialog-header-view {
  display: none;
}
.chart-fullscreen-dialog-body-view {
  padding: 0;
  height: 100%;
}
</style>

<style scoped lang="less">
.chart-base-container {
  width: 100%;
  height: 100%;
  background: #fff;
  padding: 12px !important;
  border-radius: 12px;
  div::-webkit-scrollbar {
    width: 0 !important;
    height: 0 !important;
  }
  .header-bar {
    height: 32px;
    display: flex;

    align-items: center;
    flex-direction: row;

    .tool-btn {
      width: 24px;
      height: 24px;

      font-size: 16px;
      font-weight: 400;
      line-height: 24px;
      border-radius: 6px;
      color: rgba(100, 106, 115, 1);

      .tool-btn-inner {
        display: flex;
        flex-direction: row;
        align-items: center;
      }

      &:hover {
        background: rgba(31, 35, 41, 0.1);
      }
      &:active {
        background: rgba(31, 35, 41, 0.1);
      }
    }

    .chart-active {
      background: rgba(28, 186, 144, 0.1);
      color: rgba(28, 186, 144, 1);
      border-radius: 6px;

      :deep(.ed-select__wrapper) {
        background: transparent;
      }
      :deep(.ed-select__input) {
        color: rgba(28, 186, 144, 1);
      }
      :deep(.ed-select__placeholder) {
        color: rgba(28, 186, 144, 1);
      }
      :deep(.ed-select__caret) {
        color: rgba(28, 186, 144, 1);
      }
    }

    .title {
      flex: 1;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;

      color: rgba(31, 35, 41, 1);
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
    }

    .buttons-bar {
      display: flex;
      flex-direction: row;
      align-items: center;

      gap: 16px;

      .divider {
        width: 1px;
        height: 16px;
        border-left: 1px solid rgba(31, 35, 41, 0.15);
      }
    }

    .chart-select-container {
      padding: 3px;
      display: flex;
      flex-direction: row;
      gap: 4px;
      border-radius: 6px;

      border: 1px solid rgba(217, 220, 223, 1);

      .chart-select {
        min-width: 40px;
        width: 40px;
        height: 24px;

        :deep(.ed-select__wrapper) {
          padding: 4px;
          min-height: 24px;
          box-shadow: unset;
          border-radius: 6px;

          &:hover {
            background: rgba(31, 35, 41, 0.1);
          }
          &:active {
            background: rgba(31, 35, 41, 0.1);
          }
        }
        :deep(.ed-select__caret) {
          font-size: 12px !important;
        }
      }
    }
  }
}

.chart-show-area {
  width: 100%;
  height: calc(100% - 32px);
}
</style>
