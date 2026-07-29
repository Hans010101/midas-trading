import { Buffer } from 'node:buffer'

import {
  adminActionStatement,
  requireAdmin,
} from './admin'
import { invokeAi, parseAiJson } from './ai-provider'
import {
  binanceSquareEnabled,
  publishToBinanceSquare,
} from './binance-square'
import { HttpError, jsonResponse, readJsonObject } from './http'

const MAX_PDF_BYTES = 5 * 1024 * 1024
const MAX_MD_BYTES = 512 * 1024
const ASSET_CHUNK_BYTES = 256 * 1024

function iso(timestamp: number | null): string | null {
  return timestamp === null ? null : new Date(timestamp).toISOString()
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/gu, (character) => {
    const replacements: Record<string, string> = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }
    return replacements[character] ?? character
  })
}

function cstDate(timestamp = Date.now()): Date {
  return new Date(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date(timestamp)) + 'T00:00:00Z',
  )
}

function isoWeek(timestamp = Date.now()): {
  year: number
  week: number
  start: string
  end: string
} {
  const date = cstDate(timestamp)
  const day = date.getUTCDay() || 7
  date.setUTCDate(date.getUTCDate() + 4 - day)
  const year = date.getUTCFullYear()
  const yearStart = new Date(Date.UTC(year, 0, 1))
  const week = Math.ceil(
    ((date.getTime() - yearStart.getTime()) / 86_400_000 + 1) / 7,
  )
  const start = cstDate(timestamp)
  const startDay = start.getUTCDay() || 7
  start.setUTCDate(start.getUTCDate() - startDay + 1)
  const end = new Date(start)
  end.setUTCDate(start.getUTCDate() + 6)
  return {
    year,
    week,
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  }
}

function nextSendLabel(timestamp = Date.now()): string {
  const current = new Date(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Shanghai',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).format(new Date(timestamp)) + 'T00:00:00+08:00',
  )
  const day = current.getDay()
  let days = (7 - day) % 7
  const cstHour = Number(
    new Intl.DateTimeFormat('en-US', {
      timeZone: 'Asia/Shanghai',
      hour: '2-digit',
      hourCycle: 'h23',
    }).format(new Date(timestamp)),
  )
  if (days === 0 && cstHour >= 21) days = 7
  current.setDate(current.getDate() + days)
  return `${current.getMonth() + 1}月${current.getDate()}日21:00`
}

function stringList(lines: readonly string[]): string[] {
  return lines
    .map((line) => line.replace(/^[-*+\d.)、\s]+/u, '').trim())
    .filter(Boolean)
}

function extractMarkdown(md: string): {
  lead: string
  conclusions: string[]
  strong: string[]
  weak: string[]
  next_week: string[]
} {
  const sections = new Map<string, string[]>()
  let current = 'intro'
  for (const raw of md.split(/\r?\n/u)) {
    const line = raw.trim()
    const heading = /^#{1,6}\s*(.+)$/u.exec(line)?.[1]?.trim()
    if (heading) {
      current = heading
      if (!sections.has(current)) sections.set(current, [])
    } else if (line) {
      const values = sections.get(current) ?? []
      values.push(line)
      sections.set(current, values)
    }
  }
  const find = (patterns: readonly RegExp[]) => {
    for (const [name, lines] of sections) {
      if (patterns.some((pattern) => pattern.test(name))) return stringList(lines)
    }
    return []
  }
  const intro = find([/导语/u, /摘要/u, /概览/u])
  return {
    lead: intro[0] ?? stringList(sections.get('intro') ?? [])[0] ?? '',
    conclusions: find([/结论/u, /核心/u]),
    strong: find([/走强/u, /强势/u]),
    weak: find([/走弱/u, /弱势/u]),
    next_week: find([/下周/u, /关注/u]),
  }
}

function weeklyEmailHtml(
  title: string,
  extracted: ReturnType<typeof extractMarkdown>,
): string {
  const list = (items: readonly string[]) =>
    items.length > 0
      ? `<ul>${items.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`
      : '<p style="color:#777">本期暂无</p>'
  return `
    <div style="font-family:Arial,'Noto Sans SC',sans-serif;max-width:680px;margin:0 auto;color:#171717">
      <h1 style="color:#C8102E">${escapeHtml(title)}</h1>
      ${extracted.lead ? `<p>${escapeHtml(extracted.lead)}</p>` : ''}
      <h2>核心结论</h2>${list(extracted.conclusions)}
      <h2>走强</h2>${list(extracted.strong)}
      <h2>走弱</h2>${list(extracted.weak)}
      <h2>下周关注</h2>${list(extracted.next_week)}
      <p style="color:#666;font-size:12px">完整精排版见邮件附件 · Midas Trading</p>
    </div>
  `
}

type WeeklyRow = Readonly<{
  id: number
  year: number
  week: number
  period_start: string
  period_end: string
  title: string
  status: string
  pdf_filename: string
  md_content: string
  extracted_json: string
  email_html: string
  uploaded_at: number
  sent_at: number | null
}>

