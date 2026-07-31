export interface ChatUsageDisplay {
  showContainer: boolean
  showDuration: boolean
  showTotalTokens: boolean
}

function hasFiniteUsageValue(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value)
}

export function resolveChatUsageDisplay(
  duration?: number | null,
  totalTokens?: number | null
): ChatUsageDisplay {
  const showDuration = hasFiniteUsageValue(duration)
  const showTotalTokens = hasFiniteUsageValue(totalTokens)
  return {
    showContainer: showDuration || showTotalTokens,
    showDuration,
    showTotalTokens,
  }
}
