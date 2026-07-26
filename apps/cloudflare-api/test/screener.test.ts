import { env, exports } from 'cloudflare:workers'
import { describe, expect, it } from 'vitest'

describe('independent stock screener', () => {
  it('filters the independent D1 market pool by objective spot fields', async () => {
    const snapshot = {
      market: 'us',
      quoted_at: Date.parse('2026-07-26T10:00:00.000Z'),
      rows: [
        {
          symbol: 'AAPL',
          name: '苹果',
          market: 'us',
          sector: '科技',
          last_price: 215,
          prev_close: 210,
          change_amount: 5,
          change_pct: 2.38,
          amount: 10_000,
          volume: 100,
          quoted_at: Date.parse('2026-07-26T10:00:00.000Z'),
        },
        {
          symbol: 'MSFT',
          name: '微软',
          market: 'us',
          sector: '科技',
          last_price: 510,
          prev_close: 515,
          change_amount: -5,
          change_pct: -0.97,
          amount: 20_000,
          volume: 100,
          quoted_at: Date.parse('2026-07-26T10:00:00.000Z'),
        },
      ],
    }
    await env.DB
      .prepare(
        `INSERT INTO market_home_boards
          (market, payload_json, quoted_at, updated_at)
         VALUES ('us', ?, ?, ?)
         ON CONFLICT(market) DO UPDATE SET payload_json = excluded.payload_json`,
      )
      .bind(JSON.stringify(snapshot), snapshot.quoted_at, snapshot.quoted_at)
      .run()

    const response = await exports.default.fetch(
      new Request('https://api.example.test/api/v1/screener/us', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          price_min: 100,
          price_max: 300,
          change_pct_min: 0,
        }),
      }),
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      market: 'us',
      total: 1,
      candidate_capped: true,
      hits: [{ symbol: 'AAPL', last_price: 215 }],
    })
  })
})
