'use client'

/**
 * AI 策略面板 · 形态A 单元3(ADR 0037 §5.2)。
 *
 * 一处统一组件,三套主图(工作台 / 现货详情 / 合约详情)共用:
 * - 策略信号总开关(默认关 · 不干扰现有缠论/指标)
 * - 3 个策略选择(均线金叉 / RSI 反弹 / 布林均值回归)· 选中高亮
 * - AI 推荐徽章(调 /strategy-recommend · 纯规则 · 显示「推荐 XX + 理由」)
 * - 当前是否触发提示(调 /strategy-signals · current_triggered / 最近信号)
 *
 * ★ 全 props 驱动 · 信号点的实际标注在 <StrategyOverlay>(同 strategy/enabled 状态由父组件管理)。
 * ★ 红线:纯展示 · 不下单 / 不自动交易。
 */

import { ProLock } from '@/components/account/pro-lock'
import { useStrategyRecommend, useStrategySignals } from '@/hooks/use-strategy'
import type { Instrument, StrategyKind, StrategySignal } from '@/lib/api/strategy'
import { DEFAULT_STRATEGY_ORDER } from '@/lib/store/ui-store'
import { useUiStore } from '@/lib/store/ui-store-provider'
import { cn } from '@/lib/utils'
import type { Market, Period } from '@midas/shared'

const STRATEGY_LABELS: Record<StrategyKind, string> = {
  ma_cross: '均线金叉',
  rsi_reversal: 'RSI 反弹',
  boll_reversion: '布林均值回归',
  macd_cross: 'MACD 金叉死叉',
  kdj_cross: 'KDJ 金叉死叉',
}

/** 顺序以 ui-store.strategyOrder 为准(用户左右调 · 全页持久化);此处对其做"已知键过滤 + 缺失键补全"。 */
function effectiveOrder(stored: StrategyKind[]): StrategyKind[] {
  const known = new Set(DEFAULT_STRATEGY_ORDER)
  const fromStored = stored.filter((k) => known.has(k))
  const missing = DEFAULT_STRATEGY_ORDER.filter((k) => !fromStored.includes(k))
  return [...fromStored, ...missing]
}

