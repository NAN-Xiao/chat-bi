export type ReportPopoverStyle = {
  width: string
  left: string
  top: string
  transform: string
  maxWidth: string
  maxHeight: string
  transformOrigin: string
  '--report-popover-max-height': string
}

type PlacementOptions = {
  width?: number
  height?: number
  minWidth?: number
  minHeight?: number
  gap?: number
  margin?: number
}

function clamp(value: number, min: number, max: number) {
  if (max < min) {
    return min
  }
  return Math.min(Math.max(value, min), max)
}

export function resolveReportPopoverStyle(
  trigger: HTMLElement | null | undefined,
  options: PlacementOptions = {}
): ReportPopoverStyle {
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0
  const margin = options.margin ?? 16
  const gap = options.gap ?? 8
  const preferredWidth = options.width ?? 420
  const preferredHeight = options.height ?? 560
  const minWidth = options.minWidth ?? 280
  const availableWidth = Math.max(240, viewportWidth - margin * 2)
  const availableHeight = Math.max(240, viewportHeight - margin * 2)
  const desiredWidth = Math.min(preferredWidth, availableWidth)
  const desiredHeight = Math.min(preferredHeight, availableHeight)
  const triggerRect = trigger?.getBoundingClientRect()

  if (!triggerRect) {
    return {
      width: `${Math.round(desiredWidth)}px`,
      left: `${Math.round(viewportWidth - margin - desiredWidth)}px`,
      top: `${margin}px`,
      transform: 'none',
      maxWidth: `${Math.round(availableWidth)}px`,
      maxHeight: `${Math.round(availableHeight)}px`,
      transformOrigin: 'top right',
      '--report-popover-max-height': `${Math.round(availableHeight)}px`,
    }
  }

  const triggerCenterX = triggerRect.left + triggerRect.width / 2
  const triggerCenterY = triggerRect.top + triggerRect.height / 2
  const spaceLeft = triggerRect.right - margin
  const spaceRight = viewportWidth - triggerRect.left - margin
  const spaceAbove = Math.max(0, triggerRect.top - margin - gap)
  const spaceBelow = Math.max(0, viewportHeight - triggerRect.bottom - margin - gap)
  const openToLeft =
    spaceRight < desiredWidth && spaceLeft >= spaceRight
      ? true
      : spaceLeft < desiredWidth && spaceRight > spaceLeft
        ? false
        : triggerCenterX >= viewportWidth / 2
  const openUp =
    spaceBelow < desiredHeight && spaceAbove >= spaceBelow
      ? true
      : spaceAbove < desiredHeight && spaceBelow > spaceAbove
        ? false
        : triggerCenterY >= viewportHeight / 2
  const sideWidth = Math.max(0, openToLeft ? spaceLeft : spaceRight)
  const sideHeight = Math.max(0, openUp ? spaceAbove : spaceBelow)
  const popoverWidth = Math.min(desiredWidth, Math.max(Math.min(minWidth, availableWidth), sideWidth))
  const popoverHeight = Math.min(desiredHeight, Math.max(80, sideHeight))
  const anchorLeft = openToLeft ? triggerRect.right : triggerRect.left
  const anchorTop = openUp ? triggerRect.top - gap : triggerRect.bottom + gap
  const minAnchorLeft = openToLeft ? margin + popoverWidth : margin
  const maxAnchorLeft = openToLeft
    ? viewportWidth - margin
    : viewportWidth - margin - popoverWidth
  const minAnchorTop = openUp ? margin + popoverHeight : margin
  const maxAnchorTop = openUp
    ? viewportHeight - margin
    : viewportHeight - margin - popoverHeight
  const left = clamp(anchorLeft, minAnchorLeft, maxAnchorLeft)
  const top = clamp(anchorTop, minAnchorTop, maxAnchorTop)
  const transform = `${openToLeft ? 'translateX(-100%)' : 'translateX(0)'} ${
    openUp ? 'translateY(-100%)' : 'translateY(0)'
  }`

  return {
    width: `${Math.round(popoverWidth)}px`,
    left: `${Math.round(left)}px`,
    top: `${Math.round(top)}px`,
    transform,
    maxWidth: `${Math.round(availableWidth)}px`,
    maxHeight: `${Math.round(popoverHeight)}px`,
    transformOrigin: `${openUp ? 'bottom' : 'top'} ${openToLeft ? 'right' : 'left'}`,
    '--report-popover-max-height': `${Math.round(popoverHeight)}px`,
  }
}
