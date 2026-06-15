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
const permissionDeniedPatterns = [
  '当前用户无权访问项目',
  'Datasource access is required',
  'Chat does not belong to current project',
  'SQL 超出当前数据权限范围',
  'SQL 包含无权限表',
  'SQL contains unauthorized tables',
  'SQL 包含无权限字段',
  'SQL 使用了 SELECT *，无法安全应用字段权限',
  '无法安全应用字段权限',
  '行权限过滤条件无法安全解析',
]

const showBlock = computed(() => {
  return props.error && props.error?.trim().length > 0
})

function isPermissionDeniedError(message?: string) {
  if (!message) return false
  return permissionDeniedPatterns.some(pattern => message.includes(pattern))
}

const errorMessage = computed(() => {
  const obj: { message?: string; showMore: boolean; traceback: string; type?: string } = {
    message: props.error,
    showMore: false,
    traceback: '',
    type: undefined,
  }
  if (showBlock.value && props.error?.trim().startsWith('{') && props.error?.trim().endsWith('}')) {
    try {
      const json = JSON.parse(props.error?.trim())
      obj.message = json['message']
      obj.traceback = json['traceback']
      obj.type = json['type']
      if (obj.traceback?.trim().length > 0) {
        obj.showMore = true
      }
    } catch (e) {
      console.error(e)
    }
  }
  if (isPermissionDeniedError(`${obj.message ?? ''}\n${obj.traceback ?? ''}`)) {
    obj.message = t('chat.permission_denied_tip')
    obj.showMore = false
    obj.traceback = ''
    obj.type = permissionDeniedType
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
