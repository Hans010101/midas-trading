import { afterEach, describe, expect, it, vi } from 'vitest'

import { handleMarketRoute } from '../src/market'

afterEach(() => {
  vi.unstubAllGlobals()
})

const okxCandle = {
  code: '0',
  msg: '',
  data: [
    ['1785225600000', '0.1461', '0.1471', '0.1458', '0.147', '158240', '158240', '23159.3986', '0'],
    ['1785222000000', '0.1462', '0.1467', '0.1445', '0.1461', '870273', '870273', '126693.8023', '1'],
  ],
}

const bybitCandle = {
  retCode: 0,
  result: {
    list: [
      ['1785225600000', '0.1461', '0.1471', '0.1458', '0.147', '158240', '23159.3986'],
      ['1785222000000', '0.1462', '0.1467', '0.1445', '0.1461', '870273', '126693.8023'],
    ],
  },
}

describe('multi-source market klines', () => {
  it('normalizes Binance-style symbols before requesting OKX candles', async () => {
    const upstream = vi.fn(async (_input: RequestInfo | URL) => Response.json(okxCandle))
    vi.stubGlobal('fetch', upstream)

    const response = await handleMarketRoute(
      new Request(
        'https://api.example.test/api/v1/market/kline?symbol=BTCUSDT&market=crypto&period=1d&instrument=spot&limit=100',
      ),
      {} as Env,
      'market-compact-symbol',
    )

    expect(response?.status).toBe(200)
    expect(String(upstream.mock.calls[0]?.[0])).toContain('instId=BTC-USDT')
  })

  it('uses Bybit perpetual candles for the full linear contract universe', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json(bybitCandle)))

    const response = await handleMarketRoute(
      new Request(
        'https://api.example.test/api/v1/market/kline?symbol=AGLD%2FUSDT&market=crypto&period=1h&instrument=perp&limit=100',
      ),
      {} as Env,
      'market-bybit',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      symbol: 'AGLD/USDT',
      instrument: 'perp',
      source: 'Bybit public linear candles',
      fallback_used: false,
      items: [
        { ts: '2026-07-28T07:00:00.000Z', close: 0.1461 },
        { ts: '2026-07-28T08:00:00.000Z', close: 0.147 },
      ],
    })
  })

  it('falls back from Bybit and OKX to Kraken Futures without returning an empty chart', async () => {
    const upstream = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('bybit.com') || url.includes('okx.com')) {
        return new Response('unavailable', { status: 503 })
      }
      return Response.json({
        candles: [{
          time: 1785225600000,
          open: '0.1517',
          high: '0.1520',
          low: '0.1510',
          close: '0.1518',
          volume: '1200',
        }],
        more_candles: false,
      })
    })
    vi.stubGlobal('fetch', upstream)

    const response = await handleMarketRoute(
      new Request(
        'https://api.example.test/api/v1/market/kline?symbol=AGLD%2FUSDT&market=crypto&period=1h&instrument=perp&limit=100',
      ),
      {} as Env,
      'market-kraken-fallback',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      source: 'Kraken Futures public candles',
      fallback_used: true,
      items: [{ close: 0.1518 }],
    })
    expect(upstream).toHaveBeenCalledTimes(3)
  })

  it('falls back to Yahoo query2 for stock markets', async () => {
    const upstream = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('query1.finance.yahoo.com')) {
        return new Response('rate limited', { status: 429 })
      }
      return Response.json({
        chart: {
          error: null,
          result: [{
            timestamp: [1785196800],
            indicators: {
              quote: [{
                open: [330],
                high: [340],
                low: [329],
                close: [336],
                volume: [10_000],
              }],
            },
          }],
        },
      })
    })
    vi.stubGlobal('fetch', upstream)

    const response = await handleMarketRoute(
      new Request(
        'https://api.example.test/api/v1/market/kline?symbol=AAPL&market=us&period=1d&limit=10',
      ),
      {} as Env,
      'market-yahoo-fallback',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      source: 'Yahoo Finance query2',
      fallback_used: true,
      items: [{ close: 336 }],
    })
  })

  it('discovers live OKX perpetual instruments beyond the local seed list', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({
        code: '0',
        data: [
          { instId: 'AGLD-USDT-SWAP', baseCcy: 'AGLD', state: 'live' },
          { instId: 'AGLD-USD-SWAP', baseCcy: 'AGLD', state: 'live' },
          { instId: 'OLD-USDT-SWAP', baseCcy: 'OLD', state: 'suspend' },
        ],
      })),
    )

    const response = await handleMarketRoute(
      new Request(
        'https://api.example.test/api/v1/market/symbols?q=AGLD&market=crypto&limit=20',
      ),
      {} as Env,
      'market-symbol-search',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toEqual([
      expect.objectContaining({
        symbol: 'AGLD/USDT',
        market: 'crypto',
        is_active: true,
      }),
    ])
  })
})
