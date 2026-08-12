import { invokeAi, parseAiJson } from './ai-provider'
import { adminActionStatement, requireAdmin } from './admin'
import { HttpError, jsonResponse, readJsonObject } from './http'
import { deliverUserNotification } from './notifications'

type ReportRow = Readonly<{
  id: number
  title: string
  content: string
  status: string
  period_start: string | null
  period_end: string | null
  provider: string | null
  model: string | null
  approved_at: number | null
  sent_at: number | null
  created_at: number
  updated_at: number
}>

type MaterialRow = Readonly<{
  id: number
  filename: string
  content_type: string
  size: number
  char_count: number
  extracted_text: string
  period_start: string | null
  period_end: string | null
  created_at: number
}>

function reportJson(row: ReportRow) {
  return {
    ...row,
    created_at: new Date(row.created_at).toISOString(),
    updated_at: new Date(row.updated_at).toISOString(),
    approved_at: row.approved_at ? new Date(row.approved_at).toISOString() : null,
    sent_at: row.sent_at ? new Date(row.sent_at).toISOString() : null,
  }
}

function materialJson(row: MaterialRow) {
  const { extracted_text: _extracted, ...publicRow } = row
  return { ...publicRow, created_at: new Date(row.created_at).toISOString() }
}

function mondayPeriod(now = new Date()): { start: string; end: string } {
  const day = now.getUTCDay() || 7
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
  start.setUTCDate(start.getUTCDate() - day + 1)
  const end = new Date(start)
  end.setUTCDate(end.getUTCDate() + 6)
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) }
}

async function listReports(request: Request, env: Env, requestId: string) {
  await requireAdmin(request, env)
  const url = new URL(request.url)
  const status = url.searchParams.get('status')
  const limit = Math.min(Math.max(Number(url.searchParams.get('limit') ?? 50), 1), 100)
  const offset = Math.max(Number(url.searchParams.get('offset') ?? 0), 0)
  const rows = await env.DB.prepare(
    `SELECT * FROM market_reports WHERE (? IS NULL OR status = ?)
     ORDER BY id DESC LIMIT ? OFFSET ?`,
  ).bind(status, status, limit, offset).all<ReportRow>()
  const total = await env.DB.prepare(
    `SELECT COUNT(*) AS count FROM market_reports WHERE (? IS NULL OR status = ?)`,
  ).bind(status, status).first<{ count: number }>()
  return jsonResponse(
    { items: rows.results.map(reportJson), total: Number(total?.count ?? 0) },
    200,
    requestId,
    request.method,
  )
}

async function reportById(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  await requireAdmin(request, env)
  const row = await env.DB.prepare('SELECT * FROM market_reports WHERE id = ?')
    .bind(id).first<ReportRow>()
  if (!row) throw new HttpError(404, '报告不存在')
  return jsonResponse(reportJson(row), 200, requestId, request.method)
}

