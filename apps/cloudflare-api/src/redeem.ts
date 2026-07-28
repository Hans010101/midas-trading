import { authenticate } from './auth'
import { COMMERCIAL_MEMBERSHIP_ENABLED } from './features'
import {
  HttpError,
  jsonResponse,
  optionalString,
  readJsonObject,
  requireString,
} from './http'

const PERIOD_DAYS = {
  month: 30,
  quarter: 90,
  year: 365,
} as const
const MAX_BATCH = 100
const DAY_MS = 24 * 60 * 60 * 1_000
const CODE_ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'

type RedeemPeriod = keyof typeof PERIOD_DAYS

type RedeemCodeRow = Readonly<{
  code: string
  period: string
  days: number
  note: string | null
  created_at: number
  expires_at: number
  redeemed_by: string | null
  redeemed_at: number | null
}>

function generateCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12))
  return Array.from(bytes, (byte) => CODE_ALPHABET[byte & 31]).join('')
}

async function requireAdmin(
  request: Request,
  env: Env,
): Promise<string> {
  const { user } = await authenticate(request, env)
  if (user.role !== 'admin') throw new HttpError(403, '需要管理员权限')
  return user.id
}

function parsePeriod(value: unknown): RedeemPeriod {
  if (value === 'month' || value === 'quarter' || value === 'year') {
    return value
  }
  throw new HttpError(422, 'period 仅支持 month、quarter 或 year')
}