function weeklyItem(row: WeeklyRow) {
  return {
    id: row.id,
    year: row.year,
    week: row.week,
    period_start: row.period_start,
    period_end: row.period_end,
    title: row.title,
    status: row.status,
    uploaded_at: iso(row.uploaded_at),
    sent_at: iso(row.sent_at),
  }
}

async function listWeekly(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const rows = await env.DB
    .prepare(
      `SELECT id, year, week, period_start, period_end, title, status,
              pdf_filename, md_content, extracted_json, email_html,
              uploaded_at, sent_at
       FROM weekly_dispatches
       ORDER BY year DESC, week DESC
       LIMIT 100`,
    )
    .all<WeeklyRow>()
  return jsonResponse(
    {
      items: rows.results.map(weeklyItem),
      next_send_label: nextSendLabel(),
    },
    200,
    requestId,
    request.method,
  )
}

async function getWeeklyRow(env: Env, id: number): Promise<WeeklyRow> {
  const row = await env.DB
    .prepare(
      `SELECT id, year, week, period_start, period_end, title, status,
              pdf_filename, md_content, extracted_json, email_html,
              uploaded_at, sent_at
       FROM weekly_dispatches WHERE id = ?`,
    )
    .bind(id)
    .first<WeeklyRow>()
  if (!row) throw new HttpError(404, '周报不存在')
  return row
}

async function getWeekly(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
): Promise<Response> {
  await requireAdmin(request, env)
  const row = await getWeeklyRow(env, id)
  return jsonResponse(
    {
      ...weeklyItem(row),
      pdf_filename: row.pdf_filename,
      extracted: JSON.parse(row.extracted_json) as Record<string, unknown>,
      email_html: row.email_html,
      next_send_label: nextSendLabel(),
    },
    200,
    requestId,
    request.method,
  )
}

function requiredFile(form: FormData, name: string): File {
  const value = form.get(name)
  if (!(value instanceof File) || !value.name) {
    throw new HttpError(422, `请上传 ${name} 文件`)
  }
  return value
}

async function uploadWeekly(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const contentLength = Number(request.headers.get('content-length') ?? '0')
  if (contentLength > MAX_PDF_BYTES + MAX_MD_BYTES + 1_000_000) {
    throw new HttpError(413, '上传内容过大')
  }
  const form = await request.formData()
  const pdf = requiredFile(form, 'pdf')
  const mdFile = requiredFile(form, 'md')
  if (pdf.size <= 0 || pdf.size > MAX_PDF_BYTES) {
    throw new HttpError(422, 'PDF 必须在 5 MB 以内')
  }
  if (mdFile.size <= 0 || mdFile.size > MAX_MD_BYTES) {
    throw new HttpError(422, 'md 必须在 512 KB 以内')
  }
  if (pdf.type && pdf.type !== 'application/pdf') {
    throw new HttpError(422, 'PDF 文件类型无效')
  }
  const md = await mdFile.text()
  const extracted = extractMarkdown(md)
  const missing = Object.entries(extracted)
    .filter(([, value]) => typeof value === 'string' ? !value : value.length === 0)
    .map(([key]) => key)
  const period = isoWeek()
  const title = `Midas Trading 市场周报 · ${period.year} W${period.week}`
  const emailHtml = weeklyEmailHtml(title, extracted)
  const uploadedAt = Date.now()
  const row = await env.DB
    .prepare(
      `INSERT INTO weekly_dispatches
        (year, week, period_start, period_end, title, status, pdf_filename,
         md_content, extracted_json, email_html, uploaded_at)
       VALUES (?, ?, ?, ?, ?, 'uploaded', ?, ?, ?, ?, ?)
       ON CONFLICT(year, week) DO UPDATE SET
         period_start = excluded.period_start,
         period_end = excluded.period_end,
         title = excluded.title,
         status = 'uploaded',
         pdf_filename = excluded.pdf_filename,
         md_content = excluded.md_content,
         extracted_json = excluded.extracted_json,
         email_html = excluded.email_html,
         uploaded_at = excluded.uploaded_at,
         sent_at = NULL
       RETURNING id`,
    )
    .bind(
      period.year,
      period.week,
      period.start,
      period.end,
      title,
      pdf.name.slice(0, 180),
      md,
      JSON.stringify(extracted),
      emailHtml,
      uploadedAt,
    )
    .first<{ id: number }>()
  if (!row) throw new HttpError(500, '周报保存失败')
  await env.DB
    .prepare('DELETE FROM weekly_dispatch_assets WHERE dispatch_id = ?')
    .bind(row.id)
    .run()
  const bytes = new Uint8Array(await pdf.arrayBuffer())
  const statements: D1PreparedStatement[] = []
  for (let offset = 0, index = 0; offset < bytes.length; offset += ASSET_CHUNK_BYTES, index += 1) {
    statements.push(
      env.DB
        .prepare(
          `INSERT INTO weekly_dispatch_assets
            (dispatch_id, chunk_index, content) VALUES (?, ?, ?)`,
        )
        .bind(row.id, index, bytes.slice(offset, offset + ASSET_CHUNK_BYTES)),
    )
  }
  if (statements.length > 0) await env.DB.batch(statements)
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'weekly.uploaded',
    detail: { dispatch_id: row.id, year: period.year, week: period.week },
    createdAt: uploadedAt,
  }).run()
  return jsonResponse(
    {
      id: row.id,
      year: period.year,
      week: period.week,
      status: 'uploaded',
      extracted,
      missing,
      email_html: emailHtml,
      pdf_filename: pdf.name,
    },
    200,
    requestId,
    request.method,
  )
}

