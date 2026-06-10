/**
 * 研究室回测数值格式化 · 量纲契约的唯一实现(ADR 0040 · P2-prep 任务2)。
 *
 * ★ vibe 引擎同一份 artifacts 里存在【两套量纲】(P1-4e.fix 真机翻车确诊):
 *   - metrics.csv(16 指标)+ equity.csv 的 drawdown/ret/active_ret → 【比率】(0.1 = 10%)
 *   - trades.csv 的 return_pct                                   → 【百分比数值】(-2.76 = -2.76%)
 *   选错函数 = 差 100 倍(曾把 -2.76% 显示成 -276%)。
 *
 * 选用规则(新字段上屏前先真机核对原值,再选函数 —— 标注的假设 ≠ 验过的事实):
 *   比率        → fmtPct(×100 加 %)
 *   百分比数值  → fmtPctNum(不 ×100 直接加 %)
 *   无量纲比值  → fmtRatio(sharpe/calmar 等)
 *   绝对额/价   → fmtNum
 *   整数计数    → fmtInt
 */

/** 【比率】→ 百分比显示(0.1 → "+10.00%")· 用于 metrics 16 指标的收益/回撤/胜率类。 */
export function fmtPct(v: number): string {
  return `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
}

/** 【百分比数值】→ 直接加 %(-2.76 → "-2.76%")· ★仅 trades.return_pct · 绝不 ×100(P1-4e.fix)。 */
export function fmtPctNum(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

/** 无量纲比值(sharpe/calmar/sortino/盈亏比/盈利因子/信息比率)→ 原值两位小数。 */
export function fmtRatio(v: number): string {
  return v.toFixed(2)
}

/** 整数计数(trade_count/max_consecutive_loss)。 */
export function fmtInt(v: number): string {
  return String(Math.round(v))
}

/** 绝对额/绝对价(final_value/price/pnl)→ 千分位 · 最多 2 位小数。⚠ 低价币(<$1)精度待 symbol 放开时再议。 */
export function fmtNum(v: number): string {
  return v.toLocaleString('en-US', { maximumFractionDigits: 2 })
}
