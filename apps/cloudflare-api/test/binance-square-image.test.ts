import { afterEach, describe, expect, it, vi } from 'vitest'
import { uploadSquareImage } from '../src/binance-square-image'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function upstreamWithStatus(status: () => Response) {
  const upstream = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).endsWith('/presignedUrl')) return Response.json({
      code: '000000', data: { presignedUrl: 'https://upload.example/image', fileTicket: 'ticket' },
    })
    if (String(input) === 'https://upload.example/image') {
      expect(new Headers(init?.headers).has('X-Square-OpenAPI-Key')).toBe(false)
      return new Response('')
    }
    expect(String(input)).toContain('/imageStatus')
    return status()
  })
  vi.stubGlobal('fetch', upstream)
  return upstream
}

describe('Square image processing', () => {
  it('accepts an image still processing beyond the former 30-second deadline', async () => {
    vi.useFakeTimers()
    let polls = 0
    upstreamWithStatus(() => Response.json({ code: '000000', data: ++polls <= 15
      ? { status: 0 } : { status: 1, imageUrl: 'https://images.example/chart.png' } }))
    const result = expect(uploadSquareImage('test-key', new ArrayBuffer(4)))
      .resolves.toBe('https://images.example/chart.png')
    await vi.runAllTimersAsync()
    await result
    expect(polls).toBe(16)
  })

  it('reports image rejection immediately with its reason, not a processing timeout', async () => {
    const upstream = upstreamWithStatus(() => Response.json({ code: '000000',
      data: { status: 2, failedReason: 'Unsupported image' } }))
    await expect(uploadSquareImage('test-key', new ArrayBuffer(4)))
      .rejects.toMatchObject({ kind: 'rejected', message: '图片处理被拒绝：Unsupported image' })
    expect(upstream).toHaveBeenCalledTimes(3)
  })

  it('keeps credential failures distinct from transient service failures', async () => {
    upstreamWithStatus(() => Response.json({ code: '220004', message: 'API key expired' }, { status: 401 }))
    await expect(uploadSquareImage('test-key', new ArrayBuffer(4)))
      .rejects.toMatchObject({ kind: 'account' })
    upstreamWithStatus(() => new Response('Unavailable', { status: 503 }))
    await expect(uploadSquareImage('test-key', new ArrayBuffer(4)))
      .rejects.toMatchObject({ kind: 'transient', message: expect.stringContaining('503') })
  })

  it('does not treat a ready status with an empty image URL as success', async () => {
    upstreamWithStatus(() => Response.json({ code: '000000', data: { status: 1, imageUrl: '' } }))
    await expect(uploadSquareImage('test-key', new ArrayBuffer(4)))
      .rejects.toMatchObject({ kind: 'transient' })
  })

  it('bounds pending processing to 120 seconds without treating it as an account fault', async () => {
    vi.useFakeTimers()
    const start = Date.now()
    upstreamWithStatus(() => Response.json({ code: '000000', data: { status: 0 } }))
    const result = expect(uploadSquareImage('test-key', new ArrayBuffer(4)))
      .rejects.toMatchObject({ kind: 'transient', message: expect.stringContaining('120 秒') })
    await vi.runAllTimersAsync()
    await result
    expect(Date.now() - start).toBe(120_000)
  })
})