async function setWeeklyStatus(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
  status: 'scheduled' | 'uploaded',
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const row = await getWeeklyRow(env, id)
  if (row.status === 'sent') throw new HttpError(409, '已发送周报不能修改计划')
  await env.DB
    .prepare('UPDATE weekly_dispatches SET status = ? WHERE id = ?')
    .bind(status, id)
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: status === 'scheduled' ? 'weekly.scheduled' : 'weekly.unscheduled',
    detail: { dispatch_id: id },
    createdAt: Date.now(),
  }).run()
  return getWeekly(request, env, requestId, id)
}

async function weeklyPdf(env: Env, dispatchId: number): Promise<string> {
  const chunks = await env.DB
    .prepare(
      `SELECT content FROM weekly_dispatch_assets
       WHERE dispatch_id = ? ORDER BY chunk_index`,
    )
    .bind(dispatchId)
    .all<{ content: ArrayBuffer }>()
  const buffers = chunks.results.map((row) => Buffer.from(row.content))
  return Buffer.concat(buffers).toString('base64')
}

async function sendWeeklyEmail(
  env: Env,
  recipient: string,
  row: WeeklyRow,
  pdfBase64: string,
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
      subject: row.title,
      html: row.email_html,
      attachments: [{ filename: row.pdf_filename, content: pdfBase64 }],
    }),
  })
  return response.ok
}

async function deliverWeekly(
  env: Env,
  row: WeeklyRow,
): Promise<{
  recipients: number
  emailSent: number
  emailFailed: number
  notifySent: number
  notifyFailed: number
}> {
  const recipients = await env.DB
    .prepare(
      `SELECT u.id, u.email
       FROM users u
       JOIN notification_configs n ON n.user_id = u.id
       WHERE n.weekly_report_enabled = 1
         AND u.email_verified_at IS NOT NULL
         AND u.banned_at IS NULL`,
    )
    .all<{ id: string; email: string }>()
  const pdf = await weeklyPdf(env, row.id)
  let emailSent = 0
  let emailFailed = 0
  let notifySent = 0
  for (const recipient of recipients.results) {
    try {
      if (await sendWeeklyEmail(env, recipient.email, row, pdf)) emailSent += 1
      else emailFailed += 1
    } catch {
      emailFailed += 1
    }
    try {
      await env.DB
        .prepare(
          `INSERT INTO in_app_notifications
            (id, user_id, category, title, body, created_at)
           VALUES (?, ?, 'weekly_report', ?, ?, ?)`,
        )
        .bind(
          crypto.randomUUID(),
          recipient.id,
          row.title,
          '本期市场周报已发送至你的注册邮箱。',
          Date.now(),
        )
        .run()
      notifySent += 1
    } catch {
      // The email result remains valid even if the in-app notice failed.
    }
  }
  return {
    recipients: recipients.results.length,
    emailSent,
    emailFailed,
    notifySent,
    notifyFailed: recipients.results.length - notifySent,
  }
}

async function sendWeeklyNow(
  request: Request,
  env: Env,
  requestId: string,
  id: number,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const row = await getWeeklyRow(env, id)
  if (row.status === 'sent') {
    return jsonResponse(
      {
        dispatch_id: id,
        year: row.year,
        week: row.week,
        recipients: 0,
        email_sent: 0,
        email_failed: 0,
        notify_sent: 0,
        notify_failed: 0,
        skipped: true,
      },
      200,
      requestId,
      request.method,
    )
  }
  const result = await deliverWeekly(env, row)
  const sentAt = Date.now()
  await env.DB
    .prepare(
      `UPDATE weekly_dispatches SET status = 'sent', sent_at = ? WHERE id = ?`,
    )
    .bind(sentAt, id)
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'weekly.sent',
    detail: { dispatch_id: id, recipients: result.recipients },
    createdAt: sentAt,
  }).run()
  return jsonResponse(
    {
      dispatch_id: id,
      year: row.year,
      week: row.week,
      recipients: result.recipients,
      email_sent: result.emailSent,
      email_failed: result.emailFailed,
      notify_sent: result.notifySent,
      notify_failed: result.notifyFailed,
      skipped: result.recipients === 0,
    },
    200,
    requestId,
    request.method,
  )
}

