/**
 * X 营销自动托管 · 后台 API client(自动托管 PR-4)。
 *
 * GET  /api/v1/admin/x-auto/status  → 开关/熔断/日配额/时段
 * POST /api/v1/admin/x-auto/toggle  → 开/关总开关(★默认 OFF · 开=自动起草+自动发)
 * POST /api/v1/admin/x-auto/stop    → ★紧急熔断(关开关+熔断+revoke 排队任务)
 *
 * 🔴 全 admin 端点(后端 AdminDep 403 强制)· fetch 透传 session token。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface AutoPilotPlatformItem {
  platform: string // 平台标识(binance_square / x / …)
  checked: boolean // Redis 勾选(binance 默认 ON · 其它默认 OFF)
  auto_allowed: boolean // ★硬编码白名单内(false = 灰显「暂未启用」· X 现阶段 false)
  adapter_enabled: boolean // API Key 配齐
}

export interface AutoPilotStatus {
  enabled: boolean // 总开关(默认 OFF)
  circuit_open: boolean // 熔断中(连续失败触发 · 开则停所有自动发)
  daily_used: number // 今日已自动发布
  daily_remaining: number // 今日剩余配额(50 封顶)
  in_window: boolean // 当前在发布时段(7:30-22:30 CST)
  platforms: AutoPilotPlatformItem[] // ★平台勾选(架子刀 · ADR 0050)
}

export interface AutoPilotStopOut {
  stopped: boolean
  revoked: number
  message: string
}

function _authHeaders(token?: string): HeadersInit | undefined {
  return token ? { Authorization: `Bearer ${token}` } : undefined
}

export async function getAutoPilotStatus(
  token: string,
  signal?: AbortSignal,
): Promise<AutoPilotStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-auto/status`, {
    headers: _authHeaders(token),
    signal,
  })
  if (!r.ok) throw new Error(`x-auto status HTTP ${r.status}`)
  return (await r.json()) as AutoPilotStatus
}

/** 开/关自动托管(★开 = 全自动起草+发布上线 · 调用方应在开启前二次确认)。 */
export async function toggleAutoPilot(token: string, enabled: boolean): Promise<AutoPilotStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-auto/toggle`, {
    method: 'POST',
    headers: { ...(_authHeaders(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!r.ok) throw new Error(`x-auto toggle HTTP ${r.status}`)
  return (await r.json()) as AutoPilotStatus
}

/** 勾/取消自动发布平台(★白名单外后端 400 拒 · X 现阶段「暂未启用」· ADR 0050)。 */
export async function toggleAutoPlatform(
  token: string,
  platform: string,
  checked: boolean,
): Promise<AutoPilotStatus> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-auto/platforms/${platform}`, {
    method: 'POST',
    headers: { ...(_authHeaders(token) ?? {}), 'Content-Type': 'application/json' },
    body: JSON.stringify({ checked }),
  })
  if (!r.ok) {
    const detail = await r.json().catch(() => null)
    throw new Error(detail?.detail ?? `x-auto platform toggle HTTP ${r.status}`)
  }
  return (await r.json()) as AutoPilotStatus
}

/** ★紧急熔断:立刻停止自动托管(关开关 + 熔断 + revoke 排队任务)。 */
export async function stopAutoPilot(token: string): Promise<AutoPilotStopOut> {
  const r = await fetch(`${API_BASE}/api/v1/admin/x-auto/stop`, {
    method: 'POST',
    headers: _authHeaders(token),
  })
  if (!r.ok) throw new Error(`x-auto stop HTTP ${r.status}`)
  return (await r.json()) as AutoPilotStopOut
}
