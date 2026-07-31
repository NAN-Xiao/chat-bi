import type { SQTreeNode } from '@/views/dashboard/utils/treeNode.ts'

export type SelectableDashboardOption = {
  id: string | number
  name: string
  level: number
}

export function resolveDashboardMoveTargetDatasource(
  dashboardInfo?: Pick<SQTreeNode, 'datasource'> | null,
  _viewInfo?: Pick<SQTreeNode, 'datasource'> | null
): string | number | undefined {
  const datasource = dashboardInfo?.datasource
  return datasource === null || datasource === undefined || datasource === ''
    ? undefined
    : datasource
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
