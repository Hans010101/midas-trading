'use client'

/**
 * 网站访问看板(admin · 纯只读)· PV/UV 趋势 + 注册增长趋势。
 *
 * ★ 安全边界在后端 AdminDep(403):本页数据全来自 admin API,普通用户手输 URL → 后端 403
 *   → 无权限降级提示(不渲染空表)。middleware 只兜「未登录跳登录」。
 * 访问数据自上线起累积、历史不可回溯(部署前无访问日志);注册趋势用 user.created_at 可回溯。
 * 取数走 fetchAdminVisitStats(token 透传 · 否则后端 401)。
 */

import { useQuery } from '@tanstack/react-query'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import { AdminApiError, fetchAdminVisitStats } from '@/lib/api/admin'

const RANGES = [7, 30, 90] as const
const RED = '#C8102E'
const GOLD = '#B8860B'

function mmdd(d: string): string {
  return d.length >= 10 ? d.slice(5) : d // yyyy-mm-dd → mm-dd
}

function Delta({ today, yest }: { today: number; yest: number }) {
  const diff = today - yest
  if (diff === 0) {
    return <span className="text-xs text-muted-foreground">较昨日持平</span>
  }
  const up = diff > 0
  return (
    <span className={up ? 'text-xs text-up' : 'text-xs text-down'}>
      {up ? '▲' : '▼'} {Math.abs(diff).toLocaleString()} 较昨日
    </span>
  )
}

function StatCard({
  label,
  value,
  sub,
}: {
  label: string
  value: number
  sub?: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-4 shadow-sm">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-2xl font-bold text-foreground">
        {value.toLocaleString()}
      </p>
      {sub && <div className="mt-1">{sub}</div>}
    </div>
  )
}

const TOOLTIP_STYLE = {
  background: '#FCFCF9',
  border: '1px solid #EDEAE0',
  borderRadius: 8,
  fontSize: 12,
}

export default function AdminVisitStatsPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const [days, setDays] = useState<number>(30)

  const query = useQuery({
    queryKey: ['admin-visit-stats', days],
    queryFn: ({ signal }) => fetchAdminVisitStats(token, days, signal),
    enabled: token !== '',
  })

  const forbidden = query.error instanceof AdminApiError && query.error.status === 403
  const d = query.data

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <h1 className="mb-4 font-serif text-xl font-bold">访问看板</h1>
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
              <span className="text-xs text-muted-foreground">区间</span>
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

            {/* 统计卡 */}
            <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatCard
                label="今日 PV(浏览量)"
                value={d?.today.pv ?? 0}
                sub={d ? <Delta today={d.today.pv} yest={d.yesterday.pv} /> : null}
              />
              <StatCard
                label="今日 UV(访客数)"
                value={d?.today.uv ?? 0}
                sub={d ? <Delta today={d.today.uv} yest={d.yesterday.uv} /> : null}
              />
              <StatCard
                label="累计 PV"
                value={d?.cumulative_pv ?? 0}
                sub={<span className="text-xs text-muted-foreground">自上线起</span>}
              />
              <StatCard
                label="累计注册用户"
                value={d?.total_registrations ?? 0}
                sub={<span className="text-xs text-muted-foreground">全历史</span>}
              />
            </div>

            {/* PV / UV 趋势 */}
            <section className="mb-4 rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-serif text-sm font-bold">访问趋势 · PV / UV</h2>
                <div className="flex gap-3 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: RED }} />
                    PV
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: GOLD }} />
                    UV
                  </span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={d?.daily ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
                  <XAxis dataKey="date" tickFormatter={mmdd} fontSize={10} tick={{ fill: '#94949C' }} minTickGap={20} />
                  <YAxis fontSize={10} tick={{ fill: '#94949C' }} allowDecimals={false} width={36} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="pv" name="PV" stroke={RED} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="uv" name="UV" stroke={GOLD} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </section>

            {/* 注册增长趋势 */}
            <section className="mb-4 rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <h2 className="mb-3 font-serif text-sm font-bold">注册增长 · 每日新增</h2>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={d?.registrations ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F7F6F1" />
                  <XAxis dataKey="date" tickFormatter={mmdd} fontSize={10} tick={{ fill: '#94949C' }} minTickGap={20} />
                  <YAxis fontSize={10} tick={{ fill: '#94949C' }} allowDecimals={false} width={36} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Line type="monotone" dataKey="count" name="注册" stroke={RED} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </section>

            {query.status === 'pending' && (
              <p className="text-center text-xs text-muted-foreground/60">加载中…</p>
            )}

            <p className="mt-2 text-xs leading-relaxed text-muted-foreground/70">
              说明:访问数据(PV/UV)自本功能上线起累积、历史不可回溯,初期曲线较短属正常;
              注册趋势基于用户注册时间,可回溯长期。统计仅用匿名计数,不含个人身份信息。
            </p>
          </>
        )}
      </main>
    </div>
  )
}
