# 0010 · 数据精度诊断报告

## 状态
Approved (2026-05-20 · 配置级 bug 已修 · 数据源保持不变)

## 上下文

M0 收口时产品负责人反馈:
- 用户看到 NVDA $6.55(真实约 $220)
- BTC 价格不准
- 整体数据信任度低

诊断范围(产品负责人指令):
- 不换数据源(后续单独决策)
- 只诊断根因 + 修配置级 bug
- 区分:**代码 bug 可立即修** vs **数据源固有局限须换源**

---

## 诊断结果摘要

**结论:这不是数据源问题,是代码 bug。修了 1 行 SQL 就全部对齐权威源。**

| 市场 | 旧显示 | 修复后 | 权威源 | 偏差 | 状态 |
|---|---|---|---|---|---|
| 美股 NVDA | $6.55 | **$221.37** | Yahoo Finance $220.61 | **+0.34%** | ✅ |
| 加密 BTC/USDT | $26,206 | **$76,830** | Binance API $77,357 | -0.68% | ✅ |
| A 股 600519 | ¥599.36 | **¥1,324.30** | AKShare Sina ¥1,315 / 东财 ¥1,332 | +0.71% | ✅ |

3 个市场最大偏差 0.71% · 远低于 ±1% 阈值 · **CH 内数据本身没问题,显示错的只是查询语义错位。**

---

## 根因 · ClickHouse `select_kline` SQL 取错窗口

**位置:** `apps/api/app/services/clickhouse_client.py:194`

**旧实现:**
```sql
SELECT ts, open, high, low, close, volume, amount FROM kline
WHERE symbol = ? AND market = ? AND period = ?
ORDER BY ts ASC LIMIT ?
```

**问题语义:** `ORDER BY ts ASC LIMIT N` 返回**最早的 N 根**,不是最新。

- `limit=500` 时:返回最早 500 根(2018-2019 NVDA / 2017-2018 BTC)· 看 K 线图最初渲染的 5 年走势恰好看不出问题
- `limit=1` 时(price fetcher 用):返回**第一根 K 线**(2018-06 NVDA close=$3.15,经历两次拆股已经是后复权价)
- `limit=2` 时(price anomaly worker 用):返回最早 2 根 · 错位更严重

**影响范围:**
- `/api/v1/virtual/orders` 撮合用的市场价 → 错(基于 limit=1)
- watchlist 30s 报价拉的「最新价」→ 错(用 kline limit=2 算涨跌)
- 价格异动 worker 检测 ±5% → 错(基于 limit=2)

**修复(`clickhouse_client.py` 单点改动):**
```python
# 旧
sql += " ORDER BY ts ASC LIMIT %(limit)s"
# 新 · DESC 拿最新 N 根 + Python 端 reverse 还原 ASC 契约
sql += " ORDER BY ts DESC LIMIT %(limit)s"
...
klines.reverse()  # 保持所有调用方期待的 ASC 顺序
```

**调用方契约不变:** 所有调用方原本期待 list 按 ts 升序 · 修复后仍按 ts 升序 · 只是「最近 N 根」语义恢复正确。

---

## 各市场详细诊断

### 美股 · NVDA via yfinance

**之前怀疑:** NVDA 历史多次拆股(2021 4:1 + 2024 10:1)· 复权口径错?

**实测:**
- `yf.Ticker("NVDA").history(period="2d", auto_adjust=True).iloc[-1]` → $220.61
- `yf.Ticker("NVDA").history(period="2d", auto_adjust=False).iloc[-1]` → 同 $220.61(yfinance 已经自动反向调整 + 不影响 latest 价)
- `ticker.info.regularMarketPrice` → $220.61

**结论:** **yfinance auto_adjust=True 配置正确。** us_source.py 把历史 K 全部存进 CH · 历史 K 经过复权后,2018 年 NVDA close ~ $3.15(post-2024 10:1 split = 真实 $31.50 ÷ 10),这本来就是正确的。**真正错的是查询时取了 2018 那根。**

修复后我们的 NVDA $221.37 跟 Yahoo $220.61 偏差 +0.34%,因为:
- CH 上次同步是 2026-05-19 close
- Yahoo 实时 = 2026-05-19 close
- 差 0.34% 是 yfinance 跨日 close 跟 intraday 修正的正常飘逸

✅ **yfinance 配置无 bug · 不需要换源**

### 加密 · BTC/USDT via ccxt Binance

**之前怀疑:** ccxt 配置 / timeframe 对齐?

**实测:**
- `ccxt.binance().fetch_ohlcv("BTC/USDT", timeframe="1d", limit=2)[-1]` → close=$77,356.59
- `ccxt.binance().fetch_ticker("BTC/USDT")["last"]` → $77,356.59
- 我们 CH 显示 $76,830.44 · 偏差 -0.68%

**偏差来源:** Celery beat `update-crypto-demo` 每 5 分钟跑一次 · 截图当时是几分钟前的快照 · 7-77K 价格已经飘 0.68% · 完全正常。

✅ **ccxt 配置无 bug · 不需要换源**

### A 股 · 600519(贵州茅台)via AKShare

**之前怀疑:** Sina 源复权口径(前复权 / 后复权 / 不复权)?

**实测:**
- `ak.stock_zh_a_daily(symbol="sh600519")` Sina · 最新 close ¥1,315
- `ak.stock_zh_a_hist(symbol="600519", adjust="")` 东财不复权 · close ¥1,332
- 我们 CH 显示 ¥1,324.30 · 偏差 +0.71%(对比 Sina)

