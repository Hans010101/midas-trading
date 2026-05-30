# ADR 0034 · 港股(第 4 市场)接入 · 股票现货

- 状态:**Proposed(待审 · 草稿)** · 2026-05-30
- 决策人:产品负责人(方向已定:① 每手股数必须做不简化 · ② 免费源起步不接付费 · ③ 接受免费源实时延迟 ~15min)
- 关联:0008(虚拟交易)· 0009/0028(推送/降噪)· 0010(数据精度)· 0032(多通道 TG+飞书)· 0033(自验铁律)·
  `docs/research/` 港股调研报告(本 ADR 的现状证据来源)
- 背景:在 A 股 / 美股 / 加密之外加**第 4 个市场「港股」**,定位**股票现货**(对齐 A 股 / 美股,不套加密合约逻辑)。
  这是中大工程:数据层 CH Enum8 迁移 + 每手股数(board lot)逻辑是两个大头;市场维度 ~15-20 处硬编码需加 hk;
  现货撮合内核高度复用、不碰。

---

## 1. 港股市场定位 + 红线对齐

**定位**:港股 = 股票现货 · HKD 计价 · 虚拟资金 · **复用现货撮合内核(engine `place_market_order`)· 不碰 perp**。

**现有红线在港股怎么守:**
- **虚拟资金 / 永不接真实下单**:港股走同一虚拟撮合 `virtual_trading/engine.py`,不接任何真实券商通道。产品 DNA,港股同守。
- **免责分级(0032 四-A)**:港股下单 / 成交带交易口径「本次为模拟交易,不构成投资建议」;行情 / 查询带「仅供参考」——
  复用 `ReplyModel.disclaimer` 分级,**改一处共享层、TG + 飞书两通道同生效**。
- **只读 CH 为主**:港股 K 线走现有「读 CH 优先 + cache miss 才回源 warm」(market.py:70-115),**不新增实时轮询打上游**;
  实时延迟 15min 由"读已采 CH + 低频 warm"天然吸收。
- **AI / 策略输出**带「仅供参考,不构成投资建议」。
- **凭证 / 数据源 key** 只 env 读,不进 git / 前端 / 日志。

---

## 2. ★ 数据层方案(最关键 · 含硬卡点)

### 2.1 ClickHouse `market` Enum8 迁移(★ 改已上线存储 · 中风险)
**现状**(`docker/clickhouse-init.sql`):
- `kline.market = Enum8('cn'=1, 'us'=2, 'crypto'=3)`(:7)· `symbol_meta.market` 同(:23)
- `kline` 表 `PARTITION BY (market, toYear(ts))`(:17)· `ORDER BY (symbol, period, ts)`(:18)
- Python 侧 `insert_kline` / `select_kline` 传 `market` 字符串(clickhouse_client.py:106/193),由 CH 的 Enum8 校验 ——
  **插入 `market='hk'` 而 Enum8 未含 hk → CH 直接拒**。

**迁移**(两张表):
```sql
ALTER TABLE kline       MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3,'hk'=4);
ALTER TABLE symbol_meta MODIFY COLUMN market Enum8('cn'=1,'us'=2,'crypto'=3,'hk'=4);
```
- **预期行为(★ 阶段零必须服务器实测确认)**:只**新增**枚举值、不改旧值映射(cn=1/us=2/crypto=3 不动)→
  ClickHouse 的 Enum 扩展是 **metadata-only ALTER**:秒级、**不重写已有数据、不触发重分区**(旧分区 market 值映射不变,新 hk 数据进新分区)。
- **是否需停写**:metadata-only 理论不需停写;**保险起见**迁移在低峰执行,可短暂停 worker(可选,阶段零评估)。
- **回滚预案**:Enum 加值向后兼容(旧值仍在)。回滚分两种:
  · 无 hk 数据 → `MODIFY COLUMN` 回原 Enum8 即可;
  · 已有 hk 数据 → 先 `ALTER TABLE kline DROP PARTITION`(hk 分区)再 MODIFY 回。迁移脚本写成**幂等** + 落 docs。
- **⚠ init.sql vs 线上**:`clickhouse-init.sql` 是**新环境建库初始化**;线上是已存在的表 → 线上走 **ALTER**(不是改 init.sql 重建)。
  init.sql 也同步把 Enum8 加上 hk(给将来新环境),但**线上迁移靠 ALTER 脚本**。
- 其它带 market 的表:crypto_* / cn_* / us_* 都是**市场专属命名表**(非共享 Enum8),港股不涉及;只有 `kline` + `symbol_meta` 两张共享表需 ALTER。

### 2.2 `hk_source` 数据源适配器
- 新建 `app/services/data_sources/hk_source.py`,**对齐 cn_source(akshare)/ us_source(yfinance)模式**:
  `class HkSource(BaseDataSource)` · `name=...` · `market="hk"` · 实现 `fetch_kline(symbol, period, limit)`(+ 后续 `fetch_spot_snapshot`)。
