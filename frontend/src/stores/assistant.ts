import { defineStore } from 'pinia'
import { store } from './index'
import { chatApi, ChatInfo } from '@/api/chat'

interface AssistantState {
  token: string
  assistant: boolean
}

export const AssistantStore = defineStore('assistant', {
  state: (): AssistantState => {
    return {
      token: '',
      assistant: false,
    }
  },
  getters: {
    getToken(): string {
      return this.token
    },
    getAssistant(): boolean {
      return this.assistant
    },
  },
  actions: {
    setToken(token: string) {
      this.token = token
    },
    setAssistant(assistant: boolean) {
      this.assistant = assistant
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
      this.$reset()
    },
  },
})

export const useAssistantStore = () => {
  return AssistantStore(store)
}
