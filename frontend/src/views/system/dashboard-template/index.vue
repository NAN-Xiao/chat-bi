<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_into_item_outlined from '@/assets/svg/icon_into-item_outlined.svg'
import iconDashboardUrl from '@/assets/svg/dashboard.svg?url'
import EmptyBackground from '@/views/dashboard/common/EmptyBackground.vue'
import { dashboardApi } from '@/api/dashboard'
import { useUserStore } from '@/stores/user'

const { t } = useI18n()
const userStore = useUserStore()

const loading = ref(false)
const usingId = ref('')
const keyword = ref('')
const list = ref<any[]>([])

const canUseInWorkspace = computed(() => userStore.isPlatformWorkspaceDelegate)
const filteredList = computed(() => {
  const value = keyword.value.trim().toLowerCase()
  if (!value) return list.value
  return list.value.filter((item) =>
    [item.name, item.remark, item.content_id].some((field) =>
      String(field || '').toLowerCase().includes(value)
    )
  )
})

const loadList = async () => {
  loading.value = true
  try {
    const res = await dashboardApi.platform_template_admin_list({
      requestOptions: { silent: true },
    })
    list.value = Array.isArray(res) ? res : []
  } finally {
    loading.value = false
  }
}

const sourceText = (item: any) => {
  const remark = String(item.remark || '')
  const tenantMatch = remark.match(/source_tenant_id=([^;]+)/)
  const dashboardMatch = remark.match(/source_dashboard_id=([^;]+)/)
  if (!tenantMatch && !dashboardMatch) return '-'
  return [tenantMatch ? `WS ${tenantMatch[1]}` : '', dashboardMatch ? dashboardMatch[1] : '']
    .filter(Boolean)
    .join(' / ')
}

const copyToWorkspace = async (item: any) => {
  if (!canUseInWorkspace.value || usingId.value) return
  const confirmed = await ElMessageBox.confirm(
    t('dashboard.platform_template_use_confirm', { name: item.name }),
    {
      confirmButtonText: t('common.confirm'),
      cancelButtonText: t('common.cancel'),
      type: 'warning',
      autofocus: false,
      showClose: false,
    }
  ).catch(() => false)
  if (!confirmed) return
  usingId.value = item.id
  try {
    await dashboardApi.platform_template_copy_to_workspace({ template_id: item.id })
    ElMessage.success(t('dashboard.platform_template_use_success'))
  } finally {
    usingId.value = ''
  }
}

onMounted(() => {
  loadList()
})
</script>

<template>
  <div v-loading="loading" class="platform-dashboard-template">
    <div class="page-toolbar">
      <div class="title-wrap">
        <div class="title">{{ t('dashboard.platform_template_library') }}</div>
        <div class="subtitle">{{ t('dashboard.platform_template_library_desc') }}</div>
      </div>
      <div class="toolbar-actions">
        <el-input
          v-model="keyword"
          clearable
          :placeholder="t('dashboard.platform_template_search')"
          @keyup.enter="loadList"
        >
          <template #prefix>
            <el-icon>
              <icon_searchOutline_outlined class="svg-icon" />
            </el-icon>
          </template>
        </el-input>
        <el-button secondary @click="loadList">{{ t('common.refresh') }}</el-button>
      </div>
    </div>

    <EmptyBackground
      v-if="!filteredList.length"
      :description="t('dashboard.platform_template_empty')"
      class="template-empty"
      img-type="noneWhite"
    />

    <div v-else class="template-grid">
      <div v-for="item in filteredList" :key="item.id" class="template-card">
        <div class="preview">
          <img :src="iconDashboardUrl" width="60" height="60" />
          <div class="preview-title">{{ t('dashboard.platform_template_mark') }}</div>
        </div>
        <div class="card-body">
          <div class="name ellipsis" :title="item.name">{{ item.name }}</div>
          <div class="meta-row">
            <span>{{ t('dashboard.platform_template_source') }}</span>
            <strong class="ellipsis" :title="sourceText(item)">{{ sourceText(item) }}</strong>
          </div>
          <div class="meta-row">
            <span>{{ t('dashboard.store_datasource') }}</span>
            <strong>{{ item.datasource || '-' }}</strong>
          </div>
        </div>
        <div class="card-actions">
          <el-button
            type="primary"
            :disabled="!canUseInWorkspace"
            :loading="usingId === item.id"
            @click="copyToWorkspace(item)"
          >
            <template #icon>
              <icon_into_item_outlined />
            </template>
            {{ t('dashboard.platform_template_use') }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.platform-dashboard-template {
  height: 100%;
  padding: 0 0 16px;
}

.page-toolbar {
  min-height: 44px;
  margin-bottom: 16px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.title {
  color: var(--workspace-text-primary, var(--theme-text-primary, #1f2329));
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
}

.subtitle {
  margin-top: 4px;
  color: var(--workspace-text-secondary, #667085);
  font-size: 13px;
  line-height: 20px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 12px;

  .ed-input {
    width: 260px;
  }
}

.template-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 300px));
  gap: 18px;
  align-items: start;
}

.template-card {
  border: 1px solid var(--workspace-border, #e2eaf4);
  border-radius: 8px;
  background: var(--workspace-card-bg, #fff);
  overflow: hidden;
  box-shadow: 0 12px 28px rgba(24, 46, 86, 0.07);
}

.preview {
  height: 164px;
  border-bottom: 1px solid var(--workspace-border-soft, #eff4fa);
  background: linear-gradient(180deg, #fbfdff 0%, #f3f7fc 100%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--workspace-text-secondary, #66758f);
}

.preview-title {
  margin-top: 8px;
  font-size: 13px;
  line-height: 20px;
}

.card-body {
  padding: 14px;
}

.name {
  color: var(--workspace-text-primary, #1b2a41);
  font-size: 15px;
  line-height: 24px;
  font-weight: 600;
}

.meta-row {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  align-items: center;
  color: var(--workspace-text-secondary, #66758f);
  font-size: 12px;
  line-height: 18px;

  span {
    flex: 0 0 auto;
  }

  strong {
    min-width: 0;
    color: var(--workspace-text-primary, #1b2a41);
    font-weight: 500;
  }
}

.card-actions {
  padding: 0 14px 14px;

  .ed-button {
    width: 100%;
  }
}

.template-empty {
  padding-top: 180px;
}
</style>
