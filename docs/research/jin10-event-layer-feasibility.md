# 金十数据作为 Midas「事件感知层」接入可行性调研

> 状态:**纯调研 · 不碰生产代码 · 未申请任何付费/token · 待 Hans 拍板**
> 方法:内部审计(只读 grep 全仓 · midas-i18n-fe/main)+ 官方文档/公开字段评估
> 结论先行(见 §6):**值得接,但只接「事件层」(快讯 flash + 财经日历 calendar),不接报价;先用免费额度实测决策卡增益再决定付不付费。**

---

## ① 现状清单:现有源 → 覆盖 → 喂给谁

### 1.1 四市场行情源(全在 `apps/api/app/services/data_sources/`,继承 `base.py::BaseDataSource`)

| 市场 | 源 | 覆盖数据 | 缺口 |
|---|---|---|---|
| **A股 cn** | AKShare(日K走 Sina · 分钟K走 EastMoney · 全市场 spot 走 Sina) | K线 1m~1w、全市场报价榜 ~5500 只、行业板块 | 无基本面/龙虎榜/北向/事件 |
| **美股 us** | yfinance(`Ticker.history()`) | K线全周期、策展池 ~128 只报价、11 板块+中概 | `amount` 固定 None、无事件 |
| **港股 hk** | AKShare·新浪(日K主源)+ yfinance 降级 | 仅日/周K、~900 只报价、GICS 板块 | 无分钟K、无事件 |
| **加密 crypto** | ccxt Binance 现货 + Binance fapi 直连 + CoinGecko + alternative.me | K线、现货+永续报价、资金费率、持仓量、多空比、总市值/dominance、恐惧贪婪指数(FGI) | 无链上、无事件 |

### 1.2 数据喂给谁(三条消费链)

```
AKShare(cn) ─┐
yfinance(us) ─┤  K线/报价/榜单/板块 ──┬─→ LangGraph 决策卡(只吃 K线 → 指标+缠论)
新浪(hk)     ─┤  (落库 ClickHouse)    ├─→ 回测(只吃 K线 OHLCV)
ccxt+fapi   ─┘  +funding/OI/FGI/dom  └─→ 前端行情页(纯价格/技术/分析端点)
```

- **LangGraph 决策卡**(`services/ai/workflow.py`):`DecisionState` **只吃 K线**;`_node_data_prepare` 从 K线算 MA/MACD/RSI/BOLL/ATR/5日趋势 + 缠论(笔/中枢/买卖点);喂 LLM 的 prompt(`agents/technical.py::_format_snapshot`)**只有 最新价+均线+MACD+RSI+布林+缠论结构**——**零新闻/事件/宏观**。图里只有单个 technical agent。
- **回测**(`services/backtest/midas_ch_loader.py`):**只 SELECT ClickHouse `kline` 表 OHLCV**,纯价格。
- **前端行情页**:只调 `/v1/{cn,us,hk}/board·overview·search`、`/v1/market/kline·symbols`、`/v1/overview/global`、`/v1/crypto/*`、`/v1/analysis/{chan,decision-card,strategy-*}`——**全是价格/技术/分析端点,无 news/calendar/event 端点**。

### 1.3 落库 + 新鲜度基建(★这是复用价值所在)

- **落库,非实时拉**:四市场统一落 ClickHouse `kline` 表(`market` Enum 区分)+ 各 snapshot 表;读端 cache-aside(先读 CH,缺/stale 才回源)。
- **Celery beat 定时采集**(`apps/worker/config/celery_config.py`):各市场分钟错峰(A股 15:30 收盘更新 + 盘中扫、美股夜间扫、港股 16:30、加密 7×24 每 1~30min 分任务)。
- **三重新鲜度监控**(现成范式):
  1. `services/kline_freshness.py` — cache-aside 门控(行数不足或末根 stale 才回源)。
  2. **`services/ingest_monitor.py` — 纯读各表 `max(ts)` 判 stale**,显式目标「防 BTC 价错 11 天无人发现再演」。★**这正是本任务要求的「看 max(ts) 推进,别看数据存在」范式,已在生产运行**。
  3. `apps/worker/tasks/system_health.py` — 每 20min 查 CH 磁盘超阈 TG 告警 admin。

---

## ② 金十补的空白(具体)

**全仓穷举 grep(api+web+docs,含 `财经日历/快讯/economic calendar/earnings calendar/FOMC/CPI/非农/央行/数据发布/jin10/金十/news feed`)= 零命中财经事件层。**

命中的两个 "calendar" 都是**交易时段/交易日历**,不是财经事件:
- `services/market_calendar.py` = 盘前/盘中/盘后状态机 + 硬编码节假日;
- CH `market_trade_calendar` = A股交易日判定(今天是否开市)。

最接近「宏观/情绪」的只有加密的 **FGI** 和 **CoinGecko dominance** —— 是**指标聚合值,不是事件/日程**,且仅加密侧。