// 价格符号(按市场)· cn ¥ / hk HK$ / us·crypto $
function priceSym(market: Market): string {
  return market === 'cn' ? '¥' : market === 'hk' ? 'HK$' : '$'
}
// 信号价格(智能小数 · ≥1000 整数千分位 · ≥1 两位 · <1 四位)+ 市场符号
function fmtSignalPrice(price: number, market: Market): string {
  const d = price >= 1000 ? 0 : price >= 1 ? 2 : 4
  return `${priceSym(market)}${price.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d })}`
}
// 信号时间(月/日 时:分)
function fmtSignalTs(ts: string): string {
  try {
    const d = new Date(ts)
    const p = (n: number) => String(n).padStart(2, '0')
    return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`
  } catch {
    return ts.slice(5, 16)
  }
}
// ⑤ 关键价位(批2)· 智能小数去尾零 · 不带货币符号(键已表意 · 如「MA5 10.2 · MA20 10.05」)
function fmtLevelVal(v: number): string {
  const d = v >= 1000 ? 0 : v >= 1 ? 2 : 4
  return v.toLocaleString('en-US', { maximumFractionDigits: d })
}
function fmtLevels(levels: Record<string, number>): string {
  return Object.entries(levels)
    .map(([k, v]) => `${k} ${fmtLevelVal(v)}`)
    .join(' · ')
}

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
  const storedOrder = useUiStore((s) => s.strategyOrder)
  const setOrder = useUiStore((s) => s.setStrategyOrder)

  const rec = recommend.data
  const sig = signals.data
  const order = effectiveOrder(storedOrder)

  // 左右移:与相邻项交换 · 写回 ui-store(全页持久化)。端点处 dir 越界则不动。
  function moveStrategy(k: StrategyKind, dir: -1 | 1): void {
    const i = order.indexOf(k)
    const j = i + dir
    if (j < 0 || j >= order.length) return
    const next = [...order]
    ;[next[i], next[j]] = [next[j], next[i]]
    setOrder(next)
  }

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
            {order.map((k, idx) => {
              const isRecommended = rec?.recommended_strategy === k
              return (
                <div key={k} className="flex items-center gap-0.5">
                  <button
                    type="button"
                    aria-label={`${STRATEGY_LABELS[k]} 左移`}
                    disabled={idx === 0}
                    onClick={() => moveStrategy(k, -1)}
                    className="px-1 text-[11px] text-muted-foreground/50 transition-colors hover:text-midas-red disabled:opacity-25"
                  >
                    ◀
                  </button>
                  <button
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
                  <button
                    type="button"
                    aria-label={`${STRATEGY_LABELS[k]} 右移`}
                    disabled={idx === order.length - 1}
                    onClick={() => moveStrategy(k, 1)}
                    className="px-1 text-[11px] text-muted-foreground/50 transition-colors hover:text-midas-red disabled:opacity-25"
                  >
                    ▶
                  </button>
                </div>
              )
            })}
          </div>

          {/* AI 推荐理由 */}
          {rec && (
            <p className="text-[11px] text-gold/90">
              AI 推荐:{STRATEGY_LABELS[rec.recommended_strategy]} · {rec.reason}
            </p>
          )}

          {/* 当前触发 / 历史信号 · Pro 门控(非 Pro → 后端 locked 空壳 → 遮罩两道门)*/}
          {signals.data?.locked ? (
            <ProLock title="实战策略信号" />
          ) : (
          <>
          {/* 当前触发状态(① 含触发价) */}
          <TriggerStatus
            triggered={sig?.current_triggered ?? false}
            last={sig?.last_signal ?? null}
            market={market}
            hasSignals={(sig?.signals.length ?? 0) > 0}
          />

          {/* ② 历史信号列表(可折叠 · 复盘该策略历史买卖信号点 · 纯数据展示 · 不加建议/风险废话) */}
          {sig && sig.signals.length > 0 && (
            <details className="group rounded-md border border-paper bg-background/50">
              <summary className="cursor-pointer px-2.5 py-1.5 text-[11px] text-muted-foreground/80 hover:text-foreground">
                历史信号 {sig.signals.length} 个 · 点击展开复盘
              </summary>
              <div className="max-h-44 overflow-y-auto border-t border-paper/60">
                {[...sig.signals].reverse().map((s, i) => {
                  const isBuy = s.kind === 'buy'
                  const hasDetail = Object.keys(s.levels).length > 0 || s.strength_note
                  return (
                    <div
                      key={`${s.ts}-${i}`}
                      className="px-2.5 py-1 text-[11px] odd:bg-background/30"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-20 shrink-0 font-mono text-muted-foreground/60">
                          {fmtSignalTs(s.ts)}
                        </span>
                        <span
                          className={cn('shrink-0 font-mono font-medium', isBuy ? 'text-up' : 'text-down')}
                        >
                          {isBuy ? '买' : '卖'} {fmtSignalPrice(s.price, market)}
                        </span>
                        <span className="flex-1 truncate text-right text-muted-foreground/60">
                          {s.reason}
                        </span>
                      </div>
                      {/* ⑤ 关键价位 + ⑥ 成色(批2)· 成色 ma_cross 为 null → 不显示(诚实不空塞)*/}
                      {hasDetail && (
                        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 pl-[5.5rem] text-[10px] text-muted-foreground/50">
                          {Object.keys(s.levels).length > 0 && (
                            <span className="font-mono">{fmtLevels(s.levels)}</span>
                          )}
                          {s.strength_note && <span className="text-gold/70">成色 · {s.strength_note}</span>}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </details>
          )}
          </>
          )}
        </div>
      )}
    </div>
  )
}

function TriggerStatus({
  triggered,
  last,
  market,
  hasSignals,
}: {
  triggered: boolean
  last: StrategySignal | null
  market: Market
  hasSignals: boolean
}) {
  if (!hasSignals || !last) {
    return (
      <div className="rounded-md border border-paper bg-background/50 px-2.5 py-1.5 text-[11px] text-muted-foreground/70">
        近期无信号
      </div>
    )
  }
  const isBuy = last.kind === 'buy'
  const tone = isBuy ? 'text-up' : 'text-down'
  const label = isBuy ? '买点' : '卖点'
  // ① 触发价(纯数据 · 带市场符号)
  const priceStr = ` ${fmtSignalPrice(last.price, market)}`
  // ⑤ 关键价位(信号点已算值)· ⑥ 成色(只 rsi/boll · ma_cross 为 null → 不显示成色 · 不空塞)
  const levelsStr = Object.keys(last.levels).length > 0 ? fmtLevels(last.levels) : ''
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
        <span className={cn('font-medium', tone)}>🔔 当前触发:{label}{priceStr} · {last.reason}</span>
      ) : (
        <span className="text-muted-foreground/70">
          最近信号:<span className={tone}>{label}{priceStr}</span> · {last.reason}
        </span>
      )}
      {/* ⑤ 关键价位 + ⑥ 成色(批2 · 第二行)· 成色 ma_cross 为 null → 整段不显示成色(诚实不空塞)*/}
      {(levelsStr || last.strength_note) && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-muted-foreground/60">
          {levelsStr && <span className="font-mono">{levelsStr}</span>}
          {last.strength_note && <span className="text-gold/80">成色 · {last.strength_note}</span>}
        </div>
      )}
    </div>
  )
}
