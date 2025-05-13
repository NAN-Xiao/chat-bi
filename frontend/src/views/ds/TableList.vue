<template>
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
        <el-col :span="12">
          <el-table-v2
            :columns="tableColumns"
            :data="tableData"
            :width="700"
            :height="400"
            fixed
          />
        </el-col>
        <el-col :span="12">
          <el-table-v2
            :columns="fieldColumns"
            :data="fieldData"
            :width="700"
            :height="400"
            fixed
          />
        </el-col>
      </el-row>
    </template>
    <template #footer>
      <div style="flex: auto">
        <el-button @click="cancelClick">cancel</el-button>
        <el-button type="primary" @click="confirmClick">confirm</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script lang="tsx" setup>
import { ref } from 'vue'
import { datasourceApi } from '@/api/datasource'
import { ElButton } from 'element-plus'
import { h } from 'vue'

const drawer = ref<boolean>(false)
const tableColumns = ref<any>([
  {
    key:"tableName",
    dataKey:"tableName",
    title: 'Table Name',
    width: 150,
  },
  {
    key:"tableRemark",
    dataKey:"tableRemark",
    title: 'Table Remark',
    width: 300,
  },
  {
    key: 'operations',
    title: 'Operations',
    cellRenderer: ({ rowData }) => {
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
    key:"fieldRemark",
    dataKey:"fieldRemark",
    title: 'Field Remark',
    width: 300,
  }
])
const fieldData = ref<any>([])
const dsId = ref<Number>(0)

const open = (id: Number) => {
  drawer.value = true
  dsId.value = id
  datasourceApi.getTables(id).then((res) => {
    tableData.value = res
  })
}

const showFields = (tableName: string) =>{
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

defineExpose({ open })
</script>

<style lang="less" scoped>

</style>