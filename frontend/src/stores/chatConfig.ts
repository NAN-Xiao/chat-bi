import { defineStore } from 'pinia'
import { store } from '@/stores/index.ts'
import { request } from '@/utils/request.ts'
import { formatArg } from '@/utils/utils.ts'

interface ChatConfig {
  zhishu_name: string
  expand_thinking_block: boolean
  limit_rows: boolean
  show_sql: boolean
  show_log: boolean
  generation_concurrency_limit_enabled: boolean
  max_concurrent_generations_per_user: number
  generation_total_timeout_seconds: number
}

export const chatConfigStore = defineStore('chatConfigStore', {
  state: (): ChatConfig => {
    return {
      zhishu_name: '星通智数',
      expand_thinking_block: false,
      limit_rows: true,
      show_sql: true,
      show_log: true,
      generation_concurrency_limit_enabled: true,
      max_concurrent_generations_per_user: 1,
      generation_total_timeout_seconds: 300,
    }
  },
  getters: {
    getZhishuName(): string {
      return this.zhishu_name
    },
    getExpandThinkingBlock(): boolean {
      return this.expand_thinking_block
    },
    getShowSQL(): boolean {
      return this.show_sql
    },
    getShowLog(): boolean {
      return this.show_log
    },
    getLimitRows(): boolean {
      return this.limit_rows
    },
    getGenerationConcurrencyLimitEnabled(): boolean {
      return this.generation_concurrency_limit_enabled
    },
    getMaxConcurrentGenerationsPerUser(): number {
      return this.max_concurrent_generations_per_user
    },
    getGenerationTotalTimeoutSeconds(): number {
      return this.generation_total_timeout_seconds
    },
  },
  actions: {
    fetchGlobalConfig() {
      request.get('/system/parameter/chat').then((res: any) => {
        if (res) {
          res.forEach((item: any) => {
            if (item.pkey === 'chat.expand_thinking_block') {
              this.expand_thinking_block = formatArg(item.pval)
            }
            if (item.pkey === 'chat.show_sql') {
              this.show_sql = formatArg(item.pval)
            }
            if (item.pkey === 'chat.show_log') {
              this.show_log = formatArg(item.pval)
            }
            if (item.pkey === 'chat.limit_rows') {
              this.limit_rows = formatArg(item.pval)
            }
            if (item.pkey === 'chat.generation_concurrency_limit_enabled') {
              this.generation_concurrency_limit_enabled = formatArg(item.pval)
            }
            if (item.pkey === 'chat.max_concurrent_generations_per_user') {
              const count = Number(formatArg(item.pval))
              this.max_concurrent_generations_per_user = Number.isFinite(count)
                ? Math.max(1, Math.floor(count))
                : 1
            }
            if (item.pkey === 'chat.generation_total_timeout_seconds') {
              const count = Number(formatArg(item.pval))
              this.generation_total_timeout_seconds = Number.isFinite(count)
                ? Math.max(1, Math.floor(count))
                : 300
            }
            if (item.pkey === 'chat.zhishu_name') {
              if (item.pval && item.pval.trim().length > 0) {
                this.zhishu_name = item.pval
              }
            }
          })
        }
      })
    },
  },
})

export const useChatConfigStore = () => {
  return chatConfigStore(store)
}
