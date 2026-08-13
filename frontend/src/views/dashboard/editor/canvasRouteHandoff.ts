export interface CanvasRouteHandoffPayload {
  sourceKey: string
  dashboardInfo: Record<string, any>
  canvasDataResult: any[]
  canvasStyleResult: Record<string, any>
  canvasViewInfoPreview: Record<string, any>
}

let pendingHandoff: CanvasRouteHandoffPayload | null = null

export const primeCanvasRouteHandoff = (payload: CanvasRouteHandoffPayload) => {
  pendingHandoff = payload
}

export const consumeCanvasRouteHandoff = (sourceKey: string | null | undefined) => {
  if (!sourceKey) {
    return null
  }
  const handoff = pendingHandoff
  pendingHandoff = null
  if (!handoff || handoff.sourceKey !== sourceKey) {
    return null
  }
  return handoff
}

export const clearCanvasRouteHandoff = () => {
  pendingHandoff = null
}
