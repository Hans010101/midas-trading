/**
 * 管理员 API client(用户管理刀2)· 照 virtual.ts Bearer 范式。
 *
 * ★ 鉴权边界在后端 AdminDep(403):本文件只透传 401/403,
 *   页面据此降级(无权限提示),前端不做任何"安全"判定。
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? '/api-proxy'

export type RegisterMethod = 'google' | 'password' | 'both' | 'sms'

export interface AdminUserItem {
  id: string
  email: string
  display_name: string | null
  role: string
  locked_admin: boolean
  banned: boolean
  created_at: string
  email_verified: boolean
  register_method: RegisterMethod
  last_login_at: string | null
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

export interface AdminOverview {
  total_users: number
  verified_users: number
  active_users_7d: number
  active_sessions: number
  registrations_7d: number
  open_support_tickets: number
  enabled_alert_rules: number
  generated_at: string
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

export async function fetchAdminOverview(
  token: string,
  signal?: AbortSignal,
): Promise<AdminOverview> {
  const r = await fetch(`${API_BASE}/api/v1/admin/overview`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as AdminOverview
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

export interface AdminAuthEvent {
  event_type: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface AdminUserDetail {
  id: string
  email: string
  display_name: string | null
  role: string
  locked_admin: boolean
  created_at: string
  email_verified: boolean
  banned: boolean
  register_method: RegisterMethod
  last_login_at: string | null
  last_active_7d: string | null
  active_sessions: number
  alert_rules_count: number
  notifications_count: number
  unread_notifications_count: number
  support_ticket_count: number
  auth_events: AdminAuthEvent[]
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

export async function revokeUserSessions(
  token: string,
  userId: string,
): Promise<{
  user_id: string
  revoked_sessions: number
  kept_current_session: boolean
}> {
  const r = await fetch(
    `${API_BASE}/api/v1/admin/users/${userId}/revoke-sessions`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    },
  )
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as {
    user_id: string
    revoked_sessions: number
    kept_current_session: boolean
  }
}

export type SupportTicketStatus = 'open' | 'resolved' | 'closed'

export interface AdminSupportTicket {
  id: number
  user_id: string
  account_email: string
  contact_email: string
  category: string
  description: string
  related_order_id: string | null
  image_count: number
  status: SupportTicketStatus
  created_at: string
}

export interface AdminSupportTicketList {
  items: AdminSupportTicket[]
  total: number
  page: number
  page_size: number
}

export async function fetchAdminSupportTickets(
  token: string,
  params: { page?: number; pageSize?: number; status?: SupportTicketStatus },
  signal?: AbortSignal,
): Promise<AdminSupportTicketList> {
  const qs = new URLSearchParams({
    page: String(params.page ?? 1),
    page_size: String(params.pageSize ?? 20),
  })
  if (params.status) qs.set('status', params.status)
  const r = await fetch(`${API_BASE}/api/v1/admin/support-tickets?${qs}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as AdminSupportTicketList
}

export async function updateAdminSupportTicket(
  token: string,
  ticketId: number,
  status: SupportTicketStatus,
): Promise<{ ticket_id: number; status: SupportTicketStatus }> {
  const r = await fetch(
    `${API_BASE}/api/v1/admin/support-tickets/${ticketId}`,
    {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ status }),
    },
  )
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as {
    ticket_id: number
    status: SupportTicketStatus
  }
}

/** ★superadmin 设/取铂金标记(多账户 PR-1 · 享受所有 pro 权益 · 仿 setBan)。 */
export async function setPlatinum(
  token: string,
  userId: string,
  isPlatinum: boolean,
  note?: string | null,
): Promise<{ user_id: string; is_platinum: boolean }> {
  const r = await fetch(`${API_BASE}/api/v1/admin/users/${userId}/set-platinum`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_platinum: isPlatinum, note: note ?? null }),
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as { user_id: string; is_platinum: boolean }
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

