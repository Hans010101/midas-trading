import { isLockedAdminEmail } from './admin-policy'
import { authenticate } from './auth'
import {
  HttpError,
  jsonResponse,
  readJsonObject,
} from './http'

type AdminAuth = Awaited<ReturnType<typeof authenticate>>

function iso(timestamp: number | null): string | null {
  return timestamp === null ? null : new Date(timestamp).toISOString()
}

export function integerParam(
  url: URL,
  name: string,
  fallback: number,
  min: number,
  max: number,
): number {
  const value = Number(url.searchParams.get(name) ?? String(fallback))
  if (!Number.isSafeInteger(value) || value < min || value > max) {
    throw new HttpError(422, `${name} 必须在 ${min} 到 ${max} 之间`)
  }
  return value
}

export async function requireAdmin(request: Request, env: Env): Promise<AdminAuth> {
  const auth = await authenticate(request, env)
  if (auth.user.role !== 'admin') {
    throw new HttpError(403, '需要管理员权限')
  }
  return auth
}

function registerMethod(
  googleSub: string | null,
  passwordHash: string | null,
): 'google' | 'password' | 'both' {
  if (googleSub && passwordHash) return 'both'
  return googleSub ? 'google' : 'password'
}

export function adminActionStatement(
  db: D1Database,
  values: Readonly<{
    operatorId: string
    targetUserId?: string | null
    action: string
    detail?: Readonly<Record<string, unknown>>
    createdAt: number
  }>,
): D1PreparedStatement {
  return db
    .prepare(
      `INSERT INTO admin_action_logs
        (id, operator_id, target_user_id, action, detail_json, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      crypto.randomUUID(),
      values.operatorId,
      values.targetUserId ?? null,
      values.action,
      JSON.stringify(values.detail ?? {}),
      values.createdAt,
    )
}

async function overview(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const timestamp = Date.now()
  const since = timestamp - 7 * 24 * 60 * 60 * 1_000
  const [
    users,
    verified,
    activeUsers,
    activeSessions,
    registrations,
    openTickets,
    alertRules,
  ] = await env.DB.batch([
    env.DB.prepare('SELECT COUNT(*) AS count FROM users'),
    env.DB.prepare(
      'SELECT COUNT(*) AS count FROM users WHERE email_verified_at IS NOT NULL',
    ),
    env.DB
      .prepare(
        `SELECT COUNT(DISTINCT user_id) AS count
         FROM sessions
         WHERE revoked_at IS NULL AND expires_at > ? AND last_seen_at >= ?`,
      )
      .bind(timestamp, since),
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count
         FROM sessions
         WHERE revoked_at IS NULL AND expires_at > ?`,
      )
      .bind(timestamp),
    env.DB
      .prepare('SELECT COUNT(*) AS count FROM users WHERE created_at >= ?')
      .bind(since),
    env.DB.prepare(
      "SELECT COUNT(*) AS count FROM support_tickets WHERE status = 'open'",
    ),
    env.DB.prepare(
      'SELECT COUNT(*) AS count FROM alert_rules WHERE enabled = 1',
    ),
  ])
  const count = (result: D1Result<unknown> | undefined) =>
    Number((result?.results[0] as { count?: unknown } | undefined)?.count ?? 0)
  return jsonResponse(
    {
      total_users: count(users),
      verified_users: count(verified),
      active_users_7d: count(activeUsers),
      active_sessions: count(activeSessions),
      registrations_7d: count(registrations),
      open_support_tickets: count(openTickets),
      enabled_alert_rules: count(alertRules),
      generated_at: new Date(timestamp).toISOString(),
    },
    200,
    requestId,
    request.method,
  )
}

type AdminUserListRow = Readonly<{
  id: string
  email: string
  display_name: string | null
  role: string
  banned_at: number | null
  password_hash: string | null
  google_sub: string | null
  email_verified_at: number | null
  last_login_at: number | null
  created_at: number
  last_active: number | null
  active_sessions: number
}>

