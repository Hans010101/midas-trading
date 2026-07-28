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
// ★「日韩」是合并桶(体例同「欧洲」= 多国合一):同出日本 BOJ + 韩国 BOK/KOSTAT,
//   但事件行右侧仍标各自国别(日本/韩国),用户看得出哪条是哪国。
const REGIONS = ['all', 'cn', 'us', 'eu', 'jpkr', 'crypto'] as const
type Region = (typeof REGIONS)[number]

const REGION_LABEL: Record<Region, string> = {
  all: '全部',
  cn: '中国',
  us: '美国',
  eu: '欧洲',
  jpkr: '日韩',
  crypto: '加密相关',
}

// event_type → 筛选桶(用于筛选匹配 · 合并桶把多国映到同一个 key)
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
  boj: 'jpkr',
  bok: 'jpkr',
  kr_cpi: 'jpkr',
  kr_employment: 'jpkr',
  kr_ind_activity: 'jpkr',
  jp_cpi: 'jpkr',
  jp_unemp: 'jpkr',
  jp_tankan: 'jpkr',
  // 欧洲四国(英/德/法/意)· IMF DSBB + BoE 种子 · 全归「欧洲」桶(英国按 Hans 定归欧洲)
  gb_cpi: 'eu',
  gb_gdp: 'eu',
  gb_unemp: 'eu',
  gb_boe: 'eu',
  de_cpi: 'eu',
  de_gdp: 'eu',
  de_unemp: 'eu',
  fr_cpi: 'eu',
  fr_gdp: 'eu',
  fr_unemp: 'eu',
  it_cpi: 'eu',
  it_gdp: 'eu',
  it_unemp: 'eu',
}

// event_type → 事件行右侧国别标注(只有合并桶内的类型需要覆盖 · 其余落桶标签)
const COUNTRY_LABEL_OF_TYPE: Record<string, string> = {
  boj: '日本',
  bok: '韩国',
  kr_cpi: '韩国',
  kr_employment: '韩国',
  kr_ind_activity: '韩国',
  jp_cpi: '日本',
  jp_unemp: '日本',
  jp_tankan: '日本',
  // 欧洲桶内单条标各自国别(同 jpkr 桶范式)· ECB 保持「欧元区」不覆盖(落桶标签「欧洲」)
  gb_cpi: '英国',
  gb_gdp: '英国',
  gb_unemp: '英国',
  gb_boe: '英国',
  de_cpi: '德国',
  de_gdp: '德国',
  de_unemp: '德国',
  fr_cpi: '法国',
  fr_gdp: '法国',
  fr_unemp: '法国',
  it_cpi: '意大利',
  it_gdp: '意大利',
  it_unemp: '意大利',
}

// 来源标注(客观出处 · 与库 source 字段一一对应)
const SOURCE_LABEL: Record<string, string> = {
  fed_json: '美联储官网',
  bea_json: '美国经济分析局',
  kostat: '韩国国家数据处',
  jp_estat: '日本总务省统计局',
  boj_xlsx: '日本银行',
  dsbb: 'IMF 数据标准公报',
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

// 事件行右侧国别标注:合并桶(日韩)内单条仍标各自国别;其余落桶标签
function countryLabelOf(ev: EconEvent): string | null {
  const specific = COUNTRY_LABEL_OF_TYPE[ev.event_type]
  if (specific) return specific
  const bucket = regionOf(ev)
  return bucket ? REGION_LABEL[bucket] : null
}

function matchesRegion(ev: EconEvent, region: Region): boolean {
  if (region === 'all') return true
  if (region === 'crypto') return ev.markets.includes('crypto')
  return regionOf(ev) === region
}

// ── 页面 ────────────────────────────────────────────────────────────────

export default function EconCalendarPage() {
  const [region, setRegion] = useState<Region>('all')

  const calendarQ = useQuery({
    queryKey: ['econ-calendar'],
    queryFn: ({ signal }) => fetchEconCalendar(signal),
    retry: 0,
    staleTime: 300_000, // 日程低频变化 · 5min 足够
    // 页签长开自愈:全局关了 refetchOnWindowFocus,无此项则跨 CST 午夜数据/分组永久冻结
    refetchInterval: 15 * 60_000,
  })

  const groups = useMemo(() => {
    const now = new Date()
    const today = cstDayNumber(now)
    const weekEnd = today + (7 - cstIsoWeekday(now)) // 本周日(CST)
    // 该地区今天起的全部事件(展示全 · 无重要度过滤)· 排序防御(不依赖 API 顺序隐式契约)
    const events = (calendarQ.data?.events ?? [])
      .filter((ev) => matchesRegion(ev, region) && cstDayNumber(new Date(ev.scheduled_at)) >= today)
      .sort((a, b) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at))
    const buckets: { key: string; label: string; items: EconEvent[] }[] = [
      { key: 'today', label: '今天', items: [] },
      { key: 'week', label: '本周', items: [] },
      { key: 'later', label: '未来', items: [] },
    ]
    for (const ev of events) {
      const d = cstDayNumber(new Date(ev.scheduled_at))
      if (d === today) buckets[0].items.push(ev)
      else if (d <= weekEnd) buckets[1].items.push(ev)
      else buckets[2].items.push(ev)
    }
    return buckets.filter((b) => b.items.length > 0)
  }, [calendarQ.data, region])

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
          {/* 筛选(仅地区)+ 保鲜标注(last-run 口径)。页内不设大标题:导航 Tab 已有同名入口 */}
          <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
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

          {/* 说明句(红线文案的一部分 · 一字不改,仅从页顶挪到筛选行下方) */}
          <p className="mb-5 text-xs text-muted-foreground">
            官方宏观事件日程 · 时间均为北京时间 · 重大事件公布前后市场波动可能放大,供参考
          </p>

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
              该地区近期暂无日程,试试切换地区
            </div>
          ) : (
            <div className="space-y-6">
              {groups.map((g) => (
                <section key={g.key}>
                  {/* 「今天/本周」保留(紧迫度信号有值);「未来」是冗余 catch-all 标题——
                      列表已按时间排序、每条带日期,无信息价值 → 删(同删「N 项」计数道理) */}
                  {g.key !== 'later' && (
                    <h2 className="mb-2 font-serif text-base font-bold">{g.label}</h2>
                  )}
                  <div className="overflow-hidden rounded-xl border border-paper bg-cream">
                    {g.items.map((ev, i) => {
                      const t = cstParts(ev.scheduled_at)
                      const country = countryLabelOf(ev)
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
                          {country ? (
                            <span className="rounded-full bg-surface-subtle px-2 py-0.5 text-[11px] text-muted-foreground">
                              {country}
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

          <p className="mt-6 text-xs leading-relaxed text-muted-foreground">
            发布时间以各官方机构最终公布为准；标注「时刻待定」「以官方为准」的条目为窗口或惯例推算。
          </p>
        </div>
      </main>
    </div>
  )
}
