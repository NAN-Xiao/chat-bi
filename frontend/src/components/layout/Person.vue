<script lang="ts" setup>
import { ref, computed, onMounted } from 'vue'
import Default_avatar_custom from '@/assets/img/Default-avatar.svg'
import icon_admin_outlined from '@/assets/svg/icon_admin_outlined.svg'
import icon_key_outlined from '@/assets/svg/icon-key_outlined.svg'
import icon_api_key from '@/assets/svg/icon-api_key.svg'
import icon_translate_outlined from '@/assets/svg/icon_translate_outlined.svg'
import icon_logout_outlined from '@/assets/svg/icon_logout_outlined.svg'
import icon_right_outlined from '@/assets/svg/icon_right_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_member_outlined from '@/assets/svg/icon_member_outlined.svg'
import icon_add_outlined from '@/assets/svg/icon_add_outlined.svg'
import icon_user from '@/assets/svg/icon_user.svg'
import { useI18n } from 'vue-i18n'
import PwdForm from './PwdForm.vue'
import Apikey from './Apikey.vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { dashboardStoreWithOut } from '@/stores/dashboard/dashboard'
import { userApi } from '@/api/auth'
import { type TenantInfo } from '@/api/tenant'
import { toLoginPage } from '@/utils/utils'
import { useCache } from '@/utils/useCache'
import { emitWorkspaceContextChange, useEmitt } from '@/utils/useEmitt'
import { ElMessage } from 'element-plus-secondary'
import { PLATFORM_ADMIN_HOME, resolveManagementHome } from '@/utils/navigation'
import { rememberBusinessTenantBeforeAdmin } from '@/utils/workspaceAdminContext'

const { wsCache } = useCache()
const router = useRouter()
const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const dashboardStore = dashboardStoreWithOut()
const pwdFormRef = ref()
const { t, locale } = useI18n()
defineProps({
  collapse: { type: [Boolean], required: true },
  inSysmenu: { type: [Boolean], required: true },
})

const name = computed(() => userStore.getName)
const account = computed(() => userStore.getAccount)
const currentLanguage = computed(() => userStore.getLanguage)
const isPlatformAdmin = computed(() => userStore.isSystemAdminUser)
const isPlatformWorkspaceDelegate = computed(() => userStore.isPlatformWorkspaceDelegate)
const isLocalUser = computed(() => !userStore.getOrigin)
const tenantList = computed(() => userStore.getTenants)
const adminTenantList = computed(() =>
  tenantList.value.filter((tenant) => canManageTenant(tenant.role))
)
const hasAdminTenant = computed(() => adminTenantList.value.length > 0)
const showAdminWorkspaceEntry = computed(
  () => !isPlatformAdmin.value && hasAdminTenant.value
)
const showWorkspaceApplicationEntry = computed(
  () => !isPlatformAdmin.value && !userStore.hasActiveWorkspace
)

const isClient = computed(() => {
  return !!wsCache.get('zhishu-platform-client')
})

const platFlag = computed(() => {
  const platformInfo = userStore.getPlatformInfo
  return platformInfo?.origin || 0
})
const dialogVisible = ref(false)
const apikeyDialogVisible = ref(false)
const languageList = computed(() => [
  {
    name: 'English',
    value: 'en',
  },
  {
    name: '简体中文',
    value: 'zh-CN',
  },
  {
    name: '繁體中文',
    value: 'zh-TW',
  },
  {
    name: '한국인',
    value: 'ko-KR',
  },
])
const popoverRef = ref()
const workspacePopoverVisible = ref(false)
const languagePopoverVisible = ref(false)

const tenantDisplayId = (tenant?: Partial<TenantInfo> | null) =>
  String(tenant?.public_id || '')

const formatTenantRole = (role: string) => {
  const key = `common.tenant_role_${role || 'member'}`
  const label = t(key)
  return label === key ? role || t('common.tenant_role_member') : label
}

const canManageTenant = (role?: string) => {
  return ['owner', 'admin'].includes(String(role || '').trim().toLowerCase())
}

const toSystem = () => {
  popoverRef.value?.hide?.()
  if (isPlatformWorkspaceDelegate.value) {
    userStore.exitPlatformWorkspaceDelegate().finally(() => {
      router.push(PLATFORM_ADMIN_HOME)
    })
    return
  }
  router.push(resolveManagementHome(userStore))
}