async function listUsers(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const url = new URL(request.url)
  const page = integerParam(url, 'page', 1, 1, 100_000)
  const pageSize = integerParam(url, 'page_size', 20, 1, 100)
  const timestamp = Date.now()
  const query = url.searchParams.get('query')?.trim().slice(0, 100) ?? ''
  const where = query ? 'WHERE LOWER(u.email) LIKE ?' : ''
  const bindings: unknown[] = query ? [`%${query.toLowerCase()}%`] : []
  const rows = await env.DB
    .prepare(
      `SELECT
         u.id, u.email, u.display_name, u.role, u.banned_at,
         u.password_hash, u.google_sub, u.email_verified_at,
         u.last_login_at, u.created_at,
         MAX(CASE
           WHEN s.revoked_at IS NULL AND s.expires_at > ? THEN s.last_seen_at
           ELSE NULL
         END) AS last_active,
         SUM(CASE
           WHEN s.revoked_at IS NULL AND s.expires_at > ? THEN 1
           ELSE 0
         END) AS active_sessions
       FROM users u
       LEFT JOIN sessions s ON s.user_id = u.id
       ${where}
       GROUP BY u.id
       ORDER BY u.created_at DESC, u.id DESC
       LIMIT ? OFFSET ?`,
    )
    .bind(
      timestamp,
      timestamp,
      ...bindings,
      pageSize,
      (page - 1) * pageSize,
    )
    .all<AdminUserListRow>()
  const total = await env.DB
    .prepare(
      `SELECT COUNT(*) AS count
       FROM users u
       ${where}`,
    )
    .bind(...bindings)
    .first<{ count: number }>()
  return jsonResponse(
    {
      items: rows.results.map((row) => ({
        id: row.id,
        email: row.email,
        display_name: row.display_name,
        role: row.role,
        locked_admin: isLockedAdminEmail(row.email),
        banned: row.banned_at !== null,
        created_at: iso(row.created_at),
        email_verified: row.email_verified_at !== null,
        register_method: registerMethod(row.google_sub, row.password_hash),
        last_login_at: iso(row.last_login_at),
        last_active_7d: iso(row.last_active),
        active_sessions: Number(row.active_sessions),
      })),
      total: Number(total?.count ?? 0),
      page,
      page_size: pageSize,
    },
    200,
    requestId,
    request.method,
  )
}

