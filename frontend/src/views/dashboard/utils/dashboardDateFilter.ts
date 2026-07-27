export type DashboardDateRange = [string, string]

export type DashboardDateCapabilityStatus =
  | 'available'
  | 'realtime'
  | 'unconfigured'
  | 'unsupported'
  | 'forbidden'

export type DashboardDateFilterCapability = {
  status?: DashboardDateCapabilityStatus | string
  defaultStart?: string
  defaultEnd?: string
  maxEnd?: string
  parameterType?: string
  reason?: string
}

export type DashboardDateFilterState = {
  draftRange: DashboardDateRange
  appliedRange: DashboardDateRange
  pendingRange: DashboardDateRange | null
  applying: boolean
  applyError: string
}

export type DashboardDateFilterContext = {
  identity: string
  status: string
}

export const dashboardDateParameterTokens = {
  date: ['{{dashboard_start_date}}', '{{dashboard_end_date}}'],
  yyyymmdd_number: ['{{dashboard_start_yyyymmdd}}', '{{dashboard_end_yyyymmdd}}'],
  yyyymmdd_text: ['{{dashboard_start_yyyymmdd}}', '{{dashboard_end_yyyymmdd}}'],
  timestamp: ['{{dashboard_start_timestamp}}', '{{dashboard_end_exclusive_timestamp}}'],
} as const

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const dashboardDateFilterStates = new WeakMap<object, DashboardDateFilterState>()
const dashboardChartRequestStates = new WeakMap<object, { version: number; foregroundActive: boolean }>()
const dashboardDateTokens = Array.from(new Set(Object.values(dashboardDateParameterTokens).flat()))

export function beginDashboardChartRequest(
  viewInfo: object,
  mode: 'foreground' | 'background' = 'foreground'
): number | null {
  const state = dashboardChartRequestStates.get(viewInfo) || {
    version: 0,
    foregroundActive: false,
  }
  if (mode === 'background') {
    dashboardChartRequestStates.set(viewInfo, state)
    return state.foregroundActive ? null : state.version
  }
  state.version += 1
  state.foregroundActive = true
  dashboardChartRequestStates.set(viewInfo, state)
  return state.version
}

export function isDashboardChartRequestCurrent(viewInfo: object, version: number | null): boolean {
  if (version === null) return false
  return dashboardChartRequestStates.get(viewInfo)?.version === version
}

export function finishDashboardChartRequest(viewInfo: object, version: number | null): void {
  const state = dashboardChartRequestStates.get(viewInfo)
  if (state && version !== null && state.version === version) {
    state.foregroundActive = false
  }
}

function copyRange(range: DashboardDateRange): DashboardDateRange {
  return [range[0], range[1]]
}

function parseNaturalDate(value: string): Date | null {
  const match = DATE_PATTERN.exec(String(value || ''))
  if (!match) return null
  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(Date.UTC(year, month - 1, day))
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) {
    return null
  }
  return parsed
}

