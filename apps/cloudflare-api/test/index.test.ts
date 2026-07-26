import { describe, expect, it } from 'vitest'

import { routeRequest } from '../src/index'

const config = {
  environment: 'test',
  projectName: 'midas-trading',
  apiVersion: 'v1',
} as const

describe('Cloudflare API routing', () => {
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
