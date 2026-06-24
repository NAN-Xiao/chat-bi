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
  can_share?: boolean
  can_set_default?: boolean
  is_default?: boolean
  is_shared?: boolean
  is_public?: boolean
  is_platform_delegate_draft?: boolean
  is_platform_template?: boolean
  can_publish_delegate_draft?: boolean
  can_create_maintenance_draft?: boolean
  can_copy_to_platform_template?: boolean
  virtual?: boolean
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
