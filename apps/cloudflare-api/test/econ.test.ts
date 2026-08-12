import { afterEach, describe, expect, it, vi } from 'vitest'
import { env } from 'cloudflare:workers'

import { handleEconRoute } from '../src/econ'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('independent economic calendar', () => {
  it('combines official Fed/BEA schedules with objective rule events', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-26T10:00:00.000Z'))
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('federalreserve.gov')) {
          return new Response(`\uFEFF${JSON.stringify({
            events: [{
              type: 'FOMC',
              title: 'FOMC Meeting',
              month: '2026-09',
              days: '15-16',
              time: '2:00 p.m.',
            }],
          })}`)
        }
        return Response.json({
          'Gross Domestic Product': {
            release_dates: ['2026-07-30T12:30:00+00:00'],
          },
          'Personal Income and Outlays': {
            release_dates: ['2026-08-28T12:30:00+00:00'],
          },
        })
      }),
    )

    const response = await handleEconRoute(
      new Request('https://api.example.test/api/v1/econ/calendar'),
      env,
      'econ-1',
    )
    const body = (await response?.json()) as {
      events: Array<{ event_type: string; scheduled_at: string }>
      any_stale: boolean
    }

    expect(body.any_stale).toBe(false)
    expect(body.events.map((event) => event.event_type)).toEqual(
      expect.arrayContaining(['fomc', 'us_gdp', 'us_pce', 'lpr', 'cn_pmi']),
    )
    expect(
      body.events.find((event) => event.event_type === 'fomc')?.scheduled_at,
    ).toBe('2026-09-16T18:00:00.000Z')
  })
})
