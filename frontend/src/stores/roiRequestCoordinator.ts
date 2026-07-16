export type RoiPermissionOperation = 'config' | 'dashboards' | 'charts'

export type RoiRequestToken = {
  generation: number
  requestId: number
  requestKey: string
  permissionOperation: RoiPermissionOperation
}

type PermissionErrorState = {
  message: string
  sequence: number
}

export type RoiRequestState = {
  generation: number
  nextRequestId: number
  nextErrorSequence: number
  activeRequestIds: number[]
  latestRequestIds: Record<string, number>
  permissionErrors: Partial<Record<RoiPermissionOperation, PermissionErrorState>>
}

export const createRoiRequestState = (): RoiRequestState => ({
  generation: 0,
  nextRequestId: 0,
  nextErrorSequence: 0,
  activeRequestIds: [],
  latestRequestIds: {},
  permissionErrors: {},
})

const resolvePermissionOperation = (requestKey: string): RoiPermissionOperation => {
  if (requestKey.startsWith('charts')) return 'charts'
  return requestKey === 'config' ? 'config' : 'dashboards'
}

export const beginRoiRequest = (
  state: RoiRequestState,
  requestKey: string,
  permissionOperation = resolvePermissionOperation(requestKey)
): RoiRequestToken => {
  const requestId = ++state.nextRequestId
  const token = {
    generation: state.generation,
    requestId,
    requestKey,
    permissionOperation,
  }
  state.activeRequestIds.push(requestId)
  state.latestRequestIds[requestKey] = requestId
  delete state.permissionErrors[permissionOperation]
  return token
}

export const isLatestRoiRequest = (state: RoiRequestState, token: RoiRequestToken) =>
  token.generation === state.generation &&
  state.latestRequestIds[token.requestKey] === token.requestId

export const finishRoiRequest = (state: RoiRequestState, token: RoiRequestToken) => {
  if (token.generation !== state.generation) return false
  state.activeRequestIds = state.activeRequestIds.filter((id) => id !== token.requestId)
  return true
}

export const setRoiPermissionError = (
  state: RoiRequestState,
  token: RoiRequestToken,
  message: string
) => {
  if (!isLatestRoiRequest(state, token)) return false
  state.permissionErrors[token.permissionOperation] = {
    message,
    sequence: ++state.nextErrorSequence,
  }
  return true
}

export const getRoiPermissionError = (state: RoiRequestState) =>
  Object.values(state.permissionErrors).reduce<PermissionErrorState | undefined>(
    (latest, current) => (!latest || current.sequence > latest.sequence ? current : latest),
    undefined
  )?.message || ''

export const isRoiRequestLoading = (state: RoiRequestState) => state.activeRequestIds.length > 0

export const resetRoiRequests = (state: RoiRequestState) => {
  state.generation += 1
  state.activeRequestIds = []
  state.latestRequestIds = {}
  state.permissionErrors = {}
}
