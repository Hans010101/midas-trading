/**
 * 管理员 API client(用户管理刀2)· 照 virtual.ts Bearer 范式。
 *
 * ★ 鉴权边界在后端 AdminDep(403):本文件只透传 401/403,
 *   页面据此降级(无权限提示),前端不做任何"安全"判定。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

export type RegisterMethod = 'google' | 'password' | 'both'

export interface AdminUserItem {
  id: string
  email: string
  role: string
  created_at: string
  email_verified: boolean
  register_method: RegisterMethod
  /** 未过期 session 的最后活跃时间 · 7 天滚动 TTL 口径 · null = 7 天内无活跃 */
  last_active_7d: string | null
  active_sessions: number
}

export interface AdminUserListOut {
  items: AdminUserItem[]
  total: number
  page: number
  page_size: number
}

export class AdminApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(`AdminApi ${status}: ${detail}`)
    this.name = 'AdminApiError'
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

export async function fetchAdminUsers(
  token: string,
  params: { page: number; pageSize?: number },
  signal?: AbortSignal,
): Promise<AdminUserListOut> {
  const qs = new URLSearchParams({
    page: String(params.page),
    page_size: String(params.pageSize ?? 20),
  })
  const r = await fetch(`${API_BASE}/api/v1/admin/users?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as AdminUserListOut
}
