<script lang="ts" setup>
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
const paramsRef = ref()
const paramsForm = reactive({
  name: '',
  params: '',
  value: null,
  type: 0,
})

const rules = {
  name: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('model.display_name'),
      trigger: 'blur',
    },
  ],
  params: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('model.parameters'),
      trigger: 'blur',
    },
  ],
  value: [
    {
      required: true,
      message: t('datasource.please_enter') + t('common.empty') + t('model.parameter_value'),
      trigger: 'blur',
    },
  ],
}

const initForm = (item: any) => {
  if (item) {
    Object.assign(paramsForm, { ...item })
  }
  paramsRef.value.clearValidate()
}

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
      <el-form-item prop="params" :label="$t('model.parameters')">
        <el-input
          v-model="paramsForm.params"
          :placeholder="$t('datasource.please_enter') + $t('common.empty') + $t('model.parameters')"
        />
      </el-form-item>
      <el-form-item prop="name" :label="$t('model.display_name')">
        <el-input
          v-model="paramsForm.name"
          :placeholder="
            $t('datasource.please_enter') + $t('common.empty') + $t('model.display_name')
          "
        />
      </el-form-item>
      <el-form-item prop="value" :label="$t('model.parameter_value')">
        <el-input
          v-model="paramsForm.value"
          :placeholder="
            $t('datasource.please_enter') + $t('common.empty') + $t('model.parameter_value')
          "
        />
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
