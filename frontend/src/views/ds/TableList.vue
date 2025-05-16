<template>
  <div class="layout">
    <el-row class="header">
      <div class="title">
        <el-button text :icon="ArrowLeft" @click="back()" />
        {{ props.dsName }}
      </div>
    </el-row>
    <el-row class="container" :gutter="20">
      <el-col :span="4">
        Tables
        <el-input v-model="searchValue" placeholder="Search" />
        <div>
          <div v-for="item in tableList" class="table-item" @click="clickTable(item)">{{ item.table_name }}</div>
        </div>
      </el-col>
      <el-col :span="20">
        <div v-if="fieldList.length === 0">No data, select a table from left</div>
        <div v-else>
          <div style="display: flex;justify-content: space-between;align-items: center;">
            <div style="display: flex;justify-content: start;align-items: center;">
              <span>{{ currentTable.table_name }}</span>
              <span>&nbsp;|&nbsp;Comment:&nbsp;</span>
              <span>
                <el-input v-model="currentTable.custom_comment" />
              </span>
            </div>
            <el-button type="primary" @click="save()">
              Save
            </el-button>
          </div>
          <el-tabs v-model="activeName" class="demo-tabs" @tab-click="handleClick">
            <el-tab-pane label="Table Schema" name="schema">
              <el-table :data="fieldList" style="width: 100%">
                <el-table-column prop="field_name" label="Name" width="180" />
                <el-table-column prop="field_type" label="Type" width="180" />
                <el-table-column prop="field_comment" label="Comment" />
                <el-table-column label="Custom Comment">
                  <template #default="scope">
                    <div style="display: flex; align-items: center">
                      <el-input v-model="scope.row.custom_comment" />
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="Status" width="180">
                  <template #default="scope">
                    <div style="display: flex; align-items: center">
                      <el-switch
                        v-model="scope.row.checked"
                        size="small"
                      />
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="Preview" name="preview">
              <div>Preview 100 items</div>
              <el-table :data="previewData.data" style="width: 100%;height: 600px;">
                <el-table-column v-for="c in previewData.fields" :prop="c" :label="c"/>
              </el-table>
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script lang="tsx" setup>
import { ref } from 'vue'
import { datasourceApi } from '@/api/datasource'
import { onMounted } from 'vue'
import { ArrowLeft } from '@element-plus/icons-vue'
import type { TabsPaneContext } from 'element-plus'

const props = defineProps({
  dsId: { type: [Number], required: true },
  dsName: { type: [String], required: true }
})

const dsId = ref<Number>(0)
const searchValue = ref('')
const tableList = ref<any>([])
const currentTable = ref<any>({})
const fieldList = ref<any>([])
const previewData = ref<any>({})

const activeName = ref('schema')

const buildData = () => {
  return {"table": currentTable.value, "fields": fieldList.value}
}

const back = () => {
  history.back()
}

const save = () => {
  datasourceApi.edit(buildData()).then(() => {
    ElMessage({
      message: 'Save success',
      type: 'success',
      showClose: true
    })
  })
}

const clickTable = (table: any) => {
  currentTable.value = table
  datasourceApi.fieldList(table.id).then((res) => {
    fieldList.value = res
    datasourceApi.previewData(dsId.value, buildData()).then((res) => {
      previewData.value = res
    })
  })
}

const handleClick = (tab: TabsPaneContext) => {
  if(tab.paneName === 'preview') {
    datasourceApi.previewData(dsId.value, buildData()).then((res) => {
      previewData.value = res
    })
  }
}

onMounted(() => {
  dsId.value = props.dsId
  fieldList.value = []
  datasourceApi.tableList(props.dsId).then((res) => {
    tableList.value = res
  })
})
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
  .container{
    height: 100%;
    .table-item{
      margin: 10px 0;
    }
  }
}
</style>