async function updateReport(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const admin = await requireAdmin(request, env)
  const body = await readJsonObject(request)
  const row = await env.DB.prepare('SELECT * FROM market_reports WHERE id = ?')
    .bind(id).first<ReportRow>()
  if (!row) throw new HttpError(404, '报告不存在')
  if (row.status === 'sent') throw new HttpError(409, '已发送报告不可编辑')
  const title = typeof body.title === 'string' ? body.title.trim().slice(0, 200) : row.title
  const content = typeof body.content === 'string' ? body.content.trim().slice(0, 100_000) : row.content
  if (!title || !content) throw new HttpError(400, '标题和正文不能为空')
  const now = Date.now()
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE market_reports SET title = ?, content = ?, status = 'draft',
       approved_at = NULL, approved_by = NULL, updated_at = ? WHERE id = ?`,
    ).bind(title, content, now, id),
    adminActionStatement(env.DB, {
      operatorId: admin.user.id,
      action: 'report.updated',
      detail: { report_id: id },
      createdAt: now,
    }),
  ])
  return reportById(request, env, requestId, id)
}

async function approve(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const admin = await requireAdmin(request, env)
  const now = Date.now()
  const result = await env.DB.prepare(
    `UPDATE market_reports SET status = 'approved', approved_by = ?,
     approved_at = ?, updated_at = ? WHERE id = ? AND status = 'draft'`,
  ).bind(admin.user.id, now, now, id).run()
  if (result.meta.changes !== 1) throw new HttpError(409, '仅草稿可以批准')
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'report.approved',
    detail: { report_id: id },
    createdAt: now,
  }).run()
  return reportById(request, env, requestId, id)
}

async function generate(request: Request, env: Env, requestId: string) {
  const admin = await requireAdmin(request, env)
  const period = mondayPeriod()
  const [quotes, materials] = await Promise.all([
    env.DB.prepare(
      `SELECT symbol, name, category, last_point AS price, change_pct, source, quoted_at
       FROM market_overview_quotes ORDER BY ABS(change_pct) DESC LIMIT 40`,
    ).all<Record<string, unknown>>(),
    env.DB.prepare(
      `SELECT extracted_text FROM report_materials
       WHERE period_start = ? AND period_end = ? ORDER BY id DESC LIMIT 10`,
    ).bind(period.start, period.end).all<{ extracted_text: string }>(),
  ])
  let title = `Midas Trading 市场周报 · ${period.start}—${period.end}`
  let content = [
    '# 本周市场概览',
    '',
    ...quotes.results.slice(0, 12).map((quote) =>
      `- ${String(quote.name ?? quote.symbol)}：${Number(quote.change_pct ?? 0).toFixed(2)}%`,
    ),
    '',
    '# 下周观察',
    '',
    '- 关注主要指数、流动性和成交量的同步变化。',
    '- 关注高波动品种能否获得后续量能确认。',
  ].join('\n')
  let provider = 'technical-rules'
  let model = 'weekly-template-v1'
  try {
    const ai = await invokeAi(env, {
      system: '你是专业市场周报编辑。只使用提供的数据，输出 JSON，字段为 title 和 content。content 使用 Markdown，结构清晰，不包含投资建议或外链。',
      prompt: JSON.stringify({
        period,
        quotes: quotes.results,
        materials: materials.results.map((item) => item.extracted_text).filter(Boolean),
      }),
      maxTokens: 1_600,
      temperature: 0.25,
    })
    const parsed = parseAiJson(ai.content)
    if (typeof parsed.title === 'string' && typeof parsed.content === 'string') {
      title = parsed.title.slice(0, 200)
      content = parsed.content.slice(0, 100_000)
      provider = ai.provider
      model = ai.model
    }
  } catch {
    // The deterministic report remains available when both AI providers fail.
  }
  const now = Date.now()
  const result = await env.DB.prepare(
    `INSERT INTO market_reports
      (title, content, status, period_start, period_end, provider, model,
       created_at, updated_at)
     VALUES (?, ?, 'draft', ?, ?, ?, ?, ?, ?)`,
  ).bind(title, content, period.start, period.end, provider, model, now, now).run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'report.generated',
    detail: { report_id: result.meta.last_row_id, provider, model },
    createdAt: now,
  }).run()
  return reportById(request, env, requestId, Number(result.meta.last_row_id))
}

async function resendReportEmail(
  env: Env,
  recipient: string,
  report: ReportRow,
): Promise<boolean> {
  if (!env.RESEND_API_KEY) return false
  const response = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${env.RESEND_API_KEY}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      from: env.EMAIL_FROM,
      to: [recipient],
      subject: report.title,
      text: report.content,
    }),
    signal: AbortSignal.timeout(15_000),
  })
  return response.ok
}

async function sendReport(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const admin = await requireAdmin(request, env)
  const report = await env.DB.prepare('SELECT * FROM market_reports WHERE id = ?')
    .bind(id).first<ReportRow>()
  if (!report) throw new HttpError(404, '报告不存在')
  if (report.status !== 'approved') throw new HttpError(409, '报告批准后才能发送')
  const recipients = await env.DB.prepare(
    `SELECT u.id, u.email FROM users u
     JOIN notification_configs c ON c.user_id = u.id
     WHERE u.banned_at IS NULL AND c.weekly_report_enabled = 1`,
  ).all<{ id: string; email: string }>()
  let emailSent = 0
  let emailFailed = 0
  let notifySent = 0
  let notifyFailed = 0
  for (const recipient of recipients.results) {
    if (await resendReportEmail(env, recipient.email, report)) emailSent += 1
    else emailFailed += 1
    try {
      await deliverUserNotification(env, {
        userId: recipient.id,
        category: 'weekly_report',
        title: report.title,
        body: report.content.slice(0, 800),
        dedupeKey: `report:${id}:user:${recipient.id}`,
      })
      notifySent += 1
    } catch {
      notifyFailed += 1
    }
  }
  const now = Date.now()
  await env.DB.batch([
    env.DB.prepare(
      `UPDATE market_reports SET status = 'sent', sent_at = ?, updated_at = ? WHERE id = ?`,
    ).bind(now, now, id),
    adminActionStatement(env.DB, {
      operatorId: admin.user.id,
      action: 'report.sent',
      detail: { report_id: id, recipients: recipients.results.length },
      createdAt: now,
    }),
  ])
  return jsonResponse({
    report_id: id,
    status: 'sent',
    recipients: recipients.results.length,
    email_sent: emailSent,
    email_failed: emailFailed,
    notify_sent: notifySent,
    notify_failed: notifyFailed,
  }, 200, requestId, request.method)
}

async function listMaterials(request: Request, env: Env, requestId: string) {
  await requireAdmin(request, env)
  const period = mondayPeriod()
  const rows = await env.DB.prepare(
    `SELECT * FROM report_materials
     WHERE period_start = ? AND period_end = ? ORDER BY id DESC`,
  ).bind(period.start, period.end).all<MaterialRow>()
  return jsonResponse(
    { items: rows.results.map(materialJson), period_start: period.start, period_end: period.end },
    200,
    requestId,
    request.method,
  )
}

async function uploadMaterial(request: Request, env: Env, requestId: string) {
  const admin = await requireAdmin(request, env)
  const form = await request.formData()
  const file = form.get('file')
  if (!(file instanceof File)) throw new HttpError(400, 'file 必填')
  if (file.size <= 0 || file.size > 8 * 1024 * 1024) throw new HttpError(413, '素材必须在 8MB 以内')
  const extension = file.name.split('.').at(-1)?.toLowerCase()
  const contentType = extension === 'pdf' ? 'pdf' : extension === 'txt' ? 'txt' : 'md'
  if (!['md', 'markdown', 'txt', 'pdf'].includes(extension ?? '')) {
    throw new HttpError(415, '仅支持 md、txt、pdf')
  }
  const extracted = contentType === 'pdf' ? '' : (await file.text()).slice(0, 200_000)
  const period = mondayPeriod()
  const now = Date.now()
  const result = await env.DB.prepare(
    `INSERT INTO report_materials
      (filename, content_type, size, char_count, extracted_text,
       period_start, period_end, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    file.name.slice(0, 200), contentType, file.size, extracted.length,
    extracted, period.start, period.end, now,
  ).run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'report_material.uploaded',
    detail: { material_id: result.meta.last_row_id, filename: file.name },
    createdAt: now,
  }).run()
  const row = await env.DB.prepare('SELECT * FROM report_materials WHERE id = ?')
    .bind(result.meta.last_row_id).first<MaterialRow>()
  return jsonResponse(materialJson(row!), 201, requestId, request.method)
}

