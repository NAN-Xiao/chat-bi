import { defineStore } from 'pinia'
import { store } from './index'

interface AssistantState {
  token: string
}

export const AssistantStore = defineStore('assistant', {
  state: (): AssistantState => {
    return {
      token: '',
    }
  },
  getters: {
    getToken(): string {
      return this.token
    },
  },
  actions: {
    setToken(token: string) {
      this.token = token
    },
    clear() {
      this.$reset()
    },
  },
})

export const useAssistantStore = () => {
  return AssistantStore(store)
}
