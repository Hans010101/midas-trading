'use client'

/**
 * 财经日历(PR-A · 红线级)· 宏观事件日程的纯客观展示。
 *
 * 🔴 红线(apps/api tests/services/test_econ_calendar_page.py 机器钉死):
 * - 只呈现客观事实:时间(北京时间)/ 事件名 / 地区 / 重要度星级 / 来源
 * - 绝无 AI 对单个事件的方向性解读(零 LLM:全部文案 = 库字段 + 本文件静态模板)
 * - 波动提示客观无方向 · 免责「仅供参考,不构成投资建议」完整呈现
 * - ★保鲜:页顶「数据更新时间」读采集任务 last-run(绝不是 max(事件ts),那个永远假新鲜)
 */

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { TopNav } from '@/components/layout/top-nav'
import { fetchEconCalendar, type EconEvent } from '@/lib/api/econ-calendar'
import { cn } from '@/lib/utils'

// ── 地区(筛选维度):按 event_type 归属;「加密」单独用 markets 含 crypto 判 ──────
const REGIONS = ['all', 'cn', 'us', 'eu', 'jp', 'crypto'] as const
type Region = (typeof REGIONS)[number]

const REGION_LABEL: Record<Region, string> = {
  all: '全部',
  cn: '中国',
  us: '美国',
  eu: '欧洲',
  jp: '日本',
  crypto: '加密相关',
}

const REGION_OF_TYPE: Record<string, Exclude<Region, 'all' | 'crypto'>> = {
  lpr: 'cn',
  cn_cpi: 'cn',
  cn_ppi: 'cn',
  cn_gdp: 'cn',
  cn_pmi: 'cn',
  cn_credit: 'cn',
  fomc: 'us',
  nfp: 'us',
  us_gdp: 'us',
  us_pce: 'us',
  ecb: 'eu',
  boj: 'jp',
}

// 来源标注(客观出处 · 与库 source 字段一一对应)
const SOURCE_LABEL: Record<string, string> = {
  fed_json: '美联储官网',
  bea_json: '美国经济分析局',
  rule: '官方惯例规则',
  seed: '官方年表·策展',
}

// ── 北京时间格式化(显式 Asia/Shanghai,不随访客本地时区漂移)─────────────────
const CST_TZ = 'Asia/Shanghai'

function cstParts(iso: string): { day: string; hm: string; weekday: string } {
  const d = new Date(iso)
  const fmt = new Intl.DateTimeFormat('zh-CN', {
    timeZone: CST_TZ,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    weekday: 'short',
    hour12: false,
  })
  const parts = Object.fromEntries(fmt.formatToParts(d).map((p) => [p.type, p.value]))
  return {
    day: `${parts.month}-${parts.day}`,
    hm: `${parts.hour}:${parts.minute}`,
    weekday: parts.weekday ?? '',
  }
}

