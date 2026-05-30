# 调研:全球核心市场指标概览页 · 可行性 + 工作量评估

- 状态:**纯调研 · 远期规划(港股之后)· 不写代码**
- 产品设想:一页「全球核心市场指标概览」(模仿富途那页),覆盖 环球指数 / 指数期货 / 商品期货(原油·黄金·白银)/ 外汇 / 债券收益率 / 加密,让用户快速看全球市场动态。
- 调研范围:A 代码侧改造范围(可给准)+ B 数据源类型框架(理论 · 具体选型 ★待产品负责人)。
- 证据:均带 `file:line`。

---

## TL;DR(一句话结论)

**比港股接入还轻。** 概览是「只读展示、不交易」,而项目**已经有一条几乎现成的管线**:`fetch_indices`(通用 yfinance ticker 抓取)→ `market_index_snapshot`(品类列是 **String 不是 Enum8** → 加任意新品类**零迁移**)→ 只读 API → 前端**指数卡网格**(已存在)。
新增主要是**配置(symbol 清单)+ worker 任务克隆 + 一个只读 API + 前端布局**,不碰虚拟交易红线、不碰 CH 迁移。

---

# A. 代码侧(可给准)

## A1. 数据模型:现有表能不能装下新品类?

### ★ 关键发现:`market_index_snapshot` 已是「通用报价快照」表,品类列是 String

`docker/clickhouse-init.sql:210` 的 `market_index_snapshot`:
```
market String,          -- ★ String!不是 Enum8(对比 kline:7 的 market Enum8)
symbol String,          -- '^DJI' / 'sh000001'
name String,            -- '标普500'
ts, last_point, prev_close, change_point, change_pct
```
- `market` 是 **自由 String**(`init.sql:211`),所以写 `'jp'`(日经)/ `'global'` / `'commodity'`(黄金原油)/ `'fx'`(美元日元)/ `'bond'`(美债)等**任意新品类 = 零迁移**(对比港股 hk 因 `kline.market` 是 Enum8 才要手动 ALTER)。
- 表结构 `(name, last_point, prev_close, change_point, change_pct)` 本质就是「**一个数值 + 昨收 + 涨跌**」——而指数(点位)、期货/商品(价格)、外汇(汇率)、债券(收益率%)、加密(价格)**全是这个形状**。→ **一张现成表装下全部品类。**

**结论 A1**:做「概览页」(只展示当前值 + 涨跌,不要 K 线)→ **`market_index_snapshot` 近乎零改造能装下所有品类**。唯一可选增强:加一个 `category` / `unit` 列(用 `init.sql:40-42` 同款 `ADD COLUMN IF NOT EXISTS` 幂等加列 · 非破坏性)区分显示单位(点位 / 价格 / 收益率%)——纯展示用,不加也能跑(品类靠 symbol 前缀判断)。

### 若要 K 线下钻(可选二期 · 概览本身不需要)
点进期货/外汇/债券看 K 线图,才需要碰 `kline` 表:`kline.market` 是 `Enum8('cn'=1,'us'=2,'crypto'=3[,'hk'=4])`(`init.sql:7`)→ 加新品类需要**港股那种 metadata-only ALTER**(已验证可行,见 ADR 0034a),或复用 `instrument Enum8('spot','perp')`(`init.sql:41`)扩 index/future/fx/bond。**但概览页只展示快照,不需要 K 线 → 这是独立的二期,不阻塞 MVP。**

## A1b. 市场维度抽象:要不要新维度?

- 现有「**交易市场**」维度 cn/us/crypto/hk(`schemas/market.py:15` `Market` Literal)是**绑死虚拟交易红线**的——每个 market 配了币种(`models/virtual.py:79` `MARKET_CURRENCY`)、钱包、撮合引擎。
- 全球指标(黄金/美元日元/美债)**不该塞进这个交易维度**:它们是只读展示、**不交易**,塞进去会污染交易抽象(凭空多出「黄金钱包」)。
- ✅ **好消息**:`market_index_snapshot` 已经**独立于交易维度**(它的 `market` 是自由 String、跟 `Market` Literal 无关)。所以概览页用**新的「展示品类」维度**(index/futures/commodity/forex/bond),**与交易 market 天然解耦**——而且这个解耦在现有表里**已经成立**,不用新建抽象。

