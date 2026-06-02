'use client'

/**
 * 现货下单区(0023 阶段③ · 3.4 批2)· 详情页右栏。
 *
 * 差异化(决策③④):
 *   · A股(cn):纯现货做多 · 买入(开)/ 卖出(平)· T+1 + 涨跌停提示 · position_side 不传(后端默认 long)
 *   · 美股(us):做多 + 卖空(无杠杆 1:1)· tab 切换
 *       - 做多:买入(开)/ 卖出(平)· position_side=long(不传)
 *       - 卖空:卖出(开空)/ 买入(平空)· position_side=short · 接 3.4 批1 引擎
 *
 * 复用:usePlaceOrder / useAccount / usePositions / useKline / estimateOrder / formatMoney(0008)。
 * 现金语义:
 *   - 买入做多 / 卖出开空 = 开仓 · 需现金(成本 / 担保 = notional + 手续费)· 校验余额
 *   - 卖出平多 / 买入平空 = 平仓 · 不需预付现金 · 数量受持仓上限约束
 *
 * 红线:全程虚拟资金 · 美股卖空只是虚拟负持仓记账 · 绝不接真实交易。
 */

import Link from 'next/link'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { useSession } from 'next-auth/react'
import { useAccount, useHkBoardLot, usePlaceOrder, usePositions } from '@/hooks/use-virtual'
import { useKline } from '@/hooks/use-kline'
import { VirtualApiError, type OrderSide, type PositionSide } from '@/lib/api/virtual'
import { estimateOrder } from '@/lib/fees'
import { MARKET_LABEL, currencyOf, formatMoney } from '@/lib/format-money'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

type Tab = 'long' | 'short'

interface SpotOrderPanelProps {
  symbol: string
  name?: string | null
  // 港股阶段三单元3:hk 加入(纯做多 · T+0 · 按手 board lot 取整 · 全程虚拟)
  market: 'cn' | 'us' | 'hk'
}

interface PendingAction {
  side: OrderSide
  positionSide: PositionSide
  /** 开仓(需现金)还是平仓(受持仓约束) */
  intent: 'open' | 'close'
  label: string
}

function defaultQty(market: 'cn' | 'us' | 'hk'): string {
  if (market === 'cn') return '100'
  if (market === 'hk') return '' // 港股:board lot 载入后由 effect 填 1 手(每手股数因股而异)
  return '1'
}

