import {
  base64UrlEncode,
  hmacSha256,
  randomToken,
  sha256Hex,
} from './crypto'
import { isLockedAdminEmail, roleForEmail } from './admin-policy'
import { sendVerificationEmail } from './email'
import { COMMERCIAL_MEMBERSHIP_ENABLED } from './features'
import { verifyGoogleIdToken } from './google'
import {
  activateVerifiedGrowth,
  attributeInviteStatement,
} from './growth'
import {
  HttpError,
  bearerToken,
  jsonResponse,
  normalizeEmail,
  optionalString,
  readJsonObject,
  requireString,
} from './http'
import { hashPassword, verifyPassword } from './password'
import { checkSmsCode, normalizeChinaMobile, sendSmsCode } from './sms'

const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1_000
const VERIFICATION_TTL_MS = 24 * 60 * 60 * 1_000
const MAX_ACTIVE_SESSIONS = 5
const SMS_CODE_TTL_MS = 5 * 60 * 1_000
const SMS_COOLDOWN_MS = 60 * 1_000
const SMS_DAY_MS = 24 * 60 * 60 * 1_000
const SMS_MAX_PHONE_PER_DAY = 10
const SMS_MAX_IP_PER_DAY = 30
const SMS_MAX_ATTEMPTS = 5
const SMS_ONLY_PASSWORD_HASH = 'sms-only'

type UserRow = Readonly<{
  id: string
  email: string
  password_hash: string | null
  google_sub: string | null
  display_name: string | null
  avatar_url: string | null
  role: string
  banned_at: number | null
  age_confirmed: number
  email_verified_at: number | null
  phone_e164: string | null
  phone_verified_at: number | null
}>

export type AuthenticatedUser = Readonly<{
  sessionId: string
  user: UserRow
}>

function nowMs(): number {
  return Date.now()
}

function publicIdentity(user: UserRow): string {
  return user.phone_e164 ?? user.email
}

function smsAccountEmail(phoneE164: string): string {
  return `sms+${phoneE164.slice(1)}@accounts.invalid`
}

function userAgent(request: Request): string | null {
  return request.headers.get('user-agent')?.slice(0, 500) ?? null
}

async function requestIpHash(
  request: Request,
  pepper: string,
): Promise<string | null> {
  const ip = request.headers.get('cf-connecting-ip')
  if (!ip) return null
  return base64UrlEncode(await hmacSha256(pepper, ip))
}

