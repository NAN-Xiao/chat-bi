<script lang="ts" setup>
import { ref, computed, onBeforeMount, onMounted, onUnmounted, watch } from 'vue'
import Menu from './Menu.vue'
import custom_small from '@/assets/svg/logo-custom_small.svg'
import ProjectSelector from './ProjectSelector.vue'
import Person from './Person.vue'
import ThemeSwitcher from './ThemeSwitcher.vue'
import AnalysisAssistantDock from '@/views/analysis-assistant/AnalysisAssistantDock.vue'
import elexDataLogoUrl from '@/assets/elex_data.png'
import elexDataGrayLogoUrl from '@/assets/elex_data_gray.png'
import icon_moments_categories_outlined from '@/assets/svg/icon_moments-categories_outlined.svg'
import icon_side_fold_outlined from '@/assets/svg/icon_side-fold_outlined.svg'
import icon_side_expand_outlined from '@/assets/svg/icon_side-expand_outlined.svg'
import { useRoute, useRouter } from 'vue-router'
import { useAppearanceStoreWithOut } from '@/stores/appearance'
import { useUserStore } from '@/stores/user'
import { emitWorkspaceContextChange, useEmitt } from '@/utils/useEmitt'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { isMobile } from '@/utils/utils'
import { PLATFORM_ADMIN_HOME } from '@/utils/navigation'
import { resolveBusinessDashboardLandingTarget } from '@/utils/dashboardLanding'
import { getInitialTheme, THEME_CHANGE_EVENT, type ThemeMode } from '@/utils/theme'
import {
  clearRememberedBusinessTenant,
  getRememberedBusinessTenant,
} from '@/utils/workspaceAdminContext'

const isPhone = computed(() => {
  return isMobile()
})
const router = useRouter()
const userStore = useUserStore()
const datasourceContext = useDatasourceContextStore()
const collapse = ref(false)
const collapseCopy = ref(false)
const analysisAssistantExpanded = ref(false)
const currentTheme = ref<ThemeMode>(getInitialTheme())
const appearanceStore = useAppearanceStoreWithOut()
let time: any
const handleThemeChange = (event: Event) => {
  const theme = (event as CustomEvent<ThemeMode>).detail
  if (theme === 'dark' || theme === 'light') {
    currentTheme.value = theme
  }
}
onUnmounted(() => {
  clearTimeout(time)
  window.removeEventListener(THEME_CHANGE_EVENT, handleThemeChange)
})
const loginBg = computed(() => {
  return appearanceStore.getLogin
})
const defaultLogoUrl = computed(() =>
  currentTheme.value === 'dark' ? elexDataGrayLogoUrl : elexDataLogoUrl
)
const handleCollapseChange = (val: any = true) => {
  collapseCopy.value = val
  clearTimeout(time)
  time = setTimeout(() => {
    collapse.value = val
  }, 100)
}
useEmitt({
  name: 'collapse-change',
  callback: handleCollapseChange,
})
useEmitt({
  name: 'analysis-assistant-toggle',
  callback: (expanded?: boolean) => {
    analysisAssistantExpanded.value =
      typeof expanded === 'boolean' ? expanded : !analysisAssistantExpanded.value
  },
})
watch(analysisAssistantExpanded, (expanded) => {
  useEmitt().emitter.emit('analysis-assistant-expanded', expanded)
})
const handleFoldExpand = () => {
  handleCollapseChange(!collapse.value)
}

const restoreBusinessTenant = async () => {
  const rememberedTenant = getRememberedBusinessTenant()
  if (!rememberedTenant?.id) return
  const tenantId = String(rememberedTenant.id)
  if (tenantId !== String(userStore.getTenantId || '')) {
    emitWorkspaceContextChange({ tenantId, phase: 'changing' })
    await userStore.switchTenant(tenantId)
    datasourceContext.clear(true)
    await datasourceContext.loadDatasources(true)
    useEmitt().emitter.emit('datasource-context-change', null)
    emitWorkspaceContextChange({ tenantId, phase: 'changed' })
  }
  clearRememberedBusinessTenant()
}

const exitPlatformWorkspaceDelegate = async () => {
  await userStore.exitPlatformWorkspaceDelegate()
  router.push(PLATFORM_ADMIN_HOME)
}

const toProjectList = async () => {
  await restoreBusinessTenant()
  router.push(await resolveBusinessDashboardLandingTarget(userStore))
}

const toChatIndex = async () => {
  await restoreBusinessTenant()
  router.push(await resolveBusinessDashboardLandingTarget(userStore))
}

