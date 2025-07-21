<script lang="ts" setup>
import { computed } from 'vue'
import { ElMenu } from 'element-plus-secondary'
import { useRoute, useRouter } from 'vue-router'
import MenuItem from './MenuItem.vue'
import { useUserStore } from '@/stores/user'
const userStore = useUserStore()
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

const routerList = computed(() => {
  if (showSysmenu.value) {
    return router.getRoutes().filter((route) => route.path.includes('/system') && !route.redirect)
  }
  const list = router.getRoutes().filter((route) => {
    return (
      !route.path.includes('assistant') &&
      !route.path.includes('canvas') &&
      !route.path.includes('member') &&
      !route.path.includes('permission') &&
      !route.path.includes('preview') &&
      route.path !== '/login' &&
      !route.path.includes('/system') &&
      ((route.path.includes('set') && userStore.isSpaceAdmin) || !route.redirect) &&
      route.path !== '/:pathMatch(.*)*' &&
      !route.path.includes('dsTable')
    )
  })

  return list
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
    border-radius: 6px !important;
    &.is-active {
      background-color: #fff !important;
      border-radius: 6px;
    }
  }

  .ed-sub-menu .ed-sub-menu__title:hover {
    border-radius: 6px;
  }

  .ed-sub-menu.is-active {
    .ed-sub-menu__title {
      color: #1cba90 !important;
    }
  }
}
</style>
