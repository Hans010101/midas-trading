import { afterEach, describe, expect, it, vi } from 'vitest'

import worker, { routeRequest } from '../src/index'

afterEach(() => vi.unstubAllGlobals())

const config = {
  environment: 'test',
  projectName: 'midas-trading',
  apiVersion: 'v1',
} as const

describe('Cloudflare API routing', () => {
  it('refreshes global quotes during a publishing slot', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input))
      return url.hostname === 'query1.finance.yahoo.com'
        ? Response.json({ chart: { result: [{ meta: {
            regularMarketPrice: 100,
            chartPreviousClose: 90,
            regularMarketTime: 1791626400,
          } }] } })
        : Response.json({ result: {} })
    })
    vi.stubGlobal('fetch', fetchMock)
    const statement = {
      bind: (..._values: unknown[]) => statement,
      all: async () => ({ results: [] }),
      run: async () => ({ meta: { changes: 0 } }),
    }
    const batch = vi.fn(async () => [])
    const env = {
      ENVIRONMENT: 'test',
      DB: { prepare: () => statement, batch },
    } as unknown as Env
    const tasks: Promise<unknown>[] = []
    const ctx = { waitUntil: (task: Promise<unknown>) => tasks.push(task) } as unknown as ExecutionContext

    await worker.scheduled({ scheduledTime: Date.parse('2026-10-10T10:00:00Z') } as ScheduledController, env, ctx)
    await Promise.all(tasks)

    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('query1.finance.yahoo.com'))).toBe(true)
    expect(batch).toHaveBeenCalledWith(expect.arrayContaining([statement]))
  })

  it('returns an independent health response', async () => {
    const response = await routeRequest(
      new Request('https://api.example.test/api/v1/health'),
      config,
      'request-1',
      '2026-07-26T00:00:00.000Z',
    )

    expect(response.status).toBe(200)
    await expect(response.json()).resolves.toMatchObject({
      status: 'ok',
      project: 'midas-trading',
      runtime: 'cloudflare-workers',
      independent: true,
    })
    expect(response.headers.get('x-request-id')).toBe('request-1')
  })

  it('returns no body for HEAD health checks', async () => {
    const response = await routeRequest(
      new Request('https://api.example.test/health', { method: 'HEAD' }),
      config,
      'request-2',
      '2026-07-26T00:00:00.000Z',
    )

    expect(response.status).toBe(200)
    expect(await response.text()).toBe('')
  })

  it('rejects unsupported methods and unknown routes', async () => {
    const methodResponse = await routeRequest(
      new Request('https://api.example.test/health', { method: 'POST' }),
      config,
      'request-3',
      '2026-07-26T00:00:00.000Z',
    )
    const missingResponse = await routeRequest(
      new Request('https://api.example.test/api/v1/missing'),
      config,
      'request-4',
      '2026-07-26T00:00:00.000Z',
    )

    expect(methodResponse.status).toBe(405)
    expect(missingResponse.status).toBe(404)
  })

  it('reports unavailable readiness without a database binding', async () => {
    const response = await routeRequest(
      new Request('https://api.example.test/api/v1/ready'),
      config,
      'request-5',
      '2026-07-26T00:00:00.000Z',
    )

    expect(response.status).toBe(503)
    await expect(response.json()).resolves.toMatchObject({
      status: 'unavailable',
      database: 'unavailable',
    })
  })
})
