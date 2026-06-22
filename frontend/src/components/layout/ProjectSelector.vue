<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import icon_expand_down_filled from '@/assets/svg/icon_expand-down_filled.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import icon_workspace_outlined from '@/assets/svg/icon_moments-categories_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { highlightKeyword } from '@/utils/xss'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { useUserStore } from '@/stores/user'
import { useEmitt } from '@/utils/useEmitt'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard'
import { type TenantInfo } from '@/api/tenant'

const datasourceContext = useDatasourceContextStore()
const userStore = useUserStore()
const dashboardStore = dashboardStoreWithOut()
const { t } = useI18n()
defineProps({
  collapse: { type: [Boolean], required: true },
})

const router = useRouter()
const popoverRef = ref()
const workspaceKeywords = ref('')
const workspaceSwitchingId = ref('')
const tenantList = computed(() => userStore.getTenants)
const currentWorkspace = computed(() => ({
  id: userStore.getTenantId,
  public_id: userStore.getTenantPublicId,
  name: userStore.getTenantName,
  role: userStore.getTenantRole,
}))
const currentWorkspaceName = computed(
  () => currentWorkspace.value.name || t('tenant.no_current_workspace')
)
const tenantDisplayId = (tenant?: Partial<TenantInfo> | null) =>
  String(tenant?.public_id || '')
const isSystemDefaultWorkspace = (tenant?: Partial<TenantInfo> | null) =>
  Boolean(tenant?.is_system_default) || tenant?.name === '示例工作空间'
const workspaceListWithSearch = computed(() => {
  const keyword = workspaceKeywords.value.trim().toLowerCase()
  const list = tenantList.value.filter((tenant) => !isSystemDefaultWorkspace(tenant))
  if (!keyword) return list
  return list.filter((tenant) =>
    `${tenant.name || ''} ${tenantDisplayId(tenant)}`.toLowerCase().includes(keyword)
  )
})
const systemDefaultWorkspace = computed(() =>
  tenantList.value.find((tenant) => isSystemDefaultWorkspace(tenant))
)
const systemDefaultWorkspaceVisible = computed(() => {
  const tenant = systemDefaultWorkspace.value
  if (!tenant) return false
  const keyword = workspaceKeywords.value.trim().toLowerCase()
  if (!keyword) return true
  return `${tenant.name || ''} ${tenantDisplayId(tenant)}`.toLowerCase().includes(keyword)
})
const formatKeywords = (item: string) => {
  // Use XSS-safe highlight function
  return highlightKeyword(item, workspaceKeywords.value, 'isSearch')
}

const emit = defineEmits(['selectProject'])

const formatTenantRole = (role?: string) => {
  const key = `common.tenant_role_${role || 'member'}`
  const label = t(key)
  return label === key ? role || t('common.tenant_role_member') : label
}

const handleWorkspaceChange = async (tenant: TenantInfo) => {
  const tenantId = String(tenant.id || '')
  if (!tenantId || tenantId === String(userStore.getTenantId || '')) {
    popoverRef.value?.hide?.()
    return
  }
  workspaceSwitchingId.value = tenantId
  try {
    await userStore.switchTenant(tenantId)
    datasourceContext.clear(true)
    await datasourceContext.loadDatasources(true)
    dashboardStore.canvasDataInit()
    useEmitt().emitter.emit('datasource-context-change', null)
    emit('selectProject', null)
    ElMessage.success(t('common.switch_success'))
    popoverRef.value?.hide?.()
    router.push('/chat/index')
  } finally {
    workspaceSwitchingId.value = ''
  }
}

const toWorkspaceApplication = () => {
  popoverRef.value?.hide?.()
  router.push('/account/workspace-applications')
}

const refreshWorkspaces = async () => {
  await userStore.loadTenants(true)
  if (userStore.hasActiveWorkspace) {
    await datasourceContext.loadDatasources(true)
  } else {
    datasourceContext.clear(false)
  }
}

onMounted(async () => {
  await refreshWorkspaces()
})
</script>