async function deleteMaterial(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
) {
  const admin = await requireAdmin(request, env)
  const result = await env.DB.prepare('DELETE FROM report_materials WHERE id = ?')
    .bind(id).run()
  if (result.meta.changes !== 1) throw new HttpError(404, '素材不存在')
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'report_material.deleted',
    detail: { material_id: id },
    createdAt: Date.now(),
  }).run()
  return jsonResponse({}, 204, requestId, request.method)
}

async function migrationStatus(request: Request, env: Env, requestId: string) {
  await requireAdmin(request, env)
  const results = await env.DB.batch([
    env.DB.prepare('SELECT COUNT(*) AS count FROM users'),
    env.DB.prepare('SELECT COUNT(*) AS count FROM legacy_user_mappings'),
    env.DB.prepare('SELECT COUNT(*) AS count FROM virtual_accounts'),
    env.DB.prepare('SELECT COUNT(*) AS count FROM alert_rules'),
    env.DB.prepare('SELECT COUNT(*) AS count FROM backtest_runs'),
    env.DB.prepare('SELECT * FROM legacy_migration_runs ORDER BY created_at DESC LIMIT 10'),
  ])
  const count = (index: number) => Number(
    (results[index]?.results[0] as { count?: unknown } | undefined)?.count ?? 0,
  )
  return jsonResponse({
    cloudflare_counts: {
      users: count(0),
      mapped_legacy_users: count(1),
      virtual_accounts: count(2),
      alert_rules: count(3),
      backtest_runs: count(4),
    },
    recent_runs: results[5]?.results ?? [],
    readiness: {
      legacy_api_fallback_removed: true,
      oauth_domain_ready: false,
      source_data_verified: true,
      rollback_snapshot_ready: false,
    },
  }, 200, requestId, request.method)
}

export async function handleAdminReportsRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (path === '/api/v1/admin/reports') {
    if (request.method === 'GET') return listReports(request, env, requestId)
  }
  if (path === '/api/v1/admin/reports/generate' && request.method === 'POST') {
    return generate(request, env, requestId)
  }
  const reportAction = path.match(/^\/api\/v1\/admin\/reports\/(\d+)\/(approve|send)$/u)
  if (reportAction?.[1] && request.method === 'POST') {
    return reportAction[2] === 'approve'
      ? approve(request, env, requestId, Number(reportAction[1]))
      : sendReport(request, env, requestId, Number(reportAction[1]))
  }
  const reportMatch = path.match(/^\/api\/v1\/admin\/reports\/(\d+)$/u)
  if (reportMatch?.[1]) {
    if (request.method === 'GET') return reportById(request, env, requestId, Number(reportMatch[1]))
    if (request.method === 'PUT') return updateReport(request, env, requestId, Number(reportMatch[1]))
  }
  if (path === '/api/v1/admin/report-materials') {
    if (request.method === 'GET') return listMaterials(request, env, requestId)
    if (request.method === 'POST') return uploadMaterial(request, env, requestId)
  }
  const materialMatch = path.match(/^\/api\/v1\/admin\/report-materials\/(\d+)$/u)
  if (materialMatch?.[1] && request.method === 'DELETE') {
    return deleteMaterial(request, env, requestId, Number(materialMatch[1]))
  }
  if (path === '/api/v1/admin/migration/status' && request.method === 'GET') {
    return migrationStatus(request, env, requestId)
  }
  return null
}
