import { adminActionStatement, requireAdmin } from './admin'
import { sha256Hex } from './crypto'
import { HttpError, jsonResponse, readJsonObject } from './http'

type LegacyUser = Readonly<{
  legacy_user_id: string
  email: string
  google_sub?: string | null
  display_name?: string | null
  avatar_url?: string | null
  language_pref?: 'zh' | 'en' | null
  avatar_id?: number | null
  indicator_bollinger?: boolean
  indicator_chan?: boolean
  indicator_day_trade?: boolean
  email_verified_at?: number | null
  created_at?: number | null
  watchlist?: Array<Readonly<{ symbol: string; market: string }>>
  alert_rules?: Array<Readonly<{
    market: string
    symbol?: string | null
    indicator: string
    operator: string
    threshold: number
    timeframe?: string | null
    enabled?: boolean
  }>>
  notification_preferences?: Readonly<{
    trade_alert_enabled?: boolean
    price_alert_enabled?: boolean
    weekly_report_enabled?: boolean
    dott_digest_enabled?: boolean
    dott_transition_enabled?: boolean
  }>
  academy_progress?: Array<Readonly<{
    article_slug: string
    stage: string
    completed_at?: number | null
  }>>
  academy_exam_results?: Array<Readonly<{
    stage: string
    score: number
    total: number
    passed: boolean
    created_at?: number | null
  }>>
}>

const MARKETS = new Set(['cn', 'us', 'hk', 'crypto'])
const OPERATORS = new Set(['gt', 'gte', 'lt', 'lte'])

function normalizedUsers(value: unknown): LegacyUser[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 25) {
    throw new HttpError(400, 'users 必须包含 1—25 条记录')
  }
  const seenLegacy = new Set<string>()
  const seenEmail = new Set<string>()
  return value.map((raw, index) => {
    if (!raw || typeof raw !== 'object') throw new HttpError(400, `users[${index}] 格式无效`)
    const row = raw as Record<string, unknown>
    const legacyId = String(row.legacy_user_id ?? '').trim()
    const email = String(row.email ?? '').trim().toLowerCase()
    if (!legacyId || !email.includes('@')) throw new HttpError(400, `users[${index}] 标识或邮箱无效`)
    if (seenLegacy.has(legacyId) || seenEmail.has(email)) {
      throw new HttpError(400, `users[${index}] 在批次内重复`)
    }
    seenLegacy.add(legacyId)
    seenEmail.add(email)
    return { ...row, legacy_user_id: legacyId, email } as LegacyUser
  })
}

function text(value: unknown, limit: number): string | null {
  return typeof value === 'string' && value.trim() ? value.trim().slice(0, limit) : null
}

