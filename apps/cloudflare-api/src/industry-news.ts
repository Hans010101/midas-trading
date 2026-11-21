import type { IndustryBulletin, IndustryMarket, IndustryNews } from '../../../packages/shared/src'
import { jsonResponse } from './http'
import { parseSyndicationFeed } from './social-content'

const DAY = 86_400_000
const WSCN = 'https://api-one-wscn.awtmt.com/apiv1/content/lives?limit=30&channel='
const feeds = [
  { id: 'cn', name: '华尔街见闻', market: 'cn', host: 'wallstreetcn.com', url: WSCN + 'a-stock-channel' },
  { id: 'us', name: '华尔街见闻', market: 'us', host: 'wallstreetcn.com', url: WSCN + 'us-stock-channel' },
  { id: 'hk', name: '华尔街见闻', market: 'hk', host: 'wallstreetcn.com', url: WSCN + 'hk-stock-channel' },
  { id: 'eastmoney', name: '东方财富', market: 'cn', host: 'finance.eastmoney.com', url: 'https://np-listapi.eastmoney.com/comm/web/getNewsByColumns?client=web&biz=web_news_col&column=374&order=1&needInteractData=0&page_index=1&page_size=20&req_trace=midasnews' },
  { id: 'wsj', name: 'The Wall Street Journal', market: 'us', host: 'www.wsj.com', url: 'https://feeds.content.dowjones.io/public/rss/RSSMarketsMain' },
  { id: 'hkex', name: '香港交易所', market: 'hk', host: 'www.hkex.com.hk', url: 'https://www.hkex.com.hk/Services/RSS-Feeds/News-Releases?sc_lang=zh-HK' },
  { id: 'rthk', name: '香港电台财经', market: 'hk', host: 'news.rthk.hk', url: 'https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml' },
  { id: 'panews', name: 'PANews', market: 'crypto', host: 'www.panewslab.com', url: 'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS' },
  { id: 'coindesk', name: 'CoinDesk', market: 'crypto', host: 'www.coindesk.com', url: 'https://www.coindesk.com/arc/outboundfeeds/rss/' },
  { id: 'fed', name: '美联储', market: 'macro', host: 'www.federalreserve.gov', url: 'https://www.federalreserve.gov/feeds/press_all.xml' },
] as const
type Feed = (typeof feeds)[number]
type Headline = { title: string; link: string; occurredAt: number }
type Snapshot = { feed: string; checked_at: number; items_json: string }

function parseWire(body: string): Headline[] {
  const items: unknown = JSON.parse(body)?.data?.items
  if (!Array.isArray(items)) throw new Error('Invalid wire response')
  return items.flatMap(item => {
    if (!item || item.is_priced || typeof item.uri !== 'string' || typeof item.display_time !== 'number') return []
    const content = typeof item.content_text === 'string' ? item.content_text.trim() : ''
    const title = typeof item.title === 'string' && item.title.trim()
      ? item.title : (content.match(/^[^\n。！？]+[。！？]?/u)?.[0] ?? '')
    // Some equity wires syndicate general news or standalone coin price ticks.
    if (/地震|消防救援/u.test(title) && !/股|市场|保[险險]|上市|停[产產]|供[应應]/u.test(title)) return []
    if (/比特币|以太坊/u.test(title) && !/股票|股价|公司|ETF|上市|港股|美股/iu.test(title)) return []
    return [{ title, link: item.uri, occurredAt: item.display_time * 1000 }]
  })
}

