'use client'

/**
 * 合约当前持仓(重组刀3 · 从 perp-positions-section ①段拆出,表体/平仓链零逻辑改动)。
 *
 * ★ 平仓操作链整体随段走:平仓按钮 → PerpCloseConfirm 确认弹层 → doClose
 *   (usePlacePerpOrder intent=close · mutation 内部 invalidate)→ toast。
 * 未激活 crypto 账户 → 开仓引导(原 section 级引导随主段走)。
 * 🔴 红线:全程虚拟资金 · 复用 /perp/* 接口 · 不改后端。
 */

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'
import { toast } from 'sonner'

import {
  IsolatedTag,
  SideBadge,
  fmtP,
  fmtU,
  num,
} from '@/components/account/perp-shared'
import { ConditionalOrderDialog } from '@/components/trading/conditional-order-dialog'
import { usePerpPositions, usePlacePerpOrder } from '@/hooks/use-perp'
import { useAccount } from '@/hooks/use-virtual'
import { PerpApiError, type PerpPosition } from '@/lib/api/perp'
import { cn } from '@/lib/utils'

export function PerpActivePositions() {
  const { status } = useSession()
  const authed = status === 'authenticated'
  const { data: account } = useAccount('crypto') // null = 未激活
  const posQ = usePerpPositions()
  const placeOrder = usePlacePerpOrder()
  const [confirm, setConfirm] = useState<PerpPosition | null>(null)
  // 二期刀4:持仓行内联挂止盈止损(复用现有 ConditionalOrderDialog · 含做空 · 后端零碰)
  const [sltp, setSltp] = useState<PerpPosition | null>(null)

  const active = useMemo(
    () => (posQ.data ?? []).filter((p) => p.closed_at === null),
    [posQ.data],
  )

  if (!authed) return null

  async function doClose(p: PerpPosition) {
    try {
      const o = await placeOrder.mutateAsync({
        symbol: p.symbol, intent: 'close', close_all: true,
      })
      if (o.status === 'filled') {
        const pnl =
          o.realized_pnl != null ? ` · 已实现 ${fmtU(o.realized_pnl)} USDT` : ''
        toast.success(`平仓 ${p.symbol} 已成交(虚拟)${pnl}`, {
          className: 'midas-toast-success', duration: 4000,
        })
      } else {
        toast.error(`平仓被拒 · ${o.reject_reason ?? '未知原因'}`, { duration: 5000 })
      }
    } catch (e) {
      toast.error(e instanceof PerpApiError ? e.detail : '平仓失败')
    } finally {
      setConfirm(null)
    }
  }

  if (account == null) {
    return (
      <div className="rounded-lg border border-dashed border-gold/50 bg-gold/5 p-4 text-sm text-muted-foreground">
        先在「资产总览」激活「加密」USDT,再去{' '}
        <Link href="/crypto-market" className="text-midas-red underline">加密市场</Link>{' '}
        选币种,在详情页右栏「下单指导」开合约仓(开多 / 开空)。
      </div>
    )
  }

  return (
    <div>
      <h3 className="mb-2 font-serif text-base font-bold text-foreground">
        合约持仓 · {active.length} 笔
      </h3>
      {active.length === 0 ? (
        <p className="mb-6 rounded-lg border border-paper bg-surface-card px-4 py-6 text-center text-sm text-muted-foreground/70">
          暂无合约持仓 · 去币种详情页开多 / 开空
        </p>
      ) : (
        <div className="mb-6 overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead>
              <tr className="border-b border-paper text-xs text-muted-foreground">
                <th className="py-2 text-left">标的</th>
                <th className="py-2 text-left">方向</th>
                <th className="py-2 text-right">数量</th>
                <th className="py-2 text-right">入场价</th>
                <th className="py-2 text-right">标记价</th>
                <th className="py-2 text-right">浮动盈亏 / ROE</th>
                <th className="py-2 text-right">强平价</th>
                <th className="py-2 text-right">累计资金费</th>
                <th className="py-2 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {active.map((p) => {
                const upnl = p.unrealized_pnl != null ? num(p.unrealized_pnl) : null
                const roe = p.roe_pct != null ? num(p.roe_pct) : null
                const dist = p.liquidation_distance_pct != null ? num(p.liquidation_distance_pct) : null
                const tone = upnl == null ? '' : upnl >= 0 ? 'text-up' : 'text-down'
                return (
                  <tr key={p.id} className="border-b border-paper/60">
                    <td className="py-2 font-mono">{p.symbol}</td>
                    <td className="py-2"><SideBadge side={p.side} leverage={p.leverage} /></td>
                    <td className="py-2 text-right font-mono">{num(p.quantity)}</td>
                    <td className="py-2 text-right font-mono">${fmtP(p.entry_price)}</td>
                    <td className="py-2 text-right font-mono">
                      {p.mark_price != null ? `$${fmtP(p.mark_price)}` : '—'}
                    </td>
                    <td className={cn('py-2 text-right font-mono', tone)}>
                      {upnl != null ? `${upnl >= 0 ? '+' : ''}${fmtU(p.unrealized_pnl)}` : '—'}
                      {roe != null && (
                        <span className="ml-1 text-[11px]">({roe >= 0 ? '+' : ''}{roe.toFixed(2)}%)</span>
                      )}
                    </td>
                    <td className={cn('py-2 text-right font-mono', dist != null && dist < 5 ? 'text-down' : '')}>
                      ${fmtP(p.liquidation_price)}
                      {dist != null && <span className="text-[11px]"> ({dist.toFixed(1)}%)</span>}
                      <IsolatedTag />
                    </td>
                    <td className={cn('py-2 text-right font-mono text-xs', num(p.funding_paid) > 0 ? 'text-down' : num(p.funding_paid) < 0 ? 'text-up' : 'text-muted-foreground/60')}>
                      {num(p.funding_paid) === 0
                        ? '—'
                        : num(p.funding_paid) > 0
                          ? `付 ${fmtU(p.funding_paid)}`
                          : `收 ${num(p.funding_paid) < 0 ? fmtU(String(-num(p.funding_paid))) : '0'}`}
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => setSltp(p)}
                          className="min-h-10 rounded border border-gold/60 px-2 py-1 text-xs text-gold hover:bg-gold/10 lg:min-h-0"
                        >
                          止盈止损
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirm(p)}
                          className="min-h-10 rounded border border-midas-red px-2 py-1 text-xs text-midas-red hover:bg-midas-red-glow lg:min-h-0"
                        >
                          平仓
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {confirm && (
        <PerpCloseConfirm
          pos={confirm}
          pending={placeOrder.isPending}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void doClose(confirm)}
        />
      )}

      {/* 持仓行内联挂 SL/TP · 共享条件单弹层(触发走后端 route_close_perp 平仓 · 含做空) */}
      {sltp && (
        <ConditionalOrderDialog
          open
          onClose={() => setSltp(null)}
          symbol={sltp.symbol}
          market="crypto"
          mode="sltp"
          positionSide={sltp.side}
          heldQuantity={sltp.quantity}
        />
      )}
    </div>
  )
}

