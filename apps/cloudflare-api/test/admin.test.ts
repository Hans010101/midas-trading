import { env, exports } from 'cloudflare:workers'
import { beforeAll, describe, expect, it } from 'vitest'

import { sha256Hex } from '../src/crypto'

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
})
