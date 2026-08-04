export type SmartQaErrorTranslate = (key: string) => string

const STATUS_KEYS: Record<number, string> = {
  400: 'chat.task_error.http_400',
  401: 'chat.task_error.http_401',
  403: 'chat.task_error.http_403',
  404: 'chat.task_error.http_404',
  422: 'chat.task_error.http_422',
  429: 'chat.task_error.http_429',
  500: 'chat.task_error.http_500',
  502: 'chat.task_error.http_502',
  503: 'chat.task_error.http_503',
  504: 'chat.task_error.http_504',
}

const ERROR_TYPE_KEYS: Record<string, string> = {
  permission_denied: 'chat.permission_denied_tip',
  data_unavailable: 'chat.task_error.data_unavailable',
}

const MESSAGE_FIELDS = ['detail', 'message', 'msg', 'error', 'data'] as const
const CHINESE_TEXT_PATTERN = /[\u3400-\u9fff\uf900-\ufaff]/
const NETWORK_ERROR_CODES = new Set(['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT'])
const MAX_NESTING_DEPTH = 6

function asRecord(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === 'object'
    ? (value as Record<string, unknown>)
    : undefined
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return undefined
  }
}

function findChineseMessage(
  value: unknown,
  depth = 0,
  seen = new Set<object>()
): string | undefined {
  if (depth > MAX_NESTING_DEPTH) {
    return undefined
  }
  if (typeof value === 'string') {
    const message = value.trim()
    if (!message) {
      return undefined
    }
    const parsed = parseJson(message)
    if (parsed !== undefined && parsed !== value) {
      return findChineseMessage(parsed, depth + 1, seen)
    }
    return CHINESE_TEXT_PATTERN.test(message) ? message : undefined
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = findChineseMessage(item, depth + 1, seen)
      if (message) {
        return message
      }
    }
    return undefined
  }
  const record = asRecord(value)
  if (!record || seen.has(record)) {
    return undefined
  }
  seen.add(record)
  for (const field of MESSAGE_FIELDS) {
    const message = findChineseMessage(record[field], depth + 1, seen)
    if (message) {
      return message
    }
  }
  return undefined
}

function findErrorType(value: unknown, depth = 0, seen = new Set<object>()): string | undefined {
  if (depth > MAX_NESTING_DEPTH) {
    return undefined
  }
  if (typeof value === 'string') {
    const text = value.trim()
    if (ERROR_TYPE_KEYS[text]) {
      return text
    }
    const parsed = parseJson(text)
    return parsed !== undefined && parsed !== value
      ? findErrorType(parsed, depth + 1, seen)
      : undefined
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const errorType = findErrorType(item, depth + 1, seen)
      if (errorType) {
        return errorType
      }
    }
    return undefined
  }
  const record = asRecord(value)
  if (!record || seen.has(record)) {
    return undefined
  }
  seen.add(record)
  const directType = record.error_type ?? record.errorType
  if (typeof directType === 'string' && ERROR_TYPE_KEYS[directType]) {
    return directType
  }
  for (const field of MESSAGE_FIELDS) {
    const errorType = findErrorType(record[field], depth + 1, seen)
    if (errorType) {
      return errorType
    }
  }
  return undefined
}

function numericStatus(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isInteger(value)) {
    return value
  }
  if (typeof value === 'string' && /^\d{3}$/.test(value)) {
    return Number(value)
  }
  return undefined
}

export function resolveSmartQaErrorMessage(
  error: unknown,
  translate: SmartQaErrorTranslate
): string {
  const root = asRecord(error)
  const response = asRecord(root?.response)
  const responseData = response?.data
  const payloads = responseData === undefined ? [error] : [responseData, error]

  for (const payload of payloads) {
    const chineseMessage = findChineseMessage(payload)
    if (chineseMessage) {
      return chineseMessage
    }
  }

  for (const payload of payloads) {
    const errorType = findErrorType(payload)
    if (errorType) {
      return translate(ERROR_TYPE_KEYS[errorType])
    }
  }

  const status = numericStatus(response?.status ?? root?.status)
  if (status && STATUS_KEYS[status]) {
    return translate(STATUS_KEYS[status])
  }

  const errorCode = typeof root?.code === 'string' ? root.code : undefined
  if ((!response && root && 'request' in root) || (errorCode && NETWORK_ERROR_CODES.has(errorCode))) {
    return translate('chat.task_error.network')
  }

  return translate('chat.task_error.generic')
}
