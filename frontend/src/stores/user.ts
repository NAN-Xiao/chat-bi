import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const token = ref('')
  const username = ref('')

  const login = async (formData: { username: string; password: string }) => {
    token.value = 'mock-token'
    username.value = formData.username
    return Promise.resolve()
  }

  const logout = () => {
    token.value = ''
    username.value = ''
  }

  return {
    token,
    username,
    login,
    logout
  }
})