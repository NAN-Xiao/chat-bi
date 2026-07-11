import type { SQTreeNode } from '@/views/dashboard/utils/treeNode.ts'

export type SelectableDashboardOption = {
  id: string | number
  name: string
  level: number
}

export function flattenSelectableDashboardOptions(
  nodes: SQTreeNode[] = [],
  level = 0,
  result: SelectableDashboardOption[] = []
) {
  nodes.forEach((node) => {
    if (node?.node_type === 'leaf' || node?.leaf === true) {
      if (node.can_edit !== false && node.is_default !== true) {
        result.push({
          id: node.id,
          name: node.name,
          level,
        })
      }
      return
    }
    flattenSelectableDashboardOptions(node?.children || [], level + 1, result)
  })
  return result
}
