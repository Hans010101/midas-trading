import { afterEach, describe, expect, it, vi } from 'vitest'

import { refreshMarketBoard } from '../src/market-home'

afterEach(() => vi.unstubAllGlobals())

describe('market home full-universe sources', () => {
  it('stores every valid Nasdaq screener row in one U.S. snapshot', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      data: {
        rows: [
          { symbol: 'AAA', name: 'Alpha', lastsale: '$10', netchange: '1', pctchange: '11.11%', volume: '1,000', sector: 'Technology' },
          { symbol: 'BBB', name: 'Beta', lastsale: '$20', netchange: '-1', pctchange: '-4.76%', volume: '2,000', sector: 'Finance' },
          { symbol: 'HALT', name: 'Halted', lastsale: 'N/A', netchange: '0', pctchange: '0%', volume: '0', sector: 'Other' },
        ],
      },
    })))
    const run = vi.fn(async () => ({ success: true }))
    const bind = vi.fn((..._values: unknown[]) => ({ run }))
    const env = { DB: { prepare: vi.fn(() => ({ bind })) } } as unknown as Env

    const snapshot = await refreshMarketBoard(env, 'us')

    expect(snapshot.rows).toHaveLength(2)
    expect(snapshot.rows[0]).toMatchObject({ symbol: 'AAA', sector: 'Technology', amount: 10_000 })
    expect(JSON.parse(String(bind.mock.calls[0]?.[1]))).toMatchObject({ market: 'us' })
  })
})
