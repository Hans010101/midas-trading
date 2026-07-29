import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  binanceSquareEnabled,
  publishToBinanceSquare,
} from '../src/binance-square'

const testEnv = (key = 'test-square-key') => ({
  BINANCE_SQUARE_API_KEY: key,
}) as unknown as Env

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Binance Square publishing adapter', () => {
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
