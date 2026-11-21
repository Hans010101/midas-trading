import { env } from 'cloudflare:workers'
import { afterEach, expect, it, vi } from 'vitest'
import { readIndustryNews, refreshIndustryNews } from '../src/industry-news'

afterEach(() => vi.unstubAllGlobals())

it('keeps attributed, deduplicated wire and RSS headlines through a partial outage and expires old stories', async () => {
  const now = Date.UTC(2026, 10, 21, 13)
  const wire = { title: '', content_text: '两地上市公司公布季度业绩。下一段。', display_time: now / 1000, uri: 'https://wallstreetcn.com/livenews/123' }
  const feed = (host: string) => '<rss><channel><item><title>本周政策新闻</title><link>https://' + host +
    '/release?utm_source=rss</link><pubDate>' + new Date(now - 1000).toUTCString() + '</pubDate></item></channel></rss>'
  const chinaTitle = '上市公司发布三季度经营公告'
  let outage = false
  vi.stubGlobal('fetch', async (input: string) => {
    if (input.includes('awtmt.com')) {
      if (outage) return Response.json({ data: { items: [] } })
      return Response.json({ data: { items: [wire, { ...wire, is_priced: true, uri: wire.uri + 'paid' },
        { ...wire, uri: 'https://unknown.test/bad' }, { ...wire, display_time: now / 1000 + 600, uri: wire.uri + 'future' }] } })
    }
    if (input.includes('np-listapi.eastmoney.com')) return Response.json({ data: { list: [{ title: chinaTitle,
      uniqueUrl: 'http://finance.eastmoney.com/a/company.html', showTime: '2026-11-21 20:58:10' }] } })
    if (input.includes('federalreserve.gov')) return new Response(feed('www.federalreserve.gov'))
    if (input.includes('panewslab.com')) return new Response(feed('www.panewslab.com'))
    return new Response(null, { status: 503 })
  })
  await refreshIndustryNews(env.DB, now)
  const result = await readIndustryNews(env.DB, now)
  expect(result.items).toHaveLength(3)
  expect(result.items[2]).toEqual({ title: chinaTitle, publishedAt: Date.UTC(2026, 10, 21, 12, 58, 10), markets: ['cn'],
    sources: [{ name: '东方财富', url: 'https://finance.eastmoney.com/a/company.html' }] })
  expect(result.items[0]).toEqual({ title: '两地上市公司公布季度业绩。', publishedAt: now,
    markets: ['cn', 'us', 'hk'], sources: [{ name: '华尔街见闻', url: wire.uri }] })
  expect(result.items[1]?.markets).toEqual(['crypto', 'macro'])
  expect(result.items[1]?.sources.map(source => source.url)).toEqual(['https://www.panewslab.com/release', 'https://www.federalreserve.gov/release'])
  outage = true
  const later = now + 50 * 60_000
  await refreshIndustryNews(env.DB, later)
  const cached = await readIndustryNews(env.DB, later)
  expect(cached.updatedAt).toBe(later)
  expect(cached.items).toEqual(result.items)
  expect(cached.delayedMarkets).toContain('cn')
  expect(cached.delayedMarkets).not.toContain('macro')
  expect((await readIndustryNews(env.DB, now + 8 * 86_400_000)).items).toHaveLength(0)
})
