'use client'

/**
 * 管理员 · 托管交易(策略前向测试)看板(托管交易 PR-4)。
 *
 * 🔴 安全边界后端 AdminDep(403)· 🔴纯虚拟绝不真单(用做T信号在虚拟账户自动开/平仓做前向测试)。
 * 控制(开关)+ 当前活仓(浮盈)+ 历史平仓(每单明细)+ 前向测试统计(胜率/盈亏比/最大回撤/按原因)。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  closeManagedPosition,
  getManagedHistory,
  getManagedPositions,
  getManagedStats,
  getManagedStatus,
  setManagedExitSwitch,
  setManagedMaxPositions,
  setManagedOpenLeverage,
  setManagedOpenMargin,
  setManagedTpPct,
  toggleManaged,
} from '@/lib/api/managed'
import { useSession } from 'next-auth/react'

const REASON_LABEL: Record<string, string> = {
  tp: '止盈',
  signal: '信号转换',
  timeout: '超时',
  manual: '手动',
}

function pnlTone(v: number): string {
  return v > 0 ? 'text-rose-600' : v < 0 ? 'text-emerald-700' : 'text-muted-foreground'
}

// ★信号上色(Hans:偏空红 / 中性黄 / 偏多绿 · 西式多绿空红)
function biasTone(bias: string): string {
  return bias === '偏空' ? 'text-rose-600' : bias === '偏多' ? 'text-emerald-700' : 'text-gold'
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

  // ★手动平单二次确认偏好(纯前端 localStorage · 默认开 · 可关)
  const [confirmClose, setConfirmClose] = useState(true)
  useEffect(() => {
    setConfirmClose(localStorage.getItem('managed:confirmClose') !== '0')
  }, [])
  const toggleConfirmClose = () => {
    setConfirmClose((prev) => {
      const next = !prev
      localStorage.setItem('managed:confirmClose', next ? '1' : '0')
      return next
    })
  }

  // ★手动平单(人工应急出口)· 二次确认可关(confirmClose)
  const closeMut = useMutation({
    mutationFn: (id: number) => closeManagedPosition(token, id),
    onSuccess: (r) => {
      setNote(`✓ 手动平仓 ${r.symbol ?? ''} · 盈亏 ${r.realized_pnl != null ? r.realized_pnl.toFixed(2) : '—'} U`)
      invalidate()
    },
    onError: () => setNote('平仓失败,请重试'),
  })
  const onClose = (id: number, symbol: string) => {
    if (confirmClose) {
      const ok = window.confirm(
        `确定手动平仓【${symbol}】?\n\n会立即按当前标记价平掉该托管仓位(记为「手动」平仓)。\n🔴纯虚拟资金。`,
      )
      if (!ok) return
    }
    closeMut.mutate(id)
  }

  // ★三个平仓条件开关(即时生效 · close_scan 下一轮按新开关判)
  const exitMut = useMutation({
    mutationFn: (v: { which: 'tp' | 'signal' | 'timeout'; on: boolean }) =>
      setManagedExitSwitch(token, v.which, v.on),
    onSuccess: () => invalidate(),
    onError: () => setNote('开关切换失败,请重试'),
  })

  // ★止盈目标(盈利%·即时生效)
  const tpPctMut = useMutation({
    mutationFn: (pct: number) => setManagedTpPct(token, pct),
    onSuccess: (s) => {
      setNote(`✓ 止盈目标 ${s.tp_pct}%(盈利)= 价涨 ${(s.tp_pct / 5).toFixed(1)}%`)
      invalidate()
    },
    onError: () => setNote('止盈目标更新失败,请重试'),
  })

  // ★开仓参数(每单本金 / 杠杆 / 最大单数 · 即时生效 · 失焦保存)
  const marginMut = useMutation({
    mutationFn: (margin: number) => setManagedOpenMargin(token, margin),
    onSuccess: (s) => {
      setNote(`✓ 每单本金 ${s.open_margin} U`)
      invalidate()
    },
    onError: () => setNote('每单本金更新失败(需 10-10000)'),
  })
  const leverageMut = useMutation({
    mutationFn: (lev: number) => setManagedOpenLeverage(token, lev),
    onSuccess: (s) => {
      setNote(`✓ 杠杆 ${s.open_leverage}x`)
      invalidate()
    },
    onError: () => setNote('杠杆更新失败(需 1-20)'),
  })
  const maxPosMut = useMutation({
    mutationFn: (n: number) => setManagedMaxPositions(token, n),
    onSuccess: (s) => {
      setNote(`✓ 最大总持仓 ${s.max_positions} 单`)
      invalidate()
    },
    onError: () => setNote('最大单数更新失败(需 > 0)'),
  })

  const forbidden = status.isError
  const st = status.data
  const stat = stats.data

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
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
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {/* ★账户价值(权益·浮动)为主角 · = 现金 + Σ浮盈 · 和下面活仓浮盈对得上
                    (去掉「账户现金」· 活仓 0 时与账户价值相等、重复 · 账户价值含浮盈更有意义)*/}
                <StatCard
                  label="账户价值(权益)"
                  value={st ? `${st.account_value.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'}
                  tone={st ? pnlTone(st.account_value - st.initial_capital) : undefined}
                />
                <StatCard
                  label="可用资金"
                  value={st ? `${st.available_funds.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'}
                  tone="text-gold"
                />
                <StatCard
                  label="阶段盈亏"
                  value={
                    st
                      ? `${st.account_value - st.initial_capital >= 0 ? '+' : ''}${(st.account_value - st.initial_capital).toFixed(2)} U`
                      : '—'
                  }
                  tone={st ? pnlTone(st.account_value - st.initial_capital) : undefined}
                />
                <StatCard label="已占保证金" value={st ? `${st.occupied_margin.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'} />
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
              {/* ★三个平仓条件开关(Hans 补充 · 即时生效) */}
              <div className="mt-3 border-t border-paper pt-3">
                <div className="mb-2 text-xs text-muted-foreground">
                  自动平仓条件(关 = 该条件不触发 · 即时对已有持仓生效)
                </div>
                <div className="flex flex-wrap gap-2">
                  {[
                    { which: 'tp' as const, label: `止盈 ${st?.tp_pct ?? 100}%`, val: st?.exit_tp ?? true },
                    { which: 'signal' as const, label: '信号转换', val: st?.exit_signal ?? true },
                    { which: 'timeout' as const, label: '超时 24h', val: st?.exit_timeout ?? true },
                  ].map((s) => (
                    <button
                      key={s.which}
                      type="button"
                      onClick={() => exitMut.mutate({ which: s.which, on: !s.val })}
                      disabled={exitMut.isPending || !on}
                      className={
                        s.val
                          ? 'rounded-md border border-emerald-600/40 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-700 disabled:opacity-50'
                          : 'rounded-md border border-paper bg-muted px-3 py-1 text-xs text-muted-foreground disabled:opacity-50'
                      }
                    >
                      {s.label} · {s.val ? '开' : '关'}
                    </button>
                  ))}
                </div>
                {st && !st.exit_tp && !st.exit_signal && !st.exit_timeout && (
                  <p className="mt-2 rounded-md bg-rose-50 px-3 py-2 text-xs font-medium text-rose-600">
                    ⚠️ 自动平仓已全部关闭,持仓单仅能手动平仓
                  </p>
                )}
                {/* ★止盈目标(盈利%·Hans 可调)· 口径=盈利%(保证金赚%)≠价格% · 仅止盈开关开时生效 */}
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-muted-foreground">止盈目标(盈利%):</span>
                  <input
                    key={st?.tp_pct ?? 100}
                    type="number"
                    min={1}
                    defaultValue={st?.tp_pct ?? 100}
                    disabled={!on || tpPctMut.isPending}
                    onBlur={(e) => {
                      const v = Number.parseInt(e.currentTarget.value, 10)
                      if (Number.isFinite(v) && v > 0 && v !== (st?.tp_pct ?? 100)) tpPctMut.mutate(v)
                    }}
                    className="w-16 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                  />
                  <span className="text-muted-foreground">
                    % · = 价涨 {((st?.tp_pct ?? 100) / 5).toFixed(1)}%(盈利%÷5倍杠杆 · 失焦保存)
                  </span>
                </div>
                {/* ★开仓参数(每单本金 / 杠杆 / 最大单数 · Hans 可调 · 失焦保存 · 即时生效) */}
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-paper pt-3 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">每单本金:</span>
                    <input
                      key={`m${st?.open_margin ?? 100}`}
                      type="number"
                      min={10}
                      max={10000}
                      defaultValue={st?.open_margin ?? 100}
                      disabled={!on || marginMut.isPending}
                      onBlur={(e) => {
                        const v = Number.parseFloat(e.currentTarget.value)
                        if (Number.isFinite(v) && v >= 10 && v <= 10000 && v !== (st?.open_margin ?? 100))
                          marginMut.mutate(v)
                      }}
                      className="w-20 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                    />
                    <span className="text-muted-foreground">U(10-10000)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">杠杆:</span>
                    <input
                      key={`l${st?.open_leverage ?? 5}`}
                      type="number"
                      min={1}
                      max={20}
                      defaultValue={st?.open_leverage ?? 5}
                      disabled={!on || leverageMut.isPending}
                      onBlur={(e) => {
                        const v = Number.parseInt(e.currentTarget.value, 10)
                        if (Number.isFinite(v) && v >= 1 && v <= 20 && v !== (st?.open_leverage ?? 5))
                          leverageMut.mutate(v)
                      }}
                      className="w-16 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                    />
                    <span className="text-muted-foreground">x(1-20)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">最大单数:</span>
                    <input
                      key={`p${st?.max_positions ?? 50}`}
                      type="number"
                      min={1}
                      defaultValue={st?.max_positions ?? 50}
                      disabled={!on || maxPosMut.isPending}
                      onBlur={(e) => {
                        const v = Number.parseInt(e.currentTarget.value, 10)
                        if (Number.isFinite(v) && v > 0 && v !== (st?.max_positions ?? 50))
                          maxPosMut.mutate(v)
                      }}
                      className="w-20 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                    />
                    <span className="text-muted-foreground">单(到上限不开新 · 失焦保存)</span>
                  </div>
                </div>
                {/* ★手动平单二次确认开关(纯前端偏好 · localStorage) */}
                <div className="mt-2 flex items-center gap-2 text-xs">
                  <span className="text-muted-foreground">平仓需二次确认:</span>
                  <button
                    type="button"
                    onClick={toggleConfirmClose}
                    className={
                      confirmClose
                        ? 'rounded-md border border-emerald-600/40 bg-emerald-50 px-3 py-1 font-medium text-emerald-700'
                        : 'rounded-md border border-paper bg-muted px-3 py-1 text-muted-foreground'
                    }
                  >
                    {confirmClose ? '开(防误点)' : '关(直接平)'}
                  </button>
                </div>
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
                label="止盈/信号/超时/手动"
                value={
                  stat
                    ? `${stat.by_reason.tp}/${stat.by_reason.signal}/${stat.by_reason.timeout}/${stat.by_reason.manual}`
                    : '—'
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
                    {['币种', '杠杆', '开仓价', '标记价', '信号', '浮盈U', '浮盈%', '操作'].map((h) => (
                      <th key={h} className="px-3 py-2 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(positions.data ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-3 py-4 text-center text-muted-foreground">
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
                        <td className="px-3 py-2">
                          {/* ★实时信号(维持的 bias)· 偏空红/中性黄/偏多绿 */}
                          {p.bias ? (
                            <span className={`font-medium ${biasTone(p.bias)}`}>{p.bias}</span>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className={`px-3 py-2 font-mono ${p.unrealized_pnl != null ? pnlTone(p.unrealized_pnl) : ''}`}>
                          {p.unrealized_pnl != null ? p.unrealized_pnl.toFixed(2) : '—'}
                        </td>
                        <td className={`px-3 py-2 font-mono ${p.unrealized_pct != null ? pnlTone(p.unrealized_pct) : ''}`}>
                          {p.unrealized_pct != null ? `${(p.unrealized_pct * 100).toFixed(1)}%` : '—'}
                        </td>
                        <td className="px-3 py-2">
                          {/* ★手动平单 · 人工应急出口 · 二次确认防误点 */}
                          <button
                            type="button"
                            onClick={() => onClose(p.id, p.symbol)}
                            disabled={closeMut.isPending}
                            className="rounded border border-paper px-2 py-1 text-xs font-medium text-midas-red hover:bg-midas-red/10 disabled:opacity-50"
                          >
                            平仓
                          </button>
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
