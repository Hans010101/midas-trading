import { env, exports } from 'cloudflare:workers'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { sha256Hex } from '../src/crypto'

function apiRequest(
  path: string,
  options: Readonly<{
    method?: string
    body?: BodyInit
    token?: string
    contentType?: string
  }> = {},
): Request {
  const headers = new Headers()
  if (options.token) headers.set('authorization', `Bearer ${options.token}`)
  if (options.contentType) headers.set('content-type', options.contentType)
  return new Request(`https://api.example.test${path}`, {
    method: options.method ?? 'GET',
    headers,
    ...(options.body ? { body: options.body } : {}),
  })
}

async function createTestSession(): Promise<{
  token: string
  userId: string
  email: string
}> {
  const userId = crypto.randomUUID()
  const email = `${userId}@example.com`
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
        email,
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
  return { token, userId, email }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('independent bot order presets', () => {
  it('returns defaults and stores each user preset in D1', async () => {
    const first = await createTestSession()
    const second = await createTestSession()

    const initial = await exports.default.fetch(
      apiRequest('/api/v1/bot-preset', { token: first.token }),
    )
    expect(initial.status).toBe(200)
    await expect(initial.json()).resolves.toEqual({
      perp_leverage: 3,
      perp_notional_usdt: '100',
      perp_margin_mode: 'isolated',
      spot_notional_cny: '10000',
      spot_notional_usd: '1000',
    })

    const updated = await exports.default.fetch(
      apiRequest('/api/v1/bot-preset', {
        method: 'PUT',
        token: first.token,
        contentType: 'application/json',
        body: JSON.stringify({
          perp_leverage: 8,
          perp_notional_usdt: 250,
          perp_margin_mode: 'cross',
          spot_notional_cny: 20_000,
          spot_notional_usd: 2_500,
        }),
      }),
    )
    expect(updated.status).toBe(200)
    await expect(updated.json()).resolves.toMatchObject({
      perp_leverage: 8,
      perp_notional_usdt: '250',
      perp_margin_mode: 'cross',
    })

    const firstReloaded = await exports.default.fetch(
      apiRequest('/api/v1/bot-preset', { token: first.token }),
    )
    await expect(firstReloaded.json()).resolves.toMatchObject({
      perp_leverage: 8,
      perp_notional_usdt: '250',
    })

    const secondReloaded = await exports.default.fetch(
      apiRequest('/api/v1/bot-preset', { token: second.token }),
    )
    await expect(secondReloaded.json()).resolves.toMatchObject({
      perp_leverage: 3,
      perp_notional_usdt: '100',
    })
  })

  it('rejects unauthenticated and invalid updates', async () => {
    const unauthorized = await exports.default.fetch(
      apiRequest('/api/v1/bot-preset'),
    )
    expect(unauthorized.status).toBe(401)

    const { token } = await createTestSession()
    const invalid = await exports.default.fetch(
      apiRequest('/api/v1/bot-preset', {
        method: 'PUT',
        token,
        contentType: 'application/json',
        body: JSON.stringify({
          perp_leverage: 50,
          perp_notional_usdt: 100,
          perp_margin_mode: 'isolated',
          spot_notional_cny: 10_000,
          spot_notional_usd: 1_000,
        }),
      }),
    )
    expect(invalid.status).toBe(400)
  })
})

describe('independent support tickets', () => {
  it('stores the ticket in D1 and sends it through the independent Resend binding', async () => {
    const session = await createTestSession()
    const resend = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ id: 'email_test' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    const form = new FormData()
    form.set('category', 'activation_failed')
    form.set('description', '兑换后权益没有更新')
    form.set('related_order_id', 'ORDER-1001')
    form.append(
      'images',
      new File(['image-bytes'], 'evidence.png', { type: 'image/png' }),
    )

    const response = await exports.default.fetch(
      apiRequest('/api/v1/support/ticket', {
        method: 'POST',
        token: session.token,
        body: form,
      }),
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      status: 'open',
      email_sent: true,
    })
    expect(resend).toHaveBeenCalledOnce()

    const row = await env.DB
      .prepare(
        `SELECT user_id, contact_email, category, image_count, status
         FROM support_tickets
         WHERE user_id = ?`,
      )
      .bind(session.userId)
      .first<{
        user_id: string
        contact_email: string
        category: string
        image_count: number
        status: string
      }>()
    expect(row).toEqual({
      user_id: session.userId,
      contact_email: session.email,
      category: 'activation_failed',
      image_count: 1,
      status: 'open',
    })
  })

  it('rejects unknown categories before creating a ticket', async () => {
    const { token, userId } = await createTestSession()
    const form = new FormData()
    form.set('category', 'unknown')
    form.set('description', 'test')

    const response = await exports.default.fetch(
      apiRequest('/api/v1/support/ticket', {
        method: 'POST',
        token,
        body: form,
      }),
    )
    expect(response.status).toBe(422)

    const count = await env.DB
      .prepare('SELECT COUNT(*) AS count FROM support_tickets WHERE user_id = ?')
      .bind(userId)
      .first<{ count: number }>()
    expect(count?.count).toBe(0)
  })
})
