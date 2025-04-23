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
        <el-button>Test Connect</el-button>
        <el-button type="primary" @click="save">Save</el-button>
      </el-form-item>
    </el-form>
  </el-dialog>
</template>
<script lang="ts" setup>
import { reactive } from 'vue'
import { ref } from 'vue'
const dialogVisible = ref<boolean>(false)
const form = reactive({
  name:'',
  host:'',
  port:0,
  username:'',
  password:'',
  database:''
})

const open = () => {
  dialogVisible.value = true
}

const save = () => {

}

defineExpose({ open })
</script>
<style lang="less" scoped>
</style>