type SocialDraftRow = Readonly<{
  id: number
  symbol: string
  bias: string
  tweet_text: string
  compliance_passed: number
  compliance_reason: string | null
  status: string
  image_key: string | null
  auto_drafted: number
  has_url: number
  gen_style: string
  created_at: number
}>

type CreatedSocialDraft = Readonly<{
  id: number
  symbol: string
  text: string
  compliancePassed: boolean
}>

async function listSocialDrafts(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const since = Date.now() - 7 * 24 * 60 * 60 * 1_000
  const [drafts, dispatches] = await Promise.all([
    env.DB
      .prepare(
        `SELECT id, symbol, bias, tweet_text, compliance_passed,
                compliance_reason, status, image_key, auto_drafted, has_url,
                gen_style, created_at
         FROM social_drafts
         WHERE created_at >= ?
         ORDER BY created_at DESC
         LIMIT 100`,
      )
      .bind(since)
      .all<SocialDraftRow>(),
    env.DB
      .prepare(
        `SELECT id, draft_id, platform, status, url, error, source
         FROM social_dispatches
         WHERE created_at >= ?
         ORDER BY created_at DESC`,
      )
      .bind(since)
      .all<{
        id: number
        draft_id: number
        platform: string
        status: string
        url: string | null
        error: string | null
        source: string
      }>(),
  ])
  return jsonResponse(
    {
      items: drafts.results.map((draft) => ({
        id: draft.id,
        symbol: draft.symbol,
        bias: draft.bias,
        tweet_text: draft.tweet_text,
        compliance_passed: draft.compliance_passed === 1,
        compliance_reason: draft.compliance_reason,
        status: draft.status,
        image_path: draft.image_key,
        created_at: iso(draft.created_at),
        auto_drafted: draft.auto_drafted === 1,
        has_url: draft.has_url === 1,
        gen_style: draft.gen_style,
        dispatches: dispatches.results
          .filter((item) => item.draft_id === draft.id)
          .map((item) => ({
            platform: item.platform,
            status: item.status,
            url: item.url,
            error: item.error,
            source: item.source,
          })),
      })),
      total: drafts.results.length,
    },
    200,
    requestId,
    request.method,
  )
}

function compliant(text: string): { passed: boolean; reason: string | null } {
  const blocked = /(稳赚|保本| guaranteed|无风险|确定涨|确定跌|收益保证)/iu
  if (blocked.test(text)) return { passed: false, reason: '含有收益承诺或确定性表述' }
  return { passed: true, reason: null }
}

async function createSocialDrafts(
  env: Env,
  style: 'default' | 'x_short',
  autoDrafted: boolean,
): Promise<{ items: CreatedSocialDraft[]; provider: string }> {
  const quotes = await env.DB
    .prepare(
      `SELECT symbol, name, last_point, change_pct
       FROM market_overview_quotes
       WHERE category = 'crypto'
       ORDER BY ABS(change_pct) DESC
       LIMIT 3`,
    )
    .all<{
      symbol: string
      name: string
      last_point: number
      change_pct: number
    }>()
  if (quotes.results.length === 0) throw new HttpError(409, '暂无可用市场数据')
  const ai = await invokeAi(env, {
    system:
      '你是专业市场内容编辑。只输出 JSON，不承诺收益，不给确定性涨跌结论，数据必须原样引用。',
    prompt: `根据以下实时行情生成 2 条${style === 'x_short' ? '不超过 110 个汉字的 X 短推' : '币安广场中文市场观察'}。
行情：${JSON.stringify(quotes.results)}
输出 {"drafts":[{"symbol":"BTC/USDT","bias":"偏多|偏空|中性","text":"..."}]}。`,
    maxTokens: 700,
    temperature: 0.35,
  })
  const parsed = parseAiJson(ai.content)
  const drafts = Array.isArray(parsed.drafts) ? parsed.drafts.slice(0, 4) : []
  const created: CreatedSocialDraft[] = []
  const timestamp = Date.now()
  for (const value of drafts) {
    if (typeof value !== 'object' || value === null) continue
    const item = value as Record<string, unknown>
    const symbol = typeof item.symbol === 'string' ? item.symbol.slice(0, 32) : ''
    const bias = typeof item.bias === 'string' ? item.bias.slice(0, 16) : '中性'
    let text = typeof item.text === 'string' ? item.text.trim() : ''
    if (!symbol || !text) continue
    if (style === 'x_short') text = [...text].slice(0, 110).join('')
    const gate = compliant(text)
    const row = await env.DB
      .prepare(
        `INSERT INTO social_drafts
          (symbol, bias, tweet_text, compliance_passed, compliance_reason,
           status, auto_drafted, has_url, gen_style, provider, model, created_at)
         VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?)
         RETURNING id`,
      )
      .bind(
        symbol,
        bias,
        text,
        gate.passed ? 1 : 0,
        gate.reason,
        autoDrafted ? 1 : 0,
        /https?:\/\//iu.test(text) ? 1 : 0,
        style,
        ai.provider,
        ai.model,
        timestamp + created.length,
      )
      .first<{ id: number }>()
    if (row) {
      created.push({
        id: row.id,
        symbol,
        text,
        compliancePassed: gate.passed,
      })
    }
  }
  return { items: created, provider: ai.provider }
}

