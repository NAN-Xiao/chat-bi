<template>
  <div class="layout">
    <el-row class="header">
      <div class="title">
        <el-button text :icon="ArrowLeft" @click="back()" />
        {{ props.dsName }}
      </div>
      <el-button type="primary" @click="save()">
        Save
      </el-button>
    </el-row>
    <el-row class="data">
      <el-table-v2
        :columns="tableColumns"
        :data="tableData"
        :width="1000"
        :height="800"
        fixed
      />
    </el-row>
    <el-drawer 
    v-model="drawer" 
    direction="btt" 
    :destroy-on-close="true"
    :close-on-click-modal="false"
    size="80%"
  >
    <template #header>
      <div>Detail</div>
    </template>
    <template #default>
      <el-row :gutter="20">
        <el-table-v2
          :columns="fieldColumns"
          :data="fieldData"
          :width="1000"
          :height="800"
          fixed
        />
      </el-row>
    </template>
    <template #footer>
      <div style="flex: auto">
        <el-button @click="cancelClick">Cancel</el-button>
        <el-button type="primary" @click="confirmClick">Confirm</el-button>
      </div>
    </template>
  </el-drawer>
  </div>
</template>

<script lang="tsx" setup>
import { ref } from 'vue'
import { datasourceApi } from '@/api/datasource'
import { ElButton } from 'element-plus'
import { h } from 'vue'
import { onMounted } from 'vue'
import { ArrowLeft } from '@element-plus/icons-vue'

const props = defineProps({
  dsId: { type: [Number], required: true },
  dsName: { type: [String], required: true }
})

const drawer = ref<boolean>(false)
const tableColumns = ref<any>([
  {
    key:"tableName",
    dataKey:"tableName",
    title: 'Table Name',
    width: 150,
  },
  {
    key:"tableComment",
    dataKey:"tableComment",
    title: 'Table Comment',
    width: 300,
  },
  {
    key: 'operations',
    title: 'Operations',
    cellRenderer: ({ rowData }: { rowData: any }) => {
      return h(ElButton,{
        onClick: () => showFields(rowData.tableName)
      },"Show Fields")
    },
    width: 150,
    align: 'center',
  }
])
const tableData = ref<any>([])
const fieldColumns = ref<any>([
  {
    key:"fieldName",
    dataKey:"fieldName",
    title: 'Field Name',
    width: 150,
  },
  {
    key:"fieldType",
    dataKey:"fieldType",
    title: 'Field Type',
    width: 150,
  },
  {
    key:"fieldComment",
    dataKey:"fieldComment",
    title: 'Field Comment',
    width: 300,
  }
])
const fieldData = ref<any>([])
const dsId = ref<Number>(0)

const back = () => {
  history.back()
}

const save = () => {

}

const showFields = (tableName: string) =>{
  drawer.value = true
  datasourceApi.getFields(dsId.value, tableName).then((res) => {
    fieldData.value = res
  })
}

const cancelClick = () => {
  drawer.value = false
}

const confirmClick = () => {
  // save something
  cancelClick()
}

onMounted(() => {
  dsId.value = props.dsId
  datasourceApi.getTables(props.dsId).then((res) => {
    tableData.value = res
  })
})

defineExpose({ open })
</script>

<style lang="less" scoped>
.layout{
  padding: 20px 40px;
  .header{
    padding: 20px 0;
    display: flex;
    justify-content: space-between;
  }
  .title{
    display: flex;
    align-items: center;
  }
}
</style>