- **数据后端 = 免费源**(产品②):akshare 港股接口(如 `stock_hk_hist`)或 yfinance `.HK` ticker(如 `0700.HK`)——
  **阶段零实测定主源**(零-B)。
- **接入工厂**:`_source_for`(market.py:146-160)的 `mapping` 加 `"hk": hk` + `api/deps.py` 加 `HkSourceDep`(对齐 `CnSourceDep`)。
- **symbol 规范化**:港股代码(5 位 `00700`)↔ yfinance 风格(`0700.HK`)在适配器内部 normalize(对齐 crypto `BTC/USDT`↔`BTCUSDT` 的现成模式)。

### 2.3 kline 采集 = 复用现有模型(零新管线)
港股 K 线**自动走** market.py:70-115 的「`select_kline` 读 CH 优先 → `len(cached)>=limit` 命中即返 → cache miss 才
`source.fetch_kline` 回源 → `insert_kline` 缓存」—— 只要 `_source_for` 有 hk + CH Enum8 含 hk,**不写新采集逻辑**。

---

## 3. ★ 每手股数(board lot)方案

### 3.1 现状(全缺)
- `order.py:304` 开仓 `qty = (notional / price).quantize(_QTY_Q=8dp, ROUND_DOWN)` = **小数股、不按手**。
- engine.py 全是通用 `Decimal.quantize`,无 lot 概念。港股**必须按「每手股数」整数倍下单**
  (不同股票一手不同:腾讯 00700 = 100 股/手,部分股 500 / 2000 股/手)。

### 3.2 每手股数数据来源(★ 阶段零确认 · 零-C)
- 首选:akshare 港股接口(`stock_hk_spot_em` 等)是否含「每手股数 / 最小买入量」字段 → **阶段零实测确认**。
- 兜底:若源不含 → 维护一份**港股标的 → 每手** 的**策展配置**(对齐 `us_pool.py` 策展池模式),首批覆盖热门港股;
  未覆盖标的暂不可下单(给提示)。

### 3.3 下单数量逻辑改造(全新逻辑 · 详细)
**整手取整公式**:
```
目标股数 = notional ÷ price
手数     = floor(目标股数 ÷ lot_size)        # 向下取整到整手
实际股数 = 手数 × lot_size                   # 整手
```
- **落点**:`bot/order.py` 的 `_resolve_spot_order` / `build_preview` —— 注入 `lot_size`(按 market 取),
  **market=="hk" 走整手逻辑;其它市场维持原小数逻辑(零回归)**。
- **不足 1 手 → 拒单** + 友好提示(如「名义资金 X HKD 不足 1 手:00700 一手 100 股 × 现价 Y = Z HKD」)。
- **预设名义**(`bot_order_preset`):加 **HKD 名义预设档**(对齐现有 `spot_notional_cny` / `spot_notional_usd`)。
- **持仓数量**:`VirtualPosition.quantity` 存实际整手股数;估值 / 盈亏复用现货逻辑(乘价即可)。
- **测试矩阵(港股专属)**:整手取整正确 · 不足 1 手拒单 · 不同 lot_size(100/500/2000)· HKD 名义换算 · 二次确认必经。

---

## 4. 港股特性适配清单

| 特性 | 现状证据 | 改法 |
|---|---|---|
| **HKD 币种**(~5 处)| query.py:32 / order.py:107 / replies.py:151 / templates.py:23 / replies.py:47 全缺 HKD | 各加 `hk→HKD` + `HKD→HK$`;`fees.py` 加港股 HKD 费率档(印花税 + 佣金象征虚拟值)|
| **港股交易日历** | market_calendar.py:103-106 仅 `if cn / else us`;`MarketKind=Literal["cn","us"]`(market_home.py:17)| 加 `_hk_status`:早盘 **9:30-12:00** / 午盘 **13:00-16:00**(含午休 closed)+ 港股节假日表(硬编码 or CH calendar,对齐 `cn_trading_days`)|
| **市场维度 ~15-20 处** | `Market=Literal`(market.py:15)+ 副本(alert_rule.py:14 / registry.py:226 `_ALL` / watchlist.py:55)· `_VALID_MARKETS`(router.py:52)· `_MARKET_LABEL`(replies.py:46)· examples(replies.py:292,386)· `_PREVIEW_PATH`(replies.py:49)· `MARKET_LABEL`(templates.py:22)| 各加 `hk`(类型加 `"hk"` · label `"hk":"港股"` · example `"hk":"00700"` · preview path 等)|
| 涨跌幅 / 停牌 | 虚拟撮合无涨跌停校验;停牌 = 无报价 → order.py `quote_price None → 拒单` 兜底 | 停牌靠现有无报价兜底;涨跌幅对虚拟交易无需校验(暂不做)|

---

