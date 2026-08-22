import { env } from 'cloudflare:workers'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  buildBollDigest,
  classifyBoll,
  runTelegramMarketCron,
} from '../src/boll-scan'
import type { Kline } from '../src/market'

afterEach(() => vi.restoreAllMocks())

describe('Telegram market scan', () => {
  it('classifies one shared snapshot and builds the hourly digest', () => {
    const klines: Kline[] = Array.from({ length: 30 }, (_, index) => ({
      ts: new Date(index * 900_000).toISOString(),
      open: 100 + index * 0.2,
      high: 100.2 + index * 0.2,
      low: 99.8 + index * 0.2,
      close: 100 + index * 0.2,
      volume: 1_000,
      amount: null,
    }))
    const item = classifyBoll(klines)

    expect(item).toMatchObject({ state: 'trend_up', bias: '偏多' })
    expect(buildBollDigest(
      [{ ...item!, symbol: 'BTCUSDT', change_pct_24h: 2.4 }],
      '12:00',
    )).toContain('BTCUSDT｜三线齐上·上升结构')
  })

  it('sends the hourly scan to a Feishu-only subscriber', async () => {
    const userId = crypto.randomUUID()
    const now = Date.now()
    await env.DB.batch([
      env.DB.prepare(
        `INSERT INTO users
          (id, email, google_sub, role, age_confirmed, email_verified_at,
           created_at, updated_at)
         VALUES (?, ?, ?, 'user', 1, ?, ?, ?)`,
      ).bind(userId, `${userId}@example.com`, userId, now, now, now),
      env.DB.prepare(
        `INSERT INTO notification_configs
          (user_id, feishu_open_id, dott_digest_enabled, created_at, updated_at)
         VALUES (?, 'ou_feishu_only', 1, ?, ?)`,
      ).bind(userId, now, now),
      env.DB.prepare(
        `INSERT OR REPLACE INTO telegram_market_scan_states
          (symbol, state, state_label, bias, pct_b, zone_label, bandwidth,
           close, mid, upper, lower, change_pct_24h, transition, updated_at)
         VALUES ('TSTUSDT', 'trend_up', '三线齐上·上升结构', '偏多', 0.8,
                 '近上轨', 0.1, 1, 0.9, 1.1, 0.7, 2.4, 0, ?)`,
      ).bind(now),
    ])
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) =>
      Response.json(String(input).includes('tenant_access_token')
        ? { code: 0, tenant_access_token: 'test-token' }
        : { code: 0 }),
    )

    const scheduledTime = new Date(now).setMinutes(0, 0, 0)
    await runTelegramMarketCron(env, scheduledTime)

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain('/im/v1/messages')
    await expect(env.DB.prepare(
      `SELECT status FROM notification_deliveries
       WHERE user_id = ? AND channel = 'feishu' ORDER BY created_at DESC LIMIT 1`,
    ).bind(userId).first<{ status: string }>()).resolves.toMatchObject({ status: 'sent' })
  })
})
