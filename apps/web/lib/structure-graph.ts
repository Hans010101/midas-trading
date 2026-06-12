/**
 * 因子关联图谱 · 规则引擎(沙盘助手二期刀1 · G1 乙案)。
 *
 * 边 = 确定性金融规则从 diag.snapshot 已有数值推导(可解释 · 可单测 · 不幻觉),
 * 与 LLM 判定分层:节点高亮才用 LLM 点名(isDivergentFinding),边一律署名「规则推导」。
 * 🔴 红线:纯前端推导 —— services/structure 三件零碰,不进不改 LLM 链。
 *
 * 输入容错:snapshot 因子缺失(null)→ 涉及该因子的规则整条跳过,绝不报错。
 */

import type { StructureSnapshot } from '@/lib/api/structure'

export type EdgeType = 'divergence' | 'resonance'

export interface GraphEdge {
  from: string
  to: string
  type: EdgeType
  /** 共振方向(上色:bull 朱红 / bear 墨绿)· 背离边无方向(帝王金) */
  direction?: 'bull' | 'bear'
  /** 一句中文 · tooltip 用(展示侧追加「规则推导」署名) */
  reason: string
}

// 因子键 → 中文名(图谱节点标签 · page 因子卡共用)· 三期批1 扩到 11
export const FACTOR_LABEL: Record<string, string> = {
  account_long_short: '大户账户多空比',
  position_long_short: '大户持仓多空比',
  taker_flow: 'taker 主动买卖',
  open_interest: '未平仓量(OI)',
  funding_rate: '资金费率',
  basis: '基差',
  sentiment: '市场情绪',
  funding_predicted: '预测资金费率',
  funding_zscore: '费率 Z 分数',
  oi_volume_ratio: 'OI 成交额比',
  global_long_short: '全市场人数比',
}

// 阈值(实现定稿):比值偏离均衡 · OI 24h 变化 · FGI 贪婪/恐慌档
const RATIO_SKEW = 0.15 // |ratio − 1| 超此值视为明显偏离
const OI_CHANGE_PCT = 3 // |change_pct_24h| 超此值视为明显增/减仓
const FGI_GREED = 70
const FGI_FEAR = 30
const Z_EXTREME = 2 // |z| 超此值视为费率极端(R10 · 三期批1)

