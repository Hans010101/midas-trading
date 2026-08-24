import { authenticate } from './auth'
import {
  HttpError,
  jsonResponse,
  readJsonObject,
  requireString,
} from './http'

const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const DEMO_WATCHLIST = [
  ['BTC/USDT', 'crypto'],
  ['NVDA', 'us'],
  ['600519', 'cn'],
] as const

type WatchlistRow = Readonly<{
  id: number
  symbol: string
  market: string
  sort_order: number
  added_at: number
}>

function output(row: WatchlistRow) {
  return {
    id: row.id,
    symbol: row.symbol,
    market: row.market,
    sort_order: row.sort_order,
    added_at: new Date(row.added_at).toISOString(),
  }
}

async function listRows(
  db: D1Database,
  userId: string,
): Promise<WatchlistRow[]> {
  const result = await db
    .prepare(
      `SELECT id, symbol, market, sort_order, added_at
       FROM watchlist_items
       WHERE user_id = ?
       ORDER BY sort_order ASC, added_at ASC`,
    )
    .bind(userId)
    .all<WatchlistRow>()
  return result.results
}

async function listWatchlist(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  let rows = await listRows(env.DB, user.id)
  if (
    rows.length === 0 &&
    (user.email_verified_at !== null || user.phone_verified_at !== null)
  ) {
    const state = await env.DB
      .prepare(
        'SELECT demo_watchlist_prefilled FROM users WHERE id = ?',
      )
      .bind(user.id)
      .first<{ demo_watchlist_prefilled: number }>()
    if (state?.demo_watchlist_prefilled === 0) {
      const timestamp = Date.now()
      await env.DB.batch([
        ...DEMO_WATCHLIST.map(([symbol, market], index) =>
          env.DB
            .prepare(
              `INSERT OR IGNORE INTO watchlist_items
                (user_id, symbol, market, sort_order, added_at)
               VALUES (?, ?, ?, ?, ?)`,
            )
            .bind(user.id, symbol, market, index, timestamp + index),
        ),
        env.DB
          .prepare(
            `UPDATE users
             SET demo_watchlist_prefilled = 1, updated_at = ?
             WHERE id = ?`,
          )
          .bind(timestamp, user.id),
      ])
      rows = await listRows(env.DB, user.id)
    }
  }
  return jsonResponse(
    rows.map(output),
    200,
    requestId,
    request.method,
  )
}

async function addWatchlist(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const symbol = requireString(body, 'symbol', { min: 1, max: 32 })
    .trim()
    .toUpperCase()
  const market = requireString(body, 'market', { min: 2, max: 10 })
  if (!MARKETS.has(market)) {
    throw new HttpError(422, 'market 不受支持')
  }
  const max = await env.DB
    .prepare(
      `SELECT COALESCE(MAX(sort_order), -1) AS max_order
       FROM watchlist_items
       WHERE user_id = ?`,
    )
    .bind(user.id)
    .first<{ max_order: number }>()
  try {
    const row = await env.DB
      .prepare(
        `INSERT INTO watchlist_items
          (user_id, symbol, market, sort_order, added_at)
         VALUES (?, ?, ?, ?, ?)
         RETURNING id, symbol, market, sort_order, added_at`,
      )
      .bind(
        user.id,
        symbol,
        market,
        (max?.max_order ?? -1) + 1,
        Date.now(),
      )
      .first<WatchlistRow>()
    if (!row) throw new Error('Watchlist insert did not return a row')
    return jsonResponse(output(row), 201, requestId, request.method)
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.includes('UNIQUE constraint failed')
    ) {
      throw new HttpError(409, '该标的已在自选列表中')
    }
    throw error
  }
}

async function deleteWatchlist(
  request: Request,
  env: Env,
  requestId: string,
  itemId: number,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const result = await env.DB
    .prepare(
      `DELETE FROM watchlist_items
       WHERE id = ? AND user_id = ?
       RETURNING id`,
    )
    .bind(itemId, user.id)
    .first<{ id: number }>()
  if (!result) throw new HttpError(404, '自选项不存在')
  return jsonResponse(null, 204, requestId, request.method)
}

async function reorderWatchlist(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  if (
    !Array.isArray(body.item_ids) ||
    body.item_ids.some(
      (value) => typeof value !== 'number' || !Number.isSafeInteger(value),
    )
  ) {
    throw new HttpError(422, 'item_ids 必须是整数数组')
  }
  const itemIds = body.item_ids as number[]
  if (new Set(itemIds).size !== itemIds.length) {
    throw new HttpError(422, 'item_ids 不能重复')
  }

  const owned = await env.DB
    .prepare(
      `SELECT id
       FROM watchlist_items
       WHERE user_id = ?`,
    )
    .bind(user.id)
    .all<{ id: number }>()
  const ownedIds = new Set(owned.results.map(({ id }) => id))
  if (itemIds.some((id) => !ownedIds.has(id))) {
    throw new HttpError(404, '自选项不存在')
  }

  if (itemIds.length > 0) {
    await env.DB.batch(
      itemIds.map((id, index) =>
        env.DB
          .prepare(
            `UPDATE watchlist_items
             SET sort_order = ?
             WHERE id = ? AND user_id = ?`,
          )
          .bind(index, id, user.id),
      ),
    )
  }
  return jsonResponse(
    { status: 'ok', reordered: itemIds.length },
    200,
    requestId,
    request.method,
  )
}

export async function handleWatchlistRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path === '/api/v1/watchlist' && request.method === 'GET') {
    return listWatchlist(request, env, requestId)
  }
  if (path === '/api/v1/watchlist' && request.method === 'POST') {
    return addWatchlist(request, env, requestId)
  }
  if (path === '/api/v1/watchlist/reorder' && request.method === 'PUT') {
    return reorderWatchlist(request, env, requestId)
  }
  const match = /^\/api\/v1\/watchlist\/(\d+)$/u.exec(path)
  if (match && request.method === 'DELETE') {
    return deleteWatchlist(request, env, requestId, Number(match[1]))
  }
  return path.startsWith('/api/v1/watchlist')
    ? jsonResponse(
        { detail: 'Route not found' },
        404,
        requestId,
        request.method,
      )
    : null
}
