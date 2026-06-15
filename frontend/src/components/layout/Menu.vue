<script lang="ts" setup>
import { computed } from 'vue'
import { ElMenu } from 'element-plus-secondary'
import { useRoute, useRouter } from 'vue-router'
import MenuItem from './MenuItem.vue'
// import { routes } from '@/router'
const router = useRouter()
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

const routerList = computed(() => {
  if (showSysmenu.value) {
    const [sysRouter] = formatRoute(
      router.getRoutes().filter((route: any) => route?.name === 'system')
    )
    return sysRouter.children
  }
  const list = router.getRoutes().filter((route) => {
    return (
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

  return list.sort((prev: any, next: any) => {
    const prevIsAccess = prev.path.includes('/access')
    const nextIsAccess = next.path.includes('/access')
    const prevIsStore = prev.path.includes('/dashboard-store')
    const nextIsStore = next.path.includes('/dashboard-store')
    if (prevIsAccess && nextIsStore) return -1
    if (prevIsStore && nextIsAccess) return 1
    if (prevIsAccess === nextIsAccess) {
      if (prevIsStore === nextIsStore) return 0
      return prevIsStore ? 1 : -1
    }
    return prevIsAccess ? 1 : -1
  })
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
    margin-bottom: 2px;
    color: var(--theme-text-primary);

    &:hover,
    &:focus {
      background: var(--theme-hover-bg) !important;
    }

    &.is-active {
      background-color: var(--theme-panel-bg) !important;
      border-radius: 8px;
      color: var(--ed-color-primary, #2563eb) !important;
      font-weight: 500;
      box-shadow: var(--theme-control-shadow);
    }
  }

  .ed-sub-menu .ed-sub-menu__title {
    border-radius: 8px;

    &:hover,
    &:focus {
      background: var(--theme-hover-bg) !important;
    }
  }

  .ed-sub-menu.is-active:not(.is-opened) {
    .ed-sub-menu__title {
      background-color: var(--theme-panel-bg) !important;
      color: var(--ed-color-primary, #2563eb) !important;
      font-weight: 500;
      box-shadow: var(--theme-control-shadow);
    }
  }

  .ed-sub-menu.is-active.is-opened {
    .ed-sub-menu__title {
      color: var(--ed-color-primary, #2563eb) !important;
      font-weight: 500;
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

    svg path {
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
      color: var(--theme-text-secondary);

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
        color: var(--theme-text-primary);

        &::before {
          background: var(--theme-text-secondary);
          opacity: 1;
        }
      }

      &.is-active {
        color: var(--ed-color-primary, #2563eb) !important;

        &::before {
          background: var(--ed-color-primary, #2563eb);
          opacity: 1;
        }
      }
    }
  }
}
.ed-popper.is-light:has(.ed-menu--popup) {
  border: 1px solid var(--theme-shell-border);
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(31, 35, 41, 0.1);
  background: var(--theme-shell-bg);
  overflow: hidden;
}
.ed-menu--popup {
  padding: 8px;
  background: var(--theme-shell-bg);

  .ed-menu-item {
    padding: 9px 16px;
    height: 40px !important;
    border-radius: 8px;
    &.is-active {
      background-color: var(--theme-panel-bg) !important;
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
