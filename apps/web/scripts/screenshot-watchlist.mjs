/**
 * Task 4-A · Checkpoint O · 自选股 4 张截图 + 端到端验收链路。
 *
 * 前置:
 *   1. docker compose 全栈 healthy
 *   2. 已通过 SQL 重置 hans-watchlist@midas.example:
 *        - DELETE watchlist_item · 清空
 *        - UPDATE user SET demo_prefilled = false
 *      (脚本启动时 GET /watchlist 会触发 lazy-fill 3 demo)
 *
 * 输出:
 *   - task-4a-o-watchlist-3-demo.png    (登录后看到 3 个 demo)
 *   - task-4a-o-cmdk-search.png         (Cmd+K 搜索弹窗 + 结果分组)
 *   - task-4a-o-drag-mid.png            (拖拽中状态)
 *   - task-4a-o-empty-state.png         (用户删光后 · 米白卡空态)
 *
 * 用法:
 *   node apps/web/scripts/screenshot-watchlist.mjs
 */

import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'docs', 'screenshots')

const EMAIL = 'hans-watchlist@midas.example'
const PASSWORD = 'testpass1234'

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  // ─── 步骤 1:登录 ──────────────────────────────────────────
  await page.goto('http://localhost:3000/login', { waitUntil: 'networkidle' })
  await page.locator('input[type="email"]').fill(EMAIL)
  await page.locator('input[type="password"]').fill(PASSWORD)
  await page.locator('button:has-text("登录")').click()
  await page.waitForURL('**/workbench', { timeout: 10_000 })
  // 等 watchlist API 请求 + lazy-fill + K 线渲染
  await page.waitForTimeout(2500)

  // ─── 截图 1:3 个 demo symbols(BTC/NVDA/600519)───────────
  await page.screenshot({ path: path.join(OUT_DIR, 'task-4a-o-watchlist-3-demo.png') })
  console.log('  ✓ 截图 1: 3 个 demo symbols')

  // ─── 截图 2:Cmd+K 搜索弹窗 + 输入 "AAPL" 后的结果分组 ──
  await page.keyboard.press('Meta+K')
  await page.waitForTimeout(400)
  await page.keyboard.type('A', { delay: 80 })
  // 后端 fuzzy match 拿不到太多 → 用 "A" 单字符触发更多结果
  await page.waitForTimeout(900)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-4a-o-cmdk-search.png') })
  console.log('  ✓ 截图 2: Cmd+K + 搜索 "A"')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  // ─── 截图 3:拖拽中(把 item-1 拖到 item-3 位置中段)────
  const grips = page.locator('button[aria-label="拖拽排序"]')
  const items = page.locator('aside.flex.w-\\[280px\\] ul > li')
  const firstGripBox = await grips.first().boundingBox()
  const thirdItemBox = await items.nth(2).boundingBox()
  if (firstGripBox && thirdItemBox) {
    const startX = firstGripBox.x + firstGripBox.width / 2
    const startY = firstGripBox.y + firstGripBox.height / 2
    await page.mouse.move(startX, startY)
    await page.mouse.down()
    // 先小幅移动触发 dnd-kit 的 activationConstraint(distance: 5)
    await page.mouse.move(startX + 8, startY + 8, { steps: 3 })
    // 然后慢慢移到 item-3 中段(模拟人手拖拽过程中)
    const midY = (startY + thirdItemBox.y + thirdItemBox.height / 2) / 2
    await page.mouse.move(startX, midY, { steps: 12 })
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(OUT_DIR, 'task-4a-o-drag-mid.png') })
    console.log('  ✓ 截图 3: 拖拽中')
    // 完成拖拽(移到 item-3 位置 + 松手 → 触发 reorder API)
    await page.mouse.move(startX, thirdItemBox.y + thirdItemBox.height + 4, { steps: 5 })
    await page.mouse.up()
    await page.waitForTimeout(800)
  } else {
    console.warn('  ⚠ 找不到 grip 或 item-3 的 bounding box,跳过 drag 截图')
  }

  // ─── 截图 4:删光 watchlist · 米白卡空态 ─────────────────
  // hover 每行 → 点删除按钮(按钮默认 opacity-0,hover 才出现)
  for (let i = 0; i < 6; i++) {
    const allItems = await items.all()
    if (allItems.length === 0) break
    const row = allItems[0]
    await row.hover()
    await page.waitForTimeout(200)
    const trash = row.locator('button[aria-label^="删除 "]')
    await trash.click({ force: true })
    await page.waitForTimeout(450) // 等乐观更新 + invalidate
  }
  await page.waitForTimeout(800)
  await page.screenshot({ path: path.join(OUT_DIR, 'task-4a-o-empty-state.png') })
  console.log('  ✓ 截图 4: 空态卡')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 4 张 watchlist 截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
