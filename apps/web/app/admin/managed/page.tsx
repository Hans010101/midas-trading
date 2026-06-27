'use client'

/**
 * 管理员 · 托管交易(策略前向测试)看板(托管交易 PR-4)。
 *
 * 🔴 安全边界后端 AdminDep(403)· 🔴纯虚拟绝不真单(用做T信号在虚拟账户自动开/平仓做前向测试)。
 * 控制(开关)+ 当前活仓(浮盈)+ 历史平仓(每单明细)+ 前向测试统计(胜率/盈亏比/最大回撤/按原因)。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  getManagedHistory,
  getManagedPositions,
  getManagedStats,
  getManagedStatus,
  toggleManaged,
} from '@/lib/api/managed'
import { useSession } from 'next-auth/react'

const REASON_LABEL: Record<string, string> = {
  tp: '止盈',
  signal: '信号转换',
  timeout: '超时',
}

function pnlTone(v: number): string {
  return v > 0 ? 'text-rose-600' : v < 0 ? 'text-emerald-700' : 'text-muted-foreground'
}

function StatCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-3 shadow-sm">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg font-bold ${tone ?? 'text-foreground'}`}>{value}</div>
    </div>
  )
}

export default function AdminManagedPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const on = token !== ''

  const status = useQuery({
    queryKey: ['managed-status'],
    queryFn: ({ signal }) => getManagedStatus(token, signal),
    enabled: on,
    refetchInterval: 15000,
  })
  const positions = useQuery({
    queryKey: ['managed-positions'],
    queryFn: ({ signal }) => getManagedPositions(token, signal),
    enabled: on,
    refetchInterval: 15000,
  })
  const history = useQuery({
    queryKey: ['managed-history'],
    queryFn: ({ signal }) => getManagedHistory(token, signal),
    enabled: on,
  })
  const stats = useQuery({
    queryKey: ['managed-stats'],
    queryFn: ({ signal }) => getManagedStats(token, signal),
    enabled: on,
  })

  const invalidate = () => {
    for (const k of ['managed-status', 'managed-positions', 'managed-history', 'managed-stats'])
      void qc.invalidateQueries({ queryKey: [k] })
  }

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => toggleManaged(token, enabled),
    onSuccess: (s) => {
      setNote(s.enabled ? '✓ 托管交易已开启 · 自动开/平仓做前向测试' : '托管交易已关闭(已有持仓仍会被监控平仓)')
      invalidate()
    },
    onError: () => setNote('操作失败,请重试'),
  })

  const enabled = status.data?.enabled ?? false
  const onToggle = () => {
    if (!enabled) {
      const ok = window.confirm(
        '确定开启【托管交易】(策略前向测试)?\n\n开启后:用做T偏多信号在【虚拟账户】自动开仓(只做多/100U/5x/全仓)、' +
          '止盈100%(涨20%)/信号转换/24h超时自动平仓。\n🔴纯虚拟资金,绝不接真实交易。\n\n确定开启?',
      )
      if (!ok) return
    }
    toggle.mutate(!enabled)
  }

  const forbidden = status.isError
  const st = status.data
  const stat = stats.data

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-4xl px-6 py-8">
        <h1 className="mb-4 font-serif text-xl font-bold">托管交易 · 策略前向测试</h1>
        <AdminNav />

        {forbidden ? (
          <p className="py-8 text-center text-sm text-muted-foreground">该页面仅管理员可见。</p>
        ) : (
          <>
            {/* 控制 + 账户 */}
            <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <div className="mb-3 flex items-center gap-2">
                <span className="font-serif text-base font-bold">控制台</span>
                <span
                  className={
                    enabled
                      ? 'rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700'
                      : 'rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground'
                  }
                >
                  ● {enabled ? '运行中' : '已关闭'}
                </span>
                <span className="ml-auto rounded bg-gold/10 px-2 py-0.5 text-[11px] text-gold">
                  🔴 纯虚拟资金 · 绝不真实下单
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard label="开关" value={enabled ? '开启' : '关闭'} />
                <StatCard
                  label="账户现金"
                  value={st ? `${st.cash_balance.toLocaleString()} U` : '—'}
                  tone="text-gold"
                />
                <StatCard label="起始资金" value={st ? `${st.initial_capital.toLocaleString()} U` : '—'} />
                <StatCard label="当前活仓" value={st ? `${st.open_positions}` : '—'} />
              </div>
              <div className="mt-4 flex items-center gap-2 border-t border-paper pt-3">
                <button
                  type="button"
                  onClick={onToggle}
                  disabled={toggle.isPending || !on}
                  className={
                    enabled
                      ? 'rounded-md border border-paper px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground disabled:opacity-50'
                      : 'rounded-md bg-midas-red px-4 py-1.5 text-sm font-medium text-white hover:bg-midas-red/90 disabled:opacity-50'
                  }
                >
                  {toggle.isPending ? '处理中…' : enabled ? '关闭托管交易' : '开启托管交易'}
                </button>
                {enabled && (
                  <span className="text-xs text-muted-foreground">
                    关闭只停新开仓 · 已有持仓仍被监控平仓
                  </span>
                )}
              </div>
              {note && (
                <p className="mt-3 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">{note}</p>
              )}
            </div>

            {/* 前向测试统计 */}
            <h2 className="mb-2 font-serif text-base font-bold">前向测试统计</h2>
            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="总交易" value={stat ? `${stat.total_trades}` : '—'} />
              <StatCard
                label="胜率"
                value={stat ? `${(stat.win_rate * 100).toFixed(1)}%` : '—'}
              />
              <StatCard
                label="总盈亏"
                value={stat ? `${stat.total_pnl.toFixed(2)} U` : '—'}
                tone={stat ? pnlTone(stat.total_pnl) : undefined}
              />
              <StatCard
                label="平均盈亏"
                value={stat ? `${stat.avg_pnl.toFixed(2)} U` : '—'}
                tone={stat ? pnlTone(stat.avg_pnl) : undefined}
              />
              <StatCard
                label="盈亏比"
                value={stat ? (stat.profit_factor > 0 ? stat.profit_factor.toFixed(2) : '∞/—') : '—'}
              />
              <StatCard label="最大回撤" value={stat ? `${stat.max_drawdown.toFixed(2)} U` : '—'} />
              <StatCard
                label="止盈 / 信号 / 超时"
                value={
                  stat ? `${stat.by_reason.tp} / ${stat.by_reason.signal} / ${stat.by_reason.timeout}` : '—'
                }
              />
              <StatCard label="盈 / 亏" value={stat ? `${stat.wins} / ${stat.losses}` : '—'} />
            </div>

            {/* 当前活仓 */}
            <h2 className="mb-2 font-serif text-base font-bold">
              当前活仓 {positions.data ? `(${positions.data.length})` : ''}
            </h2>
            <div className="mb-6 overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-paper text-muted-foreground">
                  <tr>
                    {['币种', '杠杆', '开仓价', '标记价', '浮盈U', '浮盈%'].map((h) => (
                      <th key={h} className="px-3 py-2 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(positions.data ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-3 py-4 text-center text-muted-foreground">
                        无活仓
                      </td>
                    </tr>
                  ) : (
                    positions.data?.map((p) => (
                      <tr key={p.symbol} className="border-b border-paper/60">
                        <td className="px-3 py-2 font-mono font-bold">{p.symbol}</td>
                        <td className="px-3 py-2">{p.leverage}x</td>
                        <td className="px-3 py-2 font-mono">{p.entry_price}</td>
                        <td className="px-3 py-2 font-mono">{p.mark ?? '—'}</td>
                        <td className={`px-3 py-2 font-mono ${p.unrealized_pnl != null ? pnlTone(p.unrealized_pnl) : ''}`}>
                          {p.unrealized_pnl != null ? p.unrealized_pnl.toFixed(2) : '—'}
                        </td>
                        <td className={`px-3 py-2 font-mono ${p.unrealized_pct != null ? pnlTone(p.unrealized_pct) : ''}`}>
                          {p.unrealized_pct != null ? `${(p.unrealized_pct * 100).toFixed(1)}%` : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* 历史平仓 */}
            <h2 className="mb-2 font-serif text-base font-bold">
              历史平仓 {history.data ? `(${history.data.length})` : ''}
            </h2>
            <div className="overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-paper text-muted-foreground">
                  <tr>
                    {['币种', '开仓价', '平仓价', '盈亏U', '盈亏%', '原因', '持仓时长'].map((h) => (
                      <th key={h} className="px-3 py-2 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(history.data ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-3 py-4 text-center text-muted-foreground">
                        还没有平仓记录
                      </td>
                    </tr>
                  ) : (
                    history.data?.map((t, i) => (
                      <tr key={`${t.symbol}-${i}`} className="border-b border-paper/60">
                        <td className="px-3 py-2 font-mono font-bold">{t.symbol}</td>
                        <td className="px-3 py-2 font-mono">{t.entry_price}</td>
                        <td className="px-3 py-2 font-mono">{t.exit_price.toFixed(4)}</td>
                        <td className={`px-3 py-2 font-mono ${pnlTone(t.pnl_usdt)}`}>{t.pnl_usdt.toFixed(2)}</td>
                        <td className={`px-3 py-2 font-mono ${pnlTone(t.pnl_pct)}`}>
                          {(t.pnl_pct * 100).toFixed(1)}%
                        </td>
                        <td className="px-3 py-2">
                          {t.close_reason ? (REASON_LABEL[t.close_reason] ?? t.close_reason) : '—'}
                        </td>
                        <td className="px-3 py-2 text-muted-foreground">
                          {Math.floor(t.hold_seconds / 3600)}h{Math.floor((t.hold_seconds % 3600) / 60)}m
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
