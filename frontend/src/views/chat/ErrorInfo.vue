<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAssistantStore } from '@/stores/assistant.ts'

const props = defineProps<{
  error?: string
}>()

const { t } = useI18n()

const assistantStore = useAssistantStore()
const isCompletePage = computed(() => !assistantStore.getAssistant || assistantStore.getEmbedded)
const permissionDeniedType = 'permission-denied'
const dataUnavailableType = 'data-unavailable'
const permissionDeniedPatterns = [
  '当前用户无权访问项目',
  'Datasource access is required',
  'Chat does not belong to current project',
  '没有查看权限',
  'SQL 超出当前数据权限范围',
  'SQL 包含无权限表',
  'SQL contains unauthorized tables',
  'SQL 包含无权限字段',
  'SQL 使用了 SELECT *，无法安全应用字段权限',
  '无法安全应用字段权限',
  '行权限过滤条件无法安全解析',
]
const dataUnavailablePatterns = [
  '当前数据源缺少本次问题所需',
  '当前数据源缺少所需',
  '当前数据源没有',
  '当前数据库 Schema 中不存在',
  'schema 中不存在',
  '缺少所需表',
  '缺少所需字段',
  '缺少所需埋点',
  '缺少埋点',
  '埋点不存在',
  '事件不存在',
  '没有这个数据',
  '没有对应埋点',
  '没有该埋点',
  'table is not present in schema',
  'field is not present in schema',
  'missing required table',
  'missing required field',
  'missing required event',
  'missing tracking event',
]
const dataUnavailableFallback =
  '当前数据源缺少本次问题所需的表、字段或埋点数据。请换一个当前数据源已包含的指标，或让管理员补充对应配置后再试。'

const showBlock = computed(() => {
  return props.error && props.error?.trim().length > 0
})

function isPermissionDeniedError(message?: string) {
  if (!message) return false
  return permissionDeniedPatterns.some(pattern => message.includes(pattern))
}

function isDataUnavailableError(message?: string) {
  if (!message) return false
  const text = message.toLowerCase()
  return dataUnavailablePatterns.some(pattern => text.includes(pattern.toLowerCase()))
}

const errorMessage = computed(() => {
  const obj: { message?: string; showMore: boolean; traceback: string; type?: string; errorType?: string } = {
    message: props.error,
    showMore: false,
    traceback: '',
    type: undefined,
    errorType: undefined,
  }
  if (showBlock.value && props.error?.trim().startsWith('{') && props.error?.trim().endsWith('}')) {
    try {
      const json = JSON.parse(props.error?.trim())
      obj.message = json['message']
      obj.traceback = json['traceback']
      obj.type = json['type']
      obj.errorType = json['error_type'] || json['errorType']
      if (obj.traceback?.trim().length > 0) {
        obj.showMore = true
      }
    } catch (e) {
      console.error(e)
    }
  }
  if (obj.errorType === 'permission_denied' || obj.type === 'permission_denied') {
    obj.message = t('chat.permission_denied_tip')
    obj.showMore = false
    obj.traceback = ''
    obj.type = permissionDeniedType
  } else if (obj.errorType === 'data_unavailable' || obj.type === 'data_unavailable') {
    obj.message = obj.message || dataUnavailableFallback
    obj.showMore = false
    obj.traceback = ''
    obj.type = dataUnavailableType
  } else if (isPermissionDeniedError(`${obj.message ?? ''}\n${obj.traceback ?? ''}`)) {
    obj.message = t('chat.permission_denied_tip')
    obj.showMore = false
    obj.traceback = ''
    obj.type = permissionDeniedType
  } else if (isDataUnavailableError(obj.message)) {
    obj.message = obj.message || dataUnavailableFallback
    obj.showMore = false
    obj.traceback = ''
    obj.type = dataUnavailableType
  }
  return obj
})

const show = ref(false)

function showTraceBack() {
  show.value = true
}
</script>

<template>
  <div v-if="showBlock">
    <div
      v-if="!errorMessage.showMore && errorMessage.type == undefined"
      v-dompurify-html="errorMessage.message"
      class="error-container"
    ></div>
    <div v-else class="error-container row">
      <template v-if="errorMessage.type === 'db-connection-err'">
        {{ t('chat.ds_is_invalid') }}
      </template>
      <template v-else-if="errorMessage.type === 'exec-sql-err'">
        {{ t('chat.exec-sql-err') }}
      </template>
      <template v-else-if="errorMessage.type === permissionDeniedType">
        {{ errorMessage.message }}
      </template>
      <template v-else-if="errorMessage.type === dataUnavailableType">
        {{ errorMessage.message }}
      </template>
      <template v-else>
        {{ t('chat.error') }}
      </template>
      <el-button v-if="errorMessage.showMore" text @click="showTraceBack">
        {{ t('chat.show_error_detail') }}
      </el-button>
    </div>

    <el-drawer
      v-model="show"
      :size="!isCompletePage ? '100%' : '600px'"
      :title="t('chat.error')"
      direction="rtl"
      body-class="chart-sql-error-body"
    >
      <el-main>
        <div v-dompurify-html="errorMessage.traceback" class="error-container open"></div>
      </el-main>
    </el-drawer>
  </div>
</template>

<style lang="less">
.chart-sql-error-body {
  padding: 0;
}
</style>
<style scoped lang="less">
.error-container {
  font-weight: 400;
  font-size: 16px;
  line-height: 24px;
  color: rgba(31, 35, 41, 1);
  white-space: pre-wrap;
  word-break: break-word;

  &.row {
    display: flex;
    flex-direction: row;
    align-items: center;
  }
  &.open {
    font-size: 14px;
    line-height: 20px;
  }
}
</style>
