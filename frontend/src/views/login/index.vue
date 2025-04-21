<template>
  <div class="login-container">
    <div class="login-bg">
      <div class="bg-overlay"></div>
      <div class="bg-content">
        <h1>Welcome back</h1>
        <p>Embark on your ChatBI journey</p>
      </div>
    </div>
    <div class="login-form-container">
      <div class="login-form">
        <el-card class="login-card">
          <h2 class="login-title">Login</h2>
          <el-form :model="loginForm" :rules="rules" ref="loginFormRef">
            <el-form-item prop="username">
              <el-input v-model="loginForm.username" placeholder="username" prefix-icon="user"></el-input>
            </el-form-item>
            <el-form-item prop="password">
              <el-input v-model="loginForm.password" placeholder="password" type="password" prefix-icon="lock"></el-input>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitForm" class="login-btn">Login</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </div>
    </div>
    
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const loginForm = ref({
  username: '',
  password: ''
})

const rules = {
  username: [{ required: true, message: 'Please input username', trigger: 'blur' }],
  password: [{ required: true, message: 'Please input password', trigger: 'blur' }]
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
  display: flex;
  height: 100vh;
  width: 100%;
  overflow: hidden;

  .login-bg {
    overflow: hidden;
    height: 100%;
    width: 40%;
    min-width: 400px;
    position: relative;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    background-size: cover;
    display: flex;
    justify-content: center;
    align-items: center;
    color: white;
    overflow: hidden;
    
    &::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: url('@/assets/login-desc-de.png') center/cover no-repeat;
      opacity: 0.8;
    }

    .bg-overlay {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.3);
    }

    .bg-content {
      position: relative;
      z-index: 2;
      text-align: center;
      padding: 0 40px;
      
      h1 {
        font-size: 2.5rem;
        margin-bottom: 1rem;
        text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
      }
      
      p {
        font-size: 1.2rem;
        opacity: 0.9;
      }
    }
  }
  .login-form-container {
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
    width: 60%;
    min-width: 400px;
    .login-form {
      width: 500px;
      display: flex;
      justify-content: center;
      align-items: center;
      background: #fff;
      padding: 0 40px;

      .login-card {
        width: 100%;
        padding: 40px;
        border: none;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);

        .login-title {
          text-align: center;
          margin-bottom: 30px;
          color: #409eff;
          font-size: 1.8rem;
        }

        .login-btn {
          width: 100%;
          height: 45px;
          font-size: 1rem;
          letter-spacing: 1px;
        }
      }
    }
  }
  
}
</style>