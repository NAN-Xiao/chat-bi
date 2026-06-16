<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue'
import icon_expand_down_filled from '@/assets/svg/icon_expand-down_filled.svg'
import icon_moments_categories_outlined from '@/assets/svg/icon_moments-categories_outlined.svg'
import icon_done_outlined from '@/assets/svg/icon_done_outlined.svg'
import icon_searchOutline_outlined from '@/assets/svg/icon_search-outline_outlined.svg'
import { ElMessage } from 'element-plus-secondary'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { highlightKeyword } from '@/utils/xss'
import { useDatasourceContextStore } from '@/stores/datasourceContext'
import { useEmitt } from '@/utils/useEmitt'

const datasourceContext = useDatasourceContextStore()
const { t } = useI18n()
defineProps({
  collapse: { type: [Boolean], required: true },
})

const router = useRouter()
const currentProject = computed(() => ({
  id: datasourceContext.datasourceId,
  name: datasourceContext.datasourceName,
}))
const defaultDatasourceList = computed(() => datasourceContext.datasources)
const projectKeywords = ref('')
const defaultProjectListWithSearch = computed(() => {
  if (!projectKeywords.value) return defaultDatasourceList.value
  return defaultDatasourceList.value.filter((ele) =>
    ele.name.toLowerCase().includes(projectKeywords.value.toLowerCase())
  )
})
const formatKeywords = (item: string) => {
  // Use XSS-safe highlight function
  return highlightKeyword(item, projectKeywords.value, 'isSearch')
}

const emit = defineEmits(['selectProject'])

const handleDefaultProjectChange = (item: any) => {
  if (
    currentProject.value?.id &&
    item.id.toString() === currentProject.value.id.toString()
  ) {
    return
  }
  datasourceContext.setDatasource(
    Number(item.id),
    item.name,
    item.type || '',
    item.type_name || '',
    item.project_role || '',
    item.can_create_dashboard === true,
    item.can_manage_dashboard === true,
    item.can_manage_project === true
  )
  ElMessage.success(t('common.switch_success'))
  router.push('/chat/index')
  useEmitt().emitter.emit('datasource-context-change', item)
  emit('selectProject', item)
}

onMounted(async () => {
  await datasourceContext.loadDatasources()
})
</script>

<template>
  <el-popover
    trigger="click"
    popper-class="system-project"
    :placement="collapse ? 'right' : 'bottom'"
  >
    <template #reference>
      <button class="project-selector" :class="collapse && 'collapse'">
        <el-icon size="18">
          <icon_moments_categories_outlined></icon_moments_categories_outlined>
        </el-icon>
        <span v-if="!collapse" :title="currentProject?.name || ''" class="name ellipsis">{{
          currentProject?.name || ''
        }}</span>
        <el-icon v-if="!collapse" style="transform: scale(0.5)" class="expand" size="24">
          <icon_expand_down_filled></icon_expand_down_filled>
        </el-icon></button
    ></template>
    <div class="popover">
      <el-input
        v-model="projectKeywords"
        clearable
        style="width: 100%; margin-right: 12px"
        :placeholder="$t('datasource.search_by_name')"
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
            v-for="ele in defaultProjectListWithSearch"
            :key="ele.name"
            class="popover-item"
            :class="currentProject?.id?.toString() === ele.id?.toString() && 'isActive'"
            @click="handleDefaultProjectChange(ele)"
          >
            <el-icon size="16">
              <icon_moments_categories_outlined></icon_moments_categories_outlined>
            </el-icon>
            <div
              :title="ele.name"
              class="datasource-name ellipsis"
              v-html="formatKeywords(ele.name)"
            ></div>
            <el-icon size="16" class="done">
              <icon_done_outlined></icon_done_outlined>
            </el-icon>
          </div>
        </el-scrollbar>

        <div v-if="!defaultProjectListWithSearch.length" class="popover-item empty">
          {{ $t('model.relevant_results_found') }}
        </div>
      </div>
    </div>
  </el-popover>
</template>

<style lang="less" scoped>
.project-selector {
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
.system-project.system-project {
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
      height: 32px;
      display: flex;
      align-items: center;
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

      .datasource-name {
        margin-left: 8px;
        font-weight: 400;
        font-size: 14px;
        line-height: 22px;
        max-width: 180px;
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