const route = useRoute()
const showSysmenu = computed(() => {
  return route.path.includes('/system')
})
const isPlatformSaasAdminShell = computed(
  () => userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
)
const useTopNavigationShell = computed(() => !isPlatformSaasAdminShell.value)
onBeforeMount(() => {
  if (isPhone.value) {
    collapse.value = true
    collapseCopy.value = true
  }
})
onMounted(() => {
  currentTheme.value = getInitialTheme()
  window.addEventListener(THEME_CHANGE_EVENT, handleThemeChange)
})
</script>

<template>
  <div class="system-layout" :class="{ 'system-layout-top-nav': useTopNavigationShell }">
    <template v-if="useTopNavigationShell">
      <header class="top-nav-shell">
        <div class="top-nav-brand" @click="toChatIndex">
          <img
            v-if="loginBg"
            height="30"
            width="30"
            :src="loginBg"
            alt=""
          />
          <custom_small
            v-else-if="appearanceStore.themeColor !== 'default'"
          ></custom_small>
          <img
            v-else
            :src="defaultLogoUrl"
            height="30"
            width="30"
            alt=""
          />
          <span
            :title="showSysmenu ? $t('tenant.management') : appearanceStore.name"
            class="ellipsis"
          >
            {{ showSysmenu ? $t('tenant.management') : appearanceStore.name }}
          </span>
        </div>
        <Menu class="top-nav-menu" mode="horizontal"></Menu>
        <div class="top-nav-actions">
          <div
            v-if="showSysmenu"
            class="top-back-to-project"
            @click="toProjectList"
          >
            <el-icon size="18">
              <icon_moments_categories_outlined></icon_moments_categories_outlined>
            </el-icon>
            <span>{{ $t('project.return_to_project') }}</span>
          </div>
          <ProjectSelector
            v-if="!showSysmenu && !userStore.isPlatformWorkspaceDelegate"
            :collapse="false"
          ></ProjectSelector>
          <Person :collapse="true" :in-sysmenu="showSysmenu"></Person>
          <ThemeSwitcher :collapse="true"></ThemeSwitcher>
        </div>
      </header>
    </template>
    <div v-else class="left-side" :class="collapse && 'left-side-collapse'">
      <div class="side-header">
        <div class="side-brand">
          <template v-if="showSysmenu">
            <div class="sys-management" @click="toChatIndex">
              <img
                v-if="loginBg"
                :style="{ marginLeft: collapse ? '5px' : 0 }"
                height="30"
                width="30"
                :src="loginBg"
                :class="!collapse && 'collapse-icon'"
                alt=""
                @click="toChatIndex"
              />
              <custom_small
                v-else-if="appearanceStore.themeColor !== 'default'"
                :style="{ marginLeft: collapse ? '5px' : 0 }"
                :class="!collapse && 'collapse-icon'"
              ></custom_small>
              <img
                v-else
                :style="{ marginLeft: collapse ? '5px' : 0 }"
                :class="!collapse && 'collapse-icon'"
                :src="defaultLogoUrl"
                height="30"
                width="30"
                alt=""
              />
              <span v-if="!collapse">{{
                userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate
                  ? $t('common.platform_manage')
                  : $t('tenant.management')
              }}</span>
            </div>
          </template>
          <template v-else>
            <template v-if="appearanceStore.isBlue">
              <img
                v-if="loginBg && collapse"
                style="margin: 0 0 6px 5px; cursor: pointer"
                height="30"
                width="30"
                :src="loginBg"
                alt=""
                @click="toChatIndex"
              />
              <div v-else-if="loginBg && !collapse" class="default-zhishu" @click="toChatIndex">
                <img
                  height="30"
                  width="30"
                  :src="loginBg"
                  alt=""
                  class="collapse-icon"
                  @click="toChatIndex"
                />
                <span style="max-width: 150px" :title="appearanceStore.name" class="ellipsis">{{
                  appearanceStore.name
                }}</span>
              </div>
              <custom_small
                v-else-if="collapse"
                :style="{ marginLeft: collapse ? '5px' : 0, cursor: 'pointer' }"
                :class="!collapse && 'collapse-icon'"
                @click="toChatIndex"
              ></custom_small>

              <div v-else class="default-zhishu" @click="toChatIndex">
                <custom_small class="collapse-icon"></custom_small>
                <span style="max-width: 150px" :title="appearanceStore.name" class="ellipsis">{{
                  appearanceStore.name
                }}</span>
              </div>
            </template>
            <template v-else-if="appearanceStore.themeColor === 'custom'">
              <img
                v-if="loginBg && collapse"
                style="margin: 0 0 6px 5px; cursor: pointer"
                height="30"
                width="30"
                :src="loginBg"
                alt=""
                @click="toChatIndex"
              />
              <div v-else-if="loginBg && !collapse" class="default-zhishu" @click="toChatIndex">
                <img
                  height="30"
                  width="30"
                  :src="loginBg"
                  alt=""
                  class="collapse-icon"
                  @click="toChatIndex"
                />
                <span style="max-width: 150px" :title="appearanceStore.name" class="ellipsis">{{
                  appearanceStore.name
                }}</span>
              </div>
              <custom_small
                v-else-if="collapse"
                style="margin: 0 0 6px 5px; cursor: pointer"
                @click="toChatIndex"
              ></custom_small>
              <div v-else class="default-zhishu" @click="toChatIndex">
                <custom_small class="collapse-icon"></custom_small>
                <span style="max-width: 150px" :title="appearanceStore.name" class="ellipsis">{{
                  appearanceStore.name
                }}</span>
              </div>
            </template>
            <template v-else>
              <img
                v-if="loginBg && collapse"
                style="margin: 0 0 6px 5px; cursor: pointer"
                height="30"
                width="30"
                :src="loginBg"
                alt=""
                @click="toChatIndex"
              />
              <div v-else-if="loginBg && !collapse" class="default-zhishu" @click="toChatIndex">
                <img
                  height="30"
                  width="30"
                  :src="loginBg"
                  alt=""
                  class="collapse-icon"
                  @click="toChatIndex"
                />
                <span style="max-width: 150px" :title="appearanceStore.name" class="ellipsis">{{
                  appearanceStore.name
                }}</span>
              </div>
              <img
                v-else-if="collapse"
                style="margin: 0 0 6px 5px; cursor: pointer"
                :src="defaultLogoUrl"
                height="30"
                width="30"
                alt=""
                @click="toChatIndex"
              />
              <div v-else class="default-zhishu" @click="toChatIndex">
                <img
                  :src="defaultLogoUrl"
                  class="collapse-icon"
                  height="30"
                  width="30"
                  alt=""
                  @click="toChatIndex"
                />
                <span style="max-width: 150px" :title="appearanceStore.name" class="ellipsis">{{
                  appearanceStore.name
                }}</span>
              </div>
            </template>
          </template>
        </div>
        <button type="button" class="fold" @click.stop="handleFoldExpand">
          <el-icon size="18">
            <icon_side_expand_outlined v-if="collapse"></icon_side_expand_outlined>
            <icon_side_fold_outlined v-else></icon_side_fold_outlined>
          </el-icon>
        </button>
      </div>
      <ProjectSelector
        v-if="!showSysmenu && !userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate"
        :collapse="collapse"
      ></ProjectSelector>
      <Menu :collapse="collapseCopy"></Menu>
      <div class="bottom">
        <div
          v-if="showSysmenu && (!userStore.isSystemAdminUser || userStore.isPlatformWorkspaceDelegate)"
          class="back-to-project"
          :class="collapse && 'collapse'"
          @click="toProjectList"
        >
          <el-icon size="18">
            <icon_moments_categories_outlined></icon_moments_categories_outlined>
          </el-icon>
          {{
            collapse
              ? ''
              : $t('project.return_to_project')
          }}
        </div>
        <div class="side-account-area">
          <Person :collapse="collapse" :in-sysmenu="showSysmenu"></Person>
          <ThemeSwitcher :collapse="collapse"></ThemeSwitcher>
        </div>
      </div>
    </div>
    <div
      class="right-main"
      :class="{
        'right-side-collapse': collapse,
        'is-platform-delegate': userStore.isPlatformWorkspaceDelegate,
      }"
    >
      <div v-if="userStore.isPlatformWorkspaceDelegate" class="delegate-banner">
        <span>{{ $t('tenant.platform_delegate_banner', { name: userStore.getTenantName }) }}</span>
        <button type="button" @click="exitPlatformWorkspaceDelegate">
          {{ $t('tenant.return_to_platform') }}
        </button>
      </div>
      <div class="content">
        <router-view />
      </div>
    </div>
    <AnalysisAssistantDock
      v-if="!showSysmenu && !isPhone && (!userStore.isSystemAdminUser || userStore.isPlatformWorkspaceDelegate)"
      v-model:expanded="analysisAssistantExpanded"
    />
  </div>