/** CST 日历日序号(用于「今天/本周/未来」分组,纯日期比较) */
function cstDayNumber(date: Date): number {
  const fmt = new Intl.DateTimeFormat('en-CA', {
    timeZone: CST_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
  const [y, m, d] = fmt.format(date).split('-').map(Number)
  return Date.UTC(y, m - 1, d) / 86_400_000
}

/** CST 今天的 ISO 星期(1=周一 … 7=周日) */
function cstIsoWeekday(date: Date): number {
  const w = new Intl.DateTimeFormat('en-US', { timeZone: CST_TZ, weekday: 'short' }).format(date)
  return { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 7 }[w] ?? 1
}

const IMPORTANCE_CLASS: Record<number, string> = {
  3: 'text-midas-red',
  2: 'text-gold',
  1: 'text-muted-foreground',
}

function regionOf(ev: EconEvent): Exclude<Region, 'all' | 'crypto'> | null {
  return REGION_OF_TYPE[ev.event_type] ?? null
}

function matchesRegion(ev: EconEvent, region: Region): boolean {
  if (region === 'all') return true
  if (region === 'crypto') return ev.markets.includes('crypto')
  return regionOf(ev) === region
}

// ── 页面 ────────────────────────────────────────────────────────────────

export default function EconCalendarPage() {
  const [region, setRegion] = useState<Region>('all')
  const [majorOnly, setMajorOnly] = useState(false)

  const calendarQ = useQuery({
    queryKey: ['econ-calendar'],
    queryFn: ({ signal }) => fetchEconCalendar(signal),
    retry: 0,
    staleTime: 300_000, // 日程低频变化 · 5min 足够
  })

  const groups = useMemo(() => {
    // 防御性排序:不依赖 API 返回顺序的隐式契约(后端确实 ORDER BY,但页面自保)
    const events = (calendarQ.data?.events ?? [])
      .filter((ev) => matchesRegion(ev, region) && (!majorOnly || ev.importance >= 2))
      .sort((a, b) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at))
    const now = new Date()
    const today = cstDayNumber(now)
    const weekEnd = today + (7 - cstIsoWeekday(now)) // 本周日(CST)
    const buckets: { key: string; label: string; items: EconEvent[] }[] = [
      { key: 'today', label: '今天', items: [] },
      { key: 'week', label: '本周', items: [] },
      { key: 'later', label: '未来', items: [] },
    ]
    for (const ev of events) {
      const d = cstDayNumber(new Date(ev.scheduled_at))
      if (d <= today) buckets[0].items.push(ev)
      else if (d <= weekEnd) buckets[1].items.push(ev)
      else buckets[2].items.push(ev)
    }
    return buckets.filter((b) => b.items.length > 0)
  }, [calendarQ.data, region, majorOnly])

  const updatedText = useMemo(() => {
    const iso = calendarQ.data?.updated_at
    if (!iso) return null
    const p = cstParts(iso)
    return `${p.day} ${p.hm}`
  }, [calendarQ.data])

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <TopNav />
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-6 py-6">
          {/* 标题 + 保鲜标注(last-run 口径) */}
          <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <h1 className="font-serif text-xl font-bold">财经日历</h1>
              <p className="mt-1 text-xs text-muted-foreground">
                官方宏观事件日程 · 时间均为北京时间 · 重大事件公布前后市场波动可能放大,供参考
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{updatedText ? `数据更新:${updatedText}` : '数据更新中'}</span>
              {calendarQ.data?.any_stale ? (
                <span className="rounded-full bg-surface-subtle px-2 py-0.5 text-[11px]">
                  部分数据更新中
                </span>
              ) : null}
            </div>
          </div>

          {/* 筛选:地区 + 重要度 */}
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="inline-flex rounded-lg border border-paper bg-surface-card p-0.5">
              {REGIONS.map((r) => (
                <button
                  key={r}
                  type="button"
                  onClick={() => setRegion(r)}
                  className={cn(
                    'whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                    region === r
                      ? 'bg-midas-red text-white shadow-sm'
                      : 'text-muted-foreground hover:text-midas-red',
                  )}
                >
                  {REGION_LABEL[r]}
                </button>
              ))}
            </div>
            <div className="inline-flex rounded-lg border border-paper bg-surface-card p-0.5">
              <button
                type="button"
                onClick={() => setMajorOnly(false)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  !majorOnly
                    ? 'bg-midas-red text-white shadow-sm'
                    : 'text-muted-foreground hover:text-midas-red',
                )}
              >
                全部重要度
              </button>
              <button
                type="button"
                onClick={() => setMajorOnly(true)}
                className={cn(
                  'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  majorOnly
                    ? 'bg-midas-red text-white shadow-sm'
                    : 'text-muted-foreground hover:text-midas-red',
                )}
              >
                仅重要 ★2+
              </button>
            </div>
          </div>

          {/* 三态:加载 / 错误 / 内容(空态友好) */}
          {calendarQ.isPending ? (
            <div className="rounded-xl border border-paper bg-cream p-8 text-center text-sm text-muted-foreground">
              日程加载中…
            </div>
          ) : calendarQ.isError ? (
            <div className="rounded-xl border border-paper bg-cream p-8 text-center text-sm text-muted-foreground">
              日历加载失败,请稍后刷新重试
            </div>
          ) : groups.length === 0 ? (
            <div className="rounded-xl border border-paper bg-cream p-8 text-center text-sm text-muted-foreground">
              该筛选条件下暂无日程,试试切换地区或重要度
            </div>
          ) : (
            <div className="space-y-6">
              {groups.map((g) => (
                <section key={g.key}>
                  <h2 className="mb-2 font-serif text-base font-bold">
                    {g.label}
                    <span className="ml-2 font-sans text-xs font-normal text-muted-foreground">
                      {g.items.length} 项
                    </span>
                  </h2>
                  <div className="overflow-hidden rounded-xl border border-paper bg-cream">
                    {g.items.map((ev, i) => {
                      const t = cstParts(ev.scheduled_at)
                      const r = regionOf(ev)
                      return (
                        <div
                          key={ev.event_key}
                          className={cn(
                            'flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3',
                            i > 0 && 'border-t border-paper',
                          )}
                        >
                          <span className="w-28 shrink-0 font-mono text-sm tabular-nums text-muted-foreground">
                            {t.day} {ev.time_confirmed ? t.hm : '时刻待定'}
                          </span>
                          <span className="w-10 shrink-0 text-xs text-muted-foreground">
                            {t.weekday}
                          </span>
                          <span
                            className={cn(
                              'w-12 shrink-0 text-sm tracking-widest',
                              IMPORTANCE_CLASS[ev.importance] ?? 'text-muted-foreground',
                            )}
                            aria-label={`重要度 ${ev.importance} 星`}
                          >
                            {'★'.repeat(Math.max(1, Math.min(3, ev.importance)))}
                          </span>
                          {/* min-w:窄屏时整体换行到下一行,而不是被挤成竖排逐字断行 */}
                          <span className="min-w-[14rem] flex-1 text-sm font-medium">
                            {ev.title}
                          </span>
                          {r ? (
                            <span className="rounded-full bg-surface-subtle px-2 py-0.5 text-[11px] text-muted-foreground">
                              {REGION_LABEL[r]}
                            </span>
                          ) : null}
                          {ev.markets.includes('crypto') ? (
                            <span className="rounded-full bg-surface-subtle px-2 py-0.5 text-[11px] text-muted-foreground">
                              加密相关
                            </span>
                          ) : null}
                          <span className="text-[11px] text-muted-foreground/70">
                            {SOURCE_LABEL[ev.source] ?? ev.source}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}

          {/* 免责(完整口径 · 红线) */}
          <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
            以上为官方公开日程的客观展示,发布时间以各官方机构最终公布为准;标注「时刻待定」「以官方为准」的条目为窗口或惯例推算。仅供参考,不构成投资建议。
          </p>
        </div>
      </main>
    </div>
  )
}
