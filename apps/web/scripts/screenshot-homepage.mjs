/**
 * M1-E · 首页静态官网分段截图 · 给产品负责人验收。
 *
 * 输出 6 张:
 *   - m1-e-home-hero.png       · Hero 区(首屏)
 *   - m1-e-home-showcase.png   · 产品实拍区
 *   - m1-e-home-markets.png    · 三市场 + 核心功能(上下连看)
 *   - m1-e-home-aichan.png     · AI + 缠论差异化重点区
 *   - m1-e-home-pricing.png    · 定价 + 底部 CTA
 *   - m1-e-home-footer.png     · 完整页脚
 *   - m1-e-home-full.png       · 整页 fullPage 截图(归档)
 */

import { chromium } from 'playwright'
import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const OUT_DIR = path.resolve(__dirname, '..', '..', '..', 'docs', 'screenshots')

async function captureSection(page, selector, filename) {
  const el = page.locator(selector)
  await el.scrollIntoViewIfNeeded()
  await page.waitForTimeout(500) // 等图片 + 字体渲染
  const box = await el.boundingBox()
  if (!box) {
    console.warn(`  ✗ ${filename}: locator no boundingBox · skip`)
    return
  }
  await page.screenshot({
    path: path.join(OUT_DIR, filename),
    clip: {
      x: Math.max(box.x, 0),
      y: Math.max(box.y, 0),
      width: box.width,
      height: box.height,
    },
  })
  console.log(`  ✓ ${filename}`)
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true })

  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  await page.goto('http://localhost:3000/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(2000) // 字体 + 图片

  // Hero(包含 TopNav · 因为是 sticky 第一屏)
  await page.screenshot({
    path: path.join(OUT_DIR, 'm1-e-home-hero.png'),
    fullPage: false,
  })
  console.log('  ✓ m1-e-home-hero.png(首屏 Hero + TopNav)')

  // 各区块独立截图(scroll into view 后裁切)
  await captureSection(page, 'section#showcase', 'm1-e-home-showcase.png')
  await captureSection(page, 'section#ai-chan', 'm1-e-home-aichan.png')
  await captureSection(page, 'section#pricing', 'm1-e-home-pricing.png')
  await captureSection(page, 'footer', 'm1-e-home-footer.png')

  // 三市场 + 核心功能合一张(上下相邻的两个 section)
  const marketsSection = page.locator('section').nth(2) // 第 3 个 section · markets
  await marketsSection.scrollIntoViewIfNeeded()
  await page.waitForTimeout(500)
  const marketBox = await marketsSection.boundingBox()
  if (marketBox) {
    // 多截 600px 包括下方 features 区
    await page.screenshot({
      path: path.join(OUT_DIR, 'm1-e-home-markets.png'),
      clip: {
        x: 0,
        y: marketBox.y,
        width: 1440,
        height: marketBox.height + 750,
      },
    })
    console.log('  ✓ m1-e-home-markets.png(三市场 + 核心功能合一)')
  }

  // 整页归档截图
  await page.screenshot({
    path: path.join(OUT_DIR, 'm1-e-home-full.png'),
    fullPage: true,
  })
  console.log('  ✓ m1-e-home-full.png(整页归档)')

  await ctx.close()
  await browser.close()
  console.log('\n✓ 截图已保存到', OUT_DIR)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
