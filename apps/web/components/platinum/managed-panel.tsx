'use client'

/**
 * 铂金自助 · 托管交易面板(多账户 PR-6)· 接 /platinum/managed/*。
 *
 * ★裁剪同智能面板:只读四件套 + 单开关;无调参/手动平/清零/改资金 · 无「纯虚拟」醒目徽章。
 * ★托管 vs 智能:恒做多(无 side)· 信号列 = 维持 bias · 三退出 = 止盈/信号/超时。
 * ★配色硬编码(红线③):盈亏盈红亏绿 · bias 偏多绿/偏空红/中性金。
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSession } from 'next-auth/react'
import { useEffect, useState } from 'react'

import { Pagination, StatCard } from '@/components/platinum/ui'
import {
  MANAGED_HISTORY_PAGE_SIZE,
  MANAGED_POSITIONS_PAGE_SIZE,
} from '@/lib/api/managed'
import {
  closeAllMyManaged,
  closeMyManagedPosition,
  getMyManagedHistory,
  getMyManagedPositions,
  getMyManagedStats,
  getMyManagedStatus,
  resetMyManaged,
  setMyManagedCapital,
  setMyManagedMaxPositions,
  setMyManagedOpenLeverage,
  setMyManagedOpenMargin,
  toggleMyManaged,
} from '@/lib/api/platinum'
import { holdLabel, MANAGED_REASON_LABEL, pnlTone } from '@/lib/platinum-format'

function biasTone(bias: string | null): string {
  if (bias === '偏多') return 'text-emerald-700'
  if (bias === '偏空') return 'text-rose-600'
  return 'text-gold'
}

export function ManagedPanel() {
  const { data: session } = useSession()
  const token = session?.accessToken ?? ''
  const on = token !== ''
  const qc = useQueryClient()
  const [note, setNote] = useState('')
  const [posPage, setPosPage] = useState(0)
  const [histPage, setHistPage] = useState(0)

  const status = useQuery({
    queryKey: ['my-managed-status'],
    queryFn: ({ signal }) => getMyManagedStatus(token, signal),
    enabled: on,
    retry: 0,
    refetchInterval: 15000,
  })
  const positions = useQuery({
    queryKey: ['my-managed-positions', posPage],
    queryFn: ({ signal }) =>
      getMyManagedPositions(token, posPage * MANAGED_POSITIONS_PAGE_SIZE, MANAGED_POSITIONS_PAGE_SIZE, signal),
    enabled: on,
    retry: 0,
    refetchInterval: 15000,
  })
  const history = useQuery({
    queryKey: ['my-managed-history', histPage],
    queryFn: ({ signal }) =>
      getMyManagedHistory(token, histPage * MANAGED_HISTORY_PAGE_SIZE, MANAGED_HISTORY_PAGE_SIZE, signal),
    enabled: on,
    retry: 0,
  })
  const stats = useQuery({
    queryKey: ['my-managed-stats'],
    queryFn: ({ signal }) => getMyManagedStats(token, signal),
    enabled: on,
    retry: 0,
  })

  const invalidate = () => {
    for (const k of ['my-managed-status', 'my-managed-positions', 'my-managed-history', 'my-managed-stats'])
      void qc.invalidateQueries({ queryKey: [k] })
  }

  const toggle = useMutation({
    mutationFn: (enabled: boolean) => toggleMyManaged(token, enabled),
    onSuccess: (s) => {
      setNote(s.enabled ? '✓ 已开启 · 系统将按策略信号在你的账户自动交易' : '已关闭(已有持仓仍会按策略自动平仓)')
      invalidate()
    },
    onError: () => setNote('操作失败,请重试'),
  })

  // ★账户操作(清零 / 改起始资金 · 决策④给铂金自助 · 二次确认)
  const resetMut = useMutation({
    mutationFn: () => resetMyManaged(token),
    onSuccess: () => {
      setNote('✓ 已清零重来 · 持仓 + 历史已清 · 现金重置起始资金')
      invalidate()
    },
    onError: () => setNote('清零失败,请重试'),
  })
  const onReset = () => {
    if (
      window.confirm(
        '确定清零重来?会删除你托管账户的【全部持仓 + 历史平仓记录】,现金重置为起始资金。不可撤销。',
      )
    )
      resetMut.mutate()
  }
  const capitalMut = useMutation({
    mutationFn: (amount: number) => setMyManagedCapital(token, amount),
    onSuccess: (s) => {
      setNote(`✓ 起始资金改为 ${s.initial_capital.toLocaleString()} U · 已清持仓重来`)
      invalidate()
    },
    onError: () => setNote('起始资金更新失败,请重试'),
  })

  // ★开仓参数(每单本金 / 杠杆 / 最大单数 · 失焦保存 · per-user · ★无 exit/tp 决策B 全局)
  const marginMut = useMutation({
    mutationFn: (margin: number) => setMyManagedOpenMargin(token, margin),
    onSuccess: (s) => {
      setNote(`✓ 每单本金 ${s.open_margin} U`)
      invalidate()
    },
    onError: () => setNote('每单本金更新失败(需 10-10000)'),
  })
  const leverageMut = useMutation({
    mutationFn: (lev: number) => setMyManagedOpenLeverage(token, lev),
    onSuccess: (s) => {
      setNote(`✓ 杠杆 ${s.open_leverage}x`)
      invalidate()
    },
    onError: () => setNote('杠杆更新失败(需 1-20)'),
  })
  const maxPosMut = useMutation({
    mutationFn: (n: number) => setMyManagedMaxPositions(token, n),
    onSuccess: (s) => {
      setNote(`✓ 最大总持仓 ${s.max_positions} 单`)
      invalidate()
    },
    onError: () => setNote('最大单数更新失败(需 > 0)'),
  })

  // ★平仓(手动平单 / 一键平 · 二次确认 · 越权由后端按 account_id 校验)
  const closeOneMut = useMutation({
    mutationFn: (positionId: number) => closeMyManagedPosition(token, positionId),
    onSuccess: (r) => {
      setNote(r.status === 'ok' ? `✓ 已平仓 ${r.symbol ?? ''}` : '平仓未成交,请重试')
      invalidate()
    },
    onError: () => setNote('平仓失败,请重试'),
  })
  const onCloseOne = (positionId: number, symbol: string) => {
    if (window.confirm(`确定手动平掉 ${symbol} 这一仓?`)) closeOneMut.mutate(positionId)
  }
  const closeAllMut = useMutation({
    mutationFn: () => closeAllMyManaged(token),
    onSuccess: (r) => {
      setNote(`✓ 一键平仓:平了 ${r.closed}/${r.total} 仓`)
      invalidate()
    },
    onError: () => setNote('一键平仓失败,请重试'),
  })
  const onCloseAll = () => {
    if (window.confirm('确定一键平掉你托管账户的【全部活仓】?不可撤销。')) closeAllMut.mutate()
  }

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
  const posPages = Math.max(1, Math.ceil(posTotal / MANAGED_POSITIONS_PAGE_SIZE))
  const histTotal = history.data?.total ?? 0
  const histPages = Math.max(1, Math.ceil(histTotal / MANAGED_HISTORY_PAGE_SIZE))
  useEffect(() => {
    if (pos.length === 0 && posPage > 0 && posTotal > 0) setPosPage((p) => Math.max(0, p - 1))
  }, [pos.length, posPage, posTotal])

  const totalUpnl = pos.reduce((s, p) => s + (p.unrealized_pnl ?? 0), 0)

  if (status.isError) {
    return <p className="py-8 text-center text-sm text-muted-foreground">该功能仅铂金用户可用。</p>
  }

  return (
    <div>
      {/* 控制台卡 */}
      <div className="mb-6 rounded-lg border border-paper bg-cream p-4 shadow-sm">
        <div className="mb-3 flex items-center gap-2">
          <span className="font-serif text-base font-bold">托管交易</span>
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
          <StatCard label="可用资金" value={st ? `${st.available_funds.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'} />
          <StatCard label="账户现金" value={st ? `${st.cash_balance.toLocaleString(undefined, { maximumFractionDigits: 2 })} U` : '—'} />
          <StatCard label="当前活仓" value={st ? `${st.open_positions}` : '—'} />
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
            {toggle.isPending ? '处理中…' : enabled ? '关闭托管交易' : '开启托管交易'}
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
              if (Number.isFinite(v) && v > 0 && v !== (st?.initial_capital ?? 100000)) capitalMut.mutate(v)
            }}
            className="w-28 rounded border border-paper bg-cream px-2 py-1 font-mono disabled:opacity-50"
          />
          <span className="text-muted-foreground">U(改则清持仓重来 · 失焦保存)</span>
        </div>
        {/* ★开仓参数(每单本金 / 杠杆 / 最大单数 · 失焦保存 · per-user · 平仓参数全局不在此) */}
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
        {note && (
          <p className="mt-3 rounded-md bg-gold/10 px-3 py-2 text-xs text-muted-foreground">{note}</p>
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
          label="止盈/信号/超时/手动"
          value={stat ? `${stat.by_reason.tp}/${stat.by_reason.signal}/${stat.by_reason.timeout}/${stat.by_reason.manual}` : '—'}
        />
      </div>

      {/* 当前活仓(+ 一键平仓 / 每仓手动平) */}
      <div className="mb-2 flex items-center gap-2">
        <h2 className="font-serif text-base font-bold">当前活仓 {positions.data ? `(${posTotal})` : ''}</h2>
        {posTotal > 0 && (
          <button
            type="button"
            onClick={onCloseAll}
            disabled={closeAllMut.isPending || !on}
            className="ml-auto rounded-md border border-paper px-3 py-1 text-xs font-medium text-midas-red hover:bg-midas-red/10 disabled:opacity-50"
          >
            {closeAllMut.isPending ? '平仓中…' : '一键平仓'}
          </button>
        )}
      </div>
      <div className="mb-2 overflow-x-auto rounded-lg border border-paper bg-cream shadow-sm">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-paper text-muted-foreground">
            <tr>
              {['币种', '杠杆', '开仓价', '标记价', '信号', '浮盈U', '浮盈%', '操作'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pos.length === 0 ? (
              <tr><td colSpan={8} className="px-3 py-4 text-center text-muted-foreground">无活仓</td></tr>
            ) : (
              pos.map((p) => (
                <tr key={p.symbol} className="border-b border-paper/60">
                  <td className="px-3 py-2 font-mono font-bold">{p.symbol}</td>
                  <td className="px-3 py-2">{p.leverage}x</td>
                  <td className="px-3 py-2 font-mono">{p.entry_price}</td>
                  <td className="px-3 py-2 font-mono">{p.mark ?? '—'}</td>
                  <td className={`px-3 py-2 font-medium ${biasTone(p.bias)}`}>{p.bias ?? '—'}</td>
                  <td className={`px-3 py-2 font-mono ${p.unrealized_pnl != null ? pnlTone(p.unrealized_pnl) : ''}`}>
                    {p.unrealized_pnl != null ? p.unrealized_pnl.toFixed(2) : '—'}
                  </td>
                  <td className={`px-3 py-2 font-mono ${p.unrealized_pct != null ? pnlTone(p.unrealized_pct) : ''}`}>
                    {p.unrealized_pct != null ? `${(p.unrealized_pct * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => onCloseOne(p.id, p.symbol)}
                      disabled={closeOneMut.isPending || !on}
                      className="rounded border border-paper px-2 py-0.5 text-midas-red hover:bg-midas-red/10 disabled:opacity-50"
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
      {posTotal > MANAGED_POSITIONS_PAGE_SIZE && (
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
              {['币种', '开仓价', '平仓价', '盈亏U', '盈亏%', '原因', '持仓时长'].map((h) => (
                <th key={h} className="px-3 py-2 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(history.data?.items ?? []).length === 0 ? (
              <tr><td colSpan={7} className="px-3 py-4 text-center text-muted-foreground">还没有平仓记录</td></tr>
            ) : (
              history.data?.items.map((t, i) => (
                <tr key={`${t.symbol}-${i}`} className="border-b border-paper/60">
                  <td className="px-3 py-2 font-mono font-bold">{t.symbol}</td>
                  <td className="px-3 py-2 font-mono">{t.entry_price}</td>
                  <td className="px-3 py-2 font-mono">{t.exit_price.toFixed(4)}</td>
                  <td className={`px-3 py-2 font-mono ${pnlTone(t.pnl_usdt)}`}>{t.pnl_usdt.toFixed(2)}</td>
                  <td className={`px-3 py-2 font-mono ${pnlTone(t.pnl_pct)}`}>{(t.pnl_pct * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2">{t.close_reason ? (MANAGED_REASON_LABEL[t.close_reason] ?? t.close_reason) : '—'}</td>
                  <td className="px-3 py-2 text-muted-foreground">{holdLabel(t.hold_seconds)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {histTotal > MANAGED_HISTORY_PAGE_SIZE && (
        <Pagination
          page={histPage} pages={histPages} isFetching={history.isFetching}
          onPrev={() => setHistPage((p) => Math.max(0, p - 1))}
          onNext={() => setHistPage((p) => Math.min(histPages - 1, p + 1))}
        />
      )}
    </div>
  )
}