async function getUser(
  request: Request,
  env: Env,
  requestId: string,
  userId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const timestamp = Date.now()
  const user = await env.DB
    .prepare(
      `SELECT
         id, email, display_name, role, banned_at, password_hash, google_sub,
         email_verified_at, last_login_at, created_at
       FROM users
       WHERE id = ?`,
    )
    .bind(userId)
    .first<Omit<AdminUserListRow, 'last_active' | 'active_sessions'>>()
  if (!user) throw new HttpError(404, '用户不存在')

  const [sessionStats, resourceStats, authEvents, actions] = await Promise.all([
    env.DB
      .prepare(
        `SELECT
           MAX(CASE
             WHEN revoked_at IS NULL AND expires_at > ? THEN last_seen_at
             ELSE NULL
           END) AS last_active,
           SUM(CASE
             WHEN revoked_at IS NULL AND expires_at > ? THEN 1
             ELSE 0
           END) AS active_sessions
         FROM sessions
         WHERE user_id = ?`,
      )
      .bind(timestamp, timestamp, userId)
      .first<{ last_active: number | null; active_sessions: number }>(),
    env.DB
      .prepare(
        `SELECT
           (SELECT COUNT(*) FROM alert_rules WHERE user_id = ?) AS alert_rules,
           (SELECT COUNT(*) FROM in_app_notifications WHERE user_id = ?) AS notifications,
           (SELECT COUNT(*) FROM in_app_notifications
             WHERE user_id = ? AND read_at IS NULL) AS unread_notifications,
           (SELECT COUNT(*) FROM support_tickets WHERE user_id = ?) AS support_tickets`,
      )
      .bind(userId, userId, userId, userId)
      .first<{
        alert_rules: number
        notifications: number
        unread_notifications: number
        support_tickets: number
      }>(),
    env.DB
      .prepare(
        `SELECT event_type, metadata_json, created_at
         FROM auth_events
         WHERE user_id = ?
         ORDER BY created_at DESC
         LIMIT 20`,
      )
      .bind(userId)
      .all<{ event_type: string; metadata_json: string; created_at: number }>(),
    env.DB
      .prepare(
        `SELECT action, detail_json, created_at
         FROM admin_action_logs
         WHERE target_user_id = ?
         ORDER BY created_at DESC
         LIMIT 20`,
      )
      .bind(userId)
      .all<{ action: string; detail_json: string; created_at: number }>(),
  ])

  return jsonResponse(
    {
      id: user.id,
      email: user.email,
      display_name: user.display_name,
      role: user.role,
      locked_admin: isLockedAdminEmail(user.email),
      banned: user.banned_at !== null,
      created_at: iso(user.created_at),
      email_verified: user.email_verified_at !== null,
      register_method: registerMethod(user.google_sub, user.password_hash),
      last_login_at: iso(user.last_login_at),
      last_active_7d: iso(sessionStats?.last_active ?? null),
      active_sessions: Number(sessionStats?.active_sessions ?? 0),
      alert_rules_count: Number(resourceStats?.alert_rules ?? 0),
      notifications_count: Number(resourceStats?.notifications ?? 0),
      unread_notifications_count: Number(
        resourceStats?.unread_notifications ?? 0,
      ),
      support_ticket_count: Number(resourceStats?.support_tickets ?? 0),
      auth_events: authEvents.results.map((event) => ({
        event_type: event.event_type,
        metadata: JSON.parse(event.metadata_json) as unknown,
        created_at: iso(event.created_at),
      })),
      admin_actions: actions.results.map((action) => ({
        action: action.action,
        detail: JSON.parse(action.detail_json) as unknown,
        created_at: iso(action.created_at),
      })),
    },
    200,
    requestId,
    request.method,
  )
}

async function setUserBan(
  request: Request,
  env: Env,
  requestId: string,
  userId: string,
  banned: boolean,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const target = await env.DB
    .prepare('SELECT id, email, banned_at FROM users WHERE id = ?')
    .bind(userId)
    .first<{ id: string; email: string; banned_at: number | null }>()
  if (!target) throw new HttpError(404, '用户不存在')
  if (isLockedAdminEmail(target.email)) {
    throw new HttpError(409, '锁定管理员账号不能停用')
  }
  const body = await readJsonObject(request)
  const note = typeof body.note === 'string'
    ? body.note.trim().slice(0, 500)
    : null
  const timestamp = Date.now()
  const action = banned ? 'user.banned' : 'user.unbanned'
  const statements = [
    env.DB
      .prepare('UPDATE users SET banned_at = ?, updated_at = ? WHERE id = ?')
      .bind(banned ? timestamp : null, timestamp, userId),
    adminActionStatement(env.DB, {
      operatorId: admin.user.id,
      targetUserId: userId,
      action,
      detail: { note },
      createdAt: timestamp,
    }),
  ]
  if (banned) {
    statements.push(
      env.DB
        .prepare(
          `UPDATE sessions
           SET revoked_at = ?
           WHERE user_id = ? AND revoked_at IS NULL`,
        )
        .bind(timestamp, userId),
    )
  }
  await env.DB.batch(statements)
  return jsonResponse(
    { user_id: userId, banned },
    200,
    requestId,
    request.method,
  )
}

async function revokeSessions(
  request: Request,
  env: Env,
  requestId: string,
  userId: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const target = await env.DB
    .prepare('SELECT id, email FROM users WHERE id = ?')
    .bind(userId)
    .first<{ id: string; email: string }>()
  if (!target) throw new HttpError(404, '用户不存在')
  const timestamp = Date.now()
  const keepCurrent = admin.user.id === userId
  const result = await env.DB
    .prepare(
      `UPDATE sessions
       SET revoked_at = ?
       WHERE user_id = ? AND revoked_at IS NULL
         ${keepCurrent ? 'AND id <> ?' : ''}`,
    )
    .bind(timestamp, userId, ...(keepCurrent ? [admin.sessionId] : []))
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    targetUserId: userId,
    action: 'user.sessions_revoked',
    detail: {
      revoked: result.meta.changes,
      kept_current_session: keepCurrent,
    },
    createdAt: timestamp,
  }).run()
  return jsonResponse(
    {
      user_id: userId,
      revoked_sessions: result.meta.changes,
      kept_current_session: keepCurrent,
    },
    200,
    requestId,
    request.method,
  )
}

