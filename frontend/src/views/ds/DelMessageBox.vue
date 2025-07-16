<script lang="ts" setup>
defineProps({
  name: {
    type: String,
    default: '-',
  },
  panelNum: {
    type: Number,
    default: 0,
  },
  smartNum: {
    type: Number,
    default: 0,
  },
  t: {
    type: Function,
    default: () => {},
  },
})

const emits = defineEmits(['panelClick', 'smartClick'])
const panelClick = () => {
  emits('panelClick')
}

const smartClick = () => {
  emits('smartClick')
}
</script>

<template>
  <div class="del-box_message">
    <div class="del-title">
      {{ t('datasource.data_source', { msg: name }) }}
    </div>
    <div class="use-panel">
      {{ t('workspace.there_are') }}
      <span @click="panelClick">{{ t('workspace.2_dashboards', { msg: panelNum }) }}</span
      >、<span @click="smartClick">{{ t('workspace.smart_data_centers', { msg: smartNum }) }}</span>
      {{ t('workspace.confirm_to_delete') }}
    </div>
  </div>
</template>

<style lang="less" scoped>
.del-box_message {
  .del-title {
    font-weight: 500;
    font-size: 16px;
    line-height: 24px;
  }

  .use-panel {
    font-weight: 400;
    font-size: 14px;
    line-height: 22px;
    margin-top: 24px;

    span {
      text-decoration: underline;
      text-decoration-style: solid;
      cursor: pointer;
      color: #1cba90;
    }
  }
}
</style>
