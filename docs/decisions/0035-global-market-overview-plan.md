# ADR 0035 · 全球指标概览模块 · 实施细案

- 状态:**Proposed(待审)**
- 关联:`docs/research/global-market-overview-feasibility.md`(正文 + 附录 D 地图)· 复用 0023 阶段③ 市场首页基建
- 决策背景:回测暂不做 / 港股暂停等延迟补测 → 集中做全球指标概览。
- 模块目标:**一页全球核心市场指标概览**。Web 宽屏 = 左世界地图(各市场标关键指标)+ 右指标列表;移动端 = 富途式卡片网格。
- 核心策略:复用 `market_index_snapshot`(String 市场列 · **零迁移**)+ 复用通用 yfinance 采集器(配 symbol 清单)· 免费源起步 · 15min 延迟可接受。
- **★ 红线**:**纯只读展示、不涉及交易**(独立于交易维度 cn/us/crypto/hk,绝不碰虚拟交易红线)· 先采 CH 再展示 · 不碰现有市场逻辑 · TG 零回归。

---

## 0. 既有基建(复用面 · 已核实 file:line)

| 资产 | 位置 | 复用方式 |
|---|---|---|
| `market_index_snapshot` 表(market **String**) | `clickhouse-init.sql:210` | **零迁移装全品类**(可选加 category/unit 列) |
| 通用指数采集 `_fetch_indices_sync` | `us_source.py:124` | `yf.Ticker(sym).history()` 对任意 ticker 通用 → 泛化成 overview 采集 |
| 写入 / 读取层 | `clickhouse_market_home.py`(`insert_index_snapshots` / `select_latest_indices`) | 仿写 overview 版 |
| 采集 worker + beat 模式 | `market_home_ingest.py:91`(`us_index_scan`)+ `celery_config.py` | 克隆出 `global_overview_scan` |
| 指数卡 `IndexCard`(网格) | `market-home-page.tsx:131`(**内联**) | **抽成共用组件**后两处复用 |
| 共用 UI | `Panel`/`StatusPill`/`EmptyState`/`LoadingNote`/`TopNav` | 直接用 |
| 响应式断点 | Tailwind `md:`/`lg:`(全站在用) | 宽窄屏分流 |

★ **解耦点**:overview 不复用 `IndexQuote.market: MarketKind`(cn/us/hk · `market_home.py:35` 太窄)→ **新建独立 schema `OverviewQuote`(`market: str` 自由地区码 + category + unit)**,与交易维度 / 市场首页 MarketKind **完全解耦**。`_fetch_indices_sync` 里 `market="us"` 是硬编码(`us_source.py:150`)→ overview 采集走**地区感知**的新方法。

---

## 1. 数据层(轻)

### 1.1 复用 `market_index_snapshot` + 幂等加 2 列

`market_index_snapshot` 当前列:`market String, symbol, name, ts, last_point, prev_close, change_point, change_pct, ingested_at`(ReplacingMergeTree · PARTITION toYYYYMM(ts) · ORDER (market,symbol,ts) · TTL 7d)。

**加 2 列(幂等 · 非破坏 · 对齐 init.sql:40 同款)**:
```sql
ALTER TABLE market_index_snapshot ADD COLUMN IF NOT EXISTS category String DEFAULT '';
ALTER TABLE market_index_snapshot ADD COLUMN IF NOT EXISTS unit     String DEFAULT 'point';
```
- `category`:分组键 = `index`(环球指数)/ `index_future`(指数期货)/ `commodity`(商品)/ `forex`(外汇)/ `bond`(债券收益率)/ `crypto`(加密)。
- `unit`:显示单位 = `point`(点位)/ `price`(价格)/ `rate`(汇率)/ `yield_pct`(收益率%)。
- `market`(沿用 String)→ overview 行存**地区码**(`us`/`cn`/`jp`/`hk`/`de`/`uk`/`global`/`fx`/`crypto`)· **同时是 Phase B 地图定位键**。
- **同步**:`init.sql` + `apps/worker/ch_schema.py` **两处 DDL 必须一致**(`clickhouse-init.sql:203` 已有此约束注释)· 老库靠幂等 ALTER,新库靠 init.sql。
- **零回归**:现有 cn/us 市场首页的索引行 `category=''` 默认值,市场首页读 `WHERE market IN ('cn','us')` 路径**不变**;overview 读 `WHERE category != ''`(或 category IN 概览分类),两套数据同表共存不打架。

