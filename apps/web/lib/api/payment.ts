/**
 * 会员订阅支付 API client(Phase 2a 刀2)· 照 quota.ts Bearer 范式。
 *
 * - POST /payment/order                      建订单 → Bcon 收款地址
 * - GET  /payment/order/{external_id}/status 订单状态(到账轮询 · 限本人)
 *
 * 🔴 红线:订阅费非交易 · 金额字段全 string(避免 JS 浮点损失)· 前端只展示不撮合。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type Period = 'month' | 'quarter' | 'year'

export interface CreateOrderOut {
  address: string
  payment_amount: string
  external_id: string
  period: string
}

export interface OrderStatusOut {
  external_id: string
  status: 'pending' | 'paid' | 'expired'
  period: string
}

export class PaymentApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`PaymentApi ${status}: ${detail}`)
    this.name = 'PaymentApiError'
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

export async function createPaymentOrder(
  token: string, period: Period,
): Promise<CreateOrderOut> {
  const r = await fetch(`${API_BASE}/api/v1/payment/order`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ period }),
  })
  if (!r.ok) throw new PaymentApiError(r.status, await readDetail(r))
  return (await r.json()) as CreateOrderOut
}

export async function fetchOrderStatus(
  token: string, externalId: string, signal?: AbortSignal,
): Promise<OrderStatusOut> {
  const r = await fetch(
    `${API_BASE}/api/v1/payment/order/${encodeURIComponent(externalId)}/status`,
    { headers: { Authorization: `Bearer ${token}` }, signal },
  )
  if (!r.ok) throw new PaymentApiError(r.status, await readDetail(r))
  return (await r.json()) as OrderStatusOut
}
