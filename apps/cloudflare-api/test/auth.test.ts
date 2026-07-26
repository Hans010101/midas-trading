import { env, exports } from 'cloudflare:workers'
import { afterEach, describe, expect, it, vi } from 'vitest'

import examBank from '../../api/app/services/academy/exam_questions.json'
import { sha256Hex } from '../src/crypto'
import { hashPassword, verifyPassword } from '../src/password'

function apiRequest(
  path: string,
  options: Readonly<{
    method?: string
    body?: Readonly<Record<string, unknown>>
    token?: string
  }> = {},
): Request {
  const headers = new Headers()
  if (options.body) headers.set('content-type', 'application/json')
  if (options.token) {
    headers.set('authorization', `Bearer ${options.token}`)
  }
  return new Request(`https://api.example.test${path}`, {
    method: options.method ?? 'GET',
    headers,
    ...(options.body ? { body: JSON.stringify(options.body) } : {}),
  })
}

afterEach(() => {
  vi.restoreAllMocks()
})

async function createTestSession(): Promise<{
  token: string
  userId: string
}> {
  const userId = crypto.randomUUID()
  const token = `test-session-${crypto.randomUUID()}`
  const timestamp = Date.now()
  await env.DB.batch([
    env.DB
      .prepare(
        `INSERT INTO users
          (id, email, google_sub, role, age_confirmed, email_verified_at,
           created_at, updated_at)
         VALUES (?, ?, ?, 'user', 1, ?, ?, ?)`,
      )
      .bind(
        userId,
        `${userId}@example.com`,
        `google-${userId}`,
        timestamp,
        timestamp,
        timestamp,
      ),
    env.DB
      .prepare(
        `INSERT INTO sessions
          (id, user_id, token_hash, expires_at, last_seen_at, created_at)
         VALUES (?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        crypto.randomUUID(),
        userId,
        await sha256Hex(token),
        timestamp + 60_000,
        timestamp,
        timestamp,
      ),
  ])
  return { token, userId }
}

describe('password storage', () => {
  it('hashes with scrypt and verifies in constant time', async () => {
    const stored = await hashPassword(
      'correct horse battery staple',
      env.PASSWORD_PEPPER,
    )

    expect(stored).toMatch(/^scrypt\$32768\$8\$3\$/u)
    await expect(
      verifyPassword(
        'correct horse battery staple',
        stored,
        env.PASSWORD_PEPPER,
      ),
    ).resolves.toBe(true)
    await expect(
      verifyPassword('wrong password', stored, env.PASSWORD_PEPPER),
    ).resolves.toBe(false)
  })
})

describe('global market overview', () => {
  it('serves independently stored D1 market snapshots', async () => {
    const quotedAt = Date.parse('2026-07-26T09:00:00.000Z')
    await env.DB
      .prepare(
        `INSERT INTO market_overview_quotes
          (symbol, market, name, category, unit, quoted_at, last_point,
           prev_close, change_point, change_pct, source, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      )
      .bind(
        '^GSPC',
        'us',
        '标普500',
        'index',
        'point',
        quotedAt,
        7_411.98,
        7_408.3,
        3.68,
        0.05,
        'yahoo',
        quotedAt,
      )
      .run()

    const response = await exports.default.fetch(
      apiRequest('/api/v1/overview/global'),
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      as_of: '2026-07-26T09:00:00.000Z',
      groups: [
        {
          category: 'index',
          items: [{ symbol: '^GSPC', last_point: 7_411.98 }],
        },
      ],
    })
    expect(response.headers.get('cache-control')).toContain('s-maxage=300')
  })
})

describe('cross-market data', () => {
  it('searches the independent symbol catalog', async () => {
    const response = await exports.default.fetch(
      apiRequest('/api/v1/market/symbols?q=腾讯&market=hk'),
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject([
      { symbol: '00700', market: 'hk', name: '腾讯控股' },
    ])
  })

  it('normalizes Yahoo chart data to the shared kline contract', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      async json() {
        return {
        chart: {
          error: null,
          result: [
            {
              timestamp: [1_785_000_000, 1_785_086_400],
              indicators: {
                quote: [
                  {
                    open: [200, 205],
                    high: [210, 212],
                    low: [198, 203],
                    close: [206, 211],
                    volume: [1_000_000, 1_200_000],
                  },
                ],
              },
            },
          ],
        },
        }
      },
    } as Response)
    const response = await exports.default.fetch(
      apiRequest('/api/v1/market/kline?symbol=AAPL&market=us&period=1d&limit=1'),
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      symbol: 'AAPL',
      market: 'us',
      period: '1d',
      items: [
        {
          open: 205,
          high: 212,
          low: 203,
          close: 211,
          volume: 1_200_000,
          amount: null,
        },
      ],
    })
  })
})

