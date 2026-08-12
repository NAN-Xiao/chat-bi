export interface FloatingTooltipDismissalOptions {
  mount: HTMLElement
  hide: () => void
}

/**
 * G2 listens for pointerleave on its canvas scene, while our tooltip is mounted on body.
 * Keep the floating tooltip lifecycle tied to the owning DOM container as well so it
 * cannot remain visible after the pointer leaves, the page scrolls, or focus changes.
 */
export function bindFloatingTooltipDismissal({
  mount,
  hide,
}: FloatingTooltipDismissalOptions): () => void {
  const ownerDocument = mount.ownerDocument
  const ownerWindow = ownerDocument.defaultView

  const handlePointerLeave = () => hide()
  const handleDocumentPointerDown = (event: PointerEvent) => {
    if (!event.target || !mount.contains(event.target as Node)) {
      hide()
    }
  }
  const handleScroll = () => hide()
  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      hide()
    }
  }
  const handleVisibilityChange = () => {
    if (ownerDocument.hidden) {
      hide()
    }
  }

  mount.addEventListener('pointerleave', handlePointerLeave)
  ownerDocument.addEventListener('pointerdown', handleDocumentPointerDown, true)
  ownerDocument.addEventListener('scroll', handleScroll, true)
  ownerDocument.addEventListener('keydown', handleKeyDown)
  ownerDocument.addEventListener('visibilitychange', handleVisibilityChange)
  ownerWindow?.addEventListener('blur', hide)
  ownerWindow?.addEventListener('pagehide', hide)

  return () => {
    mount.removeEventListener('pointerleave', handlePointerLeave)
    ownerDocument.removeEventListener('pointerdown', handleDocumentPointerDown, true)
    ownerDocument.removeEventListener('scroll', handleScroll, true)
    ownerDocument.removeEventListener('keydown', handleKeyDown)
    ownerDocument.removeEventListener('visibilitychange', handleVisibilityChange)
    ownerWindow?.removeEventListener('blur', hide)
    ownerWindow?.removeEventListener('pagehide', hide)
  }
}
