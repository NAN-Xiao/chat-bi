<script lang="ts" setup>
import { ref, computed, onBeforeMount, onMounted, onUnmounted } from 'vue'
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
import { useEmitt } from '@/utils/useEmitt'
import { isMobile } from '@/utils/utils'
import { getInitialTheme, THEME_CHANGE_EVENT, type ThemeMode } from '@/utils/theme'

const isPhone = computed(() => {
  return isMobile()
})
const router = useRouter()
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
const handleFoldExpand = () => {
  handleCollapseChange(!collapse.value)
}

const toProjectList = () => {
  router.push('/chat/index')
}

const toChatIndex = () => {
  router.push('/chat/index')
}

const toUserIndex = () => {
  router.push('/system/user')
}
const route = useRoute()
const showSysmenu = computed(() => {
  return route.path.includes('/system')
})
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
  <div class="system-layout">
    <div class="left-side" :class="collapse && 'left-side-collapse'">
      <div class="side-header">
        <div class="side-brand">
          <template v-if="showSysmenu">
            <div class="sys-management" @click="toUserIndex">
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
              <span v-if="!collapse">{{ $t('training.system_management') }}</span>
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
              <div v-else-if="loginBg && !collapse" class="default-sqlbot">
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
                :style="{ marginLeft: collapse ? '5px' : 0 }"
                :class="!collapse && 'collapse-icon'"
              ></custom_small>

              <div v-else class="default-sqlbot">
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
              <div v-else-if="loginBg && !collapse" class="default-sqlbot">
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
              <div v-else class="default-sqlbot">
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
              <div v-else-if="loginBg && !collapse" class="default-sqlbot">
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
              <div v-else class="default-sqlbot">
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
      <ProjectSelector v-if="!showSysmenu" :collapse="collapse"></ProjectSelector>
      <Menu :collapse="collapseCopy"></Menu>
      <div class="bottom">
        <div
          v-if="showSysmenu"
          class="back-to-project"
          :class="collapse && 'collapse'"
          @click="toProjectList"
        >
          <el-icon size="18">
            <icon_moments_categories_outlined></icon_moments_categories_outlined>
          </el-icon>
          {{ collapse ? '' : $t('project.return_to_project') }}
        </div>
        <div class="personal-info">
          <Person :collapse="collapse" :in-sysmenu="showSysmenu"></Person>
          <ThemeSwitcher :collapse="collapse"></ThemeSwitcher>
        </div>
      </div>
    </div>
    <div class="right-main" :class="collapse && 'right-side-collapse'">
      <div class="content">
        <router-view />
      </div>
    </div>
    <AnalysisAssistantDock
      v-if="!showSysmenu && !isPhone"
      v-model:expanded="analysisAssistantExpanded"
    />
  </div>
</template>

<style lang="less" scoped>
.system-layout {
  width: 100vw;
  height: 100vh;
  background:
    linear-gradient(135deg, var(--theme-shell-gradient-a), transparent 30%),
    linear-gradient(315deg, var(--theme-shell-gradient-b), transparent 32%),
    var(--theme-shell-bg);
  display: flex;

  @keyframes rotate {
    0% {
      width: 240px;
    }
    100% {
      width: 64px;
    }
  }

  .left-side {
    width: 240px;
    height: 100%;
    padding: 16px;
    position: relative;
    min-width: 240px;
    color: var(--theme-sidebar-text);
    background:
      linear-gradient(180deg, rgba(47, 107, 255, 0.16), transparent 34%),
      var(--theme-sidebar-bg);
    border-right: 1px solid var(--theme-sidebar-border);
    --layout-fold-bg-hover: var(--theme-sidebar-hover-bg);
    --layout-fold-bg-active: rgba(47, 107, 255, 0.34);
    --layout-fold-color: var(--theme-sidebar-text-secondary);
    --layout-fold-color-hover: var(--theme-sidebar-active-text);
    --theme-text-primary: var(--theme-sidebar-text);
    --theme-text-secondary: var(--theme-sidebar-text-secondary);
    --theme-text-tertiary: rgba(159, 176, 204, 0.72);
    --theme-control-bg: rgba(255, 255, 255, 0.08);
    --theme-control-hover-bg: rgba(255, 255, 255, 0.12);
    --theme-hover-bg: var(--theme-sidebar-hover-bg);
    --theme-active-bg: rgba(47, 107, 255, 0.34);
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

      .default-sqlbot,
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
        border-radius: 6px;
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
          background: var(--layout-fold-bg-hover);
          color: var(--layout-fold-color-hover);

          :deep(svg) {
            color: inherit;
            opacity: 1;
          }
        }

        &:active {
          background: var(--layout-fold-bg-active);
        }
      }
    }

    .default-sqlbot {
      display: flex;
      align-items: center;
      font-size: 16px;
      line-height: 22px;
      color: var(--theme-sidebar-active-text);
      cursor: pointer;
      margin-bottom: 12px;

      > span {
        font-family: 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
        font-size: 17px;
        font-weight: 700;
        line-height: 24px;
        letter-spacing: 0;
        color: var(--theme-sidebar-active-text, #ffffff);
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
      color: var(--theme-sidebar-active-text);
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
          color: var(--theme-sidebar-active-text);
        }
        &:active {
          background-color: var(--theme-active-bg);
        }
        .ed-icon {
          margin-right: 4.95px;
        }
      }

      .personal-info {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        margin-top: 16px;
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
        left: 12px;
        width: calc(100% - 24px);
        .ed-icon {
          margin-right: 0;
        }
      }

      .personal-info {
        flex-wrap: wrap;
        justify-content: center;
        gap: 8px;

        .default-avatar {
          margin: 0 0 26px 4px;
        }
      }
    }
  }

  .right-main {
    flex: 1;
    min-width: 0;
    width: auto;
    padding: 14px 14px 14px 0;
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
      border-radius: 8px;
      border: 1px solid var(--workspace-border, var(--theme-shell-border));
      box-shadow: var(--workspace-card-shadow, var(--theme-card-shadow));
      overflow-x: auto;

      &:has(.no-padding) {
        padding: 0;
      }
    }
  }
}
</style>
