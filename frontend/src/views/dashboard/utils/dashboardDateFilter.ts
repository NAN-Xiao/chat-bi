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

const DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/
const dashboardDateFilterStates = new WeakMap<object, DashboardDateFilterState>()

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
