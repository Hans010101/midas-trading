'use client'

/**
 * 加密永续合约「下单指导」· 接真实虚拟撮合(ADR-0019 v2 · M2-C.1)。
 *
 * 取代 crypto-detail 里的占位 OrderGuidance:
 *   开多/开空 · 杠杆 1–20x slider · 保证金(虚拟 USDT)· 预估开仓量/强平价/手续费实时算
 *   · 当前活仓卡(浮盈/强平价/强平距离/ROE)· 平仓 · 确认模态必经 · sonner toast。
 *
 * 🔴 红线:全程【虚拟资金】· 绝不接真实交易所下单。所有动作走点金虚拟撮合引擎。
 *   策略只读提示绝不自动下单。带「VIRTUAL·模拟」徽章 + 「仅供参考,不构成投资建议」。
 *
 * 价源:perp 日 K 末根 close(预估用)· 真正成交价以后端 perp ticker 为准(D7/§4.1)。
 */

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'
import { toast } from 'sonner'

import { VirtualBadge } from '@/components/ui/virtual-badge'
import { useKline } from '@/hooks/use-kline'
import { usePerpPositions, usePlacePerpOrder } from '@/hooks/use-perp'
import { useAccount } from '@/hooks/use-virtual'
import {
  PERP_MAX_LEVERAGE,
  PERP_MIN_LEVERAGE,
  PerpApiError,
  type PerpIntent,
  type PerpPosition,
  type PerpSide,
  estimatePerpOpen,
} from '@/lib/api/perp'
import { cn } from '@/lib/utils'

const fmtP = (n: number): string =>
  n >= 1 ? n.toLocaleString('en-US', { maximumFractionDigits: 2 }) : n.toFixed(4)