async function academyStats(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const url = new URL(request.url)
  const days = integerParam(url, 'days', 30, 1, 365)
  const since = Date.now() - days * 24 * 60 * 60 * 1_000
  const [
    learners,
    exams,
    awards,
    progressByStage,
    examsByStage,
    awardsByStage,
    submissionTrend,
  ] = await env.DB.batch([
    env.DB.prepare(
      'SELECT COUNT(DISTINCT user_id) AS count FROM academy_progress',
    ),
    env.DB.prepare(
      `SELECT COUNT(*) AS total,
              SUM(CASE WHEN passed = 1 THEN 1 ELSE 0 END) AS passed
       FROM academy_exam_results`,
    ),
    env.DB.prepare('SELECT COUNT(*) AS count FROM academy_exam_awards'),
    env.DB.prepare(
      `SELECT stage, COUNT(DISTINCT user_id) AS learners
       FROM academy_progress GROUP BY stage`,
    ),
    env.DB.prepare(
      `SELECT stage, COUNT(*) AS submissions,
              COUNT(DISTINCT CASE WHEN passed = 1 THEN user_id END) AS passers
       FROM academy_exam_results GROUP BY stage`,
    ),
    env.DB.prepare(
      `SELECT stage, COUNT(*) AS awards
       FROM academy_exam_awards GROUP BY stage`,
    ),
    env.DB
      .prepare(
        `SELECT strftime('%Y-%m-%d', created_at / 1000, 'unixepoch') AS date,
                COUNT(*) AS count
         FROM academy_exam_results
         WHERE created_at >= ?
         GROUP BY date
         ORDER BY date`,
      )
      .bind(since),
  ])
  const first = (result: D1Result<unknown> | undefined) =>
    result?.results[0] as Record<string, unknown> | undefined
  const stageMap = new Map<string, {
    stage: string
    learners: number
    submissions: number
    passers: number
    awards: number
  }>()
  const stage = (name: string) => {
    const existing = stageMap.get(name)
    if (existing) return existing
    const created = {
      stage: name,
      learners: 0,
      submissions: 0,
      passers: 0,
      awards: 0,
    }
    stageMap.set(name, created)
    return created
  }
  for (const row of (progressByStage?.results ?? []) as Array<Record<string, unknown>>) {
    stage(String(row.stage)).learners = Number(row.learners)
  }
  for (const row of (examsByStage?.results ?? []) as Array<Record<string, unknown>>) {
    const item = stage(String(row.stage))
    item.submissions = Number(row.submissions)
    item.passers = Number(row.passers)
  }
  for (const row of (awardsByStage?.results ?? []) as Array<Record<string, unknown>>) {
    stage(String(row.stage)).awards = Number(row.awards)
  }
  const examSummary = first(exams)
  const totalSubmissions = Number(examSummary?.total ?? 0)
  const passedSubmissions = Number(examSummary?.passed ?? 0)
  return jsonResponse(
    {
      range_days: days,
      learner_count: Number(first(learners)?.count ?? 0),
      total_awards: Number(first(awards)?.count ?? 0),
      membership_days_granted: 0,
      total_submissions: totalSubmissions,
      pass_rate: totalSubmissions > 0
        ? passedSubmissions / totalSubmissions
        : 0,
      by_stage: [...stageMap.values()],
      award_trend: [],
      submission_trend: (
        (submissionTrend?.results ?? []) as Array<Record<string, unknown>>
      ).map((row) => ({
        date: String(row.date),
        count: Number(row.count),
      })),
    },
    200,
    requestId,
    request.method,
  )
}

