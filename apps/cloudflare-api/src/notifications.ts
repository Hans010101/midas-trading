import { authenticate } from './auth'
import { randomToken, sha256Hex } from './crypto'
import {
  HttpError,
  jsonResponse,
  readJsonObject,
} from './http'
import {
  handleTelegramBotUpdate,
  sendTelegramWelcome,
  TELEGRAM_COMMANDS,
  telegramSend,
} from './telegram-bot'

const BIND_TTL_MS = 10 * 60 * 1_000
const TELEGRAM_WEBHOOK_ORIGIN = 'https://midas-trading-api.openclaw007.online'
const TIME_ZONES = new Set([
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Asia/Singapore',
  'Europe/London',
  'America/New_York',
  'UTC',
])

type ConfigRow = Readonly<{
  tg_chat_id: string | null
  feishu_open_id: string | null
  trade_alert_enabled: number
  price_alert_enabled: number
  weekly_report_enabled: number
  dott_digest_enabled: number
  dott_transition_enabled: number
  econ_alert_enabled: number
  econ_alert_minutes: number
  quiet_hours_enabled: number
  quiet_hours_start: number
  quiet_hours_end: number
  quiet_hours_tz: string
}>

type InAppNotificationRow = Readonly<{
  id: string
  category: string
  title: string
  body: string
  read_at: number | null
  created_at: number
}>

async function ensureConfig(db: D1Database, userId: string): Promise<void> {
  const now = Date.now()
  await db
    .prepare(
      `INSERT INTO notification_configs (user_id, created_at, updated_at)
       VALUES (?, ?, ?)
       ON CONFLICT(user_id) DO NOTHING`,
    )
    .bind(userId, now, now)
    .run()
}

async function configRow(db: D1Database, userId: string): Promise<ConfigRow> {
  await ensureConfig(db, userId)
  const row = await db
    .prepare('SELECT * FROM notification_configs WHERE user_id = ?')
    .bind(userId)
    .first<ConfigRow>()
  if (!row) throw new Error('notification config missing after initialization')
  return row
}

function serializeConfig(row: ConfigRow) {
  return {
    tg_chat_id: row.tg_chat_id,
    trade_alert_enabled: row.trade_alert_enabled === 1,
    price_alert_enabled: row.price_alert_enabled === 1,
    weekly_report_enabled: row.weekly_report_enabled === 1,
    dott_digest_enabled: row.dott_digest_enabled === 1,
    dott_transition_enabled: row.dott_transition_enabled === 1,
    econ_alert_enabled: row.econ_alert_enabled === 1,
    econ_alert_minutes: row.econ_alert_minutes,
    has_telegram: Boolean(row.tg_chat_id),
    has_feishu: Boolean(row.feishu_open_id),
    quiet_hours_enabled: row.quiet_hours_enabled === 1,
    quiet_hours_start: row.quiet_hours_start,
    quiet_hours_end: row.quiet_hours_end,
    quiet_hours_tz: row.quiet_hours_tz,
  }
}

async function getConfig(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  return jsonResponse(
    serializeConfig(await configRow(env.DB, user.id)),
    200,
    requestId,
    request.method,
  )
}

