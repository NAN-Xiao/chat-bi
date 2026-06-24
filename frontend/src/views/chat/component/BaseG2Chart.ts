import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { Chart, type G2Spec } from '@antv/g2'
import { chartTheme } from '@/views/chat/component/charts/theme.ts'

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

  constructor(id: string, name: string) {
    super(id, name)
    this.chart = new Chart({
      container: id,
      autoFit: true,
      padding: 'auto',
    })

    this.chart.theme(chartTheme)
  }

  render() {
    this.chart?.options(withFloatingTooltip(this.chart.options() as G2Spec))
    this.chart?.render()
  }

  destroy() {
    this.chart?.destroy()
  }
}
