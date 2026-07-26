import { authenticate } from './auth'
import {
  HttpError,
  jsonResponse,
  readJsonObject,
  requireString,
} from './http'

const INDICATOR_COLUMNS = {
  bollinger: 'indicator_bollinger',
  chan: 'indicator_chan',
  day_trade: 'indicator_day_trade',
} as const

type IndicatorKey = keyof typeof INDICATOR_COLUMNS

type PreferenceRow = Readonly<{
  indicator_bollinger: number
  indicator_chan: number
  indicator_day_trade: number
}>

function indicatorOutput(row: PreferenceRow) {
  return {
    bollinger: row.indicator_bollinger === 1,
    chan: row.indicator_chan === 1,
    day_trade: row.indicator_day_trade === 1,
  }
}

async function readPreferences(
  db: D1Database,
  userId: string,
): Promise<PreferenceRow> {
  const row = await db
    .prepare(
      `SELECT indicator_bollinger, indicator_chan, indicator_day_trade
       FROM users
       WHERE id = ?`,
    )
    .bind(userId)
    .first<PreferenceRow>()
  if (!row) throw new HttpError(404, '用户不存在')
  return row
}

async function setAvatar(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const avatarId = body.avatar_id
  if (
    typeof avatarId !== 'number' ||
    !Number.isSafeInteger(avatarId) ||
    avatarId < 0 ||
    avatarId > 16
  ) {
    throw new HttpError(422, 'avatar_id 必须是 0 到 16 的整数')
  }
  const stored = avatarId === 0 ? null : avatarId
  await env.DB
    .prepare('UPDATE users SET avatar_id = ?, updated_at = ? WHERE id = ?')
    .bind(stored, Date.now(), user.id)
    .run()
  return jsonResponse(
    { avatar_id: stored },
    200,
    requestId,
    request.method,
  )
}

async function setLanguage(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const language = requireString(body, 'language', { min: 2, max: 2 })
  if (language !== 'zh' && language !== 'en') {
    throw new HttpError(422, 'language 仅支持 zh 或 en')
  }
  await env.DB
    .prepare('UPDATE users SET language_pref = ?, updated_at = ? WHERE id = ?')
    .bind(language, Date.now(), user.id)
    .run()
  return jsonResponse(
    { language },
    200,
    requestId,
    request.method,
  )
}

async function getIndicatorPreferences(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  return jsonResponse(
    indicatorOutput(await readPreferences(env.DB, user.id)),
    200,
    requestId,
    request.method,
  )
}

async function updateIndicatorPreferences(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const body = await readJsonObject(request)
  const updates: Array<readonly [IndicatorKey, boolean]> = []
  for (const key of Object.keys(INDICATOR_COLUMNS) as IndicatorKey[]) {
    const value = body[key]
    if (value === undefined || value === null) continue
    if (typeof value !== 'boolean') {
      throw new HttpError(422, `${key} 必须是布尔值`)
    }
    updates.push([key, value])
  }

  if (updates.length > 0) {
    const assignments = updates
      .map(([key]) => `${INDICATOR_COLUMNS[key]} = ?`)
      .join(', ')
    await env.DB
      .prepare(
        `UPDATE users
         SET ${assignments}, updated_at = ?
         WHERE id = ?`,
      )
      .bind(
        ...updates.map(([, value]) => (value ? 1 : 0)),
        Date.now(),
        user.id,
      )
      .run()
  }

  return jsonResponse(
    indicatorOutput(await readPreferences(env.DB, user.id)),
    200,
    requestId,
    request.method,
  )
}

export async function handleProfileRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`
  switch (route) {
    case 'PATCH /api/v1/user/avatar':
      return setAvatar(request, env, requestId)
    case 'PATCH /api/v1/user/language':
      return setLanguage(request, env, requestId)
    case 'GET /api/v1/user/indicator-prefs':
      return getIndicatorPreferences(request, env, requestId)
    case 'PATCH /api/v1/user/indicator-prefs':
      return updateIndicatorPreferences(request, env, requestId)
    default:
      return path.startsWith('/api/v1/user/')
        ? jsonResponse(
            { detail: 'Route not found' },
            404,
            requestId,
            request.method,
          )
        : null
  }
}
