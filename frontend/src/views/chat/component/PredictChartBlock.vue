<script setup lang="ts">
import type { ChatMessage } from '@/api/chat.ts'
import { computed, watch, ref } from 'vue'
import type { ChartTypes } from '@/views/chat/component/BaseChart.ts'
import DisplayChartBlock from '@/views/chat/component/DisplayChartBlock.vue'
import { concat } from 'lodash-es'

const props = defineProps<{
  id?: number | string
  chartType: ChartTypes
  message: ChatMessage
  data: string
}>()

const dataObject = computed<{
  fields: Array<string>
  data: Array<{ [key: string]: any }>
}>(() => {
  if (props.message?.record?.data) {
    return JSON.parse(props.message.record.data)
  }
  return {}
})

const _data = computed(() => {
  let _list = []
  if (
    props.data &&
    props.data.length > 0 &&
    props.data.trim().startsWith('[') &&
    props.data.trim().endsWith(']')
  ) {
    try {
      _list = JSON.parse(props.data)
    } catch (e) {
      console.error(e)
    }
  }

  if (_list.length == 0) {
    return _list
  }

  if (dataObject.value.data && dataObject.value.data.length > 0) {
    return concat(dataObject.value.data, _list)
  }

  return _list
})

const blockRef = ref()

watch(
  () => props.chartType,
  () => {
    blockRef.value?.onTypeChange()
  }
)
</script>

<template>
  <DisplayChartBlock
    v-if="_data.length > 0"
    :id="id"
    ref="blockRef"
    :chart-type="chartType"
    :message="message"
    :data="_data"
  />
</template>

<style scoped lang="less">
.chart-base-container {
  padding: 20px;
  background: rgba(224, 224, 226, 0.29);
}
</style>
