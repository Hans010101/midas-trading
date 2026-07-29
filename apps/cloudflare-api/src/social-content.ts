import { invokeAi, parseAiJson } from './ai-provider'

const RSS_MAX_AGE_MS = 8 * 60 * 60_000
const TOKENOMIST_URL = 'https://api.tokenomist.ai/v1/unlock/events/upcoming'
const COINGECKO_TRENDING_URL = 'https://api.coingecko.com/api/v3/search/trending'
const DEFILLAMA_DEX_URL =
  'https://api.llama.fi/overview/dexs?excludeTotalDataChart=true&excludeTotalDataChartBreakdown=true&dataType=dailyVolume'
const OKX_PUBLIC_URL = 'https://www.okx.com/api/v5'

const NEWS_FEEDS = Object.freeze([
  {
    source: 'PANews',
    url: 'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS',
    scoreBoost: 6,
  },
  {
    source: 'Cointelegraph 中文',
    url: 'https://cointelegraph-cn.com/rss',
    scoreBoost: 5,
  },
  {
    source: 'CoinDesk',
    url: 'https://www.coindesk.com/arc/outboundfeeds/rss/',
    scoreBoost: 7,
  },
  {
    source: 'Cointelegraph',
    url: 'https://cointelegraph.com/rss',
    scoreBoost: 4,
  },
  {
    source: 'Decrypt',
    url: 'https://decrypt.co/feed',
    scoreBoost: 4,
  },
  {
    source: 'The Block',
    url: 'https://www.theblock.co/rss.xml',
    scoreBoost: 7,
  },
  {
    source: 'Blockworks',
    url: 'https://blockworks.co/feed',
    scoreBoost: 5,
  },
] as const)

const OKX_FLOW_WATCH = Object.freeze([
  { symbol: 'BTC', grossMinimum: 500_000, singleMinimum: 100_000 },
  { symbol: 'ETH', grossMinimum: 500_000, singleMinimum: 100_000 },
  { symbol: 'SOL', grossMinimum: 150_000, singleMinimum: 50_000 },
  { symbol: 'BNB', grossMinimum: 100_000, singleMinimum: 30_000 },
] as const)

const COIN_ALIASES: Readonly<Record<string, readonly string[]>> = {
  BTC: ['BTC', 'BITCOIN', '比特币'],
  ETH: ['ETH', 'ETHEREUM', '以太坊'],
  SOL: ['SOL', 'SOLANA'],
  BNB: ['BNB', 'BINANCE COIN'],
  XRP: ['XRP', 'RIPPLE'],
  DOGE: ['DOGE', 'DOGECOIN', '狗狗币'],
  ADA: ['ADA', 'CARDANO'],
  AVAX: ['AVAX', 'AVALANCHE'],
  LINK: ['LINK', 'CHAINLINK'],
  TRX: ['TRX', 'TRON'],
  SUI: ['SUI'],
  ARB: ['ARB', 'ARBITRUM'],
  OP: ['OP', 'OPTIMISM'],
  TON: ['TON', 'TONCOIN'],
  HYPE: ['HYPE', 'HYPERLIQUID'],
}

type ContentEnv = Readonly<{
  TOKENOMIST_API_KEY?: string
  TOKENOMIST_COMMERCIAL_LICENSE?: string
  COINGECKO_DEMO_API_KEY?: string
}>

export type SocialContentType = 'news' | 'whale' | 'unlock'

export type SocialContentEvent = Readonly<{
  id: number
  source: string
  contentType: SocialContentType
  title: string
  summary: string
  sourceUrl: string
  symbols: string[]
  score: number
  occurredAt: number
}>

function decodeXml(value: string): string {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/gu, '$1')
    .replace(/<[^>]+>/gu, ' ')
    .replace(/&#x([0-9a-f]+);/giu, (match, digits: string) => {
      const point = Number.parseInt(digits, 16)
      return point <= 0x10ffff ? String.fromCodePoint(point) : match
    })
    .replace(/&#([0-9]+);/gu, (match, digits: string) => {
      const point = Number.parseInt(digits, 10)
      return point <= 0x10ffff ? String.fromCodePoint(point) : match
    })
    .replace(/&nbsp;/gu, ' ')
    .replace(/&amp;/gu, '&')
    .replace(/&lt;/gu, '<')
    .replace(/&gt;/gu, '>')
    .replace(/&quot;/gu, '"')
    .replace(/&#39;|&apos;/gu, "'")
    .replace(/\s+/gu, ' ')
    .trim()
}

