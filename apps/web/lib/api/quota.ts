/**
 * AI 额度 API client(会员刀2)· GET /quota/me · 沙盘/回测/profile 三处共用。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface QuotaItem {
  feature: string
  limit: number
  used: number
}

export interface QuotaMe {
  plan: string
  plan_expires_at: string | null
  items: QuotaItem[]
  reset_at: string
}

export async function fetchQuotaMe(token: string, signal?: AbortSignal): Promise<QuotaMe> {
  const r = await fetch(`${API_BASE}/api/v1/quota/me`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new Error(`QuotaApi HTTP ${r.status}`)
  return (await r.json()) as QuotaMe
}