async function importUser(env: Env, row: LegacyUser, now: number): Promise<Readonly<{
  user: number
  watchlist: number
  alert_rules: number
  academy_progress: number
  academy_exams: number
}>> {
  const existing = await env.DB.prepare(
    'SELECT id, legacy_user_id FROM users WHERE email = ? COLLATE NOCASE',
  ).bind(row.email).first<{ id: string; legacy_user_id: string | null }>()
  if (existing?.legacy_user_id && existing.legacy_user_id !== row.legacy_user_id) {
    throw new Error(`邮箱 ${row.email} 已映射到另一旧用户`)
  }
  const userId = existing?.id ?? crypto.randomUUID()
  const createdAt = Number.isFinite(row.created_at) ? Number(row.created_at) : now
  if (existing) {
    await env.DB.prepare(
      `UPDATE users SET legacy_user_id = ?,
       display_name = COALESCE(display_name, ?), avatar_url = COALESCE(avatar_url, ?),
       google_sub = COALESCE(google_sub, ?), language_pref = COALESCE(language_pref, ?),
       avatar_id = COALESCE(avatar_id, ?),
       email_verified_at = COALESCE(email_verified_at, ?), updated_at = ?
       WHERE id = ?`,
    ).bind(
      row.legacy_user_id, text(row.display_name, 80), text(row.avatar_url, 500),
      text(row.google_sub, 200), row.language_pref ?? null, row.avatar_id ?? null,
      row.email_verified_at ?? null, now, userId,
    ).run()
  } else {
    await env.DB.prepare(
      `INSERT INTO users
        (id, email, password_hash, google_sub, display_name, avatar_url, role,
         age_confirmed, email_verified_at, created_at, updated_at,
         legacy_user_id, language_pref, avatar_id, indicator_bollinger,
         indicator_chan, indicator_day_trade)
       VALUES (?, ?, ?, ?, ?, ?, 'user', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      userId, row.email, row.google_sub ? null : '$legacy-disabled$',
      text(row.google_sub, 200), text(row.display_name, 80), text(row.avatar_url, 500),
      row.email_verified_at ?? null, createdAt, now, row.legacy_user_id,
      row.language_pref ?? null, row.avatar_id ?? null,
      row.indicator_bollinger === false ? 0 : 1,
      row.indicator_chan === false ? 0 : 1,
      row.indicator_day_trade === true ? 1 : 0,
    ).run()
  }
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO legacy_user_mappings
        (legacy_user_id, user_id, email, source_updated_at, migrated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(legacy_user_id) DO UPDATE SET
         user_id = excluded.user_id, email = excluded.email,
         source_updated_at = excluded.source_updated_at,
         migrated_at = excluded.migrated_at`,
    ).bind(row.legacy_user_id, userId, row.email, row.created_at ?? null, now),
    env.DB.prepare(
      `INSERT OR IGNORE INTO notification_configs
        (user_id, trade_alert_enabled, price_alert_enabled,
         weekly_report_enabled, dott_digest_enabled, dott_transition_enabled,
         created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      userId,
      row.notification_preferences?.trade_alert_enabled === false ? 0 : 1,
      row.notification_preferences?.price_alert_enabled === false ? 0 : 1,
      row.notification_preferences?.weekly_report_enabled === true ? 1 : 0,
      row.notification_preferences?.dott_digest_enabled === true ? 1 : 0,
      row.notification_preferences?.dott_transition_enabled === true ? 1 : 0,
      now, now,
    ),
  ])

  let watchlist = 0
  for (const [sortOrder, item] of (row.watchlist ?? []).slice(0, 100).entries()) {
    const market = String(item.market ?? '')
    const symbol = String(item.symbol ?? '').trim().toUpperCase()
    if (!MARKETS.has(market) || !symbol) continue
    const result = await env.DB.prepare(
      `INSERT OR IGNORE INTO watchlist_items
        (user_id, symbol, market, sort_order, added_at) VALUES (?, ?, ?, ?, ?)`,
    ).bind(userId, symbol, market, sortOrder, now).run()
    watchlist += result.meta.changes
  }

  const existingRules = await env.DB.prepare(
    'SELECT market, symbol, indicator, operator, threshold FROM alert_rules WHERE user_id = ?',
  ).bind(userId).all<Record<string, unknown>>()
  const keys = new Set(existingRules.results.map((item) =>
    [item.market, item.symbol ?? '', item.indicator, item.operator, item.threshold].join('|'),
  ))
  let alertRules = 0
  for (const rule of (row.alert_rules ?? []).slice(0, 50)) {
    const market = String(rule.market ?? '')
    const operator = String(rule.operator ?? '')
    const indicator = String(rule.indicator ?? '').trim()
    const symbol = text(rule.symbol, 40)?.toUpperCase() ?? null
    if (!MARKETS.has(market) || !OPERATORS.has(operator) || !indicator || !Number.isFinite(rule.threshold)) continue
    const key = [market, symbol ?? '', indicator, operator, String(rule.threshold)].join('|')
    if (keys.has(key)) continue
    const result = await env.DB.prepare(
      `INSERT INTO alert_rules
        (user_id, market, symbol, indicator, operator, threshold, timeframe,
         enabled, cooldown_sec, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, 300, ?, ?)`,
    ).bind(
      userId, market, symbol, indicator, operator, String(rule.threshold),
      text(rule.timeframe, 20), rule.enabled === false ? 0 : 1, now, now,
    ).run()
    alertRules += result.meta.changes
    keys.add(key)
  }
  let academyProgress = 0
  for (const item of (row.academy_progress ?? []).slice(0, 500)) {
    const slug = text(item.article_slug, 200)
    const stage = text(item.stage, 80)
    if (!slug || !stage) continue
    const result = await env.DB.prepare(
      `INSERT OR IGNORE INTO academy_progress
        (user_id, article_slug, stage, completed_at) VALUES (?, ?, ?, ?)`,
    ).bind(userId, slug, stage, item.completed_at ?? now).run()
    academyProgress += result.meta.changes
  }
  let academyExams = 0
  for (const item of (row.academy_exam_results ?? []).slice(0, 100)) {
    const stage = text(item.stage, 80)
    if (!stage || !Number.isFinite(item.score) || !Number.isFinite(item.total) || item.total <= 0) continue
    const result = await env.DB.prepare(
      `INSERT INTO academy_exam_results
        (id, user_id, stage, score, total, passed, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ).bind(
      crypto.randomUUID(), userId, stage, item.score, item.total,
      item.passed ? 1 : 0, item.created_at ?? now,
    ).run()
    academyExams += result.meta.changes
  }
  return {
    user: existing ? 0 : 1,
    watchlist,
    alert_rules: alertRules,
    academy_progress: academyProgress,
    academy_exams: academyExams,
  }
}

export async function handleAdminMigrationRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path !== '/api/v1/admin/migration/import-users') return null
  if (request.method !== 'POST') {
    return jsonResponse({ detail: 'Method not allowed' }, 405, requestId, request.method)
  }
  const admin = await requireAdmin(request, env)
  const body = await readJsonObject(request)
  const users = normalizedUsers(body.users)
  const dryRun = body.dry_run !== false
  const sourceRevision = text(body.source_revision, 120)
  const conflicts = []
  for (const user of users) {
    const existing = await env.DB.prepare(
      'SELECT id, legacy_user_id FROM users WHERE email = ? COLLATE NOCASE',
    ).bind(user.email).first<{ id: string; legacy_user_id: string | null }>()
    if (existing?.legacy_user_id && existing.legacy_user_id !== user.legacy_user_id) {
      conflicts.push({ email: user.email, reason: 'email_mapped_to_other_legacy_id' })
    }
  }
  if (dryRun || conflicts.length > 0) {
    return jsonResponse({
      dry_run: true,
      accepted: users.length,
      conflicts,
      password_users_require_reset: users.filter((user) => !user.google_sub).length,
    }, 200, requestId, request.method)
  }

  const runId = crypto.randomUUID()
  const now = Date.now()
  const checksum = await sha256Hex(JSON.stringify(users))
  await env.DB.prepare(
    `INSERT INTO legacy_migration_runs
      (id, status, source_revision, source_counts_json, imported_counts_json,
       checksum_json, operator_id, dry_run, started_at, created_at, updated_at)
     VALUES (?, 'running', ?, ?, '{}', ?, ?, 0, ?, ?, ?)`,
  ).bind(
    runId, sourceRevision, JSON.stringify({ users: users.length }),
    JSON.stringify({ users_sha256: checksum }), admin.user.id, now, now, now,
  ).run()
  const imported = {
    users: 0, watchlist: 0, alert_rules: 0, academy_progress: 0, academy_exams: 0,
  }
  try {
    for (const user of users) {
      const counts = await importUser(env, user, now)
      imported.users += counts.user
      imported.watchlist += counts.watchlist
      imported.alert_rules += counts.alert_rules
      imported.academy_progress += counts.academy_progress
      imported.academy_exams += counts.academy_exams
    }
    await env.DB.batch([
      env.DB.prepare(
        `UPDATE legacy_migration_runs SET status = 'verified', imported_counts_json = ?,
         completed_at = ?, updated_at = ? WHERE id = ?`,
      ).bind(JSON.stringify(imported), Date.now(), Date.now(), runId),
      adminActionStatement(env.DB, {
        operatorId: admin.user.id,
        action: 'migration.users_imported',
        detail: { run_id: runId, ...imported },
        createdAt: Date.now(),
      }),
    ])
  } catch (cause) {
    await env.DB.prepare(
      `UPDATE legacy_migration_runs SET status = 'failed', error = ?,
       completed_at = ?, updated_at = ? WHERE id = ?`,
    ).bind(cause instanceof Error ? cause.message.slice(0, 500) : String(cause), Date.now(), Date.now(), runId).run()
    throw cause
  }
  return jsonResponse({
    dry_run: false,
    run_id: runId,
    status: 'verified',
    imported,
    password_users_require_reset: users.filter((user) => !user.google_sub).length,
  }, 200, requestId, request.method)
}
