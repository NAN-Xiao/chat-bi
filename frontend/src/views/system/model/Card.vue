<script lang="ts" setup>
import azure from '@/assets/model/icon_Azure_OpenAI_colorful.png'
import delIcon from '@/assets/svg/icon_delete.svg'
import edit from '@/assets/svg/icon_edit_outlined.svg'

const props = withDefaults(
  defineProps<{
    name: string
    modleType: string
    baseModle: string
    id?: string
    isDefault?: boolean
  }>(),
  {
    name: '-',
    modleType: '-',
    baseModle: '-',
    id: '-',
    isDefault: false,
  }
)

const emits = defineEmits(['edit', 'del'])

const handleEdit = () => {
  emits('edit', props.id)
}

const handleDel = () => {
  emits('del', props.id)
}
</script>

<template>
  <div class="card">
    <div class="name-icon">
      <img :src="azure" width="32px" height="32px" />
      <span class="name">{{ name }}</span>
      <span class="default">默认模型</span>
    </div>
    <div class="type-value">
      <span class="type">模型类型</span>
      <span class="value"> {{ modleType }}</span>
    </div>
    <div class="type-value">
      <span class="type">基础模型</span>
      <span class="value"> {{ baseModle }}</span>
    </div>
    <div class="methods">
      <el-tooltip :offset="14" effect="dark" content="编辑" placement="top">
        <el-icon @click="handleEdit" size="16">
          <edit></edit>
        </el-icon>
      </el-tooltip>
      <template v-if="!isDefault">
        <span class="divide"></span>
        <el-tooltip :offset="14" effect="dark" content="删除" placement="top">
          <el-icon @click="handleDel" size="16">
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
