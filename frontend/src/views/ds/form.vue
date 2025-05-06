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
        <el-input v-model="form.desc" :rows="2" type="textarea" />
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

      <el-form-item>
        <el-button @click="check">Test Connect</el-button>
        <el-button type="primary" @click="save">Save</el-button>
      </el-form-item>
    </el-form>
  </el-dialog>
</template>
<script lang="ts" setup>
import { reactive } from 'vue'
import { ref } from 'vue'
import { datasourceApi } from '@/api/datasource'

const dialogVisible = ref<boolean>(false)
const dsType = [
  {label:"MySQL", value:"mysql"}
]
const form = reactive({
  name:'',
  desc:'',
  type:'mysql',
  host:'',
  port:0,
  username:'',
  password:'',
  database:'',
  configuration: ''
})

const open = () => {
  dialogVisible.value = true
}

const save = () => {
  form.configuration = JSON.stringify({host:form.host,port:form.port,username:form.username,password:form.password,database:form.database})
  datasourceApi.add(form).then((res: any) => {
    console.log(res)
  })
}

const check = () => {
  datasourceApi.check(form).then((res: any) => {
    console.log(res)
  })
}

defineExpose({ open })
</script>
<style lang="less" scoped>
</style>