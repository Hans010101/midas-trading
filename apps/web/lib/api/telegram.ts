/**
 * Telegram 绑定 API client · 0025 M1-G G3。
 *
 * POST /telegram/bind-token 生成一次性绑定 token + deep link(登录态)。
 * POST /telegram/unbind      解绑当前账号(清空 tg_chat_id · D7)。
 *
 * bot 未配置(TG_BOT_TOKEN 未设)→ bind-token 返回 503,UI 优雅降级为「绑定即将开放」。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export interface BindTokenResult {
  token: string
  /** t.me deep link · bot 用户名未配时为 null(回退到手动 /start <token>)。 */
  deep_link: string | null
  expires_in: number
}

export class TelegramApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`TelegramApi ${status}: ${detail}`)
    this.name = 'TelegramApiError'
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

export async function createBindToken(token: string): Promise<BindTokenResult> {
  const r = await fetch(`${API_BASE}/api/v1/telegram/bind-token`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!r.ok) throw new TelegramApiError(r.status, await readDetail(r))
  return (await r.json()) as BindTokenResult
}

export async function unbindTelegram(token: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/telegram/unbind`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!r.ok) throw new TelegramApiError(r.status, await readDetail(r))
}