/** 从 7 因子快照推导背离/共振边(确定性规则 · 缺因子跳过)。 */
export function deriveGraphEdges(snapshot: StructureSnapshot): GraphEdge[] {
  const a = snapshot.account_long_short?.value?.latest ?? null
  const p = snapshot.position_long_short?.value?.latest ?? null
  const t = snapshot.taker_flow?.value?.latest ?? null
  const oiChg = snapshot.open_interest?.value?.change_pct_24h ?? null
  const f = snapshot.funding_rate?.value?.latest ?? null
  const fAvg = snapshot.funding_rate?.value?.avg_7d ?? null
  const b = snapshot.basis?.value?.basis_pct ?? null
  const fgi = snapshot.sentiment?.value?.fear_greed ?? null

  const edges: GraphEdge[] = []

  // R1 账户比 ↔ 资金费率(结构方向 vs 付费方向劈叉 → 背离)
  if (a !== null && f !== null) {
    if (a > 1 && f < 0) {
      edges.push({
        from: 'account_long_short', to: 'funding_rate', type: 'divergence',
        reason: '结构偏多但资金费率为负(空头付费),结构与费率背离',
      })
    } else if (a < 1 && f > 0) {
      edges.push({
        from: 'account_long_short', to: 'funding_rate', type: 'divergence',
        reason: '结构偏空但资金费率为正(多头付费),结构与费率背离',
      })
    }
  }

  // R2/R3 账户比 ↔ 持仓比(劈叉 → 背离;同向且都明显偏离 → 共振)
  if (a !== null && p !== null) {
    if ((a - 1) * (p - 1) < 0) {
      edges.push({
        from: 'account_long_short', to: 'position_long_short', type: 'divergence',
        reason: '大户人数方向与持仓方向劈叉(人数与仓位背离)',
      })
    } else if (Math.abs(a - 1) > RATIO_SKEW && Math.abs(p - 1) > RATIO_SKEW) {
      const bull = a > 1
      edges.push({
        from: 'account_long_short', to: 'position_long_short', type: 'resonance',
        direction: bull ? 'bull' : 'bear',
        reason: `人数与持仓同向且明显偏${bull ? '多' : '空'},拥挤共振`,
      })
    }
  }

  // R4/R5 OI ↔ taker(增仓但卖压 → 背离;增仓+买盘 / 减仓+卖压 → 共振)
  if (oiChg !== null && t !== null) {
    if (oiChg > OI_CHANGE_PCT && t < 1) {
      edges.push({
        from: 'open_interest', to: 'taker_flow', type: 'divergence',
        reason: '24h 明显增仓但主动卖压占优,仓量与买卖流背离',
      })
    } else if (oiChg > OI_CHANGE_PCT && t > 1) {
      edges.push({
        from: 'open_interest', to: 'taker_flow', type: 'resonance', direction: 'bull',
        reason: '24h 增仓且主动买盘占优,多头动能共振',
      })
    } else if (oiChg < -OI_CHANGE_PCT && t < 1) {
      edges.push({
        from: 'open_interest', to: 'taker_flow', type: 'resonance', direction: 'bear',
        reason: '24h 减仓且主动卖压占优,多头撤退共振',
      })
    }
  }

  // R6 基差 ↔ 账户比(贴水但结构偏多 → 背离)
  if (b !== null && a !== null && b < 0 && a > 1) {
    edges.push({
      from: 'basis', to: 'account_long_short', type: 'divergence',
      reason: '合约贴水(基差为负)但结构偏多,基差与结构背离',
    })
  }

  // R7 费率 ↔ 基差 ↔ 账户比 三者同向 → 共振链(两条边)
  if (f !== null && b !== null && a !== null) {
    if (f > 0 && b > 0 && a > 1) {
      const reason = '费率为正、基差升水、结构偏多,三者同向共振'
      edges.push(
        { from: 'funding_rate', to: 'basis', type: 'resonance', direction: 'bull', reason },
        { from: 'basis', to: 'account_long_short', type: 'resonance', direction: 'bull', reason },
      )
    } else if (f < 0 && b < 0 && a < 1) {
      const reason = '费率为负、基差贴水、结构偏空,三者同向共振'
      edges.push(
        { from: 'funding_rate', to: 'basis', type: 'resonance', direction: 'bear', reason },
        { from: 'basis', to: 'account_long_short', type: 'resonance', direction: 'bear', reason },
      )
    }
  }

  // R8 情绪 ↔ 费率(贪婪×高费率 / 恐慌×负费率 → 共振)
  if (fgi !== null && f !== null) {
    if (fgi >= FGI_GREED && fAvg !== null && f > fAvg) {
      edges.push({
        from: 'sentiment', to: 'funding_rate', type: 'resonance', direction: 'bull',
        reason: '贪婪情绪与高于 7 天均值的费率共振(过热迹象)',
      })
    } else if (fgi <= FGI_FEAR && f < 0) {
      edges.push({
        from: 'sentiment', to: 'funding_rate', type: 'resonance', direction: 'bear',
        reason: '恐慌情绪与负费率共振(过冷迹象)',
      })
    }
  }

  // R9 预测费率 ↔ 当期费率均值(反号 → 背离 · 三期批1)
  const pred = snapshot.funding_predicted?.value?.latest ?? null
  if (pred !== null && fAvg !== null && pred * fAvg < 0) {
    edges.push({
      from: 'funding_predicted', to: 'funding_rate', type: 'divergence',
      reason: '预估费率与 7 天均值方向相反,费率结构转折中',
    })
  }

  // R10 费率 z-score 极端且与结构同向 → 共振(三期批1)
  const z = snapshot.funding_zscore?.value?.z ?? null
  if (z !== null && a !== null) {
    if (z > Z_EXTREME && a > 1) {
      edges.push({
        from: 'funding_zscore', to: 'account_long_short', type: 'resonance', direction: 'bull',
        reason: '费率 Z 分数极端偏高且结构偏多,多头拥挤确认',
      })
    } else if (z < -Z_EXTREME && a < 1) {
      edges.push({
        from: 'funding_zscore', to: 'account_long_short', type: 'resonance', direction: 'bear',
        reason: '费率 Z 分数极端偏低且结构偏空,空头拥挤确认',
      })
    }
  }

  return edges
}