> 备选(纯零迁移):不加列、用 `market` 列重载分类(`market='commodity'` 等)。**不推荐**——丢失「地区码给地图定位」的能力,且语义混。**推荐加 category/unit 列。**

### 1.2 采集:全球 symbol 清单 + 通用 yfinance 采集克隆

- 新建 `app/services/global_overview_config.py`:`GLOBAL_OVERVIEW: tuple[tuple[str,str,str,str,str], ...]` = `(yf_symbol, 名称, 地区码, category, unit)`。
- 采集器:复用 `_fetch_indices_sync` 的通用 `yf.Ticker(sym).history(period="5d", interval="1d")` 取 last/prev → 新方法 `fetch_overview_quotes(targets) -> list[OverviewQuote]`(地区感知,`market=地区码` + category + unit),放 YFinance 源或薄新类。
- worker:`apps/worker/tasks/` 新增 `global_overview_scan`(克隆 `us_index_scan` · `market_home_ingest.py:91`)→ `insert_overview_quotes`。
- beat:全球市场跨时区 → **周期性采**(如每 10min · 24/5)比按市场时段简单;15min 延迟可接受(决策已定)。频率待产品负责人定。
- 加密:复用现有加密行情(ccxt / `crypto_market_overview` 表)取 BTC/ETH,或并入 overview 采集(yfinance 也有 `BTC-USD`)——口径待定。

### 1.3 ★ 首批建议 symbol 清单(★全部待产品负责人核 · 国家/品类取舍)

| category | symbol(yfinance)· 名称 · 地区码 |
|---|---|
| **index** 环球指数 | `^GSPC` 标普500 us · `^IXIC` 纳斯达克 us · `^DJI` 道琼斯 us · `^N225` 日经225 jp · `^HSI` 恒生 hk · `000001.SS` 上证 cn · `^GDAXI` 德国DAX de · `^FTSE` 英国富时100 uk(可选 `^KS11`韩 / `^STI`新 / `^BSESN`印 / `^FCHI`法) |
| **index_future** 指数期货 | `ES=F` 标普期货 · `NQ=F` 纳指期货 · `YM=F` 道指期货(地区 us) |
| **commodity** 商品 | `GC=F` 黄金 · `SI=F` 白银 · `CL=F` WTI原油 · `BZ=F` 布伦特 · `HG=F` 铜 · `NG=F` 天然气(地区 global) |
| **forex** 外汇 | `DX-Y.NYB` 美元指数 · `JPY=X` 美元日元 · `EURUSD=X` 欧元美元 · `GBPUSD=X` 英镑美元 · `CNY=X` 美元人民币(地区 fx) |
| **bond** 债券收益率 | `^TNX` 美债10年 · `^TYX` 美债30年 · `^FVX` 美债5年(可选 `^IRX` 13周)(地区 us · unit=`yield_pct`) |
| **crypto** 加密 | `BTC` · `ETH`(复用现有加密通道)(地区 crypto) |

> ★ 这是**最佳努力的建议清单**,具体放哪些国家指数 / 哪些商品 / 哪些外汇对,**待产品负责人核定**。

### 1.4 ★ 不碰交易维度
overview 行的 `market` 是**地区码**(us/jp/hk/de/global/fx/crypto),**不是**交易 `Market` Literal(cn/us/crypto/hk)。全球指标**只读、不可交易**:不建虚拟钱包、不接撮合、不进 `_source_for`/`_ALL`。`schemas/market.py` 的 `Market` / `models/virtual.py` 的钱包**一字不动**。

