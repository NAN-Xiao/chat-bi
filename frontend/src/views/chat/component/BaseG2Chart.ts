import { BaseChart } from '@/views/chat/component/BaseChart.ts'
import { Chart } from '@antv/g2'
import { chartTheme } from '@/views/chat/component/charts/theme.ts'

export abstract class BaseG2Chart extends BaseChart {
  chart: Chart
  protected root: HTMLElement | null = null
  protected chartContainer: HTMLElement | null = null
  protected insightContainer: HTMLElement | null = null
  protected chartOverlay: HTMLElement | null = null

  constructor(id: string, name: string) {
    super(id, name)
    this.root = document.getElementById(id)
    this.root?.replaceChildren()
    this.chartContainer = this.createChartContainer(id)
    this.chart = new Chart({
      container: this.chartContainer ?? id,
      autoFit: true,
      padding: 'auto',
    })

    this.chart.theme(chartTheme)
  }

  render() {
    const rendered = this.chart?.render()
    if (rendered && typeof rendered.then === 'function') {
      void rendered.then(() => this.attachChartOverlay())
      return
    }
    this.attachChartOverlay()
  }

  destroy() {
    this.clearInsight()
    this.clearChartOverlay()
    this.chart?.destroy()
    this.root?.replaceChildren()
  }

  protected clearInsight() {
    if (!this.insightContainer) {
      return
    }
    this.insightContainer.replaceChildren()
    this.insightContainer.style.display = 'none'
  }

  protected setInsight(element?: HTMLElement) {
    if (!this.insightContainer) {
      return
    }
    this.clearInsight()
    if (!element) {
      return
    }
    this.insightContainer.appendChild(element)
    this.insightContainer.style.display = 'block'
  }

  protected clearChartOverlay() {
    this.chartOverlay?.remove()
    this.chartOverlay = null
  }

  protected setChartOverlay(element?: HTMLElement) {
    this.clearChartOverlay()
    if (element) {
      this.chartOverlay = element
    }
  }

  private createChartContainer(id: string): HTMLElement | null {
    if (!this.root) {
      return null
    }

    Object.assign(this.root.style, {
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      minHeight: '0',
      width: '100%',
    })

    this.insightContainer = document.createElement('div')
    Object.assign(this.insightContainer.style, {
      display: 'none',
      flex: '0 0 auto',
      minWidth: '0',
    })

    const container = document.createElement('div')
    container.id = `${id}-plot`
    Object.assign(container.style, {
      flex: '1 1 0',
      minHeight: '0',
      minWidth: '0',
      position: 'relative',
      width: '100%',
    })

    this.root.appendChild(this.insightContainer)
    this.root.appendChild(container)
    return container
  }

  private attachChartOverlay() {
    if (!this.chartContainer || !this.chartOverlay) {
      return
    }
    Object.assign(this.chartOverlay.style, {
      pointerEvents: 'none',
      position: 'absolute',
    })
    this.chartContainer.appendChild(this.chartOverlay)
  }
}
