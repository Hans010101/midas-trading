/**
 * M1-Y · 缠论配色 v2 重新截图 · 笔=金 / 顶分型墨绿▽ / 底分型朱红△ / 中枢淡灰蓝矩形。
 *
 * 输出:
 *   - m1-y-chan-btc.png · BTC/USDT 日 K + 缠论开启(新配色)
 *   - m1-y-chan-nvda.png · NVDA 日 K + 缠论开启(新配色)
 *   - m1-y-chan-600519.png · 茅台 600519 日 K + 缠论开启(新配色)
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

async function switchMarket(page, marketLabel) {
  await page.locator(`nav[aria-label="市场切换"] button:has-text("${marketLabel}")`).click()
  await page.waitForTimeout(3500) // K 线 + chan 重拉
}

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
  await page.waitForTimeout(3000) // K 线初渲

  // 开缠论(默认市场 · 加密 BTC/USDT)
  await page.locator('section button[aria-pressed="false"]').first().click()
  await page.waitForTimeout(3500)
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-y-chan-btc.png') })
  console.log('  ✓ BTC/USDT + 缠论新配色')

  // 美股 NVDA
  await switchMarket(page, '美股')
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-y-chan-nvda.png') })
  console.log('  ✓ NVDA + 缠论新配色')

  // A 股 600519
  await switchMarket(page, 'A 股')
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-y-chan-600519.png') })
  console.log('  ✓ 600519 + 缠论新配色')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 3 张截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
