'use client'

/**
 * 铂金自助 · 智能交易面板(多账户 PR-6)· 接 /platinum/intelligent/*。
 *
 * ★体验同管理员(PR-7):四件套(控制台 + 统计 + 活仓 + 历史)+ 开关 + 开仓参数/策略参数自助调
 *   + 清零/改起始资金;★决策①智能侧不做手动平/一键平 · 无「纯虚拟」醒目徽章(用户面)。
 * ★配色硬编码(红线③):方向做多绿/做空红(不随涨跌偏好翻转)· 盈亏盈红亏绿 · 共振分正绿负红。
 * 🔴 安全边界后端 PlatinumDep(403)· fetch 透传 token。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { Pagination, StatCard } from '@/components/platinum/ui'
import {
  INTELLIGENT_HISTORY_PAGE_SIZE,
  INTELLIGENT_POSITIONS_PAGE_SIZE,
  type StrategyParams,
} from '@/lib/api/intelligent'
import {
  getMyIntelligentHistory,
  getMyIntelligentPositions,
  getMyIntelligentStats,
  getMyIntelligentStatus,
  getMyIntelligentStrategyParams,
  resetMyIntelligent,
  setMyIntelligentAllowDirection,
  setMyIntelligentCapital,
  setMyIntelligentMaxPositions,
  setMyIntelligentOpenLeverage,
  setMyIntelligentOpenMargin,
  setMyIntelligentStrategyParams,
  toggleMyIntelligent,
} from '@/lib/api/platinum'
import {
  holdLabel,
  INTEL_REASON_LABEL,
  pnlTone,
  scoreTone,
  sideLabel,
  sideTone,
} from '@/lib/platinum-format'

export function IntelligentPanel() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const on = token !== ''
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const [posPage, setPosPage] = useState(0)
  const [histPage, setHistPage] = useState(0)

  const status = useQuery({
    queryKey: ['my-intelligent-status'],
    queryFn: ({ signal }) => getMyIntelligentStatus(token, signal),
    enabled: on,
    retry: 0,
    refetchInterval: 15000,
  })
  const positions = useQuery({
    queryKey: ['my-intelligent-positions', posPage],
    queryFn: ({ signal }) =>
      getMyIntelligentPositions(token, posPage * INTELLIGENT_POSITIONS_PAGE_SIZE, INTELLIGENT_POSITIONS_PAGE_SIZE, signal),
    enabled: on,
    retry: 0,
    refetchInterval: 15000,
  })
  const history = useQuery({
    queryKey: ['my-intelligent-history', histPage],
    queryFn: ({ signal }) =>
      getMyIntelligentHistory(token, histPage * INTELLIGENT_HISTORY_PAGE_SIZE, INTELLIGENT_HISTORY_PAGE_SIZE, signal),
    enabled: on,
    retry: 0,
  })
  const stats = useQuery({
    queryKey: ['my-intelligent-stats'],
    queryFn: ({ signal }) => getMyIntelligentStats(token, signal),
    enabled: on,
    retry: 0,
  })

  const invalidate = () => {
    for (const k of [
      'my-intelligent-status',
      'my-intelligent-positions',
      'my-intelligent-history',
      'my-intelligent-stats',
    ])
      void qc.invalidateQueries({ queryKey: [k] })
  }

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => toggleMyIntelligent(token, enabled),
    onSuccess: (s) => {
      setNote(s.enabled ? '✓ 已开启 · 系统将按策略信号在你的账户自动交易' : '已关闭(已有持仓仍会按策略自动平仓)')
      invalidate()
    },
    onError: () => setNote('操作失败,请重试'),
  })

  // ★账户操作(清零 / 改起始资金 · 决策④给铂金自助 · 二次确认)
  const resetMut = useMutation({
    mutationFn: () => resetMyIntelligent(token),
    onSuccess: () => {
      setNote('✓ 已清零重来 · 持仓 + 历史已清 · 现金重置起始资金')
      invalidate()
    },
    onError: () => setNote('清零失败,请重试'),
  })
  const onReset = () => {
    if (
      window.confirm(
        '确定清零重来?会删除你智能账户的【全部持仓 + 历史平仓记录】,现金重置为起始资金。不可撤销。',
      )
    )
      resetMut.mutate()
  }
  const capitalMut = useMutation({
    mutationFn: (amount: number) => setMyIntelligentCapital(token, amount),
    onSuccess: (s) => {
      setNote(`✓ 起始资金改为 ${s.initial_capital.toLocaleString()} U · 已清持仓重来`)
      invalidate()
    },
    onError: () => setNote('起始资金更新失败,请重试'),
  })

  // ★开仓参数(每单本金 / 杠杆 / 最大单数 · 失焦保存 · 即时生效 · per-user)
  const marginMut = useMutation({
    mutationFn: (margin: number) => setMyIntelligentOpenMargin(token, margin),
    onSuccess: (s) => {
      setNote(`✓ 每单本金 ${s.open_margin} U`)
      invalidate()
    },
    onError: () => setNote('每单本金更新失败(需 10-10000)'),
  })
  const leverageMut = useMutation({
    mutationFn: (lev: number) => setMyIntelligentOpenLeverage(token, lev),
    onSuccess: (s) => {
      setNote(`✓ 杠杆 ${s.open_leverage}x(不影响 ATR 止损止盈价)`)
      invalidate()
    },
    onError: () => setNote('杠杆更新失败(需 1-20)'),
  })
  const maxPosMut = useMutation({
    mutationFn: (n: number) => setMyIntelligentMaxPositions(token, n),
    onSuccess: (s) => {
      setNote(`✓ 最大总持仓 ${s.max_positions} 单`)
      invalidate()
    },
    onError: () => setNote('最大单数更新失败(需 > 0)'),
  })

  // ★策略参数(阈值/6权重/ATR倍数 · 折叠区 · 失焦保存 · per-user)
  const [showStrat, setShowStrat] = useState(false)
  const [strat, setStrat] = useState<StrategyParams | null>(null)
  const stratQuery = useQuery({
    queryKey: ['my-intelligent-strategy-params'],
    queryFn: ({ signal }) => getMyIntelligentStrategyParams(token, signal),
    enabled: on,
    retry: 0,
  })
  useEffect(() => {
    if (stratQuery.data) setStrat(stratQuery.data)
  }, [stratQuery.data])
  const stratMut = useMutation({
    mutationFn: (p: StrategyParams) => setMyIntelligentStrategyParams(token, p),
    onSuccess: (p) => {
      setStrat(p)
      setNote('✓ 策略参数已更新 · 下一轮按新参数算')
      void qc.invalidateQueries({ queryKey: ['my-intelligent-strategy-params'] })
    },
    onError: () => setNote('策略参数更新失败(阈值/ATR>0 · 权重≥0)'),
  })
  const saveStrat = () => {
    if (strat) stratMut.mutate(strat)
  }

  // ★PR-8 方向过滤(允许做多/做空 · per-user · 只滤方向不改策略)
  const allowMut = useMutation({
    mutationFn: (v: { which: 'long' | 'short'; on: boolean }) =>
      setMyIntelligentAllowDirection(token, v.which, v.on),
    onSuccess: (s) => {
      setNote(`✓ 方向 · 做多 ${s.allow_long ? '开' : '关'} · 做空 ${s.allow_short ? '开' : '关'}`)
      invalidate()
    },
    onError: () => setNote('方向过滤更新失败,请重试'),
  })

  const enabled = status.data?.enabled ?? false
  const onToggle = () => {
    if (!enabled) {
      if (!window.confirm('开启后,系统会按策略信号在你的独立账户自动开仓 / 平仓。确定开启?')) return
    } else if (!window.confirm('关闭后将停止新开仓;已有持仓仍按策略自动平仓(不会强制平掉)。确定关闭?')) {
      return
    }
    toggle.mutate(!enabled)
  }

  const st = status.data
  const stat = stats.data
  const pos = positions.data?.items ?? []
  const posTotal = positions.data?.total ?? 0
  const posPages = Math.max(1, Math.ceil(posTotal / INTELLIGENT_POSITIONS_PAGE_SIZE))
  const histTotal = history.data?.total ?? 0
  const histPages = Math.max(1, Math.ceil(histTotal / INTELLIGENT_HISTORY_PAGE_SIZE))
  useEffect(() => {
    if (pos.length === 0 && posPage > 0 && posTotal > 0) setPosPage((p) => Math.max(0, p - 1))
  }, [pos.length, posPage, posTotal])

  const totalUpnl = pos.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0)
  const longCount = pos.filter((p) => p.side === 'long').length
  const shortCount = pos.filter((p) => p.side === 'short').length

  if (status.isError) {
    return <p className="py-8 text-center text-sm text-muted-foreground">该功能仅铂金用户可用。</p>
  }

  return (
    <div>
      {/* 控制台卡 */}
      <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <span className="font-serif text-base font-bold">智能交易</span>
          <span
            className={
              enabled
                ? 'rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700'
                : 'rounded bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground'
            }
          >
            ● {enabled ? '运行中' : '已关闭'}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <StatCard
            label="账户总价值"
            value={st ? `${st.account_value.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'}
            tone={st ? pnlTone(st.account_value - st.initial_capital) : undefined}
          />
          <StatCard label="账户现金" value={st ? `${st.cash_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'} />
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
            <span className="text-xs text-muted-foreground">关闭只停新开仓 · 已有持仓仍按策略平仓</span>
          )}
        </div>
        {/* ★账户管理(清零 / 改起始资金 · 决策④给铂金 · 二次确认) */}
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
              if (
                Number.isFinite(v) &&
                v > 0 &&
                v !== (st?.initial_capital ?? 100000) &&
                window.confirm(`改起始资金为 ${v} U 将清空当前全部持仓重来,确定?`)
              )
                capitalMut.mutate(v)
            }}
            className="w-28 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
          />
          <span className="text-muted-foreground">U(改则清持仓重来 · 失焦保存)</span>
        </div>
        {/* ★开仓参数(每单本金 / 杠杆 / 最大单数 · 失焦保存 · per-user) */}
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
                if (Number.isFinite(v) && v > 0 && v !== (st?.max_positions ?? 50)) maxPosMut.mutate(v)
              }}
              className="w-20 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
            />
            <span className="text-muted-foreground">单(失焦保存)</span>
          </div>
        </div>
        {/* ★PR-8 方向过滤(允许做多/做空 · 只滤方向不改策略) */}
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-paper pt-3 text-xs">
          <span className="text-muted-foreground">方向过滤:</span>
          <button
            type="button"
            onClick={() => st && allowMut.mutate({ which: 'long', on: !st.allow_long })}
            disabled={!on || allowMut.isPending || !st}
            className={
              st?.allow_long
                ? 'rounded-md bg-emerald-50 px-3 py-1 font-medium text-emerald-700 disabled:opacity-50'
                : 'rounded-md bg-muted px-3 py-1 font-medium text-muted-foreground disabled:opacity-50'
            }
          >
            允许做多 {st?.allow_long ? 'ON' : 'OFF'}
          </button>
          <button
            type="button"
            onClick={() => st && allowMut.mutate({ which: 'short', on: !st.allow_short })}
            disabled={!on || allowMut.isPending || !st}
            className={
              st?.allow_short
                ? 'rounded-md bg-emerald-50 px-3 py-1 font-medium text-emerald-700 disabled:opacity-50'
                : 'rounded-md bg-muted px-3 py-1 font-medium text-muted-foreground disabled:opacity-50'
            }
          >
            允许做空 {st?.allow_short ? 'ON' : 'OFF'}
          </button>
          <span className="text-muted-foreground">(OFF=不开该方向新仓 · 不碰平仓)</span>
        </div>
        {note && (
          <p className="mt-3 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">{note}</p>
        )}
      </div>

      {/* ★策略参数(阈值/6权重/ATR倍数 · 折叠区 · per-user · 失焦保存) */}
      <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
        <button
          type="button"
          onClick={() => setShowStrat((v) => !v)}
          className="flex w-full items-center gap-2 font-serif text-base font-bold"
        >
          <span>策略参数</span>
          <span className="text-xs font-normal text-muted-foreground">
            (阈值 {strat?.threshold ?? 3} · ATR {strat?.atr_stop_mult ?? 2}×/{strat?.atr_tp_mult ?? 4}× · 点击
            {showStrat ? '收起' : '展开'}调参)
          </span>
          <span className="ml-auto text-muted-foreground">{showStrat ? '▲' : '▼'}</span>
        </button>
        {showStrat && strat && (
          <div className="mt-3 space-y-3 border-t border-paper pt-3 text-xs">
            <p className="text-muted-foreground">★改后失焦或点保存即时生效 · 下一轮开仓按新参数算</p>
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
        <StatCard label="总盈亏" value={stat ? `${stat.total_pnl.toFixed(2)} U` : '—'} tone={stat ? pnlTone(stat.total_pnl) : undefined} />
        <StatCard label="平均盈亏" value={stat ? `${stat.avg_pnl.toFixed(2)} U` : '—'} tone={stat ? pnlTone(stat.avg_pnl) : undefined} />
        <StatCard label="盈亏比" value={stat ? (stat.profit_factor > 0 ? stat.profit_factor.toFixed(2) : '∞/—') : '—'} />
        <StatCard label="最大回撤" value={stat ? `${stat.max_drawdown.toFixed(2)} U` : '—'} />
        <StatCard
          label="止损/止盈/反转"
          value={stat ? `${stat.by_reason.stop_loss}/${stat.by_reason.take_profit}/${stat.by_reason.signal_reversal}` : '—'}
        />
        <StatCard label="做多 / 做空(已平)" value={stat ? `${stat.by_side.long} / ${stat.by_side.short}` : '—'} />
      </div>

      {/* 当前活仓 */}
      <h2 className="mb-2 font-serif text-base font-bold">当前活仓 {positions.data ? `(${posTotal})` : ''}</h2>
      <div className="mb-2 overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-paper text-muted-foreground">
            <tr>
              {['币种', '方向', '杠杆', '开仓价', '标记价', '止损', '止盈', '共振分', '浮盈U', '浮盈%'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pos.length === 0 ? (
              <tr><td colSpan={10} className="px-3 py-4 text-center text-muted-foreground">无活仓</td></tr>
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
                  <td className={`px-3 py-2 font-mono font-bold ${p.signals?.score != null ? scoreTone(p.signals.score) : ''}`}>
                    {p.signals?.score != null ? `${p.signals.score > 0 ? '+' : ''}${p.signals.score.toFixed(1)}` : '—'}
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
      {posTotal > INTELLIGENT_POSITIONS_PAGE_SIZE && (
        <div className="mb-6">
          <Pagination
            page={posPage} pages={posPages} isFetching={positions.isFetching}
            onPrev={() => setPosPage((p) => Math.max(0, p - 1))}
            onNext={() => setPosPage((p) => Math.min(posPages - 1, p + 1))}
          />
        </div>
      )}

      {/* 历史平仓 */}
      <h2 className="mb-2 font-serif text-base font-bold">历史平仓 {history.data ? `(${histTotal})` : ''}</h2>
      <div className="overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-paper text-muted-foreground">
            <tr>
              {['币种', '方向', '开仓价', '平仓价', '盈亏U', '盈亏%', '原因', '持仓时长'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(history.data?.items ?? []).length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-4 text-center text-muted-foreground">还没有平仓记录</td></tr>
            ) : (
              history.data?.items.map((t, i) => (
                <tr key={`${t.symbol}-${i}`} className="border-b border-paper/60">
                  <td className="px-3 py-2 font-mono font-bold">{t.symbol}</td>
                  <td className={`px-3 py-2 font-medium ${sideTone(t.side)}`}>{sideLabel(t.side)}</td>
                  <td className="px-3 py-2 font-mono">{t.entry_price}</td>
                  <td className="px-3 py-2 font-mono">{t.exit_price.toFixed(4)}</td>
                  <td className={`px-3 py-2 font-mono ${pnlTone(t.pnl_usdt)}`}>{t.pnl_usdt.toFixed(2)}</td>
                  <td className={`px-3 py-2 font-mono ${pnlTone(t.pnl_pct)}`}>{(t.pnl_pct * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2">{t.close_reason ? (INTEL_REASON_LABEL[t.close_reason] ?? t.close_reason) : '—'}</td>
                  <td className="px-3 py-2 text-muted-foreground">{holdLabel(t.hold_seconds)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {histTotal > INTELLIGENT_HISTORY_PAGE_SIZE && (
        <Pagination
          page={histPage} pages={histPages} isFetching={history.isFetching}
          onPrev={() => setHistPage((p) => Math.max(0, p - 1))}
          onNext={() => setHistPage((p) => Math.min(histPages - 1, p + 1))}
        />
      )}
    </div>
  )
}
