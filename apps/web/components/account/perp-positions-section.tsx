'use client'

/**
 * 加密合约(永续)持仓 / 订单中心 · /account 独立 Section(M2-C.1 验收补充)。
 *
 * 三块:① 当前合约持仓(可平仓 · 实时浮盈/强平价/ROE)② 历史持仓(折叠 · 手动平/强平)
 *       ③ 合约订单流水。crypto 账户已激活才显示表格,未激活给开仓引导。
 *
 * 🔴 红线:全程虚拟资金。复用 M2-C.1 已验证的 /perp/* 只读接口 + close 端点,
 *   不改后端、不碰 0008 现货那套。平仓走 usePlacePerpOrder(intent=close)。
 *
 * 逐仓标注(问题2):强平价旁标「逐仓」+ tooltip,说明强平价与保证金无关。
 */

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'
import { toast } from 'sonner'

import {
  usePerpFunding,
  usePerpOrders,
  usePerpPositions,
  usePlacePerpOrder,
} from '@/hooks/use-perp'
import { useAccount } from '@/hooks/use-virtual'
import {
  PerpApiError,
  type PerpAction,
  type PerpFunding,
  type PerpPosition,
} from '@/lib/api/perp'
import { cn } from '@/lib/utils'

export const ISOLATED_TIP = '逐仓:强平价只取决于开仓价与杠杆,与保证金金额无关'

const ACTION_ZH: Record<PerpAction, string> = {
  open_long: '开多',
  open_short: '开空',
  close_long: '平多',
  close_short: '平空',
}

const num = (s: string | null | undefined): number => (s == null ? 0 : Number(s) || 0)
const fmtP = (s: string | null | undefined): string => {
  const n = num(s)
  return n >= 1 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : n.toFixed(4)
}
const fmtU = (s: string | null | undefined): string =>
  num(s).toLocaleString('en-US', { maximumFractionDigits: 2 })

function IsolatedTag() {
  return (
    <span
      title={ISOLATED_TIP}
      className="ml-1 cursor-help rounded bg-paper px-1 py-0.5 text-[9px] text-muted-foreground/80"
    >
      逐仓
    </span>
  )
}

function SideBadge({ side, leverage }: { side: 'long' | 'short'; leverage: number }) {
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-[10px] font-bold text-white',
        side === 'long' ? 'bg-up' : 'bg-down',
      )}
    >
      {side === 'long' ? '多' : '空'} {leverage}x
    </span>
  )
}

