export interface DashboardSqlPreviewToken {
  session: number
  generation: number
  signature: string
}

export function createDashboardSqlPreviewSession() {
  let session = 0
  let generation = 0
  let open = false

  const invalidate = (nextOpen: boolean) => {
    session += 1
    generation = 0
    open = nextOpen
  }

  const isLatest = (token: DashboardSqlPreviewToken) =>
    open && token.session === session && token.generation === generation

  return {
    open() {
      invalidate(true)
    },
    close() {
      invalidate(false)
    },
    switchView() {
      invalidate(open)
    },
    begin(signature: string): DashboardSqlPreviewToken {
      generation += 1
      return { session, generation, signature }
    },
    refreshSignature(token: DashboardSqlPreviewToken, signature: string): boolean {
      if (!isLatest(token)) return false
      token.signature = signature
      return true
    },
    canCommit(token: DashboardSqlPreviewToken, currentSignature: string): boolean {
      return isLatest(token) && token.signature === currentSignature
    },
    isLatest,
  }
}
