<script lang="ts" setup>
import { computed } from 'vue'
import { ElMenu } from 'element-plus-secondary'
import { useRoute, useRouter } from 'vue-router'
import MenuItem from './MenuItem.vue'
import { useUserStore } from '@/stores/user'
// import { routes } from '@/router'
const router = useRouter()
const userStore = useUserStore()
defineProps({
  collapse: Boolean,
})

const route = useRoute()
// const menuList = computed(() => route.matched[0]?.children || [])
const activeMenu = computed(() => route.path)
/* const activeIndex = computed(() => {
  const arr = route.path.split('/')
  return arr[arr.length - 1]
}) */
const showSysmenu = computed(() => {
  return route.path.includes('/system')
})

const formatRoute = (arr: any, parentPath = '') => {
  return arr.map((element: any) => {
    let children: any = []
    const path = `${parentPath ? parentPath + '/' : ''}${element.path}`
    if (element.children?.length) {
      children = formatRoute(element.children, path)
    }
    return {
      ...element,
      path,
      children,
    }
  })
}

const filterSystemRoutes = (arr: any[]): any[] => {
  return arr
    .map((item: any) => {
      const children = item.children?.length ? filterSystemRoutes(item.children) : []
      if (userStore.isSystemAdminUser && !userStore.isPlatformWorkspaceDelegate) {
        if (item.meta?.hideForPlatformAdmin) {
          return null
        }
        if (item.meta?.tenantBusiness && !item.meta?.platformOperation) {
          return null
        }
        if (item.meta?.platformOperation || item.meta?.platformOnly || children.length) {
          return { ...item, children }
        }
        return null
      }
      if (item.meta?.platformOnly) {
        return null
      }
      if (!userStore.getTenantId) {
        return null
      }
      if (item.meta?.tenantAdminOnly && !userStore.isTenantAdminUser) {
        return null
      }
      if (!item.meta?.tenantBusiness && !item.meta?.tenantAdminOnly && !children.length) {
        return null
      }
      return { ...item, children }
    })
    .filter(Boolean)
}

const mainMenuOrder = (path: string) => {
  if (path.includes('/chat')) return 10
  if (path.includes('/dashboard') && !path.includes('/dashboard-store')) return 20
  if (path.includes('/access')) return 30
  if (path.includes('/account')) return 35
  if (path.includes('/custom-agent')) return 40
  if (path.includes('/dashboard-store')) return 50
  return 100
}

const tenantOptionalMainRoutes = ['/access', '/account']
const isTenantOptionalMainRoute = (path: string) =>
  tenantOptionalMainRoutes.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))

const routerList = computed(() => {
  if (showSysmenu.value) {
    const [sysRouter] = formatRoute(
      router.getRoutes().filter((route: any) => route?.name === 'system')
    )
    return filterSystemRoutes(sysRouter.children || [])
  }
  if (userStore.isSystemAdminUser) {
    return []
  }
  const hasTenantContext = !!userStore.getTenantId
  const list = router.getRoutes().filter((route) => {
    if (!hasTenantContext && !isTenantOptionalMainRoute(route.path)) {
      return false
    }
    return (
      !route.meta?.hidden &&
      !route.path.includes('embeddedPage') &&
      !route.path.includes('assistant') &&
      !route.path.includes('embeddedPage') &&
      !route.path.includes('canvas') &&
      !route.path.includes('member') &&
      !route.path.includes('professional') &&
      !route.path.includes('401') &&
      !route.path.includes('training') &&
      !route.path.includes('prompt') &&
      !route.path.includes('permission') &&
      !route.path.includes('embeddedCommon') &&
      !route.path.includes('preview') &&
      !route.path.includes('audit') &&
      route.path !== '/login' &&
      route.path !== '/admin-login' &&
      route.path !== '/chatPreview' &&
      !route.path.includes('/system') &&
      !route.redirect &&
      route.path !== '/:pathMatch(.*)*' &&
      !route.path.includes('dsTable')
    )
  })

  return list.sort((prev: any, next: any) => mainMenuOrder(prev.path) - mainMenuOrder(next.path))
})
</script>

<template>
  <el-menu :default-active="activeMenu" class="el-menu-demo ed-menu-vertical" :collapse="collapse">
    <MenuItem v-for="menu in routerList" :key="menu.path" :menu="menu"></MenuItem>
  </el-menu>
</template>