export function PerpPositionsSection() {
  const { status } = useSession()
  const authed = status === 'authenticated'
  const { data: account } = useAccount('crypto') // null = 未激活
  const posQ = usePerpPositions({ includeClosed: true })
  const ordersQ = usePerpOrders({ limit: 50 })
  const fundingQ = usePerpFunding({ limit: 50 })
  const placeOrder = usePlacePerpOrder()
  const [confirm, setConfirm] = useState<PerpPosition | null>(null)

  const active = useMemo(
    () => (posQ.data ?? []).filter((p) => p.closed_at === null),
    [posQ.data],
  )
  const history = useMemo(
    () => (posQ.data ?? []).filter((p) => p.closed_at !== null),
    [posQ.data],
  )
  const orders = ordersQ.data ?? []
  const funding = fundingQ.data ?? []

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

  return (
    <section className="mb-10">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="font-serif text-xl font-bold text-foreground">加密合约(永续)</h2>
      </div>

      {account == null ? (
        <div className="rounded-lg border border-dashed border-gold/50 bg-gold/5 p-4 text-sm text-muted-foreground">
          先在上方「账户资金设置」激活「加密」USDT,再去{' '}
          <Link href="/crypto-market" className="text-midas-red underline">加密市场</Link>{' '}
          选币种,在详情页右栏「下单指导」开合约仓(开多 / 开空)。
        </div>
      ) : (
        <>
          {/* ① 当前合约持仓 */}
          <h3 className="mb-2 font-serif text-base font-bold text-foreground">
            当前合约持仓 · {active.length} 笔
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
                          <button
                            type="button"
                            onClick={() => setConfirm(p)}
                            className="rounded border border-midas-red px-2 py-1 text-xs text-midas-red hover:bg-midas-red-glow"
                          >
                            平仓
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* ② 历史合约持仓(折叠 · 复盘)*/}
          {history.length > 0 && (
            <details className="mb-6">
              <summary className="cursor-pointer font-serif text-base font-bold text-foreground">
                历史合约持仓 · 复盘({history.length})
              </summary>
              <div className="mt-2 overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead>
                    <tr className="border-b border-paper text-xs text-muted-foreground">
                      <th className="py-2 text-left">标的</th>
                      <th className="py-2 text-left">方向</th>
                      <th className="py-2 text-right">入场价</th>
                      <th className="py-2 text-right">已实现</th>
                      <th className="py-2 text-left">平仓原因</th>
                      <th className="py-2 text-left">开仓</th>
                      <th className="py-2 text-left">平仓</th>
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((p) => {
                      const realized = num(p.realized_pnl)
                      const liquidated = p.close_reason === 'liquidated'
                      return (
                        <tr key={p.id} className="border-b border-paper/60">
                          <td className="py-2 font-mono">{p.symbol}</td>
                          <td className="py-2"><SideBadge side={p.side} leverage={p.leverage} /></td>
                          <td className="py-2 text-right font-mono">${fmtP(p.entry_price)}</td>
                          <td className={cn('py-2 text-right font-mono', realized > 0 ? 'text-up' : realized < 0 ? 'text-down' : '')}>
                            {realized >= 0 ? '+' : ''}{fmtU(p.realized_pnl)}
                          </td>
                          <td className="py-2 text-xs">
                            <span className={cn('rounded px-1.5 py-0.5 text-[10px]', liquidated ? 'bg-down/15 text-down' : 'text-muted-foreground')}>
                              {liquidated ? '强平' : '手动平'}
                            </span>
                          </td>
                          <td className="py-2 text-xs text-muted-foreground">{new Date(p.opened_at).toLocaleString('zh-CN')}</td>
                          <td className="py-2 text-xs text-muted-foreground">
                            {p.closed_at ? new Date(p.closed_at).toLocaleString('zh-CN') : '—'}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </details>
          )}

          {/* ③ 合约订单流水 */}
          {orders.length > 0 && (
            <>
              <h3 className="mb-2 font-serif text-base font-bold text-foreground">
                合约订单流水 · {orders.length} 笔
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[820px] text-sm">
                  <thead>
                    <tr className="border-b border-paper text-xs text-muted-foreground">
                      <th className="py-2 text-left">时间</th>
                      <th className="py-2 text-left">动作</th>
                      <th className="py-2 text-left">标的</th>
                      <th className="py-2 text-right">数量</th>
                      <th className="py-2 text-right">成交价</th>
                      <th className="py-2 text-right">手续费</th>
                      <th className="py-2 text-right">已实现</th>
                      <th className="py-2 text-left">状态</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.map((o) => {
                      const pnl = o.realized_pnl != null ? num(o.realized_pnl) : null
                      return (
                        <tr key={o.id ?? Math.random()} className={cn('border-b border-paper/60', o.status === 'rejected' && 'opacity-60')}>
                          <td className="py-2 text-xs text-muted-foreground">
                            {o.placed_at || o.filled_at
                              ? new Date(o.filled_at ?? o.placed_at!).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
                              : '—'}
                          </td>
                          <td className="py-2 text-xs">
                            <span className={cn('rounded px-1.5 py-0.5 text-[10px]', o.action.startsWith('open') ? 'bg-midas-red text-white' : 'border border-midas-red text-midas-red')}>
                              {ACTION_ZH[o.action]}
                            </span>
                            {o.is_liquidation && <span className="ml-1 rounded bg-down/15 px-1 py-0.5 text-[9px] text-down">强平</span>}
                          </td>
                          <td className="py-2 font-mono text-xs">{o.symbol}{o.leverage ? <span className="ml-1 text-muted-foreground">{o.leverage}x</span> : null}</td>
                          <td className="py-2 text-right font-mono text-xs">{num(o.quantity)}</td>
                          <td className="py-2 text-right font-mono text-xs">{o.price ? `$${fmtP(o.price)}` : '—'}</td>
                          <td className="py-2 text-right font-mono text-xs">{o.fee ? fmtU(o.fee) : '—'}</td>
                          <td className={cn('py-2 text-right font-mono text-xs', pnl != null && pnl > 0 ? 'text-up' : pnl != null && pnl < 0 ? 'text-down' : '')}>
                            {pnl != null ? `${pnl >= 0 ? '+' : ''}${fmtU(o.realized_pnl)}` : '—'}
                          </td>
                          <td className="py-2 text-xs">
                            {o.status === 'filled'
                              ? <span className="text-muted-foreground">成交</span>
                              : <span className="text-midas-red" title={o.reject_reason ?? ''}>拒单</span>}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* ④ 资金费记录(M2-C.2.2)· 每整点按币周期结算 · 只读复盘 */}
          {funding.length > 0 && (
            <>
              <h3 className="mb-2 mt-6 font-serif text-base font-bold text-foreground">
                资金费记录 · {funding.length} 笔
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] text-sm">
                  <thead>
                    <tr className="border-b border-paper text-xs text-muted-foreground">
                      <th className="py-2 text-left">结算时刻</th>
                      <th className="py-2 text-left">标的</th>
                      <th className="py-2 text-left">方向</th>
                      <th className="py-2 text-right">资金费率</th>
                      <th className="py-2 text-right">标记价</th>
                      <th className="py-2 text-right">数量</th>
                      <th className="py-2 text-right">金额</th>
                    </tr>
                  </thead>
                  <tbody>
                    {funding.map((f: PerpFunding) => {
                      const pay = num(f.payment)
                      const rate = num(f.funding_rate)
                      return (
                        <tr key={f.id} className="border-b border-paper/60">
                          <td className="py-2 text-xs text-muted-foreground">
                            {new Date(f.funding_ts).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                          </td>
                          <td className="py-2 font-mono text-xs">{f.symbol}</td>
                          <td className="py-2">
                            <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold text-white', f.side === 'long' ? 'bg-up' : 'bg-down')}>
                              {f.side === 'long' ? '多' : '空'}
                            </span>
                          </td>
                          <td className={cn('py-2 text-right font-mono text-xs', rate >= 0 ? 'text-up' : 'text-down')}>
                            {rate >= 0 ? '+' : ''}{(rate * 100).toFixed(4)}%
                          </td>
                          <td className="py-2 text-right font-mono text-xs">${fmtP(f.mark_price)}</td>
                          <td className="py-2 text-right font-mono text-xs">{num(f.quantity)}</td>
                          <td className={cn('py-2 text-right font-mono text-xs', pay > 0 ? 'text-down' : pay < 0 ? 'text-up' : 'text-muted-foreground/60')}>
                            {pay === 0 ? '0' : pay > 0 ? `付 ${fmtU(f.payment)}` : `收 ${fmtU(String(-pay))}`}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground/60">
                资金费率为正:多头付、空头收 · 每币按各自结算周期(8h/4h…)在整点结算 · 只扣虚拟现金
              </p>
            </>
          )}
        </>
      )}

      {confirm && (
        <PerpCloseConfirm
          pos={confirm}
          pending={placeOrder.isPending}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void doClose(confirm)}
        />
      )}
    </section>
  )
}

// ── 平仓确认(轻量)──────────────────────────────────────────────────────────
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
