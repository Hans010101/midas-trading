import { env, exports } from 'cloudflare:workers'
import { afterEach, describe, expect, it, vi } from 'vitest'

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

    const meResponse = await exports.default.fetch(
      apiRequest('/api/v1/auth/me', { token: login.access_token }),
    )
    expect(meResponse.status).toBe(200)
    await expect(meResponse.json()).resolves.toMatchObject({
      user_id: login.user_id,
      email,
      email_verified: true,
      has_password: true,
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
