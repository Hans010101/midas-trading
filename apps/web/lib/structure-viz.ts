/**
 * 沙盘助手可视化纯逻辑(第一期)· vitest 可测。
 *
 * 🔴 红线:纯展示侧换算/判定 —— 不碰诊断链(services/structure 三件零改),
 *   sparkline/力量条数据全部旁路取自 crypto 现有端点与 snapshot 已有字段。
 */

import type { FactorFinding, StructureSnapshot } from '@/lib/api/structure'

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

// ── 二期刀2 · 因子数值格式化 + sparkline 语义配置(全部取 snapshot 结构化字段,
//    ⛔ 绝不解析 LLM 文字)────────────────────────────────────────────────────

export type Tone = 'bull' | 'bear' | 'neutral'

export interface FactorHeadline {
  text: string
  tone: Tone
}

const RATIO_FACTORS = new Set([
  'account_long_short', 'position_long_short', 'taker_flow', 'global_long_short',
])

function ratioTone(v: number): Tone {
  if (v > 1) return 'bull'
  if (v < 1) return 'bear'
  return 'neutral'
}

function signTone(v: number): Tone {
  if (v > 0) return 'bull'
  if (v < 0) return 'bear'
  return 'neutral'
}

/**
 * 因子关键数值(卡头 mono 数字 / 图谱节点第二行 / 大数字面板共用)。
 * 缺因子/缺字段 → null(调用方不渲染 · 优雅降级)。
 */
export function factorHeadline(
  factor: string, snapshot: StructureSnapshot,
): FactorHeadline | null {
  const v = (snapshot as unknown as Record<string, { value?: Record<string, number> } | null>)[
    factor
  ]?.value
  if (!v) return null

  if (RATIO_FACTORS.has(factor)) {
    const latest = v.latest
    if (latest == null || !Number.isFinite(latest)) return null
    return { text: latest.toFixed(2), tone: ratioTone(latest) }
  }
  if (factor === 'funding_rate') {
    const latest = v.latest
    if (latest == null || !Number.isFinite(latest)) return null
    return { text: `${(latest * 100).toFixed(4)}%`, tone: signTone(latest) }
  }
  if (factor === 'open_interest') {
    const chg = v.change_pct_24h
    if (chg == null || !Number.isFinite(chg)) return null
    return { text: `${chg > 0 ? '+' : ''}${chg.toFixed(2)}%`, tone: signTone(chg) }
  }
  if (factor === 'basis') {
    const pct = v.basis_pct
    if (pct == null || !Number.isFinite(pct)) return null
    return { text: `${pct.toFixed(3)}%`, tone: signTone(pct) }
  }
  if (factor === 'sentiment') {
    const fgi = v.fear_greed
    if (fgi == null || !Number.isFinite(fgi)) return null
    return { text: fgi.toFixed(0), tone: fgi >= 70 ? 'bull' : fgi <= 30 ? 'bear' : 'neutral' }
  }
  // 三期批1 +2(funding_predicted 同 funding 格式 · global 已并入 RATIO_FACTORS)
  if (factor === 'funding_predicted') {
    const latest = v.latest
    if (latest == null || !Number.isFinite(latest)) return null
    return { text: `${(latest * 100).toFixed(4)}%`, tone: signTone(latest) }
  }
  if (factor === 'funding_zscore') {
    const z = v.z
    if (z == null || !Number.isFinite(z)) return null
    // |z|>2 才按方向着色(极端才有语义)· 区间内中性
    return { text: z.toFixed(2), tone: Math.abs(z) > 2 ? signTone(z) : 'neutral' }
  }
  if (factor === 'oi_volume_ratio') {
    const ratio = v.ratio
    if (ratio == null || !Number.isFinite(ratio)) return null
    return { text: ratio.toFixed(2), tone: 'neutral' } // 仓位沉淀度无多空方向语义
  }
  return null
}

// 设计 token hex(SVG/Recharts 内联用)· 与全站涨跌语义一致 · ⛔ 缠论淡灰蓝专用不可挪用
export const TONE_HEX: Record<Tone, string> = {
  bull: '#DC143C',
  bear: '#0F6E5F',
  neutral: '#9A938A',
}

/**
 * sparkline 语义配置:基准线(费率/基差 0 轴 · 比值 1.0 轴)+ 线色(末值 vs 语义)。
 * 缺因子 → 默认帝王金、无基准线(与一期行为一致)。
 */
export function sparklineSpec(
  factor: string, snapshot: StructureSnapshot,
): { baseline?: number; stroke: string } {
  const head = factorHeadline(factor, snapshot)
  const stroke = head ? TONE_HEX[head.tone] : '#B8860B'
  if (RATIO_FACTORS.has(factor)) return { baseline: 1, stroke }
  if (factor === 'funding_rate' || factor === 'basis') return { baseline: 0, stroke }
  return { stroke }
}