async function generateSocialDrafts(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const style = new URL(request.url).searchParams.get('style') === 'x_short'
    ? 'x_short'
    : 'default'
  const result = await createSocialDrafts(env, style, false)
  const timestamp = Date.now()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'social.generated',
    detail: { style, created: result.items.length, provider: result.provider },
    createdAt: timestamp,
  }).run()
  return jsonResponse(
    {
      status: 'completed',
      message: `已生成 ${result.items.length} 条${style === 'x_short' ? ' X 短推' : '内容草稿'}`,
    },
    200,
    requestId,
    request.method,
  )
}

type ExternalEnv = Readonly<{
  X_API_KEY?: string
}>

function adapters(env: Env): { binance: boolean; x: boolean } {
  const external = env as Env & ExternalEnv
  return {
    binance: binanceSquareEnabled(env),
    x: Boolean(external.X_API_KEY?.trim()),
  }
}

function cstMinute(timestamp = Date.now()): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(timestamp))
  const value = (type: 'hour' | 'minute') =>
    Number(parts.find((part) => part.type === type)?.value ?? 0)
  return value('hour') * 60 + value('minute')
}

async function autoStatus(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const config = await env.DB
    .prepare(
      `SELECT enabled, circuit_open, binance_checked, x_checked, daily_limit,
              failure_count, last_error
       FROM social_automation_config WHERE id = 1`,
    )
    .first<{
      enabled: number
      circuit_open: number
      binance_checked: number
      x_checked: number
      daily_limit: number
      failure_count: number
      last_error: string | null
    }>()
  if (!config) throw new HttpError(500, '自动托管配置不存在')
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
  }).format(new Date())
  const used = await env.DB
    .prepare(
      `SELECT COUNT(*) AS count
       FROM social_dispatches
       WHERE source = 'auto' AND status = 'success'
         AND date(updated_at / 1000, 'unixepoch', '+8 hours') = ?`,
    )
    .bind(today)
    .first<{ count: number }>()
  const adapter = adapters(env)
  const dailyUsed = Number(used?.count ?? 0)
  const minute = cstMinute()
  return jsonResponse(
    {
      enabled: config.enabled === 1,
      circuit_open: config.circuit_open === 1,
      daily_used: dailyUsed,
      daily_remaining: Math.max(0, config.daily_limit - dailyUsed),
      failure_count: config.failure_count,
      last_error: config.last_error,
      in_window: minute >= 7 * 60 + 30 && minute <= 22 * 60 + 30,
      platforms: [
        {
          platform: 'binance_square',
          checked: config.binance_checked === 1,
          auto_allowed: true,
          adapter_enabled: adapter.binance,
        },
        {
          platform: 'x',
          checked: config.x_checked === 1,
          auto_allowed: false,
          adapter_enabled: adapter.x,
        },
      ],
    },
    200,
    requestId,
    request.method,
  )
}

async function toggleAuto(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const body = await readJsonObject(request)
  if (typeof body.enabled !== 'boolean') throw new HttpError(422, 'enabled 必须为布尔值')
  const current = await env.DB
    .prepare(
      `SELECT binance_checked, x_checked FROM social_automation_config WHERE id = 1`,
    )
    .first<{ binance_checked: number; x_checked: number }>()
  const adapter = adapters(env)
  if (
    body.enabled &&
    !(
      current?.binance_checked === 1 && adapter.binance
    )
  ) {
    throw new HttpError(409, '请先配置并勾选至少一个发布平台')
  }
  await env.DB
    .prepare(
      `UPDATE social_automation_config
       SET enabled = ?, circuit_open = 0, failure_count = 0,
           last_error = NULL, updated_at = ? WHERE id = 1`,
    )
    .bind(body.enabled ? 1 : 0, Date.now())
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: body.enabled ? 'social.auto_enabled' : 'social.auto_disabled',
    createdAt: Date.now(),
  }).run()
  return autoStatus(request, env, requestId)
}

async function toggleAutoPlatform(
  request: Request,
  env: Env,
  requestId: string,
  platform: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  if (!['binance_square', 'x'].includes(platform)) {
    throw new HttpError(422, '未知发布平台')
  }
  const body = await readJsonObject(request)
  if (typeof body.checked !== 'boolean') throw new HttpError(422, 'checked 必须为布尔值')
  if (platform === 'x' && body.checked) {
    throw new HttpError(409, 'X 自动发布尚未开放，当前仅允许币安广场')
  }
  const column = platform === 'x' ? 'x_checked' : 'binance_checked'
  await env.DB
    .prepare(
      `UPDATE social_automation_config SET ${column} = ?, updated_at = ? WHERE id = 1`,
    )
    .bind(body.checked ? 1 : 0, Date.now())
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'social.platform_updated',
    detail: { platform, checked: body.checked },
    createdAt: Date.now(),
  }).run()
  return autoStatus(request, env, requestId)
}