const toWorkspaceApplication = () => {
  popoverRef.value?.hide?.()
  router.push('/account/workspace-applications')
}

const toAccess = () => {
  popoverRef.value?.hide?.()
  router.push('/access/index')
}

const currentBusinessTenant = () => ({
  id: userStore.getTenantId,
  public_id: userStore.getTenantPublicId,
  name: userStore.getTenantName,
  role: userStore.getTenantRole,
})

const enterTenantAdmin = async (tenant?: TenantInfo) => {
  const tenantId = String(tenant?.id || userStore.getTenantId || '')
  if (!tenantId) {
    return
  }
  rememberBusinessTenantBeforeAdmin(currentBusinessTenant())
  try {
    if (tenantId !== String(userStore.getTenantId || '')) {
      emitWorkspaceContextChange({ tenantId, phase: 'changing' })
      await userStore.switchTenant(tenantId)
      datasourceContext.clear(true)
      await datasourceContext.loadDatasources(true)
      dashboardStore.canvasDataInit()
      useEmitt().emitter.emit('datasource-context-change', null)
      emitWorkspaceContextChange({ tenantId, phase: 'changed' })
      ElMessage.success(t('common.switch_success'))
    }
    popoverRef.value?.hide?.()
    router.push(resolveManagementHome(userStore))
  } catch (error) {
    emitWorkspaceContextChange({ tenantId: userStore.getTenantId, phase: 'changed' })
    throw error
  }
}

const loadTenants = async () => {
  try {
    await userStore.loadTenants()
  } catch (error) {
    console.warn('Failed to load tenant list', error)
  }
}

const changeLanguage = (lang: string) => {
  locale.value = lang
  userStore.setLanguage(lang)
  const param = {
    language: lang,
  }
  userApi.language(param).catch((error) => {
    console.warn('Failed to save language preference', error)
  })
}

const openPwd = () => {
  dialogVisible.value = true
}
const closePwd = () => {
  dialogVisible.value = false
}
const openApikey = () => {
  apikeyDialogVisible.value = true
}
const savePwdHandler = () => {
  pwdFormRef.value?.submit()
}
const logout = async () => {
  if (!(await userStore.logout())) {
    router.push(toLoginPage(router?.currentRoute?.value?.fullPath || ''))
    // router.push('/login')
  }
}

onMounted(() => {
  loadTenants()
})
</script>