`schemas/ai_decision.py` 的 `AgentScore` 枚举**预留了 `news`/`fundamental`/`onchain`/`sentiment` 四个维度,但全未实现**;crypto system prompt 甚至明说「链上数据…当前 input 暂不含,M2+ 才接」。

**→ 金十能补的空白(精确)**:
1. **7×24 快讯(flash)**:实时市场突发新闻(央行表态/地缘/突发数据/公司公告),分市场快讯(市场/期货/商品外汇/A股)。
2. **财经日历(calendar)**:全球主要经济体经济指标发布时间表(非农/CPI/FOMC/利率决议/GDP…)——**「未来 N 天有什么大事」这类前瞻信息,Midas 现在一概拿不到**(LLM 知识冻结在训练日,更看不到今天的日历)。

**不补的(已有,别重复接)**:金十的大宗商品/外汇**报价**与现有 `/v1/overview/global`(`global_overview_scan`:指数/商品/外汇/债券)**功能重叠**,价值不在再加一路价格源。

---

## ③ 商用合规判定

| 维度 | 结论 |
|---|---|
| **资质** | 金十是**央网信办首批 20 家金融信息服务备案机构**(2022-01),官方合规源 ✓ |
| **能否商用** | 能,但**须付费授权**。REST 开放平台(open.jin10.com)「内部使用版」按板块授权,**最低 2000 元/年/板块**;提供 15 天免费试用。MCP 平台(mcp.jin10.com)登录管理 TOKEN,有免费额度(精确限频未公开)。 |
| **代价** | ① **钱**:按接的板块数 × 2000 元/年起(需 Hans 定预算);② **授权范围**:「内部使用版」通常限内部/展示,**对外分发/二次销售数据需单独商用授权**——若 Midas 只把快讯/日历作为**决策卡背景 context 内部消费**(不把金十原文当独立付费商品转卖),风险低,但**签约前须向金十确认授权条款覆盖「SaaS 产品内展示」**。 |
| **红线契合** | 金十只提供**事件/日历/资讯数据**,不提供交易信号——与 Midas「仅供参考、不构成投资建议、永不真实下单」红线**天然兼容**,不引入荐股/信号风险。 |

★**精确免费额度/限频/字段深度**:公开文档太薄,查不实。**需 Hans 申请免费 token 实测**(15 天试用足够验证)——见 §5 的实测清单。

---

## ④ 推荐接入形态:REST API 直连(不用 MCP 进 agent)

金十提供两种形态:

| 形态 | 是什么 | 适合 |
|---|---|---|
| **REST API**(open.jin10.com) | `flash`(快讯)/`calendar`(财经日历)/`symbols`(报价)/`news`(资讯)四类端点,核心地址 `open-data-api.jin10.com/data-api/flash`,secret-key 鉴权 | **后端数据管道**(拉→落库→喂) |
| **MCP**(mcp.jin10.com) | 标准 MCP 协议,工具 `get_quote`/`get_kline`/`list_news`/`search_news`,登录管 TOKEN + AI 应用 JSON 配置 | **AI agent 运行时主动查询** |

**推荐:REST API 直连做后端数据管道,不把 MCP 塞进生产 LangGraph agent。理由:**

1. **契合现有范式**:Midas 已有「Celery 定时拉 → 落 ClickHouse → cache-aside 读 → `ingest_monitor` 看 `max(ts)` 保鲜」的成熟基建(§1.3)。新增一个事件源直接复用这套,零架构发明。
2. **可控/可缓存/可监控**:数据管道模式下,快讯/日历落库后可去重、可算新鲜度、可被回测/多个 agent 复用;**MCP 是 agent 运行时实时调用**,每次决策卡都打一次外部 API = 增加运行时外部依赖 + 延迟 + 限频风险 + 无法监控新鲜度,且同一份日历被 N 次决策卡重复拉。
3. **红线隔离更干净**:数据管道把金十数据「落库→格式化→作为 prompt 背景 context」,注入点单一可审计;MCP 让 LLM 自主决定何时调什么工具,注入面更宽、更难审计。
4. **MCP 不是没用**——它适合未来「用户在沙盘里主动问 AI:茅台最近有什么消息?」这类**交互式主动查询**功能。但**事件感知层(给决策卡自动注入今日日历+近期快讯)不需要 MCP,REST 管道更稳**。

---

## ⑤ 最小接入方案

**只接 `flash`(快讯)+ `calendar`(财经日历)两类,不接报价(§2 已有重叠)。**

### 5.1 接什么

```
金十 REST API
  ├─ /data-api/flash?flash_type=...   → 快讯(分市场:市场/期货/商品外汇/A股)
  └─ /data-api/calendar?...           → 财经日历(未来 N 天经济指标发布日程)
```

### 5.2 怎么落库(复用现有范式)