function authEventStatement(
  db: D1Database,
  values: Readonly<{
    userId: string | null
    eventType: string
    requestId: string
    ipHash: string | null
    userAgent: string | null
    metadata?: Readonly<Record<string, unknown>>
    createdAt: number
  }>,
): D1PreparedStatement {
  return db
    .prepare(
      `INSERT INTO auth_events
        (id, user_id, event_type, request_id, ip_hash, user_agent, metadata_json, created_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(
      crypto.randomUUID(),
      values.userId,
      values.eventType,
      values.requestId,
      values.ipHash,
      values.userAgent,
      JSON.stringify(values.metadata ?? {}),
      values.createdAt,
    )
}

async function findUserByEmail(
  db: D1Database,
  email: string,
): Promise<UserRow | null> {
  const whereClause = isLockedAdminEmail(email)
    ? `REPLACE(SUBSTR(LOWER(email), 1, INSTR(email, '@') - 1), '.', '') = ?
       AND SUBSTR(LOWER(email), INSTR(email, '@') + 1) IN ('gmail.com', 'googlemail.com')`
    : 'email = ?'
  return db
    .prepare(
      `SELECT id, email, password_hash, google_sub, display_name, avatar_url,
              role, banned_at, age_confirmed, email_verified_at,
              phone_e164, phone_verified_at
       FROM users
       WHERE ${whereClause}`,
    )
    .bind(isLockedAdminEmail(email) ? 'hanspan007' : email)
    .first<UserRow>()
}

async function findUserByPhone(
  db: D1Database,
  phoneE164: string,
): Promise<UserRow | null> {
  return db
    .prepare(
      `SELECT id, email, password_hash, google_sub, display_name, avatar_url,
              role, banned_at, age_confirmed, email_verified_at,
              phone_e164, phone_verified_at
       FROM users
       WHERE phone_e164 = ?`,
    )
    .bind(phoneE164)
    .first<UserRow>()
}

async function issueSession(
  env: Env,
  user: UserRow,
  request: Request,
  requestId: string,
  eventType: string,
): Promise<string> {
  const token = randomToken(32)
  const tokenHash = await sha256Hex(token)
  const timestamp = nowMs()
  const ipHash = await requestIpHash(request, env.PASSWORD_PEPPER)
  const sessionId = crypto.randomUUID()

  await env.DB.batch([
    env.DB
      .prepare(
        `INSERT INTO sessions
          (id, user_id, token_hash, expires_at, last_seen_at, user_agent, ip_hash, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        sessionId,
        user.id,
        tokenHash,
        timestamp + SESSION_TTL_MS,
        timestamp,
        userAgent(request),
        ipHash,
        timestamp,
      ),
    env.DB
      .prepare(
        `UPDATE sessions
         SET revoked_at = ?
         WHERE user_id = ?
           AND revoked_at IS NULL
           AND id NOT IN (
             SELECT id
             FROM sessions
             WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ?
             ORDER BY last_seen_at DESC
             LIMIT ?
           )`,
      )
      .bind(
        timestamp,
        user.id,
        user.id,
        timestamp,
        MAX_ACTIVE_SESSIONS,
      ),
    env.DB
      .prepare(
        'UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?',
      )
      .bind(timestamp, timestamp, user.id),
    authEventStatement(env.DB, {
      userId: user.id,
      eventType,
      requestId,
      ipHash,
      userAgent: userAgent(request),
      createdAt: timestamp,
    }),
  ])

  return token
}

export async function authenticate(
  request: Request,
  env: Env,
): Promise<AuthenticatedUser> {
  const token = bearerToken(request)
  if (!token) throw new HttpError(401, '未登录')

  const tokenHash = await sha256Hex(token)
  const timestamp = nowMs()
  const row = await env.DB
    .prepare(
      `SELECT
         s.id AS session_id,
         u.id,
         u.email,
         u.password_hash,
         u.google_sub,
         u.display_name,
         u.avatar_url,
         u.role,
         u.banned_at,
         u.age_confirmed,
         u.email_verified_at,
         u.phone_e164,
         u.phone_verified_at
       FROM sessions s
       JOIN users u ON u.id = s.user_id
       WHERE s.token_hash = ?
         AND s.revoked_at IS NULL
         AND s.expires_at > ?`,
    )
    .bind(tokenHash, timestamp)
    .first<UserRow & { session_id: string }>()

  if (!row) throw new HttpError(401, '登录已过期，请重新登录')
  if (row.banned_at !== null) throw new HttpError(403, '账号已停用')

  await env.DB
    .prepare(
      'UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?',
    )
    .bind(timestamp, timestamp + SESSION_TTL_MS, row.session_id)
    .run()

  return {
    sessionId: row.session_id,
    user: {
      id: row.id,
      email: row.email,
      password_hash: row.password_hash,
      google_sub: row.google_sub,
      display_name: row.display_name,
      avatar_url: row.avatar_url,
      role: row.role,
      banned_at: row.banned_at,
      age_confirmed: row.age_confirmed,
      email_verified_at: row.email_verified_at,
      phone_e164: row.phone_e164,
      phone_verified_at: row.phone_verified_at,
    },
  }
}

