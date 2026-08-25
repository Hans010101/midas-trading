import { Buffer } from 'node:buffer'

import {
  adminActionStatement,
  requireAdmin,
} from './admin'
import { invokeAi, parseAiJson } from './ai-provider'
import {
  binanceSquareEnabled,
  publishToBinanceSquare,
  type BinanceSquareAccountKey,
} from './binance-square'
import { fetchCryptoMarketScan } from './crypto-market'
import { HttpError, jsonResponse, readJsonObject } from './http'
import {
  cleanSocialPostText,
  contentTags,
  draftContentEvent,
  ingestSocialContent,
  markContentDrafted,
  nextContentEvent,
  type SocialContentType,
} from './social-content'

const MAX_PDF_BYTES = 5 * 1024 * 1024
const MAX_MD_BYTES = 512 * 1024
const ASSET_CHUNK_BYTES = 256 * 1024
const PRIMARY_SQUARE_ACCOUNT: BinanceSquareAccountKey = 'midas_trading'

function squareAccountKey(value: unknown): BinanceSquareAccountKey {
  return value === 'legacy_midas' ? 'legacy_midas' : PRIMARY_SQUARE_ACCOUNT
}

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
  content_type: string
  source_event_id: number | null
  account_key: BinanceSquareAccountKey
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
  await recoverStaleSocialDispatches(env)
  const since = Date.now() - 7 * 24 * 60 * 60 * 1_000
  const [drafts, dispatches] = await Promise.all([
    env.DB
      .prepare(
        `SELECT id, symbol, bias, tweet_text, compliance_passed,
                compliance_reason, status, image_key, auto_drafted, has_url,
                gen_style, content_type, source_event_id, account_key, created_at
         FROM social_drafts
         WHERE created_at >= ?
         ORDER BY created_at DESC
         LIMIT 100`,
      )
      .bind(since)
      .all<SocialDraftRow>(),
    env.DB
      .prepare(
        `SELECT id, draft_id, platform, status, url, error, source, account_key,
                platform_post_id, view_count, like_count, comment_count,
                share_count, metrics_updated_at
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
        account_key: BinanceSquareAccountKey
        platform_post_id: string | null
        view_count: number | null
        like_count: number | null
        comment_count: number | null
        share_count: number | null
        metrics_updated_at: number | null
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
        content_type: draft.content_type,
        source_event_id: draft.source_event_id,
        account_key: draft.account_key,
        dispatches: dispatches.results
          .filter((item) => item.draft_id === draft.id)
          .map((item) => ({
            platform: item.platform,
            status: item.status,
            url: item.url,
            error: item.error,
            source: item.source,
            account_key: item.account_key,
            platform_post_id: item.platform_post_id,
            view_count: item.view_count,
            like_count: item.like_count,
            comment_count: item.comment_count,
            share_count: item.share_count,
            metrics_updated_at: iso(item.metrics_updated_at),
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

type SocialMarketQuote = Readonly<{
  symbol: string
  name: string
  last_point: number
  change_pct: number
  high_24h?: number
  low_24h?: number
  quote_volume_24h?: number
  quoted_at?: string
}>

function compactMarketNumber(value: number): string {
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: value >= 100 ? 2 : value >= 1 ? 4 : 8,
  }).format(value)
}

function compactMarketVolume(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B USDT`
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M USDT`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K USDT`
  return `${value.toFixed(0)} USDT`
}

export function marketTemplateFallback(quote: SocialMarketQuote): {
  symbol: string
  bias: string
  text: string
} {
  const move = quote.change_pct
  const change = `${move >= 0 ? '+' : ''}${move.toFixed(2)}%`
  const base = quote.symbol.split('/')[0] ?? quote.name
  const hook = move >= 8
    ? `🔥 $${base} 今天是真热闹：24 小时已经冲了 ${change}。`
    : move <= -8
      ? `⚠️ $${base} 这波回撤不小：24 小时跌了 ${Math.abs(move).toFixed(2)}%。`
      : move >= 0
        ? `👀 $${base} 正在悄悄走强：24 小时 ${change}。`
        : `👀 $${base} 短线有点承压：24 小时 ${change}。`
  const facts = [`最新价 ${compactMarketNumber(quote.last_point)}`]
  if (Number.isFinite(quote.high_24h) && Number.isFinite(quote.low_24h)) {
    facts.push(
      `日内区间 ${compactMarketNumber(quote.low_24h!)}–${compactMarketNumber(quote.high_24h!)}`,
    )
  }
  if (Number.isFinite(quote.quote_volume_24h) && quote.quote_volume_24h! > 0) {
    facts.push(`24H 成交额 ${compactMarketVolume(quote.quote_volume_24h!)}`)
  }
  const stance = Math.abs(move) >= 8
    ? '波动已经明显放大，追涨杀跌都容易被来回扫，先看量价能不能继续配合。'
    : '现在更像是方向选择前的试探，单看涨跌幅还不够，量能确认更重要。'
  return {
    symbol: quote.symbol,
    bias: move > 0 ? '偏多' : move < 0 ? '偏空' : '中性',
    text: `${hook}\n\n数据摆在这：${facts.join('，')}。\n\n我的判断：${stance}\n\n接下来盯两件事：一是能否带量突破 24H 高点；二是回踩时能否守住日内中枢。没有量能确认，就要防冲高回落。`,
  }
}

async function createSocialDrafts(
  env: Env,
  style: 'default' | 'x_short',
  autoDrafted: boolean,
  preferredEventTypes: readonly SocialContentType[] = [],
  accountKey: BinanceSquareAccountKey = PRIMARY_SQUARE_ACCOUNT,
): Promise<{ items: CreatedSocialDraft[]; provider: string }> {
  if (style === 'default' && preferredEventTypes.length > 0) {
    const event = await nextContentEvent(env, preferredEventTypes)
    if (event) {
      const drafted = await draftContentEvent(env, event)
      const gate = compliant(drafted.text)
      const row = await env.DB
        .prepare(
          `INSERT INTO social_drafts
            (symbol, bias, tweet_text, compliance_passed, compliance_reason,
             status, auto_drafted, has_url, gen_style, provider, model,
             content_type, source_event_id, account_key, created_at)
           VALUES (?, ?, ?, ?, ?, 'draft', ?, 0, 'default', ?, ?, ?, ?, ?, ?)
           RETURNING id`,
        )
        .bind(
          drafted.symbol,
          drafted.bias,
          drafted.text,
          gate.passed ? 1 : 0,
          gate.reason,
          autoDrafted ? 1 : 0,
          drafted.provider,
          drafted.model,
          event.contentType,
          event.id,
          accountKey,
          Date.now(),
        )
        .first<{ id: number }>()
      if (row) {
        await markContentDrafted(env, event.id)
        return {
          items: [{
            id: row.id,
            symbol: drafted.symbol,
            text: drafted.text,
            compliancePassed: gate.passed,
          }],
          provider: drafted.provider,
        }
      }
    }
  }
  const recentlyPublished = await env.DB
    .prepare(
      `SELECT DISTINCT d.symbol
       FROM social_drafts d
       JOIN social_dispatches sd ON sd.draft_id = d.id
       WHERE sd.platform = 'binance_square' AND sd.status = 'success'
         AND sd.account_key = ?
         AND sd.updated_at >= ?`,
    )
    .bind(accountKey, Date.now() - SOCIAL_SYMBOL_COOLDOWN_MS)
    .all<{ symbol: string }>()
  const recentSymbols = new Set(recentlyPublished.results.map((item) => item.symbol))
  let quotes: SocialMarketQuote[] = []
  try {
    const scan = await fetchCryptoMarketScan(60)
    quotes = scan
      .filter((item) => !recentSymbols.has(item.symbol))
      .slice(0, 12)
      .map((item) => ({
        symbol: item.symbol,
        name: item.symbol.split('/')[0] ?? item.symbol,
        last_point: item.last_price,
        change_pct: item.change_pct_24h,
        high_24h: item.high_24h,
        low_24h: item.low_24h,
        quote_volume_24h: item.quote_volume_24h,
        quoted_at: item.ts,
      }))
  } catch (error) {
    console.error(JSON.stringify({
      event: 'social.market_scan_failed',
      error: error instanceof Error ? error.message : String(error),
    }))
  }
  if (quotes.length === 0) {
    const fallback = await env.DB
      .prepare(
        `SELECT symbol, name, last_point, change_pct
         FROM market_overview_quotes
         WHERE category = 'crypto'
         ORDER BY ABS(change_pct) DESC
         LIMIT 12`,
      )
      .all<{
        symbol: string
        name: string
        last_point: number
        change_pct: number
      }>()
    quotes = fallback.results.filter((item) => !recentSymbols.has(item.symbol))
    if (quotes.length === 0) quotes = fallback.results
  }
  if (quotes.length === 0) throw new HttpError(409, '暂无可用市场数据')
  const draftCount = autoDrafted ? 1 : 2
  let provider = 'rules-fallback'
  let model = 'market-scan-template-v1'
  let parsed: Record<string, unknown> = {}
  try {
    const ai = await invokeAi(env, {
      system:
        '你是有判断力、说人话的加密市场内容主编。只输出 JSON，不承诺收益，不给确定性涨跌结论，数据必须原样引用。语言口语化、有节奏、有画面感，但不使用虚假夸张。',
      prompt: `根据以下 Midas Trading 实时波动扫描生成 ${draftCount} 条${style === 'x_short' ? '不超过 110 个汉字的 X 短推' : '币安广场中文市场观察'}。
优先选择绝对涨跌幅、成交活跃度更值得关注的标的；价格、涨跌幅、24H 高低点和成交额只能引用输入数据。
每条必须用“抓眼但不过度”的口语化首句开场（最多 1 个 emoji），然后依次写：核心数据、我的判断、接下来盯两件事。
不要像普通行情播报，不要喊单，不要写“必涨/必跌/稳赚”，不要虚构支撑位、阻力位或新闻。不要输出链接、免责声明或风险提示，不要使用 Markdown 格式或 ** 加粗标记。
行情：${JSON.stringify(quotes)}
输出 {"drafts":[{"symbol":"BTC/USDT","bias":"偏多|偏空|中性","text":"..."}]}。不要自行添加 # 或 $ 标签。`,
      maxTokens: 700,
      temperature: 0.35,
    })
    parsed = parseAiJson(ai.content)
    provider = ai.provider
    model = ai.model
  } catch (error) {
    console.error(JSON.stringify({
      event: 'social.market_ai_fallback',
      error: error instanceof Error ? error.message : String(error),
    }))
  }
  const drafts = Array.isArray(parsed.drafts) ? parsed.drafts.slice(0, draftCount) : []
  const created: CreatedSocialDraft[] = []
  const timestamp = Date.now()
  const allowedSymbols = new Set(quotes.map((item) => item.symbol))
  const validDrafts = drafts.filter((value) => {
    if (typeof value !== 'object' || value === null) return false
    const symbol = (value as Record<string, unknown>).symbol
    return typeof symbol === 'string' && allowedSymbols.has(symbol)
  })
  const values = validDrafts.length > 0
    ? validDrafts
    : quotes.slice(0, draftCount).map(marketTemplateFallback)
  for (const value of values) {
    if (typeof value !== 'object' || value === null) continue
    const item = value as Record<string, unknown>
    const symbol = typeof item.symbol === 'string' ? item.symbol.slice(0, 32) : ''
    const bias = typeof item.bias === 'string' ? item.bias.slice(0, 16) : '中性'
    let text = typeof item.text === 'string' ? cleanSocialPostText(item.text) : ''
    if (!symbol || !text || !allowedSymbols.has(symbol)) continue
    if (style === 'x_short') text = [...text].slice(0, 110).join('')
    if (style === 'default') {
      const baseSymbol = symbol.split('/')[0]?.toUpperCase() ?? 'BTC'
      text = `${text}\n\n${contentTags([baseSymbol], `market:${symbol}:${timestamp}`).join(' ')}`
    }
    const gate = compliant(text)
    const row = await env.DB
      .prepare(
        `INSERT INTO social_drafts
          (symbol, bias, tweet_text, compliance_passed, compliance_reason,
           status, auto_drafted, has_url, gen_style, provider, model,
           content_type, account_key, created_at)
         VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, 'market_analysis', ?, ?)
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
        provider,
        model,
        accountKey,
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
  return { items: created, provider }
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
  const accountKey = squareAccountKey(new URL(request.url).searchParams.get('account_key'))
  const result = await createSocialDrafts(env, style, false, [], accountKey)
  const timestamp = Date.now()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'social.generated',
    detail: { style, account_key: accountKey, created: result.items.length, provider: result.provider },
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
  BINANCE_SQUARE_PUBLISH_MODE?: string
  GITHUB_PUBLISH_TOKEN?: string
}>

const GITHUB_PUBLISH_ENDPOINT =
  'https://api.github.com/repos/Hans010101/midas-trading/actions/workflows/binance-square.yml/dispatches'
const SOCIAL_SYMBOL_COOLDOWN_MS = 45 * 60_000

async function wakeGithubPublisher(env: Env): Promise<void> {
  const token = (env as Env & ExternalEnv).GITHUB_PUBLISH_TOKEN?.trim()
  if (!token) throw new Error('GitHub 独立发布器唤醒凭证未配置')
  const response = await fetch(GITHUB_PUBLISH_ENDPOINT, {
    method: 'POST',
    headers: {
      accept: 'application/vnd.github+json',
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      'user-agent': 'midas-trading-cloudflare',
      'x-github-api-version': '2022-11-28',
    },
    body: JSON.stringify({ ref: 'main' }),
    signal: AbortSignal.timeout(15_000),
  })
  if (response.status !== 204) {
    const detail = (await response.text()).slice(0, 300)
    throw new Error(`GitHub 独立发布器唤醒失败（HTTP ${response.status}）${detail ? `：${detail}` : ''}`)
  }
}

async function recoverStaleSocialDispatches(
  env: Env,
  timestamp = Date.now(),
): Promise<void> {
  await env.DB
    .prepare(
      `UPDATE social_dispatches
       SET status = 'failed',
           error = '独立发布器等待超过 10 分钟，已自动释放，可重新发布',
           updated_at = ?
       WHERE platform = 'binance_square' AND status = 'pending'
         AND updated_at < ?`,
    )
    .bind(timestamp, timestamp - 10 * 60_000)
    .run()
}

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
  const accounts = await env.DB
    .prepare(
      `SELECT account_key, display_name, enabled, circuit_open, platform_checked,
              daily_limit, failure_count, last_error, content_profile,
              slot_offset_minutes, follower_count, follower_updated_at,
              historical_view_count, historical_views_7d
       FROM social_automation_accounts ORDER BY slot_offset_minutes`,
    )
    .all<{
      account_key: BinanceSquareAccountKey
      display_name: string
      enabled: number
      circuit_open: number
      platform_checked: number
      daily_limit: number
      failure_count: number
      last_error: string | null
      content_profile: string
      slot_offset_minutes: number
      follower_count: number | null
      follower_updated_at: number | null
      historical_view_count: number
      historical_views_7d: number
    }>()
  if (accounts.results.length === 0) throw new HttpError(500, '自动托管配置不存在')
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
  }).format(new Date())
  const since = Date.now() - 7 * 24 * 60 * 60 * 1_000
  const used = await env.DB
    .prepare(
      `SELECT account_key,
              SUM(CASE WHEN source = 'auto' AND
                date(updated_at / 1000, 'unixepoch', '+8 hours') = ?
                THEN 1 ELSE 0 END) AS count,
              SUM(COALESCE(view_count, 0)) AS total_views,
              SUM(CASE WHEN updated_at >= ? THEN COALESCE(view_count, 0) ELSE 0 END) AS views_7d,
              SUM(CASE WHEN updated_at >= ? THEN COALESCE(like_count, 0) ELSE 0 END) AS likes_7d,
              SUM(CASE WHEN updated_at >= ? THEN COALESCE(comment_count, 0) ELSE 0 END) AS comments_7d
       FROM social_dispatches
       WHERE platform = 'binance_square' AND status = 'success'
       GROUP BY account_key`,
    )
    .bind(today, since, since, since)
    .all<{
      account_key: BinanceSquareAccountKey
      count: number
      total_views: number
      views_7d: number
      likes_7d: number
      comments_7d: number
    }>()
  const adapter = adapters(env)
  const usage = new Map(used.results.map((item) => [item.account_key, Number(item.count)]))
  const engagement = new Map(used.results.map((item) => [item.account_key, item]))
  const primary = accounts.results.find((item) => item.account_key === PRIMARY_SQUARE_ACCOUNT) ??
    accounts.results[0]!
  const dailyUsed = usage.get(primary.account_key) ?? 0
  const minute = cstMinute()
  const sourceHealth = await env.DB
    .prepare(
      `SELECT source, status, last_attempt_at, last_success_at, last_error,
              last_inserted, latency_ms
       FROM social_source_health
       ORDER BY CASE status WHEN 'healthy' THEN 0 WHEN 'error' THEN 1 ELSE 2 END,
                source`,
    )
    .all<{
      source: string
      status: 'healthy' | 'error' | 'disabled'
      last_attempt_at: number
      last_success_at: number | null
      last_error: string | null
      last_inserted: number
      latency_ms: number
    }>()
  return jsonResponse(
    {
      enabled: primary.enabled === 1,
      circuit_open: primary.circuit_open === 1,
      daily_used: dailyUsed,
      daily_remaining: Math.max(0, primary.daily_limit - dailyUsed),
      failure_count: primary.failure_count,
      last_error: primary.last_error,
      in_window: minute >= 8 * 60 && minute <= 22 * 60,
      accounts: accounts.results.map((account) => {
        const count = usage.get(account.account_key) ?? 0
        const metrics = engagement.get(account.account_key)
        return {
          account_key: account.account_key,
          display_name: account.display_name,
          enabled: account.enabled === 1,
          circuit_open: account.circuit_open === 1,
          checked: account.platform_checked === 1,
          adapter_enabled: binanceSquareEnabled(env, account.account_key),
          daily_used: count,
          daily_limit: account.daily_limit,
          daily_remaining: Math.max(0, account.daily_limit - count),
          failure_count: account.failure_count,
          last_error: account.last_error,
          content_profile: account.content_profile,
          slot_offset_minutes: account.slot_offset_minutes,
          follower_count: account.follower_count,
          follower_updated_at: iso(account.follower_updated_at),
          total_views: Number(metrics?.total_views ?? 0) + account.historical_view_count,
          views_7d: Number(metrics?.views_7d ?? 0) + account.historical_views_7d,
          likes_7d: Number(metrics?.likes_7d ?? 0),
          comments_7d: Number(metrics?.comments_7d ?? 0),
        }
      }),
      sources: sourceHealth.results.map((source) => ({
        source: source.source,
        status: source.status,
        last_attempt_at: iso(source.last_attempt_at),
        last_success_at: iso(source.last_success_at),
        last_error: source.last_error,
        last_inserted: source.last_inserted,
        latency_ms: source.latency_ms,
      })),
      platforms: [
        {
          platform: 'binance_square',
          checked: primary.platform_checked === 1,
          auto_allowed: true,
          adapter_enabled: adapter.binance,
        },
        {
          platform: 'x',
          checked: false,
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
  const accountKey = squareAccountKey(body.account_key)
  const current = await env.DB
    .prepare(
      `SELECT platform_checked FROM social_automation_accounts WHERE account_key = ?`,
    )
    .bind(accountKey)
    .first<{ platform_checked: number }>()
  if (
    body.enabled &&
    current?.platform_checked !== 1
  ) {
    throw new HttpError(409, '请先完成该账号凭证验收并勾选发布开关')
  }
  await env.DB
    .prepare(
      `UPDATE social_automation_accounts
       SET enabled = ?, circuit_open = 0, failure_count = 0,
           last_error = NULL, updated_at = ? WHERE account_key = ?`,
    )
    .bind(body.enabled ? 1 : 0, Date.now(), accountKey)
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
  const accountKey = squareAccountKey(body.account_key)
  if (platform === 'binance_square') {
    await env.DB
      .prepare(
        `UPDATE social_automation_accounts
         SET platform_checked = ?, updated_at = ? WHERE account_key = ?`,
      )
      .bind(body.checked ? 1 : 0, Date.now(), accountKey)
      .run()
    await adminActionStatement(env.DB, {
      operatorId: admin.user.id,
      action: 'social.account_platform_updated',
      detail: { account_key: accountKey, platform, checked: body.checked },
      createdAt: Date.now(),
    }).run()
    return autoStatus(request, env, requestId)
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
  const requestedAccount = new URL(request.url).searchParams.get('account_key')
  const accountKey = requestedAccount
    ? squareAccountKey(requestedAccount)
    : null
  await env.DB
    .prepare(
      `UPDATE social_automation_accounts
       SET enabled = 0, circuit_open = 1, updated_at = ?
       WHERE (? IS NULL OR account_key = ?)`,
    )
    .bind(Date.now(), accountKey, accountKey)
    .run()
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action: 'social.circuit_opened',
    detail: { account_key: accountKey },
    createdAt: Date.now(),
  }).run()
  return jsonResponse(
    {
      stopped: true,
      revoked: 0,
      message: accountKey
        ? `${accountKey} 自动托管已停止，熔断已开启`
        : '两个币安广场账号均已停止，熔断已开启',
    },
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
  const draftAccount = await env.DB
    .prepare('SELECT account_key FROM social_drafts WHERE id = ?')
    .bind(draftId)
    .first<{ account_key: BinanceSquareAccountKey }>()
  const accountKey = squareAccountKey(body.account_key ?? draftAccount?.account_key)
  const adapter = adapters(env)
  if ((platform === 'x' && !adapter.x) ||
    (platform === 'binance_square' &&
      (env as Env & ExternalEnv).BINANCE_SQUARE_PUBLISH_MODE !== 'github' &&
      !binanceSquareEnabled(env, accountKey))) {
    throw new HttpError(409, `${platform === 'x' ? 'X' : '币安广场'} 发布凭证尚未独立配置`)
  }
  if (platform === 'binance_square' && draftAccount?.account_key !== accountKey) {
    await env.DB
      .prepare('UPDATE social_drafts SET account_key = ? WHERE id = ?')
      .bind(accountKey, draftId)
      .run()
  }
  if (platform === 'x') {
    throw new HttpError(501, 'X 发布适配器尚未启用')
  }
  const result = await dispatchSocialDraft(env, draftId, 'binance_square', 'manual')
  const action = result.status === 'success'
    ? 'social.published'
    : result.status === 'pending'
      ? 'social.publish_queued'
      : 'social.publish_failed'
  await adminActionStatement(env.DB, {
    operatorId: admin.user.id,
    action,
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
      message: result.status === 'success'
        ? '已发布到币安广场'
        : result.status === 'pending'
          ? '已进入币安广场独立发布队列'
          : result.error,
      url: result.url,
    },
    200,
    requestId,
    request.method,
  )
}

type DispatchResult = Readonly<{
  dispatchId: number
  status: 'pending' | 'success' | 'failed'
  url: string | null
  error: string | null
}>

type BrowserEnv = Readonly<{ BROWSER?: BrowserRun }>

async function captureMarketChart(env: Env, symbol: string): Promise<ArrayBuffer | null> {
  const browser = (env as Env & BrowserEnv).BROWSER
  if (!browser) return null
  const url = new URL('/crypto-preview', env.PUBLIC_WEB_URL)
  url.searchParams.set('symbol', symbol)
  const response = await browser.quickAction('screenshot', {
    url: url.toString(),
    selector: '[data-social-chart="true"]',
    viewport: { width: 1280, height: 900, deviceScaleFactor: 2 },
    gotoOptions: { waitUntil: 'networkidle2', timeout: 45_000 },
    waitForTimeout: 3_000,
    actionTimeout: 60_000,
    screenshotOptions: { type: 'png', optimizeForSpeed: true },
    cacheTTL: 0,
  })
  if (!response.ok) {
    console.error(JSON.stringify({ event: 'social.chart_capture_failed', status: response.status }))
    return null
  }
  return response.arrayBuffer()
}

async function dispatchSocialDraft(
  env: Env,
  draftId: number,
  platform: 'binance_square',
  source: 'manual' | 'auto',
): Promise<DispatchResult> {
  const draft = await env.DB
    .prepare(
      `SELECT id, symbol, tweet_text, compliance_passed, content_type, account_key
       FROM social_drafts WHERE id = ?`,
    )
    .bind(draftId)
    .first<{
      id: number
      symbol: string
      tweet_text: string
      compliance_passed: number
      content_type: string
      account_key: BinanceSquareAccountKey
    }>()
  if (!draft) throw new HttpError(404, '推文草稿不存在')
  if (draft.compliance_passed !== 1) throw new HttpError(409, '合规门禁未通过')

  const existing = await env.DB
    .prepare(
      `SELECT id, status, url, error FROM social_dispatches
       WHERE draft_id = ? AND platform = ? AND account_key = ?`,
    )
    .bind(draftId, platform, draft.account_key)
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
           AND account_key = ?
           AND date(updated_at / 1000, 'unixepoch', '+8 hours') =
               date(? / 1000, 'unixepoch', '+8 hours')`,
      )
      .bind(platform, draft.account_key, now)
      .first<{ count: number }>(),
    env.DB
      .prepare(
        `SELECT MAX(updated_at) AS last_at FROM social_dispatches
         WHERE platform = ? AND status = 'success' AND account_key = ?`,
      )
      .bind(platform, draft.account_key)
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
        (draft_id, platform, status, url, error, source, created_at, updated_at, account_key)
       VALUES (?, ?, 'pending', NULL, NULL, ?, ?, ?, ?)
       ON CONFLICT(draft_id, platform) DO UPDATE SET
         status = 'pending', url = NULL, error = NULL,
         source = excluded.source, updated_at = excluded.updated_at
       RETURNING id`,
    )
    .bind(draftId, platform, source, now, now, draft.account_key)
    .first<{ id: number }>()
  if (!dispatch) throw new HttpError(500, '发布台账创建失败')

  if ((env as Env & ExternalEnv).BINANCE_SQUARE_PUBLISH_MODE === 'github') {
    await env.DB
      .prepare("UPDATE social_drafts SET status = 'draft' WHERE id = ?")
      .bind(draftId)
      .run()
    try {
      await wakeGithubPublisher(env)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      await env.DB
        .prepare(
          `UPDATE social_dispatches
           SET status = 'failed', error = ?, updated_at = ? WHERE id = ?`,
        )
        .bind(message.slice(0, 500), Date.now(), dispatch.id)
        .run()
      return {
        dispatchId: dispatch.id,
        status: 'failed',
        url: null,
        error: message,
      }
    }
    return {
      dispatchId: dispatch.id,
      status: 'pending',
      url: null,
      error: null,
    }
  }

  let imageBytes: ArrayBuffer | null = null
  if (draft.content_type === 'market_analysis') {
    try {
      imageBytes = await captureMarketChart(env, draft.symbol)
    } catch (error) {
      console.error(JSON.stringify({
        event: 'social.chart_capture_failed',
        error: error instanceof Error ? error.message : String(error),
      }))
    }
  }
  const published = await publishToBinanceSquare(
    env,
    draft.tweet_text,
    imageBytes,
    draft.account_key,
  )
  const status = published.success ? 'success' : 'failed'
  await env.DB.batch([
    env.DB
      .prepare(
        `UPDATE social_dispatches
         SET status = ?, url = ?, platform_post_id = ?, error = ?, updated_at = ? WHERE id = ?`,
      )
      .bind(status, published.url, published.postId, published.error, Date.now(), dispatch.id),
    env.DB
      .prepare('UPDATE social_drafts SET status = ?, image_key = COALESCE(?, image_key) WHERE id = ?')
      .bind(published.success ? 'published' : 'failed', published.imageUrl, draftId),
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

export function isAutoPublishSlot(minute: number): boolean {
  const firstSlot = 8 * 60
  const lastMinute = 22 * 60
  return minute >= firstSlot && minute <= lastMinute && (minute - firstSlot) % 10 === 0
}

export function isAutoPublishTimestamp(timestamp: number): boolean {
  return isAutoPublishSlot(cstMinute(timestamp))
}

export function isSocialIngestSlot(minute: number): boolean {
  return minute % 30 === 5
}

async function updateAutoRun(
  env: Env,
  slot: string,
  accountKey: BinanceSquareAccountKey,
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
       WHERE slot = ? AND account_key = ?`,
    )
    .bind(
      values.status,
      values.draftId ?? null,
      values.dispatchId ?? null,
      values.error?.slice(0, 500) ?? null,
      Date.now(),
      slot,
      accountKey,
    )
    .run()
}

async function autoCandidate(
  env: Env,
  timestamp: number,
  accountKey: BinanceSquareAccountKey,
): Promise<CreatedSocialDraft | null> {
  const row = await env.DB
    .prepare(
      `SELECT d.id, d.symbol, d.tweet_text, d.compliance_passed
       FROM social_drafts d
       WHERE d.auto_drafted = 1
         AND d.account_key = ?
         AND d.gen_style = 'default'
         AND d.compliance_passed = 1
         AND d.created_at >= ?
         AND NOT EXISTS (
           SELECT 1 FROM social_dispatches sd
           WHERE sd.draft_id = d.id AND sd.platform = 'binance_square'
             AND sd.account_key = ?
             AND sd.status = 'success'
         )
         AND NOT EXISTS (
           SELECT 1
           FROM social_drafts recent_d
           JOIN social_dispatches recent_sd ON recent_sd.draft_id = recent_d.id
           WHERE recent_d.symbol = d.symbol
             AND recent_sd.platform = 'binance_square'
             AND recent_sd.account_key = ?
             AND recent_sd.status = 'success'
             AND recent_sd.updated_at >= ?
         )
       ORDER BY d.created_at DESC
       LIMIT 1`,
    )
    .bind(
      accountKey,
      timestamp - 4 * 60 * 60_000,
      accountKey,
      accountKey,
      timestamp - SOCIAL_SYMBOL_COOLDOWN_MS,
    )
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

async function recordAutoFailure(
  env: Env,
  accountKey: BinanceSquareAccountKey,
  error: string,
): Promise<number> {
  await env.DB
    .prepare(
      `UPDATE social_automation_accounts
       SET failure_count = failure_count + 1, last_error = ?, updated_at = ?
       WHERE account_key = ?`,
    )
    .bind(error.slice(0, 500), Date.now(), accountKey)
    .run()
  const state = await env.DB
    .prepare('SELECT failure_count FROM social_automation_accounts WHERE account_key = ?')
    .bind(accountKey)
    .first<{ failure_count: number }>()
  const failures = state?.failure_count ?? 1
  if (failures >= 3) {
    await env.DB
      .prepare(
        `UPDATE social_automation_accounts
         SET enabled = 0, circuit_open = 1, updated_at = ? WHERE account_key = ?`,
      )
      .bind(Date.now(), accountKey)
      .run()
  }
  return failures
}

async function runSocialAutomation(env: Env, timestamp: number): Promise<void> {
  const minute = cstMinute(timestamp)
  const configs = await env.DB
    .prepare(
      `SELECT account_key, enabled, circuit_open, platform_checked, daily_limit,
              content_profile, slot_offset_minutes
       FROM social_automation_accounts
       ORDER BY slot_offset_minutes`,
    )
    .all<{
      account_key: BinanceSquareAccountKey
      enabled: number
      circuit_open: number
      platform_checked: number
      daily_limit: number
      content_profile: 'radar' | 'legacy_market'
      slot_offset_minutes: number
    }>()
  for (const config of configs.results) {
    const offset = config.slot_offset_minutes
    const inSlot = minute >= 8 * 60 + offset && minute <= 22 * 60 &&
      (minute - 8 * 60 - offset) % 10 === 0
    if (!inSlot || config.enabled !== 1 || config.circuit_open === 1 ||
      config.platform_checked !== 1) continue
    if ((env as Env & ExternalEnv).BINANCE_SQUARE_PUBLISH_MODE !== 'github' &&
      !binanceSquareEnabled(env, config.account_key)) continue
    await runSocialAccountAutomation(env, timestamp, config)
  }
}

async function runSocialAccountAutomation(
  env: Env,
  timestamp: number,
  config: Readonly<{
    account_key: BinanceSquareAccountKey
    daily_limit: number
    content_profile: 'radar' | 'legacy_market'
  }>,
): Promise<void> {
  const accountKey = config.account_key

  const used = await env.DB
    .prepare(
      `SELECT COUNT(*) AS count FROM social_dispatches
       WHERE source = 'auto' AND platform = 'binance_square' AND status = 'success'
         AND account_key = ?
         AND date(updated_at / 1000, 'unixepoch', '+8 hours') =
             date(? / 1000, 'unixepoch', '+8 hours')`,
    )
    .bind(accountKey, timestamp)
    .first<{ count: number }>()
  if (Number(used?.count ?? 0) >= config.daily_limit) return

  const slot = `${accountKey}:${socialSlot(timestamp)}`
  const claim = await env.DB
    .prepare(
      `INSERT OR IGNORE INTO social_auto_runs
        (slot, status, created_at, updated_at, account_key)
       VALUES (?, 'running', ?, ?, ?)`,
    )
    .bind(slot, timestamp, timestamp, accountKey)
    .run()
  if (Number(claim.meta.changes ?? 0) === 0) return

  try {
    let candidate = await autoCandidate(env, timestamp, accountKey)
    if (!candidate) {
      const dailyUsed = Number(used?.count ?? 0)
      const cycle = dailyUsed % 5
      const preferredEventTypes: readonly SocialContentType[] =
        config.content_profile === 'legacy_market'
          ? []
          : cycle === 1 || cycle === 3
          ? ['news']
          : cycle === 4
            ? ['whale', 'unlock', 'news']
            : []
      await createSocialDrafts(env, 'default', true, preferredEventTypes, accountKey)
      candidate = await autoCandidate(env, Date.now(), accountKey)
    }
    if (!candidate) {
      await updateAutoRun(env, slot, accountKey, {
        status: 'skipped',
        error: '当前暂无符合发布间隔的合规草稿，等待下一时段',
      })
      return
    }
    if (
      (env as Env & ExternalEnv).BINANCE_SQUARE_PUBLISH_MODE === 'github'
    ) {
      await wakeGithubPublisher(env)
      await Promise.all([
        updateAutoRun(env, slot, accountKey, {
          status: 'skipped',
          draftId: candidate.id,
          error: '已唤醒独立币安广场发布执行器',
        }),
        env.DB
          .prepare(
            `UPDATE social_automation_accounts
             SET failure_count = 0, last_error = NULL, updated_at = ?
             WHERE account_key = ?`,
          )
          .bind(Date.now(), accountKey)
          .run(),
      ])
      return
    }
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
      updateAutoRun(env, slot, accountKey, {
        status: 'success',
        draftId: candidate.id,
        dispatchId: result.dispatchId,
      }),
      env.DB
        .prepare(
          `UPDATE social_automation_accounts
           SET failure_count = 0, last_error = NULL, updated_at = ?
           WHERE account_key = ?`,
        )
        .bind(Date.now(), accountKey)
        .run(),
    ])
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    const failures = await recordAutoFailure(env, accountKey, message)
    await updateAutoRun(env, slot, accountKey, {
      status: 'failed',
      error: message,
    })
    console.error(JSON.stringify({
      event: 'social.auto_failed',
      accountKey,
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
  await recoverStaleSocialDispatches(env, timestamp)
  const minute = cstMinute(timestamp)
  if (env.ENVIRONMENT !== 'test' && isSocialIngestSlot(minute)) {
    await ingestSocialContent(env, timestamp)
  }
  await runSocialAutomation(env, timestamp)
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
    const row = await env.DB
      .prepare('SELECT image_key FROM social_drafts WHERE id = ?')
      .bind(Number(imageMatch[1]))
      .first<{ image_key: string | null }>()
    if (!row?.image_key?.startsWith('https://')) {
      throw new HttpError(404, '该草稿暂无配图')
    }
    const upstream = await fetch(row.image_key, { signal: AbortSignal.timeout(15_000) })
    if (!upstream.ok || !upstream.body) throw new HttpError(502, '配图读取失败')
    return new Response(upstream.body, {
      headers: {
        'content-type': upstream.headers.get('content-type') ?? 'image/png',
        'cache-control': 'private, max-age=3600',
      },
    })
  }
  return null
}