function isCryptoRelevant(text: string): boolean {
  return extractSymbols(text).length > 0 ||
    /(crypto|blockchain|web3|defi|stablecoin|token|coinbase|binance|tether|wallet|altcoin|on[ -]?chain|加密|区块链|稳定币|代币|币安|链上|数字资产)/iu.test(text)
}

function xmlValue(item: string, tag: string): string {
  const match = new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, 'iu').exec(item)
  return match ? decodeXml(match[1] ?? '') : ''
}

export function parseSyndicationFeed(xml: string): Array<{
  id: string
  title: string
  summary: string
  link: string
  occurredAt: number
}> {
  const rss = [...xml.matchAll(/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/giu)]
    .slice(0, 20)
    .flatMap((match) => {
    const item = match[1] ?? ''
    const title = xmlValue(item, 'title')
    const summary = xmlValue(item, 'description') || xmlValue(item, 'content:encoded')
    const link = xmlValue(item, 'link')
    const id = xmlValue(item, 'guid') || link
    const occurredAt = Date.parse(xmlValue(item, 'pubDate'))
    return title && summary && link && id && Number.isFinite(occurredAt)
      ? [{ id, title, summary, link, occurredAt }]
      : []
  })
  const atom = [...xml.matchAll(/<entry(?:\s[^>]*)?>([\s\S]*?)<\/entry>/giu)]
    .slice(0, 20)
    .flatMap((match) => {
      const item = match[1] ?? ''
      const title = xmlValue(item, 'title')
      const summary = xmlValue(item, 'summary') || xmlValue(item, 'content')
      const linkMatch = /<link\b[^>]*href=["']([^"']+)["'][^>]*\/?\s*>/iu.exec(item)
      const link = decodeXml(linkMatch?.[1] ?? '')
      const id = xmlValue(item, 'id') || link
      const occurredAt = Date.parse(xmlValue(item, 'published') || xmlValue(item, 'updated'))
      return title && summary && link && id && Number.isFinite(occurredAt)
        ? [{ id, title, summary, link, occurredAt }]
        : []
    })
  return [...rss, ...atom]
}

export function extractSymbols(text: string): string[] {
  const upper = text.toUpperCase()
  const found: string[] = []
  for (const [symbol, aliases] of Object.entries(COIN_ALIASES)) {
    if (aliases.some((alias) => {
      const escaped = alias.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')
      return /[A-Z0-9]/u.test(alias)
        ? new RegExp(`(^|[^A-Z0-9])${escaped}([^A-Z0-9]|$)`, 'u').test(upper)
        : upper.includes(alias)
    })) found.push(symbol)
  }
  for (const match of upper.matchAll(/[($]([A-Z][A-Z0-9]{1,9})\)?/gu)) {
    const symbol = match[1] ?? ''
    if (!found.includes(symbol) && !['USD', 'USDT', 'ETF', 'API', 'AI'].includes(symbol)) {
      found.push(symbol)
    }
  }
  return found.slice(0, 6)
}

function eventScore(title: string, summary: string, occurredAt: number): number {
  const text = `${title} ${summary}`
  let score = 30
  const signals: Array<[RegExp, number]> = [
    [/被盗|黑客|攻击|漏洞|exploit|hack/iu, 35],
    [/监管|法案|利率|联储|ETF|SEC|FOMC/iu, 25],
    [/上市|上线|空投|解锁|清算|巨鲸/iu, 18],
    [/币安|Binance|Bitcoin|Ethereum|Solana/iu, 12],
  ]
  for (const [pattern, weight] of signals) if (pattern.test(text)) score += weight
  const ageHours = Math.max(0, (Date.now() - occurredAt) / 3_600_000)
  return Math.max(0, Math.min(100, score - ageHours * 2))
}