<template>
  <el-popover
    ref="popoverRef"
    trigger="click"
    popper-class="system-workspace-selector"
    :placement="collapse ? 'right' : 'bottom'"
    @show="refreshWorkspaces"
  >
    <template #reference>
      <button
        class="workspace-selector"
        :class="collapse && 'collapse'"
        :title="currentWorkspaceName"
      >
        <el-icon size="18">
          <icon_workspace_outlined></icon_workspace_outlined>
        </el-icon>
        <span v-if="!collapse" :title="currentWorkspaceName" class="name ellipsis">{{
          currentWorkspaceName
        }}</span>
        <el-icon v-if="!collapse" style="transform: scale(0.5)" class="expand" size="24">
          <icon_expand_down_filled></icon_expand_down_filled>
        </el-icon></button
    ></template>
    <div class="popover">
      <el-input
        v-model="workspaceKeywords"
        clearable
        style="width: 100%; margin-right: 12px"
        :placeholder="$t('tenant.search_placeholder')"
      >
        <template #prefix>
          <el-icon>
            <icon_searchOutline_outlined class="svg-icon" />
          </el-icon>
        </template>
      </el-input>
      <div class="popover-content">
        <el-scrollbar max-height="400px">
          <div
            v-for="tenant in workspaceListWithSearch"
            :key="tenant.id"
            class="popover-item"
            :class="String(userStore.getTenantId) === String(tenant.id) && 'isActive'"
            @click="handleWorkspaceChange(tenant)"
          >
            <el-icon size="16">
              <icon_workspace_outlined></icon_workspace_outlined>
            </el-icon>
            <div class="workspace-option-main">
              <div
                :title="tenant.name || String(tenant.id || '')"
                class="workspace-name ellipsis"
                v-html="formatKeywords(tenant.name || String(tenant.id || ''))"
              ></div>
              <div class="workspace-meta ellipsis">
                {{ $t('tenant.tenant_id') }} {{ tenantDisplayId(tenant) }} · {{ formatTenantRole(tenant.role) }}
              </div>
            </div>
            <el-icon
              v-if="workspaceSwitchingId !== String(tenant.id)"
              size="16"
              class="done"
            >
              <icon_done_outlined></icon_done_outlined>
            </el-icon>
          </div>
        </el-scrollbar>

        <div
          v-if="!workspaceListWithSearch.length && !systemDefaultWorkspaceVisible"
          class="workspace-empty"
        >
          <div>{{ $t('tenant.no_joined_workspaces') }}</div>
        </div>

        <div
          v-if="systemDefaultWorkspaceVisible && systemDefaultWorkspace"
          class="workspace-quick-actions workspace-system-default"
        >
          <button
            type="button"
            class="workspace-action-item"
            :class="
              String(userStore.getTenantId) === String(systemDefaultWorkspace.id) && 'isActive'
            "
            @click="handleWorkspaceChange(systemDefaultWorkspace)"
          >
            <el-icon size="16">
              <icon_workspace_outlined></icon_workspace_outlined>
            </el-icon>
            <span
              class="workspace-action-text"
              v-html="formatKeywords(systemDefaultWorkspace.name || $t('common.default_tenant'))"
            ></span>
            <el-icon
              v-if="String(userStore.getTenantId) === String(systemDefaultWorkspace.id)"
              size="16"
              class="action-done"
            >
              <icon_done_outlined></icon_done_outlined>
            </el-icon>
          </button>
        </div>

        <div class="workspace-quick-actions">
          <button type="button" class="workspace-action-item" @click="toWorkspaceApplication">
            <el-icon size="16">
              <icon_add_outlined></icon_add_outlined>
            </el-icon>
            <span class="workspace-action-text">{{ $t('tenant.apply_or_join_workspace') }}</span>
          </button>
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style lang="less" scoped>
.workspace-selector {
  background: var(--theme-control-bg);
  border-radius: 8px;
  border: 1px solid var(--theme-shell-border);
  padding: 0 12px;
  display: flex;
  align-items: center;
  cursor: pointer;
  width: 208px;
  height: 40px;
  margin-bottom: 12px;
  color: var(--theme-text-secondary);
  transition:
    background 160ms ease,
    border-color 160ms ease,
    color 160ms ease;

  &.collapse {
    width: 40px;
    background: none;
    border: none;
  }

  .name {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    margin-left: 8px;
    max-width: 120px;
    color: var(--theme-text-primary);
  }

  .expand {
    margin-left: auto;
  }

  :deep(.ed-icon),
  :deep(svg) {
    color: inherit;
  }

  :deep(svg [fill]) {
    fill: currentColor;
  }

  :deep(svg [stroke]) {
    stroke: currentColor;
  }

  &:hover {
    background: var(--theme-hover-bg);
    border-color: var(--theme-shell-border);
    color: var(--theme-sidebar-emphasis-text, var(--theme-text-primary));
  }

  &:active {
    background: var(--theme-active-bg);
  }
}
</style>

<style lang="less">
.system-workspace-selector.system-workspace-selector {
  --ed-popover-border-radius: 6px;
  padding: 4px 0;
  width: 280px !important;
  box-shadow: var(--theme-card-shadow);
  border: 1px solid var(--theme-shell-border);
  background: var(--theme-panel-bg);
  color: var(--theme-text-primary);
  .ed-input {
    background: var(--theme-panel-bg);
    .ed-input__wrapper {
      box-shadow: none;
      background: var(--theme-panel-bg);
    }

    .ed-input__inner {
      color: var(--theme-text-primary);
    }

    border-bottom: 1px solid var(--theme-shell-border);
  }

  .popover {
    .popover-content {
      padding: 4px;
    }
    .popover-item {
      min-height: 44px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 6px;
      cursor: pointer;
      &:not(.empty):hover {
        background: var(--theme-hover-bg);
      }

      &.empty {
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        color: var(--theme-text-secondary);
        cursor: default;
      }

      .workspace-option-main {
        flex: 1;
        min-width: 0;
      }

      .workspace-name {
        font-weight: 400;
        font-size: 14px;
        line-height: 20px;
        max-width: 190px;
      }

      .workspace-meta {
        margin-top: 1px;
        max-width: 190px;
        font-size: 12px;
        line-height: 16px;
        color: var(--theme-text-secondary);
      }

      .done {
        margin-left: auto;
        display: none;
      }

      .isSearch {
        color: var(--ed-color-primary);
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }

    .workspace-empty {
      min-height: 44px;
      display: flex;
      justify-content: center;
      padding: 10px 12px;
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      color: var(--theme-text-secondary);
    }

    .workspace-quick-actions {
      padding: 4px 0 0;
      margin-top: 4px;
      border-top: 1px solid var(--theme-shell-border);

      .workspace-action-item {
        width: 100%;
        min-height: 44px;
        display: flex;
        align-items: center;
        justify-content: flex-start;
        gap: 8px;
        padding: 10px 8px 10px 12px;
        margin: 0;
        border: 0;
        border-radius: 6px;
        background: transparent;
        color: var(--ed-color-primary);
        cursor: pointer;
        font-family: inherit;
        font-weight: 400;
        font-size: 14px;
        line-height: 20px;
        text-align: left;
        box-sizing: border-box;

        &:hover {
          background: var(--theme-hover-bg);
        }
      }

      .workspace-action-text {
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      .action-done {
        flex: 0 0 auto;
        margin-left: auto;
      }
    }
  }
}
</style>
