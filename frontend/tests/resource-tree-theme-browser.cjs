async (page) => {
  const sample = async (label) => {
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().map((a) => a.finished.catch(() => {})))
    })
    const rows = await page
      .locator(
        '.dashboard-resource-tree .ed-tree-node.is-current > .ed-tree-node__content, .access-nav-item'
      )
      .evaluateAll((nodes) =>
        nodes.map((row) => {
          const text = row.querySelector('.label-tooltip') || row.querySelector('span') || row
          const icon = row.querySelector('.tree-node-icon') || row.querySelector('.ed-icon')
          let surface = row
          while (
            surface.parentElement &&
            getComputedStyle(surface).backgroundColor === 'rgba(0, 0, 0, 0)'
          )
            surface = surface.parentElement
          const color = getComputedStyle(text).color,
            background = getComputedStyle(surface).backgroundColor,
            iconColor = icon ? getComputedStyle(icon).color : null
          const luminance = (c) => {
            const a = c
              .match(/[\d.]+/g)
              .slice(0, 3)
              .map(Number)
              .map((v) => {
                v /= 255
                return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
              })
            return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722
          }
          const contrast = (a, b) =>
            (Math.max(luminance(a), luminance(b)) + 0.05) /
            (Math.min(luminance(a), luminance(b)) + 0.05)
          return {
            label: text.textContent.trim(),
            color,
            background,
            iconColor,
            contrast: contrast(color, background),
            iconContrast: iconColor ? contrast(iconColor, background) : null,
          }
        })
      )
    if (rows.length !== 4) throw Error('Expected both resource-tree modes and access navigation')
    for (const row of rows)
      if (row.contrast < 4.5 || row.iconContrast < 3)
        throw Error(label + ' unreadable: ' + JSON.stringify(row))
    return { state: label, rows }
  }
  await page.waitForFunction(() => window.sidebarQA)
  const results = []
  for (const order of ['component-last', 'global-last']) {
    await page.evaluate((order) => {
      const styles = [...document.querySelectorAll('style[data-vite-dev-id]')]
      const moved = styles.filter((s) =>
        order === 'component-last'
          ? s.dataset.viteDevId.includes('ResourceTree.vue') ||
            s.dataset.viteDevId.includes('/access/index.vue')
          : s.dataset.viteDevId.endsWith('/src/style.less')
      )
      moved.forEach((s) => s.parentNode.appendChild(s))
    }, order)
    for (const theme of ['dark', 'light', 'dark']) {
      await page.evaluate((t) => sidebarQA.applyTheme(t), theme)
      await page.evaluate(() => (sidebarQA.selected.value = 'my-first'))
      await page.getByRole('heading').hover()
      results.push(await sample(theme + ' selected'))
      await page
        .locator('[data-tree-mode="menu"] .ed-tree-node.is-current > .ed-tree-node__content')
        .hover()
      results.push(await sample(theme + ' selected hovered'))
      await page.locator('[data-tree-mode="menu"] .ed-tree-node.is-current').focus()
      results.push(await sample(theme + ' keyboard focus'))
      await page.getByRole('heading').hover()
      for (const key of ['recommended-first', 'nested', 'my-second', 'recommended']) {
        await page.evaluate((k) => (sidebarQA.selected.value = k), key)
        await page.waitForFunction(
          (k) =>
            document.querySelector('[data-tree-mode="menu"] .ed-tree-node.is-current')?.dataset
              .key === k,
          key
        )
        results.push(await sample(theme + ' ' + key))
      }
    }
  }
  await page.evaluate(() => (sidebarQA.selected.value = 'my-first'))
  await page.screenshot({ path: '.playwright-cli/sidebar-readable-dark.png' })
  return {
    states: results.length,
    rows: results.flatMap((r) => r.rows).length,
    minTextContrast: Math.min(...results.flatMap((r) => r.rows.map((n) => n.contrast))),
    minIconContrast: Math.min(...results.flatMap((r) => r.rows.map((n) => n.iconContrast))),
  }
}