async function insertEvent(
  env: Env,
  event: Readonly<{
    source: string
    sourceId: string
    contentType: SocialContentType
    title: string
    summary: string
    sourceUrl: string
    symbols: readonly string[]
    score: number
    occurredAt: number
  }>,
): Promise<number> {
  const result = await env.DB
    .prepare(
      `INSERT OR IGNORE INTO social_content_events
        (source, source_id, content_type, title, summary, source_url,
         symbols_json, score, status, occurred_at, ingested_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)`,
    )
    .bind(
      event.source,
      event.sourceId,
      event.contentType,
      event.title.slice(0, 500),
      event.summary.slice(0, 3_000),
      event.sourceUrl.slice(0, 1_000),
      JSON.stringify(event.symbols),
      event.score,
      event.occurredAt,
      Date.now(),
    )
    .run()
  return Number(result.meta.changes ?? 0)
}

async function ingestNewsFeed(
  env: Env,
  now: number,
  feed: (typeof NEWS_FEEDS)[number],
): Promise<number> {
  const response = await fetch(feed.url, {
    headers: { accept: 'application/rss+xml, application/xml;q=0.9' },
    signal: AbortSignal.timeout(15_000),
  })
  if (!response.ok) throw new Error(`${feed.source} RSS HTTP ${response.status}`)
  const items = parseSyndicationFeed(await response.text())
  let inserted = 0
  for (const item of items) {
    if (item.occurredAt < now - RSS_MAX_AGE_MS || item.occurredAt > now + 5 * 60_000) continue
    if (!isCryptoRelevant(`${item.title} ${item.summary}`)) continue
    inserted += await insertEvent(env, {
      source: feed.source,
      sourceId: item.id,
      contentType: 'news',
      title: item.title,
      summary: item.summary,
      sourceUrl: item.link,
      symbols: extractSymbols(`${item.title} ${item.summary}`),
      score: Math.min(100, eventScore(item.title, item.summary, item.occurredAt) + feed.scoreBoost),
      occurredAt: item.occurredAt,
    })
  }
  return inserted
}

async function sourceEventExists(
  env: Env,
  source: string,
  sourceId: string,
): Promise<boolean> {
  const row = await env.DB
    .prepare('SELECT 1 AS found FROM social_content_events WHERE source = ? AND source_id = ?')
    .bind(source, sourceId)
    .first<{ found: number }>()
  return row?.found === 1
}

async function ingestCoinGeckoTrending(env: Env, now: number): Promise<number> {
  const apiKey = (env as Env & ContentEnv).COINGECKO_DEMO_API_KEY?.trim()
  if (!apiKey) return 0
  const sourceId = `trending:${Math.floor(now / (2 * 60 * 60_000))}`
  if (await sourceEventExists(env, 'CoinGecko', sourceId)) return 0
  const response = await fetch(COINGECKO_TRENDING_URL, {
    headers: { 'x-cg-demo-api-key': apiKey, accept: 'application/json' },
    signal: AbortSignal.timeout(15_000),
  })
  if (!response.ok) throw new Error(`CoinGecko HTTP ${response.status}`)
  const payload = await response.json() as {
    coins?: Array<{
      item?: {
        name?: unknown
        symbol?: unknown
        market_cap_rank?: unknown
        data?: { price_change_percentage_24h?: { usd?: unknown } }
      }
    }>
  }
  const coins = (payload.coins ?? []).slice(0, 7).flatMap((row) => {
    const name = typeof row.item?.name === 'string' ? row.item.name : ''
    const symbol = typeof row.item?.symbol === 'string'
      ? row.item.symbol.toUpperCase()
      : ''
    const rank = Number(row.item?.market_cap_rank ?? 0)
    const change = Number(row.item?.data?.price_change_percentage_24h?.usd ?? 0)
    return name && symbol
      ? [{ name, symbol, rank, change: Number.isFinite(change) ? change : 0 }]
      : []
  })
  if (coins.length === 0) return 0
  return insertEvent(env, {
    source: 'CoinGecko',
    sourceId,
    contentType: 'news',
    title: `CoinGecko 过去 24 小时热搜币种：${coins.slice(0, 4).map((item) => item.symbol).join('、')}`,
    summary: coins.map((item, index) =>
      `${index + 1}. ${item.name} (${item.symbol})，市值排名 ${item.rank || '暂无'}，24H ${item.change >= 0 ? '+' : ''}${item.change.toFixed(2)}%`,
    ).join('；'),
    sourceUrl: 'https://www.coingecko.com/en/highlights/trending-crypto',
    symbols: coins.map((item) => item.symbol),
    score: 62,
    occurredAt: now,
  })
}

