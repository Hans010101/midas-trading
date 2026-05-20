/**
 * M1-Z · AI 决策卡 + 信号条 + 买卖点 overlay 截图(mock LLM)。
 *
 * 输出:
 *   - m1-z-ai-btc.png        · BTC/USDT · AI 决策卡 + 信号条 + 缠论开启(买卖点 overlay)
 *   - m1-z-ai-nvda.png       · NVDA · 同上
 *   - m1-z-ai-600519.png     · 600519 · 同上
 *   - m1-z-card-zoom.png     · 决策卡近景(右栏裁切)
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
  await page.waitForTimeout(4000) // K 线 + chan + AI 决策卡都要等
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
  await page.waitForTimeout(4000) // 初渲 + AI 决策卡 mock 响应

  // 开缠论 · 加密 BTC/USDT(默认)· 第一张
  await page.locator('section button[aria-pressed="false"]').first().click()
  await page.waitForTimeout(4000)
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-z-ai-btc.png') })
  console.log('  ✓ BTC/USDT + AI 决策卡 + 信号条 + 买卖点 overlay')

  // 美股 NVDA
  await switchMarket(page, '美股')
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-z-ai-nvda.png') })
  console.log('  ✓ NVDA + AI 决策卡')

  // A 股 600519
  await switchMarket(page, 'A 股')
  await page.screenshot({ path: path.join(OUT_DIR, 'm1-z-ai-600519.png') })
  console.log('  ✓ 600519 + AI 决策卡')

  // 决策卡近景(裁切右栏)
  const aside = page.locator('aside').last()
  const box = await aside.boundingBox()
  if (box) {
    await page.screenshot({
      path: path.join(OUT_DIR, 'm1-z-card-zoom.png'),
      clip: {
        x: box.x,
        y: box.y,
        width: box.width,
        height: Math.min(box.height, 900),
      },
    })
    console.log('  ✓ AI 决策卡 close-up')
  }

  await ctx.close()
  await browser.close()
  console.log('\n✓ 4 张截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
