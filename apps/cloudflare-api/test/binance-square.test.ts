import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  binanceSquareEnabled,
  publishToBinanceSquare,
} from '../src/binance-square'
import { isSquareCompetitorRelated, SQUARE_COMPETITOR_REASON } from '../src/social-policy'

const testEnv = (key = 'test-square-key') => ({
  BINANCE_SQUARE_API_KEY: key,
}) as unknown as Env

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Binance Square publishing adapter', () => {
  it('filters competitor brands, related projects and original sources for both accounts without uploading or posting', async () => {
    for (const text of ['OKX 上线公告', 'okex.com', '欧易钱包', '欧意交易所',
      'ＯＫＸ 新闻', 'O\u200bkX 公告', 'OKB/USDT', '$OKT', 'X Layer 生态', 'OKTChain 升级',
      'COINBASE 上市公告', 'Ｃｏｉｎｂａｓｅ 钱包', 'Coin\u200bbase Prime', 'coin base exchange',
      '币库交易所', '科因贝斯', 'Kraken Pro 公告', 'Ｋｒａｋｅｎ', '海妖交易所', '克拉肯',
      'Base 链升级', 'Base network TVL', 'https://base.org', 'Base App 更新',
      'cbBTC', '$cbETH', 'cbXRP/USDT', '$COIN', 'Ink 生态', 'Ink L2',
      'https://inkonchain.com', '$INK', 'INK/USDT']) {
      expect(isSquareCompetitorRelated(text)).toBe(true)
    }
    expect(isSquareCompetitorRelated('中性 BTC 新闻', 'OKX Public Trades')).toBe(true)
    expect(isSquareCompetitorRelated('中性 BTC 新闻', 'https://blog.kraken.com/news')).toBe(true)
    expect(isSquareCompetitorRelated('生态更新', 'https://www.coinbase.com/blog')).toBe(true)
    expect(isSquareCompetitorRelated('Bitcoin lookback period, base case and base currency',
      'BTC/USDT', 'CoinDesk', 'linking markets')).toBe(false)
    const upstream = vi.fn()
    vi.stubGlobal('fetch', upstream)
    for (const account of ['midas_trading', 'legacy_midas'] as const) {
      for (const text of ['欧易 OKX 公告', 'Coinbase 钱包更新', 'Kraken 上市公告']) {
        await expect(publishToBinanceSquare(testEnv(), text,
          new ArrayBuffer(4), account)).resolves.toMatchObject({
          success: false, error: SQUARE_COMPETITOR_REASON, imageUrl: null,
        })
      }
    }
    expect(upstream).not.toHaveBeenCalled()
  })

  it('sends the dedicated key only in the Square header and returns the post link', async () => {
    const upstream = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      expect(String(input)).toBe(
        'https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add',
      )
      const headers = new Headers(init?.headers)
      expect(headers.get('X-Square-OpenAPI-Key')).toBe('test-square-key')
      expect(headers.get('clienttype')).toBe('binanceSkill')
      expect(JSON.parse(String(init?.body))).toEqual({
        contentType: 1,
        bodyTextOnly: '市场观察测试',
      })
      return Response.json({
        code: '000000',
        success: true,
        data: {
          id: '12345',
          shareLink: 'https://www.binance.com/square/post/12345',
        },
      })
    })
    vi.stubGlobal('fetch', upstream)

    expect(binanceSquareEnabled(testEnv())).toBe(true)
    await expect(
      publishToBinanceSquare(testEnv(), '市场观察测试'),
    ).resolves.toEqual({
      success: true,
      postId: '12345',
      url: 'https://www.binance.com/square/post/12345',
      error: null,
      imageUrl: null,
      imageError: null,
    })
    expect(upstream).toHaveBeenCalledOnce()
  })

  it('treats the documented 504-after-submit response as success to prevent duplicates', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 504 })))
    await expect(
      publishToBinanceSquare(testEnv(), '已提交但没有返回帖子 ID'),
    ).resolves.toEqual({
      success: true,
      postId: null,
      url: null,
      error: null,
      imageUrl: null,
      imageError: null,
    })
  })

  it('keeps upstream business errors safe and does not expose the key', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      code: '220004',
      message: 'API key expired',
    }, { status: 401 })))
    const result = await publishToBinanceSquare(testEnv('sensitive-key'), '测试')
    expect(result.success).toBe(false)
    expect(result.error).toContain('220004')
    expect(result.error).not.toContain('sensitive-key')
  })
})