async function ingestDefiLlamaDexTrend(env: Env, now: number): Promise<number> {
  const sourceId = `dex-volume:${Math.floor(now / (4 * 60 * 60_000))}`
  if (await sourceEventExists(env, 'DefiLlama', sourceId)) return 0
  const response = await fetch(DEFILLAMA_DEX_URL, {
    headers: { accept: 'application/json' },
    signal: AbortSignal.timeout(20_000),
  })
  if (!response.ok) throw new Error(`DefiLlama HTTP ${response.status}`)
  const payload = await response.json() as {
    total24h?: unknown
    change_1d?: unknown
    protocols?: Array<{
      name?: unknown
      total24h?: unknown
      change_1d?: unknown
      chains?: unknown
    }>
  }
  const total24h = Number(payload.total24h ?? 0)
  const change1d = Number(payload.change_1d ?? 0)
  const protocols = (payload.protocols ?? []).flatMap((raw) => {
    const name = typeof raw.name === 'string' ? raw.name : ''
    const volume = Number(raw.total24h ?? 0)
    const change = Number(raw.change_1d ?? 0)
    const chains = Array.isArray(raw.chains)
      ? raw.chains.filter((value): value is string => typeof value === 'string')
      : []
    return name && Number.isFinite(volume) && volume >= 50_000_000 && Number.isFinite(change)
      ? [{ name, volume, change, chains }]
      : []
  }).sort((left, right) => right.volume - left.volume).slice(0, 5)
  if (total24h <= 0 || protocols.length === 0) return 0
  const facts = protocols.map((item) =>
    `${item.name} 24H 交易量约 $${(item.volume / 1_000_000).toFixed(1)}M（日变动 ${item.change >= 0 ? '+' : ''}${item.change.toFixed(1)}%）`,
  ).join('；')
  return insertEvent(env, {
    source: 'DefiLlama',
    sourceId,
    contentType: 'news',
    title: `全市场 DEX 24H 交易量约 $${(total24h / 1_000_000_000).toFixed(2)}B`,
    summary: `全市场较前一日 ${change1d >= 0 ? '+' : ''}${change1d.toFixed(2)}%。成交量前列：${facts}。`,
    sourceUrl: 'https://defillama.com/dexs',
    symbols: extractSymbols(protocols.flatMap((item) => [item.name, ...item.chains]).join(' ')),
    score: Math.min(82, 55 + Math.abs(change1d) * 2),
    occurredAt: now,
  })
}

