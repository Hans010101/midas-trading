import type { IndustryMarket, IndustryNews } from '@midas/shared'
import { ArrowDown } from 'lucide-react'
import Link from 'next/link'
import { NewsReadingPosition, RefreshNews } from './refresh-news'

import { TopNav } from '@/components/layout/top-nav'
import { PublicSiteFooter } from '@/components/seo/public-site-shell'
import { newsImportance } from '@/lib/news-importance'
import { midasTradingApiFetch } from '@/lib/server/midas-trading-api'
import { cn } from '@/lib/utils'

export type NewsParams = Promise<Record<string, string | string[] | undefined>>

const marketNames = {
  all: ['全部', 'All markets'], cn: ['A 股', 'A-shares'], us: ['美股', 'US stocks'],
  hk: ['港股', 'HK stocks'], crypto: ['加密', 'Crypto'], macro: ['宏观', 'Macro'],
} as const
const marketColors: Record<IndustryMarket, string> = {
  cn: 'text-red-800 bg-red-50 dark:text-red-300 dark:bg-red-950/50',
  us: 'text-blue-800 bg-blue-50 dark:text-blue-300 dark:bg-blue-950/50',
  hk: 'text-teal-800 bg-teal-50 dark:text-teal-300 dark:bg-teal-950/50',
  crypto: 'text-violet-800 bg-violet-50 dark:text-violet-300 dark:bg-violet-950/50',
  macro: 'text-amber-800 bg-amber-50 dark:text-amber-300 dark:bg-amber-950/50',
}
const priorityLabels = { 1: ['常规', 'Routine'], 2: ['关注', 'Notable'], 3: ['重要', 'Important'] } as const
type Filter = keyof typeof marketNames
const pageSize = 30
const clock = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit' })
const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' })

