export type ReportPromptStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export type ReportPromptHistoryItem = {
  text: string
  answer: string
  title: string
  targetContext: string
  updatedAt: number
  expiresAt: number
}

export type ReportPromptHistorySaveInput =
  | string
  | {
      text: string
      answer?: string
      title?: string
      targetContext?: string
    }

export type ReportPromptHistoryScope = {
  tenantId: string | number | null | undefined
  userUid: string | number | null | undefined
  dashboardUid: string | number | null | undefined
  targetScope: string | null | undefined
}

export const REPORT_PROMPT_HISTORY_STORAGE_KEY = 'dashboard_report_prompt_history:v1'
export const REPORT_PROMPT_HISTORY_STORAGE_PREFIX = 'dashboard_report_prompt_history:v2'
export const REPORT_PROMPT_HISTORY_LIMIT = 4
export const REPORT_PROMPT_HISTORY_TTL_MS = 3 * 24 * 60 * 60 * 1000

function normalizeText(text: string) {
  return text.trim()
}

function normalizeOptionalText(text: unknown) {
  return text === undefined || text === null ? '' : `${text}`.trim()
}

function normalizeSaveInput(input: ReportPromptHistorySaveInput) {
  if (typeof input === 'string') {
    return {
      text: normalizeText(input),
      answer: '',
      title: '',
      targetContext: '',
    }
  }
  return {
    text: normalizeOptionalText(input.text),
    answer: normalizeOptionalText(input.answer),
    title: normalizeOptionalText(input.title),
    targetContext: normalizeOptionalText(input.targetContext),
  }
}

function parseHistory(raw: string | null): ReportPromptHistoryItem[] {
  if (!raw) {
    return []
  }
  try {
    const value = JSON.parse(raw)
    if (!Array.isArray(value)) {
      return []
    }
    return value
      .map((item) => ({
        text: normalizeText(`${item?.text || ''}`),
        answer: normalizeOptionalText(item?.answer),
        title: normalizeOptionalText(item?.title),
        targetContext: normalizeOptionalText(item?.targetContext),
        updatedAt: Number(item?.updatedAt || 0),
        expiresAt: Number(item?.expiresAt || 0),
      }))
      .filter((item) => item.text && Number.isFinite(item.expiresAt))
  } catch {
    return []
  }
}

export function buildReportPromptHistoryStorageKey(scope: ReportPromptHistoryScope): string | null {
  const parts = [scope.tenantId, scope.userUid, scope.dashboardUid, scope.targetScope].map(
    (value) => `${value ?? ''}`.trim()
  )
  if (parts.some((value) => !value)) {
    return null
  }
  return `${REPORT_PROMPT_HISTORY_STORAGE_PREFIX}:${parts.map(encodeURIComponent).join(':')}`
}

function persistHistory(
  storage: ReportPromptStorage,
  storageKey: string,
  history: ReportPromptHistoryItem[]
) {
  if (history.length === 0) {
    storage.removeItem(storageKey)
    return
  }
  storage.setItem(storageKey, JSON.stringify(history))
}

export function loadReportPromptHistory(
  storage: ReportPromptStorage,
  scope: ReportPromptHistoryScope,
  now = Date.now()
): ReportPromptHistoryItem[] {
  storage.removeItem(REPORT_PROMPT_HISTORY_STORAGE_KEY)
  const storageKey = buildReportPromptHistoryStorageKey(scope)
  if (!storageKey) {
    return []
  }
  const history = parseHistory(storage.getItem(storageKey))
    .filter((item) => item.expiresAt > now)
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, REPORT_PROMPT_HISTORY_LIMIT)

  persistHistory(storage, storageKey, history)
  return history
}

export function saveReportPromptHistory(
  storage: ReportPromptStorage,
  scope: ReportPromptHistoryScope,
  input: ReportPromptHistorySaveInput,
  now = Date.now()
): ReportPromptHistoryItem[] {
  storage.removeItem(REPORT_PROMPT_HISTORY_STORAGE_KEY)
  const storageKey = buildReportPromptHistoryStorageKey(scope)
  if (!storageKey) {
    return []
  }
  const normalizedInput = normalizeSaveInput(input)
  if (!normalizedInput.text) {
    return loadReportPromptHistory(storage, scope, now)
  }
  const deduped = loadReportPromptHistory(storage, scope, now).filter(
    (item) => item.text !== normalizedInput.text
  )
  const history = [
    {
      text: normalizedInput.text,
      answer: normalizedInput.answer,
      title: normalizedInput.title,
      targetContext: normalizedInput.targetContext,
      updatedAt: now,
      expiresAt: now + REPORT_PROMPT_HISTORY_TTL_MS,
    },
    ...deduped,
  ].slice(0, REPORT_PROMPT_HISTORY_LIMIT)

  persistHistory(storage, storageKey, history)
  return history
}
