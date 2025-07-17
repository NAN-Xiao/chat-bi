<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'
import DisplayChartBlock from '@/views/chat/component/DisplayChartBlock.vue'
import { computed, ref } from 'vue'
import { concat } from 'lodash-es'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'

const props = withDefaults(
  defineProps<{
    message: ChatMessage
    isPredict?: boolean
  }>(),
  {
    isPredict: false,
  }
)

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
      if (props.message?.record?.predict_data.length > 0) {
        _list = props.message?.record?.predict_data
      }
    }

    if (_list.length == 0) {
      return _list
    }

    if (dataObject.value.data && dataObject.value.data.length > 0) {
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
</script>

<template>
  <div
    v-if="
      (!isPredict && (message?.record?.sql || message?.record?.chart)) ||
      (isPredict && message?.record?.chart && data.length > 0)
    "
    class="chart-component-container"
  >
    <div class="header-bar">todo</div>
    <div v-if="message?.record?.chart" class="chart-block">
      <DisplayChartBlock
        :id="message.record.id"
        ref="chartRef"
        :chart-type="chartType"
        :message="message"
        :data="data"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.chart-component-container {
  width: 100%;
  padding: 16px;
  display: flex;
  flex-direction: column;

  gap: 16px;

  border: 1px solid rgba(222, 224, 227, 1);
  border-radius: 12px;

  .header-bar {
    height: 32px;
  }

  .chart-block {
    height: 352px;
    width: 100%;
  }
}
</style>