<template>
  <el-popover
    ref="popoverRef"
    trigger="click"
    popper-class="system-person"
    :placement="collapse ? 'right' : 'top-start'"
  >
    <template #reference>
      <button class="person" :title="name" :class="collapse && 'collapse'">
        <el-icon size="32">
          <Default_avatar_custom></Default_avatar_custom>
        </el-icon>
        <span v-if="!collapse" class="name ellipsis">{{ name }}</span>
      </button></template
    >
    <div class="popover">
      <div class="popover-content">
        <div class="info">
          <el-icon class="avatar-custom" size="40">
            <Default_avatar_custom></Default_avatar_custom>
          </el-icon>
          <div :title="name" class="top ellipsis">{{ name }}</div>
          <div :title="account" class="bottom ellipsis">{{ account }}</div>
        </div>
        <div
          v-if="isPlatformAdmin && !isPlatformWorkspaceDelegate && !inSysmenu"
          class="popover-item"
          @click="toSystem"
        >
          <el-icon style="color: var(--theme-text-secondary)" size="16">
            <icon_admin_outlined></icon_admin_outlined>
          </el-icon>
          <div class="datasource-name">{{ $t('common.platform_manage') }}</div>
        </div>
        <el-popover
          v-if="showAdminWorkspaceEntry"
          v-model:visible="workspacePopoverVisible"
          :teleported="false"
          :show-after="0"
          :hide-after="0"
          popper-class="system-tenant"
          placement="right"
        >
          <template #reference>
            <div class="popover-item has-submenu" :class="workspacePopoverVisible && 'is-submenu-open'">
              <el-icon size="16">
                <icon_member_outlined></icon_member_outlined>
              </el-icon>
              <div class="datasource-name">{{ $t('tenant.my_workspaces') }}</div>
              <el-icon class="right" size="16">
                <icon_right_outlined></icon_right_outlined>
              </el-icon>
            </div>
          </template>
          <div class="tenant-popover workspace-admin-popover">
            <div class="tenant-title">{{ $t('tenant.workspace_list') }}</div>
            <el-scrollbar max-height="300px">
              <div
                v-for="tenant in adminTenantList"
                :key="tenant.id"
                class="tenant-option"
                @click="enterTenantAdmin(tenant)"
              >
                <el-icon size="16">
                  <icon_member_outlined></icon_member_outlined>
                </el-icon>
                <div class="tenant-option-main">
                  <div :title="tenant.name || String(tenant.id || '')" class="tenant-name ellipsis">
                    {{ tenant.name || tenant.id }}
                  </div>
                  <div class="tenant-meta ellipsis">
                    {{ $t('tenant.tenant_id') }} {{ tenantDisplayId(tenant) }} · {{ formatTenantRole(tenant.role) }}
                  </div>
                </div>
              </div>
            </el-scrollbar>
          </div>
        </el-popover>
        <div
          v-if="showWorkspaceApplicationEntry"
          class="popover-item"
          @click="toWorkspaceApplication"
        >
          <el-icon size="16">
            <icon_add_outlined></icon_add_outlined>
          </el-icon>
          <div class="datasource-name">{{ $t('tenant.apply_workspace') }}</div>
        </div>
        <div class="popover-item" @click="toAccess">
          <el-icon size="16">
            <icon_user></icon_user>
          </el-icon>
          <div class="datasource-name">{{ $t('access.my_permissions') }}</div>
        </div>
        <div v-if="isLocalUser && !platFlag" class="popover-item" @click="openPwd">
          <el-icon size="16">
            <icon_key_outlined></icon_key_outlined>
          </el-icon>
          <div class="datasource-name">{{ $t('user.change_password') }}</div>
        </div>
        <div v-if="!isPlatformAdmin" class="popover-item" @click="openApikey">
          <el-icon size="16">
            <icon_api_key></icon_api_key>
          </el-icon>
          <div class="datasource-name">API Key</div>
        </div>
        <el-popover
          v-model:visible="languagePopoverVisible"
          :teleported="false"
          :show-after="0"
          :hide-after="0"
          popper-class="system-language"
          placement="right"
        >
          <template #reference>
            <div class="popover-item has-submenu" :class="languagePopoverVisible && 'is-submenu-open'">
              <el-icon size="16">
                <icon_translate_outlined></icon_translate_outlined>
              </el-icon>
              <div class="datasource-name">{{ $t('common.language') }}</div>
              <el-icon class="right" size="16">
                <icon_right_outlined></icon_right_outlined>
              </el-icon>
            </div>
          </template>
          <div class="language-popover">
            <div
              v-for="ele in languageList"
              :key="ele.name"
              class="popover-item_language"
              :class="currentLanguage === ele.value && 'isActive'"
              @click="changeLanguage(ele.value)"
            >
              <div class="language-name">{{ ele.name }}</div>
              <el-icon size="16" class="done">
                <icon_done_outlined></icon_done_outlined>
              </el-icon>
            </div>
          </div>
        </el-popover>
        <div style="height: 4px; width: 100%"></div>
        <div v-if="!isClient" class="popover-item mr4" @click="logout">
          <el-icon size="16">
            <icon_logout_outlined></icon_logout_outlined>
          </el-icon>
          <div class="datasource-name">{{ $t('common.logout') }}</div>
        </div>
      </div>
    </div>
  </el-popover>

  <el-dialog v-model="dialogVisible" :title="t('user.upgrade_pwd.title')" width="600">
    <pwd-form v-if="dialogVisible" ref="pwdFormRef" @pwd-saved="closePwd" />
    <template #footer>
      <div class="dialog-footer">
        <el-button secondary @click="closePwd">{{ t('common.cancel') }}</el-button>
        <el-button type="primary" @click="savePwdHandler">{{ t('common.save') }}</el-button>
      </div>
    </template>
  </el-dialog>
  <el-dialog
    v-model="apikeyDialogVisible"
    class="workspace-light-dialog api-key-dialog"
    title="API Key"
    width="840"
  >
    <apikey v-if="apikeyDialogVisible" ref="apikeyRef" />
  </el-dialog>
</template>

