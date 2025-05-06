<template>
  <div>
    <div class="header">
      <div class="mt-4">
        <el-input
          v-model="search"
          style="max-width: 300px"
          placeholder="Search Datasource..."
          class="input-with-select"
        >
          <template #prepend>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>

      <el-button type="primary" :icon="IconOpeAdd" @click="addDs">Add Datasource</el-button>
    </div>

    <div class="connections-container">
      <div 
        class="connection-card"
        v-for="ds in dsList"
      >
        <div class="connection-icon">
          <i class="mdi mdi-database"></i>
        </div>
        <div class="connection-details">
          <div class="connection-name">{{ ds.name }}</div>
          <div class="connection-type">{{ ds.type }}</div>
          <div class="connection-host">{{ ds.host }}</div>
          <div class="connection-last">{{ datetimeFormat(ds.create_time) }}</div>
        </div>
        <div class="connection-status" :class="`${getStatus(ds.status)}`">{{ ds.status }}</div>
        <div class="connection-actions">
          <button class="action-btn">
            <el-icon><IconOpeEdit /></el-icon>
          </button>
          <button class="action-btn">
            <el-icon><IconOpeDelete /></el-icon>
          </button>
        </div>
      </div>
    </div>
  </div>
  <DsForm ref="dsForm"/>
</template>
<script lang="ts" setup>
import IconOpeAdd from '@/assets/svg/operate/ope-add.svg'
import IconOpeEdit from '@/assets/svg/operate/ope-edit.svg'
import IconOpeDelete from '@/assets/svg/operate/ope-delete.svg'
import { Search } from '@element-plus/icons-vue'
import { ref, onMounted } from 'vue'
import DsForm from './form.vue'
import { datasourceApi } from '@/api/datasource'
import { datetimeFormat } from '@/utils/utils'

const search = ref<string>('')
const dsForm = ref()
const dsList = ref<any>([])

const getStatus = (status: string) => {
  if (status === 'Success') {
    return 'connected'
  }
  if (status === 'Fail') {
    return 'failed'
  }
  if (status === 'Checking') {
    return 'needs-verification'
  }
}

const addDs = () => {
  dsForm.value.open()
}

const list = () => {
  datasourceApi.list().then((res) => {
    dsList.value = res
  })
}

onMounted(() => {
  list()
})

</script>
<style lang="less" scoped>
.header{
  background-color: white;
  padding: 16px 20px;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  margin-bottom: 20px;
  display: flex;
  justify-content: space-between;
}

.connections-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 24px;
  .connection-card {
    background-color: white;
    border-radius: 16px;
    padding: 24px 20px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
    display: flex;
    position: relative;
    border: 1px solid #dadce0;
    transition: all 0.2s ease;
    height: 110px;
    align-items: center;
  }
  .connection-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background-color: #e8f0fe;
    color: var(--primary-color);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 16px;
    flex-shrink: 0;
  }
  .connection-details {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    .connection-name {
      font-weight: 600;
      font-size: 18px;
      color: #202124;
      margin-bottom: 8px;
      line-height: 1.3;
      display: flex;
    }
    .connection-type {
      color: #5f6368;
      margin-bottom: 8px;
      font-size: 14px;
      display: flex;
    }
    .connection-host {
      color: #5f6368;
      margin-bottom: 8px;
      font-size: 14px;
      display: flex;
      align-items: center;
    }
    .connection-last {
      color: #5f6368;
      font-size: 14px;
      margin-bottom: 0;
      display: flex;
      align-items: center;
    }
  }
  .connection-status {
    position: absolute;
    right: 20px;
    top: 18px;
    padding: 3px 8px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 500;
    display: flex;
    align-items: center;
    max-width: 50px;
    text-align: center;
    justify-content: center;
    opacity: 0.9;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  }
  .connection-status.connected {
    background-color: #e6f4ea;
    color: #34a853;
  }
  .connection-status.failed {
    background-color: #fce8e6;
    color: #ea4335;
  }
  .connection-status.needs-verification {
    background-color: #fef7e0;
    color: #fbbc05;
  }
  .connection-actions {
    position: absolute;
    bottom: 20px;
    right: 20px;
    display: flex;
    transition: opacity 0.2s ease;
    gap: 8px;
    .action-btn {
      width: 36px;
      height: 36px;
      border-radius: 50%;
      display: none;
      align-items: center;
      justify-content: center;
      color: #5f6368;
      cursor: pointer;
      transition: all 0.2s;
      background-color: #f1f3f4;
      border: none;
    }
  }
  :hover .action-btn{
    display: flex;
  }
}

</style>