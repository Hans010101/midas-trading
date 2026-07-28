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

describe('independent alerts and notification settings', () => {
  it('stores notification settings and alert rules in D1 per user', async () => {
    const { token } = await createTestSession()
    const update = await exports.default.fetch(
      apiRequest('/api/v1/notifications/config', {
        method: 'PUT',
        token,
        body: {
          price_alert_enabled: false,
          dott_digest_enabled: true,
          dott_transition_enabled: true,
          quiet_hours_enabled: true,
          quiet_hours_start: 22,
          quiet_hours_end: 8,
          quiet_hours_tz: 'Asia/Singapore',
        },
      }),
    )
    expect(update.status).toBe(200)
    await expect(update.json()).resolves.toMatchObject({
      price_alert_enabled: false,
      dott_digest_enabled: true,
      dott_transition_enabled: true,
      quiet_hours_enabled: true,
      quiet_hours_start: 22,
      quiet_hours_end: 8,
      quiet_hours_tz: 'Asia/Singapore',
      has_telegram: false,
      has_feishu: false,
    })

    const created = await exports.default.fetch(
      apiRequest('/api/v1/alert-rules', {
        method: 'POST',
        token,
        body: {
          market: 'us',
          symbol: 'NVDA',
          indicator: 'rsi_14',
          operator: 'gt',
          threshold: 75,
          timeframe: '1d',
        },
      }),
    )
    expect(created.status).toBe(201)
    await expect(created.json()).resolves.toMatchObject({
      market: 'us',
      symbol: 'NVDA',
      indicator: 'rsi_14',
      threshold: '75',
      enabled: true,
    })

    const listed = await exports.default.fetch(
      apiRequest('/api/v1/alert-rules', { token }),
    )
    expect(listed.status).toBe(200)
    const rules = (await listed.json()) as unknown[]
    expect(rules).toHaveLength(1)
  })

  it('lists and marks in-app notifications without crossing user boundaries', async () => {
    const first = await createTestSession()
    const second = await createTestSession()
    const firstNotificationId = crypto.randomUUID()
    const secondNotificationId = crypto.randomUUID()
    const timestamp = Date.now()
    await env.DB.batch([
      env.DB
        .prepare(
          `INSERT INTO in_app_notifications
            (id, user_id, category, title, body, created_at)
           VALUES (?, ?, 'price_alert', '价格提醒', 'NVDA 已突破阈值', ?)`,
        )
        .bind(firstNotificationId, first.userId, timestamp),
      env.DB
        .prepare(
          `INSERT INTO in_app_notifications
            (id, user_id, category, title, body, created_at)
           VALUES (?, ?, 'price_alert', '其他用户提醒', '不可见', ?)`,
        )
        .bind(secondNotificationId, second.userId, timestamp),
    ])

    const listed = await exports.default.fetch(
      apiRequest('/api/v1/notifications/inbox?unread_only=true', {
        token: first.token,
      }),
    )
    expect(listed.status).toBe(200)
    await expect(listed.json()).resolves.toMatchObject({
      unread_count: 1,
      items: [{ id: firstNotificationId, title: '价格提醒' }],
    })

    const forbidden = await exports.default.fetch(
      apiRequest(`/api/v1/notifications/inbox/${secondNotificationId}/read`, {
        method: 'POST',
        token: first.token,
      }),
    )
    expect(forbidden.status).toBe(404)

    const read = await exports.default.fetch(
      apiRequest(`/api/v1/notifications/inbox/${firstNotificationId}/read`, {
        method: 'POST',
        token: first.token,
      }),
    )
    expect(read.status).toBe(200)

    const unread = await exports.default.fetch(
      apiRequest('/api/v1/notifications/inbox?unread_only=true', {
        token: first.token,
      }),
    )
    await expect(unread.json()).resolves.toMatchObject({
      unread_count: 0,
      items: [],
    })
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
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      Response.json({ quotes: [] }),
    )
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

  it('serves independently cached stock-market home boards', async () => {
    const quotedAt = Date.parse('2026-07-25T08:00:00.000Z')
    const rows = [
      {
        symbol: '600519',
        name: '贵州茅台',
        market: 'cn',
        sector: '消费',
        last_price: 1_500,
        prev_close: 1_470,
        change_amount: 30,
        change_pct: 2.0408,
        amount: 15_000_000_000,
        volume: 10_000_000,
        quoted_at: quotedAt,
      },
      {
        symbol: '601318',
        name: '中国平安',
        market: 'cn',
        sector: '金融',
        last_price: 58,
        prev_close: 60,
        change_amount: -2,
        change_pct: -3.3333,
        amount: 5_800_000_000,
        volume: 100_000_000,
        quoted_at: quotedAt,
      },
    ]
    await env.DB
      .prepare(
        `INSERT INTO market_home_boards
          (market, payload_json, quoted_at, updated_at)
         VALUES ('cn', ?, ?, ?)`,
      )
      .bind(
        JSON.stringify({ market: 'cn', rows, quoted_at: quotedAt }),
        quotedAt,
        quotedAt,
      )
      .run()

    const board = await exports.default.fetch(
      apiRequest('/api/v1/cn/board?limit=100'),
    )
    expect(board.status).toBe(200)
    await expect(board.json()).resolves.toMatchObject({
      pool_size: 2,
      scope_label: '重点标的池',
      breadth: {
        up_count: 1,
        down_count: 1,
      },
      gainers: [{ symbol: '600519' }, { symbol: '601318' }],
      losers: [{ symbol: '601318' }, { symbol: '600519' }],
    })

    const search = await exports.default.fetch(
      apiRequest('/api/v1/cn/search?q=茅台&limit=30'),
    )
    await expect(search.json()).resolves.toMatchObject([
      { symbol: '600519', name: '贵州茅台' },
    ])
  })
})

describe('academy learning state', () => {
  it('stores progress and grades server-side without commercial rewards', async () => {
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
      membership_awarded: false,
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
    expect(stored?.awards).toBe(0)
    expect(stored?.subscription_expires_at).toBeNull()
  })
})

describe('independent account growth', () => {
  it('disables invitations and gives every account full quota', async () => {
    const inviter = await createTestSession()
    const inviteResponse = await exports.default.fetch(
      apiRequest('/api/v1/invite/me', { token: inviter.token }),
    )
    expect(inviteResponse.status).toBe(404)

    const beforeReward = await exports.default.fetch(
      apiRequest('/api/v1/quota/me', { token: inviter.token }),
    )
    await expect(beforeReward.json()).resolves.toMatchObject({
      plan: 'registered',
      items: [
        { feature: 'diagnose', limit: 300, used: 0 },
        { feature: 'backtest', limit: 150, used: 0 },
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
          ref: 'DISABLED',
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
      trial_granted: false,
      invite_rewarded: false,
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
      plan: 'registered',
      items: [
        { feature: 'diagnose', limit: 300 },
        { feature: 'backtest', limit: 150 },
      ],
    })

    const inviterStats = await exports.default.fetch(
      apiRequest('/api/v1/invite/me', { token: inviter.token }),
    )
    expect(inviterStats.status).toBe(404)
    const inviterQuota = await exports.default.fetch(
      apiRequest('/api/v1/quota/me', { token: inviter.token }),
    )
    await expect(inviterQuota.json()).resolves.toMatchObject({
      plan: 'registered',
    })
  })
})

describe('independent redeem codes', () => {
  it('keeps redemption routes disabled while retaining their implementation', async () => {
    const admin = await createTestSession()
    const member = await createTestSession()
    await env.DB
      .prepare("UPDATE users SET role = 'admin' WHERE id = ?")
      .bind(admin.userId)
      .run()

    const generateResponse = await exports.default.fetch(
      apiRequest('/api/v1/admin/redeem-codes', {
        method: 'POST',
        token: admin.token,
        body: { period: 'month', count: 2, note: 'worker test' },
      }),
    )
    expect(generateResponse.status).toBe(404)

    const listResponse = await exports.default.fetch(
      apiRequest('/api/v1/admin/redeem-codes?page=1&page_size=20', {
        token: admin.token,
      }),
    )
    expect(listResponse.status).toBe(404)

    const redeemResponse = await exports.default.fetch(
      apiRequest('/api/v1/redeem', {
        method: 'POST',
        token: member.token,
        body: { code: 'DISABLED-CODE' },
      }),
    )
    expect(redeemResponse.status).toBe(404)

    const memberQuota = await exports.default.fetch(
      apiRequest('/api/v1/quota/me', { token: member.token }),
    )
    await expect(memberQuota.json()).resolves.toMatchObject({
      plan: 'registered',
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
