<script lang="ts" setup>
import { computed } from 'vue'
import { ElMenu } from 'element-plus-secondary'
import { useRoute, useRouter } from 'vue-router'
import MenuItem from './MenuItem.vue'

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
  return router.getRoutes().filter((route) => {
    return (
      !route.path.includes('canvas') &&
      !route.path.includes('preview') &&
      route.path !== '/login' &&
      !route.path.includes('/system') &&
      !route.redirect &&
      route.path !== '/:pathMatch(.*)*' &&
      !route.path.includes('dsTable')
    )
  })
})
</script>

<template>
  <el-menu :default-active="activeMenu" class="el-menu-demo ed-menu-vertical" :collapse="collapse">
    <MenuItem v-for="menu in routerList" :key="menu.path" :menu="menu"></MenuItem>
  </el-menu>
</template>

<style lang="less" scoped>
.ed-menu-vertical {
  --ed-menu-item-height: 40px;
  --ed-menu-bg-color: transparent;
  --ed-menu-base-level-padding: 4px;
  border-right: none;
  .ed-menu-item {
    height: 40px;
    border-radius: 6px;
    &.is-active.is-active.is-active {
      background-color: #1cba901a;
    }
  }
}
</style>