export function SpotOrderPanel({ symbol, name, market }: SpotOrderPanelProps) {
  const { status } = useSession()
  const authed = status === 'authenticated'
  const account = useAccount(market)
  const positions = usePositions({ market })
  const [tab, setTab] = useState<Tab>('long')
  const [quantity, setQuantity] = useState(defaultQty(market))
  const [pending, setPending] = useState<PendingAction | null>(null)

  // 港股每手股数(board lot)· 只读配置 · 非 hk 不请求(enabled=false)· 用于按手取整 + UI 提示 + 不在池禁用
  const boardLotQuery = useHkBoardLot(symbol, market === 'hk')
  const boardLot = boardLotQuery.data ?? null
  // ★ A2b 不在下单池:hk + 查询完成 + 返 null(后端 board-lot 404 = resolve None)→ 彻底禁用下单
  const hkNotInPool = market === 'hk' && boardLotQuery.isSuccess && boardLotQuery.data === null
  const hkLotLoading = market === 'hk' && boardLotQuery.isLoading
  // 港股:lot 首次载入时填默认 1 手(只填一次 · 用户清空后不强行回填)
  const hkInitDone = useRef(false)
  useEffect(() => {
    if (market === 'hk' && boardLot && !hkInitDone.current) {
      setQuantity(String(boardLot))
      hkInitDone.current = true
    }
  }, [market, boardLot])

  // 当前标的 · 当前方向的活仓(用于平仓上限 + 展示)
  const heldPosition = useMemo(() => {
    const wanted: PositionSide = market === 'us' ? tab : 'long'
    return (positions.data ?? []).find(
      (p) => p.symbol === symbol && p.position_side === wanted && Number(p.quantity) > 0,
    )
  }, [positions.data, symbol, market, tab])
  const heldQty = heldPosition ? Number(heldPosition.quantity) : 0

  // ===== 未登录 / 未激活 网关 =====
  if (!authed) {
    return (
      <PanelShell>
        <GateNote
          title="登录后可下单"
          hint="点金全程账户资金,登录即可买卖。"
          href="/login"
          cta="去登录"
        />
      </PanelShell>
    )
  }
  // ★ A2b 港股不在下单池:lot 表无该标的(非主板 HKD / 采不到 lot)→ resolve None → 彻底禁用下单。
  //    早返不渲染买卖按钮 → 用户根本点不到、不弹确认模态(修「不在池仍弹确认」bug)。
  //    放在激活网关【前】:不在池的标的不必先提示激活(本就不能交易)· cn/us/crypto 不进此分支。
  if (hkLotLoading) {
    return (
      <PanelShell>
        <p className="py-6 text-center text-xs text-muted-foreground/60">载入每手股数…</p>
      </PanelShell>
    )
  }
  if (hkNotInPool) {
    return (
      <PanelShell>
        <div className="rounded-md border border-dashed border-paper bg-cream p-4 text-center">
          <p className="mb-1 text-sm font-medium text-foreground">该标的暂不可下单</p>
          <p className="text-xs leading-relaxed text-muted-foreground/80">
            仅港股主板 HKD(~2406 只)支持虚拟下单 · 该标的不在下单池(行情仍可正常查看)。
          </p>
        </div>
      </PanelShell>
    )
  }
  if (account.isSuccess && account.data === null) {
    return (
      <PanelShell>
        <GateNote
          title={`${MARKET_LABEL[market]}账户资金未激活`}
          hint="先到设置页设定该市场的初始账户资金,再来下单。"
          href="/settings/wallet"
          cta="去激活"
        />
      </PanelShell>
    )
  }

  const activePositionSide: PositionSide = market === 'us' ? tab : 'long'

  function openConfirm(side: OrderSide, intent: 'open' | 'close', label: string) {
    setPending({ side, positionSide: activePositionSide, intent, label })
  }

  return (
    <PanelShell>
      {/* 美股:做多 / 卖空 tab · A股不显示(纯做多) */}
      {market === 'us' && (
        <div className="mb-3 flex overflow-hidden rounded-md border border-paper text-sm">
          {(['long', 'short'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => {
                setTab(t)
                setQuantity(defaultQty(market))
              }}
              className={cn(
                'flex-1 px-3 py-1.5 transition-colors',
                tab === t ? 'bg-midas-red text-white' : 'text-muted-foreground hover:bg-midas-red-glow/50',
              )}
            >
              {t === 'long' ? '做多' : '卖空'}
            </button>
          ))}
        </div>
      )}

      {/* 持仓提示 */}
      <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
        <span>
          当前{market === 'us' && tab === 'short' ? '空头' : '持仓'}
        </span>
        <span className="font-mono text-foreground">
          {heldQty > 0
            ? `${heldQty} @ ${formatMoney(heldPosition!.avg_entry_price, currencyOf(market))}`
            : '无'}
        </span>
      </div>

      {/* 数量输入 */}
      <label className="mb-1 block text-xs text-muted-foreground">数量</label>
      <input
        type="number"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        min={0}
        step={market === 'cn' ? 100 : market === 'hk' ? (boardLot ?? 100) : 1}
        placeholder={market === 'hk' && boardLot ? `每手 ${boardLot} 股` : undefined}
        className={cn(
          'h-9 w-full rounded border border-paper bg-background px-3 text-right font-mono text-sm',
          market === 'hk' ? 'mb-1' : 'mb-3',
        )}
      />
      {market === 'hk' && boardLot && (
        <p className="mb-3 text-[11px] leading-relaxed text-muted-foreground/70">
          每手 {boardLot} 股 · 实际下单按手取整(不足一手不可下单)
        </p>
      )}

      {/* 操作按钮 · 开仓 / 平仓 两枚 */}
      {activePositionSide === 'long' ? (
        <div className="grid grid-cols-2 gap-2">
          <OrderButton variant="solid" onClick={() => openConfirm('buy', 'open', '买入(做多)')}>
            买入
          </OrderButton>
          <OrderButton variant="outline" onClick={() => openConfirm('sell', 'close', '卖出(平多)')}>
            卖出
          </OrderButton>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <OrderButton variant="solid" onClick={() => openConfirm('sell', 'open', '卖出(开空)')}>
            卖出开空
          </OrderButton>
          <OrderButton variant="outline" onClick={() => openConfirm('buy', 'close', '买入(平空)')}>
            买入平空
          </OrderButton>
        </div>
      )}

      {/* 市场提示 */}
      {market === 'cn' ? (
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
          A股 T+1:当日买入次日方可卖出 · ±10%/20% 涨跌停限制 ·
          按最新价成交,不强制 T+1 / 涨跌停。
        </p>
      ) : market === 'hk' ? (
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
          港股 T+0:当日可买卖 · 无涨跌停 · 按手交易(每手 {boardLot ?? '—'} 股)·
          虚拟费率含印花税 0.1% + 佣金 0.1% · 按最新价成交。
        </p>
      ) : (
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
          {tab === 'short'
            ? '卖空 = 虚拟负持仓记账 · 无杠杆 1:1 锁定等额现金担保 · 无强平/资金费。'
            : '美股做多 · 现货买卖 · 按最新价成交。'}
        </p>
      )}

      {pending && (
        <SpotOrderConfirm
          symbol={symbol}
          name={name}
          market={market}
          action={pending}
          quantity={quantity}
          boardLot={boardLot}
          heldQty={heldQty}
          availableCash={account.data ? Number(account.data.cash_balance) : 0}
          onClose={() => setPending(null)}
        />
      )}
    </PanelShell>
  )
}

