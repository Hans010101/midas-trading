import { integerParam, requireAdmin } from './admin'
import { sha256Hex } from './crypto'
import { HttpError, jsonResponse, readJsonObject } from './http'

const DAY_MS = 24 * 60 * 60 * 1_000

function cstParts(timestamp: number): { date: string; hour: number } {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(timestamp))
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? ''
  return {
    date: `${value('year')}-${value('month')}-${value('day')}`,
    hour: Number(value('hour')),
  }
}

function dateOffset(date: string, offset: number): string {
  const timestamp = Date.parse(`${date}T00:00:00+08:00`) + offset * DAY_MS
  return cstParts(timestamp).date
}

function internalTrackingRequest(request: Request): boolean {
  const host = new URL(request.url).hostname
  return host === 'midas-trading-api.internal' ||
    host === 'localhost' ||
    host === '127.0.0.1'
}

function textField(
  body: Readonly<Record<string, unknown>>,
  key: string,
  maxLength: number,
  required = false,
): string | null {
  const value = body[key]
  if (value === undefined || value === null || value === '') {
    if (required) throw new HttpError(422, `${key} 不能为空`)
    return null
  }
  if (typeof value !== 'string') throw new HttpError(422, `${key} 格式无效`)
  const normalized = value.trim().slice(0, maxLength)
  if (!normalized && required) throw new HttpError(422, `${key} 不能为空`)
  return normalized || null
}

