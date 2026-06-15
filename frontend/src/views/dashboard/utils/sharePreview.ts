import html2canvas from 'html2canvas'

const PREVIEW_IMAGE_QUALITY = 0.72
const MAX_PREVIEW_WIDTH = 1280
const MAX_PREVIEW_HEIGHT = 720

const waitForSharePreviewPaint = async () => {
  await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))
  if (document.fonts?.ready) {
    await document.fonts.ready
  }
}

const compressCanvas = (source: HTMLCanvasElement) => {
  const scale = Math.min(
    1,
    MAX_PREVIEW_WIDTH / source.width,
    MAX_PREVIEW_HEIGHT / source.height
  )
  if (scale >= 1) {
    return source.toDataURL('image/jpeg', PREVIEW_IMAGE_QUALITY)
  }

  const target = document.createElement('canvas')
  target.width = Math.max(1, Math.round(source.width * scale))
  target.height = Math.max(1, Math.round(source.height * scale))
  const context = target.getContext('2d')
  if (!context) {
    return source.toDataURL('image/jpeg', PREVIEW_IMAGE_QUALITY)
  }
  context.fillStyle = '#f6f9fd'
  context.fillRect(0, 0, target.width, target.height)
  context.drawImage(source, 0, 0, target.width, target.height)
  return target.toDataURL('image/jpeg', PREVIEW_IMAGE_QUALITY)
}

export const captureDashboardSharePreview = async (target?: HTMLElement | null) => {
  const element =
    target ||
    document.querySelector<HTMLElement>('.dragAndResize') ||
    document.querySelector<HTMLElement>('#sq-preview-content .canvas-container') ||
    document.querySelector<HTMLElement>('.canvas-container')
  if (!element) return ''

  await waitForSharePreviewPaint()
  try {
    const canvas = await html2canvas(element, {
      backgroundColor: '#f6f9fd',
      scale: Math.min(2, window.devicePixelRatio || 1),
      useCORS: true,
      ignoreElements: (node) => {
        const elementNode = node as HTMLElement
        return !!elementNode.closest?.(
          '.component-bar-main, .dragHandle, .resizeHandle, .cloneNode, .positionBox, .coords'
        )
      },
    })
    return compressCanvas(canvas)
  } catch (error) {
    console.error('captureDashboardSharePreview', error)
    return ''
  }
}

export const captureElementSharePreview = async (target?: HTMLElement | null) => {
  if (!target) return ''

  await waitForSharePreviewPaint()
  try {
    const canvas = await html2canvas(target, {
      backgroundColor: '#ffffff',
      scale: Math.min(2, window.devicePixelRatio || 1),
      useCORS: true,
      ignoreElements: (node) => {
        const elementNode = node as HTMLElement
        return !!elementNode.closest?.('.component-bar-main, .dragHandle, .resizeHandle')
      },
    })
    return compressCanvas(canvas)
  } catch (error) {
    console.error('captureElementSharePreview', error)
    return ''
  }
}
