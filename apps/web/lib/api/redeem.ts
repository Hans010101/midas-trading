/**
 * 兑换码 API client(兑换码刀2)· 照 quota.ts/admin.ts Bearer 范式。
 * 管理员生成/列表 + 用户兑换。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type RedeemPeriod = 'month' | 'quarter' | 'year'
export type RedeemStatus = 'unused' | 'redeemed' | 'expired'

export interface RedeemCodeItem {
  code: string
  period: string
  status: RedeemStatus
  note: string | null
  redeemed_by_email: string | null
  created_at: string
  expires_at: string
}

export interface RedeemCodeList {
  items: RedeemCodeItem[]
  total: number
  page: number
  page_size: number
}

export interface GenerateResult {
  codes: string[]
  period: string
  days: number
}

export interface RedeemResult {
  plan: string
  days_added: number
  expires_at: string | null
}

/** 兑换失败:保留 status + 结构化 detail(各态友好文案前端解析)。 */
export class RedeemApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(`RedeemApi ${status}`)
    this.name = 'RedeemApiError'
  }
}

async function readDetail(resp: Response): Promise<unknown> {
  try {
    return ((await resp.json()) as { detail?: unknown }).detail ?? null
  } catch {
    return null
  }
}

// ── 管理员 ──
export async function generateCodes(
  token: string,
  body: { period: RedeemPeriod; count: number; note?: string | null },
): Promise<GenerateResult> {
  const r = await fetch(`${API_BASE}/api/v1/admin/redeem-codes`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new RedeemApiError(r.status, await readDetail(r))
  return (await r.json()) as GenerateResult
}

export async function fetchCodes(
  token: string,
  params: { page: number; pageSize?: number },
  signal?: AbortSignal,
): Promise<RedeemCodeList> {
  const qs = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize ?? 20),
  })
  const r = await fetch(`${API_BASE}/api/v1/admin/redeem-codes?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new RedeemApiError(r.status, await readDetail(r))
  return (await r.json()) as RedeemCodeList
}

// ── 用户兑换 ──
export async function redeemCode(token: string, code: string): Promise<RedeemResult> {
  const r = await fetch(`${API_BASE}/api/v1/redeem`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!r.ok) throw new RedeemApiError(r.status, await readDetail(r))
  return (await r.json()) as RedeemResult
}
