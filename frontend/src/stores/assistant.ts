import { defineStore } from 'pinia'
import { store } from './index'
import { chatApi, ChatInfo } from '@/api/chat'
import { useCache } from '@/utils/useCache'

const { wsCache } = useCache()
const flagKey = 'sqlbit-assistant-flag'
interface AssistantState {
  token: string
  assistant: boolean
  flag: number
  type: number
  certificate: string
}

export const AssistantStore = defineStore('assistant', {
  state: (): AssistantState => {
    return {
      token: '',
      assistant: false,
      flag: 0,
      type: 0,
      certificate: '',
    }
  },
  getters: {
    getCertificate(): string {
      return this.certificate
    },
    getToken(): string {
      return this.token
    },
    getAssistant(): boolean {
      return this.assistant
    },
    getFlag(): number {
      return this.flag
    },
    getType(): number {
      return this.type
    },
  },
  actions: {
    setCertificate(certificate: string) {
      this.certificate = certificate
    },
    setType(type: number) {
      this.type = type
    },
    setToken(token: string) {
      this.token = token
    },
    setAssistant(assistant: boolean) {
      this.assistant = assistant
    },
    setFlag(flag: number) {
      if (wsCache.get(flagKey)) {
        this.flag = wsCache.get(flagKey)
      } else {
        this.flag = flag
        wsCache.set(flagKey, flag)
      }
    },
    async setChat() {
      if (!this.assistant) {
        return null
      }
      const res = await chatApi.startAssistantChat()
      const chat: ChatInfo | undefined = chatApi.toChatInfo(res)
      return chat
    },
    clear() {
      wsCache.delete(flagKey)
      this.$reset()
    },
  },
})

export const useAssistantStore = () => {
  return AssistantStore(store)
}