function formatNaturalDate(value: Date): string {
  const year = value.getUTCFullYear()
  const month = String(value.getUTCMonth() + 1).padStart(2, '0')
  const day = String(value.getUTCDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function localTodayText(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function isValidRange(range: DashboardDateRange | null | undefined): range is DashboardDateRange {
  if (!range || range.length !== 2) return false
  const start = parseNaturalDate(range[0])
  const end = parseNaturalDate(range[1])
  return Boolean(start && end && start.getTime() <= end.getTime())
}

export function defaultDashboardDateRange(today = localTodayText()): DashboardDateRange {
  const parsedToday = parseNaturalDate(today)
  if (!parsedToday) return ['', '']
  const end = new Date(parsedToday.getTime())
  end.setUTCDate(end.getUTCDate() - 1)
  const start = new Date(end.getTime())
  start.setUTCDate(start.getUTCDate() - 13)
  return [formatNaturalDate(start), formatNaturalDate(end)]
}

export function canShowDashboardDateFilter(
  capability: DashboardDateFilterCapability | null | undefined
): boolean {
  return capability?.status === 'available'
}

export function createDashboardDateFilterState(
  capability: DashboardDateFilterCapability | null | undefined,
  today?: string
): DashboardDateFilterState {
  const configuredRange: DashboardDateRange = [
    String(capability?.defaultStart || ''),
    String(capability?.defaultEnd || ''),
  ]
  const initialRange = isValidRange(configuredRange)
    ? configuredRange
    : defaultDashboardDateRange(today)
  return {
    draftRange: copyRange(initialRange),
    appliedRange: copyRange(initialRange),
    pendingRange: null,
    applying: false,
    applyError: '',
  }
}

export function registerDashboardDateFilterState(
  viewInfo: object,
  state: DashboardDateFilterState
): DashboardDateFilterState {
  dashboardDateFilterStates.set(viewInfo, state)
  return state
}

export function getOrCreateDashboardDateFilterState(
  viewInfo: object,
  capability: DashboardDateFilterCapability | null | undefined,
  today?: string
): DashboardDateFilterState {
  const existing = dashboardDateFilterStates.get(viewInfo)
  if (existing) return existing
  return registerDashboardDateFilterState(
    viewInfo,
    createDashboardDateFilterState(capability, today)
  )
}

export function isDashboardDateApplyDisabled(
  state: DashboardDateFilterState,
  capability?: DashboardDateFilterCapability | null
): boolean {
  if (state.applying || !isValidRange(state.draftRange)) return true
  if (capability?.maxEnd) {
    const maxEnd = parseNaturalDate(capability.maxEnd)
    const draftEnd = parseNaturalDate(state.draftRange[1])
    if (!maxEnd || !draftEnd || draftEnd.getTime() > maxEnd.getTime()) return true
  }
  return state.draftRange[0] === state.appliedRange[0]
    && state.draftRange[1] === state.appliedRange[1]
}

export function buildDashboardDatePivot(
  viewInfo: { pivot?: Record<string, unknown> | null } | null | undefined,
  range: DashboardDateRange
): Record<string, unknown> {
  return {
    ...(viewInfo?.pivot && typeof viewInfo.pivot === 'object' ? viewInfo.pivot : {}),
    range: 'custom',
    custom_start: range[0],
    custom_end: range[1],
  }
}

export function buildDashboardDateSourcePreviewPivot(
  pivot: Record<string, unknown>
): Record<string, unknown> {
  return {
    ...pivot,
    enabled: false,
  }
}

export function buildAppliedDashboardDatePivot(
  viewInfo: {
    pivot?: Record<string, unknown> | null
    dateFilterCapability?: DashboardDateFilterCapability | null
  } & object,
  pivot: Record<string, unknown> | undefined = viewInfo.pivot || undefined
): Record<string, unknown> | undefined {
  if (!canShowDashboardDateFilter(viewInfo.dateFilterCapability)) return pivot
  const state = getOrCreateDashboardDateFilterState(viewInfo, viewInfo.dateFilterCapability)
  return buildDashboardDatePivot({ pivot }, state.appliedRange)
}

export function applyDashboardDateFilterCapability(
  viewInfo: ({ dateFilterCapability?: DashboardDateFilterCapability | null } & object) | null | undefined,
  result: { date_filter_capability?: DashboardDateFilterCapability | null } | null | undefined
): DashboardDateFilterCapability | null {
  const capability = result?.date_filter_capability
  if (!viewInfo || !capability || typeof capability !== 'object') return null
  viewInfo.dateFilterCapability = { ...capability }
  if (canShowDashboardDateFilter(capability)) {
    getOrCreateDashboardDateFilterState(viewInfo, capability)
  }
  return viewInfo.dateFilterCapability
}

export function dashboardDateFilterContext(
  viewInfo: { id?: unknown; sql?: unknown } | null | undefined,
  capability: DashboardDateFilterCapability | null | undefined
): DashboardDateFilterContext {
  return {
    identity: `${String(viewInfo?.id || '')}:${String(viewInfo?.sql || '')}`,
    status: String(capability?.status || ''),
  }
}

export function shouldInitializeDashboardDateFilterState(
  previous: DashboardDateFilterContext | null | undefined,
  next: DashboardDateFilterContext
): boolean {
  if (!previous) return true
  return previous.identity !== next.identity
    || (previous.status !== 'available' && next.status === 'available')
}

export function shouldResetDashboardDateFilterState(
  previous: DashboardDateFilterContext,
  next: DashboardDateFilterContext,
  sameViewInfo: boolean
): boolean {
  if (sameViewInfo && previous.identity !== next.identity) return true
  return previous.identity === next.identity
    && previous.status !== 'available'
    && next.status === 'available'
}

export function scanDashboardDateParameterTokens(sql: string): string[] {
  const active = new Set<string>()
  let state = 'normal'
  let dollarQuote = ''
  let index = 0

  while (index < sql.length) {
    const char = sql[index]
    const following = sql[index + 1] || ''
    if (state === 'normal') {
      const token = dashboardDateTokens.find((item) => sql.startsWith(item, index))
      if (token) {
        active.add(token)
        index += token.length
        continue
      }
      if (char === "'") state = 'single'
      else if (char === '"') state = 'double'
      else if (char === '`') state = 'backtick'
      else if (char === '[') state = 'bracket'
      else if ((char === '-' && following === '-') || char === '#') state = 'line_comment'
      else if (char === '/' && following === '*') state = 'block_comment'
      else if (char === '$') {
        const closing = sql.indexOf('$', index + 1)
        const candidate = closing >= 0 ? sql.slice(index, closing + 1) : ''
        const tag = candidate.slice(1, -1)
        const validTag = !tag || /^[A-Za-z_][A-Za-z0-9_]*$/.test(tag)
        if (candidate && validTag) {
          state = 'dollar_quote'
          dollarQuote = candidate
          index += candidate.length
          continue
        }
      }
      index += 1
      continue
    }

    if (state === 'dollar_quote' && sql.startsWith(dollarQuote, index)) {
      index += dollarQuote.length
      state = 'normal'
      dollarQuote = ''
      continue
    }
    index += 1
    if (['single', 'double', 'backtick'].includes(state) && char === '\\' && following) {
      index += 1
    } else if (state === 'single' && char === "'") {
      if (following === "'") index += 1
      else state = 'normal'
    } else if (state === 'double' && char === '"') {
      if (following === '"') index += 1
      else state = 'normal'
    } else if (state === 'backtick' && char === '`') {
      if (following === '`') index += 1
      else state = 'normal'
    } else if (state === 'bracket' && char === ']') {
      if (following === ']') index += 1
      else state = 'normal'
    } else if (state === 'line_comment' && (char === '\r' || char === '\n')) {
      state = 'normal'
    } else if (state === 'block_comment' && char === '*' && following === '/') {
      index += 1
      state = 'normal'
    }
  }

  return dashboardDateTokens.filter((token) => active.has(token))
}

export function beginDashboardDateApply(state: DashboardDateFilterState): void {
  state.pendingRange = copyRange(state.draftRange)
  state.applying = true
  state.applyError = ''
}

export function commitDashboardDateRange(state: DashboardDateFilterState): void {
  state.appliedRange = copyRange(state.pendingRange || state.draftRange)
  state.pendingRange = null
  state.applying = false
  state.applyError = ''
}

export function failDashboardDateRange(state: DashboardDateFilterState, message = ''): void {
  state.pendingRange = null
  state.applying = false
  state.applyError = message
}
