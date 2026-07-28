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
      disclaimer: '',
      items: [],
    })
  })

  it('uses Binance public OI history before exchange fallbacks', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/futures/data/openInterestHist')) {
        return Response.json([{
          symbol: 'AGLDUSDT',
          sumOpenInterest: '11559875',
          sumOpenInterestValue: '1677915.85625',
          timestamp: 1_785_243_600_000,
        }])
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/AGLDUSDT/open-interest?limit=96',
      ),
      'crypto-oi',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      symbol: 'AGLDUSDT',
      source: 'Binance Futures open interest',
      items: [{
        symbol: 'AGLDUSDT',
        oi_coin: 11_559_875,
        oi_usd: 1_677_915.85625,
      }],
    })
    expect(fetchMock).toHaveBeenCalledOnce()
  })

  it('combines all Binance positioning dimensions into one response', async () => {
    const timestamp = 1_785_243_600_000
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('topLongShortAccountRatio')) {
          return Response.json([{
            timestamp,
            longAccount: '0.60',
            shortAccount: '0.40',
            longShortRatio: '1.50',
          }])
        }
        if (url.includes('topLongShortPositionRatio')) {
          return Response.json([{
            timestamp,
            longAccount: '0.54',
            shortAccount: '0.46',
            longShortRatio: '1.17',
          }])
        }
        if (url.includes('globalLongShortAccountRatio')) {
          return Response.json([{
            timestamp,
            longAccount: '0.59',
            shortAccount: '0.41',
            longShortRatio: '1.44',
          }])
        }
        if (url.includes('takerlongshortRatio')) {
          return Response.json([{
            timestamp,
            buyVol: '10035',
            sellVol: '3386',
            buySellRatio: '2.9637',
          }])
        }
        throw new Error(`Unexpected request: ${url}`)
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/AGLDUSDT/long-short-ratio?limit=96',
      ),
      'crypto-ratios',
    )

    await expect(response?.json()).resolves.toMatchObject({
      symbol: 'AGLDUSDT',
      source: 'Binance Futures positioning and taker flow',
      unavailable_fields: [],
      items: [{
        top_account_ratio: 1.5,
        top_position_ratio: 1.17,
        global_account_ratio: 1.44,
        taker_buy_vol: 10_035,
        taker_sell_vol: 3_386,
        taker_ratio: 2.9637,
      }],
    })
  })

  it('falls back to OKX OI history when Binance is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('fapi.binance.com')) {
          return new Response('restricted', { status: 451 })
        }
        if (url.includes('open-interest-history')) {
          return Response.json({
            code: '0',
            data: [[
              '1785243900000',
              '5109457',
              '5109457',
              '739849.3736',
            ]],
          })
        }
        throw new Error(`Unexpected request: ${url}`)
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/AGLDUSDT/open-interest?limit=96',
      ),
      'crypto-oi-okx',
    )

    await expect(response?.json()).resolves.toMatchObject({
      source: 'OKX open interest history',
      items: [{
        oi_coin: 5_109_457,
        oi_usd: 739_849.3736,
      }],
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
        { name: 'coinpaprika', ok: false },
        { name: 'coinlore', ok: false },
        { name: 'alternative_me', ok: true },
        { name: 'kraken_futures', ok: true },
      ],
    })
  })

  it('falls back to CoinPaprika when CoinGecko is unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('api.coingecko.com')) {
          return new Response('rate limited', { status: 429 })
        }
        if (url.endsWith('/v1/global')) {
          return Response.json({
            market_cap_usd: 2_000_000_000_000,
            volume_24h_usd: 80_000_000_000,
            bitcoin_dominance_percentage: 55,
          })
        }
        if (url.includes('eth-ethereum')) {
          return Response.json({
            quotes: { USD: { market_cap: 240_000_000_000 } },
          })
        }
        if (url.includes('api.alternative.me')) {
          return Response.json({
            data: [{ value: '50', value_classification: 'Neutral' }],
          })
        }
        return Response.json({ result: 'success', tickers: [futureTicker] })
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request('https://api.example.test/api/v1/crypto/overview'),
      'crypto-overview-fallback',
    )

    await expect(response?.json()).resolves.toMatchObject({
      market_overview: {
        total_market_cap_usd: 2_000_000_000_000,
        total_volume_24h_usd: 80_000_000_000,
        btc_dominance: 55,
        eth_dominance: 12,
      },
      unavailable_fields: [],
      sources: [
        { name: 'coingecko', ok: false },
        { name: 'coinpaprika', ok: true },
        { name: 'coinlore', ok: false },
        { name: 'alternative_me', ok: true },
        { name: 'kraken_futures', ok: true },
      ],
    })
  })

  it('uses CoinLore when both primary global sources are unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('api.coingecko.com')) {
          return new Response('rate limited', { status: 429 })
        }
        if (url.includes('api.coinpaprika.com')) {
          return new Response('forbidden', { status: 403 })
        }
        if (url.includes('api.coinlore.net')) {
          return Response.json([{
            total_mcap: 2_100_000_000_000,
            total_volume: 90_000_000_000,
            btc_d: '58.5',
            eth_d: '10.7',
          }])
        }
        if (url.includes('api.alternative.me')) {
          return Response.json({
            data: [{ value: '50', value_classification: 'Neutral' }],
          })
        }
        return Response.json({ result: 'success', tickers: [futureTicker] })
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request('https://api.example.test/api/v1/crypto/overview'),
      'crypto-overview-second-fallback',
    )

    await expect(response?.json()).resolves.toMatchObject({
      market_overview: {
        total_market_cap_usd: 2_100_000_000_000,
        total_volume_24h_usd: 90_000_000_000,
        btc_dominance: 58.5,
        eth_dominance: 10.7,
      },
      unavailable_fields: [],
      sources: [
        { name: 'coingecko', ok: false },
        { name: 'coinpaprika', ok: false },
        { name: 'coinlore', ok: true },
        { name: 'alternative_me', ok: true },
        { name: 'kraken_futures', ok: true },
      ],
    })
  })
})