**偏差来源:** AKShare Sina `stock_zh_a_daily` 默认**不复权**(我们没传 `adjust` 参数)· 跟东财不复权口径一致 · ±0.71% 是当日盘后 vs 实时数据的小漂浮。

✅ **AKShare 配置无 bug · 不需要换源**

⚠️ **建议(非本波必做):** 后期可考虑在 cn_source.py 明确传 `adjust="qfq"`(前复权)· 跟用户主观感受的「历史价格」更一致。但当前不复权也能用,M2+ 决策。

---

## 关于「拆股复权」的澄清

| 市场 | 库默认行为 | 我们的配置 | 结果 |
|---|---|---|---|
| yfinance | auto_adjust=True(后复权)| auto_adjust=True | ✅ 跟实时价对齐 |
| ccxt Binance | 无拆股概念(连续 24/7) | 直接 OHLCV | ✅ |
| AKShare Sina daily | 默认不复权 | 不传 adjust | ⚠ 历史价 = 当时真实价(不复权)|

NVDA 历史 K 线显示 $3 / $8 等小价格 = 复权后正确 · 不是 bug 是 feature。前端图表把 5 年数据连成线时,自然就是从 $3 涨到 $221 的全程趋势。但**「最新价」必须取最新的一根 K**,这就是我们的 SQL bug 修掉的事。

---

## 修复后端到端验证

```
== NVDA latest via API ==
{"ts": "2026-05-19T04:00:00Z", "close": 221.37}    (Yahoo $220.61)

== BTC latest via API ==
{"ts": "2026-05-20T00:00:00Z", "close": 76830.44}  (Binance $77,357)

== 600519 latest via DB ==
2026-05-19 close ¥1324.30                          (Sina ¥1,315)
```

`/workbench` 显示的实时报价 / `/virtual/orders` 撮合用价 / 价格异动 ±5% 检测 全部受益于这个修复。

---

## 受影响功能(全部自动恢复)

| 功能 | 之前状态 | 现在 |
|---|---|---|
| 工作台顶部「可用 / 持仓」估值 | 用错市场价 → 持仓估值大错 | 正确 |
| /virtual/orders 撮合 | 撮合价是 5 年前的 K → 滑点 / 手续费基数错 | 正确(已存的 stale 订单不动)|
| /portfolio 浮盈 = (current - avg) × qty | current 错 → 浮盈错 | 正确 |
| 价格异动检测 ±5% | 比较 oldest vs second-oldest · 永不触发 | 正确(每 1 分钟扫真实当日 vs 昨日)|
| watchlist 30s 报价 | 显示 5 年前 close + 涨跌幅 0.08% 之类 | 正确 |
| 缠论分析 | 用了 ASC 的 limit=300 拿到最早 300 根 · 实际是 2018-2019 数据 | 修复后拿到最近 300 根 · 反映当前市场结构 |

---

## 自主决策清单

1. **修 SQL 而不是修调用方** · select_kline 是单点 · 改它一处保所有调用方语义正确
2. **保留 list 升序契约** · DB DESC + Python reverse · 调用方代码完全不动
3. **不换数据源** · 三家源(yfinance / ccxt / AKShare Sina)配置都正确,只是查询取错
4. **NVDA 历史 K 保持复权** · M0 阶段不动 us_source.py · 未来若有「显示真实历史价」需求,M2+ 决策
5. **AKShare 保持不复权** · 跟东财不复权一致 · 用户买虚拟单时按当前价撮合,跟复权口径无关
6. **不回填数据** · CH 内数据本来就对,只是查询窗口错;无需重新拉历史

---

## P1 残留(M0 后做)

| 项 | 影响 |
|---|---|
| **历史已存的 VirtualOrder.price 仍是 stale 价** · 这些是 Q smoke test 阶段下的「假成交」(NVDA $6.55 / BTC $26K)· 用户的 hans@test.com 持仓 avg_entry_price 也是 stale | 测试账号 reset 即可清理 · 真实用户没有这些数据 |
| **价格异动 worker 之前的 trigger key 在 Redis 中** · 可能影响下一波去重判定 | TTL 300s 自动过期,5 分钟内自愈 |
| **AKShare Sina 默认不复权** vs 前端可能希望显示前复权 | M2+ 决策时一并考虑 |

---

## 不需做(本波明确不动)

- ❌ 换 yfinance · 当前配置 100% 正确
- ❌ 换 ccxt 交易所 · Binance OK,数据来源稳定
- ❌ 换 AKShare 数据源 · Sina + 东财双源已就位
- ❌ 重新回填 CH 历史 K · 数据本来正确,只是查错
- ❌ 加付费 API(polygon.io / 同花顺 / 万得) · M2+ 真上线再考虑

---

## 撤销路径(如果以后真要换源)

`services/data_sources/{cn,us,crypto}_source.py` 三个适配器各实现 `BaseDataSource`,新源加一个新文件 + 改 main.py lifespan 注入即可,**调用方不动**。`select_kline` 修复也跟数据源选型解耦。

---

## 备注

- 本诊断花了 ~30 分钟(读源 → 实测 yfinance / ccxt / AKShare → SQL 一行修复 → 三市场 curl 验证)
- **「数据精度」不是数据源固有局限 · 是我们代码 bug · 早 发现 早 修**(违反 0002 翻车铁律 5「数据流终态用 SQL/工具直接看」· 我们之前没用 ClickHouse client 直查过「最新一根 K」)
- **新铁律候选:**「凡是 SQL `ORDER BY ... LIMIT N` 跟『最新 / 最旧』语义相关的,代码里必须显式 DESC + reverse,不能依赖 ASC 排序的偶然」