async function stopAuto(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  await env.DB
    .prepare(
      `UPDATE social_automation_config
       SET enabled = 0, circuit_open = 1, updated_at = ? WHERE id = 1`,
    )
    .bind(Date.now())
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'social.circuit_opened',
    createdAt: Date.now(),
  }).run()
  return jsonResponse(
    { stopped: true, revoked: 0, message: '自动托管已停止，熔断已开启' },
    200,
    requestId,
    request.method,
  )
}

async function publishSocialDraft(
  request: Request,
  env: Env,
  requestId: string,
  draftId: number,
): Promise<Response> {
  const admin = await requireAdmin(request, env)
  const body = await readJsonObject(request)
  const platform = body.platform
  if (platform !== 'x' && platform !== 'binance_square') {
    throw new HttpError(422, '未知发布平台')
  }
  const adapter = adapters(env)
  if ((platform === 'x' && !adapter.x) || (platform === 'binance_square' && !adapter.binance)) {
    throw new HttpError(409, `${platform === 'x' ? 'X' : '币安广场'} 发布凭证尚未独立配置`)
  }
  if (platform === 'x') {
    throw new HttpError(501, 'X 发布适配器尚未启用')
  }
  const result = await dispatchSocialDraft(env, draftId, 'binance_square', 'manual')
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: result.status === 'success' ? 'social.published' : 'social.publish_failed',
    detail: {
      draft_id: draftId,
      dispatch_id: result.dispatchId,
      platform,
      error: result.error,
    },
    createdAt: Date.now(),
  }).run()
  return jsonResponse(
    {
      dispatch_id: result.dispatchId,
      platform,
      status: result.status,
      message: result.status === 'success' ? '已发布到币安广场' : result.error,
      url: result.url,
    },
    200,
    requestId,
    request.method,
  )
}

type DispatchResult = Readonly<{
  dispatchId: number
  status: 'success' | 'failed'
  url: string | null
  error: string | null
}>

async function dispatchSocialDraft(
  env: Env,
  draftId: number,
  platform: 'binance_square',
  source: 'manual' | 'auto',
): Promise<DispatchResult> {
  const draft = await env.DB
    .prepare(
      `SELECT id, tweet_text, compliance_passed
       FROM social_drafts WHERE id = ?`,
    )
    .bind(draftId)
    .first<{ id: number; tweet_text: string; compliance_passed: number }>()
  if (!draft) throw new HttpError(404, '推文草稿不存在')
  if (draft.compliance_passed !== 1) throw new HttpError(409, '合规门禁未通过')

  const existing = await env.DB
    .prepare(
      `SELECT id, status, url, error FROM social_dispatches
       WHERE draft_id = ? AND platform = ?`,
    )
    .bind(draftId, platform)
    .first<{ id: number; status: string; url: string | null; error: string | null }>()
  if (existing?.status === 'success') {
    return {
      dispatchId: existing.id,
      status: 'success',
      url: existing.url,
      error: null,
    }
  }

  const now = Date.now()
  const [today, last] = await Promise.all([
    env.DB
      .prepare(
        `SELECT COUNT(*) AS count FROM social_dispatches
         WHERE platform = ? AND status = 'success'
           AND date(updated_at / 1000, 'unixepoch', '+8 hours') =
               date(? / 1000, 'unixepoch', '+8 hours')`,
      )
      .bind(platform, now)
      .first<{ count: number }>(),
    env.DB
      .prepare(
        `SELECT MAX(updated_at) AS last_at FROM social_dispatches
         WHERE platform = ? AND status = 'success'`,
      )
      .bind(platform)
      .first<{ last_at: number | null }>(),
  ])
  if (Number(today?.count ?? 0) >= 100) {
    throw new HttpError(429, '币安广场今日已达到 100 条官方上限')
  }
  if (last?.last_at && now - last.last_at < 30_000) {
    throw new HttpError(429, '发布间隔不足 30 秒，请稍后重试')
  }

  const dispatch = await env.DB
    .prepare(
      `INSERT INTO social_dispatches
        (draft_id, platform, status, url, error, source, created_at, updated_at)
       VALUES (?, ?, 'pending', NULL, NULL, ?, ?, ?)
       ON CONFLICT(draft_id, platform) DO UPDATE SET
         status = 'pending', url = NULL, error = NULL,
         source = excluded.source, updated_at = excluded.updated_at
       RETURNING id`,
    )
    .bind(draftId, platform, source, now, now)
    .first<{ id: number }>()
  if (!dispatch) throw new HttpError(500, '发布台账创建失败')

  const published = await publishToBinanceSquare(env, draft.tweet_text)
  const status = published.success ? 'success' : 'failed'
  await env.DB.batch([
    env.DB
      .prepare(
        `UPDATE social_dispatches
         SET status = ?, url = ?, error = ?, updated_at = ? WHERE id = ?`,
      )
      .bind(status, published.url, published.error, Date.now(), dispatch.id),
    env.DB
      .prepare('UPDATE social_drafts SET status = ? WHERE id = ?')
      .bind(published.success ? 'published' : 'failed', draftId),
  ])
  return {
    dispatchId: dispatch.id,
    status,
    url: published.url,
    error: published.error,
  }
}

