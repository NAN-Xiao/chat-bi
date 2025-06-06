<script setup lang="ts">

import type {ChatMessage} from "@/api/chat.ts";
import {computed, ref} from "vue";
import type {TabsPaneContext} from 'element-plus'
import {Loading} from "@element-plus/icons-vue";

const props = defineProps<{
  message?: ChatMessage
}>()

const settings = ref<{
  type: "chart" | "sql"
  showAnswer: boolean
}>({
  type: "chart",
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

const handleClick = (tab: TabsPaneContext, event: Event) => {
  console.log(tab, event)
}

const dataObject = computed<{
  fields: Array<string>,
  data: Array<{ [key: string]: any }>,
}>(() => {
  if (props.message?.record?.data) {
    return JSON.parse(props.message.record.data)
  }
  return {}
})

const chartObject = computed<{
  type: "table" | "bar" | "line" | "pie"
  title: string
  axis: { x: { name: string, value: string }, y: { name: string, value: string } }
  columns: Array<{ name: string, value: string }>
}>(() => {
  if (props.message?.record?.chart) {
    return JSON.parse(props.message.record.chart)
  }
  return {}
})

const currentChartType = ref<"table" | "bar" | "line" | "pie" | undefined>(undefined)

const chartType = computed<"table" | "bar" | "line" | "pie">({
  get() {
    if (currentChartType.value) {
      return currentChartType.value
    }
    return chartObject.value.type ?? "table"
  },
  set(v) {
    currentChartType.value = v
  }
})


</script>

<template>
  <div v-if="message">
    <div>
      <div v-if="message.isTyping">Thinking ...</div>
      <div v-if="chartObject.title && !message.isTyping">{{ chartObject.title }}</div>
      <el-tabs v-model="settings.type" class="demo-tabs" @tab-click="handleClick" tab-position="top">
        <el-tab-pane label="Chart" name="chart">
          <template #label>
            <el-select v-model="chartType" style="width: 80px" :disabled="settings.type!== 'chart'">
              <el-option value="table">table</el-option>
              <el-option value="bar">bar</el-option>
              <el-option value="line">line</el-option>
              <el-option value="pie">pie</el-option>
            </el-select>
          </template>
        </el-tab-pane>
        <el-tab-pane label="SQL" name="sql"></el-tab-pane>
      </el-tabs>
    </div>
    <template v-if="message.record">
      <el-collapse expand-icon-position="left">
        <el-collapse-item name="1">
          <template #title>
            Inference process
            <el-icon v-if="props.message?.isTyping">
              <Loading/>
            </el-icon>
          </template>
          <div>
            <template v-if="message.record.sql_answer">
              <div>SQL Generation:</div>
              <div v-if="message.record.sql_answer" v-html="renderSqlThinking"></div>
            </template>
            <template v-if="message.record.chart_answer">
              <el-divider></el-divider>
              <div>Chart Generation:</div>
              <div v-html="renderChartThinking"></div>
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

            <div v-if="message.record.chart">
              {{ chartObject }}
            </div>
          </div>
          <div v-if="message.record.error" style="color: red">
            {{ message.record.error }}
          </div>
        </template>
        <template v-else>
          <div>
            <div v-if="dataObject.fields">
              {{ dataObject.fields }}
              {{ dataObject.data }}
            </div>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped lang="less">
:deep(.ed-tabs__nav-scroll) {
  display: flex;
  justify-content: flex-end;
}

.answer-content {
  padding: 12px;
}
</style>