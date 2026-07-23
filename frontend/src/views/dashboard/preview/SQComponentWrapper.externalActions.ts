export type SQComponentWrapperRefreshResult = 'external' | 'fallback' | 'skipped'

export interface SQComponentWrapperRefreshOptions {
  refreshExecutor?: () => Promise<void>
  refreshing?: boolean
  fallback: () => Promise<void>
}

export async function runSQComponentWrapperRefresh(
  options: SQComponentWrapperRefreshOptions
): Promise<SQComponentWrapperRefreshResult> {
  if (options.refreshExecutor) {
    if (options.refreshing) return 'skipped'
    await options.refreshExecutor()
    return 'external'
  }
  await options.fallback()
  return 'fallback'
}

export function resolveSQComponentWrapperMoreActionsSlotProps(viewInfo: unknown) {
  return { viewInfo }
}
