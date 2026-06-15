import type { G2Spec } from '@antv/g2'

export const chartPalette = [
  '#5b8ff9',
  '#61d8a7',
  '#f08c6c',
  '#f6bd5b',
  '#6f84a8',
  '#56c7da',
  '#7d92ff',
  '#ffad66',
  '#9ab2d2',
  '#34b27b',
]

export const chartTheme = {
  color: chartPalette[0],
  category10: chartPalette,
  category20: [
    ...chartPalette,
    '#8bb1ff',
    '#75ddb2',
    '#ff9b9b',
    '#ffd37f',
    '#7d8da8',
    '#67d3dc',
    '#a6b3ff',
    '#f5b07f',
    '#b6c6dd',
    '#63c99e',
  ],
  view: {
    viewFill: 'transparent',
    plotFill: 'transparent',
    mainFill: 'transparent',
    contentFill: 'transparent',
  },
  axis: {
    gridLineDash: [3, 5],
    gridLineWidth: 1,
    gridStroke: '#edf2f8',
    gridStrokeOpacity: 1,
    labelFill: '#7c8ba2',
    labelOpacity: 1,
    labelFontSize: 12,
    line: false,
    tick: false,
    titleFill: '#7c8ba2',
  },
  legendCategory: {
    itemLabelFill: '#7c8ba2',
    itemLabelFillOpacity: 1,
    itemMarkerSize: 8,
    itemSpacing: [8, 14, 6],
    padding: 6,
  },
  legendContinuous: {
    labelFill: '#7c8ba2',
    labelFillOpacity: 1,
    handleLabelFill: '#7c8ba2',
    handleLabelFillOpacity: 1,
  },
  line: {
    line: {
      strokeOpacity: 1,
      lineWidth: 2.2,
      lineCap: 'round',
      lineJoin: 'round',
    },
  },
  point: {
    point: {
      r: 2.6,
      fillOpacity: 1,
      lineWidth: 1.4,
      stroke: '#ffffff',
    },
  },
  interval: {
    rect: {
      fillOpacity: 0.88,
    },
  },
  cell: {
    rect: {
      fillOpacity: 0.9,
    },
  },
  label: {
    fill: '#6c7d96',
    fillOpacity: 1,
    fontSize: 12,
    connectorStroke: '#b7c4d8',
    connectorStrokeOpacity: 1,
  },
  tooltip: {
    css: {
      '.g2-tooltip': {
        'background-color': '#ffffff',
        'border-radius': '14px',
        'border': '1px solid #eff4fa',
        'box-shadow': '0 18px 42px rgba(24, 46, 86, 0.12)',
        color: '#1b2a41',
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
