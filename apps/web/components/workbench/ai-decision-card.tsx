'use client'

/**
 * AI 决策卡 · 0012 ADR M1 二波单 Agent 版(0012 § M1 二波降级 v2)。
 *
 * 内容(从上到下):
 *   - Header:「AI 决策卡 · 技术面分析」
 *   - 综合评分大字 + 标签(强多/弱多/中性/弱空/强空)+ 置信度
 *   - 关键支撑/阻力位
 *   - 技术面分析文字(narrative · 已过 Validator 改写祈使句)
 *   - 缠论买卖点列表(最近 N 个)
 *   - footer:「上次更新 X 分钟前」+ mock 标识(若 llm_mode='mock')
 *
 * 视觉系统严守(0012 红线):
 *   - composite 数字:强多/弱多 → bull · 弱空/强空 → bear · 中性 → ink-faint
 */

import { Loader2 } from 'lucide-react'
import { useMemo } from 'react'

import { TradingPlanBlock } from '@/components/ai/trading-plan-block'
import { ProLock } from '@/components/account/pro-lock'
import { useAiDecision } from '@/hooks/use-ai-decision'
import type { CompositeLabel, DecisionCard } from '@/lib/api/ai-decision'
import { useWorkbenchStore } from '@/lib/store/workbench-store'
import { cn } from '@/lib/utils'
import type { Market, Period } from '@midas/shared'


interface AiDecisionCardProps {
  /** 不传 = 读 workbench store(工作台原行为)· 详情页传入覆盖(spot-preview 复用)。 */
  symbol?: string
  market?: Market
  period?: Period
}

export function AiDecisionCard({
  symbol: propSymbol,
  market: propMarket,
  period: propPeriod,
}: AiDecisionCardProps = {}) {
  const storeSymbol = useWorkbenchStore((s) => s.symbol)
  const storeMarket = useWorkbenchStore((s) => s.market)
  const storePeriod = useWorkbenchStore((s) => s.period)
  const symbol = propSymbol ?? storeSymbol
  const market = propMarket ?? storeMarket
  const period = propPeriod ?? storePeriod

  const query = useAiDecision({ symbol, market, period })

  return (
    <div className="rounded-md border border-paper bg-background p-3">
      <header className="mb-2">
        <p className="font-serif text-sm font-bold text-foreground">
          AI 决策卡
        </p>
      </header>

      {query.status === 'pending' && <CardSkeleton />}
      {query.status === 'error' && <CardError onRetry={() => void query.refetch()} />}
      {query.status === 'success' &&
        (query.data.locked
          ? <ProLock title="AI 决策分析" />
          : <CardBody card={query.data} />)}
    </div>
  )
}


// ===== 子组件 =====