describe('academy learning state', () => {
  it('stores progress, grades server-side, and awards each stage once', async () => {
    const { token, userId } = await createTestSession()

    const guestProgress = await exports.default.fetch(
      apiRequest('/api/v1/academy/progress'),
    )
    expect(guestProgress.status).toBe(200)
    await expect(guestProgress.json()).resolves.toMatchObject({
      completed_slugs: [],
      total_articles: 118,
    })

    const complete = await exports.default.fetch(
      apiRequest('/api/v1/academy/progress/complete', {
        method: 'POST',
        token,
        body: { article_slug: 'A2' },
      }),
    )
    expect(complete.status).toBe(200)
    await expect(complete.json()).resolves.toMatchObject({
      article_slug: 'A2',
      stage: 'basics',
      newly_completed: true,
    })

    const completeAgain = await exports.default.fetch(
      apiRequest('/api/v1/academy/progress/complete', {
        method: 'POST',
        token,
        body: { article_slug: 'A2' },
      }),
    )
    await expect(completeAgain.json()).resolves.toMatchObject({
      newly_completed: false,
    })

    const questions = await exports.default.fetch(
      apiRequest('/api/v1/academy/exam?stage=basics'),
    )
    expect(questions.status).toBe(200)
    const publicQuestions = (await questions.json()) as {
      questions: Array<Record<string, unknown>>
      total: number
    }
    expect(publicQuestions.total).toBe(examBank.basics.length)
    expect(publicQuestions.questions[0]).not.toHaveProperty('answerIndex')
    expect(publicQuestions.questions[0]).not.toHaveProperty('correct_answer')

    const answers = examBank.basics.map((question) => question.answerIndex)
    const firstPass = await exports.default.fetch(
      apiRequest('/api/v1/academy/exam/submit', {
        method: 'POST',
        token,
        body: { stage: 'basics', answers },
      }),
    )
    expect(firstPass.status).toBe(200)
    await expect(firstPass.json()).resolves.toMatchObject({
      stage: 'basics',
      score: examBank.basics.length,
      passed: true,
      membership_awarded: true,
    })

    const secondPass = await exports.default.fetch(
      apiRequest('/api/v1/academy/exam/submit', {
        method: 'POST',
        token,
        body: { stage: 'basics', answers },
      }),
    )
    await expect(secondPass.json()).resolves.toMatchObject({
      passed: true,
      membership_awarded: false,
      new_expires_at: null,
    })

    const status = await exports.default.fetch(
      apiRequest('/api/v1/academy/exam/results', { token }),
    )
    await expect(status.json()).resolves.toEqual({
      results: [
        {
          stage: 'basics',
          passed: true,
          best_score: examBank.basics.length,
          total: examBank.basics.length,
          attempts: 2,
        },
      ],
    })

    const stored = await env.DB
      .prepare(
        `SELECT
           (SELECT COUNT(*) FROM academy_exam_awards
             WHERE user_id = ?) AS awards,
           subscription_expires_at
         FROM users
         WHERE id = ?`,
      )
      .bind(userId, userId)
      .first<{ awards: number; subscription_expires_at: number | null }>()
    expect(stored?.awards).toBe(1)
    expect(stored?.subscription_expires_at).toBeGreaterThan(Date.now())
  })
})

describe('independent membership growth', () => {
  it('attributes an invite, grants trial plus rewards, and reports quota', async () => {
    const inviter = await createTestSession()
    const inviteResponse = await exports.default.fetch(
      apiRequest('/api/v1/invite/me', { token: inviter.token }),
    )
    expect(inviteResponse.status).toBe(200)
    const invite = (await inviteResponse.json()) as {
      code: string
      invite_url: string
    }
    expect(invite.code).toMatch(/^[0-9A-HJKMNP-TV-Z]{8}$/u)
    expect(invite.invite_url).toContain(`/register?ref=${invite.code}`)

    const beforeReward = await exports.default.fetch(
      apiRequest('/api/v1/quota/me', { token: inviter.token }),
    )
    await expect(beforeReward.json()).resolves.toMatchObject({
      plan: 'free',
      items: [
        { feature: 'diagnose', limit: 5, used: 0 },
        { feature: 'backtest', limit: 3, used: 0 },
      ],
    })

    const email = `invitee-${crypto.randomUUID()}@example.com`
    const password = 'Independent-Invite-Password-2026'
    const resendFetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        Response.json({ id: crypto.randomUUID() }, { status: 200 }),
      )
    const registerResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/register', {
        method: 'POST',
        body: {
          email,
          password,
          age_confirmed: true,
          ref: invite.code,
        },
      }),
    )
    expect(registerResponse.status).toBe(201)
    const emailPayload = JSON.parse(
      String(resendFetch.mock.calls[0]?.[1]?.body),
    ) as { html: string }
    const verificationToken =
      /token=([^"&<\s]+)/u.exec(emailPayload.html)?.[1]
    expect(verificationToken).toBeTruthy()

    const verifyResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/verify', {
        method: 'POST',
        body: {
          token: decodeURIComponent(verificationToken ?? ''),
        },
      }),
    )
    expect(verifyResponse.status).toBe(200)
    await expect(verifyResponse.json()).resolves.toMatchObject({
      trial_granted: true,
      invite_rewarded: true,
    })

    const loginResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: { email, password },
      }),
    )
    const login = (await loginResponse.json()) as { access_token: string }
    const inviteeQuota = await exports.default.fetch(
      apiRequest('/api/v1/quota/me', { token: login.access_token }),
    )
    await expect(inviteeQuota.json()).resolves.toMatchObject({
      plan: 'pro',
      items: [
        { feature: 'diagnose', limit: 300 },
        { feature: 'backtest', limit: 150 },
      ],
    })

    const inviterStats = await exports.default.fetch(
      apiRequest('/api/v1/invite/me', { token: inviter.token }),
    )
    await expect(inviterStats.json()).resolves.toMatchObject({
      invited_count: 1,
      rewarded_count: 1,
      earned_days: 15,
    })
    const inviterQuota = await exports.default.fetch(
      apiRequest('/api/v1/quota/me', { token: inviter.token }),
    )
    await expect(inviterQuota.json()).resolves.toMatchObject({
      plan: 'pro',
    })
  })
})

