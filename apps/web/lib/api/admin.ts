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
  banned: boolean
  plan: string
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

// ── 用户详情(刀3a · 纯只读聚合)──
export interface AdminQuotaUsage {
  feature: string
  used: number | null // Redis 故障 → null(显 "—")
  limit: number
}

export interface AdminRedeemedItem {
  code: string
  period: string
  redeemed_at: string
}

export interface AdminActionItem {
  action: string
  detail: Record<string, unknown>
  created_at: string
}

export interface AdminUserDetail {
  id: string
  email: string
  role: string
  created_at: string
  email_verified: boolean
  banned: boolean
  plan: string
  plan_status: string | null
  plan_expires_at: string | null
  plan_source: string | null
  quota: AdminQuotaUsage[]
  invite_code: string | null
  invited_count: number
  rewarded_count: number
  redeemed: AdminRedeemedItem[]
  admin_actions: AdminActionItem[]
}

export interface GrantResult {
  plan: string
  expires_at: string | null
  days_added: number
}

/** 管理员授予/延长 Pro(刀3b-1 · 写操作)。 */
export async function grantPro(
  token: string,
  userId: string,
  body: { period?: string; days?: number; note?: string | null },
): Promise<GrantResult> {
  const r = await fetch(`${API_BASE}/api/v1/admin/users/${userId}/grant`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as GrantResult
}

/** 管理员封禁/解封(刀3b-2 · 写操作 · 方案A 禁止登录)。 */
export async function setBan(
  token: string,
  userId: string,
  ban: boolean,
  note?: string | null,
): Promise<{ user_id: string; banned: boolean }> {
  const action = ban ? 'ban' : 'unban'
  const r = await fetch(`${API_BASE}/api/v1/admin/users/${userId}/${action}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ note: note ?? null }),
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as { user_id: string; banned: boolean }
}

export async function fetchAdminUserDetail(
  token: string,
  userId: string,
  signal?: AbortSignal,
): Promise<AdminUserDetail> {
  const r = await fetch(`${API_BASE}/api/v1/admin/users/${userId}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as AdminUserDetail
}

// ── 网站访问看板(PV/UV 趋势 + 注册趋势)──

export interface VisitDailyPoint {
  date: string // yyyy-mm-dd(CN 日)
  pv: number
  uv: number
}

export interface RegistrationPoint {
  date: string
  count: number
}

export interface VisitStats {
  range_days: number
  daily: VisitDailyPoint[]
  registrations: RegistrationPoint[]
  today: VisitDailyPoint
  yesterday: VisitDailyPoint
  cumulative_pv: number
  cumulative_uv: number
  total_registrations: number
}

export async function fetchAdminVisitStats(
  token: string,
  days: number,
  signal?: AbortSignal,
): Promise<VisitStats> {
  const r = await fetch(`${API_BASE}/api/v1/admin/visit-stats?days=${days}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as VisitStats
}

// ── 训练营「答题赢会员」统计(刀4)──────────────────────────────────────────

export interface AcademyStageStat {
  stage: string // 阶 slug(前端 map manifest 取中文名)
  learners: number
  submissions: number
  passers: number
  awards: number
}

export interface AcademyDayPoint {
  date: string
  count: number
}

export interface AcademyStats {
  range_days: number
  learner_count: number
  total_awards: number
  membership_days_granted: number // 送出会员天数 = total_awards × 7
  total_submissions: number
  pass_rate: number // 0~1
  by_stage: AcademyStageStat[]
  award_trend: AcademyDayPoint[]
  submission_trend: AcademyDayPoint[]
}

export async function fetchAdminAcademyStats(
  token: string,
  days: number,
  signal?: AbortSignal,
): Promise<AcademyStats> {
  const r = await fetch(`${API_BASE}/api/v1/admin/academy-stats?days=${days}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as AcademyStats
}
