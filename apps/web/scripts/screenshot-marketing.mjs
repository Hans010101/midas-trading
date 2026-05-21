/**
 * M1-E A3 返工 · 重新生成首页用的营销截图。
 *
 * 要求(产品负责人 2026-05-21):
 *  - 全部 real LLM 模式(无 mock 徽章)
 *  - workbench 干净完整态(自选股无残缺红框,选中态自然)
 *  - chan 截图选「干净」一张,不带任何空态
 *
 * 输出到 apps/web/public/marketing/:
 *  - workbench.png   · 全工作台 NVDA(K + 缠论 + AI 卡)
 *  - chan.png        · 同 NVDA 但裁切到 K 线区(只露图)
 *  - ai-card.png     · 右栏 AI 决策卡近景(裁切)
 *
 * 这些图被 apps/web/app/page.tsx 引用。
 */

import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', 'public', 'marketing')

const EMAIL = 'hans@test.com'
const PASSWORD = 'Test123456'

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  // 登录(为了有真实虚拟资金 + AI 决策卡 cache 命中)
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.locator('button:has-text("登录")').click()
  await page.waitForURL('**/workbench', { timeout: 10_000 })
  await page.waitForTimeout(3000)

  // 切到美股 NVDA(界面最干净 · 数据完整)
  await page.locator('nav[aria-label="市场切换"] button:has-text("美股")').click()
  await page.waitForTimeout(2500)

  // 开缠论
  const chanToggle = page.locator('section button[aria-pressed="false"]').first()
  if (await chanToggle.count() > 0) {
    await chanToggle.click()
  }
  await page.waitForTimeout(4500)

  // ① workbench 全图 · 1440x900
  await page.screenshot({
    path: path.join(OUT_DIR, 'workbench.png'),
    fullPage: false,
  })
  console.log('  ✓ workbench.png')

  // ② chan · 只截 K 线区(裁切左工具栏 + 右自选栏)
  // K 线区大致在 x=70 ~ x=1160(扣掉左 60px 工具栏 + 右 280px 自选栏)
  // 含 header + signal-bar + chart-area 整列
  await page.screenshot({
    path: path.join(OUT_DIR, 'chan.png'),
    clip: { x: 70, y: 56, width: 1090, height: 820 },
  })
  console.log('  ✓ chan.png')

  // ③ ai-card · 右栏(280px 宽)整张完整 AI 决策卡 · 保留兼容
  await page.screenshot({
    path: path.join(OUT_DIR, 'ai-card.png'),
    clip: { x: 1160, y: 400, width: 280, height: 500 },
  })
  console.log('  ✓ ai-card.png')

  // ④ ai-card-top · 上半:header(VIRTUAL · 模拟)+ 综合评分圈 + 弱空标签 + 置信度
  await page.screenshot({
    path: path.join(OUT_DIR, 'ai-card-top.png'),
    clip: { x: 1160, y: 400, width: 280, height: 200 },
  })
  console.log('  ✓ ai-card-top.png')

  // ⑤ ai-card-bottom · 下半:关键位 + 技术面分析文字 + 缠论买卖点 + disclaimer
  await page.screenshot({
    path: path.join(OUT_DIR, 'ai-card-bottom.png'),
    clip: { x: 1160, y: 600, width: 280, height: 300 },
  })
  console.log('  ✓ ai-card-bottom.png')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 营销截图已更新到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
