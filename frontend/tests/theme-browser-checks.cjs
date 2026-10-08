async (page) => {
  const results = []
  const check = (condition, message) => {
    if (!condition) throw Error(message)
    results.push(message)
  }
  await page.reload()
  await page.waitForFunction(
    () => window.qa && document.querySelectorAll('.chart-render-layer--active').length === 4
  )
  const noRequests = []
  const record = (req) => {
    if (req.url().includes('/api/')) noRequests.push(req.url())
  }
  page.on('request', record)
  await page.evaluate(() => {
    window.line = [...qa.instances].find((x) => x._name === 'line' && x.mountTarget.isConnected)
    line.chart.emit('legend:filter', {
      nativeEvent: false,
      data: { channel: 'color', values: ['A'] },
    })
  })
  await page.waitForFunction(
    () => line.chart.getContext().canvas.document.getElementsByClassName('element').length === 4
  )
  await page.evaluate(() => qa.applyTheme('light'))
  await page.waitForFunction(
    () =>
      line.chart.getContext().canvas.document.getElementsByClassName('legend-category')[0]
        .attributes.itemLabelFill === '#65758c'
  )
  await page.evaluate(() => qa.applyTheme('dark'))
  await page.waitForFunction(
    () =>
      line.chart.getContext().canvas.document.getElementsByClassName('legend-category')[0]
        .attributes.itemLabelFill === '#8b9cb2'
  )
  check(
    await page.evaluate(
      () =>
        line.mountTarget.isConnected &&
        line.chart.getContext().canvas.document.getElementsByClassName('element').length === 4
    ),
    'legend filtering survives switch on same chart instance'
  )
  check(
    await page.evaluate(() => {
      const legend = line.chart
        .getContext()
        .canvas.document.getElementsByClassName('legend-category')[0]
      const markers = legend.getElementsByClassName('legend-category-item-marker')
      return legend.attributes.data[0].color === '#79a6ff' && markers[1].style.fill === '#aaa'
    }),
    'legend colors update and disabled marker stays disabled'
  )
  await page.evaluate(() =>
    line.chart.emit('legend:filter', {
      nativeEvent: false,
      data: { channel: 'color', values: ['A', 'B'] },
    })
  )
  await page.waitForFunction(
    () => line.chart.getContext().canvas.document.getElementsByClassName('element').length === 8
  )
  check(
    await page.evaluate(() => {
      const markers = line.chart
        .getContext()
        .canvas.document.getElementsByClassName('legend-category-item-marker')
      return markers[1].style.fill === '#42d49a'
    }),
    'reselect restores new theme color'
  )
  // S2 keeps sort, column layout and scroll on the same instance.
  await page.evaluate(async () => {
    window.table = [...qa.instances].find((x) => x._name === 'table' && x.mountTarget.isConnected)
    table.table.setDataCfg({
      ...table.table.dataCfg,
      sortParams: [{ sortFieldId: 'value', sortMethod: 'DESC' }],
    })
    await table.table.render(true)
    table.table.interaction.scrollTo({ offsetY: { value: 120, animate: false } })
    window.tableState = {
      scroll: table.table.facet.getScrollOffset(),
      sort: JSON.stringify(table.table.dataCfg.sortParams),
    }
    qa.applyTheme('light')
  })
  await page.waitForFunction(
    () => table.table.getTheme().dataCell.cell.backgroundColor === '#ffffff'
  )
  check(
    await page.evaluate(
      () =>
        table.mountTarget.isConnected &&
        JSON.stringify(table.table.dataCfg.sortParams) === tableState.sort &&
        table.table.facet.getScrollOffset().scrollY === tableState.scroll.scrollY
    ),
    'table sort and scroll survive switch'
  )
  // Use actual date popper, already open during switch.
  await page.getByRole('combobox').first().click()
  await page.locator('.ed-date-range-picker').first().waitFor({ state: 'visible' })
  await page.evaluate(() => qa.applyTheme('dark'))
  await page.waitForFunction(
    () =>
      getComputedStyle(document.querySelector('.ed-picker-panel')).backgroundColor ===
      'rgb(40, 51, 67)'
  )
  await page.screenshot({ path: '.playwright-cli/theme-dark-calendar.png' })
  results.push('open date popper follows dark overlay tokens')
  await page.keyboard.press('Escape')
  await page.evaluate(() => {
    for (let i = 0; i < 20; i++) qa.applyTheme(i % 2 ? 'dark' : 'light')
  })
  await page.waitForFunction(() =>
    [...qa.instances]
      .filter((x) => x.chart && x.mountTarget.isConnected)
      .every(
        (x) => x.chart.getContext().canvas.document.getElementsByClassName('element').length > 0
      )
  )
  check(
    (await page.locator('.chart-component-validation-error').count()) === 0,
    'rapid switching keeps charts healthy'
  )
  check(noRequests.length === 0, 'theme switches issue no business requests')
  page.off('request', record)
  // Cross-tab state and refresh.
  const other = await page.context().newPage()
  await other.goto(page.url())
  await other.waitForFunction(() => window.qa?.user.themeReady)
  await other.evaluate(async () => { await qa.saveAccountTheme('dark'); await qa.saveAccountTheme('light') })
  await page.waitForFunction(() => qa.getCurrentTheme() === 'light')
  await other.close()
  await page.reload()
  await page.waitForFunction(() => window.qa)
  check(
    await page.evaluate(() => qa.getCurrentTheme() === 'light'),
    'cross-tab preference and refresh agree'
  )
  // Screen and zoom checks use real components in the fixture, not app navigation.
  for (const width of [1440, 1280, 1024, 768]) {
    await page.setViewportSize({ width, height: 1000 })
    for (const theme of ['light', 'dark']) {
      await page.evaluate((t) => qa.applyTheme(t), theme)
      await page.waitForFunction(
        () => document.querySelectorAll('.chart-render-layer--active').length === 4
      )
      await page.waitForFunction(
        () =>
          document.documentElement.scrollWidth <= innerWidth &&
          [...document.querySelectorAll('.qa-chart')].every((c) =>
            [...c.querySelectorAll('canvas')].every(
              (x) =>
                Math.abs(x.getBoundingClientRect().width - c.getBoundingClientRect().width) < 10
            )
          )
      )
      await page.screenshot({ path: '.playwright-cli/theme-' + theme + '-' + width + '.png' })
      check(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        'no fixture overflow ' + theme + ' ' + width
      )
    }
  }
  for (const zoom of [1.25, 2]) {
    await page.evaluate((z) => (document.body.style.zoom = z), zoom)
    await page.screenshot({ path: '.playwright-cli/theme-zoom-' + zoom + '.png' })
  }
  await page.evaluate(() => (document.body.style.zoom = '1'))
  // All registered renderer families, with synthetic fixtures only.
  for (const types of [
    ['bar', 'column', 'grouped_column', 'area'],
    ['pie', 'metric', 'scatter', 'boxplot'],
    ['heatmap', 'sankey', 'treemap', 'line'],
  ]) {
    await page.evaluate((v) => {
      qa.ready.clear()
      qa.types.value = v
    }, types)
    await page.waitForFunction((v) => v.every((t) => qa.ready.has(t)), types)
    await page.evaluate(() => qa.applyTheme('light'))
    await page.evaluate(() => qa.applyTheme('dark'))
    check(
      (await page.locator('.chart-component-validation-error').count()) === 0,
      'renderer group ' + types.join(',')
    )
  }
  // Switch during replacement and immediately unmount; late render errors must not leak.
  await page.evaluate(() => {
    qa.types.value = ['line', 'table', 'donut', 'metric']
    qa.applyTheme('light')
    qa.types.value = []
    qa.applyTheme('dark')
  })
  await page.waitForFunction(
    () => document.querySelectorAll('.chart-render-layer--active').length === 0
  )
  await page.evaluate(() => (qa.types.value = ['line', 'donut', 'funnel', 'table']))
  await page.waitForFunction(
    () => document.querySelectorAll('.chart-render-layer--active').length === 4
  )
  check(
    (await page.locator('.chart-component-validation-error').count()) === 0,
    'switch/unmount/remount has no stale error'
  )
  return results
}
