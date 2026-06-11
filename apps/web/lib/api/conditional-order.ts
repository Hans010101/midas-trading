/**
 * 条件单 API client(ADR 0041 刀3)· 照 virtual.ts authed 范式。
 *
 * 三端点(刀1 已上生产):
 *   POST   /api/v1/virtual/conditional-orders        挂单(LIMIT / SL / TP)
 *   GET    /api/v1/virtual/conditional-orders?status= 列表(仅本人 · 倒序)
 *   DELETE /api/v1/virtual/conditional-orders/{id}    撤单(仅 ACTIVE → 204)
 *
 * 金额字段全 string(房规:后端 Decimal 序列化 string,避免 JS 浮点损失)。
 * 🔴 红线:挂/撤/看,成交由后端 60s 扫描器走唯一虚拟撮合入口 · 前端绝不撮合。
 */

import type { ConditionalKind, ConditionalStatus } from '@/lib/conditional'
import type { OrderSide, PositionSide } from '@/lib/api/virtual'
import type { Market } from '@midas/shared'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface ConditionalOrderCreate {
  symbol: string
  market: Market
  order_kind: ConditionalKind
  side: OrderSide
  /** 不传 = long(后端默认)· 仅空头仓的 SL/TP 传 short */
  position_side?: PositionSide
  trigger_price: string
  /** LIMIT 必填;SL/TP 省略 = 触发时平全仓 */
  quantity?: string
}

export interface ConditionalOrder {
  id: number
  symbol: string
  market: string
  order_kind: ConditionalKind
  side: OrderSide
  position_side: PositionSide
  trigger_price: string
  quantity: string | null
  status: ConditionalStatus
  triggered_order_id: number | null
  note: string | null
  created_at: string
  updated_at: string
}

export class ConditionalApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`ConditionalApi ${status}: ${detail}`)
    this.name = 'ConditionalApiError'
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

export async function postConditionalOrder(
  token: string, input: ConditionalOrderCreate,
): Promise<ConditionalOrder> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/conditional-orders`, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(input),
  })
  if (!r.ok) throw new ConditionalApiError(r.status, await readDetail(r))
  return (await r.json()) as ConditionalOrder
}

export async function listConditionalOrders(
  token: string, opts: { status?: ConditionalStatus } = {}, signal?: AbortSignal,
): Promise<ConditionalOrder[]> {
  const qs = opts.status ? `?status=${opts.status}` : ''
  const r = await fetch(`${API_BASE}/api/v1/virtual/conditional-orders${qs}`, {
    headers: authHeaders(token), signal,
  })
  if (!r.ok) throw new ConditionalApiError(r.status, await readDetail(r))
  return (await r.json()) as ConditionalOrder[]
}

export async function cancelConditionalOrder(token: string, id: number): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/virtual/conditional-orders/${id}`, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
  if (!r.ok) throw new ConditionalApiError(r.status, await readDetail(r))
}
