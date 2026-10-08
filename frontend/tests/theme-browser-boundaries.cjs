async (page) => {
  const results = []
  const check = (v, m) => {
    if (!v) throw Error(m)
    results.push(m)
  }
  await page.reload()
  await page.waitForFunction(() => qa.ready.size === 4)
  await page.evaluate(async () => {
    qa.applyTheme('light')
    window.line = [...qa.instances].find((x) => x._name === 'line' && x.mountTarget.isConnected)
    line.chart.options({ ...line.chart.options(), slider: { x: {} } })
    await line.render()
    window.slider = line.chart.getContext().canvas.document.getElementsByClassName('slider')[0]
    slider.setValues([0.2, 0.8])
    qa.applyTheme('dark')
  })
  await page.waitForFunction(() => slider.attributes.handleLabelFill === '#8b9cb2')
  check(
    await page.evaluate(() => JSON.stringify(slider.getValues()) === '[0.2,0.8]'),
    'slider selection survives visual update'
  )
  await page.evaluate(async () => {
    line.chart.options({
      ...line.chart.options(),
      slider: { x: false },
      children: line.chart
        .options()
        .children.map((c) => ({ ...c, scrollbar: { x: { ratio: 0.5 } } })),
    })
    await line.render()
    window.scrollbar = line.chart
      .getContext()
      .canvas.document.getElementsByClassName('g2-scrollbar')[0]
    scrollbar.update({ value: 0.3 }, false)
    qa.applyTheme('light')
  })
  await page.waitForFunction(() => scrollbar.attributes.thumbFill === '#74849a')
  check(
    await page.evaluate(() => Math.abs(scrollbar.getValue() - 0.3) < 0.001),
    'scrollbar updates outer component and preserves position'
  )
  await page.evaluate(() => {
    qa.ready.clear()
    qa.types.value = ['heatmap']
  })
  await page.waitForFunction(() => qa.ready.has('heatmap'))
  await page.evaluate(async () => {
    window.heatmap = [...qa.instances].find(
      (x) => x._name === 'heatmap' && x.mountTarget.isConnected
    )
    heatmap.chart.options({
      ...heatmap.chart.options(),
      scale: {
        ...heatmap.chart.options().scale,
        color: { type: 'linear', range: ['#283343', '#79a6ff'] },
      },
    })
    await heatmap.render()
    window.legend = heatmap.chart
      .getContext()
      .canvas.document.getElementsByClassName('legend-continuous')[0]
    legend.update({ defaultValue: [90, 150] }, false)
    qa.applyTheme('dark')
  })
  await page.waitForFunction(() => legend.attributes.labelFill === '#8b9cb2')
  check(
    await page.evaluate(() => JSON.stringify(legend.selection) === '[90,150]'),
    'continuous legend range and text survive switch'
  )
  await page.evaluate(() => {
    qa.ready.clear()
    qa.types.value = ['line']
  })
  await page.waitForFunction(() => qa.ready.has('line'))
  await page.evaluate(async () => {
    window.line = [...qa.instances].find((x) => x._name === 'line' && x.mountTarget.isConnected)
    line.init(
      [
        { value: 'day', type: 'x' },
        { value: 'value', type: 'y' },
        { value: 'group', type: 'series' },
      ],
      [
        { day: '2026-08-01', value: 10, group: '' },
        { day: '2026-08-01', value: 20, group: 'A' },
        { day: '2026-08-01', value: 30, group: 'B' },
      ]
    )
    await line.render()
    qa.applyTheme('light')
  })
  await page.waitForFunction(
    () =>
      line.chart.getContext().canvas.document.getElementsByClassName('legend-category')[0]
        .attributes.itemLabelFill === '#65758c'
  )
  check(
    await page.evaluate(() => {
      const data = line.chart
        .getContext()
        .canvas.document.getElementsByClassName('legend-category')[0].attributes.data
      return data.find((d) => d.id === 'A').color === '#48c994'
    }),
    'legend colors follow domain identity with hidden empty category'
  )
  await page.evaluate(() => {
    localStorage.setItem('shuzhi-theme-mode', 'invalid')
    localStorage.setItem('qa-account-theme', 'light')
  })
  await page.reload()
  await page.waitForFunction(() => window.qa)
  check(
    await page.evaluate(() => qa.getCurrentTheme() === 'light'),
    'invalid preference defaults to light'
  )
  await page.emulateMedia({ colorScheme: 'dark' })
  check(
    await page.evaluate(
      () => qa.getCurrentTheme() === 'light' && document.documentElement.dataset.theme === 'light'
    ),
    'system dark preference cannot override explicit light'
  )
  const denied = await page.context().newPage()
  await denied.addInitScript(() => {
    const get = Storage.prototype.getItem,
      set = Storage.prototype.setItem
    Storage.prototype.getItem = function (key) {
      if (key.startsWith('shuzhi-theme-mode')) throw new DOMException('Storage denied', 'SecurityError')
      return get.call(this, key)
    }
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith('shuzhi-theme-mode')) throw new DOMException('Storage denied', 'SecurityError')
      return set.call(this, key, value)
    }
  })
  await denied.goto(page.url())
  await denied.waitForFunction(() => window.qa?.user.themeReady)
  await denied.getByRole('button', { name: '切换深色主题' }).click()
  check(
    await denied.evaluate(
      () => qa.getCurrentTheme() === 'dark' && document.documentElement.dataset.theme === 'dark'
    ),
    'blocked storage still permits in-session switching'
  )
  await denied.close()
  await page.emulateMedia({ colorScheme: 'light' })
  return results
}