1. 新增 `services/data_sources/jin10_source.py`,继承 `BaseDataSource`(同其它四源,secret-key 从 `.env` 读,**绝不进前端**)。
2. 新增 ClickHouse 两表(或 PG,事件量小可 PG):
   - `econ_calendar`(事件时间/国家/指标名/前值/预期/实际/重要度,主键去重)
   - `market_flash`(快讯 ts/市场/正文/重要度,主键去重)
   - ★所有时间戳 **tz-aware 落库**(CLAUDE.md 项目铁律:clickhouse-connect 绝不传 naive datetime)。
3. Celery beat 加两个任务:
   - `jin10_calendar_refresh` 每日 1~2 次(日历是前瞻日程,低频)
   - `jin10_flash_scan` 每 3~5min(快讯要新鲜,分市场错峰,同 §1.3 防限流范式)

### 5.3 怎么喂(注入决策卡)

在 `_node_data_prepare` / `agents/technical.py::_format_snapshot` 增加一段**事件背景 context**:
- **该品种所属市场 + 未来 3~7 天的财经日历重大事件**(如「6/12 20:30 美国 CPI」);
- **近 24h 相关快讯摘要**(按市场/重要度过滤,取 top N,防 prompt 爆炸)。
- ★注入格式:**只陈述事件与时间,标注来源「金十·YYYY-MM-DD HH:MM」,不做因果预测**(契合 prompt 机器证明红线:禁改价、禁祈使、禁编造)。
- 未来可点亮 `AgentScore.news` 维度(枚举已预留),让「事件面」成为决策卡一个显式打分维度。

### 5.4 怎么保鲜(★看 max(ts),不看数据存在)

- **`ingest_monitor.py` 加 `econ_calendar` / `market_flash` 两表的 `max(ts)` 监控**(复用现成 `max(ts)` 范式):
  - 快讯:阈值 = 采集频率 ×3(如 5min×3=15min 无新快讯 → 告警);
  - 日历:日历是未来日程,监控口径改为「**采集任务 last-run 成功时间**」而非 `max(事件ts)`(事件 ts 在未来,不能用它判 stale)。★这是与 K线不同的关键点:**日历的「新鲜」= 最近成功刷新过,不是最新事件时间**。
- 决策卡消费前先查新鲜度门控:事件数据 stale → **降级为「事件面暂不可用」占位,绝不喂过期日历**(CLAUDE.md 红线:接不上一律占位,绝不伪造)。

### 5.5 分阶段(降低承诺)

- **P0 验证价值(免费,不花钱)**:Hans 申请 15 天试用 + 免费 token → 只接**财经日历单板块** → 注入决策卡 → 看 AI 输出是否真的因「知道今晚有 CPI」而更有用。**值 → 再谈付费扩板块;不值 → 零成本退出。**
- **P1 正式**:付费授权需要的板块(快讯+日历,按 A股/美股/加密覆盖需求选板块)→ 全量落库 + 新鲜度监控 + 决策卡注入 + 点亮 `news` 维度。

---

## ⑥ 一句话判断

**值得做:Midas 现在完全没有事件/宏观层,决策卡纯靠 K线+技术指标+缠论,连「今晚有没有非农」都不知道;金十的快讯+财经日历正好补这块唯一空白,且落库/Celery/`max(ts)` 新鲜度基建已现成可直接复用,增量成本低、合规源、与虚拟盘红线天然兼容——建议先用 15 天免费试用+免费 token 接财经日历单板块实测决策卡增益,验证有价值再谈 2000 元/年/板块 的付费扩板块。**

---

## 附:需 Hans 决策/操作的事项

1. **[需 Hans 操作] 申请金十免费 token**(账号登录级操作,凭证不进对话)——用于实测下列公开文档查不实的项:
   - 免费额度精确限频(QPS/日调用上限);
   - `flash`/`calendar` 端点真实返回字段与粒度;
   - 历史深度(能拉多久前的快讯/日历)。
2. **[需 Hans 拍板] 预算**:先免费验证(0 元)→ 值得再定接几个板块(2000 元/年/板块起)。
3. **[需 Hans 确认] 授权条款**:签约前向金十确认「内部使用版」授权覆盖「Midas SaaS 产品内向注册用户展示事件/日历 context」,避免踩「对外分发需单独商用授权」的坑。
4. **[非阻塞] 红线**:接入后事件数据仅作决策卡背景 context,**不改 AI 输出免责语、不接真实交易、secret-key 仅进 `.env` 不进前端**。

---

*调研信息来源:内部 grep 审计(midas-i18n-fe/main,只读)+ 金十官方公开信息([open.jin10.com](https://open.jin10.com/) · [mcp.jin10.com](https://mcp.jin10.com/app/) · 央网信办备案公示 · BigQuant/公开字段文档)。精确限频/字段以 Hans 申请 token 后实测为准。*