describe('email authentication lifecycle', () => {
  it('registers, verifies, logs in, reads the session, and logs out', async () => {
    const email = `worker-test-${crypto.randomUUID()}@example.com`
    const password = 'Independent-Cloudflare-Password-2026'
    const resendFetch = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        Response.json({ id: crypto.randomUUID() }, { status: 200 }),
      )

    const registerResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/register', {
        method: 'POST',
        body: { email, password, age_confirmed: true },
      }),
    )
    expect(registerResponse.status).toBe(201)
    await expect(registerResponse.json()).resolves.toMatchObject({
      email,
      needs_verification: true,
    })

    const emailRequest = resendFetch.mock.calls[0]?.[1]
    expect(typeof emailRequest?.body).toBe('string')
    const emailPayload = JSON.parse(String(emailRequest?.body)) as {
      html: string
    }
    const token = /token=([^"&<\s]+)/u.exec(emailPayload.html)?.[1]
    expect(token).toBeTruthy()

    const beforeVerification = await exports.default.fetch(
      apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: { email, password },
      }),
    )
    expect(beforeVerification.status).toBe(403)

    const verifyResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/verify', {
        method: 'POST',
        body: { token: decodeURIComponent(token ?? '') },
      }),
    )
    expect(verifyResponse.status).toBe(200)

    const loginResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/login', {
        method: 'POST',
        body: { email, password },
      }),
    )
    expect(loginResponse.status).toBe(200)
    const login = (await loginResponse.json()) as {
      access_token: string
      user_id: string
      role: string
    }
    expect(login.access_token.length).toBeGreaterThan(32)
    expect(login.role).toBe('user')

    const defaultWatchlistResponse = await exports.default.fetch(
      apiRequest('/api/v1/watchlist', { token: login.access_token }),
    )
    expect(defaultWatchlistResponse.status).toBe(200)
    const defaultWatchlist = (await defaultWatchlistResponse.json()) as Array<{
      id: number
      symbol: string
      market: string
    }>
    expect(defaultWatchlist).toHaveLength(3)
    expect(defaultWatchlist.map(({ symbol }) => symbol)).toEqual([
      'BTC/USDT',
      'NVDA',
      '600519',
    ])

    const addWatchlistResponse = await exports.default.fetch(
      apiRequest('/api/v1/watchlist', {
        method: 'POST',
        token: login.access_token,
        body: { symbol: 'aapl', market: 'us' },
      }),
    )
    expect(addWatchlistResponse.status).toBe(201)
    await expect(addWatchlistResponse.json()).resolves.toMatchObject({
      symbol: 'AAPL',
      market: 'us',
      sort_order: 3,
    })

    const preferencesResponse = await exports.default.fetch(
      apiRequest('/api/v1/user/indicator-prefs', {
        method: 'PATCH',
        token: login.access_token,
        body: { day_trade: true },
      }),
    )
    expect(preferencesResponse.status).toBe(200)
    await expect(preferencesResponse.json()).resolves.toEqual({
      bollinger: true,
      chan: true,
      day_trade: true,
    })

    const avatarResponse = await exports.default.fetch(
      apiRequest('/api/v1/user/avatar', {
        method: 'PATCH',
        token: login.access_token,
        body: { avatar_id: 7 },
      }),
    )
    expect(avatarResponse.status).toBe(200)

    const languageResponse = await exports.default.fetch(
      apiRequest('/api/v1/user/language', {
        method: 'PATCH',
        token: login.access_token,
        body: { language: 'en' },
      }),
    )
    expect(languageResponse.status).toBe(200)

    const meResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/me', { token: login.access_token }),
    )
    expect(meResponse.status).toBe(200)
    await expect(meResponse.json()).resolves.toMatchObject({
      user_id: login.user_id,
      email,
      email_verified: true,
      has_password: true,
      avatar_id: 7,
      language_pref: 'en',
    })

    const logoutResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/logout', {
        method: 'POST',
        token: login.access_token,
      }),
    )
    expect(logoutResponse.status).toBe(200)

    const afterLogout = await exports.default.fetch(
      apiRequest('/api/v1/auth/me', { token: login.access_token }),
    )
    expect(afterLogout.status).toBe(401)
  })
})
