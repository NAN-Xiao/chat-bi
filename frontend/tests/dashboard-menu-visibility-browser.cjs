// Run with playwright-cli run-code after opening the matching Vite fixture.
;async (page) => {
  const failures = []
  let checks = 0
  const check = (value, message) => {
    checks++
    if (!value) failures.push(message)
  }
  // DOM visibility alone cannot detect an opaque pseudo-element painted over text.
  // Read the rendered pixels in the real label's Range, excluding the icon/background.
  const textPixels = async (item) => {
    const geometry = await item.evaluate((element) => {
      const range = document.createRange()
      const node = [...element.childNodes].find(
        (child) => child.nodeType === Node.TEXT_NODE && child.textContent.trim()
      )
      range.selectNodeContents(node)
      const text = range.getBoundingClientRect()
      const box = element.getBoundingClientRect()
      return {
        x: text.left - box.left,
        y: text.top - box.top,
        width: text.width,
        height: text.height,
        color: getComputedStyle(element)
          .color.match(/[\d.]+/g)
          .slice(0, 3)
          .map(Number),
      }
    })
    const png = (await item.screenshot()).toString('base64')
    return page.evaluate(
      async ({ png, geometry }) => {
        const image = new Image()
        image.src = 'data:image/png;base64,' + png
        await image.decode()
        const canvas = document.createElement('canvas')
        canvas.width = image.width
        canvas.height = image.height
        const context = canvas.getContext('2d')
        context.drawImage(image, 0, 0)
        const data = context.getImageData(0, 0, canvas.width, canvas.height).data
        let count = 0
        for (
          let y = Math.max(0, Math.ceil(geometry.y));
          y < Math.min(canvas.height, geometry.y + geometry.height);
          y++
        ) {
          for (
            let x = Math.max(0, Math.ceil(geometry.x));
            x < Math.min(canvas.width, geometry.x + geometry.width);
            x++
          ) {
            const offset = (y * canvas.width + x) * 4
            if (geometry.color.every((channel, i) => Math.abs(data[offset + i] - channel) < 35))
              count++
          }
        }
        return count
      },
      { png, geometry }
    )
  }

  await page.waitForFunction(() => window.menuVisibilityQA)
  for (const theme of ['dark', 'light']) {
    // Exercise retained dark styles without changing the product's theme switch gate.
    await page.evaluate((value) => {
      const root = document.documentElement
      root.dataset.theme = value
      root.classList.toggle('dark', value === 'dark')
      root.classList.toggle('light', value === 'light')
      root.style.colorScheme = value
    }, theme)
    for (const fixture of ['canvas', 'readonly', 'resource', 'compact', 'create']) {
      await page.locator(`[data-fixture="${fixture}"] [role="button"]`).click()
      const menu = page.locator('.ed-dropdown__popper:visible [role="menu"]')
      await menu.waitFor()
      await page.getByRole('heading').hover()
      const items = menu.getByRole('menuitem')
      if (fixture === 'readonly') {
        check(
          JSON.stringify(await items.allTextContents()) === JSON.stringify(['预览', '共享']),
          theme + ' readonly menu preserves edit/delete permission boundaries'
        )
      }
      for (let index = 0; index < (await items.count()); index++) {
        const item = items.nth(index)
        const label = (await item.textContent()).trim()
        const disabled = (await item.getAttribute('aria-disabled')) === 'true'
        await page.getByRole('heading').hover()
        const baseline = await textPixels(item)
        check(baseline > 5, `${theme} ${fixture} ${label}: label paints normally`)
        await item.hover()
        const hovered = await textPixels(item)
        check(
          hovered >= baseline * 0.5,
          `${theme} ${fixture} ${label}: hover keeps label visible (${hovered}/${baseline} pixels)`
        )
        if (!disabled) {
          await item.focus()
          await page.getByRole('heading').hover()
          const focused = await textPixels(item)
          check(
            focused >= baseline * 0.5,
            `${theme} ${fixture} ${label}: keyboard focus keeps label visible`
          )
        } else {
          const before = await page.evaluate(() => menuVisibilityQA.events.length)
          await item.click({ force: true })
          check(
            (await page.evaluate(() => menuVisibilityQA.events.length)) === before,
            theme + ' disabled action cannot emit a command'
          )
        }
      }
      await page.keyboard.press('Escape')
      await menu.waitFor({ state: 'hidden' })
    }
  }
  for (const [fixture, label, event] of [
    ['canvas', '预览', 'preview'],
    ['canvas', '编辑 SQL', 'editSql'],
    ['resource', '编辑', 'edit'],
    ['compact', '编辑', 'edit'],
    ['create', '编辑', 'edit'],
  ]) {
    await page.locator(`[data-fixture="${fixture}"] [role="button"]`).click()
    const menu = page.locator('.ed-dropdown__popper:visible [role="menu"]')
    await menu.getByRole('menuitem', { name: label, exact: true }).click()
    check(
      (await page.evaluate(() => menuVisibilityQA.events.at(-1))) === event,
      fixture + ' click preserves ' + event + ' action'
    )
    await menu.waitFor({ state: 'hidden' })
  }
  if (failures.length) throw Error(failures.join('\n'))
  return { passed: checks }
}