type SupportTicketRow = Readonly<{
  id: number
  user_id: string
  account_email: string
  contact_email: string
  category: string
  description: string
  related_order_id: string | null
  image_count: number
  status: string
  created_at: number
}>

async function supportTickets(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const url = new URL(request.url)
  const page = integerParam(url, 'page', 1, 1, 100_000)
  const pageSize = integerParam(url, 'page_size', 20, 1, 100)
  const status = url.searchParams.get('status')
  if (status && !['open', 'resolved', 'closed'].includes(status)) {
    throw new HttpError(422, '未知工单状态')
  }
  const where = status ? 'WHERE t.status = ?' : ''
  const bindings = status ? [status] : []
  const rows = await env.DB
    .prepare(
      `SELECT t.id, t.user_id, u.email AS account_email, t.contact_email,
              t.category, t.description, t.related_order_id, t.image_count,
              t.status, t.created_at
       FROM support_tickets t
       JOIN users u ON u.id = t.user_id
       ${where}
       ORDER BY t.created_at DESC
       LIMIT ? OFFSET ?`,
    )
    .bind(...bindings, pageSize, (page - 1) * pageSize)
    .all<SupportTicketRow>()
  const total = await env.DB
    .prepare(`SELECT COUNT(*) AS count FROM support_tickets t ${where}`)
    .bind(...bindings)
    .first<{ count: number }>()
  return jsonResponse(
    {
      items: rows.results.map((row) => ({
        ...row,
        created_at: iso(row.created_at),
      })),
      total: Number(total?.count ?? 0),
      page,
      page_size: pageSize,
    },
    200,
    requestId,
    request.method,
  )
}

async function updateSupportTicket(
  request: Request,
  env: Env,
  requestId: string,
  ticketId: number,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const body = await readJsonObject(request)
  const status = body.status
  if (
    typeof status !== 'string' ||
    !['open', 'resolved', 'closed'].includes(status)
  ) {
    throw new HttpError(422, '未知工单状态')
  }
  const timestamp = Date.now()
  const result = await env.DB
    .prepare(
      `UPDATE support_tickets SET status = ? WHERE id = ? RETURNING user_id`,
    )
    .bind(status, ticketId)
    .first<{ user_id: string }>()
  if (!result) throw new HttpError(404, '工单不存在')
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    targetUserId: result.user_id,
    action: 'support.status_updated',
    detail: { ticket_id: ticketId, status },
    createdAt: timestamp,
  }).run()
  return jsonResponse(
    { ticket_id: ticketId, status },
    200,
    requestId,
    request.method,
  )
}

export async function handleAdminRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (!path.startsWith('/api/v1/admin/')) return null
  const route = `${request.method} ${path}`
  if (route === 'GET /api/v1/admin/overview') {
    return overview(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/users') {
    return listUsers(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/academy-stats') {
    return academyStats(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/support-tickets') {
    return supportTickets(request, env, requestId)
  }
  const userMatch = /^\/api\/v1\/admin\/users\/([^/]+)$/u.exec(path)
  if (userMatch && request.method === 'GET') {
    return getUser(request, env, requestId, userMatch[1] ?? '')
  }
  const banMatch =
    /^\/api\/v1\/admin\/users\/([^/]+)\/(ban|unban)$/u.exec(path)
  if (banMatch && request.method === 'POST') {
    return setUserBan(
      request,
      env,
      requestId,
      banMatch[1] ?? '',
      banMatch[2] === 'ban',
    )
  }
  const revokeMatch =
    /^\/api\/v1\/admin\/users\/([^/]+)\/revoke-sessions$/u.exec(path)
  if (revokeMatch && request.method === 'POST') {
    return revokeSessions(
      request,
      env,
      requestId,
      revokeMatch[1] ?? '',
    )
  }
  const ticketMatch =
    /^\/api\/v1\/admin\/support-tickets\/(\d+)$/u.exec(path)
  if (ticketMatch && request.method === 'PATCH') {
    return updateSupportTicket(
      request,
      env,
      requestId,
      Number(ticketMatch[1]),
    )
  }
  return null
}
