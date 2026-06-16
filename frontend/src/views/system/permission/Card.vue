<script lang="ts" setup>
import delIcon from '@/assets/svg/icon_delete.svg'
import icon_key_outlined from '@/assets/svg/icon-key_outlined.svg'
import icon_member_outlined from '@/assets/svg/icon_member_outlined.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import Lock from '@/assets/permission/icon_custom-tools_colorful.svg'
withDefaults(
  defineProps<{
    name: string
    type: string
    num: string
    projectSummary?: string
    id?: string
  }>(),
  {
    name: '-',
    type: '-',
    id: '-',
    num: '-',
    projectSummary: '-',
  }
)

const emits = defineEmits(['edit', 'del', 'setUser', 'setRule'])

const handleEdit = () => {
  emits('edit')
}

const handleDel = () => {
  emits('del')
}

const setUser = () => {
  emits('setUser')
}

// const setRule = () => {
//   emits('setRule')
// }
</script>

<template>
  <div class="card">
    <div class="name-icon">
      <el-icon class="icon-primary" size="32">
        <Lock></Lock>
      </el-icon>
      <div class="info">
        <div class="name ellipsis" :title="name">{{ name }}</div>
        <div class="sub-title">{{ $t('permission.permission_rule') }}</div>
      </div>
    </div>

    <div class="detail-list">
      <div class="type-value">
        <span class="type">{{ $t('permission.permission_rule') }}</span>
        <span class="value ellipsis"> {{ $t('permission.2', { msg: num }) }}</span>
      </div>
      <div class="type-value">
        <span class="type">{{ $t('permission.project_database') }}</span>
        <span class="value ellipsis" :title="projectSummary">
          {{ projectSummary }}
        </span>
      </div>
      <div class="type-value">
        <span class="type">{{ $t('permission.restricted_user') }}</span>
        <span class="value ellipsis"> {{ $t('permission.238_people', { msg: type }) }}</span>
      </div>
    </div>

    <div class="bottom-info">
      <div class="form-rate">
        <el-icon class="form-icon" size="14">
          <icon_key_outlined></icon_key_outlined>
        </el-icon>
        {{ $t('permission.2', { msg: num }) }}
      </div>
      <div class="methods" @click.stop>
        <el-popover
          trigger="click"
          :teleported="true"
          popper-class="popover-card_permission"
          placement="bottom-end"
        >
          <template #reference>
            <button type="button" class="more" aria-label="more actions">
              <icon_more_outlined></icon_more_outlined>
            </button>
          </template>
          <div class="content">
            <div class="item" @click.stop="handleEdit">
              <el-icon size="16">
                <icon_key_outlined></icon_key_outlined>
              </el-icon>
              {{ $t('permission.set_rule') }}
            </div>
            <div class="item" @click.stop="setUser">
              <el-icon size="16">
                <icon_member_outlined></icon_member_outlined>
              </el-icon>
              {{ $t('permission.set_user') }}
            </div>
            <div class="item" @click.stop="handleDel">
              <el-icon size="16">
                <delIcon></delIcon>
              </el-icon>
              {{ $t('dashboard.delete') }}
            </div>
          </div>
        </el-popover>
      </div>
    </div>
  </div>
</template>

