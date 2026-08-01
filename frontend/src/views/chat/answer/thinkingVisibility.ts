export function initialThinkingVisibility(isTyping: boolean): boolean {
  return isTyping
}

export function isThinkingActive(isTyping: boolean, loading: boolean): boolean {
  return isTyping || loading
}

export function transitionThinkingVisibility(
  currentShow: boolean,
  previousTyping: boolean,
  currentTyping: boolean
): boolean {
  if (previousTyping === currentTyping) {
    return currentShow
  }
  return currentTyping
}
