import { authenticate } from './auth'
import { COMMERCIAL_MEMBERSHIP_ENABLED } from './features'
import { getOrCreateInviteCode, INVITE_DAYS } from './growth'
import { jsonResponse } from './http'

// Membership billing is paused. Keep the historical subscription fields and
// payment code intact, while every authenticated account receives the former
// full-access limits.
const REGISTERED_QUOTAS = { diagnose: 300, backtest: 150 } as const

function usageMonth(timestamp = new Date()): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Singapore',
    year: 'numeric',
    month: '2-digit',
  }).formatToParts(timestamp)
  const year = parts.find((part) => part.type === 'year')?.value
  const month = parts.find((part) => part.type === 'month')?.value
  if (!year || !month) throw new Error('failed to calculate quota month')
  return `${year}${month}`
}

function quotaResetAt(timestamp = new Date()): string {
  const month = usageMonth(timestamp)
  const yearNumber = Number(month.slice(0, 4))
  const monthNumber = Number(month.slice(4, 6))
  const nextYear = monthNumber === 12 ? yearNumber + 1 : yearNumber
  const nextMonth = monthNumber === 12 ? 1 : monthNumber + 1
  return `${String(nextYear).padStart(4, '0')}-${String(nextMonth).padStart(2, '0')}-01T00:00:00+08:00`
}

async function quotaMe(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const timestamp = Date.now()
  const usage = await env.DB
    .prepare(
      `SELECT feature, used
       FROM quota_usage
       WHERE user_id = ? AND usage_month = ?`,
    )
    .bind(user.id, usageMonth(new Date(timestamp)))
    .all<{ feature: string; used: number }>()
  const usedByFeature = Object.fromEntries(
    usage.results.map((row) => [row.feature, row.used]),
  )
  return jsonResponse(
    {
      plan: 'registered',
      plan_expires_at: null,
      items: (['diagnose', 'backtest'] as const).map((feature) => ({
        feature,
        limit: REGISTERED_QUOTAS[feature],
        used: usedByFeature[feature] ?? 0,
      })),
      reset_at: quotaResetAt(new Date(timestamp)),
    },
    200,
    requestId,
    request.method,
  )
}

async function inviteMe(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const code = await getOrCreateInviteCode(env.DB, user.id)
  const stats = await env.DB
    .prepare(
      `SELECT
         COUNT(*) AS invited_count,
         SUM(CASE WHEN rewarded_at IS NOT NULL THEN 1 ELSE 0 END)
           AS rewarded_count
       FROM invitations
       WHERE inviter_id = ?`,
    )
    .bind(user.id)
    .first<{ invited_count: number; rewarded_count: number | null }>()
  const rewardedCount = stats?.rewarded_count ?? 0
  return jsonResponse(
    {
      code,
      invite_url: `${env.PUBLIC_WEB_URL.replace(/\/$/u, '')}/register?ref=${code}`,
      invited_count: stats?.invited_count ?? 0,
      rewarded_count: rewardedCount,
      earned_days: rewardedCount * INVITE_DAYS,
    },
    200,
    requestId,
    request.method,
  )
}

export async function handleAccountRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`
  switch (route) {
    case 'GET /api/v1/quota/me':
      return quotaMe(request, env, requestId)
    case 'GET /api/v1/invite/me':
      return COMMERCIAL_MEMBERSHIP_ENABLED
        ? inviteMe(request, env, requestId)
        : jsonResponse(
            { detail: 'Route not found' },
            404,
            requestId,
            request.method,
          )
    default:
      return path.startsWith('/api/v1/quota/') ||
        path.startsWith('/api/v1/invite/')
        ? jsonResponse(
            { detail: 'Route not found' },
            404,
            requestId,
            request.method,
          )
        : null
  }
}
