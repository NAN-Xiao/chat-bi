import {
  axisLabel,
  BaseChart,
  type ChartAxis,
  type ChartData,
  type ChartMountTarget,
} from '@/views/chat/component/BaseChart.ts'
import {
  copyToClipboard,
  type S2DataConfig,
  S2Event,
  type S2Options,
  type SortMethod,
  TableSheet,
  type SortFuncParam,
} from '@antv/s2'
import { debounce, filter } from 'lodash-es'
import { i18n } from '@/i18n'
import { formatValueByAxis } from '@/views/chat/component/charts/utils.ts'
import {
  collectTableFilterOptions,
  refreshFilteredTableData,
  searchTableFilterOptions,
  type TableFilters,
} from '@/views/chat/component/charts/tableFilter.ts'
import {
  TABLE_HEADER_ACTION_ICON_THEME,
  resolveTableHeaderActionIconFill,
} from '@/views/chat/component/charts/tableHeaderActions.ts'
import { CaretBottom, CaretTop, DCaret, Filter } from '@element-plus/icons-vue'
import { h, render, type Component } from 'vue'
import '@antv/s2/dist/s2.min.css'
import '@/views/chat/component/charts/tableFilter.css'

const { t } = i18n.global

const createSmartSortFunc = (sortMethod: string) => {
  const compareNumericString = (a: string, b: string): number => {
    const isNegA = a.startsWith('-')
    const isNegB = b.startsWith('-')

    // 负数 < 正数
    if (isNegA && !isNegB) return -1
    if (!isNegA && isNegB) return 1

    const [intA, decA = ''] = isNegA ? a.slice(1).split('.') : a.split('.')
    const [intB, decB = ''] = isNegB ? b.slice(1).split('.') : b.split('.')

    // 都是正数
    if (!isNegA && !isNegB) {
      if (intA.length !== intB.length) return intA.length - intB.length
      const intCmp = intA.localeCompare(intB)
      if (intCmp !== 0) return intCmp
      if (decA && decB) return decA.localeCompare(decB)
      return decA ? 1 : decB ? -1 : 0
    }

    // 都是负数：绝对值大的实际值小，比较结果取反
    if (intA.length !== intB.length) return -(intA.length - intB.length)
    const intCmp = intA.localeCompare(intB)
    if (intCmp !== 0) return -intCmp
    if (decA && decB) return -decA.localeCompare(decB)
    return decA ? 1 : decB ? -1 : 0
  }

  return (params: SortFuncParam) => {
    const { data, sortFieldId } = params
    if (!data || data.length === 0) return data ?? []
    const isAsc = sortMethod.toLowerCase() === 'asc'
    return [...data].sort((a: any, b: any) => {
      const valA = a[sortFieldId],
        valB = b[sortFieldId]
      if (valA == null) return isAsc ? -1 : 1
      if (valB == null) return isAsc ? 1 : -1
      const strA = String(valA),
        strB = String(valB)
      const isNumA = !isNaN(Number(strA)) && strA.trim() !== ''
      const isNumB = !isNaN(Number(strB)) && strB.trim() !== ''
      if (isNumA && !isNumB) return isAsc ? -1 : 1
      if (!isNumA && isNumB) return isAsc ? 1 : -1
      if (isNumA && isNumB) {
        const cmp = compareNumericString(strA, strB)
        return isAsc ? cmp : -cmp
      }
      const cmp = strA.localeCompare(strB)
      return isAsc ? cmp : -cmp
    })
  }
}

const TABLE_MIN_COLUMN_WIDTH = 92
const TABLE_HORIZONTAL_INSET = 8
const TABLE_HEADER_CELL_HEIGHT = 32
const TABLE_DATA_CELL_HEIGHT = 30
const TABLE_FILTER_ICON = 'TableFilter'
const TABLE_FILTER_ACTIVE_ICON = 'TableFilterActive'
const TABLE_SORT_NONE_ICON = 'TableSortNone'
const TABLE_SORT_ASC_ICON = 'TableSortAsc'
const TABLE_SORT_DESC_ICON = 'TableSortDesc'

