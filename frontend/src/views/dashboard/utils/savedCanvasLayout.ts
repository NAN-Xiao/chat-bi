type SavedCanvasLayoutItem = {
  id?: string | number
  x: number
  y: number
  sizeX: number
  sizeY: number
}

export type SavedCanvasLayoutIssue = {
  type: 'invalid_frame' | 'overlap'
  itemIds: Array<string | number>
}

function itemId(item: SavedCanvasLayoutItem, index: number) {
  return item.id ?? index
}

function hasValidFrame(item: SavedCanvasLayoutItem, maxColumns: number) {
  const values = [item.x, item.y, item.sizeX, item.sizeY]
  return (
    values.every((value) => Number.isInteger(value)) &&
    item.x >= 1 &&
    item.y >= 1 &&
    item.sizeX >= 1 &&
    item.sizeY >= 1 &&
    item.x + item.sizeX - 1 <= maxColumns
  )
}

function overlaps(a: SavedCanvasLayoutItem, b: SavedCanvasLayoutItem) {
  return (
    a.x < b.x + b.sizeX &&
    a.x + a.sizeX > b.x &&
    a.y < b.y + b.sizeY &&
    a.y + a.sizeY > b.y
  )
}

export function validateSavedCanvasLayout(
  items: SavedCanvasLayoutItem[],
  maxColumns: number
): SavedCanvasLayoutIssue[] {
  const issues: SavedCanvasLayoutIssue[] = []
  const validItems: Array<{ item: SavedCanvasLayoutItem; index: number }> = []

  items.forEach((item, index) => {
    if (!hasValidFrame(item, maxColumns)) {
      issues.push({ type: 'invalid_frame', itemIds: [itemId(item, index)] })
      return
    }
    validItems.push({ item, index })
  })

  for (let i = 0; i < validItems.length; i++) {
    for (let j = i + 1; j < validItems.length; j++) {
      const left = validItems[i]
      const right = validItems[j]
      if (overlaps(left.item, right.item)) {
        issues.push({
          type: 'overlap',
          itemIds: [itemId(left.item, left.index), itemId(right.item, right.index)],
        })
      }
    }
  }

  return issues
}