async function ingestOkxFlow(env: Env, now: number): Promise<number> {
  const slot = Math.floor(now / (30 * 60_000))
  const results = await Promise.all(OKX_FLOW_WATCH.map(async (watch) => {
    const sourceId = `${watch.symbol}:${slot}`
    if (await sourceEventExists(env, 'OKX Public Trades', sourceId)) return 0
    const instrumentId = `${watch.symbol}-USDT-SWAP`
    const [instrumentResponse, tradesResponse] = await Promise.all([
      fetch(`${OKX_PUBLIC_URL}/public/instruments?instType=SWAP&instId=${instrumentId}`, {
        headers: { accept: 'application/json' },
        signal: AbortSignal.timeout(12_000),
      }),
      fetch(`${OKX_PUBLIC_URL}/market/trades?instId=${instrumentId}&limit=500`, {
        headers: { accept: 'application/json' },
        signal: AbortSignal.timeout(12_000),
      }),
    ])
    if (!instrumentResponse.ok || !tradesResponse.ok) {
      throw new Error(`OKX ${instrumentId} HTTP ${instrumentResponse.status}/${tradesResponse.status}`)
    }
    const instrumentPayload = await instrumentResponse.json() as {
      data?: Array<{ ctVal?: unknown; state?: unknown }>
    }
    const tradesPayload = await tradesResponse.json() as {
      data?: Array<{
        tradeId?: unknown
        px?: unknown
        sz?: unknown
        side?: unknown
        ts?: unknown
      }>
    }
    const contractValue = Number(instrumentPayload.data?.[0]?.ctVal ?? 0)
    if (contractValue <= 0 || instrumentPayload.data?.[0]?.state !== 'live') return 0
    const trades = (tradesPayload.data ?? []).flatMap((trade) => {
      const price = Number(trade.px ?? 0)
      const size = Number(trade.sz ?? 0)
      const timestamp = Number(trade.ts ?? 0)
      const side = trade.side === 'buy' || trade.side === 'sell' ? trade.side : null
      const tradeId = typeof trade.tradeId === 'string' ? trade.tradeId : ''
      const notional = price * size * contractValue
      return side && tradeId && price > 0 && size > 0 && Number.isFinite(timestamp)
        ? [{ side, tradeId, timestamp, price, notional }]
        : []
    })
    if (trades.length === 0) return 0
    const buy = trades.filter((trade) => trade.side === 'buy')
      .reduce((sum, trade) => sum + trade.notional, 0)
    const sell = trades.filter((trade) => trade.side === 'sell')
      .reduce((sum, trade) => sum + trade.notional, 0)
    const gross = buy + sell
    const largest = trades.reduce((best, trade) => trade.notional > best.notional ? trade : best)
    const imbalance = gross > 0 ? Math.abs(buy - sell) / gross : 0
    if (
      !((gross >= watch.grossMinimum && imbalance >= 0.2) ||
        largest.notional >= watch.singleMinimum)
    ) return 0
    const dominant = buy >= sell ? '主动买入' : '主动卖出'
    const coverageSeconds = Math.max(
      1,
      Math.round((Math.max(...trades.map((trade) => trade.timestamp)) -
        Math.min(...trades.map((trade) => trade.timestamp))) / 1_000),
    )
    return insertEvent(env, {
      source: 'OKX Public Trades',
      sourceId,
      contentType: 'whale',
      title: `OKX ${watch.symbol} 永续出现大额${dominant}成交信号`,
      summary: `最近 ${trades.length} 笔公开成交样本覆盖约 ${coverageSeconds} 秒，主动买入约 $${buy.toFixed(0)}，主动卖出约 $${sell.toFixed(0)}，最大单笔约 $${largest.notional.toFixed(0)}。这是成交样本而非链上转账，需结合价格、OI 与资金费率交叉验证。`,
      sourceUrl: `https://www.okx.com/trade-swap/${watch.symbol.toLowerCase()}-usdt-swap`,
      symbols: [watch.symbol],
      score: Math.min(92, 58 + imbalance * 30 + Math.min(10, largest.notional / watch.singleMinimum * 3)),
      occurredAt: Math.max(...trades.map((trade) => trade.timestamp)),
    })
  }))
  return results.reduce((sum, value) => sum + value, 0)
}

async function ingestTokenomist(env: Env, now: number): Promise<number> {
  const external = env as Env & ContentEnv
  const apiKey = external.TOKENOMIST_API_KEY?.trim()
  if (!apiKey || external.TOKENOMIST_COMMERCIAL_LICENSE !== '1') return 0
  const start = new Date(now).toISOString().slice(0, 10)
  const end = new Date(now + 7 * 86_400_000).toISOString().slice(0, 10)
  const url = new URL(TOKENOMIST_URL)
  url.searchParams.set('minUnlockDate', start)
  url.searchParams.set('maxUnlockDate', end)
  url.searchParams.set('minMarketCap', '50000000')
  url.searchParams.set('minValueToMarketCap', '1')
  const response = await fetch(url, {
    headers: { 'x-api-key': apiKey },
    signal: AbortSignal.timeout(15_000),
  })
  if (!response.ok) throw new Error(`Tokenomist HTTP ${response.status}`)
  const payload = await response.json() as { data?: unknown[] }
  let inserted = 0
  for (const raw of (payload.data ?? []).slice(0, 30)) {
    if (typeof raw !== 'object' || raw === null) continue
    const item = raw as Record<string, unknown>
    const upcoming = typeof item.upcomingEvent === 'object' && item.upcomingEvent !== null
      ? item.upcomingEvent as Record<string, unknown>
      : {}
    const cliffs = typeof upcoming.cliffUnlocks === 'object' && upcoming.cliffUnlocks !== null
      ? upcoming.cliffUnlocks as Record<string, unknown>
      : {}
    const symbol = typeof item.tokenSymbol === 'string' ? item.tokenSymbol.toUpperCase() : ''
    const unlockDate = Date.parse(String(upcoming.unlockDate ?? ''))
    const unlockValue = Number(cliffs.totalCliffValue ?? 0)
    const ratio = Number(cliffs.valueToMarketCap ?? 0)
    if (!symbol || !Number.isFinite(unlockDate)) continue
    inserted += await insertEvent(env, {
      source: 'Tokenomist',
      sourceId: `${symbol}:${new Date(unlockDate).toISOString()}`,
      contentType: 'unlock',
      title: `${symbol} 即将迎来代币解锁`,
      summary: `预计解锁价值 ${unlockValue.toFixed(0)} 美元，约占市值 ${ratio.toFixed(2)}%；时间 ${new Date(unlockDate).toISOString()}。`,
      sourceUrl: 'https://tokenomist.ai/',
      symbols: [symbol],
      score: Math.min(100, 55 + Math.min(30, ratio * 3) + Math.min(15, unlockValue / 10_000_000)),
      occurredAt: unlockDate,
    })
  }
  return inserted
}