function CardBody({ card }: { card: DecisionCard }) {
  const labelColor = useMemo(() => composeLabelColor(card.composite_label), [card.composite_label])
  const adv = card.actionable

  return (
    <div className="space-y-3">
      {/* 综合评分大字 */}
      <div className="flex items-center gap-3">
        <div
          className={cn(
            'flex h-16 w-16 shrink-0 items-center justify-center rounded-full',
            'bg-midas-red-glow font-mono text-xl font-bold tabular-nums',
            labelColor,
          )}
          aria-label={`综合评分 ${card.composite_score}`}
        >
          {card.composite_score > 0 ? '+' : ''}{card.composite_score}
        </div>
        <div className="flex-1">
          <p className={cn('font-serif text-lg font-bold leading-tight', labelColor)}>
            {card.composite_label}
          </p>
          <p className="font-mono text-[11px] text-muted-foreground/80">
            置信度 {(card.composite_confidence * 100).toFixed(0)}%
          </p>
        </div>
      </div>

      {/* 关键位 */}
      {card.agent_scores[0]?.key_levels.length ? (
        <div className="border-t border-paper pt-2">
          <p className="mb-1 text-[10px] text-muted-foreground/70">关键位</p>
          <ul className="space-y-0.5 font-mono text-xs tabular-nums">
            {card.agent_scores[0].key_levels.map((lvl, i) => (
              <li key={`${lvl}-${i}`} className="flex items-center justify-between">
                <span className="text-muted-foreground/60">
                  {i === 0 ? '支撑' : i === 1 ? '阻力' : `位 ${i + 1}`}
                </span>
                <span className="text-foreground">{lvl.toFixed(2)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 技术面分析(narrative · 已过 Validator)*/}
      <div className="border-t border-paper pt-2">
        <p className="mb-1 text-[10px] text-muted-foreground/70">技术面分析</p>
        <p className="text-xs leading-relaxed text-foreground">
          {card.narrative}
        </p>
      </div>

      {/* AI 操作建议 + 一键模拟下单(0036 批次甲 · 走 ai-order → 同一虚拟撮合引擎)*/}
      {adv && (
        <div className="border-t border-paper pt-2">
          <p className="mb-1 text-[10px] text-muted-foreground/70">操作建议</p>
          <p className="text-xs leading-relaxed text-foreground">{adv.hint}</p>
          <p className="mt-0.5 text-[10px] text-muted-foreground/60">
            {adv.basis} · 仓位:{adv.size_note}
          </p>
        </div>
      )}

      {/* 缠论买卖点列表 */}
      {card.chan_signals.length > 0 && (
        <div className="border-t border-paper pt-2">
          <p className="mb-1 text-[10px] text-muted-foreground/70">缠论买卖点</p>
          <ul className="space-y-1">
            {card.chan_signals.slice(-4).reverse().map((s, i) => {
              const isBuy = s.kind.startsWith('B')
              return (
                <li
                  key={`${s.kind}-${s.ts}-${i}`}
                  className="flex items-center gap-2 text-[11px]"
                >
                  <span
                    className={cn(
                      'inline-flex h-5 w-7 shrink-0 items-center justify-center rounded',
                      'font-mono text-[10px] font-bold',
                      isBuy ? 'bg-up/10 text-up' : 'bg-down/10 text-down',
                    )}
                  >
                    {s.kind}
                  </span>
                  <span className="font-mono tabular-nums text-foreground">
                    {s.price.toFixed(2)}
                  </span>
                  <span className="truncate text-muted-foreground/70" title={s.description}>
                    {s.description}
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {/* 交易计划参考(三价位 + plan_note + 按计划价挂限价单)· 缠论买卖点区之后 */}
      <TradingPlanBlock plan={card.trading_plan} symbol={card.symbol} market={card.market} actionable={card.actionable} />

      {/* ★事件日程层 P0:近期重大事件风险提示(后端纯模板·只提示波动不给方向·自带免责) */}
      {card.event_risk && (
        <p className="rounded-md bg-muted px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
          📅 {card.event_risk}
        </p>
      )}

      {/* footer · cached + mock 标记 */}
      <div className="flex items-center justify-between border-t border-paper pt-2 text-[10px] text-muted-foreground/60">
        <span>{card.cached ? '· 缓存命中' : '· 实时计算'}</span>
        {card.llm_mode === 'mock' && (
          <span className="rounded bg-gold/10 px-1.5 py-0.5 font-mono text-gold">
            mock(待填 KEY)
          </span>
        )}
      </div>

    </div>
  )
}


function CardSkeleton() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-6">
      <Loader2 className="h-6 w-6 animate-spin text-midas-red" />
      <p className="text-xs text-muted-foreground/70">AI 思考中...</p>
    </div>
  )
}


function CardError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-md border border-dashed border-paper bg-cream p-4 text-center">
      <p className="mb-2 text-xs text-muted-foreground/80">
        暂时无法生成决策卡
      </p>
      <button
        type="button"
        onClick={onRetry}
        className={cn(
          'inline-flex items-center rounded-md border border-midas-red px-3 py-1',
          'text-xs text-midas-red transition-colors hover:bg-midas-red-glow',
        )}
      >
        重试
      </button>
    </div>
  )
}


// ===== Helpers =====


function composeLabelColor(label: CompositeLabel): string {
  switch (label) {
    case '强多':
    case '弱多':
      return 'text-up'
    case '强空':
    case '弱空':
      return 'text-down'
    default:
      return 'text-muted-foreground'
  }
}
