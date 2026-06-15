<script lang="ts" setup>
import delIcon from '@/assets/svg/icon_delete.svg'
import icon_more_outlined from '@/assets/svg/icon_more_outlined.svg'
import icon_admin_outlined from '@/assets/svg/icon_admin_outlined.svg'
import edit from '@/assets/svg/icon_edit_outlined.svg'
import { get_supplier } from '@/entity/supplier'
import { computed, ref, unref } from 'vue'
import { ClickOutside as vClickOutside } from 'element-plus-secondary'
const props = withDefaults(
  defineProps<{
    name: string
    modelType: string
    baseModel: string
    id?: string
    isDefault?: boolean
    supplier?: number
  }>(),
  {
    name: '-',
    modelType: '-',
    baseModel: '-',
    id: '-',
    isDefault: false,
    supplier: 0,
  }
)
const errorMsg = ref('')
const current_supplier = computed(() => {
  if (!props.supplier) {
    return null
  }
  return get_supplier(props.supplier)
})
const showErrorMask = (msg?: string) => {
  if (!msg) {
    return
  }
  errorMsg.value = msg
  setTimeout(() => {
    errorMsg.value = ''
  }, 3000)
}
const emits = defineEmits(['edit', 'del', 'default'])

const handleDefault = () => {
  emits('default')
}

const handleDel = () => {
  emits('del', { id: props.id, name: props.name, default_model: props.isDefault })
}

const handleEdit = () => {
  emits('edit')
}

const buttonRef = ref()
const popoverRef = ref()
const onClickOutside = () => {
  unref(popoverRef).popperRef?.delayHide?.()
}

defineExpose({ showErrorMask })
</script>

<template>
  <div
    v-loading="!!errorMsg"
    class="card"
    :element-loading-text="errorMsg"
    element-loading-custom-class="model-card-loading"
  >
    <div class="card-head">
      <div class="name-icon">
        <img :src="current_supplier?.icon" width="32px" height="32px" />
        <span :title="name" class="name ellipsis">{{ name }}</span>
        <span v-if="isDefault" class="default">{{ $t('model.default_model') }}</span>
      </div>
    </div>
    <div class="type-value">
      <span class="type">{{ $t('model.model_type') }}</span>
      <span class="value">
        {{ modelType.startsWith('modelType.') ? $t(modelType) : modelType }}</span
      >
    </div>
    <div class="type-value">
      <span class="type">{{ $t('model.basic_model') }}</span>
      <span class="value"> {{ baseModel }}</span>
    </div>
    <div class="methods" @click.stop>
      <el-icon
        ref="buttonRef"
        v-click-outside="onClickOutside"
        class="more"
        size="16"
        style="color: #646a73"
        @click.stop
      >
        <icon_more_outlined></icon_more_outlined>
      </el-icon>
      <el-popover
        ref="popoverRef"
        :virtual-ref="buttonRef"
        virtual-triggering
        trigger="click"
        :teleported="true"
        popper-class="popover-card_model"
        placement="bottom-end"
      >
        <div class="content">
          <div v-if="!isDefault" class="item" @click.stop="handleDefault">
            <el-icon size="16">
              <icon_admin_outlined></icon_admin_outlined>
            </el-icon>
            {{ $t('common.as_default_model') }}
          </div>
          <div class="item" @click.stop="handleEdit">
            <el-icon size="16">
              <edit></edit>
            </el-icon>
            {{ $t('dashboard.edit') }}
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
</template>

<style lang="less" scoped>
.card {
  width: 100%;
  height: 152px;
  border: 1px solid #dee0e3;
  padding: 16px 60px 16px 16px;
  border-radius: 8px;
  background: #fff;
  box-shadow: 1px 5px 14px rgba(31, 35, 41, 0.08);
  display: flex;
  flex-direction: column;
  position: relative;
  transition:
    box-shadow 0.12s ease,
    transform 0.12s ease,
    border-color 0.12s ease;

  &:hover {
    border-color: #d7dce2;
    box-shadow: 3px 8px 24px rgba(31, 35, 41, 0.13);
    transform: translateY(-2px) scale(1.012);
  }

  .card-head {
    display: flex;
    align-items: center;
    margin-bottom: 14px;
  }

  .name-icon {
    display: flex;
    align-items: center;
    min-width: 0;
    flex: 1;

    img {
      flex: 0 0 auto;
    }

    .name {
      margin-left: 12px;
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
      min-width: 0;
    }
    .default {
      margin-left: auto;
      background: var(--ed-color-primary-33, #1cba9033);
      padding: 1px 7px;
      border-radius: 999px;
      color: var(--ed-color-primary-dark-2);
      font-weight: 400;
      font-size: 12px;
      line-height: 18px;
      white-space: nowrap;
    }
  }

  .type-value {
    margin-top: 8px;
    display: flex;
    align-items: center;
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    .type {
      color: #646a73;
    }

    .value {
      margin-left: 16px;
      min-width: 0;
      flex: 1;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }
  }

  .methods {
    position: absolute;
    right: 16px;
    top: 96px;
    flex: 0 0 auto;
    align-items: center;
    display: flex;

    .divide {
      height: 14px;
      width: 1px;
      background-color: #1f232926;
      margin: 0 12px;
    }
    .more {
      position: relative;
      cursor: pointer;
      width: 32px;
      height: 32px;
      flex: 0 0 32px;
      display: inline-flex;
      align-items: center;
      justify-content: center;

      svg {
        position: relative;
        z-index: 10;
      }

      &::after {
        content: '';
        position: absolute;
        border-radius: 6px;
        width: 32px;
        height: 32px;
        transform: translate(-50%, -50%);
        top: 50%;
        left: 50%;
        background: #fff;
        border: 1px solid #d9dcdf;
      }

      &:hover {
        &::after {
          background-color: #f5f6f7;
        }
      }
    }
  }
  :deep(.model-card-loading) {
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    align-items: end;
    background-color: rgb(122 122 122 / 87%);
    .ed-loading-spinner {
      top: auto;
      margin: 8px 4px;
      display: flex;
      position: relative;
      justify-content: flex-end;
      align-items: center;
      width: calc(100% - 8px);
    }
    svg {
      display: none;
    }
    p {
      text-align: left;
      color: var(--ed-color-danger);
    }
  }
}
</style>

<style lang="less">
.popover-card_model.popover-card_model.popover-card_model {
  box-shadow: 0px 4px 8px 0px #1f23291a;
  border-radius: 6px;
  border: 1px solid #dee0e3;
  width: fit-content !important;
  min-width: 120px !important;
  padding: 0;

  .content {
    position: relative;

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
