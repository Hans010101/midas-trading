/**
 * 沙盘助手可视化纯逻辑(第一期)· vitest 可测。
 *
 * 🔴 红线:纯展示侧换算/判定 —— 不碰诊断链(services/structure 三件零改),
 *   sparkline/力量条数据全部旁路取自 crypto 现有端点与 snapshot 已有字段。
 */

import type { FactorFinding } from '@/lib/api/structure'

/** 背离/极端因子高亮判定:LLM 在 state/detail 里点名「背离」「极端」即高亮(帝王金)。 */
export function isDivergentFinding(f: Pick<FactorFinding, 'state' | 'detail'>): boolean {
  return /背离|极端/.test(`${f.state} ${f.detail}`)
}

/**
 * 多空比值 → 双边占比(力量对比条用)。
 * ratio = long/short(如 1.65)→ long = r/(1+r), short = 1/(1+r)。
 * 非法(<=0 / 非有限)返回 null(条不渲染 · 优雅降级)。
 */
export function ratioToLongShortPct(ratio: number): { longPct: number; shortPct: number } | null {
  if (!Number.isFinite(ratio) || ratio <= 0) return null
  const longPct = (ratio / (1 + ratio)) * 100
  return { longPct: +longPct.toFixed(1), shortPct: +(100 - longPct).toFixed(1) }
}
