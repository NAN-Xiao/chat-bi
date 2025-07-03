<script lang="ts" setup>
import { ref, computed } from 'vue'
import icon_expand_down_filled from '@/assets/svg/icon_expand-down_filled.svg'
import icon_moments_categories_outlined from '@/assets/svg/icon_moments-categories_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'

defineProps({
  collapse: { type: [Boolean], required: true },
})

const name = ref('默认工作空间')
const currentWorkspace = ref('默认工作空间')
const defaultDatasourceList = ref([
  {
    name: '默认工作空间',
  },
] as any[])
const workspaceKeywords = ref('')
const defaultWorkspaceListWithSearch = computed(() => {
  if (!workspaceKeywords.value) return defaultDatasourceList.value
  return defaultDatasourceList.value.filter((ele) =>
    ele.name.toLowerCase().includes(workspaceKeywords.value.toLowerCase())
  )
})
const formatKeywords = (item: string) => {
  if (!workspaceKeywords.value) return item
  return item.replaceAll(
    workspaceKeywords.value,
    `<span class="isSearch">${workspaceKeywords.value}</span>`
  )
}

const emit = defineEmits(['selectWorkspace'])

const handleDefaultWorkspaceChange = (item: any) => {
  currentWorkspace.value = item.name
  emit('selectWorkspace', item)
}
</script>

<template>
  <el-popover popper-class="system-workspace" :placement="collapse ? 'right' : 'bottom'">
    <template #reference>
      <button class="workspace" :class="collapse && 'collapse'">
        <el-icon size="16">
          <icon_moments_categories_outlined></icon_moments_categories_outlined>
        </el-icon>
        <span v-if="!collapse" class="name">{{ name }}</span>
        <el-icon v-if="!collapse" style="transform: scale(0.5)" class="expand" size="24">
          <icon_expand_down_filled></icon_expand_down_filled>
        </el-icon></button
    ></template>
    <div class="popover">
      <el-input
        v-model="workspaceKeywords"
        clearable
        style="width: 100%; margin-right: 12px"
        placeholder="通过名称搜索"
      >
        <template #prefix>
          <el-icon>
            <icon_searchOutline_outlined class="svg-icon" />
          </el-icon>
        </template>
      </el-input>
      <div class="popover-content">
        <div
          v-for="ele in defaultWorkspaceListWithSearch"
          :key="ele.name"
          class="popover-item"
          :class="currentWorkspace === ele.name && 'isActive'"
          @click="handleDefaultWorkspaceChange(ele)"
        >
          <el-icon size="16">
            <icon_moments_categories_outlined></icon_moments_categories_outlined>
          </el-icon>
          <div class="datasource-name" v-html="formatKeywords(ele.name)"></div>
          <el-icon size="16" class="done">
            <icon_done_outlined></icon_done_outlined>
          </el-icon>
        </div>
        <div v-if="!defaultWorkspaceListWithSearch.length" class="popover-item empty">
          没有找到相关结果
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style lang="less" scoped>
.workspace {
  background: #1f23290a;
  border-radius: 6px;
  border: 1px solid #1f23291a;
  padding: 0 12px;
  display: flex;
  align-items: center;
  cursor: pointer;
  width: 208px;
  height: 40px;
  margin-bottom: 12px;

  &.collapse {
    width: 40px;
  }

  .name {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    margin-left: 8px;
  }

  .expand {
    margin-left: auto;
  }

  &:hover {
    background: #1f23291a;
  }

  &:active {
    background: #1f232926;
  }
}
</style>

<style lang="less">
.system-workspace.system-workspace {
  padding: 4px 0;
  width: 280px !important;
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border: 1px solid #dee0e3;
  .ed-input {
    .ed-input__wrapper {
      box-shadow: none;
    }

    border-bottom: 1px solid #1f232926;
  }

  .popover {
    .popover-content {
      padding: 4px;
    }
    .popover-item {
      height: 32px;
      display: flex;
      align-items: center;
      padding-left: 12px;
      padding-right: 8px;
      margin-bottom: 2px;
      position: relative;
      border-radius: 4px;
      cursor: pointer;
      &:not(.empty):hover {
        background: #1f23291a;
      }

      &.empty {
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        color: #8f959e;
        cursor: default;
      }

      .datasource-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
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
  }
}
</style>
