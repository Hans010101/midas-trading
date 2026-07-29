import { env, exports } from 'cloudflare:workers'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { sha256Hex } from '../src/crypto'
import { runAdminOperationsCron } from '../src/admin-operations'

function request(
  path: string,
  options: Readonly<{
    method?: string
    token?: string
    body?: Record<string, unknown>
  }> = {},
): Request {
  const headers = new Headers()
  if (options.token) headers.set('authorization', `Bearer ${options.token}`)
  if (options.body) headers.set('content-type', 'application/json')
  return new Request(`https://api.example.test${path}`, {
    method: options.method ?? 'GET',
    headers,
    ...(options.body ? { body: JSON.stringify(options.body) } : {}),
  })
}

async function createUser(
  email: string,
): Promise<{ id: string; token: string }> {
  const id = crypto.randomUUID()
  const token = `admin-test-${crypto.randomUUID()}`
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
        id,
        email,
        `google-${id}`,
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
        id,
        await sha256Hex(token),
        timestamp + 60_000,
        timestamp,
        timestamp,
      ),
  ])
  return { id, token }
}

let owner: Awaited<ReturnType<typeof createUser>>

beforeAll(async () => {
  owner = await createUser('hans.pan.007@gmail.com')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('independent Cloudflare administrator controls', () => {
  it('locks the owner mailbox as an administrator at the database boundary', async () => {
    const row = await env.DB
      .prepare('SELECT role, banned_at FROM users WHERE id = ?')
      .bind(owner.id)
      .first<{ role: string; banned_at: number | null }>()
    expect(row).toEqual({ role: 'admin', banned_at: null })

    await expect(
      env.DB
        .prepare("UPDATE users SET role = 'user' WHERE id = ?")
        .bind(owner.id)
        .run(),
    ).rejects.toThrow('locked administrator cannot be demoted')
  })

  it('enforces 401/403/admin access and exposes operational overview', async () => {
    const member = await createUser(`${crypto.randomUUID()}@example.com`)
    const unauthenticated = await exports.default.fetch(
      request('/api/v1/admin/overview'),
    )
    expect(unauthenticated.status).toBe(401)

    const forbidden = await exports.default.fetch(
      request('/api/v1/admin/overview', { token: member.token }),
    )
    expect(forbidden.status).toBe(403)

    const response = await exports.default.fetch(
      request('/api/v1/admin/overview', { token: owner.token }),
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      total_users: expect.any(Number),
      verified_users: expect.any(Number),
      active_users_7d: expect.any(Number),
      active_sessions: expect.any(Number),
      open_support_tickets: expect.any(Number),
    })
  })

  it('lists users, returns security detail, and protects the locked admin', async () => {
    const list = await exports.default.fetch(
      request('/api/v1/admin/users?page=1&page_size=20', {
        token: owner.token,
      }),
    )
    expect(list.status).toBe(200)
    const listBody = (await list.json()) as {
      items: Array<{ id: string; locked_admin: boolean; role: string }>
    }
    expect(listBody.items).toContainEqual(
      expect.objectContaining({
        id: owner.id,
        locked_admin: true,
        role: 'admin',
      }),
    )

    const detail = await exports.default.fetch(
      request(`/api/v1/admin/users/${owner.id}`, { token: owner.token }),
    )
    await expect(detail.json()).resolves.toMatchObject({
      id: owner.id,
      locked_admin: true,
      active_sessions: expect.any(Number),
      alert_rules_count: expect.any(Number),
      auth_events: expect.any(Array),
      admin_actions: expect.any(Array),
    })

    const banOwner = await exports.default.fetch(
      request(`/api/v1/admin/users/${owner.id}/ban`, {
        method: 'POST',
        token: owner.token,
        body: {},
      }),
    )
    expect(banOwner.status).toBe(409)
  })

  it('bans a user, revokes sessions, and records the admin action', async () => {
    const member = await createUser(`${crypto.randomUUID()}@example.com`)
    const ban = await exports.default.fetch(
      request(`/api/v1/admin/users/${member.id}/ban`, {
        method: 'POST',
        token: owner.token,
        body: { note: 'security test' },
      }),
    )
    expect(ban.status).toBe(200)
    await expect(ban.json()).resolves.toEqual({
      user_id: member.id,
      banned: true,
    })

    const memberMe = await exports.default.fetch(
      request('/api/v1/auth/me', { token: member.token }),
    )
    expect(memberMe.status).toBe(401)

    const detail = await exports.default.fetch(
      request(`/api/v1/admin/users/${member.id}`, { token: owner.token }),
    )
    await expect(detail.json()).resolves.toMatchObject({
      banned: true,
      active_sessions: 0,
      admin_actions: [
        expect.objectContaining({ action: 'user.banned' }),
      ],
    })
  })

  it('lists support tickets and lets an administrator resolve them', async () => {
    const member = await createUser(`${crypto.randomUUID()}@example.com`)
    const created = await env.DB
      .prepare(
        `INSERT INTO support_tickets
          (user_id, contact_email, category, description, image_count, status,
           created_at)
         VALUES (?, ?, 'other', 'Need help', 0, 'open', ?)
         RETURNING id`,
      )
      .bind(member.id, 'help@example.com', Date.now())
      .first<{ id: number }>()
    expect(created).not.toBeNull()

    const list = await exports.default.fetch(
      request('/api/v1/admin/support-tickets?status=open', {
        token: owner.token,
      }),
    )
    expect(list.status).toBe(200)
    await expect(list.json()).resolves.toMatchObject({
      items: [
        expect.objectContaining({
          id: created?.id,
          status: 'open',
          account_email: expect.any(String),
        }),
      ],
    })

    const update = await exports.default.fetch(
      request(`/api/v1/admin/support-tickets/${created?.id}`, {
        method: 'PATCH',
        token: owner.token,
        body: { status: 'resolved' },
      }),
    )
    await expect(update.json()).resolves.toEqual({
      ticket_id: created?.id,
      status: 'resolved',
    })
  })

  it('collects anonymous internal visits and exposes visit/source dashboards', async () => {
    const rejected = await exports.default.fetch(
      request('/api/v1/track/visit', {
        method: 'POST',
        body: { visitor_id: 'external-client' },
      }),
    )
    expect(rejected.status).toBe(403)

    const tracked = await exports.default.fetch(
      new Request('https://midas-trading-api.internal/api/v1/track/visit', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          visitor_id: 'anonymous-test-visitor',
          ref_host: 'example.com',
          utm_source: 'newsletter',
        }),
      }),
    )
    expect(tracked.status).toBe(202)

    const stats = await exports.default.fetch(
      request('/api/v1/admin/visit-stats?days=7', { token: owner.token }),
    )
    expect(stats.status).toBe(200)
    await expect(stats.json()).resolves.toMatchObject({
      range_days: 7,
      daily: expect.any(Array),
      hourly: expect.arrayContaining([
        expect.objectContaining({ hour: 0 }),
        expect.objectContaining({ hour: 23 }),
      ]),
      cumulative_pv: expect.any(Number),
      cumulative_uv: expect.any(Number),
    })

    const sources = await exports.default.fetch(
      request('/api/v1/admin/source-stats?days=7', { token: owner.token }),
    )
    await expect(sources.json()).resolves.toMatchObject({
      sources: expect.arrayContaining([
        expect.objectContaining({ source: 'utm:newsletter' }),
      ]),
      top_referrers: expect.arrayContaining([
        expect.objectContaining({ referrer: 'example.com' }),
      ]),
    })
  })

  it('uploads, schedules, and lists a Cloudflare-native weekly dispatch', async () => {
    const form = new FormData()
    form.set(
      'pdf',
      new File([new Uint8Array([0x25, 0x50, 0x44, 0x46])], 'weekly.pdf', {
        type: 'application/pdf',
      }),
    )
    form.set(
      'md',
      new File(
        [
          '# 市场周报\n## 一句话导语\n保持纪律。\n## 核心结论\n- 波动上升\n## 下周关注\n- BTC',
        ],
        'weekly.md',
        { type: 'text/markdown' },
      ),
    )
    const uploaded = await exports.default.fetch(
      new Request(
        'https://api.example.test/api/v1/admin/weekly-dispatch/upload',
        {
          method: 'POST',
          headers: { authorization: `Bearer ${owner.token}` },
          body: form,
        },
      ),
    )
    expect(uploaded.status).toBe(200)
    const uploadBody = (await uploaded.json()) as { id: number }

    const scheduled = await exports.default.fetch(
      request(
        `/api/v1/admin/weekly-dispatch/${uploadBody.id}/schedule`,
        { method: 'POST', token: owner.token },
      ),
    )
    await expect(scheduled.json()).resolves.toMatchObject({
      id: uploadBody.id,
      status: 'scheduled',
      pdf_filename: 'weekly.pdf',
    })

    const list = await exports.default.fetch(
      request('/api/v1/admin/weekly-dispatch', { token: owner.token }),
    )
    await expect(list.json()).resolves.toMatchObject({
      items: expect.arrayContaining([
        expect.objectContaining({ id: uploadBody.id, status: 'scheduled' }),
      ]),
      next_send_label: expect.any(String),
    })

    const sent = await exports.default.fetch(
      request(
        `/api/v1/admin/weekly-dispatch/${uploadBody.id}/send-now`,
        { method: 'POST', token: owner.token },
      ),
    )
    expect(sent.status).toBe(200)
    await expect(sent.json()).resolves.toMatchObject({
      dispatch_id: uploadBody.id,
      email_sent: 0,
      notify_sent: 0,
      skipped: true,
    })
  })

  it('provides independent social automation and virtual trading control planes', async () => {
    const auto = await exports.default.fetch(
      request('/api/v1/admin/x-auto/status', { token: owner.token }),
    )
    await expect(auto.json()).resolves.toMatchObject({
      enabled: false,
      circuit_open: false,
      platforms: expect.arrayContaining([
        expect.objectContaining({ platform: 'binance_square' }),
        expect.objectContaining({ platform: 'x' }),
      ]),
    })

    const managed = await exports.default.fetch(
      request('/api/v1/admin/managed/status', { token: owner.token }),
    )
    await expect(managed.json()).resolves.toMatchObject({
      enabled: false,
      account_ready: true,
      initial_capital: 100000,
      open_positions: 0,
    })

    const toggle = await exports.default.fetch(
      request('/api/v1/admin/managed/toggle', {
        method: 'POST',
        token: owner.token,
        body: { enabled: true },
      }),
    )
    await expect(toggle.json()).resolves.toMatchObject({ enabled: true })

    const params = await exports.default.fetch(
      request('/api/v1/admin/intelligent/strategy-params', {
        token: owner.token,
      }),
    )
    await expect(params.json()).resolves.toMatchObject({
      threshold: 3,
      weights: expect.objectContaining({ macd: 1 }),
      atr_stop_mult: 2,
      atr_tp_mult: 4,
    })
  })

  it('publishes an approved social draft to Binance Square and records the ledger', async () => {
    const timestamp = Date.now()
    const draft = await env.DB
      .prepare(
        `INSERT INTO social_drafts
          (symbol, bias, tweet_text, compliance_passed, status, auto_drafted,
           has_url, gen_style, provider, model, created_at)
         VALUES ('BTC/USDT', '中性', 'BTC 市场结构联调内容', 1, 'draft', 0,
                 0, 'default', 'technical-rules', 'test', ?)
         RETURNING id`,
      )
      .bind(timestamp)
      .first<{ id: number }>()
    expect(draft).not.toBeNull()
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      code: '000000',
      success: true,
      data: {
        id: 'square-test-1',
        shareLink: 'https://www.binance.com/square/post/square-test-1',
      },
    })))

    const response = await exports.default.fetch(
      request(`/api/v1/admin/x-tweets/${draft!.id}/publish`, {
        method: 'POST',
        token: owner.token,
        body: { platform: 'binance_square' },
      }),
    )
    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      platform: 'binance_square',
      status: 'success',
      url: 'https://www.binance.com/square/post/square-test-1',
    })
    await expect(
      env.DB
        .prepare(
          `SELECT status, source, url FROM social_dispatches
           WHERE draft_id = ? AND platform = 'binance_square'`,
        )
        .bind(draft!.id)
        .first(),
    ).resolves.toMatchObject({
      status: 'success',
      source: 'manual',
      url: 'https://www.binance.com/square/post/square-test-1',
    })
  })

  it('runs one claimed Binance Square auto slot and never duplicates it', async () => {
    const scheduledAt = Date.parse('2026-07-29T08:05:00.000Z')
    await env.DB.batch([
      env.DB
        .prepare(
          `UPDATE social_automation_config
           SET enabled = 1, circuit_open = 0, binance_checked = 1,
               failure_count = 0, last_error = NULL, updated_at = ?
           WHERE id = 1`,
        )
        .bind(scheduledAt),
      env.DB
        .prepare(
          `INSERT INTO social_drafts
            (symbol, bias, tweet_text, compliance_passed, status, auto_drafted,
             has_url, gen_style, provider, model, created_at)
           VALUES ('ETH/USDT', '中性', 'ETH 自动发布联调内容', 1, 'draft', 1,
                   0, 'default', 'technical-rules', 'test', ?)`,
        )
        .bind(scheduledAt),
      env.DB.prepare('UPDATE social_dispatches SET updated_at = 0'),
    ])
    const upstream = vi.fn(async () => Response.json({
      code: '000000',
      success: true,
      data: {
        id: 'square-auto-1',
        shareLink: 'https://www.binance.com/square/post/square-auto-1',
      },
    }))
    vi.stubGlobal('fetch', upstream)

    await runAdminOperationsCron(env, scheduledAt)
    await runAdminOperationsCron(env, scheduledAt)

    expect(upstream).toHaveBeenCalledOnce()
    await expect(
      env.DB
        .prepare(
          `SELECT status, draft_id, dispatch_id FROM social_auto_runs
           WHERE slot = '2026-07-29T16:05'`,
        )
        .first(),
    ).resolves.toMatchObject({
      status: 'success',
      draft_id: expect.any(Number),
      dispatch_id: expect.any(Number),
    })
    await env.DB
      .prepare(
        `UPDATE social_automation_config
         SET enabled = 0, binance_checked = 0 WHERE id = 1`,
      )
      .run()
  })

  it('opens the automatic publishing circuit after three consecutive failures', async () => {
    const firstSlot = Date.parse('2026-07-30T08:05:00.000Z')
    await env.DB.batch([
      env.DB
        .prepare(
          `UPDATE social_automation_config
           SET enabled = 1, circuit_open = 0, binance_checked = 1,
               failure_count = 0, last_error = NULL, updated_at = ?
           WHERE id = 1`,
        )
        .bind(firstSlot),
      env.DB
        .prepare(
          `INSERT INTO social_drafts
            (symbol, bias, tweet_text, compliance_passed, status, auto_drafted,
             has_url, gen_style, provider, model, created_at)
           VALUES ('SOL/USDT', '中性', 'SOL 自动发布失败熔断测试', 1, 'draft', 1,
                   0, 'default', 'technical-rules', 'test', ?)`,
        )
        .bind(firstSlot),
      env.DB.prepare('UPDATE social_dispatches SET updated_at = 0'),
    ])
    const upstream = vi.fn(async () => Response.json({
      code: '20002',
      message: 'content rejected',
    }, { status: 400 }))
    vi.stubGlobal('fetch', upstream)

    await runAdminOperationsCron(env, firstSlot)
    await runAdminOperationsCron(env, firstSlot + 15 * 60_000)
    await runAdminOperationsCron(env, firstSlot + 30 * 60_000)

    expect(upstream).toHaveBeenCalledTimes(3)
    await expect(
      env.DB
        .prepare(
          `SELECT enabled, circuit_open, failure_count, last_error
           FROM social_automation_config WHERE id = 1`,
        )
        .first(),
    ).resolves.toMatchObject({
      enabled: 0,
      circuit_open: 1,
      failure_count: 3,
      last_error: expect.stringContaining('20002'),
    })
  })
})