async function generateCodes(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const adminId = await requireAdmin(request, env)
  const body = await readJsonObject(request)
  const period = parsePeriod(body.period)
  const count = body.count
  if (
    typeof count !== 'number' ||
    !Number.isSafeInteger(count) ||
    count < 1 ||
    count > MAX_BATCH
  ) {
    throw new HttpError(422, `count 必须是 1 到 ${MAX_BATCH} 的整数`)
  }
  const note = optionalString(body, 'note', 128)
  const timestamp = Date.now()
  const expiresAt = timestamp + 365 * DAY_MS
  const days = PERIOD_DAYS[period]

  for (let attempt = 0; attempt < 5; attempt += 1) {
    const codes = Array.from({ length: count }, generateCode)
    try {
      await env.DB.batch(
        codes.map((code) =>
          env.DB
            .prepare(
              `INSERT INTO redeem_codes
                (id, code, period, days, note, created_by, created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
            )
            .bind(
              crypto.randomUUID(),
              code,
              period,
              days,
              note,
              adminId,
              timestamp,
              expiresAt,
            ),
        ),
      )
      return jsonResponse(
        { codes, period, days },
        200,
        requestId,
        request.method,
      )
    } catch (error) {
      if (
        attempt === 4 ||
        !(error instanceof Error) ||
        !error.message.includes('UNIQUE constraint failed')
      ) {
        throw error
      }
    }
  }
  throw new Error('redeem code collision retry exhausted')
}

function positiveIntegerParam(
  params: URLSearchParams,
  key: string,
  fallback: number,
  max?: number,
): number {
  const raw = params.get(key)
  if (raw === null) return fallback
  const value = Number(raw)
  if (
    !Number.isSafeInteger(value) ||
    value < 1 ||
    (max !== undefined && value > max)
  ) {
    throw new HttpError(422, `${key} 格式无效`)
  }
  return value
}

async function listCodes(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  await requireAdmin(request, env)
  const params = new URL(request.url).searchParams
  const page = positiveIntegerParam(params, 'page', 1)
  const pageSize = positiveIntegerParam(params, 'page_size', 20, 100)
  const [rows, count] = await Promise.all([
    env.DB
      .prepare(
        `SELECT
           r.code, r.period, r.days, r.note, r.created_at, r.expires_at,
           r.redeemed_by, r.redeemed_at, u.email AS redeemed_by_email
         FROM redeem_codes r
         LEFT JOIN users u ON u.id = r.redeemed_by
         ORDER BY r.created_at DESC, r.id DESC
         LIMIT ? OFFSET ?`,
      )
      .bind(pageSize, (page - 1) * pageSize)
      .all<RedeemCodeRow & { redeemed_by_email: string | null }>(),
    env.DB
      .prepare('SELECT COUNT(*) AS total FROM redeem_codes')
      .first<{ total: number }>(),
  ])
  const timestamp = Date.now()
  return jsonResponse(
    {
      items: rows.results.map((row) => ({
        code: row.code,
        period: row.period,
        status:
          row.redeemed_at !== null
            ? 'redeemed'
            : row.expires_at <= timestamp
              ? 'expired'
              : 'unused',
        note: row.note,
        redeemed_by_email: row.redeemed_by_email,
        created_at: new Date(row.created_at).toISOString(),
        expires_at: new Date(row.expires_at).toISOString(),
      })),
      total: count?.total ?? 0,
      page,
      page_size: pageSize,
    },
    200,
    requestId,
    request.method,
  )
}

function redeemError(
  request: Request,
  requestId: string,
  status: number,
  error: string,
  message: string,
): Response {
  return jsonResponse(
    { detail: { error, message } },
    status,
    requestId,
    request.method,
  )
}

async function redeemCode(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const code = requireString(body, 'code', { min: 1, max: 32 })
    .trim()
    .toUpperCase()
  const row = await env.DB
    .prepare(
      `SELECT
         code, period, days, note, created_at, expires_at,
         redeemed_by, redeemed_at
       FROM redeem_codes
       WHERE code = ?`,
    )
    .bind(code)
    .first<RedeemCodeRow>()
  if (!row) {
    return redeemError(
      request,
      requestId,
      404,
      'not_found',
      '兑换码不存在',
    )
  }
  if (row.redeemed_at !== null) {
    return redeemError(
      request,
      requestId,
      409,
      'already_used',
      '兑换码已被使用',
    )
  }
  const timestamp = Date.now()
  if (row.expires_at <= timestamp) {
    return redeemError(
      request,
      requestId,
      410,
      'expired',
      '兑换码已过期',
    )
  }

  const claimId = crypto.randomUUID()
  const results = await env.DB.batch([
    env.DB
      .prepare(
        `UPDATE redeem_codes
         SET redeemed_by = ?, redeemed_at = ?, redemption_claim_id = ?
         WHERE code = ? AND redeemed_by IS NULL AND expires_at > ?`,
      )
      .bind(user.id, timestamp, claimId, code, timestamp),
    env.DB
      .prepare(
        `UPDATE users
         SET subscription_expires_at =
               CASE
                 WHEN subscription_expires_at IS NULL
                   OR subscription_expires_at < ?
                 THEN ?
                 ELSE subscription_expires_at + ?
               END,
             updated_at = ?
         WHERE id = ?
           AND EXISTS (
             SELECT 1
             FROM redeem_codes
             WHERE redemption_claim_id = ?
           )`,
      )
      .bind(
        timestamp,
        timestamp + row.days * DAY_MS,
        row.days * DAY_MS,
        timestamp,
        user.id,
        claimId,
      ),
  ])
  if (results[0]?.meta.changes !== 1) {
    return redeemError(
      request,
      requestId,
      409,
      'already_used',
      '兑换码已被使用',
    )
  }
  const account = await env.DB
    .prepare('SELECT subscription_expires_at FROM users WHERE id = ?')
    .bind(user.id)
    .first<{ subscription_expires_at: number | null }>()
  return jsonResponse(
    {
      plan: 'pro',
      days_added: row.days,
      expires_at:
        account?.subscription_expires_at !== null &&
        account?.subscription_expires_at !== undefined
          ? new Date(account.subscription_expires_at).toISOString()
          : null,
    },
    200,
    requestId,
    request.method,
  )
}

export async function handleRedeemRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  if (
    !COMMERCIAL_MEMBERSHIP_ENABLED &&
    (path === '/api/v1/redeem' ||
      path === '/api/v1/admin/redeem-codes')
  ) {
    return jsonResponse(
      { detail: 'Route not found' },
      404,
      requestId,
      request.method,
    )
  }
  const route = `${request.method} ${path}`
  switch (route) {
    case 'POST /api/v1/admin/redeem-codes':
      return generateCodes(request, env, requestId)
    case 'GET /api/v1/admin/redeem-codes':
      return listCodes(request, env, requestId)
    case 'POST /api/v1/redeem':
      return redeemCode(request, env, requestId)
    default:
      return path === '/api/v1/redeem' ||
        path === '/api/v1/admin/redeem-codes'
        ? jsonResponse(
            { detail: 'Method not allowed' },
            405,
            requestId,
            request.method,
          )
        : null
  }
}
