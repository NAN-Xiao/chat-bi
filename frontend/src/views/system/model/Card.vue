<script lang="ts" setup>
import delIcon from '@/assets/svg/icon_delete.svg'
import edit from '@/assets/svg/icon_edit_outlined.svg'
import { get_supplier } from '@/entity/supplier'
import { computed } from 'vue'
const props = withDefaults(
  defineProps<{
    name: string
    modleType: string
    baseModle: string
    id?: string
    isDefault?: boolean
    supplier?: number
  }>(),
  {
    name: '-',
    modleType: '-',
    baseModle: '-',
    id: '-',
    isDefault: false,
    supplier: 0,
  }
)
const current_supplier = computed(() => {
  if (!props.supplier) {
    return null
  }
  return get_supplier(props.supplier)
})
const emits = defineEmits(['edit', 'del'])

const handleEdit = () => {
  emits('edit', props.id)
}

const handleDel = () => {
  emits('del', { id: props.id, name: props.name, default_model: props.isDefault })
}
</script>

<template>
  <div class="card">
    <div class="name-icon">
      <img :src="current_supplier?.icon" width="32px" height="32px" />
      <span class="name">{{ name }}</span>
      <span v-if="isDefault" class="default">{{ $t('model.default_model') }}</span>
    </div>
    <div class="type-value">
      <span class="type">{{ $t('model.model_type') }}</span>
      <span class="value"> {{ modleType }}</span>
    </div>
    <div class="type-value">
      <span class="type">{{ $t('model.basic_model') }}</span>
      <span class="value"> {{ baseModle }}</span>
    </div>
    <div class="methods">
      <el-tooltip :offset="14" effect="dark" :content="$t('datasource.edit')" placement="top">
        <el-icon size="16" @click="handleEdit">
          <edit></edit>
        </el-icon>
      </el-tooltip>
      <template v-if="!isDefault">
        <span class="divide"></span>
        <el-tooltip :offset="14" effect="dark" :content="$t('dashboard.delete')" placement="top">
          <el-icon size="16" @click="handleDel">
            <delIcon></delIcon>
          </el-icon>
        </el-tooltip>
      </template>
    </div>
  </div>
</template>

<style lang="less" scoped>
.card {
  width: 404px;
  height: 160px;
  border: 1px solid #dee0e3;
  padding: 16px;
  border-radius: 12px;
  margin: 0 16px 16px 0;
  &:hover {
    box-shadow: 0px 6px 24px 0px #1f232914;
  }

  .name-icon {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
    .name {
      margin-left: 12px;
      font-weight: 500;
      font-size: 16px;
      line-height: 24px;
    }
    .default {
      margin-left: auto;
      background: #1cba9033;
      padding: 0 4px;
      border-radius: 4px;
      color: #189e7a;
      font-weight: 400;
      font-size: 12px;
      line-height: 20px;
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
    }
  }

  .methods {
    margin-top: 16px;
    align-items: center;
    justify-content: flex-end;
    display: none;

    .ed-icon {
      position: relative;
      cursor: pointer;

      &::after {
        content: '';
        background-color: #1f23291a;
        position: absolute;
        border-radius: 6px;
        width: 24px;
        height: 24px;
        transform: translate(-50%, -50%);
        top: 50%;
        left: 50%;
        display: none;
      }

      &:hover {
        &::after {
          display: block;
        }
      }
    }

    .divide {
      height: 14px;
      width: 1px;
      background-color: #1f232926;
      margin: 0 12px;
    }
  }

  &:hover {
    .methods {
      display: flex;
    }
  }
}
</style>
