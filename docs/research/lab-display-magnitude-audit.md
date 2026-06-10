# /lab 显示层量纲/格式假设审计(P2-prep 任务1 · 2026-06-10)

> 背景:return_pct ×100 bug(P1-4e.fix)的教训 = 「标注的假设 ≠ 验过的事实」。本报告只读排查
> /lab 两页(app/lab/page.tsx + components/lab/lab-report.tsx + lib/api/backtest.ts)**所有上屏
> 数值字段**,逐个列「来源 → 前端处理 → 量纲假设 → 验证状态」。只出报告,不改代码。
> 验证状态三档:**实测**(真机原值核对过)/ **强印证**(真机看过显示值合理 + 多源自洽)/ **推断**(仅代码/字段名)。

## 一、metrics_json(16 指标 · 指标卡 + 结论区)

| 字段 | 前端处理 | 量纲假设 | 验证状态 |
|---|---|---|---|
| total_return / annual_return / max_drawdown / win_rate / benchmark_return / excess_return | `fmtPct`(×100) | **比率**(0.1=10%) | **强印证**:真机指标卡数值合理(未见 ×100 级异常);P1-3 实测 total_return -18.5% ↔ 0.185;max_drawdown 与 drawdown 曲线(实测比率)同源自洽 |
| sharpe / calmar / sortino / profit_loss_ratio / profit_factor / information_ratio | `fmtRatio`(toFixed(2) 原值) | 无量纲比值 | 强印证(真机合理) |
| trade_count / max_consecutive_loss | `fmtInt` | 整数计数;trade_count=完整回合 | **实测**(34/17 口径诊断,真机印证 17) |
| avg_holding_days | toFixed(1) | 单位=天 | 推断+弱印证(字段名 + 与 trades.holding_days 同源;未逐字段对照原值) |
| final_value | `fmtNum` | 绝对额(报价币 USDT) | 强印证(与 initial_cash 1,000,000 口径自洽) |

## 二、equity_json(收益曲线 + 回撤副图)

| 字段 | 前端处理 | 量纲假设 | 验证状态 |
|---|---|---|---|
| equity / benchmark_equity | 双线直接画 + toLocaleString | 绝对额 | 强印证(真机曲线与初始资金量级一致) |
| drawdown | `Math.abs` + ×100 显示 | **比率 ≤0**(-0.0201=回撤2%) | **实测**(P1-4e 副图 tooltip 带原值,真机确认 -0.0201) |
| ret / active_ret | **前端未渲染** | 比率(推断 · fixture 0.01/0.005) | 推断 · **无显示风险**(没上屏);若未来上屏须先真机核原值 |

## 三、trades_json(逐笔明细表)

| 字段 | 前端处理 | 量纲假设 | 验证状态 |
|---|---|---|---|
| return_pct | `fmtPctNum`(**不**×100) | **百分比数值**(-2.76=-2.76%) | **实测**(P1-4e.fix · 真机 -276%→-2.76% 修正确认) |
| pnl | `fmtNum` | 绝对额(报价币) | **实测**(确诊时手算价差×qty 与 -27,547.76 自洽) |
| price | `fmtNum`(2 位小数) | 绝对价 | 强印证;⚠ 留意:低价币(<$1)2 位小数损精度 —— 当前标的 BTC 无碍,放开 symbol 后需关注 |
| qty | **裸渲染 `{t.qty}`(零格式化)** | base 币数量 | 推断;⚠ 浮点长尾(如 9.5384615…)会原样上屏 —— 非量纲错,纯显示打磨候选,**待 Hans 真机瞄一眼** |
| holding_days | toFixed(1) | 单位=天 | 推断+弱印证(同 avg_holding_days) |
| timestamp | 裸渲染字符串 | 日期串("2025-01-18") | 实测(1d 下正常);period 若放开 1h 会变长含时间,裸串仍正确只是变宽 |
| side | buy=开仓腿 / sell=平仓腿(isOpen 判定) | 多头策略恒先买后卖 | **实测**(34/17);⚠ **边界**:若未来策略含做空(先 sell 开仓),`isOpen=side==='buy'` 判定会反 —— 当前 SMA 纯多头成立,放开策略类型时必须重审 |
| reason | 裸渲染字符串 | — | 安全 |

## 四、run_card_json + 列表页

- run_card:`JSON.stringify` 原样 pretty + data_sources join —— **无量纲假设,安全 by construction**。
- 列表页 created_at:`new Date(...).toLocaleString('zh-CN')` —— FastAPI 序列化 tz-aware ISO 串可解析,真机列表时间正确(实测)。

## 五、结论(按风险排序)

1. **高风险残留:无**(return_pct 已修;全部「×100 类」字段均已实测或强印证)。
2. **中(纯显示,非量纲错)**:`qty` 零格式化可能长尾上屏 —— 建议 Hans 真机瞄 run 6/8 逐笔表「数量」列,难看再修(toFixed/有效位数,一行级)。
3. **低/记账**:① holding_days「天」单位是推断(弱印证);② ret/active_ret 未验但未上屏;③ price 2 位小数对低价币的精度(放开 symbol 才相关);④ side 开/平判定的做空边界(放开策略类型才相关)。
4. **建议防御**(对应 P2-prep 任务2,另分支落地):字段量纲写进 lib/api/backtest.ts 类型注释 + ADR 契约;格式化函数抽出可测文件 + vitest 断言;**测试 fixture 不要用 0 值**(本次 fixture return_pct=0.0 导致量纲无法侧证——0 在两种量纲下相同)。
