<template>
  <el-dialog
    v-model="dialogVisible"
    title="Add Datasource"
    width="500"
  >
    <el-form :model="form" label-width="auto">
      <el-form-item label="Name">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="Description">
        <el-input v-model="form.description" :rows="2" type="textarea" />
      </el-form-item>
      <el-form-item label="Type">
        <el-select v-model="form.type" placeholder="Select Type">
          <el-option
            v-for="item in dsType"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
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

      <div style="display: flex;justify-content: flex-end;">
        <el-button @click="close">Cancel</el-button>
        <el-button @click="check">Test Connect</el-button>
        <el-button type="primary" @click="save">Save</el-button>
      </div>
    </el-form>
  </el-dialog>
</template>
<script lang="ts" setup>
import { ref } from 'vue'
import { datasourceApi } from '@/api/datasource'
import { encrypted, decrypted } from './js/aes'
import { ElMessage } from 'element-plus'

const emit = defineEmits(['refresh'])

const dialogVisible = ref<boolean>(false)
const dsType = [
  {label:"MySQL", value:"mysql"}
]
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
})

const close = () => {
  dialogVisible.value = false
}

const open = (item: any) => {
  if (item) {
    form.value.id = item.id
    form.value.name = item.name
    form.value.description = item.description
    form.value.type = item.type
    if(item.configuration) {
      const configuration = JSON.parse(decrypted(item.configuration))
      config.value.host = configuration.host
      config.value.port = configuration.port
      config.value.username = configuration.username
      config.value.password = configuration.password
      config.value.database = configuration.database
    }
  } else {
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
    }
  }
  dialogVisible.value = true
}

const save = () => {
  form.value.configuration = encrypted(JSON.stringify({
    host:config.value.host,
    port:config.value.port,
    username:config.value.username,
    password:config.value.password,
    database:config.value.database
  }))
  if (form.value.id) {
    datasourceApi.update(form.value).then((res) => {
      console.log(res)
      close()
      emit('refresh')
    })
  } else {
    datasourceApi.add(form.value).then((res: any) => {
      console.log(res)
      close()
      emit('refresh')
    })
  }
}

const check = () => {
  form.value.configuration = encrypted(JSON.stringify({
    host:config.value.host,
    port:config.value.port,
    username:config.value.username,
    password:config.value.password,
    database:config.value.database
  }))
  datasourceApi.check(form.value).then((res: any) => {
    console.log(res)
    if(res) {
      ElMessage({
        message: 'Connect success',
        type: 'success',
        showClose: true
      })
    }
  })
}

defineExpose({ open })
</script>
<style lang="less" scoped>
</style>./js/aes