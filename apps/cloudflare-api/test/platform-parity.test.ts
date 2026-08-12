import { env, exports } from 'cloudflare:workers'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { sha256Hex } from '../src/crypto'
import { runVirtualFundingSettlement } from '../src/virtual-trading'

function request(
  path: string,
  token?: string,
  method = 'GET',
  body?: unknown,
): Request {
  const headers = new Headers()
  if (token) headers.set('authorization', `Bearer ${token}`)
  if (body !== undefined) headers.set('content-type', 'application/json')
  return new Request(`https://api.example.test${path}`, {
    method,
    headers,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
}

async function session(): Promise<{ token: string; userId: string }> {
  const userId = crypto.randomUUID()
  const token = `parity-${crypto.randomUUID()}`
  const now = Date.now()
  await env.DB.batch([
    env.DB.prepare(
      `INSERT INTO users
        (id, email, google_sub, role, age_confirmed, email_verified_at,
         created_at, updated_at)
       VALUES (?, ?, ?, 'user', 1, ?, ?, ?)`,
    ).bind(userId, `${userId}@example.com`, `google-${userId}`, now, now, now),
    env.DB.prepare(
      `INSERT INTO sessions
        (id, user_id, token_hash, expires_at, last_seen_at, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
    ).bind(crypto.randomUUID(), userId, await sha256Hex(token), now + 60_000, now, now),
  ])
  return { token, userId }
}

function okxCandles(count = 120): Response {
  const start = Date.UTC(2026, 0, 1)
  const rows = Array.from({ length: count }, (_, index) => {
    const wave = Math.sin(index / 5) * 12
    const close = 100 + wave + index * 0.08
    return [
      String(start + index * 86_400_000),
      String(close - 1),
      String(close + 2),
      String(close - 2),
      String(close),
      '1000',
      '1000',
      '100000',
    ]
  }).reverse()
  return Response.json({ code: '0', data: rows })
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('independent professional trading tools', () => {
  it('uses the Cloudflare session for accounts, perpetuals and conditional orders', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('okx.com/api/v5/market/candles')) return okxCandles()
      if (String(input).includes('okx.com/api/v5/public/funding-rate')) {
        return Response.json({ code: '0', data: [{ fundingRate: '0.0001' }] })
      }
      throw new Error(`unexpected upstream ${String(input)}`)
    })
    const auth = await session()

    const activate = await exports.default.fetch(request(
      '/api/v1/virtual/accounts/crypto',
      auth.token,
      'PUT',
      { initial_capital: '10000' },
    ))
    expect(activate.status).toBe(200)
    await expect(activate.json()).resolves.toMatchObject({
      market: 'crypto',
      currency: 'USDT',
      cash_balance: '10000',
    })

    const opened = await exports.default.fetch(request(
      '/api/v1/virtual/perp/orders',
      auth.token,
      'POST',
      {
        symbol: 'BTC/USDT',
        intent: 'open_long',
        leverage: 3,
        margin: '100',
        margin_mode: 'isolated',
      },
    ))
    expect(opened.status).toBe(200)
    await expect(opened.json()).resolves.toMatchObject({
      action: 'open_long',
      status: 'filled',
      leverage: 3,
    })

    const positions = await exports.default.fetch(request(
      '/api/v1/virtual/perp/positions', auth.token,
    ))
    expect(positions.status).toBe(200)
    const positionBody = await positions.json() as Array<{ side: string }>
    expect(positionBody).toHaveLength(1)
    expect(positionBody[0]?.side).toBe('long')

    const aiOrder = await exports.default.fetch(request(
      '/api/v1/virtual/ai-order',
      auth.token,
      'POST',
      { symbol: 'ETH/USDT', market: 'crypto', direction: 'open_short' },
    ))
    expect(aiOrder.status).toBe(200)
    await expect(aiOrder.json()).resolves.toMatchObject({
      filled: true,
      source: 'ai_signal',
    })

    await runVirtualFundingSettlement(env, Date.parse('2026-08-08T00:15:00.000Z'))
    const funding = await exports.default.fetch(request(
      '/api/v1/virtual/perp/funding', auth.token,
    ))
    const fundingBody = await funding.json() as unknown[]
    expect(fundingBody).toHaveLength(2)

    const curves = await exports.default.fetch(request(
      '/api/v1/virtual/equity-curves?days=30', auth.token,
    ))
    const curvesBody = await curves.json() as { curves: { crypto: unknown[] } }
    expect(curvesBody.curves.crypto.length).toBeGreaterThanOrEqual(5)

    const conditional = await exports.default.fetch(request(
      '/api/v1/virtual/conditional-orders',
      auth.token,
      'POST',
      {
        symbol: 'BTC/USDT',
        market: 'crypto',
        order_kind: 'take_profit',
        side: 'sell',
        position_side: 'long',
        trigger_price: '150',
        quantity: '1',
      },
    ))
    expect(conditional.status).toBe(201)
    await expect(conditional.json()).resolves.toMatchObject({
      status: 'active',
      order_kind: 'take_profit',
    })
  })

  it('runs a persisted SMA backtest and returns independent Chan structures', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      if (String(input).includes('okx.com/api/v5/market/candles')) return okxCandles()
      throw new Error(`unexpected upstream ${String(input)}`)
    })
    const auth = await session()
    const created = await exports.default.fetch(request(
      '/api/v1/backtest',
      auth.token,
      'POST',
      {
        symbol: 'BTC/USDT',
        market: 'crypto',
        period: '1d',
        start: '2026-01-01',
        end: '2026-04-30',
        sma_fast: 5,
        sma_slow: 20,
        initial_cash: 100000,
      },
    ))
    expect(created.status).toBe(201)
    const createdBody = await created.json() as { id: number; status: string }
    expect(createdBody.status).toBe('done')

    const detail = await exports.default.fetch(request(
      `/api/v1/backtest/${createdBody.id}`,
      auth.token,
    ))
    expect(detail.status).toBe(200)
    await expect(detail.json()).resolves.toMatchObject({
      status: 'done',
      metrics_json: { final_value: expect.any(Number) },
      run_card_json: { engine: 'cloudflare-sma-cross-v1' },
    })

    const chan = await exports.default.fetch(request(
      '/api/v1/analysis/chan?symbol=BTC%2FUSDT&market=crypto&period=1d&limit=120',
    ))
    expect(chan.status).toBe(200)
    const chanBody = await chan.json() as {
      bar_count: number
      fractals: unknown[]
      bis: unknown[]
      disclaimer: string
    }
    expect(chanBody.bar_count).toBe(120)
    expect(chanBody.fractals.length).toBeGreaterThan(5)
    expect(chanBody.bis.length).toBeGreaterThan(3)
    expect(chanBody.disclaimer).toBe('')
  })
})
