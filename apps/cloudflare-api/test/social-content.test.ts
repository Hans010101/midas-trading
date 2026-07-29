import { describe, expect, it } from 'vitest'

import {
  contentTags,
  extractSymbols,
  parseSyndicationFeed,
} from '../src/social-content'

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

  it('parses RSS and Atom feeds into the same normalized shape', () => {
    const rss = parseSyndicationFeed(`
      <rss><channel><item>
        <guid>rss-1</guid><title><![CDATA[BTC &#8216;update&#8217;]]></title>
        <description><![CDATA[Market summary]]></description>
        <link>https://example.com/rss-1</link>
        <pubDate>Wed, 29 Jul 2026 00:00:00 GMT</pubDate>
      </item></channel></rss>`)
    const atom = parseSyndicationFeed(`
      <feed><entry>
        <id>atom-1</id><title>ETH update</title><summary>Network summary</summary>
        <link rel="alternate" href="https://example.com/atom-1" />
        <updated>2026-07-29T00:00:00Z</updated>
      </entry></feed>`)

    expect(rss).toEqual([{
      id: 'rss-1',
      title: 'BTC ‘update’',
      summary: 'Market summary',
      link: 'https://example.com/rss-1',
      occurredAt: Date.parse('2026-07-29T00:00:00Z'),
    }])
    expect(atom).toEqual([{
      id: 'atom-1',
      title: 'ETH update',
      summary: 'Network summary',
      link: 'https://example.com/atom-1',
      occurredAt: Date.parse('2026-07-29T00:00:00Z'),
    }])
  })
})
