import type { G2Spec } from '@antv/g2'

const chartFontFamily = 'Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif'

export const chartPalette = [
  '#4f7df3',
  '#48c994',
  '#f07c64',
  '#f5bd4f',
  '#657a9b',
  '#50bfd2',
  '#7c8df6',
  '#f29a4b',
  '#8fa8c9',
  '#2faa78',
]

export const chartTheme = {
  color: chartPalette[0],
  category10: chartPalette,
  category20: [
    ...chartPalette,
    '#7fa6ff',
    '#70d9ad',
    '#ff9886',
    '#ffd06f',
    '#7d8fa9',
    '#68d0dc',
    '#a4afff',
    '#f7b06d',
    '#afc2dc',
    '#58c293',
  ],
  view: {
    viewFill: 'transparent',
    plotFill: 'transparent',
    mainFill: 'transparent',
    contentFill: 'transparent',
  },
  axis: {
    gridLineDash: [4, 6],
    gridLineWidth: 1,
    gridStroke: '#e7eef7',
    gridStrokeOpacity: 1,
    labelFill: '#74849a',
    labelOpacity: 1,
    labelFontFamily: chartFontFamily,
    labelFontSize: 11,
    labelFontWeight: 400,
    line: false,
    tick: false,
    titleFill: '#74849a',
    titleFontFamily: chartFontFamily,
    titleFontWeight: 500,
  },
  legendCategory: {
    itemLabelFill: '#65758c',
    itemLabelFillOpacity: 1,
    itemLabelFontFamily: chartFontFamily,
    itemLabelFontSize: 12,
    itemLabelFontWeight: 500,
    itemMarkerSize: 7,
    itemSpacing: [8, 12, 6],
    padding: 6,
  },
  legendContinuous: {
    labelFill: '#65758c',
    labelFillOpacity: 1,
    labelFontFamily: chartFontFamily,
    labelFontSize: 12,
    handleLabelFill: '#65758c',
    handleLabelFillOpacity: 1,
  },
  line: {
    line: {
      strokeOpacity: 1,
      lineWidth: 2.4,
      lineCap: 'round',
      lineJoin: 'round',
    },
  },
  point: {
    point: {
      r: 2.8,
      fillOpacity: 1,
      lineWidth: 1.4,
      stroke: '#ffffff',
    },
  },
  interval: {
    rect: {
      fillOpacity: 0.94,
    },
  },
  cell: {
    rect: {
      fillOpacity: 0.9,
    },
  },
  label: {
    fill: '#42526b',
    fillOpacity: 1,
    fontFamily: chartFontFamily,
    fontSize: 12,
    fontWeight: 500,
    connectorStroke: '#b7c4d8',
    connectorStrokeOpacity: 1,
  },
  tooltip: {
    css: {
      '.g2-tooltip': {
        'background-color': '#ffffff',
        'border-radius': '8px',
        border: '1px solid #e7edf6',
        'box-shadow': '0 14px 36px rgba(24, 46, 86, 0.14)',
        color: '#18263a',
        'font-family': chartFontFamily,
        'font-size': '12px',
        'z-index': 3000,
      },
    },
  },
} as const

export function withChartThemeOptions(options: G2Spec): G2Spec {
  return {
    ...options,
    scale: {
      ...options.scale,
      color: {
        range: chartPalette,
        ...(typeof options.scale?.color === 'object' ? options.scale.color : {}),
      },
    },
  }
}