export async function NewsTimeline({ searchParams, english = false }: { searchParams: NewsParams; english?: boolean }) {
  const query = await searchParams
  const market = typeof query.market === 'string' && Object.hasOwn(marketNames, query.market) ? query.market as Filter : 'all'
  const days = query.range === '24h' ? 1 : 7
  const importantOnly = query.priority === 'important'
  const path = english ? '/en/news' : '/news'
  const label = (key: Filter) => marketNames[key][english ? 1 : 0]
  function href(filter: Filter, span: number, page = 1, more = 0, important = importantOnly) {
    const params = new URLSearchParams()
    if (filter !== 'all') params.set('market', filter)
    if (span === 1) params.set('range', '24h')
    if (important) params.set('priority', 'important')
    if (more > 0) params.set('more', String(more))
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
  const items = (data?.items ?? [])
    .filter(item => item.publishedAt >= since && (market === 'all' || item.markets.includes(market)))
    .map(item => ({ ...item, priority: newsImportance(item) }))
    .filter(item => !importantOnly || item.priority === 3)
  const pages = Math.max(1, Math.ceil(items.length / pageSize))
  const requested = typeof query.page === 'string' ? Number(query.page) : 1
  const page = Number.isSafeInteger(requested) ? Math.max(1, Math.min(pages, requested)) : 1
  const more = typeof query.more === 'string' ? Number(query.more) : 0
  const endPage = page + (Number.isSafeInteger(more) ? Math.max(0, Math.min(more, pages - page)) : 0)
  const slice = items.slice((page - 1) * pageSize, endPage * pageSize)
  const nextStory = items[endPage * pageSize]
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
            <div className="flex flex-wrap items-center gap-2">
              <Link href={href(market, days, 1, 0, !importantOnly)} prefetch={false}
                aria-current={importantOnly ? 'true' : undefined}
                className={cn(chip, 'border text-xs', importantOnly
                  ? 'border-amber-500/50 bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                  : 'border-paper text-muted-foreground hover:bg-surface-subtle')}>
                {english ? 'Important only' : '只看重要'}
              </Link>
              <nav aria-label={english ? 'Time window' : '时间范围'} className="inline-flex rounded-lg bg-surface-subtle p-1">
                {[1, 7].map(span => <Link key={span} prefetch={false} href={href(market, span)}
                  aria-current={days === span ? 'page' : undefined}
                  className={cn(chip, 'py-1 text-xs', days === span ? 'bg-background text-foreground shadow-sm' : inactive)}>
                  {span === 1 ? (english ? '24 hours' : '近 24 小时') : (english ? '7 days' : '近 7 天')}
                </Link>)}
              </nav>
            </div>
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
            {data ? (importantOnly ? (english ? 'No important headlines in this window.' : '所选时段暂无重要快讯。')
              : (english ? 'No headlines in this window.' : '所选市场在该时段暂无收录。'))
              : (english ? 'Headlines are temporarily unavailable. Please refresh shortly.' : '快讯暂时无法加载，请稍后刷新。')}
          </p>}
          {Array.from(byDay, ([day, headlines]) => (
            <section key={day} className="mt-5" aria-label={day}>
              <h2 className="border-b border-border pb-2 text-sm font-semibold tabular-nums">{day}</h2>
              <ol className="divide-y divide-border/70">
                {headlines.map(item => {
                  const first = item.sources[0]!
                  const priority = priorityLabels[item.priority][english ? 1 : 0]
                  return <li id={'headline-' + first.url} key={first.url} className={cn('px-2 py-2.5 sm:px-3', item.priority === 3 && 'bg-amber-50/80 dark:bg-amber-950/25')}>
                    <article className="grid grid-cols-[2.75rem_minmax(0,1fr)] items-baseline gap-x-2 sm:grid-cols-[3.5rem_minmax(0,1fr)]">
                      <time dateTime={new Date(item.publishedAt).toISOString()} className="font-mono text-xs tabular-nums text-muted-foreground">
                        {clock.format(item.publishedAt)}
                      </time>
                      <div className="min-w-0">
                        <h3 className={cn('text-sm leading-snug [overflow-wrap:anywhere]', item.priority === 3 && 'font-semibold')}>
                          <a href={first.url} target="_blank" rel="noopener noreferrer" className="hover:text-midas-red hover:underline focus-visible:outline-midas-red">{item.title}</a>
                        </h3>
                        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                          <span title={english ? 'Reading priority based on headline and sources' : '按标题与报道来源自动判断阅读优先级'}
                            className={cn('inline-flex items-center gap-1', item.priority === 3 && 'font-medium text-warn')}>
                            <span aria-hidden="true" className="inline-flex gap-0.5">
                              {[1, 2, 3].map(level => <span key={level} className={cn('h-1.5 w-1.5 rounded-full bg-current', level > item.priority && 'opacity-20')} />)}
                            </span>
                            {priority}
                          </span>
                          {item.markets.map(key => <span key={key} className={cn('rounded px-1.5 leading-4', marketColors[key])}>{label(key)}</span>)}
                          {item.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noopener noreferrer"
                            className="hover:text-foreground hover:underline focus-visible:outline-midas-red">{source.name}</a>)}
                        </div>
                      </div>
                    </article>
                  </li>
                })}
              </ol>
            </section>
          ))}
          {(page > 1 || endPage < pages) && <nav aria-label={english ? 'More headlines' : '更多快讯'} className="mt-4 flex items-center justify-center gap-4 text-sm">
            {page > 1 && <Link prefetch={false} className="text-midas-red hover:underline" href={href(market, days, page - 1)}>{english ? 'Newer headlines' : '查看较新快讯'}</Link>}
            {nextStory && <Link prefetch={false} scroll={false}
              className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 hover:bg-surface-subtle focus-visible:outline-midas-red"
              href={href(market, days, page, endPage - page + 1) + '#' + encodeURIComponent('headline-' + nextStory.sources[0]!.url)}>
              {english ? 'Load older headlines' : '加载更早快讯'}<ArrowDown aria-hidden="true" className="h-3.5 w-3.5" />
            </Link>}
          </nav>}
          <NewsReadingPosition endPage={endPage} />
        </section>
      </main>
      <PublicSiteFooter english={english} />
    </div>
  )
}
