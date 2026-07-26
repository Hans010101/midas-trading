import { jsonResponse } from './http'

type EconEvent = Readonly<{
  event_key: string
  event_type: string
  title: string
  markets: string[]
  importance: number
  scheduled_at: string
  time_confirmed: boolean
  source: string
}>

const FED_URL = 'https://www.federalreserve.gov/json/calendar.json'
const BEA_URL = 'https://apps.bea.gov/API/signup/release_dates.json'

async function publicJson<T>(url: string): Promise<T> {
  const response = await fetch(url, {
    headers: {
      accept: 'application/json',
      'user-agent': 'Midas-Trading-Cloudflare/1.0',
    },
    signal: AbortSignal.timeout(12_000),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  const text = (await response.text()).replace(/^\uFEFF/u, '')
  return JSON.parse(text) as T
}

function zonedUtc(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  timeZone: string,
): Date {
  let timestamp = Date.UTC(year, month - 1, day, hour, minute)
  for (let pass = 0; pass < 2; pass += 1) {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat('en-US', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23',
      })
        .formatToParts(new Date(timestamp))
        .map((part) => [part.type, part.value]),
    )
    const represented = Date.UTC(
      Number(parts.year),
      Number(parts.month) - 1,
      Number(parts.day),
      Number(parts.hour),
      Number(parts.minute),
    )
    timestamp += Date.UTC(year, month - 1, day, hour, minute) - represented
  }
  return new Date(timestamp)
}

function fedTime(value: string): [number, number] {
  const match = value.trim().toLowerCase().match(
    /^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m/u,
  )
  if (!match) return [14, 0]
  let hour = Number(match[1]) % 12
  if (match[3] === 'p') hour += 12
  return [hour, Number(match[2] ?? '0')]
}

function parseFed(payload: {
  events?: Array<Record<string, unknown>>
}): EconEvent[] {
  return (payload.events ?? []).flatMap((raw) => {
    if (
      raw.type !== 'FOMC' ||
      String(raw.title ?? '').trim().toLowerCase() !== 'fomc meeting'
    ) {
      return []
    }
    const month = String(raw.month ?? '')
    const day = Number(String(raw.days ?? '').split('-').at(-1)?.trim())
    const match = month.match(/^(\d{4})-(\d{2})$/u)
    if (!match || !Number.isSafeInteger(day) || day < 1 || day > 31) return []
    const [hour, minute] = fedTime(String(raw.time ?? ''))
    const scheduled = zonedUtc(
      Number(match[1]),
      Number(match[2]),
      day,
      hour,
      minute,
      'America/New_York',
    )
    if (Number.isNaN(scheduled.valueOf())) return []
    return [{
      event_key: `fomc-${scheduled.toISOString().slice(0, 10)}`,
      event_type: 'fomc',
      title: 'FOMC 利率决议',
      markets: ['us', 'crypto', 'hk', 'cn'],
      importance: 3,
      scheduled_at: scheduled.toISOString(),
      time_confirmed: true,
      source: 'fed_json',
    }]
  })
}

function parseBea(payload: Record<string, {
  release_dates?: string[]
}>): EconEvent[] {
  const releases = [
    ['Gross Domestic Product', 'us_gdp', '美国GDP', 2, ['us']],
    ['Personal Income and Outlays', 'us_pce', '美国PCE物价', 2, ['us', 'crypto']],
  ] as const
  const seen = new Set<string>()
  return releases.flatMap(([release, eventType, title, importance, markets]) =>
    (payload[release]?.release_dates ?? []).flatMap((value) => {
      const scheduled = new Date(value)
      if (Number.isNaN(scheduled.valueOf())) return []
      const eventKey = `${eventType}-${scheduled.toISOString().slice(0, 10)}`
      if (seen.has(eventKey)) return []
      seen.add(eventKey)
      return [{
        event_key: eventKey,
        event_type: eventType,
        title,
        markets: [...markets],
        importance,
        scheduled_at: scheduled.toISOString(),
        time_confirmed: true,
        source: 'bea_json',
      }]
    }),
  )
}

function monthSequence(now: Date, count: number): Array<[number, number]> {
  const result: Array<[number, number]> = []
  let year = now.getUTCFullYear()
  let month = now.getUTCMonth() + 1
  for (let index = 0; index < count; index += 1) {
    result.push([year, month])
    month += 1
    if (month === 13) {
      year += 1
      month = 1
    }
  }
  return result
}

