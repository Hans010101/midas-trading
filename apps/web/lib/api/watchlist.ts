/**
 * 点金 Midas · 自选股 API client。
 *
 * 包装 /api/v1/watchlist 的 4 个端点(GET / POST / DELETE / PUT reorder)。
 * 所有请求必须带 Bearer JWT(从 NextAuth session.accessToken 取)。
 */

import type { Market } from '@midas/shared'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface WatchlistItem {
  id: number
  symbol: string
  market: Market
  sort_order: number
  added_at: string // ISO 8601 with tz
}

export class WatchlistApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`WatchlistApi ${status}: ${detail}`)
    this.name = 'WatchlistApiError'
  }
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    return typeof body.detail === 'string' ? body.detail : `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

function authHeaders(token: string): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  }
}

export async function fetchWatchlist(
  token: string,
  signal?: AbortSignal,
): Promise<WatchlistItem[]> {
  const r = await fetch(`${API_BASE}/api/v1/watchlist`, {
    headers: authHeaders(token),
    signal,
  })
  if (!r.ok) throw new WatchlistApiError(r.status, await readDetail(r))
  return (await r.json()) as WatchlistItem[]
}

export async function addToWatchlist(
  token: string,
  symbol: string,
  market: Market,
): Promise<WatchlistItem> {
  const r = await fetch(`${API_BASE}/api/v1/watchlist`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ symbol, market }),
  })
  if (!r.ok) throw new WatchlistApiError(r.status, await readDetail(r))
  return (await r.json()) as WatchlistItem
}

export async function deleteFromWatchlist(
  token: string,
  id: number,
): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/watchlist/${id}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
  if (!r.ok) throw new WatchlistApiError(r.status, await readDetail(r))
}

export async function reorderWatchlist(
  token: string,
  itemIds: number[],
): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/watchlist/reorder`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify({ item_ids: itemIds }),
  })
  if (!r.ok) throw new WatchlistApiError(r.status, await readDetail(r))
}