<style lang="less" scoped>
.card {
  width: 100%;
  height: 216px;
  border: 1px solid var(--workspace-border, #e2eaf4);
  padding: 16px 54px 20px 16px;
  border-radius: 8px;
  background: var(--workspace-card-bg, #ffffff);
  box-shadow: 0 12px 28px rgba(24, 46, 86, 0.07);
  display: flex;
  flex-direction: column;
  position: relative;
  transition:
    box-shadow 0.12s ease,
    transform 0.12s ease,
    border-color 0.12s ease;

  &:hover {
    border-color: var(--workspace-border, #e2eaf4);
    box-shadow: 0 16px 36px rgba(24, 46, 86, 0.11);
    transform: translateY(-2px) scale(1.012);
  }

  .name-icon {
    display: flex;
    align-items: center;
    margin-bottom: 12px;

    .info {
      margin-left: 12px;
      max-width: calc(100% - 50px);
      min-width: 0;
    }

    .name {
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
      max-width: 100%;
      color: var(--workspace-text-primary, #1b2a41);
    }

    .sub-title {
      font-weight: 400;
      font-size: 12px;
      line-height: 20px;
      color: var(--workspace-text-secondary, #66758f);
    }
  }

  .detail-list {
    flex: 0 0 auto;
    min-width: 0;
  }

  .type-value {
    display: flex;
    align-items: center;
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    .type {
      color: var(--workspace-text-secondary, #66758f);
      flex: 0 0 86px;
      white-space: nowrap;
    }

    .value {
      margin-left: 16px;
      min-width: 0;
      flex: 1;
      color: var(--workspace-text-primary, #1b2a41);
    }
  }

  .type-value + .type-value {
    margin-top: 6px;
  }

  .bottom-info {
    margin-top: auto;
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 22px;

    .form-rate {
      display: flex;
      align-items: center;
      min-width: 0;
      color: var(--workspace-text-secondary, #66758f);
      font-weight: 400;
      font-size: 14px;
      line-height: 22px;

      .form-icon {
        margin-right: 10px;
        flex: 0 0 auto;
        color: var(--workspace-text-secondary, #66758f);
      }
    }

    .methods {
      position: absolute;
      right: 16px;
      top: 16px;
      align-items: center;
      display: flex;

      .more {
        border: 0;
        padding: 0;
        color: var(--workspace-text-secondary, #66758f);
        background: transparent;
        appearance: none;
        line-height: 1;
        position: relative;
        cursor: pointer;
        width: 28px;
        height: 28px;
        flex: 0 0 28px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        transition:
          color 0.16s ease,
          transform 0.16s ease;

        svg {
          position: relative;
          z-index: 10;
        }

        &::after {
          content: '';
          position: absolute;
          border-radius: 8px;
          width: 28px;
          height: 28px;
          transform: translate(-50%, -50%);
          top: 50%;
          left: 50%;
          background: var(--workspace-control-bg, #f7faff);
          border: 1px solid var(--workspace-border-soft, #eff4fa);
          box-shadow: 0 1px 2px rgba(24, 46, 86, 0.05);
          transition:
            background-color 0.16s ease,
            border-color 0.16s ease,
            box-shadow 0.16s ease;
        }

        &:hover {
          color: var(--workspace-text-primary, #1b2a41);
          transform: translateY(-1px);

          &::after {
            background-color: var(--workspace-control-hover-bg, #edf3ff);
            border-color: var(--workspace-border, #e2eaf4);
            box-shadow: 0 4px 10px rgba(24, 46, 86, 0.08);
          }
        }

        &:focus-visible {
          outline: none;
        }
      }
    }
  }
}
</style>

<style lang="less">
.popover-card_permission.popover-card_permission.popover-card_permission {
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border-radius: 6px;
  border: 1px solid #dee0e3;
  width: fit-content !important;
  min-width: 120px !important;
  padding: 0;

  .content {
    position: relative;

    &::after {
      position: absolute;
      content: '';
      top: 80px;
      left: 0;
      width: 100%;
      height: 1px;
      background: #dee0e3;
    }

    .item {
      position: relative;
      padding: 0 12px;
      height: 40px;
      display: flex;
      align-items: center;
      cursor: pointer;

      .ed-icon {
        margin-right: 8px;
        color: #646a73;
      }

      &:hover {
        &::after {
          display: block;
        }
      }

      &::after {
        content: '';
        width: calc(100% - 8px);
        height: 32px;
        border-radius: 6px;
        position: absolute;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #1f23291a;
        display: none;
      }
    }
  }
}
</style>
