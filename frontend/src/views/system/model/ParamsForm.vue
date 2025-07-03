<script lang="ts" setup>
import { ref, reactive } from 'vue'
const paramsRef = ref()
const paramsForm = reactive({
  name: '',
  params: '',
  value: null,
  type: 0,
})

const rules = {
  name: [{ required: true, message: '请给基础模型设置一个名称', trigger: 'blur' }],
  params: [{ required: true, message: '请给基础模型设置一个名称', trigger: 'blur' }],
  value: [{ required: true, message: '请给基础模型设置一个名称', trigger: 'blur' }],
  type: [{ required: true, message: '请给基础模型设置一个名称', trigger: 'blur' }],
}

const initForm = (item: any) => {
  if (item) {
    Object.assign(paramsForm, { ...item })
  }
  paramsRef.value.clearValidate()
}

const typeList = ['文本', '数值', 'Json']

const emits = defineEmits(['submit'])

const submit = () => {
  paramsRef.value.validate((res: any) => {
    if (res) {
      emits('submit', paramsForm)
    }
  })
}
defineExpose({
  initForm,
  submit,
})
</script>

<template>
  <div class="params-form">
    <el-form
      ref="paramsRef"
      :rules="rules"
      label-position="top"
      :model="paramsForm"
      style="width: 100%"
    >
      <el-form-item prop="params" label="参数">
        <el-input v-model="paramsForm.params" />
      </el-form-item>
      <el-form-item prop="name" label="显示名称">
        <el-input v-model="paramsForm.name" />
      </el-form-item>
      <el-form-item prop="type" label="参数类型">
        <el-radio-group v-model="paramsForm.type">
          <el-radio v-for="(ele, index) in typeList" :key="ele" :value="index">{{ ele }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item prop="value" :label="typeList[paramsForm.type]">
        <el-input-number
          v-if="paramsForm.type === 1"
          v-model="paramsForm.value"
          controls-position="right"
        />
        <el-input
          v-if="paramsForm.type === 0"
          v-model="paramsForm.value"
          placeholder="请输入 1-50 个字符"
        />
        <el-input v-if="paramsForm.type === 2" v-model="paramsForm.value" type="textarea" />
      </el-form-item>
    </el-form>
  </div>
</template>

<style lang="less" scoped>
.params-form {
  .ed-form-item--default {
    margin-bottom: 16px;

    &.is-error {
      margin-bottom: 40px;
    }
  }

  .ed-input-number {
    width: 100%;
  }
}
</style>
