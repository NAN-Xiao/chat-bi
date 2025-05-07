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
        <el-input v-model="form.host" />
      </el-form-item>
      <el-form-item label="Port">
        <el-input v-model="form.port" />
      </el-form-item>
      <el-form-item label="Username">
        <el-input v-model="form.username" />
      </el-form-item>
      <el-form-item label="Password">
        <el-input v-model="form.password" />
      </el-form-item>
      <el-form-item label="Database">
        <el-input v-model="form.database" />
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

const emit = defineEmits(['refresh'])

const dialogVisible = ref<boolean>(false)
const dsType = [
  {label:"MySQL", value:"mysql"}
]
const form = ref<any>({
  name:'',
  description:'',
  type:'mysql',
  driver:'',
  host:'',
  port:0,
  username:'',
  password:'',
  database:'',
  configuration: ''
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
    const configuration = JSON.parse(item.configuration)
    form.value.host = configuration.host
    form.value.port = configuration.port
    form.value.username = configuration.username
    form.value.password = configuration.password
    form.value.database = configuration.database
  }
  dialogVisible.value = true
}

const save = () => {
  form.value.configuration = JSON.stringify({
    host:form.value.host,
    port:form.value.port,
    username:form.value.username,
    password:form.value.password,
    database:form.value.database
  })
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
  datasourceApi.check(form.value).then((res: any) => {
    console.log(res)
  })
}

defineExpose({ open })
</script>
<style lang="less" scoped>
</style>