<style lang="less" scoped>
.person {
  padding: 0 8px;
  display: flex;
  align-items: center;
  cursor: pointer;
  width: 100%;
  height: 40px;
  border: 1px solid transparent;
  border-radius: 8px;
  background-color: transparent;
  position: relative;
  color: var(--theme-text-secondary);
  transition:
    background 160ms ease,
    border-color 160ms ease,
    color 160ms ease;

  &.collapse {
    width: 40px;
    min-width: 40px;
    padding: 0;
    margin-left: 0;
    justify-content: center;
    position: relative;
    margin-top: 0;
    margin-bottom: 0;

    .ed-icon {
      display: inline-grid;
      place-items: center;
    }

    .ed-icon svg {
      display: block;
    }

    .default-avatar {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
    }
  }

  .name {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    margin-left: 8px;
    max-width: calc(100% - 48px);
    color: var(--theme-text-primary);
  }

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100%;
    height: 100%;
    border-radius: 8px;
  }

  &:hover,
  &:focus {
    border-color: var(--theme-shell-border);
    background: var(--theme-control-bg);
    color: var(--theme-sidebar-emphasis-text, var(--theme-text-primary));

    &::after {
      background: transparent;
    }
  }

  &:active {
    background: var(--theme-active-bg);

    &::after {
      background: transparent;
    }
  }
}

</style>

<style lang="less">
.system-person.system-person {
  padding: 0;
  width: 240px !important;
  box-shadow: var(--theme-card-shadow);
  border: 1px solid var(--theme-shell-border);
  background: var(--theme-panel-bg);
  color: var(--theme-text-primary);
  position: relative;
  border-radius: 10px;

  .popover {
    .info {
      height: 62px;
      padding: 8px;
      margin-bottom: 4px;
      border-bottom: 1px solid var(--theme-shell-border);

      .avatar-custom {
        float: left;
        margin: 3px 8px 0 7px;
      }

      .top {
        float: left;
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
        width: calc(100% - 60px);
      }

      .bottom {
        float: left;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        width: calc(100% - 60px);
        color: var(--theme-text-secondary);
      }
    }
    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 8px;
      padding-right: 4px;
      position: relative;
      cursor: pointer;
      margin: 0 4px;
      border-radius: 8px;
      color: var(--theme-text-primary);
      &:hover {
        background-color: var(--theme-hover-bg);
      }
      &:active {
        background-color: var(--theme-active-bg);
      }
      .datasource-name {
        margin-left: 8px;
        min-width: 0;
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      &.mr4 {
        margin: 4px;
        border-top: 1px solid var(--theme-shell-border);
        padding-top: 4px;
        height: 36px;
      }

      .right {
        margin-left: auto;
        opacity: 0;
      }

      &:hover,
      &.is-submenu-open {
        .right {
          opacity: 1;
        }
      }
    }
  }
}

.system-tenant.system-tenant {
  padding: 4px;
  width: 280px !important;
  box-shadow: var(--theme-card-shadow);
  border: 1px solid var(--theme-shell-border);
  background: var(--theme-panel-bg);
  color: var(--theme-text-primary);

  .tenant-title {
    padding: 4px 8px 6px;
    font-size: 12px;
    line-height: 18px;
    color: var(--theme-text-secondary);
  }

  .tenant-option {
    min-height: 44px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;

    &:hover {
      background: var(--theme-hover-bg);
    }

    &.isActive {
      color: var(--ed-color-primary);

      .done {
        display: block;
      }
    }

    .tenant-option-main {
      min-width: 0;
      flex: 1;
    }

    .tenant-name {
      font-size: 14px;
      line-height: 20px;
      font-weight: 500;
    }

    .tenant-meta {
      font-size: 12px;
      line-height: 16px;
      color: var(--theme-text-secondary);
    }

    .done {
      margin-left: auto;
      display: none;
    }
  }
}

.system-language.system-language {
  padding: 4px 4px 2px 4px;
  width: 240px !important;
  box-shadow: var(--theme-card-shadow);
  border: 1px solid var(--theme-shell-border);
  background: var(--theme-panel-bg);
  color: var(--theme-text-primary);

  .language-popover {
    .popover-item_language {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 8px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 6px;
      cursor: pointer;
      &:not(.empty):hover {
        background: var(--theme-hover-bg);
      }

      .language-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        margin-bottom: 2px;
      }

      .done {
        margin-left: auto;
        display: none;
      }

      &.isActive {
        color: var(--ed-color-primary);

        .done {
          display: block;
        }
      }
    }
  }
}
</style>
