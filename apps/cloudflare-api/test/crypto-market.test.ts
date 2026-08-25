import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchCryptoMarketScan, handleCryptoMarketRoute } from '../src/crypto-market'

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
  it('keeps the social volatility scan liquid and crypto-native', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({
        result: 'success',
        tickers: [
          futureTicker,
          {
            ...futureTicker,
            symbol: 'PF_WTIOILUSD',
            pair: 'WTIOIL:USD',
            change24h: 12,
          },
          {
            ...futureTicker,
            symbol: 'PF_OPENUSD',
            pair: 'OPEN:USD',
            volumeQuote: 50_000,
            change24h: 20,
          },
        ],
      })),
    )

    await expect(fetchCryptoMarketScan()).resolves.toEqual([
      expect.objectContaining({ symbol: 'BTC/USDT' }),
    ])
  })

  it('maps the full Bybit USDT perpetual feed to the existing public contract', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          retCode: 0,
          time: 1_785_243_600_000,
          result: {
            list: [{
              symbol: 'BTCUSDT',
              lastPrice: '64456',
              price24hPcnt: '0.0078',
              highPrice24h: '64542',
              lowPrice24h: '63926',
              volume24h: '1449.18',
              turnover24h: '93161640',
              openInterest: '2138.2',
              markPrice: '64456.5',
            }],
          },
        }),
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
      source: 'Bybit public linear market data',
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

  it('uses Bybit metrics for contracts outside the legacy Kraken universe', async () => {
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v5/market/tickers')) {
          return Response.json({
            retCode: 0,
            time: 1_785_243_600_000,
            result: { list: [{ symbol: 'HUSDT', fundingRate: '-0.0044' }] },
          })
        }
        if (url.includes('/account-ratio')) {
          return Response.json({
            retCode: 0,
            result: { list: [{ buyRatio: '0.55', sellRatio: '0.45', timestamp: '2000' }] },
          })
        }
        if (url.includes('/open-interest')) {
          return Response.json({
            retCode: 0,
            result: { list: [
              { openInterest: '125', timestamp: '2000' },
              { openInterest: '100', timestamp: '1000' },
            ] },
          })
        }
        throw new Error(`Unexpected request: ${url}`)
      },
    )
    vi.stubGlobal(
      'fetch',
      fetchMock,
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/metrics-batch?symbols=HUSDT',
      ),
      'crypto-metrics-partial',
    )

    expect(response?.status).toBe(200)
    await expect(response?.json()).resolves.toMatchObject({
      requested: 1,
      processed: 1,
      truncated: false,
      items: [{
        symbol: 'HUSDT',
        funding_rate: -0.0044,
        account_long_short_ratio: 0.55 / 0.45,
        oi_change_pct_24h: 25,
      }],
    })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('uses Gate contract statistics for complete OI history', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/contract_stats')) {
        return Response.json([{
          time: 1_785_243_600,
          open_interest: '11559875',
          open_interest_usd: '1677915.85625',
          mark_price: '0.14515',
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
      source: 'Gate futures contract statistics',
      items: [{
        symbol: 'AGLDUSDT',
        oi_coin: 11_559_875,
        oi_usd: 1_677_915.85625,
      }],
    })
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('serves every supported detail metric for a Bybit-only contract', async () => {
    const timestamp = 1_785_243_600_000
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/market/tickers')) {
        return Response.json({
          retCode: 0,
          time: timestamp,
          result: { list: [{
            symbol: 'CASHCATUSDT',
            markPrice: '0.2156',
            indexPrice: '0.2154',
            openInterest: '2000000',
            fundingRate: '0.0001',
            nextFundingTime: String(timestamp + 28_800_000),
          }] },
        })
      }
      if (url.includes('/open-interest')) {
        return Response.json({
          retCode: 0,
          result: { list: [{ openInterest: '2000000', timestamp: String(timestamp) }] },
        })
      }
      if (url.includes('/account-ratio')) {
        return Response.json({
          retCode: 0,
          result: { list: [{ buyRatio: '0.55', sellRatio: '0.45', timestamp: String(timestamp) }] },
        })
      }
      if (url.includes('/recent-trade')) {
        return Response.json({
          retCode: 0,
          result: { list: [
            { time: String(timestamp), side: 'Buy', size: '120' },
            { time: String(timestamp), side: 'Sell', size: '80' },
          ] },
        })
      }
      if (url.includes('/funding/history')) {
        return Response.json({
          retCode: 0,
          result: { list: [{ fundingRate: '0.0001', fundingRateTimestamp: String(timestamp) }] },
        })
      }
      if (url.includes('/mark-price-kline')) {
        return Response.json({
          retCode: 0,
          result: { list: [
            [String(timestamp), '0.2155', '0.2158', '0.2154', '0.2156'],
            [String(timestamp - 300_000), '0.2151', '0.2156', '0.2150', '0.2154'],
          ] },
        })
      }
      if (url.includes('/index-price-kline')) {
        return Response.json({
          retCode: 0,
          result: { list: [
            [String(timestamp), '0.2153', '0.2156', '0.2152', '0.2154'],
            [String(timestamp - 300_000), '0.2149', '0.2154', '0.2148', '0.2152'],
          ] },
        })
      }
      throw new Error(`Unexpected request: ${url}`)
    }))

    const request = (path: string) => handleCryptoMarketRoute(
      new Request(`https://api.example.test/api/v1/crypto/futures/CASHCATUSDT/${path}`),
      `cashcat-${path}`,
    )
    const [info, oi, ratio, funding, basis] = await Promise.all([
      request('info'),
      request('open-interest?limit=96'),
      request('long-short-ratio?limit=96'),
      request('funding-rate?limit=96'),
      request('basis?limit=96'),
    ])

    await expect(info?.json()).resolves.toMatchObject({
      source: 'Bybit linear perpetual',
      mark_price: 0.2156,
      index_price: 0.2154,
    })
    await expect(oi?.json()).resolves.toMatchObject({
      source: 'Bybit linear open interest',
      items: [{ oi_coin: 2_000_000, oi_usd: 431_200 }],
    })
    await expect(ratio?.json()).resolves.toMatchObject({
      source: 'Bybit global positioning and recent taker flow',
      unavailable_fields: ['top_account_ratio', 'top_position_ratio'],
      items: [{ global_account_ratio: 0.55 / 0.45, taker_ratio: 1.5 }],
    })
    await expect(funding?.json()).resolves.toMatchObject({
      source: 'Bybit funding history',
      items: [{ rate: 0.0001 }],
    })
    await expect(basis?.json()).resolves.toMatchObject({
      source: 'Bybit mark/index candles',
      items: expect.arrayContaining([
        expect.objectContaining({ mark_price: 0.2156, index_price: 0.2154 }),
      ]),
    })
  })

  it('maps all Gate positioning dimensions into one complete response', async () => {
    const timestamp = 1_785_243_600
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/contract_stats')) {
          return Response.json([{
            time: timestamp,
            top_lsr_account: '1.5',
            top_long_account: '60',
            top_short_account: '40',
            top_lsr_size: '1.173913',
            top_long_size: '54',
            top_short_size: '46',
            lsr_account: '1.439024',
            long_users: '59',
            short_users: '41',
            long_taker_size: '10035',
            short_taker_size: '3386',
            lsr_taker: '2.9637',
          }])
        }
        throw new Error(`Unexpected request: ${url}`)
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/AGLDUSDT/long-short-ratio?limit=96',
      ),
      'crypto-ratios-gate',
    )

    await expect(response?.json()).resolves.toMatchObject({
      symbol: 'AGLDUSDT',
      source: 'Gate futures top-trader positioning and taker flow',
      unavailable_fields: [],
      items: [{
        top_account_long: 0.6,
        top_account_short: 0.4,
        top_account_ratio: 1.5,
        top_position_long: 0.54,
        top_position_short: 0.46,
        top_position_ratio: 1.173913,
        global_account_long: 0.59,
        global_account_short: 0.41,
        global_account_ratio: 1.439024,
        taker_buy_vol: 10_035,
        taker_sell_vol: 3_386,
        taker_ratio: 2.9637,
      }],
    })
  })

  it('falls back to Binance for positioning when Gate is unavailable', async () => {
    const timestamp = 1_785_243_600_000
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('api.gateio.ws')) {
          return new Response('unavailable', { status: 503 })
        }
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

  it('falls back to OKX OI history when Gate and Binance are unavailable', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('api.gateio.ws')) {
          return new Response('unavailable', { status: 503 })
        }
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

  it('builds a historical basis series from aligned Gate mark and index candles', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = new URL(String(input))
        const contract = url.searchParams.get('contract')
        if (contract === 'mark_AGLD_USDT') {
          return Response.json([
            { t: 1_785_243_300, c: '0.1450' },
            { t: 1_785_243_600, c: '0.1455' },
          ])
        }
        if (contract === 'index_AGLD_USDT') {
          return Response.json([
            { t: 1_785_243_300, c: '0.1448' },
            { t: 1_785_243_600, c: '0.1452' },
          ])
        }
        throw new Error(`Unexpected request: ${url}`)
      }),
    )

    const response = await handleCryptoMarketRoute(
      new Request(
        'https://api.example.test/api/v1/crypto/futures/AGLDUSDT/basis?limit=96',
      ),
      'crypto-basis-gate',
    )
    const body = (await response?.json()) as {
      source: string
      items: Array<{ mark_price: number; index_price: number; basis_pct: number }>
    }

    expect(body.source).toBe('Gate futures mark/index candles')
    expect(body.items).toHaveLength(2)
    expect(body.items[1]).toMatchObject({
      mark_price: 0.1455,
      index_price: 0.1452,
    })
    expect(body.items[1]?.basis_pct).toBeCloseTo(
      ((0.1455 - 0.1452) / 0.1452) * 100,
    )
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
