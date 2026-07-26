/**
 * 当前用户资料 API client · /auth/me + 改密码 + 头像。照 quota.ts Bearer 范式。
 *
 * 🔴 密码明文只在请求体传输,不入任何前端持久化;头像只传编号(零图片存储)。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export interface MeResponse {
  user_id: string
  email: string
  email_verified: boolean
  role: string
  has_password: boolean // false = OAuth-only(无密码)→ 不显示改密码表单
  avatar_id: number | null // NULL/0=首字母 · 1-16=预设头像
  is_platinum: boolean // 铂金标记 · 前端据此显/隐铂金自助入口(PR-6 · 真边界在后端 PlatinumDep)
  language_pref: string | null // 'zh' | 'en' | null(未设)· i18n 跨设备同步用(后端 resolve_lang level②)
}

export class MeApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`MeApi ${status}: ${detail}`)
    this.name = 'MeApiError'
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

export async function fetchMe(token: string, signal?: AbortSignal): Promise<MeResponse> {
  const r = await fetch(`${API_BASE}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new MeApiError(r.status, await readDetail(r))
  return (await r.json()) as MeResponse
}

export async function changePassword(
  token: string, oldPassword: string, newPassword: string,
): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/auth/change-password`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  })
  if (!r.ok) throw new MeApiError(r.status, await readDetail(r))
}

/** 保存语言偏好(登录用户跨设备同步)· PATCH /user/language · 后端写 User.language_pref。 */
export async function setLanguage(token: string, language: 'zh' | 'en'): Promise<void> {
  const r = await fetch(`${API_BASE}/api/v1/user/language`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ language }),
  })
  if (!r.ok) throw new MeApiError(r.status, await readDetail(r))
}

/** 选预设头像(0=恢复默认首字母 · 1-16=预设)· 返回服务端最终 avatar_id。 */
export async function setAvatar(token: string, avatarId: number): Promise<number | null> {
  const r = await fetch(`${API_BASE}/api/v1/user/avatar`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ avatar_id: avatarId }),
  })
  if (!r.ok) throw new MeApiError(r.status, await readDetail(r))
  const body = (await r.json()) as { avatar_id: number | null }
  return body.avatar_id
}
