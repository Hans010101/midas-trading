/**
 * 策略信号「按市场可用集 + 显示顺序」纯逻辑 · 第二刀抽出(可单测 · 无 React/DOM 依赖)。
 *
 * 🔴 极端信号(extreme)= 合约 funding/OI/多空比情绪 · ★仅 crypto perp 可用;
 *    现货(cn/us/hk)无这些数据 → 不出 extreme。其余 5 个信号四市场通用。
 */

import type { Instrument, StrategyKind } from '@/lib/api/strategy'
import { DEFAULT_STRATEGY_ORDER } from '@/lib/store/ui-store'
import type { Market } from '@midas/shared'

/** 当前市场可用的信号集 · extreme 仅 crypto perp · 其余 5 个通用。 */
export function availableStrategies(market: Market, instrument?: Instrument): StrategyKind[] {
  const isCryptoPerp = market === 'crypto' && instrument === 'perp'
  return DEFAULT_STRATEGY_ORDER.filter((k) => k !== 'extreme' || isCryptoPerp)
}

/**
 * 显示顺序 = 用户存的顺序 ∩ 当前市场可用集,再把缺失的可用项按默认顺序补全。
 * ★兼容"某市场无 extreme":stored 里的 extreme 在现货被过滤掉(avail 不含)。
 */
export function effectiveOrder(stored: StrategyKind[], available: StrategyKind[]): StrategyKind[] {
  const avail = new Set(available)
  const fromStored = stored.filter((k) => avail.has(k))
  const missing = available.filter((k) => !fromStored.includes(k))
  return [...fromStored, ...missing]
}
