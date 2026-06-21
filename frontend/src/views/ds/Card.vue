<script lang="ts" setup>
import delIcon from '@/assets/svg/icon_delete.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import icon_form_outlined from '@/assets/svg/icon_form_outlined.svg'
import { computed } from 'vue'
import { dsTypeWithImg } from './js/ds-type'
import edit from '@/assets/svg/icon_edit_outlined.svg'
import icon_member_outlined from '@/assets/svg/icon_member_outlined.svg'
import icon_recommended_problem from '@/assets/svg/icon_recommended_problem.svg'

const props = withDefaults(
  defineProps<{
    name: string
    type: string
    typeName: string
    num: string
    description?: string
    id?: string
    datasourceRole?: string
    authorizedUserCount?: number | string
    canManageDatasource?: boolean
    canMaintainDatasource?: boolean
  }>(),
  {
    name: '-',
    type: '-',
    description: '-',
    id: '-',
    datasourceRole: '',
    authorizedUserCount: 0,
    typeName: '-',
    canManageDatasource: false,
    canMaintainDatasource: false,
  }
)

const emits = defineEmits([
  'edit',
  'del',
  'dataTableDetail',
  'showTable',
  'recommendation',
  'members',
])
const icon = computed(() => {
  return (dsTypeWithImg.find((ele) => props.type === ele.type) || {}).img
})
const handleEdit = () => {
  emits('edit')
}

const handleRecommendation = () => {
  emits('recommendation')
}

const handleMembers = () => {
  emits('members')
}

const handleDel = () => {
  emits('del')
}

const dataTableDetail = () => {
  emits('dataTableDetail')
}
</script>

<template>
  <div class="card" @click="dataTableDetail">
    <div class="name-icon">
      <img :src="icon" width="32px" height="32px" />
      <div class="info">
        <div :title="name" class="name ellipsis">{{ name }}</div>
        <div class="type">{{ typeName }}</div>
      </div>
    </div>
    <div :title="description" class="type-value">
      {{ description }}
    </div>

    <div class="detail-list">
      <div class="detail-row">
        <span class="label">{{ $t('ds.type') }}</span>
        <span class="value ellipsis">{{ typeName }}</span>
      </div>
      <div class="detail-row">
        <span class="label">{{ $t('datasource.authorized_users') }}</span>
        <span class="value ellipsis">{{
          $t('datasource.authorized_user_count', { msg: authorizedUserCount })
        }}</span>
      </div>
      <div class="detail-row detail-row-table">
        <el-icon class="table-icon" size="14">
          <icon_form_outlined></icon_form_outlined>
        </el-icon>
        <span class="label">{{ $t('ds.tables') }}</span>
        <span class="value ellipsis">{{ num }}</span>
      </div>
    </div>

    <div class="methods" @click.stop>
      <el-popover
        v-if="canManageDatasource || canMaintainDatasource"
        trigger="click"
        :teleported="true"
        popper-class="popover-card_ds"
        placement="bottom-end"
      >
        <template #reference>
          <button type="button" class="more" aria-label="more actions" @click.stop>
            <icon_more_outlined></icon_more_outlined>
          </button>
        </template>
        <div class="content">
          <div v-if="canMaintainDatasource" class="item" @click.stop="handleEdit">
            <el-icon size="16">
              <edit></edit>
            </el-icon>
            {{ $t('datasource.edit') }}
          </div>
          <div v-if="canMaintainDatasource" class="item" @click.stop="handleRecommendation">
            <el-icon size="16">
              <icon_recommended_problem></icon_recommended_problem>
            </el-icon>
            {{ $t('datasource.recommended_problem_configuration') }}
          </div>
          <div v-if="canManageDatasource" class="item" @click.stop="handleMembers">
            <el-icon size="16">
              <icon_member_outlined></icon_member_outlined>
            </el-icon>
            {{ $t('datasource.datasource_authorization') }}
          </div>
          <div v-if="canMaintainDatasource" class="item" @click.stop="handleDel">
            <el-icon size="16">
              <delIcon></delIcon>
            </el-icon>
            {{ $t('dashboard.delete') }}
          </div>
        </div>
      </el-popover>
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
  cursor: pointer;
  position: relative;
  display: flex;
  flex-direction: column;
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
    margin-bottom: 8px;

    .info {
      margin-left: 12px;
      max-width: calc(100% - 50px);
      min-width: 0;

      .name {
        font-weight: 500;
        font-size: 16px;
        line-height: 24px;
        max-width: 100%;
        color: var(--workspace-text-primary, #1b2a41);
      }

      .type {
        font-weight: 400;
        font-size: 12px;
        line-height: 20px;
        color: var(--workspace-text-secondary, #66758f);
      }
    }
  }

  .type-value {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    color: var(--workspace-text-secondary, #66758f);
    height: 44px;
    flex: 0 0 44px;
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    word-break: break-word;
    overflow: hidden;
    width: 100%;
  }

  .detail-list {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
    flex: 0 0 auto;
  }

  .detail-row {
    display: flex;
    align-items: center;
    font-size: 14px;
    line-height: 22px;
    min-height: 22px;

    .label {
      flex: 0 0 72px;
      color: var(--workspace-text-secondary, #66758f);
      white-space: nowrap;
    }

    .value {
      min-width: 0;
      color: var(--workspace-text-primary, #1b2a41);
    }
  }

  .detail-row + .detail-row {
    margin-top: 0;
  }

  .detail-row-table {
    color: var(--workspace-text-secondary, #66758f);

    .table-icon {
      align-self: center;
      margin-right: 10px;
      flex: 0 0 auto;
      color: var(--workspace-text-secondary, #66758f);
    }

    .label {
      flex: 0 0 auto;
      margin-right: 12px;
    }
  }

  .methods {
    position: absolute;
    right: 16px;
    top: 16px;
    align-items: center;
    display: flex;

      .ed-button {
        margin-left: 0;
      }

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
</style>

<style lang="less">
.popover-card_ds.popover-card_ds.popover-card_ds {
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
      top: 120px !important;
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
