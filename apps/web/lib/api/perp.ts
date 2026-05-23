/**
 * 加密永续合约虚拟交易 API client · ADR-0019 v2 · M2-C.1。
 *
 * 🔴 红线:全程虚拟资金 · 绝不接真实下单。
 * 端点需要 Bearer JWT(NextAuth session.accessToken)。
 * 金额字段全部 string(后端 Decimal 序列化为 string,避免 JS 浮点损失)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type PerpSide = 'long' | 'short'
export type PerpIntent = 'open_long' | 'open_short' | 'close'
export type PerpAction = 'open_long' | 'open_short' | 'close_long' | 'close_short'
export type PerpOrderStatus = 'filled' | 'rejected'
export type PerpCloseReason = 'manual' | 'liquidated' | 'reset'

// ── 教学版常量(与后端 perp_fees.py 对齐 · 前端预估实时算用)─────────────────
export const PERP_MAX_LEVERAGE = 20
export const PERP_MIN_LEVERAGE = 1
export const PERP_TAKER_FEE_RATE = 0.0005
export const PERP_SLIPPAGE_BPS = 10
export const PERP_MMR = 0.005

export interface PerpPosition {
  id: number
  symbol: string
  side: PerpSide
  leverage: number
  quantity: string
  entry_price: string
  initial_margin: string
  liquidation_price: string
  realized_pnl: string
  fee_paid: string
  opened_at: string
  closed_at: string | null
  close_reason: PerpCloseReason | null
  mark_price: string | null
  unrealized_pnl: string | null
  liquidation_distance_pct: string | null
  roe_pct: string | null
}

export interface PerpOrder {
  id: number | null
  account_id: number | null
  position_id: number | null
  symbol: string
  action: PerpAction
  leverage: number | null
  quantity: string
  price: string | null
  notional: string | null
  margin_delta: string | null
  fee: string | null
  realized_pnl: string | null
  status: PerpOrderStatus
  reject_reason: string | null
  is_liquidation: boolean
  placed_at: string | null
  filled_at: string | null
}

export interface PlacePerpOrderInput {
  symbol: string
  intent: PerpIntent
  leverage?: number
  margin?: string
  quantity?: string
  close_all?: boolean
}

export class PerpApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`PerpApi ${status}: ${detail}`)
    this.name = 'PerpApiError'
  }
}

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = (await resp.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
    // pydantic 422:detail 是数组
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: string }
      return first.msg ?? `HTTP ${resp.status}`
    }
    return `HTTP ${resp.status}`
  } catch {
    return `HTTP ${resp.status}`
  }
}

function authHeaders(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

export async function placePerpOrder(
  token: string, input: PlacePerpOrderInput,
): Promise<PerpOrder> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/perp/orders`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(input),
  })
  if (!r.ok) throw new PerpApiError(r.status, await readDetail(r))
  return (await r.json()) as PerpOrder
}

export async function fetchPerpPositions(
  token: string,
  opts: { includeClosed?: boolean } = {},
  signal?: AbortSignal,
): Promise<PerpPosition[]> {
  const params = new URLSearchParams()
  if (opts.includeClosed) params.set('include_closed', 'true')
  const r = await fetch(
    `${API_BASE}/api/v1/virtual/perp/positions?${params.toString()}`,
    { headers: authHeaders(token), signal },
  )
  if (!r.ok) throw new PerpApiError(r.status, await readDetail(r))
  return (await r.json()) as PerpPosition[]
}

export async function fetchPerpOrders(
  token: string,
  opts: { symbol?: string; limit?: number; beforeId?: number } = {},
  signal?: AbortSignal,
): Promise<PerpOrder[]> {
  const params = new URLSearchParams()
  if (opts.symbol) params.set('symbol', opts.symbol)
  if (opts.limit) params.set('limit', String(opts.limit))
  if (opts.beforeId) params.set('before_id', String(opts.beforeId))
  const r = await fetch(
    `${API_BASE}/api/v1/virtual/perp/orders?${params.toString()}`,
    { headers: authHeaders(token), signal },
  )
  if (!r.ok) throw new PerpApiError(r.status, await readDetail(r))
  return (await r.json()) as PerpOrder[]
}

// ── 前端预估(开仓预览 · ADR-0019 §5.1 实时算 · 与后端公式一致)────────────────
export interface PerpOpenEstimate {
  fillPrice: number
  quantity: number
  notional: number
  requiredMargin: number
  fee: number
  liquidationPrice: number
  liquidationDistancePct: number
}

export function estimatePerpOpen(
  markPrice: number, side: PerpSide, marginUsdt: number, leverage: number,
): PerpOpenEstimate | null {
  if (markPrice <= 0 || marginUsdt <= 0 || leverage < PERP_MIN_LEVERAGE) return null
  const slip = PERP_SLIPPAGE_BPS / 10000
  const isBuy = side === 'long'
  const fillPrice = isBuy ? markPrice * (1 + slip) : markPrice * (1 - slip)
  const quantity = (marginUsdt * leverage) / fillPrice
  const notional = quantity * fillPrice
  const fee = notional * PERP_TAKER_FEE_RATE
  const liquidationPrice = isBuy
    ? fillPrice * (1 - 1 / leverage + PERP_MMR)
    : fillPrice * (1 + 1 / leverage - PERP_MMR)
  const liquidationDistancePct =
    Math.abs(markPrice - liquidationPrice) / markPrice * 100
  return {
    fillPrice, quantity, notional, requiredMargin: marginUsdt, fee,
    liquidationPrice: Math.max(0, liquidationPrice), liquidationDistancePct,
  }
}