async function recordSourceHealth(
  env: Env,
  source: string,
  values: Readonly<{
    status: 'healthy' | 'error' | 'disabled'
    inserted?: number
    error?: string | null
    attemptedAt: number
    latencyMs: number
  }>,
): Promise<void> {
  await env.DB
    .prepare(
      `INSERT INTO social_source_health
        (source, status, last_attempt_at, last_success_at, last_error,
         last_inserted, latency_ms)
       VALUES (?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(source) DO UPDATE SET
         status = excluded.status,
         last_attempt_at = excluded.last_attempt_at,
         last_success_at = CASE
           WHEN excluded.status = 'healthy' THEN excluded.last_success_at
           ELSE social_source_health.last_success_at
         END,
         last_error = excluded.last_error,
         last_inserted = excluded.last_inserted,
         latency_ms = excluded.latency_ms`,
    )
    .bind(
      source,
      values.status,
      values.attemptedAt,
      values.status === 'healthy' ? values.attemptedAt : null,
      values.error?.slice(0, 500) ?? null,
      values.inserted ?? 0,
      values.latencyMs,
    )
    .run()
}

export async function ingestSocialContent(env: Env, now = Date.now()): Promise<void> {
  const external = env as Env & ContentEnv
  const sources: Array<Readonly<{
    source: string
    enabled: boolean
    task: () => Promise<number>
  }>> = [
    ...NEWS_FEEDS.map((feed) => ({
      source: feed.source,
      enabled: true,
      task: () => ingestNewsFeed(env, now, feed),
    })),
    {
      source: 'DefiLlama',
      enabled: true,
      task: () => ingestDefiLlamaDexTrend(env, now),
    },
    {
      source: 'OKX Public Trades',
      enabled: true,
      task: () => ingestOkxFlow(env, now),
    },
    {
      source: 'CoinGecko',
      enabled: Boolean(external.COINGECKO_DEMO_API_KEY?.trim()),
      task: () => ingestCoinGeckoTrending(env, now),
    },
    {
      source: 'Tokenomist',
      enabled: Boolean(
        external.TOKENOMIST_API_KEY?.trim() &&
        external.TOKENOMIST_COMMERCIAL_LICENSE === '1',
      ),
      task: () => ingestTokenomist(env, now),
    },
  ]
  await Promise.all(sources.map(async ({ source, enabled, task }) => {
    const startedAt = Date.now()
    if (!enabled) {
      await recordSourceHealth(env, source, {
        status: 'disabled',
        attemptedAt: now,
        latencyMs: 0,
      })
      return
    }
    try {
      const inserted = await task()
      await recordSourceHealth(env, source, {
        status: 'healthy',
        inserted,
        attemptedAt: now,
        latencyMs: Date.now() - startedAt,
      })
      if (inserted > 0) console.log(JSON.stringify({ event: 'social.ingest', source, inserted }))
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      await recordSourceHealth(env, source, {
        status: 'error',
        error: message,
        attemptedAt: now,
        latencyMs: Date.now() - startedAt,
      })
      console.error(JSON.stringify({
        event: 'social.ingest_failed',
        source,
        error: message,
      }))
    }
  }))
  await env.DB
    .prepare(
      `UPDATE social_content_events SET status = 'ignored'
       WHERE status = 'pending' AND content_type = 'news' AND occurred_at < ?`,
    )
    .bind(now - 24 * 60 * 60_000)
    .run()
}

