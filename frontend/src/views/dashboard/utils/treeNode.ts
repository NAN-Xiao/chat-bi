export interface SQTreeNode {
  id: string | number
  pid: string | number
  name: string
  leaf?: boolean
  weight: number
  ext?: number
  extraFlag: number
  extraFlag1: number
  children?: SQTreeNode[]
}

export interface SQTreeRequest {
  treeFlag?: string
  leaf?: boolean
  weight?: number
  sortType?: string
  resourceTable?: string
}