// ── 平仓确认(轻量 · 随平仓链一体搬迁)──────────────────────────────────────
function PerpCloseConfirm({
  pos, pending, onCancel, onConfirm,
}: { pos: PerpPosition; pending: boolean; onCancel: () => void; onConfirm: () => void }) {
  const upnl = pos.unrealized_pnl != null ? num(pos.unrealized_pnl) : null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="w-full max-w-sm rounded-lg border border-midas-red bg-cream p-6 shadow-xl">
        <h3 className="mb-5 text-center font-serif text-lg font-bold">确认平仓</h3>
        <dl className="space-y-2.5 text-sm">
          <div className="flex justify-between"><dt className="text-xs text-muted-foreground">标的</dt><dd className="font-mono">{pos.symbol}</dd></div>
          <div className="flex items-center justify-between"><dt className="text-xs text-muted-foreground">方向</dt><dd><SideBadge side={pos.side} leverage={pos.leverage} /></dd></div>
          <div className="flex justify-between"><dt className="text-xs text-muted-foreground">平仓量</dt><dd className="font-mono">{num(pos.quantity)}(全部)</dd></div>
          {upnl != null && (
            <div className="flex justify-between">
              <dt className="text-xs text-muted-foreground">当前浮盈</dt>
              <dd className={cn('font-mono', upnl >= 0 ? 'text-up' : 'text-down')}>{upnl >= 0 ? '+' : ''}{fmtU(pos.unrealized_pnl)} USDT</dd>
            </div>
          )}
        </dl>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md border border-paper bg-background px-4 py-2 text-sm hover:bg-cream">取消</button>
          <button type="button" onClick={onConfirm} disabled={pending}
            className={cn('rounded-md px-4 py-2 text-sm font-medium text-white', pending ? 'cursor-not-allowed bg-midas-red/40' : 'bg-midas-red hover:bg-midas-red-deep')}>
            {pending ? '提交中…' : '确认平仓'}
          </button>
        </div>
      </div>
    </div>
  )
}
