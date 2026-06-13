'use client'

/**
 * 加密永续合约「下单指导」· 接真实虚拟撮合(ADR-0019 v2 · M2-C.1)。
 *
 * 取代 crypto-detail 里的占位 OrderGuidance:
 *   开多/开空 · 杠杆 1–20x slider · 保证金(虚拟 USDT)· 预估开仓量/强平价/手续费实时算
 *   · 当前活仓卡(浮盈/强平价/强平距离/ROE)· 平仓 · 确认模态必经 · sonner toast。
 *
 * 🔴 红线:全程【虚拟资金】· 绝不接真实交易所下单。所有动作走点金虚拟撮合引擎。
 *   策略只读提示绝不自动下单。
 *
 * 价源:perp 日 K 末根 close(预估用)· 真正成交价以后端 perp ticker 为准(D7/§4.1)。
 */

import Link from 'next/link'
import { useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'
import { toast } from 'sonner'

import { ConditionalOrderDialog } from '@/components/trading/conditional-order-dialog'
import { useFuturesInfo } from '@/hooks/use-crypto'
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

// 模式标注 · 强平语义因 mode 不同(逐仓=每仓强平价;全仓=账户级 · 该字段不展示)
const MODE_TIP: Record<'isolated' | 'cross', string> = {
  isolated: '逐仓:强平价只取决于开仓价与杠杆,与保证金金额无关',
  cross: '全仓:账户级强平 · 单仓不存在独立强平价(后端 worker 看整账户保证金率)',
}
function ModeTag({ mode }: { mode: 'isolated' | 'cross' }) {
  const label = mode === 'isolated' ? '逐仓' : '全仓'
  return (
    <span
      title={MODE_TIP[mode]}
      className="ml-1 cursor-help rounded bg-paper px-1 py-0.5 text-[9px] text-muted-foreground/80"
    >
      {label}
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
  const infoQ = useFuturesInfo(futuresSymbol)

  // 刀A1:预估价源改真标记价优先(premium_index 1min · 与后端撮合价同源);
  // kline 末根仅兜底(缓存零新鲜度 · 旧快照会让预估开仓量/强平价整组失真)。
  const markPrice = infoQ.data?.mark_price ?? klineQ.data?.items?.at(-1)?.close ?? null
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
  const [marginMode, setMarginMode] = useState<'isolated' | 'cross'>('isolated')
  const [confirm, setConfirm] = useState<PerpIntent | null>(null)
  // 持仓挂 SL/TP(ADR 0041 刀3 · 共享 ConditionalOrderDialog · 触发走 route_close_perp)
  const [sltpOpen, setSltpOpen] = useState(false)
  // perp 限价开仓(二期刀3 · 共享 ConditionalOrderDialog perp-limit · 触发走 route_open_perp)
  const [perpLimitOpen, setPerpLimitOpen] = useState(false)

  // 加仓(开同向)沿用持仓杠杆;反向 / 新开可调
  const sameSideAsPos = activePos != null && activePos.side === side
  const effLeverage = sameSideAsPos ? activePos!.leverage : leverage
  // MC-4:有活仓时,模式锁定为活仓模式(DP-7 同 symbol 单一模式 · 后端也守)
  const effMarginMode: 'isolated' | 'cross' =
    activePos != null ? activePos.margin_mode : marginMode

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
              // MC-4:开仓带 margin_mode → dispatcher 按此分流(平仓忽略,后端按活仓 mode 自动分流)
              margin_mode: effMarginMode,
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
      </div>

      {/* 当前活仓卡 */}
      {activePos && (
        <ActivePositionCard
          pos={activePos}
          onClose={() => setConfirm('close')}
          onSetSltp={() => setSltpOpen(true)}
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

      {/* 保证金模式(MC-4)· 有活仓 → 锁定为活仓 mode(DP-7 同 symbol 单一模式) */}
      <div className="mb-3">
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>保证金模式</span>
          {activePos != null && (
            <span className="font-mono text-[10px] text-gold">已锁定 · 与活仓一致</span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-2">
          {(['isolated', 'cross'] as const).map((m) => {
            const active = effMarginMode === m
            const disabled = activePos != null && activePos.margin_mode !== m
            return (
              <button
                key={m}
                type="button"
                disabled={disabled}
                onClick={() => activePos == null && setMarginMode(m)}
                aria-pressed={active}
                className={cn(
                  'rounded-md py-1.5 text-xs transition-colors',
                  active
                    ? 'border border-gold bg-gold/[0.08] font-medium text-gold'
                    : 'border border-paper text-muted-foreground/70 hover:border-gold/40',
                  disabled && 'cursor-not-allowed opacity-40 hover:border-paper',
                )}
              >
                {m === 'isolated' ? '逐仓 isolated' : '全仓 cross'}
              </button>
            )
          })}
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground/70">
          {effMarginMode === 'cross'
            ? '全仓:保证金不实扣,账户 USDT 作共享抵押 · 强平为账户级(MC-3)'
            : '逐仓:保证金从账户划出 · 每仓独立强平价 · 亏损封顶本仓保证金'}
        </p>
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
              <span className={cn('ml-1', estimate.liquidationDistancePct < 5 ? 'text-down' : 'text-muted-foreground/70')}>
                (距现价 {estimate.liquidationDistancePct.toFixed(2)}%)
              </span>
              <ModeTag mode={effMarginMode} />
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

      {/* 限价单入口(到价自动开多/开空 · 触发走后端 route_open_perp)·
          限价是未来触发,不受当前余额约束,authed + 账户即常驻 */}
      {authed && account != null && (
        <button
          type="button"
          onClick={() => setPerpLimitOpen(true)}
          className="mt-2 w-full rounded-md border border-gold/60 py-2 text-sm text-gold transition-colors hover:bg-gold/10"
        >
          挂限价单(到价自动开多 / 开空 · 虚拟)
        </button>
      )}

      {confirm && estimate != null && (
        <PerpConfirmModal
          intent={confirm}
          symbol={futuresSymbol}
          side={side}
          leverage={effLeverage}
          marginMode={effMarginMode}
          estimate={estimate}
          activePos={activePos}
          pending={placeOrder.isPending}
          onCancel={() => setConfirm(null)}
          onConfirm={() => void submit(confirm)}
        />
      )}

      {/* 持仓挂 SL/TP · 共享条件单弹层(触发时后端 route_close_perp 平仓) */}
      {sltpOpen && activePos && (
        <ConditionalOrderDialog
          open
          onClose={() => setSltpOpen(false)}
          symbol={futuresSymbol}
          market="crypto"
          mode="sltp"
          positionSide={activePos.side}
          heldQuantity={activePos.quantity}
          klineSymbol={klineSymbol}
        />
      )}

      {/* perp 限价开仓 · 共享条件单弹层 perp-limit(触发时后端 route_open_perp 开多/开空) */}
      {perpLimitOpen && (
        <ConditionalOrderDialog
          open
          onClose={() => setPerpLimitOpen(false)}
          symbol={futuresSymbol}
          market="crypto"
          mode="perp-limit"
          klineSymbol={klineSymbol}
        />
      )}
    </div>
  )
}

// ── 活仓卡 ───────────────────────────────────────────────────────────────────
function ActivePositionCard({
  pos, onClose, onSetSltp, closing,
}: { pos: PerpPosition; onClose: () => void; onSetSltp: () => void; closing: boolean }) {
  const upnl = pos.unrealized_pnl != null ? Number(pos.unrealized_pnl) : null
  const roe = pos.roe_pct != null ? Number(pos.roe_pct) : null
  const dist = pos.liquidation_distance_pct != null ? Number(pos.liquidation_distance_pct) : null
  const longSide = pos.side === 'long'
  return (
    <div className="mb-3 rounded-md border border-paper bg-surface-card p-3 text-xs">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5">
          <span className={cn('rounded px-1.5 py-0.5 text-[10px] font-bold text-white', longSide ? 'bg-up' : 'bg-down')}>
            {longSide ? '多' : '空'} {pos.leverage}x
          </span>
          <span className="font-mono">{Number(pos.quantity)} @ ${fmtP(Number(pos.entry_price))}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onSetSltp}
            className="rounded border border-gold/60 px-2 py-0.5 text-[11px] text-gold hover:bg-gold/10"
          >
            止损/止盈
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={closing}
            className="rounded border border-midas-red px-2 py-0.5 text-[11px] text-midas-red hover:bg-midas-red-glow/40 disabled:opacity-50"
          >
            平仓
          </button>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono">
        <Cell label="浮动盈亏" v={upnl != null ? `${upnl >= 0 ? '+' : ''}${fmtU(upnl)}` : '—'} tone={upnl == null ? undefined : upnl >= 0 ? 'bull' : 'bear'} />
        <Cell label="ROE" v={roe != null ? `${roe >= 0 ? '+' : ''}${roe.toFixed(2)}%` : '—'} tone={roe == null ? undefined : roe >= 0 ? 'bull' : 'bear'} />
        <Cell label="标记价" v={pos.mark_price != null ? `$${fmtP(Number(pos.mark_price))}` : '—'} />
        <Cell
          label={<>强平价<ModeTag mode={pos.margin_mode} /></>}
          v={
            pos.margin_mode === 'cross'
              ? '—(账户级)'
              : `$${fmtP(Number(pos.liquidation_price))}${dist != null ? ` (${dist.toFixed(1)}%)` : ''}`
          }
          tone={pos.margin_mode === 'isolated' && dist != null && dist < 5 ? 'bear' : undefined}
        />
      </div>
      {pos.margin_mode === 'isolated' && dist != null && dist < 5 && (
        <p className="mt-1.5 text-[10px] text-down">⚠️ 强平距离仅 {dist.toFixed(1)}% · 建议降杠杆 / 加保证金(虚拟)</p>
      )}
    </div>
  )
}

function Cell({ label, v, tone }: { label: React.ReactNode; v: string; tone?: 'bull' | 'bear' }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground/70">{label}</span>
      <span className={cn(tone === 'bull' ? 'text-up' : tone === 'bear' ? 'text-down' : 'text-foreground')}>{v}</span>
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
  intent, symbol, side, leverage, marginMode, estimate, activePos, pending, onCancel, onConfirm,
}: {
  intent: PerpIntent
  symbol: string
  side: PerpSide
  leverage: number
  marginMode: 'isolated' | 'cross'
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
        <h3 className="mb-5 text-center font-serif text-lg font-bold">{title}</h3>
        <dl className="space-y-2.5 text-sm">
          <ModalRow label="标的"><span className="font-mono">{symbol}</span></ModalRow>
          {isClose && activePos ? (
            <>
              <ModalRow label="保证金模式">
                <span className={cn(
                  'rounded border px-2 py-0.5 text-[11px] font-mono',
                  activePos.margin_mode === 'cross'
                    ? 'border-gold bg-gold/[0.08] text-gold'
                    : 'border-paper text-muted-foreground',
                )}>
                  {activePos.margin_mode === 'cross' ? '全仓 cross' : '逐仓 isolated'}
                </span>
              </ModalRow>
              <ModalRow label="方向">
                <span className={cn('rounded px-2 py-0.5 text-xs text-white', activePos.side === 'long' ? 'bg-up' : 'bg-down')}>
                  平{activePos.side === 'long' ? '多' : '空'} {activePos.leverage}x
                </span>
              </ModalRow>
              <ModalRow label="平仓量"><span className="font-mono">{Number(activePos.quantity)}(全部)</span></ModalRow>
              {activePos.unrealized_pnl != null && (
                <ModalRow label="当前浮盈">
                  <span className={cn('font-mono', Number(activePos.unrealized_pnl) >= 0 ? 'text-up' : 'text-down')}>
                    {Number(activePos.unrealized_pnl) >= 0 ? '+' : ''}{fmtU(Number(activePos.unrealized_pnl))} USDT
                  </span>
                </ModalRow>
              )}
            </>
          ) : estimate && (
            <>
              <ModalRow label="保证金模式">
                <span className={cn(
                  'rounded border px-2 py-0.5 text-[11px] font-mono',
                  marginMode === 'cross'
                    ? 'border-gold bg-gold/[0.08] text-gold'
                    : 'border-paper text-muted-foreground',
                )}>
                  {marginMode === 'cross' ? '全仓 cross' : '逐仓 isolated'}
                </span>
              </ModalRow>
              <ModalRow label="方向">
                <span className="rounded bg-midas-red px-2 py-0.5 text-xs text-white">
                  {side === 'long' ? '开多' : '开空'} {leverage}x
                </span>
              </ModalRow>
              <ModalRow label={marginMode === 'cross' ? '保证金(要求)' : '保证金'}>
                <span className="font-mono">{fmtU(estimate.requiredMargin)} USDT</span>
              </ModalRow>
              <ModalRow label="预估开仓量"><span className="font-mono">{estimate.quantity.toFixed(estimate.quantity >= 1 ? 4 : 6)} {base(symbol)}</span></ModalRow>
              <ModalRow label="预估强平价">
                <span className="font-mono">
                  {marginMode === 'cross' ? '— · 账户级强平(MC-3)' : `$${fmtP(estimate.liquidationPrice)}`}
                </span>
              </ModalRow>
              <ModalRow label="预估手续费"><span className="font-mono">{fmtU(estimate.fee)} USDT</span></ModalRow>
            </>
          )}
        </dl>
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