function socialSlot(timestamp: number): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(timestamp))
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? '00'
  return `${value('year')}-${value('month')}-${value('day')}T${value('hour')}:${value('minute')}`
}

async function updateAutoRun(
  env: Env,
  slot: string,
  values: Readonly<{
    status: 'success' | 'failed' | 'skipped'
    draftId?: number | null
    dispatchId?: number | null
    error?: string | null
  }>,
): Promise<void> {
  await env.DB
    .prepare(
      `UPDATE social_auto_runs
       SET status = ?, draft_id = ?, dispatch_id = ?, error = ?, updated_at = ?
       WHERE slot = ?`,
    )
    .bind(
      values.status,
      values.draftId ?? null,
      values.dispatchId ?? null,
      values.error?.slice(0, 500) ?? null,
      Date.now(),
      slot,
    )
    .run()
}

async function autoCandidate(env: Env, timestamp: number): Promise<CreatedSocialDraft | null> {
  const row = await env.DB
    .prepare(
      `SELECT d.id, d.symbol, d.tweet_text, d.compliance_passed
       FROM social_drafts d
       WHERE d.auto_drafted = 1
         AND d.gen_style = 'default'
         AND d.compliance_passed = 1
         AND d.created_at >= ?
         AND NOT EXISTS (
           SELECT 1 FROM social_dispatches sd
           WHERE sd.draft_id = d.id AND sd.platform = 'binance_square'
             AND sd.status = 'success'
         )
         AND NOT EXISTS (
           SELECT 1
           FROM social_drafts recent_d
           JOIN social_dispatches recent_sd ON recent_sd.draft_id = recent_d.id
           WHERE recent_d.symbol = d.symbol
             AND recent_sd.platform = 'binance_square'
             AND recent_sd.status = 'success'
             AND recent_sd.updated_at >= ?
         )
       ORDER BY d.created_at DESC
       LIMIT 1`,
    )
    .bind(timestamp - 30 * 60_000, timestamp - 6 * 60 * 60_000)
    .first<{
      id: number
      symbol: string
      tweet_text: string
      compliance_passed: number
    }>()
  return row
    ? {
        id: row.id,
        symbol: row.symbol,
        text: row.tweet_text,
        compliancePassed: row.compliance_passed === 1,
      }
    : null
}

async function recordAutoFailure(env: Env, error: string): Promise<number> {
  await env.DB
    .prepare(
      `UPDATE social_automation_config
       SET failure_count = failure_count + 1, last_error = ?, updated_at = ?
       WHERE id = 1`,
    )
    .bind(error.slice(0, 500), Date.now())
    .run()
  const state = await env.DB
    .prepare('SELECT failure_count FROM social_automation_config WHERE id = 1')
    .first<{ failure_count: number }>()
  const failures = state?.failure_count ?? 1
  if (failures >= 3) {
    await env.DB
      .prepare(
        `UPDATE social_automation_config
         SET enabled = 0, circuit_open = 1, updated_at = ? WHERE id = 1`,
      )
      .bind(Date.now())
      .run()
  }
  return failures
}

async function runSocialAutomation(env: Env, timestamp: number): Promise<void> {
  const minute = cstMinute(timestamp)
  if (minute < 7 * 60 + 30 || minute > 22 * 60 + 30 || minute % 15 !== 5) return
  const config = await env.DB
    .prepare(
      `SELECT enabled, circuit_open, binance_checked, daily_limit
       FROM social_automation_config WHERE id = 1`,
    )
    .first<{
      enabled: number
      circuit_open: number
      binance_checked: number
      daily_limit: number
    }>()
  if (
    !config || config.enabled !== 1 || config.circuit_open === 1 ||
    config.binance_checked !== 1 || !binanceSquareEnabled(env)
  ) return

  const used = await env.DB
    .prepare(
      `SELECT COUNT(*) AS count FROM social_dispatches
       WHERE source = 'auto' AND platform = 'binance_square' AND status = 'success'
         AND date(updated_at / 1000, 'unixepoch', '+8 hours') =
             date(? / 1000, 'unixepoch', '+8 hours')`,
    )
    .bind(timestamp)
    .first<{ count: number }>()
  if (Number(used?.count ?? 0) >= config.daily_limit) return

  const slot = socialSlot(timestamp)
  const claim = await env.DB
    .prepare(
      `INSERT OR IGNORE INTO social_auto_runs
        (slot, status, created_at, updated_at)
       VALUES (?, 'running', ?, ?)`,
    )
    .bind(slot, timestamp, timestamp)
    .run()
  if (Number(claim.meta.changes ?? 0) === 0) return

  try {
    let candidate = await autoCandidate(env, timestamp)
    if (!candidate) {
      await createSocialDrafts(env, 'default', true)
      candidate = await autoCandidate(env, Date.now())
    }
    if (!candidate) throw new Error('未生成可发布且通过门禁的币安广场草稿')
    const result = await dispatchSocialDraft(
      env,
      candidate.id,
      'binance_square',
      'auto',
    )
    if (result.status !== 'success') {
      throw new Error(result.error ?? '币安广场发布失败')
    }
    await Promise.all([
      updateAutoRun(env, slot, {
        status: 'success',
        draftId: candidate.id,
        dispatchId: result.dispatchId,
      }),
      env.DB
        .prepare(
          `UPDATE social_automation_config
           SET failure_count = 0, last_error = NULL, updated_at = ? WHERE id = 1`,
        )
        .bind(Date.now())
        .run(),
    ])
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const failures = await recordAutoFailure(env, message)
    await updateAutoRun(env, slot, {
      status: 'failed',
      error: message,
    })
    console.error(JSON.stringify({
      event: 'social.auto_failed',
      slot,
      failures,
      circuitOpened: failures >= 3,
      error: message,
    }))
  }
}

