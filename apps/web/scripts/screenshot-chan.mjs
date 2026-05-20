/**
 * M1 缠论 + 绘图工具栏截图。
 *
 * 输出:
 *   - m1-x-chan-btc.png · BTC/USDT 日 K + 缠论开启 · 笔/中枢/分型
 *   - m1-x-chan-nvda.png · NVDA 日 K + 缠论开启
 *   - m1-x-toolbar.png · 左栏绘图工具栏(M1 实装版)
 *   - m1-x-chan-off.png · 缠论关闭态对比
 */

import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'docs', 'screenshots')

const EMAIL = 'hans@test.com'
const PASSWORD = 'Test123456'

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.locator('button:has-text("登录")').click()
  await page.waitForURL('**/workbench', { timeout: 10_000 })
  await page.waitForTimeout(3000) // 等 K 线初渲

  // 截图 1: 缠论关 + 工具栏(默认态)
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-x-chan-off.png') })
  console.log('  ✓ 截图 1: 默认态 · 缠论关 · 工具栏可见')

  // 开缠论 · ChanToggle 是 chart-area 内 aria-pressed=false 的唯一按钮
  await page.locator('section button[aria-pressed="false"]').first().click()
  // 等 chan API + overlay 渲染
  await page.waitForTimeout(3500)
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-x-chan-btc.png') })
  console.log('  ✓ 截图 2: BTC/USDT + 缠论开启 · 笔/中枢/分型')

  // 切美股 NVDA
  await page.locator('nav[aria-label="市场切换"] button:has-text("美股")').click()
  await page.waitForTimeout(3000)
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-x-chan-nvda.png') })
  console.log('  ✓ 截图 3: NVDA + 缠论开启')

  // 工具栏 hover 局部图(crop 左栏)
  await page.locator('aside[aria-label="绘图工具栏"] button').first().hover()
  await page.waitForTimeout(500)
  const toolbar = page.locator('aside[aria-label="绘图工具栏"]')
  const box = await toolbar.boundingBox()
  if (box) {
    await page.screenshot({
      path: path.join(OUT_DIR, 'm1-x-toolbar.png'),
      clip: { x: box.x, y: box.y, width: 80, height: Math.min(box.height, 600) },
    })
    console.log('  ✓ 截图 4: 绘图工具栏 close-up')
  }

  await ctx.close()
  await browser.close()
  console.log('\n✓ 4 张截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