export async function nextContentEvent(
  env: Env,
  preferredTypes: readonly SocialContentType[] = ['whale', 'unlock', 'news'],
): Promise<SocialContentEvent | null> {
  const placeholders = preferredTypes.map(() => '?').join(',')
  const row = await env.DB
    .prepare(
      `SELECT id, source, content_type, title, summary, source_url,
              symbols_json, score, occurred_at
       FROM social_content_events
       WHERE status = 'pending' AND content_type IN (${placeholders})
       ORDER BY CASE content_type
         ${preferredTypes.map((type, index) => `WHEN '${type}' THEN ${index}`).join(' ')}
       ELSE 99 END, score DESC, occurred_at DESC
       LIMIT 1`,
    )
    .bind(...preferredTypes)
    .first<{
      id: number
      source: string
      content_type: SocialContentType
      title: string
      summary: string
      source_url: string
      symbols_json: string
      score: number
      occurred_at: number
    }>()
  if (!row) return null
  let symbols: string[] = []
  try {
    const parsed = JSON.parse(row.symbols_json) as unknown
    if (Array.isArray(parsed)) symbols = parsed.filter((value): value is string => typeof value === 'string')
  } catch { /* invalid legacy JSON becomes an empty symbol list */ }
  return {
    id: row.id,
    source: row.source,
    contentType: row.content_type,
    title: row.title,
    summary: row.summary,
    sourceUrl: row.source_url,
    symbols,
    score: row.score,
    occurredAt: row.occurred_at,
  }
}

function stableNumber(value: string): number {
  let hash = 2166136261
  for (const char of value) hash = Math.imul(hash ^ char.codePointAt(0)!, 16777619)
  return hash >>> 0
}

export function contentTags(symbols: readonly string[], seed: string): string[] {
  const majors = ['BTC', 'ETH', 'SOL', 'BNB']
  const unique = [...new Set(symbols.map((value) => value.toUpperCase()).filter(Boolean))]
  const count = 2 + (stableNumber(seed) % 3)
  const rotated = majors.map((_, index) => majors[(index + stableNumber(`${seed}:${index}`)) % majors.length])
  return [...new Set([...unique, ...rotated])].slice(0, count).map((symbol) => `$${symbol}`)
}

export async function draftContentEvent(
  env: Env,
  event: SocialContentEvent,
): Promise<{ text: string; bias: string; provider: string; model: string; symbol: string }> {
  const ai = await invokeAi(env, {
    system:
      '你是专业的 Web3 快讯编辑。只输出 JSON，不复制原文，不补造事实，不承诺收益，不下确定性涨跌结论。',
    prompt: `${JSON.stringify({
      type: event.contentType,
      source: event.source,
      title: event.title,
      facts: event.summary,
      source_url: event.sourceUrl,
      symbols: event.symbols,
      occurred_at: new Date(event.occurredAt).toISOString(),
    })}
改写为 180-360 个中文字的币安广场帖子：首句给出信息点，然后解释市场为何关注、两个可验证的后续观察点。明确写“据 ${event.source}”并在末尾保留来源链接。不要生成 # 或 $ 标签，标签由系统添加。
输出 {"text":"...","bias":"偏多|偏空|中性"}。`,
    maxTokens: 800,
    temperature: 0.3,
  })
  const parsed = parseAiJson(ai.content)
  let text = typeof parsed.text === 'string' ? parsed.text.trim() : ''
  if (!text) throw new Error('热点内容改写未返回正文')
  if (!text.includes(event.sourceUrl)) text += `\n\n来源：${event.source} ${event.sourceUrl}`
  const tags = contentTags(event.symbols, `${event.source}:${event.id}`)
  text = `${text}\n\n${tags.join(' ')}`
  const symbol = event.symbols[0] ?? 'BTC'
  return {
    text: [...text].slice(0, 4_000).join(''),
    bias: typeof parsed.bias === 'string' ? parsed.bias.slice(0, 16) : '中性',
    provider: ai.provider,
    model: ai.model,
    symbol: `${symbol}/USDT`,
  }
}

export async function markContentDrafted(env: Env, eventId: number): Promise<void> {
  await env.DB
    .prepare(`UPDATE social_content_events SET status = 'drafted' WHERE id = ?`)
    .bind(eventId)
    .run()
}
