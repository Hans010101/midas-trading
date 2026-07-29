/**
 * 沙盘助手可视化纯逻辑(第一期)· vitest 可测。
 *
 * 🔴 红线:纯展示侧换算/判定 —— 不碰诊断链(services/structure 三件零改),
 *   sparkline/力量条数据全部旁路取自 crypto 现有端点与 snapshot 已有字段。
 */

import type { FactorFinding, StructureSnapshot } from '@/lib/api/structure'
import { FACTOR_ORDER } from '@/lib/structure-graph'

/**
 * 数据口径文案(批1 修复刀:与 prompts.py 红线三对齐 —— 全市场人数比已采(刀C),
 * 只有清算/盘口仍未采;抽常量供 vitest 断言防再漂移)。
 */
export const CALIBER_NOTE =
  '各因子结论均限定其数据窗口(24h / 7d / latest);本系统因子历史最长 60 天,' +
  '「极值/分位」类表述均为近 N 天内口径,非长期历史基线。清算数据暂未采集。'
export const CALIBER_NOTE_EN =
  'Every factor is limited to its stated window (24h / 7d / latest). Factor history spans at most 60 days, so extremes and percentiles refer only to the recent N-day window, not a long-term baseline. Liquidation data is not yet collected.'

/** 背离/极端因子高亮判定:LLM 在 state/detail 里点名「背离」「极端」即高亮(帝王金)。 */
export function isDivergentFinding(f: Pick<FactorFinding, 'state' | 'detail'>): boolean {
  return /背离|极端|divergen|extreme/i.test(`${f.state} ${f.detail}`)
}

export interface FactorCardSpec {
  key: string
  /** null = LLM 未对该因子输出判定 → 降级卡(数值+图,判定如实留白,绝不伪造) */
  finding: FactorFinding | null
  window: string
}

/**
 * 因子卡区改 snapshot 驱动(批1 修复刀):按 FACTOR_ORDER 列 snapshot 非空因子,
 * 有 LLM finding 的附判定、无 finding 的降级(LLM 没点名 ≠ 数据不存在)。
 */
