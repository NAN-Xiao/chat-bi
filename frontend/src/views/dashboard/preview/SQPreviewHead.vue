<script setup lang="ts">
import icon_pc_outlined from '@/assets/svg/icon_pc_outlined.svg'
import icon_edit_outlined from '@/assets/svg/icon_edit_outlined.svg'
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
const { t } = useI18n()

const preview = () => {
  window.open(`#/dashboard-preview?resourceId=${props.dashboardInfo.id}`, '_blank')
}
const edit = () => {
  window.open(`#/canvas?resourceId=${props.dashboardInfo.id}`, '_self')
}
const props = defineProps({
  dashboardInfo: {
    type: Object,
    required: false,
    default: () => ({}),
  },
})
const canEdit = computed(() => props.dashboardInfo?.canEdit === true)
const canPreview = computed(() => !!props.dashboardInfo?.id)
const titleText = computed(() => props.dashboardInfo?.name || t('dashboard.dashboard'))
</script>

<template>
  <div class="preview-head flex-align-center">
    <div class="canvas-name ellipsis" :class="{ 'is-placeholder': !dashboardInfo?.name }">
      {{ titleText }}
    </div>
    <div class="canvas-opt-button">
      <el-button v-if="canPreview" secondary @click="preview">
        <template #icon>
          <icon name="icon_pc_outlined">
            <icon_pc_outlined class="svg-icon" />
          </icon>
        </template>
        {{ t('dashboard.preview') }}
      </el-button>
      <el-button v-if="canEdit" class="custom-button" type="primary" @click="edit">
        <template #icon>
          <Icon name="icon_edit_outlined">
            <icon_edit_outlined class="svg-icon" />
          </Icon>
        </template>
        {{ t('dashboard.edit') }}
      </el-button>
    </div>
  </div>
</template>

<style lang="less">
.pad12 {
  .ed-dropdown-menu__item {
    padding: 5px 36px 5px 12px !important;

    .ed-icon {
      margin-right: 8px;
    }

    .arrow-right_icon {
      position: absolute;
      right: 12px;
      margin-right: 0;
    }

    &:has(.arrow-right_icon) {
      width: 100%;
    }
  }
}

.preview-head {
  display: flex;
  width: 100%;
  min-width: 300px;
  height: 64px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--workspace-border, var(--theme-shell-border));
  background: var(--workspace-panel-bg, var(--theme-panel-bg));

  .canvas-name {
    max-width: 280px;
    font-size: 17px;
    font-weight: 600;
    color: var(--workspace-text-primary, #1b2a41);

    &.is-placeholder {
      color: var(--workspace-text-secondary, #66758f);
      font-weight: 500;
    }
  }

  .canvas-have-update {
    background-color: rgba(52, 199, 36, 0.2);
    color: rgba(44, 169, 31, 1);
    font-weight: 400;
    font-size: 12px;
    line-height: 20px;
    vertical-align: middle;
    padding: 0 4px;
    margin-left: 8px;
  }

  .custom-icon {
    cursor: pointer;
    margin-left: 8px;
  }

  .create-area {
    color: var(--workspace-text-secondary, #66758f);
    font-weight: 400;
    font-size: 14px;
  }

  .canvas-opt-button {
    display: flex;
    justify-content: right;
    align-items: center;
    flex: 1;

    .head-more-icon {
      color: var(--workspace-text-primary, #1b2a41);
      margin-left: 12px;
      cursor: pointer;
      font-size: 20px;
      border-radius: 8px;
      position: relative;

      &:hover {
        &::after {
          content: '';
          position: absolute;
          top: -4px;
          left: -4px;
          border-radius: 6px;
          height: 28px;
          width: 28px;
          background: #1f23291a;
        }
      }
    }
  }
}

.info-tips {
  margin-left: 4px;
  font-size: 16px;
  color: var(--workspace-text-secondary, #66758f);
}

.custom-button {
  margin-left: 10px;
}

.flex-align-center {
  & + & {
    margin-left: 4px;
  }
}
</style>
