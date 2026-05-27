/**
 * 告警规则 API client · 0026 G5(复用 G2b CRUD + G5 一键应用推荐)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type Operator = 'gt' | 'gte' | 'lt' | 'lte'

export interface IndicatorMeta {
  key: string
  label: string
  category: string
  markets: string[]
  requires_symbol: boolean
  needs_timeframe: boolean
  unit: string | null
}

export interface AlertRule {
  id: number
  market: string
  symbol: string | null
  indicator: string
  operator: Operator
  threshold: string // Decimal → JSON string
  timeframe: string | null
  enabled: boolean
  cooldown_sec: number
}

export interface AlertRuleCreate {
  market: string
  symbol?: string | null
  indicator: string
  operator: Operator
  threshold: number
  timeframe?: string | null
}

export interface ApplyRecommendedResult {
  created: number
  skipped: number
}

export class AlertRulesApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`AlertRulesApi ${status}: ${detail}`)
    this.name = 'AlertRulesApiError'
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
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

export async function fetchIndicators(token: string, signal?: AbortSignal): Promise<IndicatorMeta[]> {
  const r = await fetch(`${API_BASE}/api/v1/alert-rules/indicators`, {
    headers: authHeaders(token), signal,
  })
  if (!r.ok) throw new AlertRulesApiError(r.status, await readDetail(r))
  return (await r.json()) as IndicatorMeta[]
}

export async function fetchAlertRules(token: string, signal?: AbortSignal): Promise<AlertRule[]> {
  const r = await fetch(`${API_BASE}/api/v1/alert-rules`, { headers: authHeaders(token), signal })
  if (!r.ok) throw new AlertRulesApiError(r.status, await readDetail(r))
  return (await r.json()) as AlertRule[]
}

export async function createAlertRule(token: string, body: AlertRuleCreate): Promise<AlertRule> {
  const r = await fetch(`${API_BASE}/api/v1/alert-rules`, {
    method: 'POST', headers: authHeaders(token), body: JSON.stringify(body),
  })
  if (!r.ok) throw new AlertRulesApiError(r.status, await readDetail(r))
  return (await r.json()) as AlertRule
}

export async function setAlertRuleEnabled(token: string, id: number, enabled: boolean): Promise<AlertRule> {
  const r = await fetch(`${API_BASE}/api/v1/alert-rules/${id}`, {
    method: 'PATCH', headers: authHeaders(token), body: JSON.stringify({ enabled }),
  })
  if (!r.ok) throw new AlertRulesApiError(r.status, await readDetail(r))
  return (await r.json()) as AlertRule
}

export async function deleteAlertRule(token: string, id: number): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/alert-rules/${id}`, {
    method: 'DELETE', headers: authHeaders(token),
  })
  if (!r.ok && r.status !== 204) throw new AlertRulesApiError(r.status, await readDetail(r))
}

export async function applyRecommended(token: string): Promise<ApplyRecommendedResult> {
  const r = await fetch(`${API_BASE}/api/v1/alert-rules/apply-recommended`, {
    method: 'POST', headers: authHeaders(token),
  })
  if (!r.ok) throw new AlertRulesApiError(r.status, await readDetail(r))
  return (await r.json()) as ApplyRecommendedResult
}
