import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchWithRetry } from './fetch-with-retry'

afterEach(() => vi.unstubAllGlobals())

describe('fetchWithRetry', () => {
  it('retries one transient response', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 503 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    expect((await fetchWithRetry('/market')).status).toBe(200)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('does not retry a permanent response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 404 }))
    vi.stubGlobal('fetch', fetchMock)

    expect((await fetchWithRetry('/market')).status).toBe(404)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
