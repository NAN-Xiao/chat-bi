<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'
import { computed, nextTick, ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import ChartComponent from './component/ChartComponent.vue'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
import { ArrowDown } from '@element-plus/icons-vue'
import ICON_BAR from '@/assets/svg/chart/bar.svg'
import ICON_COLUMN from '@/assets/svg/chart/column.svg'
import ICON_LINE from '@/assets/svg/chart/line.svg'
import ICON_PIE from '@/assets/svg/chart/pie.svg'
import ICON_TABLE from '@/assets/svg/chart/table.svg'
import { find } from 'lodash-es'

const props = defineProps<{
  message?: ChatMessage
}>()

const settings = ref<{
  type: 'chart' | 'sql'
  showAnswer: boolean
}>({
  type: 'chart',
  showAnswer: false,
})

const renderSqlThinking = computed(() => {
  //todo md render?
  return props.message?.record?.sql_answer
})

const renderChartThinking = computed(() => {
  //todo md render?
  return props.message?.record?.chart_answer
})

const dataObject = computed<{
  fields: Array<string>
  data: Array<{ [key: string]: any }>
}>(() => {
  if (props.message?.record?.data) {
    return JSON.parse(props.message.record.data)
  }
  return {}
})

const chartObject = computed<{
  type: ChartTypes
  title: string
  axis: {
    x: { name: string; value: string }
    y: { name: string; value: string }
    series: { name: string; value: string }
  }
  columns: Array<{ name: string; value: string }>
}>(() => {
  if (props.message?.record?.chart) {
    return JSON.parse(props.message.record.chart)
  }
  return {}
})

const xAxis = computed(() => {
  if (chartObject.value?.axis?.x) {
    return [chartObject.value.axis.x]
  }
  return []
})
const yAxis = computed(() => {
  if (chartObject.value?.axis?.y) {
    return [chartObject.value.axis.y]
  }
  return []
})
const series = computed(() => {
  if (chartObject.value?.axis?.series) {
    return [chartObject.value.axis.series]
  }
  return []
})

const currentChartType = ref<ChartTypes | undefined>(undefined)

const chartType = computed<ChartTypes>({
  get() {
    if (currentChartType.value) {
      return currentChartType.value
    }
    return chartObject.value.type ?? 'table'
  },
  set(v) {
    currentChartType.value = v
  },
})

function clickTab(type: 'chart' | 'sql') {
  settings.value.type = type
}

const chartSelectRef = ref()

function openChartSelect() {
  chartSelectRef.value.toggleMenu()
}

const chartTypeList = computed(() => {
  const _list = [
    {
      value: 'table',
      icon: ICON_TABLE,
    },
  ]
  if (chartObject.value) {
    switch (chartObject.value.type) {
      case 'table':
        break
      case 'column':
      case 'bar':
      case 'line':
        _list.push({
          value: 'column',
          icon: ICON_COLUMN,
        })
        _list.push({
          value: 'bar',
          icon: ICON_BAR,
        })
        _list.push({
          value: 'line',
          icon: ICON_LINE,
        })
        break
      case 'pie':
        _list.push({
          value: 'pie',
          icon: ICON_PIE,
        })
    }
  }

  return _list
})

const currentChartTypeIcon = computed(() => {
  return find(chartTypeList.value, (c) => c.value === chartType.value)?.icon ?? ICON_TABLE
})

const chartRef = ref()

function onTypeChange() {
  nextTick(() => {
    chartRef.value?.destroyChart()
    chartRef.value?.renderChart()
  })
}
</script>

<template>
  <el-container v-if="message">
    <el-header style="display: flex; align-items: center; flex-direction: row">
      <div style="flex: 1">
        <div v-if="message.isTyping">Thinking ...</div>
        <div v-if="chartObject.title && !message.isTyping">{{ chartObject.title }}</div>
      </div>
      <div class="tab-container">
        <div class="base-chart-choose-btn" @click="clickTab('chart')">
          <div
            class="chart-choose-btn"
            :class="{ active: settings.type === 'chart', 'no-click': settings.type !== 'chart' }"
            @click="openChartSelect"
          >
            <el-icon size="34">
              <component :is="currentChartTypeIcon" />
            </el-icon>
            <el-icon>
              <ArrowDown />
            </el-icon>
          </div>
          <el-select
            ref="chartSelectRef"
            v-model="chartType"
            class="inner-select"
            :disabled="settings.type !== 'chart'"
            @change="onTypeChange"
          >
            <el-option v-for="t in chartTypeList" :key="t.value" :value="t.value">
              <div class="inner-chart-option">
                <el-icon size="34">
                  <component :is="t.icon" />
                </el-icon>
                {{ t.value }}
              </div>
            </el-option>
          </el-select>
        </div>
        <div
          class="chart-choose-btn"
          :class="{ active: settings.type !== 'chart' }"
          @click="clickTab('sql')"
        >
          SQL
        </div>
      </div>
    </el-header>
    <el-container direction="vertical">
      <template v-if="message.record">
        <el-collapse expand-icon-position="left">
          <el-collapse-item name="1">
            <template #title>
              Inference process
              <el-icon v-if="props.message?.isTyping">
                <Loading />
              </el-icon>
            </template>
            <div>
              <template v-if="message.record.sql_answer">
                <div>SQL Generation:</div>
                <div v-if="message.record.sql_answer" v-dompurify-html="renderSqlThinking"></div>
              </template>
              <template v-if="message.record.chart_answer">
                <el-divider></el-divider>
                <div>Chart Generation:</div>
                <div v-dompurify-html="renderChartThinking"></div>
              </template>
            </div>
          </el-collapse-item>
        </el-collapse>
        <div class="answer-content">
          <template v-if="settings.type === 'sql'">
            <div>
              <div v-if="message.record.sql">
                {{ message.record.sql }}
              </div>
            </div>
          </template>
          <template v-else-if="settings.type === 'chart'">
            <div>
              <div v-if="message.record.chart" class="chart-base-container">
                <div>
                  <ChartComponent
                    v-if="message.record.id"
                    :id="message.record.id"
                    ref="chartRef"
                    :type="chartType"
                    :columns="chartObject?.columns"
                    :x="xAxis"
                    :y="yAxis"
                    :series="series"
                    :data="dataObject.data"
                  />
                </div>
              </div>
            </div>
            <div v-if="message.record.error" style="color: red">
              {{ message.record.error }}
            </div>
          </template>
        </div>
      </template>
    </el-container>
    <!--<el-footer></el-footer>-->
  </el-container>
</template>

<style scoped lang="less">
:deep(.ed-tabs__nav-scroll) {
  display: flex;
  justify-content: flex-end;
}

.answer-content {
  padding: 12px;
}

.type-tabs {
  margin-right: 24px;
}

.chart-base-container {
  padding: 20px;
  background: rgba(224, 224, 226, 0.29);
}

.tab-container {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 4px;
}

.base-chart-choose-btn {
  cursor: pointer;
  color: var(--ed-color-primary);
  font-size: 16px;
  font-weight: 500;
  height: 34px;

  border-radius: 4px;

  position: relative;

  &:hover {
    background: var(--ed-color-primary-light-5);
    color: var(--ed-color-primary-light-9);
  }

  .inner-select {
    position: absolute;

    :deep(.ed-select__wrapper) {
      height: 0;
      padding: unset;
      min-height: unset;
      line-height: unset;
    }

    :deep(.ed-select__suffix) {
      display: none;
    }

    :deep(.ed-select__selected-item) {
      display: none;
    }
  }
}

.inner-chart-option {
  display: flex;
  align-items: center;
  flex-direction: row;
  padding-right: 4px;
}

.chart-choose-btn {
  cursor: pointer;
  color: var(--ed-color-primary);
  font-size: 16px;
  font-weight: 500;
  height: 34px;

  border-radius: 4px;

  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  padding: 0 4px;

  &.no-click {
    pointer-events: none;
  }

  &.active {
    background: var(--ed-color-primary-light-7);
    color: var(--ed-color-primary);
  }

  &:hover {
    background: var(--ed-color-primary-light-5);
    color: var(--ed-color-primary-light-9);
  }
}
</style>
