/**
 * 飞书绑定 API client · ADR 0032 阶段三(对称 telegram.ts)。
 *
 * POST /feishu/bind-token 生成一次性绑定码(登录态)· POST /feishu/unbind 解绑。
 * 飞书无 t.me 式 deep link,绑定码由用户手动发给 bot(粘贴或 /bind <码>)。
 * 应用未配置(FEISHU_APP_ID/SECRET 未设)→ bind-token 返回 503,UI 降级为「绑定即将开放」。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export interface FeishuBindTokenResult {
  token: string
  expires_in: number
  /** 飞书应用 App ID(公开标识 · 非密钥)· 用于拼 applink 一键打开机器人会话。 */
  app_id: string
}

/** applink:一键在飞书中打开机器人会话(飞书 3.40.0+ · 只带 appId,不能带 token)。 */
export function feishuBotOpenLink(appId: string): string {
  return `https://applink.feishu.cn/client/bot/open?appId=${encodeURIComponent(appId)}`
}

export class FeishuApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`FeishuApi ${status}: ${detail}`)
    this.name = 'FeishuApiError'
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

export async function createFeishuBindToken(
  token: string,
): Promise<FeishuBindTokenResult> {
  const r = await fetch(`${API_BASE}/api/v1/feishu/bind-token`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!r.ok) throw new FeishuApiError(r.status, await readDetail(r))
  return (await r.json()) as FeishuBindTokenResult
}

export async function unbindFeishu(token: string): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/feishu/unbind`, {
    method: 'POST',
    headers: authHeaders(token),
  })
  if (!r.ok) throw new FeishuApiError(r.status, await readDetail(r))
}
