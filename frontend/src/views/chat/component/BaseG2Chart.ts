import { BaseChart, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { Chart, type G2Spec } from '@antv/g2'
import { chartTheme } from '@/views/chat/component/charts/theme.ts'
import { bindFloatingTooltipDismissal } from '@/views/chat/component/floatingTooltipLifecycle.ts'

const TOOLTIP_MOUNT_SELECTOR = 'body'
const TOOLTIP_MARKER_OPTIONS = {
  markerR: 2.4,
  markerStroke: '#ffffff',
  markerLineWidth: 2,
  markerStrokeOpacity: 1,
}

function hasVisibleTooltip(options: Record<string, any>): boolean {
  if (!options || typeof options !== 'object') {
    return false
  }
  if (options.tooltip !== undefined && options.tooltip !== false) {
    return true
  }
  if (options.interaction?.tooltip !== undefined && options.interaction.tooltip !== false) {
    return true
  }
  return Array.isArray(options.children) && options.children.some(hasVisibleTooltip)
}

function withFloatingTooltip(options: G2Spec): G2Spec {
  const chartOptions = options as Record<string, any>
  const children = Array.isArray(chartOptions.children)
    ? chartOptions.children.map((child) =>
        child && typeof child === 'object' ? withFloatingTooltip(child as G2Spec) : child
      )
    : chartOptions.children

  if (!hasVisibleTooltip({ ...chartOptions, children })) {
    return { ...chartOptions, children } as G2Spec
  }

  const currentInteraction = chartOptions.interaction || {}
  const currentTooltip = currentInteraction.tooltip
  const tooltip =
    currentTooltip && typeof currentTooltip === 'object'
      ? { mount: TOOLTIP_MOUNT_SELECTOR, ...TOOLTIP_MARKER_OPTIONS, ...currentTooltip }
      : { mount: TOOLTIP_MOUNT_SELECTOR, ...TOOLTIP_MARKER_OPTIONS }

  return {
    ...chartOptions,
    children,
    interaction: {
      ...currentInteraction,
      tooltip,
    },
  } as G2Spec
}

export abstract class BaseG2Chart extends BaseChart {
  chart: Chart
  private removeTooltipDismissalListeners?: () => void
  private destroyed = false

  constructor(mountTarget: ChartMountTarget, name: string) {
    super(mountTarget, name)
    this.chart = new Chart({
      container: mountTarget,
      autoFit: true,
      padding: 'auto',
    })

    this.chart.theme(chartTheme)

    const mountElement =
      typeof mountTarget === 'string' ? document.getElementById(mountTarget) : mountTarget
    if (mountElement) {
      this.removeTooltipDismissalListeners = bindFloatingTooltipDismissal({
        mount: mountElement,
        hide: () => this.hideTooltip(),
      })
    }
  }

  render() {
    this.hideTooltip()
    this.chart?.options(withFloatingTooltip(this.chart.options() as G2Spec))
    return this.chart?.render()
  }

  private hideTooltip() {
    if (!this.destroyed) {
      this.chart?.emit('tooltip:hide', { nativeEvent: false })
    }
  }

  destroy() {
    if (this.destroyed) {
      return
    }
    this.hideTooltip()
    this.removeTooltipDismissalListeners?.()
    this.removeTooltipDismissalListeners = undefined
    this.destroyed = true
    this.chart?.destroy()
  }
}
