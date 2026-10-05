import { env } from 'cloudflare:workers'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  cleanSocialPostText,
  contentTags,
  draftContentEvent,
  eventTemplateFallback,
  extractSymbols,
  ingestSocialContent,
  nextContentEvent,
  parseCftcPressReleases,
  parseSyndicationFeed,
} from '../src/social-content'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('Binance Square content operations', () => {
  it('ignores legacy pending events whose original facts mention OKX before drafting', async () => {
    const event = await env.DB.prepare(
      `INSERT INTO social_content_events
        (source,source_id,content_type,title,summary,source_url,symbols_json,score,occurred_at,ingested_at)
       VALUES ('PANews',?,'whale','BTC 资金流观察','欧易公开市场数据','https://example.com/news','["BTC"]',100,?,?)
       RETURNING id`,
    ).bind(crypto.randomUUID(), Date.now(), Date.now()).first<{ id: number }>()
    expect(await nextContentEvent(env, ['whale'])).toBeNull()
    expect(await env.DB.prepare('SELECT status FROM social_content_events WHERE id = ?')
      .bind(event!.id).first()).toEqual({ status: 'ignored' })
  })

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

  it('accepts title-only official feeds and CFTC press release pages', () => {
    expect(parseSyndicationFeed(`
      <rss><channel><item>
        <guid>cftc-1</guid><title>Digital asset advisory</title><description/>
        <link>https://example.com/cftc-1</link>
        <pubDate>Thu, 10 Sep 2026 03:00:00 GMT</pubDate>
      </item></channel></rss>`)[0]?.summary).toBe('Digital asset advisory')
    expect(parseCftcPressReleases(`
      <table><tr><td><time datetime="2026-09-10T03:00:00Z">09/10/2026</time></td>
      <td><a href="/PressRoom/PressReleases/9999-26">Digital Asset Advisory</a></td></tr></table>`)[0]).toMatchObject({
      title: 'Digital Asset Advisory',
      link: 'https://www.cftc.gov/PressRoom/PressReleases/9999-26',
    })
  })

  it('keeps an attributed, tagged event draft available when both AI channels are unavailable', async () => {
    const env = {
      AI: {
        run: async () => {
          throw new Error('temporary Workers AI outage')
        },
      },
    } as unknown as Env
    const result = await draftContentEvent(env, {
      id: 42,
      source: 'PANews',
      contentType: 'news',
      title: 'BTC 现货成交活跃度上升',
      summary: '公开市场数据更新',
      sourceUrl: 'https://example.com/news/42',
      symbols: ['BTC'],
      score: 80,
      occurredAt: Date.parse('2026-07-30T01:00:00Z'),
    })

    expect(result).toMatchObject({
      provider: 'rules-fallback',
      model: 'event-template-v1',
      symbol: 'BTC/USDT',
      bias: '中性',
    })
    expect(result.text).toContain('据 PANews')
    expect(result.text).not.toContain('https://')
    expect(result.text).not.toContain('不构成投资建议')
    expect(result.text).toContain('$BTC')
  })

  it('keeps the deterministic news fallback conversational and evidence-led', () => {
    const text = eventTemplateFallback({
      id: 7,
      source: 'PANews',
      contentType: 'news',
      title: 'BTC 现货成交活跃度上升',
      summary: '公开市场数据显示，成交量较前一时段放大。',
      sourceUrl: 'https://example.com/news/7',
      symbols: ['BTC'],
      score: 80,
      occurredAt: Date.parse('2026-07-30T01:00:00Z'),
    })
    expect(text).toContain('📰')
    expect(text).toContain('先看事实')
    expect(text).toContain('我的观察')
    expect(text).not.toContain('不构成投资建议')
  })

  it('removes links and redundant public-post boilerplate', () => {
    expect(cleanSocialPostText(
      '**核心数据：** 正文\n\n仅供参考，不构成投资建议。\n\n来源：PANews https://example.com/news/1',
    )).toBe('核心数据： 正文')
  })

  it('limits concurrent source fetches so one cron run cannot exhaust Worker connections', async () => {
    let active = 0
    let maximum = 0
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      active += 1
      maximum = Math.max(maximum, active)
      await scheduler.wait(5)
      active -= 1
      const url = String(input)
      expect(url).not.toContain('okx.com')
      if (url.includes('api.llama.fi')) return Response.json({ total24h: 0, protocols: [] })
      return new Response('<rss><channel></channel></rss>', { status: 200 })
    })
    const statement = {
      bind: () => statement,
      first: async () => null,
      run: async () => ({ meta: { changes: 0 } }),
    }
    const testEnv = {
      DB: { prepare: () => statement },
      BROWSER: {
        quickAction: async () => Response.json({
          success: true,
          result: '<pre>{"articles":[]}</pre>',
          meta: { status: 200, title: '' },
        }),
      },
    } as unknown as Env

    await ingestSocialContent(testEnv, Date.parse('2026-09-10T02:35:00Z'))

    expect(maximum).toBeLessThanOrEqual(2)
  })
})