function ruleEvents(now: Date): EconEvent[] {
  return monthSequence(now, 6).flatMap(([year, month]) => {
    const lprDate = new Date(Date.UTC(year, month - 1, 20))
    while (lprDate.getUTCDay() === 0 || lprDate.getUTCDay() === 6) {
      lprDate.setUTCDate(lprDate.getUTCDate() + 1)
    }
    const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate()
    const firstFriday = new Date(Date.UTC(year, month - 1, 1))
    while (firstFriday.getUTCDay() !== 5) {
      firstFriday.setUTCDate(firstFriday.getUTCDate() + 1)
    }
    return [
      {
        event_key: `lpr-${year}-${String(month).padStart(2, '0')}`,
        event_type: 'lpr',
        title: 'LPR 贷款市场报价利率',
        markets: ['cn', 'hk'],
        importance: 2,
        scheduled_at: zonedUtc(
          lprDate.getUTCFullYear(),
          lprDate.getUTCMonth() + 1,
          lprDate.getUTCDate(),
          9,
          15,
          'Asia/Shanghai',
        ).toISOString(),
        time_confirmed: true,
        source: 'rule',
      },
      {
        event_key: `cn_pmi-${year}-${String(month).padStart(2, '0')}`,
        event_type: 'cn_pmi',
        title: '中国制造业PMI',
        markets: ['cn', 'hk'],
        importance: 2,
        scheduled_at: zonedUtc(
          year,
          month,
          lastDay,
          9,
          30,
          'Asia/Shanghai',
        ).toISOString(),
        time_confirmed: true,
        source: 'rule',
      },
      {
        event_key: `cn_credit-${year}-${String(month).padStart(2, '0')}`,
        event_type: 'cn_credit',
        title: '中国社融/M2(每月9-15日窗口·具体日待定)',
        markets: ['cn'],
        importance: 1,
        scheduled_at: zonedUtc(year, month, 9, 9, 0, 'Asia/Shanghai').toISOString(),
        time_confirmed: false,
        source: 'rule',
      },
      {
        event_key: `nfp-${year}-${String(month).padStart(2, '0')}`,
        event_type: 'nfp',
        title: '美国非农就业报告(惯例日·以官方为准)',
        markets: ['us', 'crypto'],
        importance: 3,
        scheduled_at: zonedUtc(
          firstFriday.getUTCFullYear(),
          firstFriday.getUTCMonth() + 1,
          firstFriday.getUTCDate(),
          8,
          30,
          'America/New_York',
        ).toISOString(),
        time_confirmed: false,
        source: 'rule',
      },
    ]
  })
}

const SEEDED: ReadonlyArray<readonly [
  string,
  string,
  string,
  number,
  number,
  number,
  number,
  number,
  string,
  readonly string[],
  number,
  boolean,
]> = [
  ['cn_cpi', '中国CPI', 'Asia/Shanghai', 2026, 8, 9, 9, 30, 'seed', ['cn', 'hk'], 2, true],
  ['cn_ppi', '中国PPI', 'Asia/Shanghai', 2026, 8, 9, 9, 30, 'seed', ['cn', 'hk'], 2, true],
  ['cn_cpi', '中国CPI', 'Asia/Shanghai', 2026, 9, 9, 9, 30, 'seed', ['cn', 'hk'], 2, true],
  ['cn_ppi', '中国PPI', 'Asia/Shanghai', 2026, 9, 9, 9, 30, 'seed', ['cn', 'hk'], 2, true],
  ['cn_gdp', '中国季度GDP·国民经济运行发布会', 'Asia/Shanghai', 2026, 10, 19, 10, 0, 'seed', ['cn', 'hk'], 3, true],
  ['ecb', '欧央行ECB利率决议', 'Europe/Berlin', 2026, 9, 10, 14, 15, 'seed', ['us'], 1, true],
  ['ecb', '欧央行ECB利率决议', 'Europe/Berlin', 2026, 10, 29, 14, 15, 'seed', ['us'], 1, true],
  ['ecb', '欧央行ECB利率决议', 'Europe/Berlin', 2026, 12, 17, 14, 15, 'seed', ['us'], 1, true],
  ['boj', '日央行BOJ利率决议', 'Asia/Tokyo', 2026, 7, 31, 12, 0, 'seed', ['us', 'crypto'], 1, false],
  ['boj', '日央行BOJ利率决议', 'Asia/Tokyo', 2026, 9, 18, 12, 0, 'seed', ['us', 'crypto'], 1, false],
  ['boj', '日央行BOJ利率决议', 'Asia/Tokyo', 2026, 10, 30, 12, 0, 'seed', ['us', 'crypto'], 1, false],
  ['boj', '日央行BOJ利率决议', 'Asia/Tokyo', 2026, 12, 18, 12, 0, 'seed', ['us', 'crypto'], 1, false],
  ['bok', '韩国央行BOK利率决议', 'Asia/Seoul', 2026, 8, 27, 10, 30, 'seed', ['kr'], 1, true],
  ['bok', '韩国央行BOK利率决议', 'Asia/Seoul', 2026, 10, 22, 10, 30, 'seed', ['kr'], 1, true],
  ['bok', '韩国央行BOK利率决议', 'Asia/Seoul', 2026, 11, 26, 10, 30, 'seed', ['kr'], 1, true],
  ['gb_boe', '英国央行BoE利率决议', 'Europe/London', 2026, 7, 30, 12, 0, 'seed', ['eu'], 1, true],
  ['gb_boe', '英国央行BoE利率决议', 'Europe/London', 2026, 9, 17, 12, 0, 'seed', ['eu'], 1, true],
  ['gb_boe', '英国央行BoE利率决议', 'Europe/London', 2026, 11, 5, 12, 0, 'seed', ['eu'], 1, true],
  ['gb_boe', '英国央行BoE利率决议', 'Europe/London', 2026, 12, 17, 12, 0, 'seed', ['eu'], 1, true],
]

