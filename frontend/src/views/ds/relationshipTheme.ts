import type { CellAttrs, Graph, NodeProperties } from '@antv/x6'

// SVG CSS variables keep defaults theme-independent when X6 serializes the graph.
export const relationshipColors = {
  border: 'var(--workspace-border)',
  top: 'var(--workspace-text-tertiary)',
  header: 'var(--workspace-control-bg)',
  surface: 'var(--workspace-card-bg)',
  text: 'var(--workspace-text-primary)',
  secondary: 'var(--workspace-text-secondary)',
}

export function normalizeGeneratedRelationshipPortStyles(ports: NodeProperties['ports']) {
  if (!ports || Array.isArray(ports)) return ports
  const attrs = ports.groups?.list?.attrs
  if (!attrs) return ports
  const themed = structuredClone(ports)
  const groupAttrs = themed.groups!.list.attrs!
  // Previous er-rect registration generated these exact defaults. X6 toJSON
  // includes inherited port groups; this editor exposes no color controls.
  // Per-port attrs and any non-default group colors remain authoritative.
  const stroke = groupAttrs.portBody?.stroke
  const fill = groupAttrs.portBody?.fill
  if (typeof stroke === 'string' && stroke.toLowerCase() === '#dee0e3') {
    groupAttrs.portBody.stroke = relationshipColors.border
  }
  if (typeof fill === 'string' && fill.toLowerCase() === '#ffffff') {
    groupAttrs.portBody.fill = relationshipColors.surface
  }
  if (!groupAttrs.portNameLabel?.fill) {
    groupAttrs.portNameLabel = { ...groupAttrs.portNameLabel, fill: relationshipColors.text }
  }
  return themed
}

export function themeRelationshipEdgeAttrs(attrs: CellAttrs = {}): CellAttrs {
  const themed = structuredClone(attrs)
  const stroke = themed.line?.stroke
  if (stroke == null || (typeof stroke === 'string' && stroke.toLowerCase() === '#dee0e3')) {
    themed.line = { ...themed.line, stroke: relationshipColors.border }
  }
  return themed
}

export function refreshRelationshipTheme(graph: Graph | null | undefined) {
  if (!graph) return
  // Update existing SVG views only. Never rebuild cells, serialize resolved
  // palette colors, change geometry, or reset the viewport on a theme switch.
  for (const cell of [...graph.getNodes(), ...graph.getEdges()]) {
    const view = cell.findView(graph)
    if (view?.isNodeView() || view?.isEdgeView()) view.update()
  }
}