async function register(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const email = normalizeEmail(
    requireString(body, 'email', { min: 3, max: 254 }),
  )
  const password = requireString(body, 'password', { min: 8, max: 128 })
  if (body.age_confirmed !== true) {
    throw new HttpError(400, '请先确认已达到使用年龄要求')
  }

  if (await findUserByEmail(env.DB, email)) {
    throw new HttpError(409, '该邮箱已注册')
  }

  const passwordHash = await hashPassword(password, env.PASSWORD_PEPPER)
  const role = roleForEmail(email)
  const timestamp = nowMs()
  const userId = crypto.randomUUID()
  const token = randomToken(48)
  const tokenHash = await sha256Hex(token)
  const ipHash = await requestIpHash(request, env.PASSWORD_PEPPER)
  const registrationStatements = [
    env.DB
      .prepare(
        `INSERT INTO users
          (id, email, password_hash, role, age_confirmed, created_at, updated_at)
         VALUES (?, ?, ?, ?, 1, ?, ?)`,
      )
      .bind(userId, email, passwordHash, role, timestamp, timestamp),
    env.DB
      .prepare(
        `INSERT INTO verification_tokens
          (id, user_id, token_hash, purpose, expires_at, created_at)
         VALUES (?, ?, ?, 'verify_email', ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        userId,
        tokenHash,
        timestamp + VERIFICATION_TTL_MS,
        timestamp,
      ),
    authEventStatement(env.DB, {
      userId,
      eventType: 'auth.registered',
      requestId,
      ipHash,
      userAgent: userAgent(request),
      createdAt: timestamp,
    }),
  ]
  if (COMMERCIAL_MEMBERSHIP_ENABLED) {
    const inviteAttribution = attributeInviteStatement(
      env.DB,
      userId,
      body.ref,
      timestamp,
    )
    if (inviteAttribution) registrationStatements.push(inviteAttribution)
  }

  try {
    await env.DB.batch(registrationStatements)
  } catch (error) {
    if (
      error instanceof Error &&
      error.message.includes('UNIQUE constraint failed')
    ) {
      throw new HttpError(409, '该邮箱已注册')
    }
    throw error
  }

  let emailSent = true
  try {
    await sendVerificationEmail(env, email, token)
  } catch (error) {
    emailSent = false
    console.error(
      JSON.stringify({
        event: 'auth.register.email_deferred',
        requestId,
        userId,
        error: error instanceof Error ? error.message : String(error),
      }),
    )
  }

  return jsonResponse(
    {
      user_id: userId,
      email,
      needs_verification: true,
      email_sent: emailSent,
    },
    201,
    requestId,
    request.method,
  )
}

async function login(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const email = normalizeEmail(
    requireString(body, 'email', { min: 3, max: 254 }),
  )
  const password = requireString(body, 'password', { min: 1, max: 128 })
  const user = await findUserByEmail(env.DB, email)

  const validPassword =
    user?.password_hash !== null &&
    user?.password_hash !== undefined &&
    user.password_hash !== SMS_ONLY_PASSWORD_HASH
      ? await verifyPassword(
          password,
          user.password_hash,
          env.PASSWORD_PEPPER,
        )
      : false

  if (!user || !validPassword) {
    const timestamp = nowMs()
    await authEventStatement(env.DB, {
      userId: user?.id ?? null,
      eventType: 'auth.login_failed',
      requestId,
      ipHash: await requestIpHash(request, env.PASSWORD_PEPPER),
      userAgent: userAgent(request),
      metadata: { emailHash: await sha256Hex(email) },
      createdAt: timestamp,
    }).run()
    throw new HttpError(401, '邮箱或密码错误')
  }
  if (user.banned_at !== null) {
    throw new HttpError(403, '账号已停用')
  }
  if (user.email_verified_at === null) {
    throw new HttpError(403, '请先完成邮箱验证')
  }

  const token = await issueSession(
    env,
    user,
    request,
    requestId,
    'auth.login_succeeded',
  )
  return jsonResponse(
    {
      access_token: token,
      token_type: 'bearer',
      user_id: user.id,
      email: user.email,
      role: user.role,
    },
    200,
    requestId,
    request.method,
  )
}

async function requestSmsCode(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const phone = normalizeChinaMobile(
    requireString(body, 'phone', { min: 11, max: 30 }),
  )
  const timestamp = nowMs()
  const ipHash = await requestIpHash(request, env.PASSWORD_PEPPER)
  const [phoneStats, ipStats] = await env.DB.batch([
    env.DB
      .prepare(
        `SELECT MAX(created_at) AS latest,
                SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS daily
         FROM sms_challenges WHERE phone_e164 = ?`,
      )
      .bind(timestamp - SMS_DAY_MS, phone),
    env.DB
      .prepare(
        `SELECT SUM(CASE WHEN created_at >= ? THEN 1 ELSE 0 END) AS daily
         FROM sms_challenges WHERE ip_hash = ?`,
      )
      .bind(timestamp - SMS_DAY_MS, ipHash),
  ])
  const phoneRow = phoneStats?.results[0] as
    | { latest?: number | null; daily?: number | null }
    | undefined
  const ipRow = ipStats?.results[0] as { daily?: number | null } | undefined
  if (
    (phoneRow?.latest ?? 0) > timestamp - SMS_COOLDOWN_MS ||
    Number(phoneRow?.daily ?? 0) >= SMS_MAX_PHONE_PER_DAY ||
    (ipHash !== null && Number(ipRow?.daily ?? 0) >= SMS_MAX_IP_PER_DAY)
  ) {
    throw new HttpError(429, '请求过于频繁，请稍后再试')
  }

  const challengeId = crypto.randomUUID()
  await env.DB
    .prepare(
      `INSERT INTO sms_challenges
        (id, phone_e164, ip_hash, expires_at, created_at)
       VALUES (?, ?, ?, ?, ?)`,
    )
    .bind(
      challengeId,
      phone,
      ipHash,
      timestamp + SMS_CODE_TTL_MS,
      timestamp,
    )
    .run()
  try {
    await sendSmsCode(env, phone)
  } catch (error) {
    await env.DB
      .prepare('DELETE FROM sms_challenges WHERE id = ?')
      .bind(challengeId)
      .run()
    throw error
  }

  await authEventStatement(env.DB, {
    userId: null,
    eventType: 'auth.sms_requested',
    requestId,
    ipHash,
    userAgent: userAgent(request),
    metadata: { phoneHash: await sha256Hex(phone) },
    createdAt: timestamp,
  }).run()
  return jsonResponse(
    { status: 'ok', expires_in: SMS_CODE_TTL_MS / 1_000 },
    202,
    requestId,
    request.method,
  )
}

async function verifySmsCode(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const phone = normalizeChinaMobile(
    requireString(body, 'phone', { min: 11, max: 30 }),
  )
  const code = requireString(body, 'code', { min: 6, max: 6 })
  if (!/^\d{6}$/u.test(code)) throw new HttpError(422, '验证码格式不正确')
  const create = body.create === true
  const timestamp = nowMs()
  const challenge = await env.DB
    .prepare(
      `SELECT id, attempts
       FROM sms_challenges
       WHERE phone_e164 = ? AND consumed_at IS NULL AND expires_at > ?
       ORDER BY created_at DESC LIMIT 1`,
    )
    .bind(phone, timestamp)
    .first<{ id: string; attempts: number }>()
  if (!challenge || challenge.attempts >= SMS_MAX_ATTEMPTS) {
    throw new HttpError(400, '验证码无效或已过期')
  }
  const valid = await checkSmsCode(env, phone, code)
  if (!valid) {
    await env.DB
      .prepare('UPDATE sms_challenges SET attempts = attempts + 1 WHERE id = ?')
      .bind(challenge.id)
      .run()
    throw new HttpError(400, '验证码无效或已过期')
  }

  let user = await findUserByPhone(env.DB, phone)
  if (!user && !create) {
    throw new HttpError(404, '该手机号尚未注册，请先完成注册')
  }
  if (!user && body.age_confirmed !== true) {
    throw new HttpError(400, '请先确认已达到使用年龄要求')
  }
  const consumed = await env.DB
    .prepare(
      `UPDATE sms_challenges SET consumed_at = ?
       WHERE id = ? AND consumed_at IS NULL RETURNING id`,
    )
    .bind(timestamp, challenge.id)
    .first<{ id: string }>()
  if (!consumed) throw new HttpError(400, '验证码已使用')

  let isNewUser = false
  if (!user) {
    const userId = crypto.randomUUID()
    await env.DB
      .prepare(
        `INSERT INTO users
          (id, email, password_hash, phone_e164, phone_verified_at, role,
           age_confirmed, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, 'user', 1, ?, ?)`,
      )
      .bind(
        userId,
        smsAccountEmail(phone),
        SMS_ONLY_PASSWORD_HASH,
        phone,
        timestamp,
        timestamp,
        timestamp,
      )
      .run()
    user = await findUserByPhone(env.DB, phone)
    if (!user) throw new Error('SMS user creation failed')
    isNewUser = true
    if (COMMERCIAL_MEMBERSHIP_ENABLED) {
      try {
        await activateVerifiedGrowth(env.DB, userId, timestamp)
      } catch (error) {
        console.error(JSON.stringify({
          event: 'growth.activation_failed',
          requestId,
          userId,
          error: error instanceof Error ? error.message : String(error),
        }))
      }
    }
  }
  if (user.banned_at !== null) throw new HttpError(403, '账号已停用')

  const token = await issueSession(
    env,
    user,
    request,
    requestId,
    'auth.sms_succeeded',
  )
  return jsonResponse(
    {
      access_token: token,
      token_type: 'bearer',
      user_id: user.id,
      phone,
      identity: phone,
      role: user.role,
      is_new_user: isNewUser,
    },
    200,
    requestId,
    request.method,
  )
}

async function logout(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const token = bearerToken(request)
  if (token) {
    const tokenHash = await sha256Hex(token)
    const timestamp = nowMs()
    await env.DB
      .prepare(
        `UPDATE sessions
         SET revoked_at = ?
         WHERE token_hash = ? AND revoked_at IS NULL`,
      )
      .bind(timestamp, tokenHash)
      .run()
  }
  return jsonResponse({ ok: true }, 200, requestId, request.method)
}

async function verifyEmail(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const token = requireString(body, 'token', { min: 32, max: 256 })
  const tokenHash = await sha256Hex(token)
  const timestamp = nowMs()
  const consumed = await env.DB
    .prepare(
      `UPDATE verification_tokens
       SET used_at = ?
       WHERE token_hash = ?
         AND purpose = 'verify_email'
         AND used_at IS NULL
         AND expires_at > ?
       RETURNING user_id`,
    )
    .bind(timestamp, tokenHash, timestamp)
    .first<{ user_id: string }>()

  if (!consumed) {
    throw new HttpError(400, '验证链接无效或已过期')
  }

  const user = await env.DB
    .prepare(
      `UPDATE users
       SET email_verified_at = COALESCE(email_verified_at, ?), updated_at = ?
       WHERE id = ?
       RETURNING email`,
    )
    .bind(timestamp, timestamp, consumed.user_id)
    .first<{ email: string }>()
  if (!user) throw new HttpError(404, '用户不存在')

  await authEventStatement(env.DB, {
    userId: consumed.user_id,
    eventType: 'auth.email_verified',
    requestId,
    ipHash: await requestIpHash(request, env.PASSWORD_PEPPER),
    userAgent: userAgent(request),
    createdAt: timestamp,
  }).run()

  let growth = { trialGranted: false, inviteRewarded: false }
  if (COMMERCIAL_MEMBERSHIP_ENABLED) {
    try {
      growth = await activateVerifiedGrowth(
        env.DB,
        consumed.user_id,
        timestamp,
      )
    } catch (error) {
      console.error(
        JSON.stringify({
          event: 'growth.activation_failed',
          requestId,
          userId: consumed.user_id,
          error: error instanceof Error ? error.message : String(error),
        }),
      )
    }
  }

  return jsonResponse(
    {
      verified: true,
      email: user.email,
      trial_granted: growth.trialGranted,
      invite_rewarded: growth.inviteRewarded,
    },
    200,
    requestId,
    request.method,
  )
}

async function resendVerification(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const email = normalizeEmail(
    requireString(body, 'email', { min: 3, max: 254 }),
  )
  const user = await findUserByEmail(env.DB, email)

  if (user && user.email_verified_at === null) {
    const timestamp = nowMs()
    const token = randomToken(48)
    const tokenHash = await sha256Hex(token)
    const tokenId = crypto.randomUUID()
    await env.DB
      .prepare(
        `INSERT INTO verification_tokens
          (id, user_id, token_hash, purpose, expires_at, created_at)
         VALUES (?, ?, ?, 'verify_email', ?, ?)`,
      )
      .bind(
        tokenId,
        user.id,
        tokenHash,
        timestamp + VERIFICATION_TTL_MS,
        timestamp,
      )
      .run()

    try {
      await sendVerificationEmail(env, email, token)
    } catch (error) {
      await env.DB
        .prepare('DELETE FROM verification_tokens WHERE id = ?')
        .bind(tokenId)
        .run()
      console.error(
        JSON.stringify({
          event: 'auth.resend.email_deferred',
          requestId,
          userId: user.id,
          error: error instanceof Error ? error.message : String(error),
        }),
      )
      throw error
    }

    await env.DB
      .prepare(
        `UPDATE verification_tokens
         SET used_at = ?
         WHERE user_id = ? AND purpose = 'verify_email'
           AND used_at IS NULL AND id != ?`,
      )
      .bind(timestamp, user.id, tokenId)
      .run()
  }

  return jsonResponse(
    { status: 'ok' },
    202,
    requestId,
    request.method,
  )
}

async function googleOauth(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const body = await readJsonObject(request)
  const idToken = requireString(body, 'id_token', {
    min: 10,
    max: 10_000,
  })
  const ref = optionalString(body, 'ref', 12)
  const identity = await verifyGoogleIdToken(idToken, env.GOOGLE_CLIENT_ID)
  const email = normalizeEmail(identity.email)
  const timestamp = nowMs()

  let user = await env.DB
    .prepare(
      `SELECT id, email, password_hash, google_sub, display_name, avatar_url,
              role, banned_at, age_confirmed, email_verified_at,
              phone_e164, phone_verified_at
       FROM users
       WHERE google_sub = ?`,
    )
    .bind(identity.subject)
    .first<UserRow>()
  let isNewUser = false
  let growth = { trialGranted: false, inviteRewarded: false }

  if (!user) {
    const emailUser = await findUserByEmail(env.DB, email)
    if (emailUser?.google_sub && emailUser.google_sub !== identity.subject) {
      throw new HttpError(409, '该邮箱已关联其他 Google 账号')
    }

    if (emailUser) {
      if (emailUser.banned_at !== null) {
        throw new HttpError(403, '账号已停用')
      }
      await env.DB
        .prepare(
          `UPDATE users
           SET google_sub = ?, display_name = COALESCE(display_name, ?),
               avatar_url = COALESCE(avatar_url, ?),
               email_verified_at = COALESCE(email_verified_at, ?), updated_at = ?
           WHERE id = ?`,
        )
        .bind(
          identity.subject,
          identity.name,
          identity.picture,
          timestamp,
          timestamp,
          emailUser.id,
        )
        .run()
      user = {
        ...emailUser,
        google_sub: identity.subject,
        display_name: emailUser.display_name ?? identity.name,
        avatar_url: emailUser.avatar_url ?? identity.picture,
        email_verified_at: emailUser.email_verified_at ?? timestamp,
        phone_e164: emailUser.phone_e164,
        phone_verified_at: emailUser.phone_verified_at,
      }
    } else {
      const userId = crypto.randomUUID()
      const role = roleForEmail(email)
      await env.DB
        .prepare(
          `INSERT INTO users
            (id, email, google_sub, display_name, avatar_url, role, age_confirmed,
             email_verified_at, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)`,
        )
        .bind(
          userId,
          email,
          identity.subject,
          identity.name,
          identity.picture,
          role,
          timestamp,
          timestamp,
          timestamp,
        )
        .run()
      user = {
        id: userId,
        email,
        password_hash: null,
        google_sub: identity.subject,
        display_name: identity.name,
        avatar_url: identity.picture,
        role,
        banned_at: null,
        age_confirmed: 1,
        email_verified_at: timestamp,
        phone_e164: null,
        phone_verified_at: null,
      }
      isNewUser = true
      if (COMMERCIAL_MEMBERSHIP_ENABLED) {
        const inviteAttribution = attributeInviteStatement(
          env.DB,
          userId,
          ref,
          timestamp,
        )
        if (inviteAttribution) await inviteAttribution.run()
        try {
          growth = await activateVerifiedGrowth(env.DB, userId, timestamp)
        } catch (error) {
          console.error(
            JSON.stringify({
              event: 'growth.activation_failed',
              requestId,
              userId,
              error: error instanceof Error ? error.message : String(error),
            }),
          )
        }
      }
    }
  }

  if (user.banned_at !== null) {
    throw new HttpError(403, '账号已停用')
  }

  const token = await issueSession(
    env,
    user,
    request,
    requestId,
    'auth.google_succeeded',
  )
  return jsonResponse(
    {
      access_token: token,
      token_type: 'bearer',
      user_id: user.id,
      email: publicIdentity(user),
      role: user.role,
      is_new_user: isNewUser,
      trial_granted: growth.trialGranted,
      invite_rewarded: growth.inviteRewarded,
    },
    200,
    requestId,
    request.method,
  )
}

async function me(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  const profile = await env.DB
    .prepare(
      `SELECT avatar_id, language_pref
       FROM users
       WHERE id = ?`,
    )
    .bind(user.id)
    .first<{ avatar_id: number | null; language_pref: string | null }>()
  return jsonResponse(
    {
      user_id: user.id,
      email: publicIdentity(user),
      phone: user.phone_e164,
      email_verified: user.email_verified_at !== null,
      phone_verified: user.phone_verified_at !== null,
      role: user.role,
      has_password:
        user.password_hash !== null && user.password_hash !== SMS_ONLY_PASSWORD_HASH,
      avatar_id: profile?.avatar_id ?? null,
      is_platinum: false,
      language_pref: profile?.language_pref ?? null,
    },
    200,
    requestId,
    request.method,
  )
}

async function changePassword(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response> {
  const { user } = await authenticate(request, env)
  if (!user.password_hash || user.password_hash === SMS_ONLY_PASSWORD_HASH) {
    throw new HttpError(409, '当前账号没有可修改的本地密码')
  }

  const body = await readJsonObject(request)
  const oldPassword = requireString(body, 'old_password', {
    min: 1,
    max: 128,
  })
  const newPassword = requireString(body, 'new_password', {
    min: 8,
    max: 128,
  })
  if (
    !(await verifyPassword(
      oldPassword,
      user.password_hash,
      env.PASSWORD_PEPPER,
    ))
  ) {
    throw new HttpError(400, '旧密码错误')
  }

  const timestamp = nowMs()
  const newHash = await hashPassword(newPassword, env.PASSWORD_PEPPER)
  await env.DB.batch([
    env.DB
      .prepare('UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?')
      .bind(newHash, timestamp, user.id),
    authEventStatement(env.DB, {
      userId: user.id,
      eventType: 'auth.password_changed',
      requestId,
      ipHash: await requestIpHash(request, env.PASSWORD_PEPPER),
      userAgent: userAgent(request),
      createdAt: timestamp,
    }),
  ])

  return jsonResponse(
    { message: '密码已修改' },
    200,
    requestId,
    request.method,
  )
}

export async function handleAuthRoute(
  request: Request,
  env: Env,
  requestId: string,
): Promise<Response | null> {
  const path = new URL(request.url).pathname
  const route = `${request.method} ${path}`

  switch (route) {
    case 'POST /api/v1/auth/register':
      return register(request, env, requestId)
    case 'POST /api/v1/auth/login':
      return login(request, env, requestId)
    case 'POST /api/v1/auth/sms/request':
      return requestSmsCode(request, env, requestId)
    case 'POST /api/v1/auth/sms/verify':
      return verifySmsCode(request, env, requestId)
    case 'POST /api/v1/auth/logout':
      return logout(request, env, requestId)
    case 'POST /api/v1/auth/verify':
      return verifyEmail(request, env, requestId)
    case 'POST /api/v1/auth/resend-verification':
      return resendVerification(request, env, requestId)
    case 'POST /api/v1/auth/oauth/google':
      return googleOauth(request, env, requestId)
    case 'GET /api/v1/auth/me':
      return me(request, env, requestId)
    case 'POST /api/v1/auth/change-password':
      return changePassword(request, env, requestId)
    default:
      return path.startsWith('/api/v1/auth/')
        ? jsonResponse(
            { detail: 'Route not found' },
            404,
            requestId,
            request.method,
          )
        : null
  }
}
