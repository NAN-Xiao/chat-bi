<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()

const isPlatformAdmin = computed(() => userStore.isSystemAdminUser)
const isCollabAdmin = computed(() => userStore.isCollabAdminUser)
const isTenantAdmin = computed(() => userStore.isTenantAdminUser)
const isTenantOwner = computed(() => userStore.isTenantOwnerUser)
const isManager = computed(() => userStore.isSystemManagerUser)
const hasTenantContext = computed(() => !!userStore.getTenantId)

const accessLevel = computed(() => {
  if (isPlatformAdmin.value) {
    return {
      label: t('access.platform_admin'),
      type: 'success',
      description: t('access.platform_admin_description'),
    }
  }
  if (isCollabAdmin.value) {
    return {
      label: t('access.collab_admin'),
      type: 'success',
      description: t('access.collab_admin_description'),
    }
  }
  if (!hasTenantContext.value) {
    return {
      label: t('access.normal_user'),
      type: 'info',
      description: t('access.normal_user_description'),
    }
  }
  if (isTenantAdmin.value) {
    return {
      label: isTenantOwner.value ? t('access.tenant_owner') : t('access.tenant_admin'),
      type: 'success',
      description: isTenantOwner.value
        ? t('access.tenant_owner_description')
        : t('access.tenant_admin_description'),
    }
  }
  return {
    label: t('access.tenant_member'),
    type: 'warning',
    description: t('access.tenant_member_description'),
  }
})

const capabilityList = computed(() => {
  const businessStatus = isPlatformAdmin.value ? t('access.restricted') : t('access.policy_open')
  const noTenantBusinessStatus = hasTenantContext.value ? businessStatus : t('access.restricted')
  const dataStatus = isManager.value && !isPlatformAdmin.value ? t('access.full') : t('access.limited')
  const adminStatus = isManager.value ? t('access.policy_open') : t('access.restricted')

  return [
    {
      title: t('access.qa'),
      status: noTenantBusinessStatus,
      description: t('access.qa_description'),
    },
    {
      title: t('access.dashboard'),
      status: noTenantBusinessStatus,
      description: t('access.dashboard_description'),
    },
    {
      title: t('access.analysis_assistant'),
      status: noTenantBusinessStatus,
      description: t('access.analysis_assistant_description'),
    },
    {
      title: t('access.data_scope'),
      status: hasTenantContext.value ? dataStatus : t('access.restricted'),
      description: hasTenantContext.value
        ? t('access.data_scope_description')
        : t('access.no_tenant_data_scope_description'),
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
