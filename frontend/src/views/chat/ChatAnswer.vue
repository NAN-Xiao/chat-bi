<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'
import { computed, ref } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import MdComponent from './component/MdComponent.vue'
import DisplayChartBlock from './component/DisplayChartBlock.vue'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
import { ArrowDown } from '@element-plus/icons-vue'
import ICON_BAR from '@/assets/svg/chart/bar.svg'
import ICON_COLUMN from '@/assets/svg/chart/column.svg'
import ICON_LINE from '@/assets/svg/chart/line.svg'
import ICON_PIE from '@/assets/svg/chart/pie.svg'
import ICON_TABLE from '@/assets/svg/chart/table.svg'
import { find } from 'lodash-es'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
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
  return props.message?.record?.sql_answer ?? ''
})

const renderChartThinking = computed(() => {
  return props.message?.record?.chart_answer ?? ''
})

const renderSQL = computed(() => {
  return props.message?.record?.sql
    ? `\`\`\`sql

${props.message?.record?.sql}
    `
    : ''
})

const dataObject = computed<{
  fields: Array<string>
  data: Array<{ [key: string]: any }>
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
      name: t('chat.chart_type.table'),
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
          name: t('chat.chart_type.column'),
          icon: ICON_COLUMN,
        })
        _list.push({
          value: 'bar',
          name: t('chat.chart_type.bar'),
          icon: ICON_BAR,
        })
        _list.push({
          value: 'line',
          name: t('chat.chart_type.line'),
          icon: ICON_LINE,
        })
        break
      case 'pie':
        _list.push({
          value: 'pie',
          name: t('chat.chart_type.pie'),
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
  chartRef.value?.onTypeChange()
}
</script>

<template>
  <el-container v-if="message">
    <el-header style="display: flex; align-items: center; flex-direction: row">
      <div style="flex: 1">
        <div v-if="message.isTyping">{{ t('chat.thinking') }} ...</div>
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
                {{ t.name }}
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
          <el-collapse-item name="1" class="md-collapse">
            <template #title>
              {{ t('chat.inference_process') }}
              <el-icon v-if="props.message?.isTyping">
                <Loading />
              </el-icon>
            </template>
            <div>
              <template v-if="message.record.sql_answer">
                <div style="font-weight: 500">{{ t('chat.sql_generation') }}:</div>
                <MdComponent
                  v-if="message.record.sql_answer"
                  :message="renderSqlThinking"
                ></MdComponent>
              </template>
              <template v-if="message.record.chart_answer">
                <el-divider></el-divider>
                <div style="font-weight: 500">{{ t('chat.chart_generation') }}:</div>
                <MdComponent :message="renderChartThinking"></MdComponent>
              </template>
            </div>
          </el-collapse-item>
        </el-collapse>
        <div class="answer-content">
          <template v-if="settings.type === 'sql'">
            <div>
              <MdComponent v-if="message.record.sql" :message="renderSQL"></MdComponent>
            </div>
          </template>
          <template v-else-if="settings.type === 'chart'">
            <DisplayChartBlock
              :id="message.record.id"
              ref="chartRef"
              :chart-type="chartType"
              :message="message"
              :data="dataObject.data"
            />
            <div v-if="message.record.error" style="color: red">
              {{ message.record.error }}
            </div>
          </template>
        </div>
      </template>
    </el-container>
    <slot :data="{ id: message.record?.id, chartType: chartType, chartObject: chartObject }"></slot>
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

.md-collapse {
  :deep(.ed-collapse-item__content) {
    padding: 16px 22px;
  }
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