export function buildFactorCards(
  snapshot: StructureSnapshot, findings: FactorFinding[],
): FactorCardSpec[] {
  const byFactor = new Map(findings.map((f) => [f.factor, f]))
  const snap = snapshot as unknown as Record<string, { window?: string } | null>
  return FACTOR_ORDER.filter((k) => snap[k] != null).map((k) => {
    const finding = byFactor.get(k) ?? null
    return { key: k, finding, window: finding?.window ?? snap[k]?.window ?? '' }
  })
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

function signTone(v: number): Tone {
  if (v > 0) return 'bull'
  if (v < 0) return 'bear'
  return 'neutral'
}

/** LLM finding.state 档位 → tone(偏多类朱红 / 偏空类墨绿 / 其余中性灰)。 */
export function stateTone(state: string): Tone {
  if (/多|bull|long/i.test(state)) return 'bull'
  if (/空|bear|short/i.test(state)) return 'bear'
  return 'neutral'
}

/**
 * 因子关键数值(卡头 mono 数字 / 图谱节点第二行 / 大数字面板共用)。
 * 缺因子/缺字段 → null(调用方不渲染 · 优雅降级)。
 *
 * tone 档位收敛(移动刀D-B):跟 LLM finding.state 档位 —— 有判定才有方向色,
 * 无判定/中性档一律灰。旧版「数值 vs 固定基准」(比值>1 即红、费率>0 即红)
 * 把 1.02 这类弱偏离也染色,与状态胶囊"中性"互相打架 = 视觉噪音。
 * 唯一特例 funding_zscore:|z|>2 数据极端才按符号着色(极端才有语义 · 不依赖 LLM)。
 */
export function factorHeadline(
  factor: string,
  snapshot: StructureSnapshot,
  finding?: Pick<FactorFinding, 'state'> | null,
  locale: 'en' | 'zh' = 'zh',
): FactorHeadline | null {
  const v = (snapshot as unknown as Record<string, { value?: Record<string, number> } | null>)[
    factor
  ]?.value
  if (!v) return null
  const tone: Tone = finding ? stateTone(finding.state) : 'neutral'

  if (RATIO_FACTORS.has(factor)) {
    const latest = v.latest
    if (latest == null || !Number.isFinite(latest)) return null
    return { text: latest.toFixed(2), tone }
  }
  if (factor === 'funding_rate') {
    const latest = v.latest
    if (latest == null || !Number.isFinite(latest)) return null
    return { text: `${(latest * 100).toFixed(4)}%`, tone }
  }
  if (factor === 'open_interest') {
    const chg = v.change_pct_24h
    if (chg == null || !Number.isFinite(chg)) return null
    return { text: `${chg > 0 ? '+' : ''}${chg.toFixed(2)}%`, tone }
  }
  if (factor === 'basis') {
    const pct = v.basis_pct
    if (pct == null || !Number.isFinite(pct)) return null
    return { text: `${pct.toFixed(3)}%`, tone }
  }
  if (factor === 'sentiment') {
    const fgi = v.fear_greed
    if (fgi == null || !Number.isFinite(fgi)) return null
    return { text: fgi.toFixed(0), tone }
  }
  // 三期批1 +2(funding_predicted 同 funding 格式 · global 已并入 RATIO_FACTORS)
  if (factor === 'funding_predicted') {
    const latest = v.latest
    if (latest == null || !Number.isFinite(latest)) return null
    return { text: `${(latest * 100).toFixed(4)}%`, tone }
  }
  if (factor === 'funding_zscore') {
    const z = v.z
    if (z == null || !Number.isFinite(z)) return null
    // 特例:|z|>2 才按方向着色(极端才有语义)· 区间内中性,不跟 finding 档
    return { text: z.toFixed(2), tone: Math.abs(z) > 2 ? signTone(z) : 'neutral' }
  }
  if (factor === 'oi_volume_ratio') {
    const ratio = v.ratio
    if (ratio == null || !Number.isFinite(ratio)) return null
    return { text: ratio.toFixed(2), tone }
  }
  // 二批刀3:盘口深度 · 失衡(Σ买/Σ卖)+ 价差率 · 任一缺则只显有效项,全缺留白
  if (factor === 'depth') {
    const imb = v.imbalance
    const sp = v.spread_pct
    const parts: string[] = []
    if (imb != null && Number.isFinite(imb)) {
      parts.push(`${locale === 'en' ? 'Imbalance' : '失衡'} ${imb.toFixed(2)}`)
    }
    if (sp != null && Number.isFinite(sp)) {
      parts.push(`${locale === 'en' ? 'Spread' : '价差'} ${(sp * 100).toFixed(3)}%`)
    }
    if (parts.length === 0) return null
    return { text: parts.join(' · '), tone }
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
 * sparkline 语义配置:基准线(费率/基差 0 轴 · 比值 1.0 轴)+ 线色。
 * 线色与 factorHeadline 同源(刀D-B:跟 finding.state 档位收敛,无判定中性灰)。
 * 缺因子 → 默认帝王金、无基准线(与一期行为一致)。
 */
export function sparklineSpec(
  factor: string,
  snapshot: StructureSnapshot,
  finding?: Pick<FactorFinding, 'state'> | null,
  locale: 'en' | 'zh' = 'zh',
): { baseline?: number; stroke: string } {
  const head = factorHeadline(factor, snapshot, finding, locale)
  const stroke = head ? TONE_HEX[head.tone] : '#B8860B'
  if (RATIO_FACTORS.has(factor)) return { baseline: 1, stroke }
  if (factor === 'funding_rate' || factor === 'basis') return { baseline: 0, stroke }
  return { stroke }
}