function renderTableIconSvg(component: Component) {
  const container = document.createElement('span')
  render(h(component), container)
  const svg = container.innerHTML
  render(null, container)
  return svg
}

const tableFilterIconSvg = renderTableIconSvg(Filter)
const tableSortNoneIconSvg = renderTableIconSvg(DCaret)
const tableSortAscIconSvg = renderTableIconSvg(CaretTop)
const tableSortDescIconSvg = renderTableIconSvg(CaretBottom)

function resolveTableColumnWidth(containerWidth: number, visibleColumnCount: number) {
  return Math.max(
    TABLE_MIN_COLUMN_WIDTH,
    Math.floor(containerWidth / Math.max(visibleColumnCount, 1))
  )
}

function resolveTableContainerSize(container: Element | null) {
  if (!container) {
    return null
  }
  const width = Math.round(container.clientWidth)
  const height = Math.round(container.clientHeight)
  return width > 0 && height > 0 ? { width, height } : null
}

function resolveTableViewportHeight(containerHeight: number) {
  const minimumTableHeight = TABLE_HEADER_CELL_HEIGHT + TABLE_DATA_CELL_HEIGHT
  if (containerHeight <= minimumTableHeight) {
    return containerHeight
  }
  const availableDataHeight = containerHeight - TABLE_HEADER_CELL_HEIGHT
  const completeDataRows = Math.max(
    1,
    Math.floor(availableDataHeight / TABLE_DATA_CELL_HEIGHT)
  )
  return TABLE_HEADER_CELL_HEIGHT + completeDataRows * TABLE_DATA_CELL_HEIGHT
}

function resolveTableDisplayValue(
  value: any,
  axis?: Pick<ChartAxis, 'name' | 'value'> | null
): string {
  if (
    value === null ||
    value === undefined ||
    (typeof value === 'string' && value.trim().toLowerCase() === 'null')
  ) {
    return '-'
  }

  const formatted = formatValueByAxis(value, axis)
  if (
    formatted === null ||
    formatted === undefined ||
    (typeof formatted === 'string' && formatted.trim().toLowerCase() === 'null')
  ) {
    return '-'
  }

  return String(formatted)
}

export class Table extends BaseChart {
  table?: TableSheet = undefined

  container: Element | null = null

  debounceRender: any

  resizeObserver: ResizeObserver

  lastResizeWidth = 0

  lastResizeHeight = 0

  private tableFilters: TableFilters = new Map()

  private filterSourceData: S2DataConfig['data'] = []

  private filterPopup: HTMLDivElement | null = null

  private filterListenerTimer: number | null = null

  private filterDataUpdater: (() => Promise<void>) | null = null

  private handleFilterOutsidePointerDown = (event: PointerEvent) => {
    if (this.filterPopup && !this.filterPopup.contains(event.target as Node)) {
      this.closeFilterPopup()
    }
  }

