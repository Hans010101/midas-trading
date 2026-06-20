'use client'

/**
 * 训练营「答题赢会员」统计(admin · 纯只读)· B 期刀4。
 *
 * ★ 安全边界在后端 AdminDep(403):数据全来自 admin API,普通用户手输 URL → 后端 403 → 降级提示。
 * 聚合刀1-3 三表:学习进度 / 结业测验成绩 / 发会员记录。对齐访问看板范式(StatCard + recharts + 红金配色)。
 */

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import { ACADEMY_STAGES } from '@/content/academy/manifest'
import { AdminApiError, fetchAdminAcademyStats } from '@/lib/api/admin'

const RANGES = [7, 30, 90] as const
const RED = '#C8102E'
const GOLD = '#B8860B'
const GREEN = '#0F6E5F'

const STAGE_NAME: Record<string, string> = Object.fromEntries(
  ACADEMY_STAGES.map((s) => [s.slug, s.name]),
)

function mmdd(d: string): string {
  return d.length >= 10 ? d.slice(5) : d
}

const TOOLTIP_STYLE = {
  background: '#FCFCF9',
  border: '1px solid #EDEAE0',
  borderRadius: 8,
  fontSize: 12,
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string
  value: string | number
  sub?: string
}) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-2xl font-bold text-foreground">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </p>
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

export default function AdminAcademyStatsPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const [days, setDays] = useState<number>(30)

  const query = useQuery({
    queryKey: ['admin-academy-stats', days],
    queryFn: ({ signal }) => fetchAdminAcademyStats(token, days, signal),
    enabled: token !== '',
  })

  const forbidden = query.error instanceof AdminApiError && query.error.status === 403
  const d = query.data

  const stageData = (d?.by_stage ?? []).map((s) => ({
    name: STAGE_NAME[s.stage] ?? s.stage,
    达标人数: s.passers,
    发会员人次: s.awards,
  }))
  const trendData = (d?.award_trend ?? []).map((a, i) => ({
    date: a.date,
    发会员: a.count,
    提交: d?.submission_trend[i]?.count ?? 0,
  }))

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <h1 className="mb-4 font-serif text-xl font-bold">训练营统计</h1>
        <AdminNav />

        {forbidden ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center shadow-sm">
            <p className="text-sm text-muted-foreground">该页面仅管理员可见。</p>
            <Link
              href="/global"
              className="mt-3 inline-block rounded-md bg-midas-red px-4 py-1.5 text-sm text-white transition-colors hover:bg-midas-red/90"
            >
              返回首页
            </Link>
          </div>
        ) : query.status === 'error' ? (
          <div className="rounded-lg border border-paper bg-cream p-8 text-center text-sm text-muted-foreground shadow-sm">
            加载失败,请稍后重试。
          </div>
        ) : (
          <>
            {/* 区间切换 */}
            <div className="mb-4 flex items-center gap-2">
              <span className="text-xs text-muted-foreground">趋势区间</span>
              <div className="flex overflow-hidden rounded-md border border-paper text-sm">
                {RANGES.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setDays(r)}
                    className={
                      days === r
                        ? 'bg-midas-red px-3 py-1.5 font-medium text-white'
                        : 'px-3 py-1.5 text-muted-foreground transition-colors hover:bg-midas-red-glow/50'
                    }
                  >
                    {r} 天
                  </button>
                ))}
              </div>
            </div>

            {/* 总览统计卡(全历史)*/}
            <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
              <StatCard label="有学习记录人数" value={d?.learner_count ?? 0} sub="标记过学完" />
              <StatCard label="结业达标人次" value={d?.total_awards ?? 0} sub="首次达标发会员数" />
              <StatCard
                label="送出会员天数"
                value={d?.membership_days_granted ?? 0}
                sub="= 人次 × 7 天"
              />
              <StatCard label="测验提交总数" value={d?.total_submissions ?? 0} sub="含重考" />
              <StatCard
                label="整体通过率"
                value={`${Math.round((d?.pass_rate ?? 0) * 100)}%`}
                sub="达标 / 总提交"
              />
            </div>

            {/* 各模块:达标人数 + 发会员人次(柱状对比)*/}
            <section className="mb-4 rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <h2 className="mb-3 font-serif text-sm font-bold">各模块 · 结业达标人数 / 发会员人次</h2>
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={stageData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
                  <XAxis dataKey="name" fontSize={10} tick={{ fill: '#94949C' }} interval={0} />
                  <YAxis fontSize={10} tick={{ fill: '#94949C' }} allowDecimals={false} width={36} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="达标人数" fill={GREEN} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="发会员人次" fill={GOLD} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </section>

            {/* 发会员 / 提交每日趋势 */}
            <section className="mb-4 rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <h2 className="mb-3 font-serif text-sm font-bold">每日趋势 · 发会员 / 测验提交</h2>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
                  <XAxis dataKey="date" tickFormatter={mmdd} fontSize={10} tick={{ fill: '#94949C' }} minTickGap={20} />
                  <YAxis fontSize={10} tick={{ fill: '#94949C' }} allowDecimals={false} width={36} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="发会员" stroke={GOLD} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="提交" stroke={RED} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </section>

            {query.status === 'pending' && (
              <p className="text-center text-xs text-muted-foreground/60">加载中…</p>
            )}

            <p className="mt-2 text-xs leading-relaxed text-muted-foreground/70">
              说明:总览为全历史累计;趋势按所选区间(CN 日)。「送出会员天数」= 结业达标人次 × 7
              天(每人每模块首次达标发 1 周会员,重考不重复发)。纯统计,不含个人身份信息。
            </p>
          </>
        )}
      </main>
    </div>
  )
}