// ===== 确认模态 =====

interface ConfirmProps {
  symbol: string
  name?: string | null
  market: 'cn' | 'us' | 'hk'
  action: PendingAction
  quantity: string
  // 港股每手股数(board lot)· 非 hk 为 null · 用于确认前按手取整
  boardLot: number | null
  heldQty: number
  availableCash: number
  onClose: () => void
}

function SpotOrderConfirm({
  symbol, name, market, action, quantity, boardLot, heldQty, availableCash, onClose,
}: ConfirmProps) {
  const currency = currencyOf(market)
  const place = usePlaceOrder()
  const { data: kline } = useKline({
    symbol, market: market as Market, period: '1d', limit: 1,
  })
  const marketPrice = kline?.items?.at(-1)?.close ?? null
  const qtyRaw = Number(quantity) || 0
  // ★ 港股按手取整:floor(qty/lot)*lot · 不足一手 → 0(不可下单)· 与后端 place_order 同口径
  //   实际执行 / 展示 / 估算 / 提交都用 lotQty(cn/us 时 lotQty === qtyRaw,零影响)
  const lotQty = market === 'hk' && boardLot ? Math.floor(qtyRaw / boardLot) * boardLot : qtyRaw

  const estimate = marketPrice && lotQty > 0
    ? estimateOrder(market as Market, action.side, marketPrice, lotQty)
    : null

  // 现金影响 · 开仓需现金(买做多成本 / 卖空担保 = notional + 手续费);平仓不需预付
  const cashNeeded =
    action.intent === 'open' && estimate ? estimate.notional + estimate.commission : 0
  const enoughCash = action.intent !== 'open' || (estimate !== null && cashNeeded <= availableCash)
  const enoughPosition = action.intent !== 'close' || lotQty <= heldQty

  const canSubmit =
    !place.isPending && lotQty > 0 && estimate !== null && enoughCash && enoughPosition

  async function handleSubmit() {
    try {
      const order = await place.mutateAsync({
        symbol,
        market: market as Market,
        side: action.side,
        // ★ 港股送按手取整后的 lotQty(后端 place_order 会再次取整 · 同口径幂等)
        quantity: market === 'hk' ? String(lotQty) : quantity.trim(),
        // A股 / 美股做多 不传(后端默认 long · 字节同 0008)· 仅美股卖空传 short
        ...(action.positionSide === 'short' ? { position_side: 'short' as const } : {}),
      })
      if (order.status === 'filled') {
        const realized = order.realized_pnl
        toast.success(
          `${action.label} ${market === 'hk' ? lotQty : quantity} ${symbol} 已成交` +
            (realized ? ` · 已实现 ${formatMoney(realized, currency)}` : ''),
          { className: 'midas-toast-success', duration: 4000 },
        )
      } else {
        toast.error(`下单被拒 · ${order.reject_reason ?? '未知原因'}`, { duration: 5000 })
      }
      onClose()
    } catch (e) {
      toast.error(e instanceof VirtualApiError ? e.detail : '下单失败')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="w-full max-w-md rounded-lg border border-midas-red bg-cream p-6 shadow-xl">
        <h3 className="mb-5 text-center font-serif text-xl font-bold text-foreground">确认下单</h3>

        <dl className="space-y-3 text-sm">
          <Row label="标的">
            <span className="font-mono">{symbol}</span>
            {name && <span className="ml-2 text-xs text-muted-foreground">· {name}</span>}
          </Row>
          <Row label="操作">
            <span className="rounded bg-midas-red px-2 py-0.5 text-xs font-medium text-white">
              {action.label}
            </span>
          </Row>
          <Row label="数量">
            <span className="font-mono">{market === 'hk' ? lotQty : quantity}</span>
            {market === 'hk' && boardLot && lotQty > 0 && lotQty !== qtyRaw && (
              <span className="ml-2 text-[10px] text-muted-foreground/70">
                · 按手取整(每手 {boardLot})
              </span>
            )}
          </Row>

          <div className="my-2 border-t border-paper" />

          <Row label="市场价" muted>
            <span className="font-mono">
              {marketPrice ? formatMoney(marketPrice, currency) : '—'}
            </span>
          </Row>
          <Row label="预估成交价" muted>
            <span className="font-mono">
              {estimate ? formatMoney(estimate.fillPrice, currency, { decimals: 4 }) : '—'}
              <span className="ml-1 text-xs text-muted-foreground/70">(含滑点)</span>
            </span>
          </Row>
          {market !== 'us' && (
            <Row label="预估手续费" muted>
              <span className="font-mono">
                {estimate ? formatMoney(estimate.commission, currency, { decimals: 4 }) : '—'}
              </span>
            </Row>
          )}

          <div className="my-2 border-t border-paper" />

          {action.intent === 'open' ? (
            <>
              <Row label={action.positionSide === 'short' ? '锁定担保' : '预估成本'}>
                <span className="font-mono text-base font-bold text-midas-red">
                  {estimate ? formatMoney(cashNeeded, currency) : '—'}
                </span>
              </Row>
              <Row label="可用余额" muted>
                <span className="font-mono">{formatMoney(availableCash, currency)}</span>
              </Row>
            </>
          ) : (
            <Row label="可平数量" muted>
              <span className="font-mono">{heldQty}</span>
            </Row>
          )}
        </dl>

        {market === 'hk' && boardLot && qtyRaw > 0 && lotQty === 0 && (
          <p className="mt-3 rounded-md bg-midas-red-glow px-3 py-2 text-xs text-midas-red">
            不足一手 · 港股每手 {boardLot} 股,最少下单 1 手
          </p>
        )}
        {action.intent === 'open' && estimate && !enoughCash && (
          <p className="mt-3 rounded-md bg-midas-red-glow px-3 py-2 text-xs text-midas-red">
            {action.positionSide === 'short' ? '现金担保不足' : '余额不足'} · 差{' '}
            {formatMoney(cashNeeded - availableCash, currency)}
          </p>
        )}
        {action.intent === 'close' && !enoughPosition && (
          <p className="mt-3 rounded-md bg-midas-red-glow px-3 py-2 text-xs text-midas-red">
            {action.positionSide === 'short' ? '空头持仓不足' : '持仓不足'} · 最多 {heldQty}
          </p>
        )}
        {action.positionSide === 'short' && action.intent === 'close' && (
          <p className="mt-2 text-[11px] text-muted-foreground/70">
            平空返还担保 + 已实现盈亏(成交后按开仓均价结算)
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground hover:bg-cream"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-medium text-white transition-colors',
              canSubmit ? 'bg-midas-red hover:bg-midas-red-deep' : 'cursor-not-allowed bg-midas-red/30',
            )}
          >
            {place.isPending ? '提交中…' : `确认${action.label}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ===== 小组件 =====

function PanelShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-paper bg-background p-3">
      <header className="mb-3">
        <p className="font-serif text-sm font-bold text-foreground">下单</p>
      </header>
      {children}
    </div>
  )
}

function GateNote({
  title, hint, href, cta,
}: {
  title: string; hint: string; href: '/login' | '/settings/wallet'; cta: string
}) {
  return (
    <div className="rounded-md border border-dashed border-paper bg-cream p-4 text-center">
      <p className="mb-1 text-sm font-medium text-foreground">{title}</p>
      <p className="mb-3 text-xs leading-relaxed text-muted-foreground/80">{hint}</p>
      <Link
        href={href}
        className="inline-flex items-center rounded-md border border-midas-red px-3 py-1 text-xs text-midas-red transition-colors hover:bg-midas-red-glow"
      >
        {cta}
      </Link>
    </div>
  )
}

function OrderButton({
  variant, onClick, children,
}: {
  variant: 'solid' | 'outline'; onClick: () => void; children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md px-4 py-2.5 text-sm font-medium transition-colors',
        variant === 'solid'
          ? 'bg-midas-red text-white hover:bg-midas-red-deep'
          : 'border border-midas-red text-midas-red hover:bg-midas-red-glow',
      )}
    >
      {children}
    </button>
  )
}

function Row({
  label, children, muted,
}: {
  label: string; children: React.ReactNode; muted?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className={cn('text-xs', muted ? 'text-muted-foreground/70' : 'text-muted-foreground')}>
        {label}
      </dt>
      <dd className="text-right text-foreground">{children}</dd>
    </div>
  )
}
