<script lang="ts" setup>
import { ref, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { userApi } from '@/api/auth'
const { t } = useI18n()
const pwdRef = ref()
const pwdForm = reactive({
  pwd: '',
  new_pwd: '',
  confirm_pwd: '',
})

const rules = {
  pwd: [
    {
      required: true,
      message: t('common.please_input', { msg: t('user.upgrade_pwd.old_pwd') }),
      trigger: 'blur',
    },
  ],
  new_pwd: [
    {
      required: true,
      message: t('common.please_input', { msg: t('user.upgrade_pwd.new_pwd') }),
      trigger: 'blur',
    },
  ],
  confirm_pwd: [
    {
      required: true,
      message: t('common.please_input', { msg: t('user.upgrade_pwd.confirm_pwd') }),
      trigger: 'blur',
    },
  ],
}

const initForm = (item: any) => {
  if (item) {
    Object.assign(pwdForm, { ...item })
  }
  pwdRef.value.clearValidate()
}

const emits = defineEmits(['pwdSaved'])

const submit = () => {
  pwdRef.value.validate((res: any) => {
    if (res) {
      const param = {
        pwd: pwdForm.pwd,
        new_pwd: pwdForm.new_pwd,
      }
      userApi.pwd(param).then(() => {
        ElMessage({
          type: 'success',
          message: t('common.save_success'),
        })
        emits('pwdSaved')
      })
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
    <el-form ref="pwdRef" :rules="rules" label-position="top" :model="pwdForm" style="width: 100%">
      <el-form-item prop="pwd" :label="t('user.upgrade_pwd.old_pwd')">
        <el-input
          v-model="pwdForm.pwd"
          :placeholder="t('common.please_input', { msg: t('user.upgrade_pwd.old_pwd') })"
          type="password"
          show-password
        />
      </el-form-item>
      <el-form-item prop="new_pwd" :label="t('user.upgrade_pwd.new_pwd')">
        <el-input
          v-model="pwdForm.new_pwd"
          :placeholder="t('common.please_input', { msg: t('user.upgrade_pwd.new_pwd') })"
          type="password"
          show-password
        />
      </el-form-item>
      <el-form-item prop="confirm_pwd" :label="t('user.upgrade_pwd.confirm_pwd')">
        <el-input
          v-model="pwdForm.confirm_pwd"
          :placeholder="t('common.please_input', { msg: t('user.upgrade_pwd.confirm_pwd') })"
          type="password"
          show-password
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