const fmtU = (n: number): string =>
  `${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
const numOr = (s: string | null, d = 0): number => (s == null ? d : Number(s) || d)

// 逐仓标注(问题2)· 强平价旁说明强平价与保证金金额无关
const ISOLATED_TIP = '逐仓:强平价只取决于开仓价与杠杆,与保证金金额无关'
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

interface Props {
  /** Binance 风格 'BTCUSDT' */
  futuresSymbol: string
  /** ccxt 风格 'BTC/USDT'(取 perp 日 K 用) */
  klineSymbol: string
}

export function PerpOrderGuidance({ futuresSymbol, klineSymbol }: Props) {
  const { status } = useSession()
  const authed = status === 'authenticated'

  const { data: account } = useAccount('crypto') // null = 未激活
  const positionsQ = usePerpPositions()
  const placeOrder = usePlacePerpOrder()
  const klineQ = useKline({
    symbol: klineSymbol, market: 'crypto', period: '1d', limit: 1, instrument: 'perp',
  })

  const markPrice = klineQ.data?.items?.at(-1)?.close ?? null
  const activePos = useMemo<PerpPosition | null>(
    () =>
      (positionsQ.data ?? []).find(
        (p) => p.symbol === futuresSymbol && p.closed_at === null,
      ) ?? null,
    [positionsQ.data, futuresSymbol],
  )

  const [side, setSide] = useState<PerpSide>('long')
  const [leverage, setLeverage] = useState(10)
  const [margin, setMargin] = useState('1000')
  const [confirm, setConfirm] = useState<PerpIntent | null>(null)

  // 加仓(开同向)沿用持仓杠杆;反向 / 新开可调
  const sameSideAsPos = activePos != null && activePos.side === side
  const effLeverage = sameSideAsPos ? activePos!.leverage : leverage

  const marginNum = Number(margin) || 0
  const estimate =
    markPrice && marginNum > 0
      ? estimatePerpOpen(markPrice, side, marginNum, effLeverage)
      : null
  const available = numOr(account?.cash_balance ?? null)
  const canOpen =
    authed && account != null && estimate != null
    && estimate.requiredMargin + estimate.fee <= available
    && !placeOrder.isPending

  const sideZh = (s: PerpSide): string => (s === 'long' ? '开多' : '开空')

  async function submit(intent: PerpIntent) {
    try {
      const order = await placeOrder.mutateAsync(
        intent === 'close'
          ? { symbol: futuresSymbol, intent, close_all: true }
          : {
              symbol: futuresSymbol, intent, leverage: effLeverage,
              margin: margin.trim(),
            },
      )
      if (order.status === 'filled') {
        const label =
          intent === 'close'
            ? `平仓 ${futuresSymbol}`
            : `${sideZh(side)} ${futuresSymbol} ${effLeverage}x`
        const pnl =
          order.realized_pnl != null
            ? ` · 已实现 ${fmtU(Number(order.realized_pnl))} USDT`
            : ''
        toast.success(`${label} 已成交(虚拟)${pnl}`, {
          className: 'midas-toast-success', duration: 4000,
        })
      } else {
        toast.error(`下单被拒 · ${order.reject_reason ?? '未知原因'}`, { duration: 5000 })
      }
    } catch (e) {
      toast.error(e instanceof PerpApiError ? e.detail : '下单失败')
    } finally {
      setConfirm(null)
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-gold/60 bg-gold/5 p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="font-serif text-base font-bold">下单指导</span>
        <VirtualBadge size="sm" />
      </div>

      {/* 当前活仓卡 */}
      {activePos && (
        <ActivePositionCard
          pos={activePos}
          onClose={() => setConfirm('close')}
          closing={placeOrder.isPending}
        />
      )}

      {/* 开多 / 开空 */}
      <div className="mb-3 grid grid-cols-2 gap-2">
        <button
          type="button"
          onClick={() => setSide('long')}
          className={cn(
            'rounded-md py-2 text-sm font-medium transition-colors',
            side === 'long'
              ? 'bg-midas-red text-white'
              : 'border border-midas-red/50 text-midas-red hover:bg-midas-red-glow/40',
          )}
        >
          开多(虚拟)
        </button>
        <button
          type="button"
          onClick={() => setSide('short')}
          className={cn(
            'rounded-md py-2 text-sm font-medium transition-colors',
            side === 'short'
              ? 'bg-midas-red text-white'
              : 'border border-midas-red/50 text-midas-red hover:bg-midas-red-glow/40',
          )}
        >
          开空(虚拟)
        </button>
      </div>

      {/* 杠杆 */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>杠杆</span>
          <span className="font-mono font-bold text-foreground">{effLeverage}x</span>
        </div>
        <input
          type="range"
          min={PERP_MIN_LEVERAGE}
          max={PERP_MAX_LEVERAGE}
          step={1}
          value={effLeverage}
          disabled={sameSideAsPos}
          onChange={(e) => setLeverage(Number(e.target.value))}
          className="w-full accent-midas-red disabled:opacity-50"
        />
        {sameSideAsPos && (
          <p className="mt-0.5 text-[10px] text-gold">加仓沿用当前持仓杠杆 {activePos!.leverage}x</p>
        )}
      </div>

      {/* 保证金 */}
      <div className="mb-3">
        <div className="mb-1 text-xs text-muted-foreground">保证金(虚拟 USDT)</div>
        <input
          type="number"
          value={margin}
          min={0}
          step={50}
          onChange={(e) => setMargin(e.target.value)}
          className="h-9 w-full rounded-md border border-paper bg-background px-3 text-right font-mono text-sm"
        />
      </div>

      {/* 预估 */}
      <dl className="mb-3 space-y-1.5 rounded-md bg-background/60 px-3 py-2 text-xs">
        <EstRow label="预估开仓量">
          {estimate ? `${estimate.quantity.toFixed(estimate.quantity >= 1 ? 4 : 6)} ${base(futuresSymbol)}` : '—'}
        </EstRow>
        <EstRow label="预估强平价">
          {estimate ? (
            <>
              <span className="font-mono">${fmtP(estimate.liquidationPrice)}</span>
              <span className={cn('ml-1', estimate.liquidationDistancePct < 5 ? 'text-bear' : 'text-muted-foreground/70')}>
                (距现价 {estimate.liquidationDistancePct.toFixed(2)}%)
              </span>
              <IsolatedTag />
            </>
          ) : '—'}
        </EstRow>
        <EstRow label="预估手续费">{estimate ? `${fmtU(estimate.fee)} USDT` : '—'}</EstRow>
        <EstRow label="可用 USDT">{account ? `${fmtU(available)} USDT` : '—'}</EstRow>
      </dl>

      {/* 动作 / 状态 */}
      {!authed ? (
        <Link
          href="/login"
          className="block rounded-md border border-midas-red py-2 text-center text-sm text-midas-red hover:bg-midas-red-glow/40"
        >
          登录后开始虚拟合约交易
        </Link>
      ) : account == null ? (
        <Link
          href="/account"
          className="block rounded-md border border-gold bg-gold/10 py-2 text-center text-sm text-gold"
        >
          去「我的账户」设置加密虚拟 USDT
        </Link>
      ) : (
        <button
          type="button"
          disabled={!canOpen}
          onClick={() => setConfirm(side === 'long' ? 'open_long' : 'open_short')}
          className={cn(
            'w-full rounded-md py-2.5 text-sm font-medium text-white transition-colors',
            canOpen ? 'bg-midas-red hover:bg-midas-red-deep' : 'cursor-not-allowed bg-midas-red/30',
          )}
        >
          确认{sideZh(side)}(虚拟)
        </button>
      )}
      {authed && account != null && estimate != null && !canOpen && !placeOrder.isPending && (
        <p className="mt-2 text-center text-[11px] text-midas-red">
          保证金 + 手续费 {fmtU(estimate.requiredMargin + estimate.fee)} 超过可用 {fmtU(available)} USDT
        </p>
      )}

      <p className="mt-3 text-[10px] leading-relaxed text-muted-foreground/70">
        全程虚拟资金 · 绝不接真实交易所下单 · 杠杆/做空/强平均为模拟教学 ·
        所有动作走点金虚拟撮合 · 仅供参考,不构成投资建议
      </p>

      {confirm && estimate != null && (
        <PerpConfirmModal
          intent={confirm}
          symbol={futuresSymbol}
          side={side}
          leverage={effLeverage}
          estimate={estimate}
          activePos={activePos}
          pending={placeOrder.isPending}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void submit(confirm)}
        />
      )}
    </div>
  )
}

// ── 活仓卡 ───────────────────────────────────────────────────────────────────
function ActivePositionCard({
  pos, onClose, closing,
}: { pos: PerpPosition; onClose: () => void; closing: boolean }) {
  const upnl = pos.unrealized_pnl != null ? Number(pos.unrealized_pnl) : null
  const roe = pos.roe_pct != null ? Number(pos.roe_pct) : null
  const dist = pos.liquidation_distance_pct != null ? Number(pos.liquidation_distance_pct) : null
  const longSide = pos.side === 'long'
  return (
    <div className="mb-3 rounded-md border border-paper bg-cream/60 p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold text-white', longSide ? 'bg-bull' : 'bg-bear')}>
            {longSide ? '多' : '空'} {pos.leverage}x
          </span>
          <span className="font-mono">{Number(pos.quantity)} @ ${fmtP(Number(pos.entry_price))}</span>
        </span>
        <button
          type="button"
          onClick={onClose}
          disabled={closing}
          className="rounded border border-midas-red px-2 py-0.5 text-[11px] text-midas-red hover:bg-midas-red-glow/40 disabled:opacity-50"
        >
          平仓
        </button>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
        <Cell label="浮动盈亏" v={upnl != null ? `${upnl >= 0 ? '+' : ''}${fmtU(upnl)}` : '—'} tone={upnl == null ? undefined : upnl >= 0 ? 'bull' : 'bear'} />
        <Cell label="ROE" v={roe != null ? `${roe >= 0 ? '+' : ''}${roe.toFixed(2)}%` : '—'} tone={roe == null ? undefined : roe >= 0 ? 'bull' : 'bear'} />
        <Cell label="标记价" v={pos.mark_price != null ? `$${fmtP(Number(pos.mark_price))}` : '—'} />
        <Cell
          label={<>强平价<IsolatedTag /></>}
          v={`$${fmtP(Number(pos.liquidation_price))}${dist != null ? ` (${dist.toFixed(1)}%)` : ''}`}
          tone={dist != null && dist < 5 ? 'bear' : undefined}
        />
      </div>
      {dist != null && dist < 5 && (
        <p className="mt-1.5 text-[10px] text-bear">⚠️ 强平距离仅 {dist.toFixed(1)}% · 建议降杠杆 / 加保证金(虚拟)</p>
      )}
    </div>
  )
}

function Cell({ label, v, tone }: { label: React.ReactNode; v: string; tone?: 'bull' | 'bear' }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground/70">{label}</span>
      <span className={cn(tone === 'bull' ? 'text-bull' : tone === 'bear' ? 'text-bear' : 'text-foreground')}>{v}</span>
    </div>
  )
}

function EstRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted-foreground/70">{label}</dt>
      <dd className="text-right text-foreground">{children}</dd>
    </div>
  )
}

// ── 确认模态(必经)──────────────────────────────────────────────────────────
function PerpConfirmModal({
  intent, symbol, side, leverage, estimate, activePos, pending, onCancel, onConfirm,
}: {
  intent: PerpIntent
  symbol: string
  side: PerpSide
  leverage: number
  estimate: ReturnType<typeof estimatePerpOpen>
  activePos: PerpPosition | null
  pending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const isClose = intent === 'close'
  const title = isClose ? '确认平仓(虚拟)' : `确认${side === 'long' ? '开多' : '开空'}(虚拟)`
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => { if (e.target === e.currentTarget) onCancel() }}
    >
      <div className="w-full max-w-sm rounded-lg border border-midas-red bg-cream p-6 shadow-xl">
        <div className="mb-3 flex justify-center"><VirtualBadge size="sm" /></div>
        <h3 className="mb-5 text-center font-serif text-lg font-bold">{title}</h3>
        <dl className="space-y-2.5 text-sm">
          <ModalRow label="标的"><span className="font-mono">{symbol}</span></ModalRow>
          {isClose && activePos ? (
            <>
              <ModalRow label="方向">
                <span className={cn('rounded px-2 py-0.5 text-xs text-white', activePos.side === 'long' ? 'bg-bull' : 'bg-bear')}>
                  平{activePos.side === 'long' ? '多' : '空'} {activePos.leverage}x
                </span>
              </ModalRow>
              <ModalRow label="平仓量"><span className="font-mono">{Number(activePos.quantity)}(全部)</span></ModalRow>
              {activePos.unrealized_pnl != null && (
                <ModalRow label="当前浮盈">
                  <span className={cn('font-mono', Number(activePos.unrealized_pnl) >= 0 ? 'text-bull' : 'text-bear')}>
                    {Number(activePos.unrealized_pnl) >= 0 ? '+' : ''}{fmtU(Number(activePos.unrealized_pnl))} USDT
                  </span>
                </ModalRow>
              )}
            </>
          ) : estimate && (
            <>
              <ModalRow label="方向">
                <span className="rounded bg-midas-red px-2 py-0.5 text-xs text-white">
                  {side === 'long' ? '开多' : '开空'} {leverage}x
                </span>
              </ModalRow>
              <ModalRow label="保证金"><span className="font-mono">{fmtU(estimate.requiredMargin)} USDT</span></ModalRow>
              <ModalRow label="预估开仓量"><span className="font-mono">{estimate.quantity.toFixed(estimate.quantity >= 1 ? 4 : 6)} {base(symbol)}</span></ModalRow>
              <ModalRow label="预估强平价"><span className="font-mono">${fmtP(estimate.liquidationPrice)}</span></ModalRow>
              <ModalRow label="预估手续费"><span className="font-mono">{fmtU(estimate.fee)} USDT</span></ModalRow>
            </>
          )}
        </dl>
        <p className="mt-4 text-center text-[10px] text-muted-foreground/70">
          本次为模拟交易,不构成投资建议 · 全程虚拟资金
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md border border-paper bg-background px-4 py-2 text-sm hover:bg-cream">
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className={cn('rounded-md px-4 py-2 text-sm font-medium text-white', pending ? 'cursor-not-allowed bg-midas-red/40' : 'bg-midas-red hover:bg-midas-red-deep')}
          >
            {pending ? '提交中…' : '确认'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ModalRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  )
}

function base(binanceSymbol: string): string {
  for (const q of ['USDT', 'USDC', 'BUSD', 'FDUSD']) {
    if (binanceSymbol.endsWith(q) && binanceSymbol.length > q.length) {
      return binanceSymbol.slice(0, -q.length)
    }
  }
  return binanceSymbol
}
