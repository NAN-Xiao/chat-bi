<script lang="ts" setup>
import { computed } from 'vue'
import { ElMenu } from 'element-plus-secondary'
import { useRoute } from 'vue-router'
import MenuItem from './MenuItem.vue'

defineProps({
  collapse: Boolean,
})

const route = useRoute()
const menuList = computed(() => route.matched[0]?.children || [])

const activeIndex = computed(() => {
  const arr = route.path.split('/')
  return arr[arr.length - 1]
})
</script>

<template>
  <el-menu :default-active="activeIndex" class="ed-menu-vertical" :collapse="collapse">
    <MenuItem v-for="menu in menuList" :key="menu.path" :menu="menu"></MenuItem>
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
      background-color: #1CBA901A;
    }
  }
}
</style>