async function updateConfig(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const booleanFields = [
    'trade_alert_enabled',
    'price_alert_enabled',
    'weekly_report_enabled',
    'dott_digest_enabled',
    'dott_transition_enabled',
    'econ_alert_enabled',
    'quiet_hours_enabled',
  ] as const
  const integerFields = ['quiet_hours_start', 'quiet_hours_end'] as const
  await ensureConfig(env.DB, user.id)
  const sets: string[] = []
  const values: unknown[] = []
  for (const field of booleanFields) {
    if (body[field] === undefined) continue
    if (typeof body[field] !== 'boolean') {
      throw new HttpError(400, `${field} 必须是布尔值`)
    }
    sets.push(`${field} = ?`)
    values.push(body[field] ? 1 : 0)
  }
  for (const field of integerFields) {
    if (body[field] === undefined) continue
    const value = body[field]
    if (!Number.isSafeInteger(value) || Number(value) < 0 || Number(value) > 23) {
      throw new HttpError(400, `${field} 必须是 0 到 23 的整数`)
    }
    sets.push(`${field} = ?`)
    values.push(value)
  }
  if (body.econ_alert_minutes !== undefined) {
    const value = body.econ_alert_minutes
    if (!Number.isSafeInteger(value) || ![15, 30, 60].includes(Number(value))) {
      throw new HttpError(400, 'econ_alert_minutes 必须是 15、30 或 60')
    }
    sets.push('econ_alert_minutes = ?')
    values.push(value)
  }
  if (body.quiet_hours_tz !== undefined) {
    if (
      typeof body.quiet_hours_tz !== 'string' ||
      !TIME_ZONES.has(body.quiet_hours_tz)
    ) {
      throw new HttpError(400, 'quiet_hours_tz 不受支持')
    }
    sets.push('quiet_hours_tz = ?')
    values.push(body.quiet_hours_tz)
  }
  if (sets.length > 0) {
    sets.push('updated_at = ?')
    values.push(Date.now(), user.id)
    await env.DB
      .prepare(`UPDATE notification_configs SET ${sets.join(', ')} WHERE user_id = ?`)
      .bind(...values)
      .run()
  }
  return jsonResponse(
    serializeConfig(await configRow(env.DB, user.id)),
    200,
    requestId,
    request.method,
  )
}

export async function ensureTelegramWebhook(env: Env): Promise<void> {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_WEBHOOK_SECRET) return
  const desiredUrl = `${TELEGRAM_WEBHOOK_ORIGIN}/api/v1/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`
  const infoResponse = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/getWebhookInfo`,
    { signal: AbortSignal.timeout(10_000) },
  )
  const info = (await infoResponse.json()) as {
    ok?: boolean
    result?: { url?: string; allowed_updates?: string[] }
  }
  if (!infoResponse.ok || !info.ok) throw new Error('Telegram webhook 查询失败')
  if (
    info.result?.url === desiredUrl &&
    info.result.allowed_updates?.includes('message') &&
    info.result.allowed_updates.includes('callback_query')
  ) return

  const setResponse = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        url: desiredUrl,
        allowed_updates: ['message', 'callback_query'],
        drop_pending_updates: false,
      }),
      signal: AbortSignal.timeout(10_000),
    },
  )
  const setResult = (await setResponse.json()) as { ok?: boolean }
  if (!setResponse.ok || !setResult.ok) throw new Error('Telegram webhook 注册失败')
  const commandsResponse = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setMyCommands`,
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ commands: TELEGRAM_COMMANDS }),
      signal: AbortSignal.timeout(10_000),
    },
  )
  const commandsResult = (await commandsResponse.json()) as { ok?: boolean }
  if (!commandsResponse.ok || !commandsResult.ok) {
    throw new Error('Telegram 指令菜单注册失败')
  }
  console.log(JSON.stringify({
    event: 'telegram.webhook_migrated',
    bot: env.TELEGRAM_BOT_USERNAME,
    from: info.result?.url ? new URL(info.result.url).hostname : null,
    to: new URL(desiredUrl).hostname,
  }))
}

async function feishuTenantToken(env: Env): Promise<string> {
  const response = await fetch(
    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
    {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({
        app_id: env.FEISHU_APP_ID,
        app_secret: env.FEISHU_APP_SECRET,
      }),
      signal: AbortSignal.timeout(10_000),
    },
  )
  const body = (await response.json()) as {
    code?: number
    tenant_access_token?: string
  }
  if (!response.ok || body.code !== 0 || !body.tenant_access_token) {
    throw new Error('飞书 tenant token 获取失败')
  }
  return body.tenant_access_token
}

