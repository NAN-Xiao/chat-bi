<script lang="ts" setup>
import delIcon from '@/assets/svg/icon_delete.svg'
import icon_embedded_outlined from '@/assets/embedded/icon_embedded_outlined.svg'
import IconOpeEdit from '@/assets/svg/icon_edit_outlined.svg'
import Lock from '@/assets/embedded/LOGO-sql.png'

withDefaults(
  defineProps<{
    name: string
    isBase: boolean
    description: string
    id?: string
  }>(),
  {
    name: '-',
    isBase: false,
    id: '-',
    description: '-',
  }
)

const emits = defineEmits(['edit', 'del', 'embedded'])

const handleEdit = () => {
  emits('edit')
}

const handleDel = () => {
  emits('del')
}

const handleEmbedded = () => {
  emits('embedded')
}
</script>

<template>
  <div class="card">
    <div class="name-icon">
      <img :src="Lock" width="32px" height="32px" />
      <span class="name">{{ name }}</span>
      <span class="default" :class="isBase && 'is-base'">{{
        isBase ? $t('embedded.basic_application') : $t('embedded.advanced_application')
      }}</span>
    </div>
    <div class="description" :title="description">{{ description }}</div>
    <div class="methods">
      <el-button secondary @click="handleEmbedded">
        <el-icon style="margin-right: 4px" size="16">
          <icon_embedded_outlined></icon_embedded_outlined>
        </el-icon>
        {{ $t('embedded.embed_third_party') }}
      </el-button>
      <el-button secondary @click="handleEdit">
        <el-icon style="margin-right: 4px" size="16">
          <IconOpeEdit></IconOpeEdit>
        </el-icon>
        {{ $t('dashboard.edit') }}
      </el-button>
      <el-button secondary @click="handleDel">
        <el-icon style="margin-right: 4px" size="16">
          <delIcon></delIcon>
        </el-icon>
        {{ $t('dashboard.delete') }}
      </el-button>
    </div>
  </div>
</template>

<style lang="less" scoped>
.card {
  width: 371px;
  height: 168px;
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
      padding: 0 4px;
      border-radius: 4px;
      font-weight: 400;
      font-size: 12px;
      line-height: 20px;
      background: #ff880033;
      color: #d97400;

      &.is-base {
        background: #1cba9033;
        color: #189e7a;
      }
    }
  }

  .description {
    margin-top: 12px;
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    max-width: 100%;
    display: -webkit-box;
    height: 44px;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .methods {
    margin-top: 16px;
  }
}
</style>