export interface VisitHourlyPoint {
  hour: number // 0-23(CST)
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
  hourly: VisitHourlyPoint[] // ★当天 24 小时分布(Redis 实时 · 上线后渐满)
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

// ── SEO 批6:流量来源归因 + AI 爬虫看板 ──────────────────────────────────────
export interface SourceCount {
  source: string
  pv: number
}
export interface CrawlerCount {
  bot: string
  hits: number
}
export interface ReferrerCount {
  referrer: string
  pv: number
}
export interface SourceStats {
  range_days: number
  sources: SourceCount[]
  crawlers: CrawlerCount[]
  top_referrers: ReferrerCount[]
  total_attributed_pv: number
}

export async function fetchAdminSourceStats(
  token: string,
  days: number,
  signal?: AbortSignal,
): Promise<SourceStats> {
  const r = await fetch(`${API_BASE}/api/v1/admin/source-stats?days=${days}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as SourceStats
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

// ── 周报全自动发送(weekly-dispatch)· 上传成品 PDF+md → 提取 → 定时/补传发送 ──────
export interface WeeklyDispatchItem {
  id: number
  year: number
  week: number
  period_start: string
  period_end: string
  title: string
  status: string // uploaded | sent | skipped
  uploaded_at: string
  sent_at: string | null
}

export interface WeeklyUploadResult {
  id: number
  year: number
  week: number
  status: string // ★上传只入库 uploaded,不自动发
  extracted: Record<string, unknown>
  missing: string[]
  email_html: string
  pdf_filename: string
}

export interface WeeklyDispatchDetail extends WeeklyDispatchItem {
  pdf_filename: string
  extracted: Record<string, unknown>
  email_html: string
  next_send_label: string // 下一个周日 21:00(「M月D日21:00」· scheduled 展示)
}

export interface WeeklySendResult {
  dispatch_id: number
  year: number
  week: number
  recipients: number
  email_sent: number
  email_failed: number
  notify_sent: number
  notify_failed: number
  skipped: boolean
}

export async function fetchWeeklyDispatches(
  token: string,
  signal?: AbortSignal,
): Promise<{ items: WeeklyDispatchItem[]; next_send_label: string }> {
  const r = await fetch(`${API_BASE}/api/v1/admin/weekly-dispatch`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as { items: WeeklyDispatchItem[]; next_send_label: string }
}

export async function fetchWeeklyDispatch(
  token: string,
  id: number,
  signal?: AbortSignal,
): Promise<WeeklyDispatchDetail> {
  const r = await fetch(`${API_BASE}/api/v1/admin/weekly-dispatch/${id}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as WeeklyDispatchDetail
}

/** 上传成品周报(PDF + md · multipart)→ 解析 + 存 OSS + 补救窗口内可上传即发。 */
export async function uploadWeeklyDispatch(
  token: string,
  pdf: File,
  md: File,
): Promise<WeeklyUploadResult> {
  const form = new FormData()
  form.append('pdf', pdf)
  form.append('md', md)
  const r = await fetch(`${API_BASE}/api/v1/admin/weekly-dispatch/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` }, // ★不手设 Content-Type
    body: form,
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as WeeklyUploadResult
}

/** ★「计划发送」(主)· uploaded/scheduled → scheduled · 纯标记,等周日21:00定时发。 */
export async function scheduleWeeklyDispatch(
  token: string,
  id: number,
): Promise<WeeklyDispatchDetail> {
  const r = await fetch(`${API_BASE}/api/v1/admin/weekly-dispatch/${id}/schedule`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as WeeklyDispatchDetail
}

/** 「取消计划」· scheduled → uploaded(21:00前撤回改稿)。 */
export async function cancelWeeklyDispatchSchedule(
  token: string,
  id: number,
): Promise<WeeklyDispatchDetail> {
  const r = await fetch(`${API_BASE}/api/v1/admin/weekly-dispatch/${id}/cancel-schedule`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as WeeklyDispatchDetail
}

/** ★「立即发送」(辅)· 当场发送 · 已发幂等跳过 · ★前端二次确认后才调。 */
export async function sendWeeklyDispatchNow(
  token: string,
  id: number,
): Promise<WeeklySendResult> {
  const r = await fetch(`${API_BASE}/api/v1/admin/weekly-dispatch/${id}/send-now`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!r.ok) throw new AdminApiError(r.status, await readDetail(r))
  return (await r.json()) as WeeklySendResult
}