async function feishuSend(env: Env, openId: string, text: string): Promise<void> {
  const token = await feishuTenantToken(env)
  const url = new URL('https://open.feishu.cn/open-apis/im/v1/messages')
  url.searchParams.set('receive_id_type', 'open_id')
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      receive_id: openId,
      msg_type: 'text',
      content: JSON.stringify({ text }),
    }),
    signal: AbortSignal.timeout(10_000),
  })
  if (!response.ok) throw new Error(`飞书 HTTP ${response.status}`)
}

function isQuietHour(row: ConfigRow, now: number): boolean {
  if (row.quiet_hours_enabled !== 1) return false
  const hour = Number(
    new Intl.DateTimeFormat('en-US', {
      timeZone: row.quiet_hours_tz,
      hour: '2-digit',
      hourCycle: 'h23',
    }).format(new Date(now)),
  )
  return row.quiet_hours_start === row.quiet_hours_end
    ? true
    : row.quiet_hours_start < row.quiet_hours_end
      ? hour >= row.quiet_hours_start && hour < row.quiet_hours_end
      : hour >= row.quiet_hours_start || hour < row.quiet_hours_end
}

export async function deliverUserNotification(
  env: Env,
  input: Readonly<{
    userId: string
    category: string
    title: string
    body: string
    dedupeKey?: string
  }>,
): Promise<string> {
  const now = Date.now()
  const notificationId = input.dedupeKey
    ? `dedupe:${input.dedupeKey}`
    : crypto.randomUUID()
  const inserted = await env.DB
    .prepare(
      `INSERT INTO in_app_notifications
        (id, user_id, category, title, body, created_at)
       VALUES (?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO NOTHING`,
    )
    .bind(
      notificationId,
      input.userId,
      input.category,
      input.title.slice(0, 160),
      input.body.slice(0, 2_000),
      now,
    )
    .run()
  if (inserted.meta.changes === 0) return notificationId

  const config = await configRow(env.DB, input.userId)
  const deliveries: Array<Readonly<{
    channel: 'in_app' | 'telegram' | 'feishu'
    enabled: boolean
    send?: () => Promise<void>
  }>> = [{ channel: 'in_app', enabled: true }]
  deliveries.push(config.tg_chat_id
    ? {
        channel: 'telegram',
        enabled: !isQuietHour(config, now),
        send: () => telegramSend(env, config.tg_chat_id!, `${input.title}\n${input.body}`),
      }
    : { channel: 'telegram', enabled: false })
  deliveries.push(config.feishu_open_id
    ? {
        channel: 'feishu',
        enabled: !isQuietHour(config, now),
        send: () => feishuSend(env, config.feishu_open_id!, `${input.title}\n${input.body}`),
      }
    : { channel: 'feishu', enabled: false })
  for (const delivery of deliveries) {
    let status: 'sent' | 'failed' | 'skipped' = delivery.enabled ? 'sent' : 'skipped'
    let error: string | null = null
    if (delivery.enabled && delivery.send) {
      try {
        await delivery.send()
      } catch (cause) {
        status = 'failed'
        error = cause instanceof Error ? cause.message : String(cause)
      }
    }
    await env.DB
      .prepare(
        `INSERT INTO notification_deliveries
          (id, notification_id, user_id, channel, status, attempts, error,
           sent_at, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)` ,
      )
      .bind(
        crypto.randomUUID(),
        notificationId,
        input.userId,
        delivery.channel,
        status,
        delivery.enabled ? 1 : 0,
        error,
        status === 'sent' ? now : null,
        now,
        now,
      )
      .run()
  }
  return notificationId
}

