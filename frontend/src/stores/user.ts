import { defineStore } from 'pinia'
// import { ref } from 'vue'
import { AuthApi } from '@/api/login'
import { useCache } from '@/utils/useCache'
import { i18n } from '@/i18n'
import { store } from './index'

const { wsCache } = useCache()



interface UserState {
  token: string
  uid: string
  name: string
  oid: string
  language: string
  exp: number
  time: number
  [key: string]: string | number 
}

export const UserStore = defineStore('user', {
  state: (): UserState => {
    return {
      token: '',
      uid: '',
      name: '',
      oid: '',
      language: 'zh-CN',
      exp: 0,
      time: 0
    }
  },
  getters: {
    getToken(): string {
      return this.token
    },
    getUid(): string {
      return this.uid
    },
    getName(): string {
      return this.name
    },
    getOid(): string {
      return this.oid
    },
    getLanguage(): string {
      return this.language
    },
    getExp(): number {
      return this.exp
    },
    getTime(): number {
      return this.time
    }
  },
  actions: {

    async login(formData: { username: string; password: string }) {
      const res: any = await AuthApi.login(formData)
      this.setToken(res.access_token)
    },

    logout() {
      this.clear()
    },

    async info () {
      const res: any = await AuthApi.info()
      const res_data = res || {}

      // 指定 keys 类型为 UserState 的键
      const keys = ['uid', 'name', 'oid', 'language', 'exp', 'time'] as const
      
      keys.forEach(key => {
        const dkey = key === 'uid' ? 'id' : key
        const value = res_data[dkey]
       
        // 使用类型守卫区分数字和字符串类型
        if (key === 'exp' || key === 'time') {
          this[key] = Number(value)
          wsCache.set('user.' + key, value.toString())
        } else {
          this[key] = String(value)
          wsCache.set('user.' + key, value)
        }
      })

      this.setLanguage(this.language)
    },
    setToken(token: string) {
      wsCache.set('user.token', token)
      this.token = token
    },
    setExp(exp: number) {
      wsCache.set('user.exp', exp)
      this.exp = exp
    },
    setTime(time: number) {
      wsCache.set('user.time', time)
      this.time = time
    },
    setUid(uid: string) {
      wsCache.set('user.uid', uid)
      this.uid = uid
    },
    setName(name: string) {
      wsCache.set('user.name', name)
      this.name = name
    },
    setOid(oid: string) {
      wsCache.set('user.oid', oid)
      this.oid = oid
    },
    setLanguage(language: string) {
      if (!language || language === 'zh_CN') {
        language = 'zh-CN'
      }
      wsCache.set('user.language', language)
      this.language = language
      i18n.global.locale.value = language
      /* const { locale } = useI18n()
      locale.value = language */
      // locale.setLang(language)
    },
    clear() {
      const keys: string[] = ['token', 'uid', 'name', 'oid', 'language', 'exp', 'time']
      keys.forEach(key => wsCache.delete('user.' + key))
    }
  }
})

export const useUserStore = () => {
  return UserStore(store)
}