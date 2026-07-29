import { invokeAi, parseAiJson } from './ai-provider'

const PANEWS_RSS = 'https://www.panewslab.com/rss.xml?lang=zh&type=NEWS'
const RSS_MAX_AGE_MS = 8 * 60 * 60_000
const TOKENOMIST_URL = 'https://api.tokenomist.ai/v1/unlock/events/upcoming'

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
    .replace(/&nbsp;/gu, ' ')
    .replace(/&amp;/gu, '&')
    .replace(/&lt;/gu, '<')
    .replace(/&gt;/gu, '>')
    .replace(/&quot;/gu, '"')
    .replace(/&#39;|&apos;/gu, "'")
    .replace(/\s+/gu, ' ')
    .trim()
}

function xmlValue(item: string, tag: string): string {
  const match = new RegExp(`<${tag}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${tag}>`, 'iu').exec(item)
  return match ? decodeXml(match[1] ?? '') : ''
}

function rssItems(xml: string): Array<{
  id: string
  title: string
  summary: string
  link: string
  occurredAt: number
}> {
  return [...xml.matchAll(/<item>([\s\S]*?)<\/item>/giu)].slice(0, 30).flatMap((match) => {
    const item = match[1] ?? ''
    const title = xmlValue(item, 'title')
    const summary = xmlValue(item, 'description')
    const link = xmlValue(item, 'link')
    const id = xmlValue(item, 'guid') || link
    const occurredAt = Date.parse(xmlValue(item, 'pubDate'))
    return title && summary && link && id && Number.isFinite(occurredAt)
      ? [{ id, title, summary, link, occurredAt }]
      : []
  })
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

async function ingestPanews(env: Env, now: number): Promise<number> {
  const response = await fetch(PANEWS_RSS, {
    headers: { accept: 'application/rss+xml, application/xml;q=0.9' },
    signal: AbortSignal.timeout(15_000),
  })
  if (!response.ok) throw new Error(`PANews RSS HTTP ${response.status}`)
  const items = rssItems(await response.text())
  let inserted = 0
  for (const item of items) {
    if (item.occurredAt < now - RSS_MAX_AGE_MS || item.occurredAt > now + 5 * 60_000) continue
    inserted += await insertEvent(env, {
      source: 'PANews',
      sourceId: item.id,
      contentType: 'news',
      title: item.title,
      summary: item.summary,
      sourceUrl: item.link,
      symbols: extractSymbols(`${item.title} ${item.summary}`),
      score: eventScore(item.title, item.summary, item.occurredAt),
      occurredAt: item.occurredAt,
    })
  }
  return inserted
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

export async function ingestSocialContent(env: Env, now = Date.now()): Promise<void> {
  const sources: Array<[string, () => Promise<number>]> = [
    ['panews', () => ingestPanews(env, now)],
    ['tokenomist', () => ingestTokenomist(env, now)],
  ]
  for (const [source, task] of sources) {
    try {
      const inserted = await task()
      if (inserted > 0) console.log(JSON.stringify({ event: 'social.ingest', source, inserted }))
    } catch (error) {
      console.error(JSON.stringify({
        event: 'social.ingest_failed',
        source,
        error: error instanceof Error ? error.message : String(error),
      }))
    }
  }
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