function seedEvents(): EconEvent[] {
  return SEEDED.map(([
    type,
    title,
    zone,
    year,
    month,
    day,
    hour,
    minute,
    source,
    markets,
    importance,
    confirmed,
  ]) => ({
    event_key: `${type}-${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`,
    event_type: type,
    title,
    markets: [...markets],
    importance,
    scheduled_at: zonedUtc(year, month, day, hour, minute, zone).toISOString(),
    time_confirmed: confirmed,
    source,
  }))
}

export async function handleEconRoute(
  request: Request,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/econ/')) return null
  if (path !== '/api/v1/econ/calendar') {
    return jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
  }
  if (request.method !== 'GET') {
    return jsonResponse({ detail: 'Method not allowed' }, 405, requestId, request.method)
  }
  const started = new Date()
  const [fed, bea] = await Promise.allSettled([
    publicJson<{ events?: Array<Record<string, unknown>> }>(FED_URL),
    publicJson<Record<string, { release_dates?: string[] }>>(BEA_URL),
  ])
  const events = [
    ...ruleEvents(started),
    ...seedEvents(),
    ...(fed.status === 'fulfilled' ? parseFed(fed.value) : []),
    ...(bea.status === 'fulfilled' ? parseBea(bea.value) : []),
  ]
    .filter((event) => Date.parse(event.scheduled_at) >= started.valueOf() - 86_400_000)
    .filter((event, index, all) =>
      all.findIndex((candidate) => candidate.event_key === event.event_key) === index,
    )
    .sort((left, right) => Date.parse(left.scheduled_at) - Date.parse(right.scheduled_at))
  const now = new Date().toISOString()
  const sources = [
    {
      source: 'fed_json',
      last_success: fed.status === 'fulfilled' ? now : null,
      age_seconds: fed.status === 'fulfilled' ? 0 : null,
      stale: fed.status !== 'fulfilled',
    },
    {
      source: 'bea_json',
      last_success: bea.status === 'fulfilled' ? now : null,
      age_seconds: bea.status === 'fulfilled' ? 0 : null,
      stale: bea.status !== 'fulfilled',
    },
    {
      source: 'rule',
      last_success: now,
      age_seconds: 0,
      stale: false,
    },
    {
      source: 'seed',
      last_success: now,
      age_seconds: 0,
      stale: false,
    },
  ]
  const response = jsonResponse(
    {
      events,
      sources,
      updated_at:
        fed.status === 'fulfilled' || bea.status === 'fulfilled' ? now : null,
      any_stale: sources.some((source) => source.stale),
    },
    200,
    requestId,
    request.method,
  )
  response.headers.set('cache-control', 'public, max-age=300, s-maxage=900')
  return response
}