function parseEastmoney(body: string): Headline[] {
  const list: unknown = JSON.parse(body)?.data?.list
  if (!Array.isArray(list)) throw new Error('Invalid Eastmoney response')
  return list.flatMap(row => {
    if (typeof row?.title !== 'string' || typeof row.uniqueUrl !== 'string' ||
        !/^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$/u.test(row.showTime)) return []
    return [{ title: row.title, link: row.uniqueUrl.replace(/^http:\/\//u, 'https://'),
      occurredAt: Date.parse(row.showTime.replace(' ', 'T') + '+08:00') }]
  })
}

function parseFeed(feed: Feed, body: string, now: number): Headline[] {
  const entries = feed.id === 'eastmoney' ? parseEastmoney(body)
    : feed.url.startsWith(WSCN) ? parseWire(body) : parseSyndicationFeed(body)
  return entries.flatMap(item => {
    if (!Number.isFinite(item.occurredAt) || item.occurredAt <= 0 || item.occurredAt > now + 300_000) return []
    const url = URL.canParse(item.link) ? new URL(item.link) : null
    if (!url || url.protocol !== 'https:' || url.host !== feed.host || url.username || url.password || url.pathname === '/') return []
    url.hash = ''
    for (const key of [...url.searchParams.keys()]) if (key.startsWith('utm_')) url.searchParams.delete(key)
    const clean = item.title.replace(/\s+/gu, ' ').trim()
    if (clean.length < 4) return []
    return [{ title: clean.length > 115 ? clean.slice(0, 114) + '…' : clean, link: url.href, occurredAt: item.occurredAt }]
  })
}

async function snapshots(db: D1Database) {
  return (await db.prepare('SELECT feed, checked_at, items_json FROM industry_feed_snapshots').all<Snapshot>()).results
}

export async function refreshIndustryNews(db: D1Database, now = Date.now()) {
  const previous = await snapshots(db)
  const tasks = await Promise.allSettled(feeds.map(async feed => {
    const res = await fetch(feed.url, {
      signal: AbortSignal.timeout(12_000),
      headers: { 'User-Agent': 'MidasTrading-News/1.0 (+https://midastrade.asia/news)', Accept: 'application/json, application/rss+xml, application/xml, text/xml, */*' },
    })
    if (!res.ok) throw new Error('HTTP ' + res.status)
    const fresh = parseFeed(feed, await res.text(), now)
    if (!fresh.length) throw new Error('No valid headlines')
    const old = previous.find(row => row.feed === feed.id)
    const byLink = new Map<string, Headline>()
    for (const item of [...(old ? JSON.parse(old.items_json) as Headline[] : []), ...fresh]) {
      if (item.occurredAt >= now - 7 * DAY) byLink.set(item.link, item)
    }
    const kept = [...byLink.values()].sort((a, b) => b.occurredAt - a.occurredAt).slice(0, 120)
    await db.prepare(
      'INSERT INTO industry_feed_snapshots(feed, checked_at, items_json) VALUES (?, ?, ?) ON CONFLICT(feed) DO UPDATE SET checked_at=excluded.checked_at, items_json=excluded.items_json WHERE excluded.checked_at > industry_feed_snapshots.checked_at',
    ).bind(feed.id, now, JSON.stringify(kept)).run()
  }))
  tasks.forEach((task, i) => {
    if (task.status === 'rejected') console.warn('industry.feed_failed', feeds[i]?.id, String(task.reason))
  })
  if (tasks.every(task => task.status === 'rejected')) throw new Error('All industry feeds failed')
}

export async function readIndustryNews(db: D1Database, now = Date.now()): Promise<IndustryNews> {
  const rows = await snapshots(db)
  const stories = new Map<string, IndustryBulletin>()
  const titles = new Map<string, IndustryBulletin>()
  const delayedMarkets = new Set<IndustryMarket>()
  let updatedAt = 0
  for (const feed of feeds) {
    const row = rows.find(entry => entry.feed === feed.id)
    if (!row || now - row.checked_at > 45 * 60_000) delayedMarkets.add(feed.market)
    if (!row) continue
    updatedAt = Math.max(updatedAt, row.checked_at)
    for (const item of JSON.parse(row.items_json) as Headline[]) {
      if (item.occurredAt < now - 7 * DAY) continue
      const key = item.title.toLowerCase().replace(/\s+/gu, ' ').trim()
      const sameTitle = item.title.endsWith('…') ? undefined : titles.get(key)
      const story = stories.get(item.link) ?? (sameTitle && Math.abs(sameTitle.publishedAt - item.occurredAt) < DAY ? sameTitle : undefined)
      if (story) {
        if (!story.markets.includes(feed.market)) story.markets.push(feed.market)
        if (!story.sources.some(source => source.url === item.link)) story.sources.push({ name: feed.name, url: item.link })
        stories.set(item.link, story)
      } else {
        const entry: IndustryBulletin = { title: item.title, publishedAt: item.occurredAt, markets: [feed.market], sources: [{ name: feed.name, url: item.link }] }
        stories.set(item.link, entry)
        titles.set(key, entry)
      }
    }
  }
  return { updatedAt, delayedMarkets: [...delayedMarkets], items: [...new Set(stories.values())].sort((a, b) => b.publishedAt - a.publishedAt) }
}

let cached: { at: number; payload: IndustryNews } | undefined
export async function handleIndustryNewsRoute(request: Request, env: Env, requestId: string) {
  if (new URL(request.url).pathname !== '/api/v1/industry/news') return null
  if (request.method !== 'HEAD' && request.method !== 'GET') return jsonResponse({ detail: 'Method not allowed' }, 405, requestId)
  const now = Date.now()
  if (!cached || now - cached.at > 60_000) cached = { at: now, payload: await readIndustryNews(env.DB, now) }
  return jsonResponse(cached.payload, cached.payload.updatedAt ? 200 : 503, requestId, request.method)
}