<style lang="less">
.ed-menu-vertical {
  --ed-menu-item-height: 40px;
  --ed-menu-bg-color: transparent;
  --ed-menu-base-level-padding: 4px;
  border-right: none;

  .ed-menu-item {
    height: 40px !important;
    border-radius: 8px !important;
    margin-bottom: 4px;
    color: var(--theme-sidebar-text-secondary, var(--theme-text-secondary));
    transition:
      background 160ms ease,
      color 160ms ease,
      box-shadow 160ms ease;

    &:hover,
    &:focus {
      background: var(--theme-hover-bg) !important;
      color: var(--theme-sidebar-emphasis-text, var(--theme-text-primary));
    }

    &.is-active {
      background:
        linear-gradient(90deg, rgba(255, 255, 255, 0.16), transparent),
        var(--theme-sidebar-active-bg, var(--ed-color-primary, #2f6bff)) !important;
      border-radius: 8px;
      color: var(--theme-sidebar-active-text, #ffffff) !important;
      font-weight: 600;
      box-shadow: var(--theme-sidebar-active-shadow, 0 10px 22px rgba(47, 107, 255, 0.24));
    }
  }

  .ed-sub-menu .ed-sub-menu__title {
    border-radius: 8px;
    margin-bottom: 4px;
    color: var(--theme-sidebar-text-secondary, var(--theme-text-secondary));
    transition:
      background 160ms ease,
      color 160ms ease,
      box-shadow 160ms ease;

    &:hover,
    &:focus {
      background: var(--theme-hover-bg) !important;
      color: var(--theme-sidebar-emphasis-text, var(--theme-text-primary));
    }
  }

  .ed-sub-menu.is-active:not(.is-opened) {
    .ed-sub-menu__title {
      background:
        linear-gradient(90deg, rgba(255, 255, 255, 0.16), transparent),
        var(--theme-sidebar-active-bg, var(--ed-color-primary, #2f6bff)) !important;
      color: var(--theme-sidebar-active-text, #ffffff) !important;
      font-weight: 600;
      box-shadow: var(--theme-sidebar-active-shadow, 0 10px 22px rgba(47, 107, 255, 0.24));
    }
  }

  .ed-sub-menu.is-active.is-opened {
    .ed-sub-menu__title {
      color: var(--theme-sidebar-text-secondary, var(--theme-text-secondary)) !important;
      font-weight: 600;
    }
  }

  .ed-sub-menu .ed-icon {
    margin-right: 8px;
  }

  .ed-menu-item,
  .ed-sub-menu__title {
    .ed-icon,
    svg {
      color: inherit !important;
    }

    .zhishu-menu-line-icon {
      color: inherit !important;

      path,
      circle,
      rect,
      ellipse,
      polyline,
      line {
        fill: none !important;
        stroke: currentColor !important;
        stroke-width: 1.55 !important;
        stroke-linecap: round !important;
        stroke-linejoin: round !important;
      }
    }

    svg:not(.zhishu-menu-line-icon) path {
      fill: currentColor !important;
      stroke: currentColor !important;
    }
  }

  &:not(.ed-menu--collapse) {
    .ed-sub-menu .ed-menu {
      padding: 2px 0 4px 0;
    }

    .ed-menu-item.menu-level-1 {
      position: relative;
      margin-left: 20px;
      width: calc(100% - 20px);
      padding-left: 22px !important;
      color: var(--theme-sidebar-text-secondary, var(--theme-text-secondary));

      .ed-icon {
        width: 0;
        margin-right: 0;
        opacity: 0;
      }

      &::before {
        content: '';
        position: absolute;
        left: 8px;
        top: 50%;
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--theme-text-tertiary);
        transform: translateY(-50%);
        opacity: 0.72;
      }

      &:hover,
      &:focus {
        color: var(--theme-sidebar-emphasis-text, var(--theme-text-primary));

        &::before {
          background: var(--theme-sidebar-emphasis-text, var(--theme-text-secondary));
          opacity: 1;
        }
      }

      &.is-active {
        color: var(--theme-sidebar-active-text, #ffffff) !important;

        &::before {
          background: var(--theme-sidebar-active-text, #ffffff);
          opacity: 1;
        }
      }
    }
  }
}
.ed-popper.is-light:has(.ed-menu--popup) {
  border: 1px solid var(--workspace-border, var(--theme-shell-border));
  border-radius: 8px;
  box-shadow: var(--workspace-card-shadow, 0 8px 24px rgba(17, 37, 73, 0.1));
  background: var(--workspace-card-bg, var(--theme-panel-bg));
  overflow: hidden;
}
.ed-menu--popup {
  padding: 8px;
  background: var(--workspace-card-bg, var(--theme-panel-bg));

  .ed-menu-item {
    padding: 9px 16px;
    height: 40px !important;
    border-radius: 8px;
    &.is-active {
      background-color: var(--workspace-primary-soft-bg, var(--theme-primary-soft-bg)) !important;
      color: var(--ed-color-primary, #2f6bff) !important;
      font-weight: 500;
    }
  }
}
.ed-sub-menu {
  .subTitleMenu {
    display: none;
  }
}

.ed-menu--popup-container .subTitleMenu {
  color: var(--theme-text-secondary) !important;
  pointer-events: none;
}
</style>