async function sendTest(request: Request, env: Env, requestId: string) {
  const { user } = await authenticate(request, env)
  const row = await configRow(env.DB, user.id)
  const channel = new URL(request.url).searchParams.get('channel') ?? 'telegram'
  try {
    if (channel === 'telegram') {
      if (!row.tg_chat_id) throw new HttpError(400, '尚未绑定 Telegram')
      await telegramSend(env, row.tg_chat_id, 'Midas Trading 测试通知：独立通道配置成功。')
    } else if (channel === 'feishu') {
      if (!row.feishu_open_id) throw new HttpError(400, '尚未绑定飞书')
      await feishuSend(env, row.feishu_open_id, 'Midas Trading 测试通知：独立通道配置成功。')
    } else {
      throw new HttpError(400, 'channel 不受支持')
    }
    return jsonResponse({ channel, ok: true, error: null }, 200, requestId, request.method)
  } catch (error) {
    if (error instanceof HttpError) throw error
    return jsonResponse(
      { channel, ok: false, error: error instanceof Error ? error.message : '发送失败' },
      200,
      requestId,
      request.method,
    )
  }
}

async function createBindToken(
  request: Request,
  env: Env,
  requestId: string,
  channel: 'telegram' | 'feishu',
) {
  const { user } = await authenticate(request, env)
  if (channel === 'telegram' && !env.TELEGRAM_BOT_TOKEN) {
    throw new HttpError(503, 'Telegram 机器人尚未配置')
  }
  if (channel === 'feishu' && (!env.FEISHU_APP_ID || !env.FEISHU_APP_SECRET)) {
    throw new HttpError(503, '飞书机器人尚未配置')
  }
  const token = randomToken(24)
  const now = Date.now()
  await env.DB
    .prepare(
      `INSERT INTO notification_bind_tokens
        (token_hash, user_id, channel, expires_at, created_at)
       VALUES (?, ?, ?, ?, ?)`,
    )
    .bind(await sha256Hex(token), user.id, channel, now + BIND_TTL_MS, now)
    .run()
  return jsonResponse(
    channel === 'telegram'
      ? {
          token,
          deep_link: env.TELEGRAM_BOT_USERNAME
            ? `https://t.me/${env.TELEGRAM_BOT_USERNAME}?start=${token}`
            : null,
          expires_in: BIND_TTL_MS / 1_000,
        }
      : { token, expires_in: BIND_TTL_MS / 1_000, app_id: env.FEISHU_APP_ID },
    200,
    requestId,
    request.method,
  )
}

async function consumeBindToken(
  env: Env,
  channel: 'telegram' | 'feishu',
  token: string,
  externalId: string,
): Promise<boolean> {
  const now = Date.now()
  const tokenHash = await sha256Hex(token)
  const row = await env.DB
    .prepare(
      `SELECT user_id FROM notification_bind_tokens
       WHERE token_hash = ? AND channel = ? AND used_at IS NULL AND expires_at > ?`,
    )
    .bind(tokenHash, channel, now)
    .first<{ user_id: string }>()
  if (!row) return false
  await ensureConfig(env.DB, row.user_id)
  await env.DB.batch([
    env.DB
      .prepare(
        `UPDATE notification_bind_tokens SET used_at = ?
         WHERE token_hash = ? AND used_at IS NULL`,
      )
      .bind(now, tokenHash),
    env.DB
      .prepare(
        `UPDATE notification_configs SET
           ${channel === 'telegram' ? 'tg_chat_id' : 'feishu_open_id'} = ?,
           updated_at = ?
         WHERE user_id = ?`,
      )
      .bind(externalId, now, row.user_id),
  ])
  return true
}

async function telegramWebhook(request: Request, env: Env, requestId: string) {
  const body = await readJsonObject(request)
  const message = body.message as
    | { text?: unknown; chat?: { id?: unknown } }
    | undefined
  const match =
    typeof message?.text === 'string'
      ? message.text.match(/^\/start\s+([A-Za-z0-9_-]{20,80})$/u)
      : null
  const chatId = message?.chat?.id
  if (match?.[1] && (typeof chatId === 'number' || typeof chatId === 'string')) {
    const ok = await consumeBindToken(env, 'telegram', match[1], String(chatId))
    if (ok) await sendTelegramWelcome(env, String(chatId), true)
    else await telegramSend(env, String(chatId), '绑定码无效或已过期，请重新生成。')
  } else {
    await handleTelegramBotUpdate(env, body)
  }
  return jsonResponse({ ok: true }, 200, requestId, request.method)
}

