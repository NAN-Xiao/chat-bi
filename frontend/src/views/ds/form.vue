<template>
  <el-dialog
    v-model="dialogVisible"
    title="Add Datasource"
    width="500"
    :destroy-on-close="true"
    :close-on-click-modal="false"
    @closed="close"
  >
    <el-steps v-show="isCreate" style="max-width: 600px" :active="active" align-center>
      <el-step title="Base Info" />
      <el-step title="Choose Tables" />
    </el-steps>
    <div v-show="active === 1" class="container">
      <el-form :model="form" label-width="auto" ref="dsFormRef" :rules="rules">
        <el-form-item label="Name" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="Description">
          <el-input v-model="form.description" :rows="2" type="textarea" />
        </el-form-item>
        <el-form-item label="Type">
          <el-select v-model="form.type" placeholder="Select Type" :disabled="!isCreate">
            <el-option
              v-for="item in dsType"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>
        <div v-if="form.type === 'excel'">
          <el-form-item label="File">
            <el-upload
              accept=".xls, .xlsx, .csv"
              :headers="headers"
              action="http://localhost:8000/api/v1/datasource/uploadExcel"
              :before-upload="beforeUpload"
            >
              <el-button>Upload</el-button>
              <template #tip>
                <div class="el-upload__tip">
                  Only support .xls, .xlsx, .csv, size less than 50MB.
                </div>
              </template>
            </el-upload>
          </el-form-item>
        </div>
        <div v-else>
          <el-form-item label="Host/Ip">
            <el-input v-model="config.host" />
          </el-form-item>
          <el-form-item label="Port">
            <el-input v-model="config.port" />
          </el-form-item>
          <el-form-item label="Username">
            <el-input v-model="config.username" />
          </el-form-item>
          <el-form-item label="Password">
            <el-input v-model="config.password" type="password" show-password />
          </el-form-item>
          <el-form-item label="Database">
            <el-input v-model="config.database" />
          </el-form-item>
          <el-form-item label="Extra JDBC String">
            <el-input v-model="config.extraJdbc" />
          </el-form-item>
          <el-form-item label="Schema" v-if="haveSchema.includes(form.type)">
            <el-input v-model="config.dbSchema" />
            <el-button link type="primary" :icon="Plus" v-if="false">Get Schema</el-button>
          </el-form-item>
        </div>
      </el-form>
    </div>
    <div v-show="active === 2" class="container">
      <el-scrollbar>
        <el-checkbox-group v-model="checkList">
          <el-row :gutter="10">
            <el-col v-for="item in tableList" :key="item.value" :span="12">
              <el-checkbox :label="item.tableName">{{ item.tableName }}</el-checkbox>
            </el-col>
          </el-row>
        </el-checkbox-group>
      </el-scrollbar>
      <span>Selected: {{ checkList.length }}/{{ tableList.length }}</span>
    </div>
    <div style="display: flex;justify-content: flex-end;margin-top: 20px;">
      <el-button @click="close">Cancel</el-button>
      <el-button v-show="!isCreate && !isEditTable && form.type !== 'excel'" @click="check">Test Connect</el-button>
      <el-button v-show="active === 1 && isCreate" type="primary" @click="next(dsFormRef)">Next</el-button>
      <el-button v-show="active === 2 && isCreate" @click="preview">Preview</el-button>
      <el-button v-show="active === 2 || !isCreate" type="primary" @click="save(dsFormRef)">Save</el-button>
    </div>
  </el-dialog>
</template>
<script lang="ts" setup>
import { ref, reactive } from 'vue'
import { datasourceApi } from '@/api/datasource'
import { encrypted, decrypted } from './js/aes'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useCache } from '@/utils/useCache'
import { dsType, haveSchema} from '@/views/ds/js/ds-type'

const { wsCache } = useCache()
const dsFormRef = ref<FormInstance>()
const emit = defineEmits(['refresh'])
const active = ref(1)
const isCreate = ref(true)
const isEditTable = ref(false)
const checkList = ref<any>([])
const tableList = ref<any>([])

const token = wsCache.get('user.token')
const headers = ref<any>({'X-SQLBOT-TOKEN': `Bearer ${token}`})


const rules = reactive<FormRules>({
  name: [
    { required: true, message: 'Please input name', trigger: 'blur' },
    { min: 1, max: 50, message: 'Length should be 1 to 50', trigger: 'blur' },
  ],
})

