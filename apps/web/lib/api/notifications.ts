/**
 * 推送通知 API client · 0009 → 0025 G2a 统一 Telegram bot。
 *
 * GET /config 返回绑定状态 + 总开关(不再有飞书 / per-user token)。
 * PUT /config 只更新总开关 · Telegram 绑定经 bot 内 /start。
 * POST /test?channel=telegram 经统一 bot 发测试消息。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export interface NotificationConfig {
  tg_chat_id: string | null
  trade_alert_enabled: boolean
  price_alert_enabled: boolean
  // P3 · 市场周报订阅(默认 false · 选择性订阅)
  weekly_report_enabled: boolean
  // 做T M2-4 · 做T信号 TG 通知拆两体系(都 Pro 专属 · 默认 false · opt-in)
  dott_digest_enabled: boolean       // 体系1 · 每小时定时全景
  dott_transition_enabled: boolean   // 体系2 · 行情转换
  econ_alert_enabled: boolean
  econ_alert_minutes: 15 | 30 | 60
  has_telegram: boolean
  // ADR 0032 阶段三 · 是否已绑定飞书
  has_feishu: boolean
  // 0028 N2 · 安静时段(N1 已落 DB · 本期接前端)
  quiet_hours_enabled: boolean
  // 起止小时 0-23 · start > end 表示跨夜(如 23-7)
  quiet_hours_start: number
  quiet_hours_end: number
  // IANA tz 名(如 "Asia/Shanghai")
  quiet_hours_tz: string
}

export interface NotificationConfigUpdate {
  trade_alert_enabled?: boolean
  price_alert_enabled?: boolean
  // P3 · 市场周报订阅开关(undefined = 不动)
  weekly_report_enabled?: boolean
  // 做T M2-4 · 做T信号 TG 通知拆两体系(★Pro 专属 · 后端二道 gate · undefined = 不动)
  dott_digest_enabled?: boolean
  dott_transition_enabled?: boolean
  econ_alert_enabled?: boolean
  econ_alert_minutes?: 15 | 30 | 60
  // 0028 N2 · 4 字段各自可选(undefined = 不动,后端 None 语义)
  quiet_hours_enabled?: boolean
  quiet_hours_start?: number
  quiet_hours_end?: number
  quiet_hours_tz?: string
}

export interface NotificationTestResult {
  channel: string
  ok: boolean
  error: string | null
}

export class NotificationApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`NotificationApi ${status}: ${detail}`)
    this.name = 'NotificationApiError'
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

export async function fetchNotificationConfig(
  token: string, signal?: AbortSignal,
): Promise<NotificationConfig> {
  const r = await fetch(`${API_BASE}/api/v1/notifications/config`, {
    cache: 'no-store',
    headers: authHeaders(token), signal,
  })
  if (!r.ok) throw new NotificationApiError(r.status, await readDetail(r))
  return (await r.json()) as NotificationConfig
}

export async function updateNotificationConfig(
  token: string, update: NotificationConfigUpdate,
): Promise<NotificationConfig> {
  const r = await fetch(`${API_BASE}/api/v1/notifications/config`, {
    method: 'PUT',
    headers: authHeaders(token),
    body: JSON.stringify(update),
  })
  if (!r.ok) throw new NotificationApiError(r.status, await readDetail(r))
  return (await r.json()) as NotificationConfig
}

export async function sendTestNotification(
  token: string, channel: 'telegram' | 'feishu' = 'telegram',
): Promise<NotificationTestResult> {
  const r = await fetch(
    `${API_BASE}/api/v1/notifications/test?channel=${channel}`,
    {
      method: 'POST',
      headers: authHeaders(token),
    },
  )
  if (!r.ok) throw new NotificationApiError(r.status, await readDetail(r))
  return (await r.json()) as NotificationTestResult
}
