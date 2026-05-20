/**
 * 推送通知 API client · 0009 v2。
 *
 * GET /config 返回截断展示的 token(前 10 + ... + 后 4 字符)。
 * PUT /config 部分更新 · 空字符串清空 · 字段不传 = 保持原值。
 * POST /test?channel=feishu|telegram 用当前配置发测试消息。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface NotificationConfig {
  feishu_webhook_url: string | null
  tg_bot_token: string | null  // 截断展示 · 不是真 token
  tg_chat_id: string | null
  trade_alert_enabled: boolean
  price_alert_enabled: boolean
  has_feishu: boolean
  has_telegram: boolean
}

export interface NotificationConfigUpdate {
  feishu_webhook_url?: string | null
  tg_bot_token?: string | null
  tg_chat_id?: string | null
  trade_alert_enabled?: boolean
  price_alert_enabled?: boolean
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
  token: string, channel: 'feishu' | 'telegram',
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
