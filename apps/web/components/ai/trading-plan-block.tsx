'use client'

/**
 * 交易计划参考 · 共享子组件(crypto-ai-card + ai-decision-card 两端共用 · 覆盖红线)。
 *
 * 三价位(入场区间/止损失效价/双目标/盈亏比)由后端【规则】算好(trading_plan),本组件只渲染;
 * plan_note 是后端 AI 写的计划逻辑解释。「按计划入场价挂限价单」走 ai-plan-order → 条件单 LIMIT
 * (二次确认必经 · 复用现成虚拟撮合,绝不接真实交易)。
 *
 * 配色(★产品负责人定稿 · 本区块刻意用「多头绿 / 空头红」西式方向色,与全局涨红跌绿解耦):
 *   long → 绿(墨绿)· short → 红(中国红)· neutral → 中性灰(不出三价位 · 优雅降级)。
 */

import { useState } from 'react'
import { toast } from 'sonner'

import { AiOrderConfirmDialog } from '@/components/workbench/ai-order-confirm-dialog'
import { useRuntimeLocale } from '@/components/i18n/locale-runtime-provider'
import { usePlaceAiPlanOrder } from '@/hooks/use-conditional-orders'
import type { ActionableAdvice, TradingPlan } from '@/lib/api/ai-decision'
import { ConditionalApiError } from '@/lib/api/conditional-order'
import { cn } from '@/lib/utils'
import type { Market } from '@midas/shared'

const GREEN = '#0F6E5F' // 多头
const RED = '#C8102E' // 空头

function fmt(v: number | null): string {
  if (v === null) return '—'
  const a = Math.abs(v)
  const d = a >= 1000 ? 2 : a >= 1 ? 3 : a >= 0.01 ? 5 : 7
  return v.toFixed(d)
}

/** 计划方向 → 挂单方向(crypto open_*；spot 仅 buy 可挂 · 空头现货不挂)。null=不出挂单按钮。 */
export function orderDirection(
  market: Market,
  dir: TradingPlan['direction'],
): 'buy' | 'open_long' | 'open_short' | null {
  if (dir === 'neutral') return null
  if (market === 'crypto') return dir === 'long' ? 'open_long' : 'open_short'
  return dir === 'long' ? 'buy' : null // 现货不限价做空
}

