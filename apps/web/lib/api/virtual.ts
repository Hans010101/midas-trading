/**
 * 虚拟交易 API client · 0008 v2 三独立子账户。
 *
 * 8 个 endpoint 全部需要 Bearer JWT(从 NextAuth session.accessToken 取)。
 * 金额字段全部 string(后端 Decimal 序列化为 string,避免 JS 浮点精度损失)。
 */

import type { Market } from '@midas/shared'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type Currency = 'CNY' | 'USD' | 'USDT'
export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market'
export type OrderStatus = 'filled' | 'rejected'
// 3.4 · 持仓方向 · long=做多(A股/加密/美股做多)· short=美股卖空(SELL 开空 / BUY 平空)
export type PositionSide = 'long' | 'short'

export interface VirtualAccount {
  id: number
  market: Market
  currency: Currency
  initial_capital: string
  cash_balance: string
  realized_pnl: string
  activated_at: string
}

export interface PositionView {
  id: number
  symbol: string
  market: Market
  position_side: PositionSide
  quantity: string
  avg_entry_price: string
  current_price: string | null
  unrealized_pnl: string | null
  value: string | null
}

export interface AccountSummary {
  account_id: number
  market: Market
  currency: Currency
  initial_capital: string
  cash_balance: string
  realized_pnl: string
  positions: PositionView[]
  positions_value: string
  total_equity: string
}

export interface Position {
  id: number
  symbol: string
  market: Market
  position_side: PositionSide
  quantity: string
  avg_entry_price: string
  realized_pnl: string | null
  opened_at: string
  closed_at: string | null
}

export interface VirtualOrder {
  id: number | null
  account_id: number | null
  symbol: string
  market: Market
  side: OrderSide
  position_side: PositionSide
  order_type: OrderType
  quantity: string
  price: string | null
  notional: string | null
  commission: string | null
  slippage_cost: string | null
  realized_pnl: string | null
  status: OrderStatus
  reject_reason: string | null
  placed_at: string | null
  filled_at: string | null
}

export interface EquitySnapshot {
  cash: string
  positions_value: string
  equity: string
  realized_pnl_cumulative: string
  snapshot_at: string
}

export interface EquityCurves {
  curves: Record<string, EquitySnapshot[]>
}

export class VirtualApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`VirtualApi ${status}: ${detail}`)
    this.name = 'VirtualApiError'
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

// ===== Accounts =====

export async function fetchAccounts(
  token: string, signal?: AbortSignal,
): Promise<VirtualAccount[]> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/accounts`, {
    headers: authHeaders(token), signal,
  })
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as VirtualAccount[]
}

export async function fetchAccount(
  token: string, market: Market, signal?: AbortSignal,
): Promise<VirtualAccount | null> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/accounts/${market}`, {
    headers: authHeaders(token), signal,
  })
  if (r.status === 404) return null
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as VirtualAccount
}

export async function activateOrResetAccount(
  token: string, market: Market, initialCapital: string,
): Promise<VirtualAccount> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/accounts/${market}`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify({ initial_capital: initialCapital }),
  })
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as VirtualAccount
}

// ===== Portfolio =====

export async function fetchPortfolio(
  token: string, signal?: AbortSignal,
): Promise<AccountSummary[]> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/portfolio`, {
    headers: authHeaders(token), signal,
  })
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as AccountSummary[]
}

// ===== Orders =====

export interface PlaceOrderInput {
  symbol: string
  market: Market
  side: OrderSide
  quantity: string
  // 3.4 · 不传 = long(后端默认 · A股/加密/美股做多原行为不变)· short 仅美股卖空
  position_side?: PositionSide
}

export async function placeOrder(
  token: string, input: PlaceOrderInput,
): Promise<VirtualOrder> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/orders`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(input),
  })
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as VirtualOrder
}

export async function fetchOrders(
  token: string,
  opts: { market?: Market; limit?: number; beforeId?: number } = {},
  signal?: AbortSignal,
): Promise<VirtualOrder[]> {
  const params = new URLSearchParams()
  if (opts.market) params.set('market', opts.market)
  if (opts.limit) params.set('limit', String(opts.limit))
  if (opts.beforeId) params.set('before_id', String(opts.beforeId))
  const r = await fetch(
    `${API_BASE}/api/v1/virtual/orders?${params.toString()}`,
    { headers: authHeaders(token), signal },
  )
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as VirtualOrder[]
}

// ===== Positions =====

export async function fetchPositions(
  token: string,
  opts: { includeClosed?: boolean; market?: Market } = {},
  signal?: AbortSignal,
): Promise<Position[]> {
  const params = new URLSearchParams()
  if (opts.includeClosed) params.set('include_closed', 'true')
  if (opts.market) params.set('market', opts.market)
  const r = await fetch(
    `${API_BASE}/api/v1/virtual/positions?${params.toString()}`,
    { headers: authHeaders(token), signal },
  )
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as Position[]
}

// ===== Equity curves =====

export async function fetchEquityCurves(
  token: string, days = 30, signal?: AbortSignal,
): Promise<EquityCurves> {
  const r = await fetch(
    `${API_BASE}/api/v1/virtual/equity-curves?days=${days}`,
    { headers: authHeaders(token), signal },
  )
  if (!r.ok) throw new VirtualApiError(r.status, await readDetail(r))
  return (await r.json()) as EquityCurves
}
