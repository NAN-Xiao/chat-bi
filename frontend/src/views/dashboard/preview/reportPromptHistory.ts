export type ReportPromptStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export type ReportPromptHistoryItem = {
  text: string
  updatedAt: number
  expiresAt: number
}

export const REPORT_PROMPT_HISTORY_STORAGE_KEY = 'dashboard_report_prompt_history:v1'
export const REPORT_PROMPT_HISTORY_LIMIT = 4
export const REPORT_PROMPT_HISTORY_TTL_MS = 3 * 24 * 60 * 60 * 1000

function normalizeText(text: string) {
  return text.trim()
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
        updatedAt: Number(item?.updatedAt || 0),
        expiresAt: Number(item?.expiresAt || 0),
      }))
      .filter((item) => item.text && Number.isFinite(item.expiresAt))
  } catch {
    return []
  }
}

function persistHistory(storage: ReportPromptStorage, history: ReportPromptHistoryItem[]) {
  if (history.length === 0) {
    storage.removeItem(REPORT_PROMPT_HISTORY_STORAGE_KEY)
    return
  }
  storage.setItem(REPORT_PROMPT_HISTORY_STORAGE_KEY, JSON.stringify(history))
}

export function loadReportPromptHistory(
  storage: ReportPromptStorage,
  now = Date.now()
): ReportPromptHistoryItem[] {
  const history = parseHistory(storage.getItem(REPORT_PROMPT_HISTORY_STORAGE_KEY))
    .filter((item) => item.expiresAt > now)
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, REPORT_PROMPT_HISTORY_LIMIT)

  persistHistory(storage, history)
  return history
}

export function saveReportPromptHistory(
  storage: ReportPromptStorage,
  text: string,
  now = Date.now()
): ReportPromptHistoryItem[] {
  const normalizedText = normalizeText(text)
  if (!normalizedText) {
    return loadReportPromptHistory(storage, now)
  }
  const deduped = loadReportPromptHistory(storage, now).filter(
    (item) => item.text !== normalizedText
  )
  const history = [
    {
      text: normalizedText,
      updatedAt: now,
      expiresAt: now + REPORT_PROMPT_HISTORY_TTL_MS,
    },
    ...deduped,
  ].slice(0, REPORT_PROMPT_HISTORY_LIMIT)

  persistHistory(storage, history)
  return history
}
