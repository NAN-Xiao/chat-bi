<template>
  <div v-loading="loading">
    <div class="header">
      <div class="mt-4">
        <el-input
            v-model="searchValue"
            style="max-width: 300px"
            placeholder="Search Datasource..."
            class="input-with-select"
            clearable
            @change="searchHandle"
        >
          <template #prepend>
            <el-icon>
              <Search/>
            </el-icon>
          </template>
        </el-input>
      </div>

      <el-button type="primary" :icon="IconOpeAdd" @click="editDs(undefined)">Add Datasource</el-button>
    </div>

    <div class="connections-container">
      <template v-for="ds in dsList">
        <DatasourceItemCard :ds="ds">
          <div class="connection-actions">
            <el-button class="action-btn" circle @click="getTables(ds.id, ds.name)" :icon="List"/>
            <el-button class="action-btn" circle @click="editTables(ds)" :icon="CreditCard"/>
            <el-button type="primary" class="action-btn" circle @click="editDs(ds)" :icon="IconOpeEdit"/>
            <el-button type="danger" class="action-btn" circle @click="deleteDs(ds)" :icon="IconOpeDelete"/>
          </div>
        </DatasourceItemCard>
      </template>
    </div>
  </div>
  <DsForm ref="dsForm" @refresh="refresh"/>
</template>
<script lang="ts" setup>
import IconOpeAdd from '@/assets/svg/operate/ope-add.svg'
import IconOpeEdit from '@/assets/svg/operate/ope-edit.svg'
import IconOpeDelete from '@/assets/svg/operate/ope-delete.svg'
import {Search, List, CreditCard} from '@element-plus/icons-vue'
import {ref, onMounted} from 'vue'
import DsForm from './form.vue'
import {datasourceApi} from '@/api/datasource'
import {ElMessageBox} from 'element-plus-secondary'
import {useRouter} from 'vue-router'
import DatasourceItemCard from "@/views/ds/DatasourceItemCard.vue";

const searchValue = ref<string>('')
const dsForm = ref()
const dsList = ref<any>([])// show ds list
const allDsList = ref<any>([])// all ds list
const router = useRouter()
const loading = ref(false)


function searchHandle() {
  if (searchValue.value) {
    dsList.value = JSON.parse(JSON.stringify(allDsList.value)).filter((item: any) => {
      return item.name.toLowerCase().includes(searchValue.value.toLowerCase())
    })
  } else {
    dsList.value = JSON.parse(JSON.stringify(allDsList.value))
  }
}

const refresh = () => {
  list()
}

const list = () => {
  loading.value = true
  datasourceApi.list().then((res) => {
    allDsList.value = res
    dsList.value = JSON.parse(JSON.stringify(allDsList.value))
    loading.value = false
  })
}

const editDs = (item: any) => {
  dsForm.value.open(item)
}

const editTables = (item: any) => {
  dsForm.value.open(item, true)
}

const deleteDs = (item: any) => {
  ElMessageBox.confirm(
      'Delete this datasource?',
      'Delete',
      {
        confirmButtonText: 'Confirm',
        cancelButtonText: 'Cancel',
        type: 'warning',
      }
  )
      .then(() => {
        datasourceApi.delete(item.id).then(() => {
          console.log('success')
          list()
        })
      })
      .catch(() => {
      })
}

const getTables = (id: number, name: string) => {
  // datasourceApi.getTables(id).then((res) => {
  //   console.log(res)
  // })

  // datasourceApi.getFields(id,'core_dataset_table').then((res) => {
  //   console.log(res)
  // })

  // datasourceApi.execSql(id,'select id,name,table_name from core_dataset_table limit 10').then((res) => {
  //   console.log(res)
  // })
  router.push(`/dsTable/${id}/${name}`)
}

onMounted(() => {
  list()
})

</script>
<style lang="less" scoped>
.header {
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

  .connection-actions {
    position: absolute;
    bottom: 20px;
    right: 20px;
    display: flex;

    .action-btn {
      display: none;
      min-width: 0;
    }
  }

  :hover .action-btn {
    display: flex;
  }
}

</style>