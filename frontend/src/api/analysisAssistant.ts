import { request } from '@/utils/request'

export type AnalysisAssistantRole = 'user' | 'assistant'

export interface AnalysisAssistantMessage {
  role: AnalysisAssistantRole
  content: string
}

export interface AnalysisAssistantHistoryMessage extends AnalysisAssistantMessage {
  plan?: any
  planText?: string
  traces?: string[]
  blocks?: any[]
  final?: string
  error?: boolean
}

export interface AnalysisAssistantConversationSummary {
  id: number
  title: string
  datasource_id?: number | null
  datasource_name?: string | null
  custom_prompt_id?: number | null
  data_skill_id?: number | null
  message_count: number
  create_time: string
  update_time: string
}

export interface AnalysisAssistantConversationDetail extends AnalysisAssistantConversationSummary {
  messages: AnalysisAssistantHistoryMessage[]
}

export interface AnalysisAssistantConversationSave {
  id?: number | null
  title?: string
  datasource_id?: number
  datasource_name?: string
  custom_prompt_id?: number | string | null
  data_skill_id?: number | string | null
  messages: AnalysisAssistantHistoryMessage[]
}

export interface AnalysisAssistantExportBlock {
  title: string
  purpose?: string
  chart_type?: string
  fields?: string[]
  data?: Record<string, any>[]
  summary?: string
  warning?: string
  error?: string
  image?: string
}

export interface AnalysisAssistantExportRequest {
  title?: string
  question?: string
  datasource_id?: number
  datasource_name?: string
  format: 'pdf' | 'docx'
  blocks: AnalysisAssistantExportBlock[]
  final?: string
  generated_at?: string
}

export const analysisAssistantApi = {
  chat: (
    messages: AnalysisAssistantMessage[],
    context?: string,
    datasourceId?: number,
    customPromptId?: number | string | null,
    dataSkillId?: number | string | null,
    controller?: AbortController
  ) =>
    request.fetchStream(
      '/analysis-assistant/chat',
      {
        messages,
        context,
        datasource_id: datasourceId,
        custom_prompt_id: customPromptId,
        data_skill_id: dataSkillId,
      },
      controller
    ),
  reportInterpretation: (
    messages: AnalysisAssistantMessage[],
    context?: string,
    datasourceId?: number,
    dataSkillId?: number | string | null,
    controller?: AbortController
  ) =>
    request.fetchStream(
      '/analysis-assistant/report-interpretation',
      {
        messages,
        context,
        datasource_id: datasourceId,
        data_skill_id: dataSkillId,
      },
      controller
    ),
  history: (datasourceId?: number, limit = 30): Promise<AnalysisAssistantConversationSummary[]> =>
    request.get('/analysis-assistant/history', {
      params: {
        datasource_id: datasourceId,
        limit,
      },
    }),
  historyDetail: (id: number): Promise<AnalysisAssistantConversationDetail> =>
    request.get(`/analysis-assistant/history/${id}`),
  saveHistory: (
    data: AnalysisAssistantConversationSave
  ): Promise<AnalysisAssistantConversationDetail> =>
    request.post('/analysis-assistant/history', data),
  deleteHistory: (id: number): Promise<void> =>
    request.delete(`/analysis-assistant/history/${id}`),
  exportReport: (data: AnalysisAssistantExportRequest): Promise<Blob> =>
    request.post('/analysis-assistant/export', data, {
      responseType: 'blob',
      requestOptions: {
        silent: true,
      },
    }),
}
