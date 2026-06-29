'use client'

/**
 * 管理员 · 智能交易(策略前向测试)看板(智能交易 PR-6 · 第一期收官)。
 *
 * 🔴 安全边界后端 AdminDep(403)· 🔴纯虚拟绝不真单(打分共振信号在虚拟账户自动开/平仓做前向测试)。
 * 控制(开关 + 账户管理)+ 总敞口/做多做空 + 当前活仓(浮盈 + 共振 + 止损止盈)+ 历史平仓 + 统计。
 * ★intelligent vs managed:做多做空(side)· 每仓 ATR 止损/止盈 + 共振明细 · 三退出(止损/止盈/信号反转)。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { AdminNav } from '@/components/admin/admin-nav'
import { TopNav } from '@/components/layout/top-nav'
import {
  getIntelligentHistory,
  getIntelligentPositions,
  getIntelligentStats,
  getIntelligentStatus,
  getIntelligentStrategyParams,
  INTELLIGENT_HISTORY_PAGE_SIZE,
  INTELLIGENT_POSITIONS_PAGE_SIZE,
  resetIntelligentAccount,
  setIntelligentCapital,
  setIntelligentMaxPositions,
  setIntelligentOpenLeverage,
  setIntelligentOpenMargin,
  setIntelligentStrategyParams,
  type StrategyParams,
  toggleIntelligent,
} from '@/lib/api/intelligent'
import { useSession } from 'next-auth/react'

const REASON_LABEL: Record<string, string> = {
  stop_loss: '止损',
  take_profit: '止盈',
  signal_reversal: '信号反转',
}

// 盈亏上色(涨红跌绿 · A 股 · 盈利红/亏损绿)
function pnlTone(v: number): string {
  return v > 0 ? 'text-rose-600' : v < 0 ? 'text-emerald-700' : 'text-muted-foreground'
}

// ★方向上色(做多绿 / 做空红 · 西式 · 与决策卡一致 · 与涨红跌绿解耦)
function sideTone(side: string): string {
  return side === 'long' ? 'text-emerald-700' : 'text-rose-600'
}
const sideLabel = (side: string): string => (side === 'long' ? '做多' : '做空')

// ★共振分上色(正偏多绿 / 负偏空红 / 0 中性金)
function scoreTone(v: number): string {
  return v > 0 ? 'text-emerald-700' : v < 0 ? 'text-rose-600' : 'text-gold'
}

function StatCard({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg border border-paper bg-cream p-3 shadow-sm">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-lg font-bold ${tone ?? 'text-foreground'}`}>{value}</div>
    </div>
  )
}

export default function AdminIntelligentPage() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const on = token !== ''

  const status = useQuery({
    queryKey: ['intelligent-status'],
    queryFn: ({ signal }) => getIntelligentStatus(token, signal),
    enabled: on,
    refetchInterval: 15000,
  })
  // ★活仓分页(每页 100)· 15s 刷新保持当前页(posPage state 不随 refetch 重置)
  const [posPage, setPosPage] = useState(0)
  const positions = useQuery({
    queryKey: ['intelligent-positions', posPage],
    queryFn: ({ signal }) =>
      getIntelligentPositions(token, posPage * INTELLIGENT_POSITIONS_PAGE_SIZE, INTELLIGENT_POSITIONS_PAGE_SIZE, signal),
    enabled: on,
    refetchInterval: 15000,
  })
  // ★历史分页(每页 50·照搬托管 PR#82)
  const [histPage, setHistPage] = useState(0)
  const history = useQuery({
    queryKey: ['intelligent-history', histPage],
    queryFn: ({ signal }) =>
      getIntelligentHistory(token, histPage * INTELLIGENT_HISTORY_PAGE_SIZE, INTELLIGENT_HISTORY_PAGE_SIZE, signal),
    enabled: on,
  })
  const stats = useQuery({
    queryKey: ['intelligent-stats'],
    queryFn: ({ signal }) => getIntelligentStats(token, signal),
    enabled: on,
  })

  const invalidate = () => {
    for (const k of [
      'intelligent-status',
      'intelligent-positions',
      'intelligent-history',
      'intelligent-stats',
    ])
      void qc.invalidateQueries({ queryKey: [k] })
  }

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => toggleIntelligent(token, enabled),
    onSuccess: (s) => {
      setNote(
        s.enabled
          ? '✓ 智能交易已开启 · 打分共振信号自动做多做空做前向测试'
          : '智能交易已关闭(已有持仓仍会被监控平仓)',
      )
      invalidate()
    },
    onError: () => setNote('操作失败,请重试'),
  })

  const enabled = status.data?.enabled ?? false
  const onToggle = () => {
    if (!enabled) {
      const ok = window.confirm(
        '确定开启【智能交易】(策略前向测试)?\n\n开启后:用打分共振信号在【虚拟账户】自动开仓' +
          '(★做多做空/100U/5x/全仓)、ATR 止损/2:1 止盈/信号反转自动平仓。\n🔴纯虚拟资金,绝不接真实交易。\n\n确定开启?',
      )
      if (!ok) return
    }
    toggle.mutate(!enabled)
  }

  // ★清零重来(人工 · 二次确认)
  const resetMut = useMutation({
    mutationFn: () => resetIntelligentAccount(token),
    onSuccess: () => {
      setNote('✓ 已清零重来 · 持仓+历史已清 · 现金重置起始资金')
      invalidate()
    },
    onError: () => setNote('清零失败,请重试'),
  })
  const onReset = () => {
    const ok = window.confirm(
      '确定【清零重来】?\n\n会删除智能账户的【全部持仓 + 历史平仓记录】,现金重置为起始资金。\n🔴纯虚拟资金 · 不可撤销。',
    )
    if (ok) resetMut.mutate()
  }

  // ★改起始资金(人工)
  const capitalMut = useMutation({
    mutationFn: (amount: number) => setIntelligentCapital(token, amount),
    onSuccess: (s) => {
      setNote(`✓ 起始资金改为 ${s.initial_capital.toLocaleString()} U · 已清持仓重来`)
      invalidate()
    },
    onError: () => setNote('起始资金更新失败,请重试'),
  })

  // ★开仓参数(每单本金 / 杠杆 / 最大单数 · 即时生效 · 失焦保存)
  const marginMut = useMutation({
    mutationFn: (margin: number) => setIntelligentOpenMargin(token, margin),
    onSuccess: (s) => {
      setNote(`✓ 每单本金 ${s.open_margin} U`)
      invalidate()
    },
    onError: () => setNote('每单本金更新失败(需 10-10000)'),
  })
  const leverageMut = useMutation({
    mutationFn: (lev: number) => setIntelligentOpenLeverage(token, lev),
    onSuccess: (s) => {
      setNote(`✓ 杠杆 ${s.open_leverage}x(不影响 ATR 止损止盈价)`)
      invalidate()
    },
    onError: () => setNote('杠杆更新失败(需 1-20)'),
  })
  const maxPosMut = useMutation({
    mutationFn: (n: number) => setIntelligentMaxPositions(token, n),
    onSuccess: (s) => {
      setNote(`✓ 最大总持仓 ${s.max_positions} 单`)
      invalidate()
    },
    onError: () => setNote('最大单数更新失败(需 > 0)'),
  })

  // ★策略参数(阈值/6权重/ATR倍数 · 前向测试迭代调参 · 折叠区 · 失焦保存批量提交)
  const [showStrat, setShowStrat] = useState(false)
  const [strat, setStrat] = useState<StrategyParams | null>(null)
  const stratQuery = useQuery({
    queryKey: ['intelligent-strategy-params'],
    queryFn: ({ signal }) => getIntelligentStrategyParams(token, signal),
    enabled: on,
  })
  useEffect(() => {
    if (stratQuery.data) setStrat(stratQuery.data)
  }, [stratQuery.data])
  const stratMut = useMutation({
    mutationFn: (p: StrategyParams) => setIntelligentStrategyParams(token, p),
    onSuccess: (p) => {
      setStrat(p)
      setNote('✓ 策略参数已更新 · 下一轮按新参数算')
      void qc.invalidateQueries({ queryKey: ['intelligent-strategy-params'] })
    },
    onError: () => setNote('策略参数更新失败(阈值/ATR>0·权重≥0)'),
  })
  const saveStrat = () => {
    if (strat) stratMut.mutate(strat)
  }

  const forbidden = status.isError
  const st = status.data
  const stat = stats.data
  const pos = positions.data?.items ?? []  // ★当前页活仓(分页 100/页)
  const posTotal = positions.data?.total ?? 0
  const posPages = Math.max(1, Math.ceil(posTotal / INTELLIGENT_POSITIONS_PAGE_SIZE))
  const histTotal = history.data?.total ?? 0
  const histPages = Math.max(1, Math.ceil(histTotal / INTELLIGENT_HISTORY_PAGE_SIZE))
  // ★当前页变空(平仓后)且非首页 → 回上一页(动态刷新兜底)
  useEffect(() => {
    if (pos.length === 0 && posPage > 0 && posTotal > 0) setPosPage((p) => Math.max(0, p - 1))
  }, [pos.length, posPage, posTotal])

  // ★前端汇总:总敞口/做多做空/浮盈(当前页·活仓 <100 时即全部·1 页)
  const totalMargin = pos.reduce((s, p) => s + p.margin, 0)
  const longCount = pos.filter((p) => p.side === 'long').length
  const shortCount = pos.filter((p) => p.side === 'short').length
  const totalUpnl = pos.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0)

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-8">
        <AdminNav />

        {forbidden ? (
          <p className="py-8 text-center text-sm text-muted-foreground">该页面仅管理员可见。</p>
        ) : (
          <>
            {/* 控制 + 账户管理 */}
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
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                {/* ★需求1:起始资金 → 账户总价值(权益·含浮盈亏·动态)· 盈亏染色 */}
                <StatCard
                  label="账户总价值"
                  value={st ? `${st.account_value.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'}
                  tone={st ? pnlTone(st.account_value - st.initial_capital) : undefined}
                />
                <StatCard
                  label="账户现金"
                  value={st ? `${st.cash_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'}
                />
                {/* ★需求2:总敞口 ↔ 当前活仓 对换(资金类在前·仓位类在后)*/}
                <StatCard label="总敞口(保证金)" value={`${totalMargin.toFixed(0)} U`} />
                <StatCard label="当前活仓" value={st ? `${st.open_positions}` : '—'} />
                <StatCard label="做多 / 做空" value={`${longCount} / ${shortCount}`} />
                <StatCard
                  label="持仓浮盈"
                  value={`${totalUpnl >= 0 ? '+' : ''}${totalUpnl.toFixed(2)} U`}
                  tone={pnlTone(totalUpnl)}
                />
              </div>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-paper pt-3">
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
                  {toggle.isPending ? '处理中…' : enabled ? '关闭智能交易' : '开启智能交易'}
                </button>
                {enabled && (
                  <span className="text-xs text-muted-foreground">关闭只停新开仓 · 已有持仓仍被监控平仓</span>
                )}
              </div>
              {/* ★账户管理(清零 / 改起始资金 · 人工) */}
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-paper pt-3 text-xs">
                <span className="text-muted-foreground">账户管理:</span>
                <button
                  type="button"
                  onClick={onReset}
                  disabled={resetMut.isPending || !on}
                  className="rounded-md border border-paper px-3 py-1 font-medium text-midas-red hover:bg-midas-red/10 disabled:opacity-50"
                >
                  清零重来
                </button>
                <span className="ml-2 text-muted-foreground">起始资金:</span>
                <input
                  key={st?.initial_capital ?? 100000}
                  type="number"
                  min={1}
                  defaultValue={st?.initial_capital ?? 100000}
                  disabled={!on || capitalMut.isPending}
                  onBlur={(e) => {
                    const v = Number.parseFloat(e.currentTarget.value)
                    if (Number.isFinite(v) && v > 0 && v !== (st?.initial_capital ?? 100000))
                      capitalMut.mutate(v)
                  }}
                  className="w-28 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                />
                <span className="text-muted-foreground">U(改则清持仓重来 · 失焦保存)</span>
              </div>
              {/* ★开仓参数(每单本金 / 杠杆 / 最大单数 · 失焦保存 · 即时生效) */}
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
                  <span className="text-muted-foreground">x(1-20·不改止损止盈)</span>
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
              {note && (
                <p className="mt-3 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">{note}</p>
              )}
            </div>

            {/* ★策略参数(阈值/6权重/ATR倍数 · 前向测试迭代调参 · 折叠区) */}
            <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
              <button
                type="button"
                onClick={() => setShowStrat((v) => !v)}
                className="flex w-full items-center gap-2 font-serif text-base font-bold"
              >
                <span>策略参数</span>
                <span className="text-xs font-normal text-muted-foreground">
                  (阈值 {strat?.threshold ?? 3} · ATR {strat?.atr_stop_mult ?? 2}×/{strat?.atr_tp_mult ?? 4}× · 点击{showStrat ? '收起' : '展开'}调参)
                </span>
                <span className="ml-auto text-muted-foreground">{showStrat ? '▲' : '▼'}</span>
              </button>
              {showStrat && strat && (
                <div className="mt-3 space-y-3 border-t border-paper pt-3 text-xs">
                  <p className="text-muted-foreground">★改后点「保存」即时生效 · 下一轮 open/close 按新参数算 · 失焦或点保存提交</p>
                  {/* 阈值 + ATR 倍数 */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <label className="flex items-center gap-2">
                      <span className="text-muted-foreground">开仓阈值(&gt;0):</span>
                      <input
                        type="number" step="0.5" min={0.5}
                        value={strat.threshold}
                        disabled={!on || stratMut.isPending}
                        onChange={(e) => setStrat({ ...strat, threshold: Number.parseFloat(e.currentTarget.value) || 0 })}
                        onBlur={saveStrat}
                        className="w-20 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                      />
                    </label>
                    <label className="flex items-center gap-2">
                      <span className="text-muted-foreground">ATR 止损倍数:</span>
                      <input
                        type="number" step="0.5" min={0.5}
                        value={strat.atr_stop_mult}
                        disabled={!on || stratMut.isPending}
                        onChange={(e) => setStrat({ ...strat, atr_stop_mult: Number.parseFloat(e.currentTarget.value) || 0 })}
                        onBlur={saveStrat}
                        className="w-16 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                      />
                    </label>
                    <label className="flex items-center gap-2">
                      <span className="text-muted-foreground">ATR 止盈倍数:</span>
                      <input
                        type="number" step="0.5" min={0.5}
                        value={strat.atr_tp_mult}
                        disabled={!on || stratMut.isPending}
                        onChange={(e) => setStrat({ ...strat, atr_tp_mult: Number.parseFloat(e.currentTarget.value) || 0 })}
                        onBlur={saveStrat}
                        className="w-16 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                      />
                    </label>
                  </div>
                  {/* 6 权重 */}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <span className="text-muted-foreground">指标权重(≥0):</span>
                    {(
                      [
                        ['boll', '布林'], ['macd', 'MACD'], ['ma', 'MA'],
                        ['rsi', 'RSI'], ['kdj', 'KDJ'], ['extreme', '极端'],
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key} className="flex items-center gap-1">
                        <span className="text-muted-foreground">{label}</span>
                        <input
                          type="number" step="0.5" min={0}
                          value={strat.weights[key]}
                          disabled={!on || stratMut.isPending}
                          onChange={(e) =>
                            setStrat({
                              ...strat,
                              weights: { ...strat.weights, [key]: Number.parseFloat(e.currentTarget.value) || 0 },
                            })
                          }
                          onBlur={saveStrat}
                          className="w-14 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
                        />
                      </label>
                    ))}
                  </div>
                  <button
                    type="button"
                    onClick={saveStrat}
                    disabled={!on || stratMut.isPending}
                    className="rounded-md bg-midas-red px-4 py-1.5 text-xs font-medium text-white hover:bg-midas-red/90 disabled:opacity-50"
                  >
                    {stratMut.isPending ? '保存中…' : '保存策略参数'}
                  </button>
                </div>
              )}
            </div>

            {/* 前向测试统计 */}
            <h2 className="mb-2 font-serif text-base font-bold">前向测试统计</h2>
            <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="总交易" value={stat ? `${stat.total_trades}` : '—'} />
              <StatCard label="胜率" value={stat ? `${(stat.win_rate * 100).toFixed(1)}%` : '—'} />
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
                label="止损/止盈/信号反转"
                value={
                  stat
                    ? `${stat.by_reason.stop_loss}/${stat.by_reason.take_profit}/${stat.by_reason.signal_reversal}`
                    : '—'
                }
              />
              <StatCard
                label="做多 / 做空(已平)"
                value={stat ? `${stat.by_side.long} / ${stat.by_side.short}` : '—'}
              />
            </div>

            {/* 当前活仓(★分页 100/页) */}
            <h2 className="mb-2 font-serif text-base font-bold">
              当前活仓 {positions.data ? `(${posTotal})` : ''}
            </h2>
            <div className="mb-6 overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-paper text-muted-foreground">
                  <tr>
                    {['币种', '方向', '杠杆', '开仓价', '标记价', '止损', '止盈', '共振分', '浮盈U', '浮盈%'].map(
                      (h) => (
                        <th key={h} className="px-3 py-2 font-medium">
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {pos.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="px-3 py-4 text-center text-muted-foreground">
                        无活仓
                      </td>
                    </tr>
                  ) : (
                    pos.map((p) => (
                      <tr key={p.symbol} className="border-b border-paper/60">
                        <td className="px-3 py-2 font-mono font-bold">{p.symbol}</td>
                        <td className={`px-3 py-2 font-medium ${sideTone(p.side)}`}>{sideLabel(p.side)}</td>
                        <td className="px-3 py-2">{p.leverage}x</td>
                        <td className="px-3 py-2 font-mono">{p.entry_price}</td>
                        <td className="px-3 py-2 font-mono">{p.mark ?? '—'}</td>
                        <td className="px-3 py-2 font-mono text-rose-600">{p.stop_price ?? '—'}</td>
                        <td className="px-3 py-2 font-mono text-emerald-700">{p.tp_price ?? '—'}</td>
                        <td
                          className={`px-3 py-2 font-mono font-bold ${p.signals?.score != null ? scoreTone(p.signals.score) : ''}`}
                        >
                          {p.signals?.score != null
                            ? `${p.signals.score > 0 ? '+' : ''}${p.signals.score.toFixed(1)}`
                            : '—'}
                        </td>
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
            {/* ★活仓分页控件(100/页·超出翻页) */}
            {posTotal > INTELLIGENT_POSITIONS_PAGE_SIZE && (
              <div className="mb-6 flex items-center justify-center gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => setPosPage((p) => Math.max(0, p - 1))}
                  disabled={posPage <= 0 || positions.isFetching}
                  className="rounded-md border border-paper px-3 py-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  上一页
                </button>
                <span className="font-mono text-muted-foreground">第 {posPage + 1} / {posPages} 页</span>
                <button
                  type="button"
                  onClick={() => setPosPage((p) => Math.min(posPages - 1, p + 1))}
                  disabled={posPage >= posPages - 1 || positions.isFetching}
                  className="rounded-md border border-paper px-3 py-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            )}

            {/* 历史平仓(★分页 50/页) */}
            <h2 className="mb-2 font-serif text-base font-bold">
              历史平仓 {history.data ? `(${histTotal})` : ''}
            </h2>
            <div className="overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-paper text-muted-foreground">
                  <tr>
                    {['币种', '方向', '开仓价', '平仓价', '盈亏U', '盈亏%', '原因', '持仓时长'].map((h) => (
                      <th key={h} className="px-3 py-2 font-medium">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(history.data?.items ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={8} className="px-3 py-4 text-center text-muted-foreground">
                        还没有平仓记录
                      </td>
                    </tr>
                  ) : (
                    history.data?.items.map((t, i) => (
                      <tr key={`${t.symbol}-${i}`} className="border-b border-paper/60">
                        <td className="px-3 py-2 font-mono font-bold">{t.symbol}</td>
                        <td className={`px-3 py-2 font-medium ${sideTone(t.side)}`}>{sideLabel(t.side)}</td>
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
            {/* ★历史分页控件(50/页·超出翻页·照搬托管 PR#82) */}
            {histTotal > INTELLIGENT_HISTORY_PAGE_SIZE && (
              <div className="mt-3 flex items-center justify-center gap-3 text-xs">
                <button
                  type="button"
                  onClick={() => setHistPage((p) => Math.max(0, p - 1))}
                  disabled={histPage <= 0 || history.isFetching}
                  className="rounded-md border border-paper px-3 py-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  上一页
                </button>
                <span className="font-mono text-muted-foreground">第 {histPage + 1} / {histPages} 页</span>
                <button
                  type="button"
                  onClick={() => setHistPage((p) => Math.min(histPages - 1, p + 1))}
                  disabled={histPage >= histPages - 1 || history.isFetching}
                  className="rounded-md border border-paper px-3 py-1 text-muted-foreground hover:text-foreground disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