## A2. 前端:能复用多少?

概览页 = 卡片网格(类似富途)。现有 `components/market-home/market-home-page.tsx` **已经有指数卡网格**:
- `市场首页:90` `grid grid-cols-2 md:grid-cols-4` 的 `<Panel>` 卡(`IndexCard:131`),展示 `last_point` + `change_point` + `change_pct`,涨红跌绿(`text-up`/`text-down`)。**这正是概览页要的卡。**
- 共用组件库齐全且已在用:`Panel` / `StatusPill` / `EmptyState` / `LoadingNote`(`components/ui/`)+ `TopNav` + `MarketSwitcher`。
- 另有 `/crypto-market`、`/cn-market`、`/us-market` 三个同款网格页作参考。

**结论 A2**:前端**高复用**。概览页主要是「多分组的指数卡网格」——每组(环球指数 / 期货 / 商品 / 外汇 / 债券 / 加密)一个 section,复用 `IndexCard`。前端工作量 = 页面布局 + 分组标题 + 数据 hook,**不是从零造组件**。

## A3. 结论:改造范围 + 复用度

| 层 | 现状 | 概览 MVP 要新增 |
|---|---|---|
| **CH 表** | `market_index_snapshot`(String 品类 · 通用报价形状)✅ | **零迁移**(可选加 category 列) |
| **采集源** | `fetch_indices`(通用 yfinance ticker 抓取 · `us_source.py:124`)✅ | 0 行新采集代码(见 B1) |
| **采集 worker** | `us_index_scan` / `cn_index_scan`(`market_home_ingest.py:91/69`)✅ | 克隆任务 + 新 symbol 清单 |
| **读写层** | `insert_index_snapshots` / `select_latest_indices`(`clickhouse_market_home.py`)✅ | 复用 / 微扩 |
| **API** | `/cn/overview`、`/us/overview`(`api/v1/cn.py`、`us.py`)只读 | **新增** `/overview/global` 只读端点 |
| **前端** | IndexCard 网格 + 共用组件 ✅ | **新增**概览页布局 + 分组 + hook |

**改造范围**:后端 **小**(配置 + worker 克隆 + 1 个只读 API + 可选加列),前端 **中**(复用网格 + 组织分组)。
**复用度**:**很高**(数据层 ~80% 现成,前端卡片现成)。**比港股接入还轻**——港股要碰交易维度 + Enum8 迁移;概览只读、用 String 表、零迁移、不碰交易红线。

---

# B. 数据源类型框架(理论 · 具体选型 ★待产品负责人)

## B1. ★ 最大发现:现有免费源已覆盖大半

项目**已经用 yfinance 抓美股指数**(`market_home_config.py:14` `US_INDICES = ^DJI/^IXIC/^GSPC/^RUT`),而 `_fetch_indices_sync`(`us_source.py:124`)是**完全通用的 yfinance ticker 抓取**:`yf.Ticker(symbol).history(period="5d", interval="1d")` 取 last/prev close 算涨跌——**对任意 Yahoo ticker 都成立**。Yahoo ticker 命名空间覆盖(理论上加进 symbol 清单即可采):

| 品类 | Yahoo ticker 例子 | 备注 |
|---|---|---|
| 环球指数 | `^N225`(日经)`^HSI`(恒生)`^GDAXI`(德DAX)`^FTSE`(英) | 同 `^DJI` 套路 |
| 商品/期货 | `GC=F`(黄金)`SI=F`(白银)`CL=F`(原油)`ES=F`(标普期货)`NQ=F`(纳指期货) | `=F` 命名 |
| 外汇 | `JPY=X`(美元日元)`EURUSD=X` `GBPUSD=X` | `=X` 命名 |
| 债券收益率 | `^TNX`(美债10Y)`^TYX`(30Y)`^FVX`(5Y) | 值是**收益率%**(单位不同 → A1 的 unit 列处理) |
| 加密 | — | **已有**(ccxt/Binance + `crypto_market_overview` 表 `init.sql:153`) |

