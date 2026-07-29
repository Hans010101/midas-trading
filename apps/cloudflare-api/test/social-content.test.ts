import { describe, expect, it } from 'vitest'

import { contentTags, extractSymbols } from '../src/social-content'

describe('Binance Square content operations', () => {
  it('extracts only relevant coin symbols from Chinese and English news', () => {
    expect(extractSymbols('比特币 ETF 与 Solana 生态进展，同时关注 $ARB')).toEqual([
      'BTC',
      'SOL',
      'ARB',
    ])
  })

  it('creates two to four deterministic, unique Binance cashtags', () => {
    const first = contentTags(['SOL'], 'same-event')
    const second = contentTags(['SOL'], 'same-event')
    expect(first).toEqual(second)
    expect(first.length).toBeGreaterThanOrEqual(2)
    expect(first.length).toBeLessThanOrEqual(4)
    expect(first[0]).toBe('$SOL')
    expect(new Set(first).size).toBe(first.length)
  })
})
