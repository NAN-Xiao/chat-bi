<script setup lang="ts">
import { computed } from 'vue'
import { InfoFilled, WarningFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  notice?: Record<string, any>
  message?: string
}>()

const reasonText: Record<string, string> = {
  missing_event: '缺少埋点',
  missing_schema: '缺少字段/表',
  permission_denied: '权限限制',
  data_unavailable: '数据不可用',
  event_existence_unknown: '埋点待确认',
}

const severity = computed(() => String(props.notice?.severity || 'warning'))
const tagText = computed(() => reasonText[String(props.notice?.reason || '')] || '数据范围提示')
const items = computed(() => {
  const raw = props.notice?.items
  return Array.isArray(raw) ? raw.map((item) => String(item)).filter(Boolean) : []
})
const isWarning = computed(() => severity.value !== 'info')
</script>

<template>
  <div class="business-notice" :class="{ warning: isWarning }">
    <el-icon class="notice-icon" :size="16">
      <WarningFilled v-if="isWarning" />
      <InfoFilled v-else />
    </el-icon>
    <div class="notice-body">
      <div class="notice-line">
        <el-tag class="notice-tag" :type="isWarning ? 'warning' : 'info'" size="small" effect="light">
          {{ tagText }}
        </el-tag>
        <span class="notice-message">{{ message }}</span>
      </div>
      <div v-if="items.length > 0" class="notice-items">
        <el-tag v-for="item in items" :key="item" size="small" type="danger" effect="light">
          {{ item }}
        </el-tag>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.business-notice {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 0 0 8px;
  padding: 10px 12px;
  border: 1px solid #d9e7ff;
  border-radius: 8px;
  background: #f5f9ff;
  color: #27364a;
  font-size: 14px;
  line-height: 22px;

  &.warning {
    border-color: #ffd8bd;
    background: #fff7f0;

    .notice-icon {
      color: #d0630f;
    }
  }

  .notice-icon {
    margin-top: 3px;
    color: #3f73e6;
    flex: 0 0 auto;
  }

  .notice-body {
    min-width: 0;
  }

  .notice-line {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }

  .notice-tag {
    flex: 0 0 auto;
  }

  .notice-message {
    word-break: break-word;
  }

  .notice-items {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
  }
}
</style>