export async function runAdminOperationsCron(
  env: Env,
  timestamp = Date.now(),
): Promise<void> {
  await runSocialAutomation(env, timestamp)
  const minute = cstMinute(timestamp)
  const day = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    weekday: 'short',
  }).format(new Date(timestamp))
  if (day === 'Sun' && minute >= 21 * 60 && minute < 21 * 60 + 5) {
    const scheduled = await env.DB
      .prepare(
        `SELECT id, year, week, period_start, period_end, title, status,
                pdf_filename, md_content, extracted_json, email_html,
                uploaded_at, sent_at
         FROM weekly_dispatches
         WHERE status = 'scheduled'
         ORDER BY uploaded_at
         LIMIT 10`,
      )
      .all<WeeklyRow>()
    for (const row of scheduled.results) {
      try {
        await deliverWeekly(env, row)
        await env.DB
          .prepare(
            `UPDATE weekly_dispatches SET status = 'sent', sent_at = ? WHERE id = ?`,
          )
          .bind(Date.now(), row.id)
          .run()
      } catch (error) {
        console.error(JSON.stringify({
          event: 'weekly.cron_failed',
          dispatchId: row.id,
          error: error instanceof Error ? error.message : String(error),
        }))
      }
    }
  }
}

export async function handleAdminOperationsRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`
  if (route === 'GET /api/v1/admin/weekly-dispatch') {
    return listWeekly(request, env, requestId)
  }
  if (route === 'POST /api/v1/admin/weekly-dispatch/upload') {
    return uploadWeekly(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/x-tweets') {
    return listSocialDrafts(request, env, requestId)
  }
  if (route === 'POST /api/v1/admin/x-tweets/generate') {
    return generateSocialDrafts(request, env, requestId)
  }
  if (route === 'GET /api/v1/admin/x-auto/status') {
    return autoStatus(request, env, requestId)
  }
  if (route === 'POST /api/v1/admin/x-auto/toggle') {
    return toggleAuto(request, env, requestId)
  }
  if (route === 'POST /api/v1/admin/x-auto/stop') {
    return stopAuto(request, env, requestId)
  }
  const weeklyMatch = /^\/api\/v1\/admin\/weekly-dispatch\/(\d+)$/u.exec(path)
  if (weeklyMatch && request.method === 'GET') {
    return getWeekly(request, env, requestId, Number(weeklyMatch[1]))
  }
  const scheduleMatch =
    /^\/api\/v1\/admin\/weekly-dispatch\/(\d+)\/(schedule|cancel-schedule|send-now)$/u.exec(path)
  if (scheduleMatch && request.method === 'POST') {
    const id = Number(scheduleMatch[1])
    if (scheduleMatch[2] === 'send-now') {
      return sendWeeklyNow(request, env, requestId, id)
    }
    return setWeeklyStatus(
      request,
      env,
      requestId,
      id,
      scheduleMatch[2] === 'schedule' ? 'scheduled' : 'uploaded',
    )
  }
  const platformMatch =
    /^\/api\/v1\/admin\/x-auto\/platforms\/([^/]+)$/u.exec(path)
  if (platformMatch && request.method === 'POST') {
    return toggleAutoPlatform(
      request,
      env,
      requestId,
      platformMatch[1] ?? '',
    )
  }
  const publishMatch =
    /^\/api\/v1\/admin\/x-tweets\/(\d+)\/publish$/u.exec(path)
  if (publishMatch && request.method === 'POST') {
    return publishSocialDraft(
      request,
      env,
      requestId,
      Number(publishMatch[1]),
    )
  }
  const imageMatch =
    /^\/api\/v1\/admin\/x-tweets\/(\d+)\/image$/u.exec(path)
  if (imageMatch && request.method === 'GET') {
    await requireAdmin(request, env)
    throw new HttpError(404, '该草稿暂无配图')
  }
  return null
}
