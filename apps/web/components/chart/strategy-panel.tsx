'use client'

/**
 * AI 策略面板 · 形态A 单元3(ADR 0037 §5.2)。
 *
 * 一处统一组件,三套主图(工作台 / 现货详情 / 合约详情)共用:
 * - 策略信号总开关(默认关 · 不干扰现有缠论/指标)
 * - 3 个策略选择(均线金叉 / RSI 反弹 / 布林均值回归)· 选中高亮
 * - AI 推荐徽章(调 /strategy-recommend · 纯规则 · 显示「推荐 XX + 理由」)
 * - 当前是否触发提示(调 /strategy-signals · current_triggered / 最近信号)
 * - disclaimer:仅供参考 · 信号仅展示,下单走第一层一键模拟
 *
 * ★ 全 props 驱动 · 信号点的实际标注在 <StrategyOverlay>(同 strategy/enabled 状态由父组件管理)。
 * ★ 红线:纯展示 · 不下单 / 不自动交易。
 */

import { useStrategyRecommend, useStrategySignals } from '@/hooks/use-strategy'
import type { Instrument, StrategyKind } from '@/lib/api/strategy'
import { cn } from '@/lib/utils'
import type { Market, Period } from '@midas/shared'

const STRATEGY_LABELS: Record<StrategyKind, string> = {
  ma_cross: '均线金叉',
  rsi_reversal: 'RSI 反弹',
  boll_reversion: '布林均值回归',
}

const STRATEGY_ORDER: StrategyKind[] = ['ma_cross', 'rsi_reversal', 'boll_reversion']

interface Props {
  symbol: string
  market: Market
  period: Period
  instrument?: Instrument
  strategy: StrategyKind
  onStrategyChange: (s: StrategyKind) => void
  enabled: boolean
  onToggle: () => void
}

export function StrategyPanel({
  symbol,
  market,
  period,
  instrument,
  strategy,
  onStrategyChange,
  enabled,
  onToggle,
}: Props) {
  const recommend = useStrategyRecommend({ symbol, market, period, instrument, enabled })
  const signals = useStrategySignals({ symbol, market, period, strategy, instrument, enabled })

  const rec = recommend.data
  const sig = signals.data

  return (
    <div className="rounded-lg border border-paper bg-surface-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="font-serif text-sm font-bold">AI 策略信号</span>
          <span className="ml-2 text-[11px] text-muted-foreground/50">
            买卖信号标在 K 线 · 朱红买点 / 墨绿卖点
          </span>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            'rounded-md border px-3 py-1 text-xs transition-colors',
            enabled
              ? 'border-gold bg-gold/10 text-gold'
              : 'border-paper text-muted-foreground hover:border-gold/60',
          )}
        >
          策略信号 {enabled ? '开' : '关'}
        </button>
      </div>

      {enabled && (
        <div className="mt-3 space-y-2">
          {/* 策略选择 */}
          <div className="flex flex-wrap items-center gap-2">
            {STRATEGY_ORDER.map((k) => {
              const isRecommended = rec?.recommended_strategy === k
              return (
                <button
                  key={k}
                  type="button"
                  onClick={() => onStrategyChange(k)}
                  className={cn(
                    'relative rounded-md border px-3 py-1 text-xs transition-colors',
                    strategy === k
                      ? 'border-midas-red bg-midas-red-glow text-midas-red'
                      : 'border-paper text-muted-foreground hover:border-midas-red/40 hover:text-foreground',
                  )}
                >
                  {STRATEGY_LABELS[k]}
                  {isRecommended && (
                    <span className="ml-1 text-[10px] text-gold">★荐</span>
                  )}
                </button>
              )
            })}
          </div>

          {/* AI 推荐理由 */}
          {rec && (
            <p className="text-[11px] text-gold/90">
              AI 推荐:{STRATEGY_LABELS[rec.recommended_strategy]} · {rec.reason}
            </p>
          )}

          {/* 当前触发状态 */}
          <TriggerStatus
            triggered={sig?.current_triggered ?? false}
            lastKind={sig?.last_signal?.kind ?? null}
            lastReason={sig?.last_signal?.reason ?? null}
            hasSignals={(sig?.signals.length ?? 0) > 0}
          />

          <p className="text-[10px] leading-relaxed text-muted-foreground/60">
            仅供参考,不构成投资建议 · 信号仅展示,下单请走「一键模拟下单」(虚拟)
          </p>
        </div>
      )}
    </div>
  )
}

function TriggerStatus({
  triggered,
  lastKind,
  lastReason,
  hasSignals,
}: {
  triggered: boolean
  lastKind: 'buy' | 'sell' | null
  lastReason: string | null
  hasSignals: boolean
}) {
  if (!hasSignals) {
    return (
      <div className="rounded-md border border-paper bg-background/50 px-2.5 py-1.5 text-[11px] text-muted-foreground/70">
        近期无信号
      </div>
    )
  }
  const isBuy = lastKind === 'buy'
  const tone = isBuy ? 'text-up' : 'text-down'
  const label = isBuy ? '买点' : '卖点'
  return (
    <div
      className={cn(
        'rounded-md border px-2.5 py-1.5 text-[11px]',
        triggered
          ? isBuy
            ? 'border-up/40 bg-up/10'
            : 'border-down/40 bg-down/10'
          : 'border-paper bg-background/50',
      )}
    >
      {triggered ? (
        <span className={cn('font-medium', tone)}>🔔 当前触发:{label} · {lastReason}</span>
      ) : (
        <span className="text-muted-foreground/70">
          最近信号:<span className={tone}>{label}</span> · {lastReason}
        </span>
      )}
    </div>
  )
}
