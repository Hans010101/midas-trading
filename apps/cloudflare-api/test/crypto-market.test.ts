import { afterEach, describe, expect, it, vi } from 'vitest'

import { handleCryptoMarketRoute } from '../src/crypto-market'

const futureTicker = {
  symbol: 'PF_XBTUSD',
  pair: 'XBT:USD',
  last: 64_456,
  lastTime: '2026-07-26T10:05:05.000Z',
  markPrice: 64_456.5,
  indexPrice: 64_447.8,
  vol24h: 1_449.18,
  volumeQuote: 93_161_640,
  openInterest: 2_138.2,
  fundingRate: 0.6672,
  change24h: 0.78,
  high24h: 64_542,
  low24h: 63_926,
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('independent crypto market routes', () => {
  it('maps Kraken perpetual tickers to the existing public contract', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ result: 'success', tickers: [futureTicker] }),
      ),
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/tickers/24h?instrument=perp&top=10',
      ),
      'crypto-1',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      instrument: 'perp',
      items: [{
        symbol: 'BTC/USDT',
        last_price: 64_456,
        change_pct_24h: 0.78,
      }],
      source: 'Kraken public market data',
    })
  })

  it('exposes real contract info and converts absolute funding to a relative rate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({ result: 'success', tickers: [futureTicker] }),
      ),
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/BTCUSDT/info',
      ),
      'crypto-2',
    )
    const body = (await response?.json()) as {
      symbol: string
      last_funding_rate: number
      open_interest_usd: number
    }

    expect(body.symbol).toBe('BTCUSDT')
    expect(body.last_funding_rate).toBeCloseTo(0.6672 / 64_447.8)
    expect(body.open_interest_usd).toBeGreaterThan(0)
  })

  it('returns an explicit empty state for unavailable strategy snapshots', async () => {
    const response = await handleCryptoMarketRoute(
      new Request('https://api.example.test/api/v1/crypto/boll-scan'),
      'crypto-3',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      as_of: null,
      count: 0,
      items: [],
    })
  })

  it('combines global crypto, sentiment, and derivatives sources without zero placeholders', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('api.coingecko.com')) {
          return Response.json({
            data: {
              total_market_cap: { usd: 2_250_000_000_000 },
              total_volume: { usd: 67_000_000_000 },
              market_cap_percentage: { btc: 57.2, eth: 12.8 },
            },
          })
        }
        if (url.includes('api.alternative.me')) {
          return Response.json({
            data: [{ value: '44', value_classification: 'Fear' }],
          })
        }
        return Response.json({ result: 'success', tickers: [futureTicker] })
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request('https://api.example.test/api/v1/crypto/overview'),
      'crypto-overview',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      market_overview: {
        total_market_cap_usd: 2_250_000_000_000,
        total_volume_24h_usd: 67_000_000_000,
        btc_dominance: 57.2,
        eth_dominance: 12.8,
        fear_greed_value: 44,
        fear_greed_classification: 'Fear',
      },
      unavailable_fields: [],
      sources: [
        { name: 'coingecko', ok: true },
        { name: 'alternative_me', ok: true },
        { name: 'kraken_futures', ok: true },
      ],
    })
  })
})
