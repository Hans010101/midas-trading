/**
 * Task 6 · Checkpoint U · 推送配置 + 段 1 补丁截图。
 *
 * 输出:
 *   - task-6-u-settings-notifications.png    设置页 · 推送配置 UI(全空/未配置)
 *   - task-6-u-test-toast.png                测试发送失败 toast(假 webhook 必失败)
 *   - patch-a-symbol-switcher.png            工作台顶部 symbol 搜索切换弹窗
 *   - patch-b-account-wallet-section.png     /account 页 · 整合后的资金 + KPI
 *
 * 用 hans@test.com / Test123456 测试账号(已 verified)。
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

  // 登录
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.locator('button:has-text("登录")').click()
  await page.waitForURL('**/workbench', { timeout: 10_000 })
  await page.waitForTimeout(2500)

  // 段 1 补丁 A: 工作台顶部 SymbolSwitcher
  // 默认在加密 Tab,symbol = BTC/USDT
  await page.locator('button:has-text("BTC/USDT")').first().click()
  await page.waitForTimeout(800)
  // 输入 BTC 看看搜索效果
  await page.keyboard.type('B', { delay: 80 })
  await page.waitForTimeout(800)
  await page.screenshot({ path: path.join(OUT_DIR, 'patch-a-symbol-switcher.png') })
  console.log('  ✓ 截图 1: SymbolSwitcher')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  // 段 1 补丁 B: /account 页(整合后)
  await page.goto('http://localhost:3000/account', { waitUntil: 'networkidle' })
  await page.waitForTimeout(2500)
  await page.screenshot({
    path: path.join(OUT_DIR, 'patch-b-account-wallet-section.png'),
    fullPage: true,
  })
  console.log('  ✓ 截图 2: /account 整合页')

  // Task 6 U: /settings 推送配置
  await page.goto('http://localhost:3000/settings', { waitUntil: 'networkidle' })
  await page.waitForTimeout(2000)
  await page.screenshot({
    path: path.join(OUT_DIR, 'task-6-u-settings-notifications.png'),
    fullPage: true,
  })
  console.log('  ✓ 截图 3: /settings 推送配置')

  // 填假 webhook + 测试发送 → 必失败 toast
  await page.locator('input[id="feishu-url"]').fill(
    'https://open.feishu.cn/open-apis/bot/v2/hook/fake-test',
  )
  await page.locator('button:has-text("保存飞书配置")').click()
  await page.waitForTimeout(1500)
  // 点测试发送
  const feishuTestBtn = page.locator('button:has-text("发送测试")').first()
  await feishuTestBtn.click()
  // 等真实 HTTP 失败(假 webhook 飞书会返业务码错误)
  await page.waitForTimeout(3500)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-6-u-test-toast.png') })
  console.log('  ✓ 截图 4: 测试发送失败 toast')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 4 张截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