</template>

<style lang="less" scoped>
.system-layout {
  width: 100vw;
  height: 100vh;
  background: var(--theme-shell-bg);
  display: flex;

  @keyframes rotate {
    0% {
      width: 240px;
    }
    100% {
      width: 64px;
    }
  }

  &.system-layout-top-nav {
    flex-direction: column;
    background: var(--workspace-shell-bg, var(--theme-shell-bg));

    .top-nav-shell {
      flex: 0 0 60px;
      width: 100%;
      min-width: 0;
      height: 60px;
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 0 16px;
      color: var(--workspace-text-primary, var(--theme-text-primary));
      background: var(--workspace-card-bg, var(--theme-panel-bg));
      border-bottom: 1px solid var(--workspace-border, var(--theme-shell-border));
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
      z-index: 9;
    }

    .top-nav-brand {
      flex: 0 0 auto;
      min-width: 190px;
      max-width: 230px;
      display: flex;
      align-items: center;
      gap: 10px;
      cursor: pointer;

      img,
      :deep(svg) {
        flex: 0 0 auto;
        width: 30px;
        height: 30px;
      }

      span {
        min-width: 0;
        font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
        font-size: 17px;
        font-weight: 700;
        line-height: 24px;
        letter-spacing: 0;
        color: var(--workspace-text-primary, var(--theme-text-primary));
      }
    }

    :deep(.workspace-selector) {
      width: 220px;
      height: 36px;
      margin-bottom: 0;
      background: var(--workspace-control-bg, var(--theme-control-bg));
      border-color: var(--workspace-border, var(--theme-shell-border));
      color: var(--workspace-text-secondary, var(--theme-text-secondary));

      .name {
        color: var(--workspace-text-primary, var(--theme-text-primary));
      }

      &:hover,
      &:focus {
        background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
        color: var(--workspace-text-primary, var(--theme-text-primary));
      }
    }

    .top-nav-menu {
      flex: 1 1 auto;
      min-width: 0;
      height: 60px;
      overflow: hidden;
    }

    .top-nav-actions {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 8px;
      height: 60px;

      :deep(.person),
      :deep(.theme-toggle.collapse) {
        color: var(--workspace-text-secondary, var(--theme-text-secondary));

        &:hover,
        &:focus {
          background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
          color: var(--workspace-text-primary, var(--theme-text-primary));
        }
      }
    }

    .top-back-to-project {
      height: 36px;
      padding: 0 12px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      gap: 6px;
      color: var(--workspace-text-secondary, var(--theme-text-secondary));
      cursor: pointer;
      font-size: 14px;
      line-height: 20px;
      white-space: nowrap;
      transition:
        background 160ms ease,
        color 160ms ease;

      &:hover,
      &:focus {
        background: var(--workspace-control-hover-bg, var(--theme-hover-bg));
        color: var(--workspace-text-primary, var(--theme-text-primary));
      }

      &:active {
        background: var(--workspace-active-bg, var(--theme-active-bg));
      }
    }

    .right-main {
      width: 100%;
      min-height: 0;
      max-height: calc(100vh - 60px);

      .content {
        height: 100%;
      }

      &.is-platform-delegate {
        max-height: calc(100vh - 60px);
      }
    }
  }

  .left-side {
    width: 240px;
    height: 100%;
    padding: 16px;
    position: relative;
    min-width: 240px;
    color: var(--theme-sidebar-text);
    background: var(--theme-sidebar-bg);
    border-right: 1px solid var(--theme-sidebar-border);
    --layout-fold-color: var(--theme-sidebar-text-secondary);
    --layout-fold-color-hover: var(--theme-sidebar-emphasis-text);
    --theme-text-primary: var(--theme-sidebar-text);
    --theme-text-secondary: var(--theme-sidebar-text-secondary);
    --theme-text-tertiary: var(--theme-sidebar-text-tertiary);
    --theme-control-bg: var(--theme-sidebar-control-bg);
    --theme-control-hover-bg: var(--theme-sidebar-control-hover-bg);
    --theme-hover-bg: var(--theme-sidebar-hover-bg);
    --theme-active-bg: var(--theme-sidebar-active-soft-bg);
    --theme-shell-border: var(--theme-sidebar-border);
    --theme-card-shadow: none;

    .side-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 12px;

      .side-brand {
        flex: 1;
        min-width: 0;
      }

      .default-zhishu,
      .sys-management {
        margin-bottom: 0;
      }

      .fold {
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 40px;
        width: 40px;
        height: 32px;
        padding: 0;
        border: none;
        color: var(--layout-fold-color);
        background: transparent;
        cursor: pointer;

        :deep(.ed-icon) {
          color: inherit;
        }

        :deep(svg) {
          width: 18px;
          height: 18px;
          color: inherit;
          opacity: 0.9;
        }

        :deep(svg [stroke]) {
          stroke: currentColor;
        }

        &:hover,
        &:focus {
          background: transparent;
          color: var(--layout-fold-color-hover);

          :deep(svg) {
            color: inherit;
            opacity: 1;
          }
        }

        &:active {
          background: transparent;
        }
      }
    }

    .side-account-area {
      display: flex;
      flex-direction: column;
      align-items: stretch;
      gap: 8px;
      width: 100%;
    }

    .default-zhishu {
      display: flex;
      align-items: center;
      font-size: 16px;
      line-height: 22px;
      color: var(--theme-sidebar-emphasis-text);
      cursor: pointer;
      margin-bottom: 12px;

      > span {
        font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
        font-size: 17px;
        font-weight: 700;
        line-height: 24px;
        letter-spacing: 0;
        color: var(--theme-sidebar-emphasis-text, var(--theme-sidebar-text));
      }

      .collapse-icon {
        margin-right: 10px;
      }
    }

    .sys-management {
      display: flex;
      align-items: center;
      font-weight: 500;
      font-size: 16px;
      line-height: 22px;
      color: var(--theme-sidebar-emphasis-text);
      cursor: pointer;
      margin-bottom: 12px;
      .collapse-icon {
        margin-right: 8px;
      }
    }

    .bottom {
      position: absolute;
      bottom: 20px;
      left: 16px;
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;
      width: calc(100% - 32px);
      .back-to-project {
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 8px;
        height: 40px;
        cursor: pointer;
        color: var(--theme-sidebar-text-secondary);
        transition:
          background 160ms ease,
          color 160ms ease,
          border-color 160ms ease;

        &:not(.collapse) {
          background: var(--theme-control-bg);
          border: 1px solid var(--theme-shell-border);
        }
        &:hover {
          background-color: var(--theme-hover-bg);
          color: var(--theme-sidebar-emphasis-text);
        }
        &:active {
          background-color: var(--theme-active-bg);
        }
        .ed-icon {
          margin-right: 4.95px;
        }
      }

      .back-to-project + .side-account-area {
        margin-top: 12px;
      }
    }

    &.left-side-collapse {
      width: 64px;
      min-width: 64px;
      padding: 16px 12px;
      // animation: rotate 0.1s ease-in-out;

      .side-header {
        flex-direction: column;
        gap: 6px;
      }

      .ed-menu--collapse {
        --ed-menu-icon-width: 32px;
        width: 40px;
      }

      .bottom {
        left: 50%;
        width: 40px;
        transform: translateX(-50%);
        .ed-icon {
          margin-right: 0;
        }
      }

      .side-account-area {
        align-items: center;
        width: 40px;
        gap: 8px;

        .default-avatar {
          margin: 0;
        }
      }
    }
  }

  .right-main {
    flex: 1;
    min-width: 0;
    width: auto;
    padding: 0;
    max-height: 100vh;

    &.right-side-collapse {
      width: auto;
    }

    .content {
      width: 100%;
      height: 100%;
      padding: 18px 24px;
      background-color: var(--workspace-shell-bg, var(--theme-panel-bg));
      color: var(--workspace-text-primary, var(--theme-text-primary));
      border-radius: 0;
      border: 0;
      box-shadow: none;
      color-scheme: light;
      overflow-x: auto;
      overflow-y: auto;
      scrollbar-width: thin;
      scrollbar-color: #b8c4d6 #edf2f8;

      &:has(.no-padding) {
        padding: 0;
      }
    }

    &.is-platform-delegate {
      .content {
        height: calc(100% - 36px);
      }
    }

    .delegate-banner {
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 24px;
      border-bottom: 1px solid var(--theme-shell-border, #d9dcdf);
      background: #ecfdf5;
      color: #065f46;
      font-size: 13px;
      line-height: 20px;

      span {
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }

      button {
        flex: 0 0 auto;
        border: none;
        background: transparent;
        color: #047857;
        font-size: 13px;
        cursor: pointer;
        padding: 0;

        &:hover {
          color: #065f46;
          text-decoration: underline;
        }
      }
    }

    .content::-webkit-scrollbar {
      width: 10px;
      height: 10px;
    }

    .content::-webkit-scrollbar-track {
      background: #edf2f8;
      border-radius: 999px;
    }

    .content::-webkit-scrollbar-thumb {
      background: #b8c4d6;
      border-radius: 999px;
      border: 2px solid #edf2f8;
    }

    .content::-webkit-scrollbar-thumb:hover {
      background: #94a3b8;
    }
  }
}
</style>