## 5. 复用现货内核(高复用 · 确认不碰)
- **撮合 / 下单 / 持仓**:`virtual_trading/engine.py` 现货撮合(`place_market_order`)+ `bot/order.py` `_exec_spot` +
  `VirtualPosition` 都按 `market` 字符串走、**不写死 cn/us** → 港股直接复用现货路径(整手取整是唯一新增,见 §3)。
- **行情 / 自选 / 持仓渲染**:bot/replies.py 按 market 渲染,加 hk 的 label/ccy 即用。
- **★ 明确不碰**:perp 全链路(engine / dispatcher / funding / liquidation)· A 股 / 美股 / crypto 现有行为(零回归 · golden 守)。

---

## 6. ★ 阶段零 · 开工前置(港股特有 · 实测通过才进写代码)
三个 must-confirm,**任一不过 → 暂停,回产品负责人重定方案**(换源 / 接付费 / 缩范围):
- **零-A · CH Enum8 在线迁移实测**(midas_test + 服务器):`ALTER MODIFY market Enum8` 加 `'hk'=4` →
  确认 metadata-only、秒级、不重写 / 不重分区、不需长停写 + **回滚演练**(改回 Enum8)。Hans 服务器执行。
- **零-B · 港股数据实测**:拉一只 `0700.HK` 的历史 K 线 + 实时 / 快照 + 复权 → 看**数据质量**(字段全 / 价格对 / 复权对)
  + **延迟**(15min 可接受)→ 定 **akshare vs yfinance 主源**。
- **零-C · 每手股数数据源**:akshare 港股接口有无「每手」字段 → 有则直采;无则策展配置兜底(§3.2)。
> 阶段零**不写业务代码**,只跑实测脚本 + 出报告;三项绿才进阶段一。

---

## 7. 分阶段交付(大工程拆小步 · 每步 feature 分支 + 审 + 验收 + `--no-ff` 合 main)

| 阶段 | 范围 | 风险 | 验收点 | 分支 |
|---|---|---|---|---|
| **零 · 实测前置** | CH 迁移实测 + 港股数据实测 + lot 源确认(**不写业务代码**)| 中(碰存储 / 确认源)| 三项实测报告通过 | 服务器 + 脚本 |
| **一 · 数据层** | CH Enum8 迁移(ALTER + init.sql 同步)+ `hk_source` + `_source_for` 接入 + kline 采集复用 | 中(改存储)| hk K 线进 CH · `/market/kline?market=hk` 返数据 · 迁移可逆(up/down/up)| feat/hk-1-data |
| **二 · 市场维度 + 只读** | ~15-20 处加 hk(Literal / 币种 HKD / 标签 / 示例 / 路由)+ `_hk_status` 交易日历 + HKD 钱包档 + 行情/自选/持仓只读 | 低(加配置)| 港股行情 / 自选 / 持仓对齐 A 股/美股 · **TG + 飞书两通道** · golden 零回归 | feat/hk-2-readonly |
| **三 · 下单(每手股数)** | lot_size 注入 + 整手取整 + 不足 1 手拒单 + HKD 名义预设 + 二次确认卡 | **大(新逻辑 + 碰下单)**| 港股整手成交 · 二次确认必经 · 不足 1 手拒单 · 红线测试 · TG + 飞书 | feat/hk-3-order |
| **四 · 收尾** | 港股板块榜单(可选)/ AI 分析接港股 / 视觉细节 / 文档 | 低 | 全链路真机验收 | feat/hk-4-finale |

- 每阶段:feature 分支 + 审过 + **真机验收** + `--no-ff` 合 main;**TG 零回归(golden)每阶段守**。
- **两通道**:港股呈现走共享层(`ReplyModel` / `replies.build_*`),改一处 TG + 飞书同生效(对齐 0032)。
- **部署**:每阶段合 main 触发 deploy;阶段一含 CH 迁移 → 按 0033 铁律盯 Actions 绿 + docker ps + 服务器迁移确认才算上线。

---

## 决策点(需产品负责人拍板)
1. **数据源主源**:阶段零实测后,akshare 港股 vs yfinance `.HK`,哪个做主源?(零-B 定)
2. **每手股数兜底**:若免费源不含每手字段,是否接受「策展配置覆盖热门港股 + 未覆盖标的暂不可下单」?
3. **HKD 虚拟费率**:港股印花税(~0.1%)+ 佣金的虚拟值怎么定(象征性 or 拟真)?
4. **港股标的范围**:首批覆盖全市场 vs 策展热门池(对齐 us_pool ~120 只)?
5. **CH 迁移窗口**:Enum8 ALTER 低峰执行 + 是否短暂停 worker 保险?
6. **板块榜单**:港股 spot/sector 榜单放阶段四(可选)还是不做?

---
> 待审重点(产品负责人 / 我):**§2 数据层迁移方案(Enum8 在线 ALTER 安全性 + 回滚)· §3 每手股数设计 · §6 阶段零前置条件**。
> 审过 + 拍板 → 先做**阶段零实测**,实测过才进阶段一写代码。本 ADR 本轮只出设计,未写实现、未改业务代码。
