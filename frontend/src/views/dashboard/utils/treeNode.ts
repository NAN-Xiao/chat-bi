export interface SQTreeNode {
  id: string | number
  pid: string | number
  name: string
  leaf?: boolean
  weight: number
  type: string
  node_type: string
  datasource?: number | string
  can_edit?: boolean
  is_shared?: boolean
  share_id?: string
  children?: SQTreeNode[]
}

export interface SQTreeRequest {
  treeFlag?: string
  leaf?: boolean
  weight?: number
  sortType?: string
  resourceTable?: string
}