async function decryptFeishuEvent(body: Record<string, unknown>, env: Env) {
  if (typeof body.encrypt !== 'string') return body
  const encryptKey = (env as Env & { FEISHU_ENCRYPT_KEY?: string })
    .FEISHU_ENCRYPT_KEY
  if (!encryptKey) throw new HttpError(403, '飞书事件加密密钥未配置')
  try {
    const key = await crypto.subtle.importKey(
      'raw',
      await crypto.subtle.digest('SHA-256', new TextEncoder().encode(encryptKey)),
      { name: 'AES-CBC' },
      false,
      ['decrypt'],
    )
    const encrypted = Uint8Array.from(atob(body.encrypt), (char) =>
      char.charCodeAt(0),
    )
    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-CBC', iv: encrypted.slice(0, 16) },
      key,
      encrypted.slice(16),
    )
    return JSON.parse(new TextDecoder().decode(decrypted)) as Record<
      string,
      unknown
    >
  } catch {
    throw new HttpError(403, '飞书事件解密失败')
  }
}

async function feishuEvents(request: Request, env: Env, requestId: string) {
  const body = await decryptFeishuEvent(await readJsonObject(request), env)
  if (typeof body.challenge === 'string') {
    if (body.token !== env.FEISHU_VERIFICATION_TOKEN) {
      throw new HttpError(403, '飞书验证 Token 不匹配')
    }
    return jsonResponse({ challenge: body.challenge }, 200, requestId, request.method)
  }
  const header = body.header as { token?: unknown } | undefined
  if (header?.token !== env.FEISHU_VERIFICATION_TOKEN) {
    throw new HttpError(403, '飞书验证 Token 不匹配')
  }
  const event = body.event as {
    message?: { content?: unknown }
    sender?: { sender_id?: { open_id?: unknown } }
  } | undefined
  let text = ''
  if (typeof event?.message?.content === 'string') {
    try {
      const content = JSON.parse(event.message.content) as { text?: unknown }
      if (typeof content.text === 'string') text = content.text
    } catch {
      text = ''
    }
  }
  const match = text.match(/(?:\/bind\s+)?([A-Za-z0-9_-]{20,80})/u)
  const openId = event?.sender?.sender_id?.open_id
  if (match?.[1] && typeof openId === 'string') {
    const ok = await consumeBindToken(env, 'feishu', match[1], openId)
    await feishuSend(
      env,
      openId,
      ok ? 'Midas Trading 绑定成功。' : '绑定码无效或已过期，请重新生成。',
    )
  }
  return jsonResponse({ code: 0 }, 200, requestId, request.method)
}

async function unbind(
  request: Request,
  env: Env,
  requestId: string,
  channel: 'telegram' | 'feishu',
) {
  const { user } = await authenticate(request, env)
  await ensureConfig(env.DB, user.id)
  await env.DB
    .prepare(
      `UPDATE notification_configs SET
        ${channel === 'telegram' ? 'tg_chat_id' : 'feishu_open_id'} = NULL,
        updated_at = ? WHERE user_id = ?`,
    )
    .bind(Date.now(), user.id)
    .run()
  return jsonResponse({}, 204, requestId, request.method)
}

