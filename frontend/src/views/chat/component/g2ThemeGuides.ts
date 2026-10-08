/**
 * G2 5 preserves filtered guides and caches original styles in __ordinal__.
 * Refresh both the visible component and that restoration cache, otherwise
 * reselecting a legend restores the previous theme. Keep guide/node identity.
 */
interface StatefulNode {
  children?: StatefulNode[]
  style: Record<string, unknown>
  __states__?: string[]
  __ordinal__?: Record<string, unknown>
  attr: (name: string, value: unknown) => unknown
}

export function refreshStatefulGuide(
  guide: {
    children?: StatefulNode[]
    update: (attributes: Record<string, unknown>, animate?: boolean) => unknown
  },
  attributes: Record<string, unknown>
) {
  const snapshots: { node: StatefulNode; active: boolean; values: Record<string, unknown> }[] = []
  function visit(node: StatefulNode) {
    if (node.__ordinal__) {
      snapshots.push({
        node,
        active: Boolean(node.__states__?.length),
        values: Object.fromEntries(
          Object.keys(node.__ordinal__).map((key) => [key, node.style[key]])
        ),
      })
    }
    node.children?.forEach(visit)
  }
  guide.children?.forEach(visit)
  guide.update(attributes, false)
  for (const { node, active, values } of snapshots) {
    for (const key of Object.keys(values)) {
      node.__ordinal__![key] = node.style[key]
      if (active) node.attr(key, values[key])
    }
  }
}
