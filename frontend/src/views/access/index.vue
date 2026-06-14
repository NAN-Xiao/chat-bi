<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()

const accessLevel = computed(() => {
  if (userStore.isAdmin) {
    return {
      label: t('access.full'),
      type: 'success',
      description: t('access.full_description'),
    }
  }
  return {
    label: t('access.limited'),
    type: 'warning',
    description: t('access.limited_description'),
  }
})

const capabilityList = computed(() => {
  const isFull = userStore.isAdmin
  const status = isFull ? t('access.full') : t('access.policy_open')
  const dataStatus = isFull ? t('access.full') : t('access.limited')
  const adminStatus = isFull ? t('access.full') : t('access.restricted')

  return [
    {
      title: t('access.qa'),
      status,
      description: t('access.qa_description'),
    },
    {
      title: t('access.dashboard'),
      status,
      description: t('access.dashboard_description'),
    },
    {
      title: t('access.analysis_assistant'),
      status,
      description: t('access.analysis_assistant_description'),
    },
    {
      title: t('access.data_scope'),
      status: dataStatus,
      description: t('access.data_scope_description'),
    },
    {
      title: t('access.admin_settings'),
      status: adminStatus,
      description: t('access.admin_settings_description'),
    },
  ]
})
</script>

<template>
  <div class="access-page">
    <div class="access-header">
      <div>
        <div class="access-title">{{ t('access.my_permissions') }}</div>
        <div class="access-subtitle">{{ t('access.subtitle') }}</div>
      </div>
      <el-tag :type="accessLevel.type" effect="light" round>
        {{ accessLevel.label }}
      </el-tag>
    </div>

    <section class="access-summary">
      <div class="summary-label">{{ t('access.current_level') }}</div>
      <div class="summary-value">{{ accessLevel.label }}</div>
      <div class="summary-description">{{ accessLevel.description }}</div>
    </section>

    <section class="access-section">
      <div class="section-title">{{ t('access.available_capabilities') }}</div>
      <div class="capability-list">
        <div v-for="item in capabilityList" :key="item.title" class="capability-item">
          <div class="capability-main">
            <div class="capability-title">{{ item.title }}</div>
            <div class="capability-description">{{ item.description }}</div>
          </div>
          <el-tag effect="plain" round>
            {{ item.status }}
          </el-tag>
        </div>
      </div>
    </section>

    <section class="access-notice">
      <div class="notice-title">{{ t('access.privacy_title') }}</div>
      <div class="notice-description">{{ t('access.privacy_description') }}</div>
      <div class="notice-footer">{{ t('access.apply_tip') }}</div>
    </section>
  </div>
</template>

<style lang="less" scoped>
.access-page {
  height: 100%;
  padding: 8px 0 24px;
  color: #1f2329;

  .access-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 24px;
  }

  .access-title {
    font-weight: 600;
    font-size: 22px;
    line-height: 30px;
  }

  .access-subtitle {
    margin-top: 6px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
  }

  .access-summary,
  .access-section,
  .access-notice {
    border: 1px solid #dee0e3;
    border-radius: 8px;
    background: #fff;
  }

  .access-summary {
    padding: 24px;
    margin-bottom: 16px;
    background: linear-gradient(180deg, #f7faf9 0%, #fff 100%);
  }

  .summary-label {
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .summary-value {
    margin-top: 8px;
    font-weight: 600;
    font-size: 28px;
    line-height: 36px;
  }

  .summary-description {
    margin-top: 8px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
  }

  .access-section {
    padding: 20px 24px 8px;
    margin-bottom: 16px;
  }

  .section-title {
    margin-bottom: 8px;
    font-weight: 600;
    font-size: 16px;
    line-height: 24px;
  }

  .capability-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    min-height: 76px;
    border-top: 1px solid #eff0f1;
  }

  .capability-main {
    min-width: 0;
  }

  .capability-title {
    font-weight: 500;
    font-size: 14px;
    line-height: 22px;
  }

  .capability-description {
    margin-top: 4px;
    color: #646a73;
    font-size: 13px;
    line-height: 20px;
  }

  .access-notice {
    padding: 20px 24px;
    background: #f7faf9;
  }

  .notice-title {
    font-weight: 600;
    font-size: 15px;
    line-height: 23px;
  }

  .notice-description,
  .notice-footer {
    margin-top: 8px;
    color: #646a73;
    font-size: 14px;
    line-height: 22px;
  }

  .notice-footer {
    color: #1f2329;
    font-weight: 500;
  }
}
</style>