async function listInAppNotifications(
  request: Request,
  env: Env,
  requestId: string,
) {
  const { user } = await authenticate(request, env)
  const url = new URL(request.url)
  const unreadOnly = url.searchParams.get('unread_only') === 'true'
  const rows = await env.DB
    .prepare(
      `SELECT id, category, title, body, read_at, created_at
       FROM in_app_notifications
       WHERE user_id = ? ${unreadOnly ? 'AND read_at IS NULL' : ''}
       ORDER BY created_at DESC
       LIMIT 50`,
    )
    .bind(user.id)
    .all<InAppNotificationRow>()
  const unread = await env.DB
    .prepare(
      `SELECT COUNT(*) AS count
       FROM in_app_notifications
       WHERE user_id = ? AND read_at IS NULL`,
    )
    .bind(user.id)
    .first<{ count: number }>()
  return jsonResponse(
    {
      items: rows.results.map((row) => ({
        id: row.id,
        category: row.category,
        title: row.title,
        body: row.body,
        read_at: row.read_at,
        created_at: row.created_at,
      })),
      unread_count: unread?.count ?? 0,
    },
    200,
    requestId,
    request.method,
  )
}

async function markInAppNotificationRead(
  request: Request,
  env: Env,
  requestId: string,
  notificationId: string,
) {
  const { user } = await authenticate(request, env)
  const result = await env.DB
    .prepare(
      `UPDATE in_app_notifications
       SET read_at = COALESCE(read_at, ?)
       WHERE id = ? AND user_id = ?`,
    )
    .bind(Date.now(), notificationId, user.id)
    .run()
  if (result.meta.changes === 0) {
    throw new HttpError(404, '站内通知不存在')
  }
  return jsonResponse({ ok: true }, 200, requestId, request.method)
}

async function markAllInAppNotificationsRead(
  request: Request,
  env: Env,
  requestId: string,
) {
  const { user } = await authenticate(request, env)
  const result = await env.DB
    .prepare(
      `UPDATE in_app_notifications
       SET read_at = ?
       WHERE user_id = ? AND read_at IS NULL`,
    )
    .bind(Date.now(), user.id)
    .run()
  return jsonResponse(
    { ok: true, updated: result.meta.changes },
    200,
    requestId,
    request.method,
  )
}

export async function handleNotificationRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`
  if (route === 'GET /api/v1/notifications/config') return getConfig(request, env, requestId)
  if (route === 'PUT /api/v1/notifications/config') return updateConfig(request, env, requestId)
  if (route === 'POST /api/v1/notifications/test') return sendTest(request, env, requestId)
  if (route === 'GET /api/v1/notifications/inbox') {
    return listInAppNotifications(request, env, requestId)
  }
  if (route === 'POST /api/v1/notifications/inbox/read-all') {
    return markAllInAppNotificationsRead(request, env, requestId)
  }
  const readMatch = path.match(/^\/api\/v1\/notifications\/inbox\/([^/]+)\/read$/u)
  if (request.method === 'POST' && readMatch?.[1]) {
    return markInAppNotificationRead(
      request,
      env,
      requestId,
      decodeURIComponent(readMatch[1]),
    )
  }
  if (route === 'POST /api/v1/telegram/bind-token') {
    return createBindToken(request, env, requestId, 'telegram')
  }
  if (route === 'POST /api/v1/telegram/unbind') {
    return unbind(request, env, requestId, 'telegram')
  }
  if (
    request.method === 'POST' &&
    path === `/api/v1/telegram/webhook/${env.TELEGRAM_WEBHOOK_SECRET}`
  ) {
    return telegramWebhook(request, env, requestId)
  }
  if (route === 'POST /api/v1/feishu/bind-token') {
    return createBindToken(request, env, requestId, 'feishu')
  }
  if (route === 'POST /api/v1/feishu/unbind') {
    return unbind(request, env, requestId, 'feishu')
  }
  if (route === 'POST /api/v1/feishu/events') {
    return feishuEvents(request, env, requestId)
  }
  return path.startsWith('/api/v1/notifications/') ||
    path.startsWith('/api/v1/telegram/') ||
    path.startsWith('/api/v1/feishu/')
    ? jsonResponse({ detail: 'Route not found' }, 404, requestId, request.method)
    : null
}
