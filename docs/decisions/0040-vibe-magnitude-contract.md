# ADR 0040 · vibe 回测数值字段量纲契约(防 ×100 类显示翻车)

- 状态:**Draft(未拍板)** —— 随 feat/vibe-magnitude-contract 分支一起审;Hans 合并即转 Accepted。
- 日期:2026-06-10(P2-prep 任务2 · 接力期间产出)
- 相关:P1-4e.fix(return_pct ×100 真机翻车)· docs/research/lab-display-magnitude-audit.md(全字段审计)· ADR 0038

## 背景(翻车驱动)

vibe 引擎**同一份 artifacts 用两套量纲**:metrics.csv(16 指标)与 equity.csv 的比例类字段是
【比率】(0.1=10%),而 trades.csv 的 return_pct 是【百分比数值】(-2.76=-2.76%)。P1-4d 前端把
return_pct 当比率 ×100 → 真机显示 -276%/-498%/+2352%(P1-4e.fix 修复)。教训:
**标注的假设 ≠ 验过的事实;同源引擎 ≠ 同一量纲。**

## 决策

1. **量纲契约落在两处,源码即文档**:
   - `apps/web/lib/api/backtest.ts` —— 三个 interface 逐字段注明【比率/百分比数值/绝对额/无量纲比值/计数/天】+ 验证状态(实测/推断);
   - `apps/web/lib/format-backtest.ts` —— 格式化函数唯一实现(从 lab-report.tsx 抽出),头注释写选用规则。
2. **格式化函数 ↔ 量纲一一对应**(选错=差 100 倍):

| 量纲 | 函数 | 例 | 适用字段 |
|---|---|---|---|
| 比率 | `fmtPct`(×100) | 0.1→"+10.00%" | metrics 收益/回撤/胜率类 · equity.drawdown |
| 百分比数值 | `fmtPctNum`(不×100) | -2.76→"-2.76%" | **仅 trades.return_pct** |
| 无量纲比值 | `fmtRatio` | 1.2→"1.20" | sharpe/calmar/sortino/盈亏比/盈利因子/IR |
| 绝对额/价 | `fmtNum` | -27547.76→"-27,547.76" | final_value/price/pnl/equity |
| 整数计数 | `fmtInt` | 17→"17" | trade_count(完整回合)/max_consecutive_loss |

3. **vitest 锁死契约**(`lib/format-backtest.test.ts`):用真机实测值断言(-2.76→-2.76%;反例断言
   `fmtPct(-2.76)==='-276.00%'` 锁死两函数 100 倍差异);**fixture 禁用 0 值**(0 在两种量纲下相同,
   侧证不了契约 —— 本次 fixture return_pct=0.0 正是漏网原因之一)。
4. **新字段上屏流程(强制)**:先真机核对原值(tooltip 带原值 / SQL 直查)确认量纲 → 选函数 → 上屏。
   未验字段在类型注释标「推断 · 上屏前须真机核原值」(现存:equity.ret/active_ret)。

## 现状缺口(诚实记账)

- web-test.yml **不跑 vitest**(只 lint+type-check+build)→ 本测试目前仅本地闸。把 `pnpm test` 加进
  CI 是一行步骤,但动 CI 配置 = Hans 拍(建议合并本分支时顺手加)。
- 后端 `tests/factories.py` 的 `make_backtest_result` 仍含 return_pct=0.0 等不可侧证值 → 后续改非零
  可辨值(动 apps/api 触发后端 CI,另刀)。

## 后续

- Hans 审合本分支 → 状态转 Accepted;
- 可选追加:web-test.yml 加 `pnpm test` 步;后端 fixture 改非零值。
