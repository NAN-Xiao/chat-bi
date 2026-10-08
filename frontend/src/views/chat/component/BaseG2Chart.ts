import { BaseChart, type ChartMountTarget } from '@/views/chat/component/BaseChart.ts'
import { Chart, type G2Spec } from '@antv/g2'
import { getChartTheme } from '@/views/chat/component/charts/theme.ts'
import { bindFloatingTooltipDismissal } from '@/views/chat/component/floatingTooltipLifecycle.ts'
import { refreshStatefulGuide } from './g2ThemeGuides'

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
  private themeViewUpdates = new Set<() => Promise<unknown>>()
  // G2 supplies the same state reducer store used by legend/brush/slider interactions.
  // Updating this store keeps those selections, unlike calling Chart.render() again.
  private themeInteraction =
    () =>
    (context: {
      setState: (
        key: string,
        reducer: (options: Record<string, any>) => Record<string, any>
      ) => void
      update: () => Promise<{
        view: { scale: Record<string, { map: (value: unknown) => unknown }> }
      }>
      container: { getElementsByClassName: (name: string) => any[] }
    }) => {
      const update = async () => {
        const selections = new Map<any, Record<string, unknown>>()
        for (const guide of context.container.getElementsByClassName('slider')) {
          selections.set(guide, { values: [...guide.getValues()] })
        }
        for (const guide of context.container.getElementsByClassName('g2-scrollbar')) {
          selections.set(guide, { value: guide.getValue() })
        }
        for (const guide of context.container.getElementsByClassName('legend-continuous')) {
          selections.set(guide, { defaultValue: [...guide.selection] })
        }
        context.setState('color-theme', (options) => ({
          ...options,
          theme: getChartTheme(this.chart.getContainer()),
        }))
        const { view } = await context.update()
        if (!this.destroyed) this.refreshThemeGuides(context.container, view.scale, selections)
      }
      this.themeViewUpdates.add(update)
      return () => this.themeViewUpdates.delete(update)
    }

  constructor(mountTarget: ChartMountTarget, name: string) {
    super(mountTarget, name)
    this.chart = new Chart({
      container: mountTarget,
      autoFit: true,
      padding: 'auto',
    })

    this.chart.theme(getChartTheme(this.chart.getContainer()))

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
    this.chart.theme(getChartTheme(this.chart.getContainer()))
    const options = withFloatingTooltip(this.chart.options() as G2Spec)
    this.chart?.options({
      ...options,
      interaction: { ...options.interaction, colorTheme: { type: this.themeInteraction } },
    } as G2Spec)
    return this.chart?.render()
  }

  async updateTheme() {
    if (this.destroyed) return
    this.hideTooltip()
    this.chart.theme(getChartTheme(this.chart.getContainer()))
    await Promise.all([...this.themeViewUpdates].map((update) => update()))
    if (this.destroyed) return
  }

  private refreshThemeGuides(
    container: { getElementsByClassName: (name: string) => any[] },
    scales: Record<string, { map: (value: unknown) => unknown }>,
    selections: Map<any, Record<string, unknown>>
  ) {
    const theme = getChartTheme(this.chart.getContainer())
    for (const guide of container.getElementsByClassName('legend-category')) {
      const data = guide.attributes.data
      const colorScale = scales.color
      const isColorLegend = guide.attributes.scales?.some(
        (scale: { name: string }) => scale.name === 'color'
      )
      refreshStatefulGuide(guide, {
        ...theme.legendCategory,
        ...(colorScale && isColorLegend && Array.isArray(data)
          ? {
              data: data.map((item: Record<string, unknown>) => ({
                ...item,
                color: colorScale.map(item.id),
              })),
            }
          : {}),
      })
    }
    for (const guide of container.getElementsByClassName('legend-continuous')) {
      refreshStatefulGuide(guide, { ...theme.legendContinuous, ...selections.get(guide) })
    }
    for (const guide of container.getElementsByClassName('slider')) {
      refreshStatefulGuide(guide, { ...theme.slider, ...selections.get(guide) })
    }
    for (const guide of container.getElementsByClassName('g2-scrollbar')) {
      refreshStatefulGuide(guide, { ...theme.scrollbar, ...selections.get(guide) })
    }
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
    this.themeViewUpdates.clear()
    this.chart?.destroy()
  }
}
