export interface InsightFrameSize {
  width: number
  height: number
}

export interface InsightFrameGeometry {
  borderBox: InsightFrameSize
  borderInline: number
  borderBlock: number
  compactPaddingInline: number
  compactPaddingBlock: number
  compactHeaderHeight: number
  compactHeaderGap: number
  controlsBlock: number
}

export const INSIGHT_FRAME_CSS_PROPERTIES = {
  compactPaddingInline: '--insight-frame-compact-padding-inline',
  compactPaddingBlock: '--insight-frame-compact-padding-block',
  compactHeaderHeight: '--insight-frame-compact-header-height',
  compactHeaderGap: '--insight-frame-compact-header-gap',
} as const

const CSS_PIXEL_PATTERN = /^-?(?:\d+(?:\.\d+)?|\.\d+)px$/

export function parseCssPixel(value: string): number | null {
  const normalized = String(value || '').trim()
  if (!CSS_PIXEL_PATTERN.test(normalized)) return null
  const parsed = Number(normalized.slice(0, -2))
  return Number.isFinite(parsed) ? parsed : null
}

export function resolveCanonicalInsightFrame(
  geometry: InsightFrameGeometry
): InsightFrameSize | null {
  const values = [
    geometry.borderBox.width,
    geometry.borderBox.height,
    geometry.borderInline,
    geometry.borderBlock,
    geometry.compactPaddingInline,
    geometry.compactPaddingBlock,
    geometry.compactHeaderHeight,
    geometry.compactHeaderGap,
    geometry.controlsBlock,
  ]
  if (values.some((value) => !Number.isFinite(value) || value < 0)) return null

  const width = Math.round(
    geometry.borderBox.width - geometry.borderInline - geometry.compactPaddingInline * 2
  )
  const height = Math.round(
    geometry.borderBox.height
      - geometry.borderBlock
      - geometry.compactPaddingBlock * 2
      - geometry.compactHeaderHeight
      - geometry.compactHeaderGap
      - geometry.controlsBlock
  )
  return width > 0 && height > 0 ? { width, height } : null
}

export function sameInsightFrame(
  left: InsightFrameSize | null,
  right: InsightFrameSize | null
) {
  return left?.width === right?.width && left?.height === right?.height
}
