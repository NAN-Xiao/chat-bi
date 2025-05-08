import { defineStore } from 'pinia'
import { ref } from 'vue'
import { AuthApi } from '@/api/login'
import { useCache } from '@/utils/useCache'
const { wsCache } = useCache()
export const useUserStore = defineStore('user', () => {
  const token = ref('')
  const username = ref('')

  const login = async (formData: { username: string; password: string }) => {
    username.value = formData.username
    const res: any = await AuthApi.login(formData)
    token.value = res.access_token
    wsCache.set('user.token', token.value)
    username.value = formData.username
  }

  const logout = () => {
    token.value = ''
    username.value = ''
    wsCache.delete('user.token')
  }

  return {
    token,
    username,
    login,
    logout
  }
})