import { chromium } from 'playwright'

const PUBLIC_WEB_URL =
  process.env.MIDAS_PUBLIC_WEB_URL?.trim() ||
  'https://midas-trading.hans-pan007.workers.dev'

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function compact(value, maximum) {
  const text = String(value ?? '').replace(/\s+/gu, ' ').trim()
  return [...text].slice(0, maximum).join('')
}

function cardLabel(contentType) {
  if (contentType === 'whale') return ['链上异动', '🐋']
  if (contentType === 'unlock') return ['代币解锁', '⏳']
  return ['热点快讯', '📰']
}

export function requireReadyMarketChart(state) {
  if (state !== 'ready') throw new Error(`质检未通过：K 线图表状态为 ${state || '未知'}`)
}

export function newsCardHtml(candidate) {
  const [label, icon] = cardLabel(candidate.content_type)
  const title = compact(candidate.event_title || candidate.tweet_text, 120)
  const summary = compact(candidate.event_summary, 260)
  const source = compact(candidate.event_source || '公开信息', 40)
  const time = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(new Date())
  return `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; background: #f5f2eb; }
  body { width: 1080px; height: 1080px; padding: 54px; color: #161616;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", sans-serif; }
  .card { position: relative; width: 100%; height: 100%; overflow: hidden; padding: 56px;
    border: 1px solid #e1d9ca; border-radius: 38px; background: #fffefa;
    box-shadow: 0 24px 70px rgba(56, 39, 15, .10); }
  .line { position: absolute; top: 0; left: 0; width: 100%; height: 12px;
    background: linear-gradient(90deg, #c8102e 0 68%, #c5962f 68%); }
  .top { display: flex; align-items: center; justify-content: space-between; }
  .brand { display: flex; align-items: center; gap: 18px; font-family: Georgia, serif;
    font-size: 34px; color: #b60d27; }
  .seal { display: grid; place-items: center; width: 54px; height: 54px; border: 2px solid #b60d27;
    color: #b60d27; font-family: serif; font-size: 20px; }
  .badge { padding: 11px 20px; border-radius: 999px; color: #9b152a; background: #f9e7e7;
    font-size: 23px; font-weight: 700; letter-spacing: .08em; }
  .eyebrow { margin-top: 62px; color: #a97516; font-size: 27px; font-weight: 700; }
  h1 { margin: 22px 0 32px; font-family: Georgia, "Songti SC", serif; font-size: 60px;
    line-height: 1.25; letter-spacing: -.02em; }
  .summary { padding-left: 26px; border-left: 5px solid #c8102e; color: #4f4b45;
    font-size: 31px; line-height: 1.7; }
  .watermark { position: absolute; right: -20px; bottom: 90px; color: rgba(200,16,46,.035);
    font: 700 170px Georgia, serif; transform: rotate(-12deg); }
</style>
</head>
<body>
  <main class="card" data-midas-card>
    <div class="line"></div>
    <div class="watermark">MIDAS</div>
    <div class="top">
      <div class="brand"><span class="seal">点金</span><span>Midas Trading</span></div>
      <div class="badge">${escapeHtml(icon)} ${escapeHtml(label)}</div>
    </div>
    <div class="eyebrow">${escapeHtml(source)} · ${escapeHtml(time)}</div>
    <h1>${escapeHtml(title)}</h1>
    <div class="summary">${escapeHtml(summary || '市场信息正在更新，重点关注后续数据与价格反应。')}</div>
  </main>
</body>
</html>`
}

async function captureMarketChart(page, symbol) {
  const url = new URL('/crypto-preview', PUBLIC_WEB_URL)
  url.searchParams.set('symbol', symbol)
  await page.setViewportSize({ width: 1280, height: 920 })
  await page.goto(url.toString(), { waitUntil: 'domcontentloaded', timeout: 60_000 })
  const chart = page.locator('[data-social-chart="true"]').first()
  await chart.waitFor({ state: 'visible', timeout: 50_000 })
  const state = chart.locator('[data-kline-state]').first()
  await state.waitFor({ state: 'attached', timeout: 50_000 })
  await page.waitForFunction(
    (element) => element?.getAttribute('data-kline-state') !== 'loading',
    await state.elementHandle(),
    { timeout: 50_000 },
  )
  requireReadyMarketChart(await state.getAttribute('data-kline-state'))
  await page.waitForTimeout(1_000)
  return chart.screenshot({ type: 'png' })
}

async function captureNewsCard(page, candidate) {
  await page.setViewportSize({ width: 1080, height: 1080 })
  await page.setContent(newsCardHtml(candidate), { waitUntil: 'load' })
  return page.locator('[data-midas-card]').screenshot({ type: 'png' })
}

export async function createSquareMedia(candidate) {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage({ deviceScaleFactor: 1 })
    if (candidate.content_type === 'market_analysis') {
      return {
        bytes: await captureMarketChart(page, candidate.symbol),
        kind: 'market_chart',
      }
    }
    return {
      bytes: await captureNewsCard(page, candidate),
      kind: 'news_card',
    }
  } finally {
    await browser.close()
  }
}