→ **全球概览的「指数/期货/商品/外汇/债券」大半,理论上用现有 yfinance 适配器 + 加 symbol 清单就能采,几乎不写新采集代码。** AKShare(已用)也覆盖 CN 指数 + 部分全球指数/期货/外汇(Sina/EM 通道)。

## B2. 数据源「类型」框架(★ 不点名供应商/价格 · 选型待产品负责人)

| 类型 | 特征 | 适用 | 商业信息 |
|---|---|---|---|
| **① 免费社区抓取型**(yfinance / AKShare 这一类) | 广覆盖、零成本、~15min 延迟、**非官方抓取**(上游改版会断)、有限流 | 概览 MVP 首选(**项目已用、已验证**) | 免费 |
| **② Freemium 聚合 API 型**(有免费档+付费档的金融数据聚合商这一类) | 接口干净稳定、免费档限流、实时/高频/历史深度要付费 | 概览要更稳/更全时 | ★ 哪家/多少钱/SLA **待产品负责人** |
| **③ 交易所 / 官方授权 feed 型** | 权威、低延迟,通常要授权/付费(尤其实时指数·期货) | 要真实时/合规时 | ★ 商业+合规 **待产品负责人** |
| **④ 政府 / 央行开放数据型** | 债券收益率这类:财政部/央行公布的收益率曲线,很多免费 | 国债收益率 | 渠道 **待产品负责人** |

> ★ **诚实标注**:具体供应商名、定价、稳定性 SLA 都是**商业信息,查代码查不出来**。以上只是「类型框架 + 各品类通常从哪类源来」,**选型留给产品负责人调研**。

## B3. 15min 延迟够不够(概览场景)?

**够用。** 理由:
- 概览**不是交易**,看的是大方向(今天哪个市场涨跌、谁强谁弱),延迟容忍度高。
- 现有 `us_index_scan` 就是基于 yfinance ~15min 延迟数据、交易时段每 2min 采一次(`celery_config.py` beat)——**已在跑、用户接受**。
- 秒级真实时只有**交易**才需要;概览不需要 → 可全程用免费源 + CH 缓存,**不破红线**。

---

# 红线(概览同样遵守)

- **只读已采 CH · 不打实时上游**:概览同样「采集 worker → `market_index_snapshot` → 只读 API → 前端」(现有 market-home 已是这模式,复用即可)。`market_home_ingest.py:15` 红线:worker 只 GET 行情 + INSERT CH,永不碰交易接口。
- **纯只读展示 · 不涉及交易**:概览不建仓位 / 不下单 / 不碰虚拟交易引擎 → **比港股还安全**(港股要碰交易维度)。
- **免责**:展示数据带「行情仅供参考」即可(非 AI/策略输出,但金融数据展示惯例加)。

---

# 分期建议(给产品负责人参考 · 非承诺)

1. **一期 MVP(轻 · 验证产品价值)**:用现有 yfinance/AKShare + `market_index_snapshot`,采「环球指数 + 商品 + 外汇 + 债券收益率」几十个 symbol,做一个只读概览页(复用 IndexCard 网格)。**零迁移、零新源、低成本。**
2. **二期(若免费源质量/延迟/稳定性不够)**:产品负责人评估付费源(类型②/③)。换源 = **加一个新 source 适配器**,采集 worker / CH 表 / 前端**都不动**(现有 `BaseDataSource` 抽象支持)。
3. **三期(若要 K 线下钻)**:`kline` 加品类(Enum8 ALTER · 港股同款 · 已验证可行)。

---

# 待产品负责人拍板(本调研给不出的)
- **具体数据源选型**(免费源够不够 / 要不要上付费聚合源 / 哪家)——商业信息。
- **品类范围 + 每类放几个 symbol**(环球指数放几个国家?商品放哪几个?)——产品取舍。
- **债券收益率单位/口径展示**(收益率% vs 价格)——展示设计。
- **要不要 K 线下钻**(决定是否触 `kline` Enum8 迁移)——产品深度取舍。

> 本调研只回答「代码侧能不能做、改多大、复用多少」(可给准)+「数据源有哪些类型、各品类通常从哪类源来」(理论框架)。具体选型 / 定价 / 范围留给产品负责人。
