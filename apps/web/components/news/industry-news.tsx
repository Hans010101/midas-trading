import type { IndustryNews } from '@midas/shared'
import { ArrowUpRight } from 'lucide-react'
import Link from 'next/link'
import { RefreshNews } from './refresh-news'

import { TopNav } from '@/components/layout/top-nav'
import { PublicSiteFooter } from '@/components/seo/public-site-shell'
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
  const byDay = new Map<string, typeof slice>()
  for (const item of slice) {
    const day = date.format(item.publishedAt)
    const group = byDay.get(day)
    if (group) group.push(item)
    else byDay.set(day, [item])
  }
  const chip = 'rounded-md px-2.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-midas-red'
  const inactive = 'text-muted-foreground hover:bg-surface-subtle hover:text-foreground'

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-6">
        <header className="mb-6">
          <h1 className="font-serif text-2xl font-bold">{english ? 'Market news' : '行业快讯'}</h1>
          <p className="mt-2 text-sm text-muted-foreground">{english
            ? 'Follow crypto, mainland China, US and Hong Kong equities, and macro policy.'
            : '追踪加密、A 股、美股、港股与宏观政策动态。'}</p>
        </header>

        <section aria-label={english ? 'Latest headlines' : '最新快讯'}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <nav aria-label={english ? 'Market' : '选择市场'} className="flex flex-wrap gap-1">
              {(Object.keys(marketNames) as Filter[]).map(key => (
                <Link key={key} href={href(key, days)} prefetch={false} aria-current={market === key ? 'page' : undefined}
                  className={cn(chip, market === key ? 'bg-midas-red text-white' : inactive)}>{label(key)}</Link>
              ))}
            </nav>
            <nav aria-label={english ? 'Time window' : '时间范围'} className="inline-flex rounded-lg bg-surface-subtle p-1">
              {[1, 7].map(span => <Link key={span} prefetch={false} href={href(market, span)}
                aria-current={days === span ? 'page' : undefined}
                className={cn(chip, 'py-1 text-xs', days === span ? 'bg-background text-foreground shadow-sm' : inactive)}>
                {span === 1 ? (english ? '24 hours' : '近 24 小时') : (english ? '7 days' : '近 7 天')}
              </Link>)}
            </nav>
          </div>
          <div className="mt-3 flex items-center gap-3 border-b border-paper pb-3 text-xs text-muted-foreground">
            {data && <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span>{english ? items.length + ' headlines' : '共 ' + items.length + ' 条'}</span>
              <span>{english ? 'Last checked ' : '最近采集 '}{date.format(data.updatedAt)} {clock.format(data.updatedAt)} · UTC+8</span>
            </div>}
            <RefreshNews english={english} />
          </div>

          {delayed.length > 0 && <p className="mt-4 text-sm text-muted-foreground">{english
            ? 'Some sources are delayed for ' : '部分来源更新延迟，涉及'}{delayed.map(label).join(english ? ', ' : '、')}{english ? '.' : '。'}</p>}
          {!slice.length && <p role="status" className="mt-5 rounded-xl border border-paper bg-cream p-5 text-sm text-muted-foreground">
            {data ? (english ? 'No headlines in this window.' : '所选市场在该时段暂无收录。')
              : (english ? 'Headlines are temporarily unavailable. Please refresh shortly.' : '快讯暂时无法加载，请稍后刷新。')}
          </p>}
          {Array.from(byDay, ([day, headlines]) => (
            <section key={day} className="mt-5" aria-label={day}>
              <h2 className="mb-3 text-sm font-semibold tabular-nums">{day}</h2>
              <ol className="grid gap-4 sm:grid-cols-2">
                {headlines.map(item => {
                  const first = item.sources[0]!
                  return <li key={first.url} className="min-w-0">
                    <article className="relative flex h-full flex-col rounded-xl border border-paper bg-cream p-5 shadow-sm transition-colors hover:border-midas-red/40 focus-within:border-midas-red/40">
                      <div className="flex items-center justify-between gap-3">
                        <span className="rounded-full bg-midas-red/10 px-2.5 py-0.5 text-xs text-midas-red dark:text-midas-red-soft">
                          {item.markets.map(label).join(' · ')}
                        </span>
                        <time dateTime={new Date(item.publishedAt).toISOString()} className="font-mono text-xs tabular-nums text-muted-foreground">{clock.format(item.publishedAt)}</time>
                      </div>
                      <h3 className="mt-3 flex-1 break-words font-serif text-lg font-bold leading-snug [overflow-wrap:anywhere]">
                        <a href={first.url} target="_blank" rel="noopener noreferrer" className="after:absolute after:inset-0 after:rounded-xl hover:text-midas-red focus-visible:outline-midas-red">{item.title}</a>
                      </h3>
                      <div className="mt-4 flex flex-wrap gap-x-3 gap-y-1">
                        {item.sources.map(source => (
                          <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer"
                            className="relative inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-midas-red focus-visible:outline-midas-red">
                            {source.name}<ArrowUpRight aria-hidden="true" className="h-3.5 w-3.5" />
                          </a>
                        ))}
                      </div>
                    </article>
                  </li>
                })}
              </ol>
            </section>
          ))}
          {pages > 1 && <nav aria-label={english ? 'Pagination' : '翻页'} className="mt-6 flex items-center justify-center gap-4 text-sm">
            {page > 1 && <Link prefetch={false} className="text-midas-red hover:underline" href={href(market, days, page - 1)}>{english ? 'Previous' : '上一页'}</Link>}
            <span className="tabular-nums text-muted-foreground">{page} / {pages}</span>
            {page < pages && <Link prefetch={false} className="text-midas-red hover:underline" href={href(market, days, page + 1)}>{english ? 'Next' : '下一页'}</Link>}
          </nav>}
        </section>
      </main>
      <PublicSiteFooter english={english} />
    </div>
  )
}
