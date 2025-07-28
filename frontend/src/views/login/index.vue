<template>
  <div class="login-container">
    <div class="login-content">
      <div class="login-left">
        <div class="illustration"></div>
      </div>
      <div class="login-right">
        <div class="login-form">
          <h2 class="title">Login</h2>
          <el-form
            ref="loginFormRef"
            class="form-content_error"
            :model="loginForm"
            :rules="rules"
            @keyup.enter="submitForm"
          >
            <el-form-item prop="username">
              <el-input
                v-model="loginForm.username"
                clearable
                :placeholder="$t('common.your_account_email_address')"
                size="large"
              ></el-input>
            </el-form-item>
            <el-form-item prop="password">
              <el-input
                v-model="loginForm.password"
                :placeholder="$t('common.enter_your_password')"
                type="password"
                show-password
                clearable
                size="large"
              ></el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" class="login-btn" @click="submitForm">Login</el-button>
            </el-form-item>
          </el-form>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useI18n } from 'vue-i18n'

const router = useRouter()
const userStore = useUserStore()
const { t } = useI18n()

const loginForm = ref({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: t('common.your_account_email_address'), trigger: 'blur' }],
  password: [{ required: true, message: t('common.the_correct_password'), trigger: 'blur' }],
}

const loginFormRef = ref()

const submitForm = () => {
  loginFormRef.value.validate((valid: boolean) => {
    if (valid) {
      userStore.login(loginForm.value).then(() => {
        router.push('/chat')
      })
    }
  })
}
</script>

<style lang="less" scoped>
.login-container {
  height: 100vh;
  width: 100vw;
  background-color: #f0f6f7;
  display: flex;
  align-items: center;
  justify-content: center;

  .login-content {
    display: flex;
    width: 1000px;
    // height: 600px;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.05);
    overflow: hidden;

    .login-left {
      flex: 1;
      background: linear-gradient(135deg, #28c76f 0%, #81fbb8 100%);
      // padding: 40px;
      display: flex;
      flex-direction: column;
      align-items: center;

      .illustration {
        flex: 1;
        width: 100%;
        background-image: url('@/assets/login-bg-sqlbot.jpg');
        background-size: contain;
        background-position: center;
        background-repeat: no-repeat;
      }
    }

    .login-right {
      flex: 1;
      padding: 40px;
      display: flex;
      align-items: center;
      position: relative;
      height: 361px;

      .login-form {
        width: 100%;
        padding: 0 40px;
        position: absolute;
        top: 40px;
        left: 0;

        .form-content_error {
          .ed-form-item--default {
            margin-bottom: 24px;
            &.is-error {
              margin-bottom: 48px;
            }
          }
        }

        .title {
          font-size: 28px;
          color: #1a1a1a;
          margin-bottom: 40px;
          text-align: center;
        }

        .login-btn {
          width: 100%;
          height: 45px;
          font-size: 16px;
          border-radius: 4px;
        }

        .agreement {
          margin-top: 20px;
          text-align: center;
          color: #666;
        }
      }
    }
  }
}

:deep(.ed-input__wrapper) {
  background-color: #f5f7fa;
}
</style>
