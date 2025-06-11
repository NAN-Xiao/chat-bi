<template>
  <div class="info-card">
    <div class="info-title">
      Dashboard ID
    </div>
    <div class="info-content">{{ dashboardInfo.id }}</div>
    <div v-if="dashboardInfo.createName" class="info-title">Creator</div>
    <div v-if="dashboardInfo.createName" class="info-content">{{ dashboardInfo.createName }}</div>
    <div class="info-title">Create Time</div>
    <div class="info-content">{{ timestampFormatDate(dashboardInfo.createTime) }}</div>
    <div v-if="dashboardInfo.updateName" class="info-title">Updator</div>
    <div v-if="dashboardInfo.updateName" class="info-content">{{ dashboardInfo.updateName }}</div>
    <div class="info-title">Update Time</div>
    <div v-if="dashboardInfo.updateTime" class="info-content">
      {{ timestampFormatDate(dashboardInfo.updateTime) }}
    </div>
    <div v-if="!dashboardInfo.updateTime" class="info-content">N/A</div>
  </div>
</template>

<script lang="ts" setup>

defineProps({
  dashboardInfo: {
    type: Object,
    required: true
  }
})

const timestampFormatDate = (value: any) => {
  if (!value) {
    return '-'
  }
  return new Date(value * 1000).toLocaleString()
}
</script>

<style lang="less" scoped>
.info-card {
  font-style: normal;
  padding-left: 4px;
  font-weight: 400;
  line-height: 22px;

  .info-title {
    color: #646a73;
    font-size: 14px;
    margin-bottom: 4px;
  }

  .info-content {
    color: #1f2329;
    font-size: 14px;
    margin-bottom: 12px;
  }

  :last-child {
    margin-bottom: 0;
  }
}
</style>
