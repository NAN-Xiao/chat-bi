import { request } from '@/utils/request'

export type AnalysisAssistantRole = 'user' | 'assistant'

export interface AnalysisAssistantMessage {
  role: AnalysisAssistantRole
  content: string
}

export const analysisAssistantApi = {
  chat: (
    messages: AnalysisAssistantMessage[],
    context?: string,
    datasourceId?: number,
    controller?: AbortController
  ) =>
    request.fetchStream(
      '/analysis-assistant/chat',
      { messages, context, datasource_id: datasourceId },
      controller
    ),
}