  private handleFilterKeydown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') {
      this.closeFilterPopup()
    }
  }

  constructor(mountTarget: ChartMountTarget) {
    super(mountTarget, 'table')
    this.container =
      typeof mountTarget === 'string' ? document.getElementById(mountTarget) : mountTarget

    this.debounceRender = debounce(async (width?: number, height?: number) => {
      if (this.table && width && height) {
        const visibleColumnCount = this.axis?.filter((axis) => !axis.hidden).length ?? 0
        const contentWidth = Math.max(width - TABLE_HORIZONTAL_INSET, 320)
        const columnWidth = resolveTableColumnWidth(contentWidth, visibleColumnCount)
        const viewportHeight = resolveTableViewportHeight(height)

        this.table.setOptions({
          width: contentWidth,
          height: viewportHeight,
          style: {
            layoutWidthType: 'adaptive',
            colCell: {
              height: TABLE_HEADER_CELL_HEIGHT,
              width: columnWidth,
            },
            dataCell: {
              height: TABLE_DATA_CELL_HEIGHT,
              width: columnWidth,
            },
          },
        })
        this.table.changeSheetSize(contentWidth, viewportHeight)
        await this.table.render(false)
      }
    }, 200)

    this.resizeObserver = new ResizeObserver(() => {
      const size = resolveTableContainerSize(this.container)
      if (!size) return
      const { width, height } = size
      if (width === this.lastResizeWidth && height === this.lastResizeHeight) return
      this.lastResizeWidth = width
      this.lastResizeHeight = height
      this.debounceRender(width, height)
    })

    if (this.container) {
      this.resizeObserver.observe(this.container)
    }
  }

  private closeFilterPopup() {
    if (this.filterListenerTimer !== null) {
      window.clearTimeout(this.filterListenerTimer)
      this.filterListenerTimer = null
    }
    document.removeEventListener('pointerdown', this.handleFilterOutsidePointerDown)
    document.removeEventListener('keydown', this.handleFilterKeydown)
    this.filterPopup?.remove()
    this.filterPopup = null
  }

  private openFilterPopup(params: any) {
    const { meta } = params
    const field = meta?.field
    if (!meta?.isLeaf || !field) {
      return
    }

    this.closeFilterPopup()

    const options = collectTableFilterOptions(this.filterSourceData, field)
    const allOptionKeys = new Set(options.map((option) => option.key))
    let selectedValues = this.tableFilters.has(field)
      ? new Set(this.tableFilters.get(field))
      : new Set(allOptionKeys)

    const popup = document.createElement('div')
    popup.className = 'table-column-filter'
    popup.setAttribute('role', 'dialog')
    popup.setAttribute('aria-label', `${field} 列筛选`)

    const header = document.createElement('div')
    header.className = 'table-column-filter__header'

    const fieldAxis = this.axis?.find((axisItem) => axisItem.value === field)
    const title = document.createElement('strong')
    title.className = 'table-column-filter__title'
    title.textContent = fieldAxis ? axisLabel(fieldAxis) : field

    const selectionSummary = document.createElement('span')
    selectionSummary.className = 'table-column-filter__summary'
    header.append(title, selectionSummary)

    const searchInput = document.createElement('input')
    searchInput.className = 'table-column-filter__search'
    searchInput.type = 'search'
    searchInput.placeholder = '搜索值'
    searchInput.autocomplete = 'off'

    const actions = document.createElement('div')
    actions.className = 'table-column-filter__actions'

    const selectAllButton = document.createElement('button')
    selectAllButton.type = 'button'
    selectAllButton.textContent = '全选'

    const selectNoneButton = document.createElement('button')
    selectNoneButton.type = 'button'
    selectNoneButton.textContent = '全不选'

    const clearButton = document.createElement('button')
    clearButton.type = 'button'
    clearButton.textContent = '清除筛选'
    clearButton.className = 'table-column-filter__clear'

    actions.append(selectAllButton, selectNoneButton, clearButton)

    const optionList = document.createElement('div')
    optionList.className = 'table-column-filter__options'

    const footer = document.createElement('div')
    footer.className = 'table-column-filter__footer'
    footer.textContent = '候选值最多显示前 200 项'

    const updateSelectionSummary = () => {
      selectionSummary.textContent = `已选 ${selectedValues.size} / ${options.length}`
    }

    const commitSelection = () => {
      if (selectedValues.size === allOptionKeys.size) {
        this.tableFilters.delete(field)
      } else {
        this.tableFilters.set(field, new Set(selectedValues))
      }
      updateSelectionSummary()
      void this.filterDataUpdater?.()
    }

    const renderOptions = () => {
      optionList.replaceChildren()
      const visibleOptions = searchTableFilterOptions(options, searchInput.value)

      if (visibleOptions.length === 0) {
        const empty = document.createElement('div')
        empty.className = 'table-column-filter__empty'
        empty.textContent = '无匹配值'
        optionList.appendChild(empty)
        return
      }

      visibleOptions.forEach((option) => {
        const item = document.createElement('label')
        item.className = 'table-column-filter__option'

        const checkbox = document.createElement('input')
        checkbox.type = 'checkbox'
        checkbox.checked = selectedValues.has(option.key)
        checkbox.addEventListener('change', () => {
          if (checkbox.checked) {
            selectedValues.add(option.key)
          } else {
            selectedValues.delete(option.key)
          }
          commitSelection()
        })

        const label = document.createElement('span')
        label.className = 'table-column-filter__option-label'
        label.textContent = option.label

        const count = document.createElement('span')
        count.className = 'table-column-filter__option-count'
        count.textContent = String(option.count)

        item.append(checkbox, label, count)
        optionList.appendChild(item)
      })
    }

    searchInput.addEventListener('input', renderOptions)
    selectAllButton.addEventListener('click', () => {
      selectedValues = new Set(allOptionKeys)
      renderOptions()
      commitSelection()
    })
    selectNoneButton.addEventListener('click', () => {
      selectedValues = new Set()
      renderOptions()
      commitSelection()
    })
    clearButton.addEventListener('click', () => {
      selectedValues = new Set(allOptionKeys)
      renderOptions()
      commitSelection()
    })

    updateSelectionSummary()
    renderOptions()
    popup.append(header, searchInput, actions, optionList, footer)
    document.body.appendChild(popup)
    this.filterPopup = popup

    const canvasRect = this.table?.getCanvasElement().getBoundingClientRect()
    const sourceEvent = params.event as any
    const originalEvent = sourceEvent?.originalEvent
    const anchorX =
      originalEvent?.clientX ??
      sourceEvent?.clientX ??
      sourceEvent?.client?.x ??
      (canvasRect?.left ?? 0) + (meta.x ?? 0) + (meta.width ?? 0)
    const anchorY =
      originalEvent?.clientY ??
      sourceEvent?.clientY ??
      sourceEvent?.client?.y ??
      (canvasRect?.top ?? 0) + (meta.y ?? 0) + (meta.height ?? 0)
    const popupRect = popup.getBoundingClientRect()
    const viewportPadding = 8
    const left = Math.min(
      Math.max(anchorX - popupRect.width, viewportPadding),
      window.innerWidth - popupRect.width - viewportPadding
    )
    const top = Math.min(
      Math.max(anchorY + 6, viewportPadding),
      window.innerHeight - popupRect.height - viewportPadding
    )
    popup.style.left = `${left}px`
    popup.style.top = `${top}px`

    this.filterListenerTimer = window.setTimeout(() => {
      document.addEventListener('pointerdown', this.handleFilterOutsidePointerDown)
      document.addEventListener('keydown', this.handleFilterKeydown)
      this.filterListenerTimer = null
      searchInput.focus()
    })
  }

  init(axis: Array<ChartAxis>, data: Array<ChartData>) {
    this.closeFilterPopup()
    this.tableFilters.clear()
    super.init(
      filter(axis, (a) => !a.hidden), //隐藏多指标的other-info列
      data
    )
    this.filterSourceData = [...(this.data as S2DataConfig['data'])]

    const s2DataConfig: S2DataConfig = {
      sortParams:
        this.axis?.map((a) => {
          return {
            sortFieldId: a.value,
          }
        }) ?? [],
      fields: {
        columns: this.axis?.map((a) => a.value) ?? [],
      },
      meta:
        this.axis?.map((a) => {
          return {
            field: a.value,
            name: axisLabel(a),
            formatter: (value: any) => {
              return resolveTableDisplayValue(value, a)
            },
          }
        }) ?? [],
      data: this.data,
    }

    const sortState: Record<string, string> = {}
    let currentSortParams = s2DataConfig.sortParams ?? []

    this.filterDataUpdater = async () => {
      if (!this.table) {
        return
      }
      await refreshFilteredTableData(
        this.table,
        { ...s2DataConfig, sortParams: currentSortParams },
        this.filterSourceData,
        this.tableFilters
      )
    }

    const handleSortClick = (params: any) => {
      const { meta } = params
      const s2 = meta.spreadsheet
      if (s2 && meta.isLeaf) {
        const fieldId = meta.field
        const currentMethod = sortState[fieldId] || 'none'
        const sortOrder = ['none', 'desc', 'asc']
        const nextMethod = sortOrder[(sortOrder.indexOf(currentMethod) + 1) % sortOrder.length]
        sortState[fieldId] = nextMethod
        if (nextMethod === 'none') {
          currentSortParams = [{ sortFieldId: fieldId, sortMethod: 'none' as SortMethod }]
        } else {
          currentSortParams = [
            {
              sortFieldId: fieldId,
              sortMethod: nextMethod as SortMethod,
              sortFunc: createSmartSortFunc(nextMethod),
            },
          ]
        }
        s2.emit(S2Event.RANGE_SORT, currentSortParams)
        s2.render()
      }
    }

    const containerElement = this.container
    const visibleAxis = this.axis?.filter((a) => !a.hidden) ?? []
    const containerSize = resolveTableContainerSize(containerElement)
    const containerWidth = Math.max(
      (containerSize?.width || 600) - TABLE_HORIZONTAL_INSET,
      320
    )
    const containerHeight = containerSize?.height || 360
    const viewportHeight = resolveTableViewportHeight(containerHeight)
    const columnWidth = resolveTableColumnWidth(containerWidth, visibleAxis.length)

    const s2Options: S2Options = {
      width: containerWidth,
      height: viewportHeight,
      style: {
        layoutWidthType: 'adaptive',
        colCell: {
          height: TABLE_HEADER_CELL_HEIGHT,
          width: columnWidth,
        },
        dataCell: {
          height: TABLE_DATA_CELL_HEIGHT,
          width: columnWidth,
        },
      },
      showDefaultHeaderActionIcon: false,
      csp: { iconStrategy: 'path' },
      customSVGIcons: [
        { name: TABLE_FILTER_ICON, src: tableFilterIconSvg },
        { name: TABLE_FILTER_ACTIVE_ICON, src: tableFilterIconSvg },
        { name: TABLE_SORT_NONE_ICON, src: tableSortNoneIconSvg },
        { name: TABLE_SORT_ASC_ICON, src: tableSortAscIconSvg },
        { name: TABLE_SORT_DESC_ICON, src: tableSortDescIconSvg },
      ],
      headerActionIcons: [
        {
          icons: [
            { name: TABLE_FILTER_ACTIVE_ICON, fill: '#409eff', position: 'right' },
            { name: TABLE_FILTER_ICON, fill: '#909399', position: 'right' },
            { name: TABLE_SORT_DESC_ICON, fill: '#409eff', position: 'right' },
            { name: TABLE_SORT_ASC_ICON, fill: '#409eff', position: 'right' },
            { name: TABLE_SORT_NONE_ICON, fill: '#909399', position: 'right' },
          ],
          belongsCell: 'colCell',
          displayCondition: (node: any, iconName: string) => {
            if (!node.isLeaf) {
              return false
            }
            if (iconName === TABLE_FILTER_ACTIVE_ICON) {
              return this.tableFilters.has(node.field)
            }
            if (iconName === TABLE_FILTER_ICON) {
              return !this.tableFilters.has(node.field)
            }
            if (iconName === TABLE_SORT_DESC_ICON) {
              return sortState[node.field] === 'desc'
            }
            if (iconName === TABLE_SORT_ASC_ICON) {
              return sortState[node.field] === 'asc'
            }
            return (
              iconName === TABLE_SORT_NONE_ICON &&
              (!sortState[node.field] || sortState[node.field] === 'none')
            )
          },
          onHover: (params) => {
            const isFilter =
              params.name === TABLE_FILTER_ICON || params.name === TABLE_FILTER_ACTIVE_ICON
            const isActive = isFilter
              ? params.name === TABLE_FILTER_ACTIVE_ICON
              : params.name !== TABLE_SORT_NONE_ICON
            const icon = params.event?.currentTarget as
              | { setImageAttrs?: (attrs: { fill: string }) => void }
              | undefined
            icon?.setImageAttrs?.({
              fill: resolveTableHeaderActionIconFill(
                isFilter ? 'filter' : 'sort',
                isActive,
                params.hovering
              ),
            })
          },
          onClick: (params) => {
            if (params.name === TABLE_FILTER_ICON || params.name === TABLE_FILTER_ACTIVE_ICON) {
              this.openFilterPopup(params)
              return
            }
            handleSortClick(params)
          },
        },
      ],
      tooltip: {
        operation: {
          sort: true,
        },
        dataCell: {
          enable: true,
          content: (cell) => {
            const meta = cell.getMeta()
            const container = document.createElement('div')
            container.style.padding = '8px 0'
            container.style.minWidth = '100px'
            container.style.maxWidth = '400px'
            container.style.display = 'flex'
            container.style.alignItems = 'center'
            container.style.padding = '8px 16px'
            container.style.cursor = 'pointer'
            container.style.color = '#606266'
            container.style.fontSize = '14px'
            container.style.whiteSpace = 'pre-wrap'

            const axis = this.axis?.find((axisItem) => axisItem.value === meta.field)
            const formattedValue = resolveTableDisplayValue(meta.fieldValue, axis)
            const text = document.createTextNode(String(formattedValue))
            container.appendChild(text)

            return container
          },
        },
      },
      // 如果有省略号, 复制到的是完整文本
      interaction: {
        // 将滚动条放在内容边缘，避免横向滚动条覆盖最后一行数据。
        scrollbarPosition: 'content',
        copy: {
          enable: true,
          withFormat: false,
          withHeader: false,
        },
        brushSelection: {
          dataCell: true,
          rowCell: true,
          colCell: true,
        },
      },
      placeholder: {
        cell: '-',
        empty: {
          icon: 'Empty',
          description: 'No Data',
        },
      },
    }

    if (this.container) {
      this.table = new TableSheet(this.container, s2DataConfig, s2Options)
      this.table.setThemeCfg({
        theme: {
          colCell: {
            icon: TABLE_HEADER_ACTION_ICON_THEME,
          },
        },
      })
      // right click
      this.table.on(S2Event.GLOBAL_COPIED, (data) => {
        ElMessage.success(t('qa.copied'))
        console.debug('copied: ', data)
      })
      this.table.getCanvasElement().addEventListener('contextmenu', (event) => {
        event.preventDefault()
      })
      this.table.on(S2Event.GLOBAL_CONTEXT_MENU, (event) => copyData(event, this.table))
      // this.table.on(S2Event.RANGE_SORT, (sortParams) => {
      //   console.log('sortParams:', sortParams)
      // })
    }
  }

  render() {
    return this.table?.render()
  }

  destroy() {
    this.closeFilterPopup()
    this.tableFilters.clear()
    this.filterSourceData = []
    this.filterDataUpdater = null
    this.debounceRender?.cancel?.()
    this.table?.destroy()
    this.resizeObserver?.disconnect()
  }
}