---

## 2. 后端 API(只读)

- 新建 `app/api/v1/overview.py`:`GET /api/v1/overview/global` → 读 `market_index_snapshot`(category != ''),按 category 分组返回各 symbol 最新快照。
- schema `app/schemas/overview.py`:
  - `OverviewQuote`(market:str 地区 · category:str · unit:str · name · last_point · prev_close · change_point · change_pct · ts)
  - `OverviewCategoryGroup`(category · label · items: list[OverviewQuote])
  - `GlobalOverviewResponse`(groups: list[OverviewCategoryGroup] · as_of)
- 读层 `clickhouse_overview.py`:`select_latest_overview()`(仿 `select_latest_indices` · 取每 symbol 最新 ts 行 · FINAL)。
- 注册:`api/v1/__init__.py` 加 `router.include_router(overview_router)`(对齐现有 cn/us router 注册)。
- 只读 · 不写 · 不碰交易。

---

## 3. 前端(务实路径 · 先基座后地图)

### ★ 阶段 A:响应式卡片基座(能上线)
- 新页 `/global`(或 `/global-market` 对齐 `/cn-market` 命名 · 待定)· `app/global/page.tsx`。
- **抽 `IndexCard`** 成共用组件(现内联于 `market-home-page.tsx:131`)→ overview 页按 category 分 section(环球指数 / 期货 / 商品 / 外汇 / 债券 / 加密),每组一个卡片网格(`grid grid-cols-2 md:grid-cols-4`)· 涨红跌绿(`text-up`/`text-down`)· 按 `unit` 显示单位(点位/价格/汇率/收益率%)。
- API client `lib/api/overview.ts` + hook(`useQuery` · staleTime 30s · refetchInterval 60s · 对齐 market-home)。
- 状态:`LoadingNote` / `EmptyState`(无数据态)。
- 入口:TopNav / 首页加「全球概览」入口(**不进 MarketSwitcher** · 那是交易市场切换)· 入口位置待产品负责人定(可设新落地页)。
- 免责:页脚「行情仅供参考」。
- **宽窄屏都能用**(纯卡片网格已响应式)· 快速出效果 · 独立可上线。

### ★ 阶段 B:世界地图视觉增强(fast-follow · 后置不阻塞)
- 宽屏(lg+):两栏 `lg:grid lg:grid-cols-[2fr_1fr]` —— 左 = 地图(环球指数按地区码定位标指标)· 右 = 指标列表(商品/外汇/债券等非地理品类)。
- 窄屏(<lg):地图 `lg:hidden`,回退**阶段 A 的卡片网格**(降级免费)。
- 地图组件:`next/dynamic(() => import(...), { ssr:false })` 懒加载 → 移动端不下发地图 bundle。读**同一份** overview 数据。
- **地图选型(待产品负责人定)**:
  - **A 风格化手绘 SVG**:视觉灵魂最强 · 品牌可控 · 东亚标签不重叠 · 零库 · **但设计主导**(要先有好 SVG/布局设计)。
  - **B react-simple-maps + 重风格化**:库现成开发快 · 地理精确 · **但东亚标签重叠要专门处理(引线/碰撞)** · 灵魂稍弱。
  - ★ **门槛在设计不在技术** · 待产品负责人定**选型 + 提供/确认设计方向**(地图风格 / 市场定位布局)。本阶段先不锁。

---

## 4. 红线(本模块全程守)
- **纯只读展示 · 不涉及交易**:不建仓 / 不下单 / 不碰 `virtual_trading` / 不进交易 `Market` 维度 → 比港股还安全。
- **先采 CH 再展示**:采集 worker → `market_index_snapshot` → 只读 API → 前端(现有 market-home 同模式)· 不在展示时打实时上游。
- **不碰现有市场逻辑**:cn/us/crypto/hk 交易 + cn/us 市场首页读路径**零改动**(overview 用新 category 行 + 新读路径,不动旧路径)。
- **TG 零回归**:不碰 bot(replies/renderers)· golden 天然不受影响。
- **前端 build 过** · ruff/mypy/pytest 过。

