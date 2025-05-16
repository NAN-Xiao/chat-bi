export interface CanvasItem  {
  _dragId: string | number
  x: number
  y: number
  sizeX: number
  sizeY: number
  [key: string]: any
}


export type CanvasCoord = {
  x1: number
  y1: number
  x2: number
  y2: number
  c1: number
  c2: number
  el: {
    x: number
    y: number
    sizeX: number
    sizeY: number
    _dragId: string | number
    [key: string]: any
  }
}