const dialogVisible = ref<boolean>(false)
const form = ref<any>({
  name:'',
  description:'',
  type:'mysql',
  configuration: ''
})
const config = ref<any>({
  driver:'',
  host:'',
  port:0,
  username:'',
  password:'',
  database:'',
  extraJdbc:'',
  dbSchema:''
})

const close = () => {
  dialogVisible.value = false
  isCreate.value = true
  active.value = 1
  isEditTable.value = false
  checkList.value = []
  tableList.value = []
}

const open = (item: any, editTable: boolean = false) => {
  isEditTable.value = false
  if (item) {
    isCreate.value = false
    form.value.id = item.id
    form.value.name = item.name
    form.value.description = item.description
    form.value.type = item.type
    form.value.configuration = item.configuration
    if(item.configuration) {
      const configuration = JSON.parse(decrypted(item.configuration))
      config.value.host = configuration.host
      config.value.port = configuration.port
      config.value.username = configuration.username
      config.value.password = configuration.password
      config.value.database = configuration.database
      config.value.extraJdbc = configuration.extraJdbc
      config.value.dbSchema = configuration.dbSchema
    }

    if (editTable) {
      active.value = 2
      isEditTable.value = true
      isCreate.value = false
      // request tables and check tables
      datasourceApi.tableList(item.id).then((res) => {
        checkList.value = res.map((ele:any) => {return ele.table_name})
        datasourceApi.getTablesByConf(form.value).then((res) => {
          tableList.value = res
        })
      })
    }
  } else {
    isCreate.value = true
    isEditTable.value = false
    checkList.value = []
    tableList.value = []
    form.value = {
      name:'',
      description:'',
      type:'mysql',
      configuration: ''
    }
    config.value = {
      driver:'',
      host:'',
      port:0,
      username:'',
      password:'',
      database:'',
      extraJdbc:'',
      dbSchema:''
    }
  }
  dialogVisible.value = true
}

const save = async(formEl: FormInstance | undefined) => {
  if(!formEl) return
  await formEl.validate((valid) => {
    if (valid) {
      const list = tableList.value
          .filter((ele: any) => {return checkList.value.includes(ele.tableName)})
          .map((ele: any) => {return {"table_name": ele.tableName, "table_comment": ele.tableComment}})

      buildConf()
      if (form.value.id) {
        if (!isEditTable.value) {
          // only update datasource config info
          datasourceApi.update(form.value).then((res) => {
            console.log(res)
            close()
            emit('refresh')
          })
        } else {
          // save table and field
          datasourceApi.chooseTables(form.value.id, list).then(() => {
            close()
          })
        }
      } else {
        form.value.tables = list
        datasourceApi.add(form.value).then((res: any) => {
          console.log(res)
          close()
          emit('refresh')
        })
      }
    }
  })
}

const buildConf = () => {
  form.value.configuration = encrypted(JSON.stringify({
    host:config.value.host,
    port:config.value.port,
    username:config.value.username,
    password:config.value.password,
    database:config.value.database,
    extraJdbc:config.value.extraJdbc,
    dbSchema:config.value.dbSchema
  }))
}

const check = () => {
  buildConf()
  datasourceApi.check(form.value).then((res: any) => {
    if(res) {
      ElMessage({
        message: 'Connect success',
        type: 'success',
        showClose: true
      })
    }
  })
}

const next = async(formEl: FormInstance | undefined) => {
  if (form.value.type === "excel") {
    // next, show tables 
  } else {
    if(!formEl) return
    await formEl.validate((valid) => {
      if (valid) {
        // check status if success do next
        buildConf()
        datasourceApi.check(form.value).then((res: boolean) => {
          if(res) {
            active.value++
            // request tables
            datasourceApi.getTablesByConf(form.value).then((res) => {
              tableList.value = res
            })
          }
        })
      }
    })
  }
}

const preview = () => {
  active.value--
}

const beforeUpload = (rawFile: any) => {
  if (rawFile.size / 1024 / 1024 > 50) {
    ElMessage.error('File size can not exceed 50MB!')
    return false
  }
  return true
}

defineExpose({ open })
</script>
<style lang="less" scoped>
.container{
  height: 600px;
  margin-top: 20px;
}
</style>