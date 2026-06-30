'use client'

/**
 * 铂金自助 · 智能交易面板(多账户 PR-6)· 接 /platinum/intelligent/*。
 *
 * ★裁剪(对比 admin 看板):只读四件套(控制台卡 + 统计 + 活仓 + 历史)+ 单开关;
 *   无调参/手动平/清零/改资金(自助端点无 setter)· 无「纯虚拟」醒目徽章(用户面)。
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
} from '@/lib/api/intelligent'
import {
  getMyIntelligentHistory,
  getMyIntelligentPositions,
  getMyIntelligentStats,
  getMyIntelligentStatus,
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