export function TradingPlanBlock({
  plan,
  symbol,
  market,
  actionable,
}: {
  plan: TradingPlan | null
  symbol: string
  market: Market
  /** 用于「按市价下单」二次确认展示(基础依据/仓位口径)· 可空走默认文案 */
  actionable?: ActionableAdvice | null
}) {
  const { locale } = useRuntimeLocale()
  const en = locale === 'en'
  const aiPlanOrder = usePlaceAiPlanOrder()
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [marketOpen, setMarketOpen] = useState(false)

  if (!plan) return null

  const isLong = plan.direction === 'long'
  const isShort = plan.direction === 'short'
  const tone = isLong ? GREEN : isShort ? RED : '#94949C'

  // 中性:不给三价位 · 仅一句话优雅说明(不崩)
  if (plan.direction === 'neutral' || plan.entry_low === null) {
    return (
      <section className="mt-3 rounded-lg border border-paper bg-cream/60 p-3">
        <h4 className="font-serif text-sm font-bold text-muted-foreground">
          {en ? 'Trade plan · Neutral' : '交易计划参考 · 中性'}
        </h4>
        <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
          {plan.plan_note ||
            (en
              ? 'Signals are neutral and the structure offers no clear trend entry.'
              : '当前多空信号中性,结构未给出明确顺势入场位,倾向观望等待方向选择。')}
        </p>
      </section>
    )
  }

  const dirLabel = en
    ? isLong ? 'Long' : 'Short'
    : isLong ? '开多' : '开空'
  // 挂单入场价:多头取区间上沿(价回落先触)· 空头取区间下沿(价反弹先触)
  const entryPrice = isLong ? plan.entry_high : plan.entry_low
  const od = orderDirection(market, plan.direction)

  async function handlePlaceLimit() {
    if (entryPrice === null || od === null) return
    try {
      await aiPlanOrder.mutateAsync({
        symbol,
        market,
        direction: od,
        entry_price: String(entryPrice),
      })
      toast.success(
        en
          ? `Limit order placed at plan entry · ${symbol} @ ${fmt(entryPrice)}`
          : `已按计划价挂限价单 · ${symbol} @ ${fmt(entryPrice)}`,
        {
        className: 'midas-toast-success',
        duration: 4000,
        },
      )
      setConfirmOpen(false)
    } catch (e) {
      const msg = e instanceof ConditionalApiError
        ? e.detail
        : en ? 'Unable to place order' : '挂单失败'
      toast.error(msg)
    }
  }

  return (
    <section
      className="mt-3 border-l-2 bg-background/60 py-3 pl-3 pr-2"
      style={{ borderColor: tone }}
    >
      <h4 className="font-serif text-sm font-bold" style={{ color: tone }}>
        {en ? 'Trade plan' : '交易计划参考'} · {dirLabel}
      </h4>

      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
        <Field label={en ? 'Entry zone' : '入场区间'}>
          <span className="font-mono" style={{ color: tone }}>
            {fmt(plan.entry_low)} – {fmt(plan.entry_high)}
          </span>
        </Field>
        <Field label={en ? 'Invalidation' : '止损(失效价)'}>
          <span className="font-mono" style={{ color: RED }}>
            {fmt(plan.stop)}
          </span>
        </Field>
        <Field label={en ? 'Target 1' : '目标 1'}>
          <span className="font-mono text-foreground">{fmt(plan.target1)}</span>
        </Field>
        <Field label={en ? 'Target 2' : '目标 2'}>
          <span className="font-mono text-foreground">{fmt(plan.target2)}</span>
        </Field>
        <Field label={en ? 'Risk / reward' : '风险回报比'}>
          <span className="font-mono text-foreground">
            {plan.risk_reward === null ? '—' : `1 : ${plan.risk_reward}`}
          </span>
        </Field>
      </dl>

      {plan.plan_note && (
        <p className="mt-2 border-t border-paper/60 pt-2 text-xs leading-relaxed text-muted-foreground">
          {plan.plan_note}
        </p>
      )}

      {od !== null && entryPrice !== null && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="rounded-md py-2 text-sm font-medium text-white transition-opacity hover:opacity-90"
            style={{ background: tone }}
          >
            {en ? 'Place limit' : '按计划挂限价单'}
          </button>
          <button
            type="button"
            onClick={() => setMarketOpen(true)}
            className="rounded-md border py-2 text-sm font-medium transition-opacity hover:opacity-80"
            style={{ borderColor: tone, color: tone }}
          >
            {en ? 'Market order' : '按市价下单'}
          </button>
        </div>
      )}

      {/* 限价单二次确认 → ai-plan-order → 条件单 LIMIT */}
      {od !== null && entryPrice !== null && (
        <PlanLimitConfirm
          open={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          symbol={symbol}
          dirLabel={dirLabel}
          entryPrice={entryPrice}
          tone={tone}
          pending={aiPlanOrder.isPending}
          onConfirm={handlePlaceLimit}
          locale={locale}
        />
      )}

      {/* 市价单二次确认 → ai-order → 同一虚拟撮合引擎(复用现成市价链路)*/}
      {od !== null && (
        <AiOrderConfirmDialog
          open={marketOpen}
          onClose={() => setMarketOpen(false)}
          symbol={symbol}
          market={market}
          direction={od}
          basis={actionable?.basis ?? (en ? 'AI trade-plan direction' : 'AI 交易计划方向')}
          sizeNote={actionable?.size_note ?? (en ? 'Use your order preset' : '按你的下单预设')}
        />
      )}
    </section>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] text-muted-foreground/70">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

function PlanLimitConfirm({
  open,
  onClose,
  symbol,
  dirLabel,
  entryPrice,
  tone,
  pending,
  onConfirm,
  locale,
}: {
  open: boolean
  onClose: () => void
  symbol: string
  dirLabel: string
  entryPrice: number
  tone: string
  pending: boolean
  onConfirm: () => void
  locale: 'zh' | 'en'
}) {
  if (!open) return null
  const en = locale === 'en'
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        className="w-full max-w-sm rounded-lg border bg-cream p-6 shadow-xl"
        style={{ borderColor: tone }}
      >
        <h3 className="mb-4 text-center font-serif text-lg font-bold text-foreground">
          {en ? 'Confirm plan limit order' : '确认按计划价挂限价单'}
        </h3>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">
              {en ? 'Symbol / side' : '标的 / 方向'}
            </dt>
            <dd>
              <span className="font-mono">{symbol}</span>
              <span
                className="ml-2 rounded px-1.5 py-0.5 text-xs text-white"
                style={{ background: tone }}
              >
                {dirLabel}
              </span>
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">
              {en ? 'Limit entry' : '限价(入场价)'}
            </dt>
            <dd className="font-mono" style={{ color: tone }}>
              {fmt(entryPrice)}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-[11px] leading-relaxed text-muted-foreground/70">
          {en
            ? 'The virtual engine monitors the level and fills when price reaches it, using your order preset.'
            : '挂单后由系统监控,价格触及即按虚拟引擎成交;仓位按你的下单预设。'}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-paper bg-background px-4 py-2 text-sm text-foreground hover:bg-cream"
          >
            {en ? 'Cancel' : '取消'}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className={cn(
              'rounded-md px-4 py-2 text-sm font-medium text-white transition-opacity',
              pending ? 'cursor-not-allowed opacity-40' : 'hover:opacity-90',
            )}
            style={{ background: tone }}
          >
            {pending
              ? en ? 'Placing…' : '挂单中…'
              : en ? 'Confirm order' : '确认挂单'}
          </button>
        </div>
      </div>
    </div>
  )
}