function copyData(event: any, s2?: TableSheet) {
  event.preventDefault()
  if (!s2) {
    return
  }
  const cells = s2.interaction.getCells()

  if (cells.length == 0) {
    return
  } else if (cells.length == 1) {
    const c = cells[0]
    const cellMeta = s2.facet.getCellMeta(c.rowIndex, c.colIndex)
    if (cellMeta) {
      let value = cellMeta.fieldValue
      if (value === null || value === undefined) {
        value = '-'
      }
      value = value + ''
      copyToClipboard(value).finally(() => {
        ElMessage.success(t('qa.copied'))
        console.debug('copied:', cellMeta.fieldValue)
      })
    }
    return
  } else {
    let currentRowIndex = -1
    let currentRowData: Array<string> = []
    const rowData: Array<string> = []
    for (let i = 0; i < cells.length; i++) {
      const c = cells[i]
      const cellMeta = s2.facet.getCellMeta(c.rowIndex, c.colIndex)
      if (!cellMeta) {
        continue
      }
      if (currentRowIndex == -1) {
        currentRowIndex = c.rowIndex
      }
      if (c.rowIndex !== currentRowIndex) {
        rowData.push(currentRowData.join('\t'))
        currentRowData = []
        currentRowIndex = c.rowIndex
      }
      let value = cellMeta.fieldValue
      if (value === null || value === undefined) {
        value = '-'
      }
      value = value + ''
      currentRowData.push(value)
    }
    rowData.push(currentRowData.join('\t'))
    const finalValue = rowData.join('\n')
    copyToClipboard(finalValue).finally(() => {
      ElMessage.success(t('qa.copied'))
      console.debug('copied:\n', finalValue)
    })
  }
}