async function ingestVisit(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  if (!internalTrackingRequest(request)) {
    throw new HttpError(403, '访问埋点仅允许内部服务调用')
  }
  const body = await readJsonObject(request)
  const visitorId = textField(body, 'visitor_id', 128, true) ?? ''
  const referrer = textField(body, 'ref_host', 180)
  const utm = textField(body, 'utm_source', 64)
  const now = Date.now()
  const parts = cstParts(now)
  const source = utm ? `utm:${utm}` : referrer ? 'referral' : 'direct'
  await env.DB
    .prepare(
      `INSERT INTO web_visit_events
        (visitor_id, visit_date, visit_hour, source, referrer, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      (await sha256Hex(visitorId)).slice(0, 32),
      parts.date,
      parts.hour,
      source,
      referrer,
      now,
    )
    .run()
  return jsonResponse({ accepted: true }, 202, requestId, request.method)
}

async function ingestCrawler(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  if (!internalTrackingRequest(request)) {
    throw new HttpError(403, '爬虫埋点仅允许内部服务调用')
  }
  const body = await readJsonObject(request)
  const bot = textField(body, 'bot', 64, true) ?? 'unknown'
  const now = Date.now()
  await env.DB
    .prepare(
      `INSERT INTO crawler_visit_events (bot, visit_date, created_at)
       VALUES (?, ?, ?)`,
    )
    .bind(bot, cstParts(now).date, now)
    .run()
  return jsonResponse({ accepted: true }, 202, requestId, request.method)
}

type CountRow = Readonly<Record<string, unknown>>

function rowsByKey(
  rows: readonly CountRow[],
  key: string,
): Map<string, CountRow> {
  return new Map(rows.map((row) => [String(row[key]), row]))
}

async function visitStats(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const days = integerParam(new URL(request.url), 'days', 30, 1, 90)
  const today = cstParts(Date.now()).date
  const start = dateOffset(today, -(days - 1))
  const yesterday = dateOffset(today, -1)
  const [daily, hourly, registrations, totals, totalRegistrations] =
    await Promise.all([
      env.DB
        .prepare(
          `SELECT visit_date AS date, COUNT(*) AS pv,
                  COUNT(DISTINCT visitor_id) AS uv
           FROM web_visit_events
           WHERE visit_date >= ?
           GROUP BY visit_date
           ORDER BY visit_date`,
        )
        .bind(start)
        .all<CountRow>(),
      env.DB
        .prepare(
          `SELECT visit_hour AS hour, COUNT(*) AS pv,
                  COUNT(DISTINCT visitor_id) AS uv
           FROM web_visit_events
           WHERE visit_date = ?
           GROUP BY visit_hour
           ORDER BY visit_hour`,
        )
        .bind(today)
        .all<CountRow>(),
      env.DB
        .prepare(
          `SELECT date(created_at / 1000, 'unixepoch', '+8 hours') AS date,
                  COUNT(*) AS count
           FROM users
           WHERE created_at >= ?
           GROUP BY date
           ORDER BY date`,
        )
        .bind(Date.parse(`${start}T00:00:00+08:00`))
        .all<CountRow>(),
      env.DB
        .prepare(
          `SELECT COUNT(*) AS pv, COUNT(DISTINCT visitor_id) AS uv
           FROM web_visit_events`,
        )
        .first<{ pv: number; uv: number }>(),
      env.DB
        .prepare('SELECT COUNT(*) AS count FROM users')
        .first<{ count: number }>(),
    ])
  const dailyMap = rowsByKey(daily.results, 'date')
  const registrationMap = rowsByKey(registrations.results, 'date')
  const hourlyMap = rowsByKey(hourly.results, 'hour')
  const dailySeries = Array.from({ length: days }, (_, index) => {
    const date = dateOffset(start, index)
    const row = dailyMap.get(date)
    return { date, pv: Number(row?.pv ?? 0), uv: Number(row?.uv ?? 0) }
  })
  const registrationSeries = Array.from({ length: days }, (_, index) => {
    const date = dateOffset(start, index)
    return { date, count: Number(registrationMap.get(date)?.count ?? 0) }
  })
  const point = (date: string) => {
    const row = dailyMap.get(date)
    return { date, pv: Number(row?.pv ?? 0), uv: Number(row?.uv ?? 0) }
  }
  return jsonResponse(
    {
      range_days: days,
      daily: dailySeries,
      hourly: Array.from({ length: 24 }, (_, hour) => ({
        hour,
        pv: Number(hourlyMap.get(String(hour))?.pv ?? 0),
        uv: Number(hourlyMap.get(String(hour))?.uv ?? 0),
      })),
      registrations: registrationSeries,
      today: point(today),
      yesterday: point(yesterday),
      cumulative_pv: Number(totals?.pv ?? 0),
      cumulative_uv: Number(totals?.uv ?? 0),
      total_registrations: Number(totalRegistrations?.count ?? 0),
    },
    200,
    requestId,
    request.method,
  )
}

async function sourceStats(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const days = integerParam(new URL(request.url), 'days', 30, 1, 90)
  const today = cstParts(Date.now()).date
  const start = dateOffset(today, -(days - 1))
  const [sources, crawlers, referrers] = await Promise.all([
    env.DB
      .prepare(
        `SELECT source, COUNT(*) AS pv
         FROM web_visit_events
         WHERE visit_date >= ?
         GROUP BY source
         ORDER BY pv DESC
         LIMIT 20`,
      )
      .bind(start)
      .all<{ source: string; pv: number }>(),
    env.DB
      .prepare(
        `SELECT bot, COUNT(*) AS hits
         FROM crawler_visit_events
         WHERE visit_date >= ?
         GROUP BY bot
         ORDER BY hits DESC
         LIMIT 20`,
      )
      .bind(start)
      .all<{ bot: string; hits: number }>(),
    env.DB
      .prepare(
        `SELECT referrer, COUNT(*) AS pv
         FROM web_visit_events
         WHERE visit_date >= ? AND referrer IS NOT NULL
         GROUP BY referrer
         ORDER BY pv DESC
         LIMIT 20`,
      )
      .bind(start)
      .all<{ referrer: string; pv: number }>(),
  ])
  const sourceRows = sources.results.map((row) => ({
    source: row.source,
    pv: Number(row.pv),
  }))
  return jsonResponse(
    {
      range_days: days,
      sources: sourceRows,
      crawlers: crawlers.results.map((row) => ({
        bot: row.bot,
        hits: Number(row.hits),
      })),
      top_referrers: referrers.results.map((row) => ({
        referrer: row.referrer,
        pv: Number(row.pv),
      })),
      total_attributed_pv: sourceRows.reduce((sum, row) => sum + row.pv, 0),
    },
    200,
    requestId,
    request.method,
  )
}

export async function handleAdminAnalyticsRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`
  if (route === 'POST /api/v1/track/visit') {
    return ingestVisit(request, env, requestId)
  }
  if (route === 'POST /api/v1/track/crawler') {
    return ingestCrawler(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/visit-stats') {
    return visitStats(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/source-stats') {
    return sourceStats(request, env, requestId)
  }
  return null
}
