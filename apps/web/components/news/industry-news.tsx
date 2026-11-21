import type { IndustryMarket, IndustryNews } from '@midas/shared'
import Link from 'next/link'
import { RefreshNews } from './refresh-news'

import { PublicSiteShell } from '@/components/seo/public-site-shell'
import { midasTradingApiFetch } from '@/lib/server/midas-trading-api'
import { cn } from '@/lib/utils'

export type NewsParams = Promise<Record<string, string | string[] | undefined>>

const marketNames = {
  all: ['全部', 'All markets'], cn: ['A 股', 'A-shares'], us: ['美股', 'US stocks'],
  hk: ['港股', 'HK stocks'], crypto: ['加密', 'Crypto'], macro: ['宏观', 'Macro'],
} as const
type Filter = keyof typeof marketNames
const pageSize = 30
const clock = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' })
const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' })

export async function NewsTimeline({ searchParams, english = false }: { searchParams: NewsParams; english?: boolean }) {
  const query = await searchParams
  const market = typeof query.market === 'string' && Object.hasOwn(marketNames, query.market) ? query.market as Filter : 'all'
  const days = query.range === '24h' ? 1 : 7
  const path = english ? '/en/news' : '/news'
  const label = (key: Filter) => marketNames[key][english ? 1 : 0]
  function href(filter: Filter, span: number, page = 1) {
    const params = new URLSearchParams()
    if (filter !== 'all') params.set('market', filter)
    if (span === 1) params.set('range', '24h')
    if (page > 1) params.set('page', String(page))
    return params.size ? path + '?' + params.toString() : path
  }
  let data: IndustryNews | null = null
  try {
    const res = await midasTradingApiFetch('/api/v1/industry/news', { cache: 'no-store' })
    if (res.ok) data = await res.json() as IndustryNews
  } catch (error) {
    console.warn('industry.news_unavailable', String(error))
  }
  const since = Date.now() - days * 86_400_000
  const items = (data?.items ?? []).filter(item => item.publishedAt >= since && (market === 'all' || item.markets.includes(market)))
  const pages = Math.max(1, Math.ceil(items.length / pageSize))
  const requested = typeof query.page === 'string' ? Number(query.page) : 1
  const page = Number.isSafeInteger(requested) ? Math.max(1, Math.min(pages, requested)) : 1
  const slice = items.slice((page - 1) * pageSize, page * pageSize)
  const delayed = data?.delayedMarkets.filter(key => market === 'all' || market === key) ?? []
  const chip = 'rounded-md px-3 py-1.5 text-sm hover:bg-midas-red-glow focus-visible:outline-midas-red'
  return (
    <PublicSiteShell english={english}>
      <header className="border-b border-paper pb-6">
        <h1 className="font-serif text-3xl font-bold tracking-tight sm:text-4xl">{english ? 'Market news' : '行业快讯'}</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">{english
          ? 'Crypto, mainland China, US and Hong Kong equities, plus macro releases. Headlines link to the original reports in the publisher’s language.'
          : '追踪加密、A 股、美股、港股与宏观政策动态。点击标题可阅读发布方原文。'}</p>
      </header>
      <section className="mt-5" aria-label={english ? 'Latest headlines' : '最新快讯'}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav aria-label={english ? 'Market' : '选择市场'} className="flex flex-wrap gap-1">
            {(Object.keys(marketNames) as Filter[]).map(key => (
              <Link key={key} href={href(key, days)} prefetch={false} aria-current={market === key ? 'page' : undefined}
                className={cn(chip, market === key && 'bg-midas-red text-white hover:bg-midas-red-deep')}>{label(key)}</Link>
            ))}
          </nav>
          <nav aria-label={english ? 'Time window' : '时间范围'} className="flex gap-1">
            {[1, 7].map(span => <Link key={span} prefetch={false} href={href(market, span)}
              aria-current={days === span ? 'page' : undefined}
              className={cn(chip, days === span && 'bg-surface-card font-semibold underline underline-offset-4')}>
              {span === 1 ? (english ? '24 hours' : '近 24 小时') : (english ? '7 days' : '近 7 天')}
            </Link>)}
          </nav>
        </div>
        <div className="my-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {data && <>
          <span>{english ? items.length + ' headlines' : '共 ' + items.length + ' 条'}</span>
          <span>{english ? 'Last checked ' : '最近采集 '}{date.format(data.updatedAt)} {clock.format(data.updatedAt)} · UTC+8</span>
          </>}
          <RefreshNews english={english} />
        </div>
        {delayed.length > 0 && <p className="mb-3 text-sm text-muted-foreground">{english
          ? 'Some sources are delayed for ' : '部分来源更新延迟，涉及'}{delayed.map(label).join(english ? ', ' : '、')}{english ? '.' : '。'}</p>}
        {!slice.length && <p role="status" className="rounded-lg border border-paper p-6 text-sm">
          {data ? (english ? 'No headlines in this window.' : '所选市场在该时段暂无收录。')
            : (english ? 'Headlines are temporarily unavailable. Please refresh shortly.' : '快讯暂时无法加载，请稍后刷新。')}
        </p>}
        <ol>
          {slice.map((item, index) => {
            const first = item.sources[0]!
            const day = date.format(item.publishedAt)
            const prev = slice[index - 1]
            return <li key={first.url}>
              {(!prev || day !== date.format(prev.publishedAt)) && <h2 className="border-b border-paper bg-surface-card px-3 py-2 text-sm font-semibold">{day}</h2>}
              <article className="grid grid-cols-[3rem_minmax(0,1fr)] gap-3 border-b border-paper px-1 py-4 sm:grid-cols-[4rem_minmax(0,1fr)] sm:px-3">
                <time dateTime={new Date(item.publishedAt).toISOString()} className="pt-0.5 font-mono text-sm tabular-nums text-muted-foreground">{clock.format(item.publishedAt)}</time>
                <div>
                  <a href={first.url} target="_blank" rel="noopener noreferrer" className="text-base font-medium leading-6 hover:text-midas-red hover:underline">{item.title}</a>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                    <span className="text-midas-red">{item.markets.map((key: IndustryMarket) => label(key)).join(' · ')}</span>
                    {item.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:underline">{source.name} ↗</a>)}
                  </div>
                </div>
              </article>
            </li>
          })}
        </ol>
        {pages > 1 && <nav aria-label={english ? 'Pagination' : '翻页'} className="mt-5 flex items-center justify-end gap-3 text-sm">
          {page > 1 && <Link prefetch={false} href={href(market, days, page - 1)}>{english ? 'Previous' : '上一页'}</Link>}
          <span>{page} / {pages}</span>
          {page < pages && <Link prefetch={false} href={href(market, days, page + 1)}>{english ? 'Next' : '下一页'}</Link>}
        </nav>}
      </section>
    </PublicSiteShell>
  )
}