---

## 5. 分阶段(每步 feature 分支 + 审 + 验收 + 合 main)

### 阶段 A · 数据采集 + 只读 API + 响应式卡片基座(★ 能上线)
| 子步 | 范围 | 风险 | 验收点 |
|---|---|---|---|
| A1 · CH 列 + DDL 同步 | `market_index_snapshot` 加 category/unit(init.sql + ch_schema.py 幂等 ALTER) | 低(加列非破坏) | 列存在 · 现有 cn/us 市场首页零回归 |
| A2 · 配置 + schema | `global_overview_config.py` 首批清单 + `schemas/overview.py` | 低(纯新增) | mypy 过 |
| A3 · 采集器 + worker + beat | `fetch_overview_quotes` + `global_overview_scan` + beat 周期 | 低 | 跑一次 → CH 有各品类最新行 |
| A4 · 只读 API + 读层 | `overview.py` `/overview/global` + `clickhouse_overview.py` + 注册 | 低(只读) | `curl /overview/global` 返分组数据 |
| A5 · 前端卡片页 | 抽 `IndexCard` + `/global` 页 + 分组网格 + API hook + nav 入口 | 低 | 真机 `/global` 显示各品类实时卡片 · build 过 |
| A6 · 自验 + push | ruff/mypy/pytest + tsc/lint/build + push feature | — | 全绿 + 真机抽查 |
- **工作量**:后端**小**(配置+采集克隆+只读API+加列)· 前端**中**(抽卡 + 分组页 + hook)· **可独立上线**。

### 阶段 B · 世界地图视觉增强(fast-follow · 不阻塞 A)
| 子步 | 范围 | 验收点 |
|---|---|---|
| B1 · 选型 + 设计方向(★待产品负责人) | 定 A 手绘 / B react-simple-maps + 设计风格 | 选型拍板 |
| B2 · 地图组件 | 懒加载 · 地区码定位 · 涨跌上色 · 读同一数据 | 宽屏显示地图标指标 |
| B3 · 宽屏两栏布局 + 窄屏卡片回退 | `lg:grid-cols-[2fr_1fr]` 地图+列表 · `lg:hidden` 回退卡片 | 宽屏地图+列表 / 窄屏卡片 · 响应式正确 |
| B4 · 自验 + push | tsc/lint/build + 真机宽窄屏抽查 | 全绿 |
- **工作量**:前端**中**(地图唯一实质新组件 · 有现成库非从零)· **真正成本在设计** · 后端 **0**(读同一 API)。

---

## 6. 需产品负责人拍板
1. **首批 symbol 清单 + 品类范围**(§1.3 建议清单核定 · 放哪些国家指数 / 商品 / 外汇对 / 要不要指数期货)。
2. **★ 地图选型**(风格化手绘 vs react-simple-maps)+ **设计方向/资源**(门槛在设计)。
3. **债券收益率展示口径**(收益率% · 涨跌用 bp 还是 %)。
4. **要不要 K 线下钻**(点指数看图 → 触 `kline` Enum8 迁移;**概览本身不需要**,默认不做)。
5. **入口位置**(TopNav「全球概览」/ 首页 / 是否设为默认落地页)。
6. **采集频率 + 时区策略**(全球跨时区 · 周期性采 vs 按市场时段 · 默认周期性每 10min)。
7. **加密数据口径**(复用现有 ccxt 通道 vs yfinance `BTC-USD`)。

---

> 待审重点:**§1 数据层(零迁移复用 + 加 category/unit 列)** · **§1.4 不碰交易维度(独立红线)** · **§3 前端务实路径(先卡片基座、地图后置)** · **§5 分阶段(A 能独立上线)**。
> 审过 + 拍板(尤其 §6 的清单 + 地图选型)→ 按**阶段 A** 先写代码。本轮只出细案。
