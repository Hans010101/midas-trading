# ADR 0035 · 全球指标概览模块 · 实施细案

- 状态:**阶段A 已实施并上线**(2026-05-30 · merge `8fb3b30` + hotfix `0ee1d8a` · 部署 run 26685966333 绿 · prod `/api/v1/overview/global` 200 实测有数据)· 阶段B(地图)待开工
  - 阶段A 落地:CH 幂等加 category/unit 列 · yfinance 采集(每 10min · 20 标的)+ 加密复用 ccxt · 只读 API `/overview/global` · 前端 QuoteCard 抽取 + `/global` 响应式卡片页 + 切换器「全球」入口 + 默认落地页改 `/global`(四市场零回归实证)。
  - ⚠️ 阶段A 上线后真机抽查翻车 2 处(已修 · 详见文末「阶段A 实施记录」):① 读路径误传 ClickHouseClient 包装层(应传 `._client`,沿用 cn/us 约定)② category/unit 列只靠 worker `worker_ready` 信号建 → 跨服务竞态 → 改 API lifespan 自保幂等建列。
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

---

## 阶段A 实施记录(2026-05-30 · 已上线)

落地版本对 §6 拍板做了 1 处收窄:首批清单 = 20 个 yfinance 标的(8 指数 / 5 商品 / 4 外汇 / 3 债券)+ 2 加密(BTC/ETH),**无指数期货 / 无天然气 / 无英镑**(产品负责人拍板收窄版)。债券 unit=yield_pct 涨跌 bp;加密复用 ccxt;入口设为默认落地页 `/global`。

### ⚠️ 上线后真机抽查翻车 2 处(均「接缝处必有翻车」· 模块单测全过但集成层没测 · 0002 教训)

合 main 部署绿、容器重建 healthy,但真机抽查 `GET /api/v1/overview/global` 返 **500**(四市场 + `/global` 页壳都正常)。两个根因叠加:

1. **读路径误传包装层**:`ClickHouseClient`(`app.state.clickhouse`)是包装类,**不暴露通用 `.query()`**;既有 cn.py/us.py 约定是把 `ch._client`(底层 `AsyncClient`)传给 service 函数。overview.py 直接传了 `ch` → `client.query(...)` AttributeError → 500。**根因**:read 路径只测了 config/schema + 裸 SQL,从没走真实 wrapper 的集成测试。**修**:`select_*_overview(ch._client)`。
2. **schema 依赖赌 worker 时序**:`category`/`unit` 列原本只靠 worker `worker_ready` 信号 `ensure_crypto_ch_tables()` 建 → 跨服务竞态(worker 未起 / DDL 列表中途某条失败会 abort 整个循环)→ API 查 `category` 列 CH Code 47 UNKNOWN_IDENTIFIER → 二次 500。**修**:API lifespan 自保幂等 `ensure_overview_columns()`(`ADD COLUMN IF NOT EXISTS` · 吞异常不阻断启动)——**reader 自己保证 schema 依赖,不赌别的服务时序**。

**修复闭环**(hotfix `0ee1d8a`):补回集成测试(真实 wrapper→`._client`→读路径打本地 CH + 真实端点函数返合法响应)· 全量回归 540 passed · 部署 run 26685966333 绿 · prod 端点转 200 且有实数据(标普/纳指/道指…)。

> 教训沉淀:**只读端点接 CH 必须走 `ch._client`(包装层无通用 query);跨服务的 schema 依赖,消费方(API)自己 lifespan 幂等保证,绝不赌生产方(worker)信号时序。**

---

## 运维备注 · 扩市场后「首轮采集延迟」(2026-05-31 · 阶段B 迭代实证)

阶段B 迭代扩 4 市场(韩国KOSPI / 新加坡STI / 法国CAC / 澳洲ASX)上线后,真机抽查 `/global` 一度看不到新市场点 —— **不是 bug,是采集时序**,虚惊一场。沉淀如下,免得以后再扩市场又惊。

**机制**:`global_overview_scan`(Celery beat · 每 10 分钟 · 在 :00/:10/:20… 触发)抓全部 yfinance 代码(当前 24 个 · 约 78s)后才写进 `market_index_snapshot`。所以:
- **新增采集市场后,数据要等下一轮 scan 跑完才进库**;首轮跑完前 `/global` 地图/卡片上新市场暂无数据 = **正常**。
- 实证:阶段B 迭代部署 01:06 完成、worker 01:05 重建,首轮 scan 01:10 触发、**01:11:18 才写完** 12 指数。中间窗口查只看到上一轮的 8 个;写完后 prod API 立即返 12、地图立即 10 点(前端有数据就显示,MARKET_GEO 无需改)。
- 前端读 CH 现状,有数据即显示;**「API 不返回新市场」永远先怀疑采集没跑完,而不是前端**(API 返回 = 采到了 → 才是前端问题)。

**想立刻看效果**(不等 10 分钟):手动触发一轮,等约 90s:
```bash
docker exec midas-worker celery -A celery_app call tasks.market.global_overview_scan
```

### 只读诊断套路(查表 / 查日志 / 手动触发 · 全只读 · 不改库不改配置)

```bash
# 最简单:不进服务器,直接打 API 看指数组有几个、含不含新代码
curl -s https://api.midastrade.asia/api/v1/overview/global \
  | python3 -c "import sys,json;g=[x for x in json.load(sys.stdin)['groups'] if x['category']=='index'][0];print(len(g['items']),[i['symbol'] for i in g['items']])"

# 进服务器(/opt/midas)三连:
cd /opt/midas && source .env

# A) 查表:新市场进 CH 没?(有行=采到 · 空=没采到)
docker exec midas-clickhouse clickhouse-client \
  --user "${CLICKHOUSE_USER:-midas}" --password "${CLICKHOUSE_PASSWORD:-midas_dev}" --query "
  SELECT symbol, market, last_point, ts FROM market_index_snapshot FINAL
  WHERE category='index' AND symbol IN ('^KS11','^STI','^FCHI','^AXJO') ORDER BY symbol"

# B) 查 worker 采集跑没 + 写了几条(看到 overview written=20 = 成功 · N=12指数+5商品+4外汇+3债券,加密走另表不计)
docker logs --since 40m midas-worker 2>&1 | grep -E 'global_overview_scan|overview written'

# C) 手动触发一轮(只是提前跑采集 · 不改库结构/配置)· 等 ~90s 再跑 A)
docker exec midas-worker celery -A celery_app call tasks.market.global_overview_scan
```
> CH 是有状态容器,以上命令全只读,绝不动数据卷。`market_index_snapshot` 有 `TTL 7 DAY`,采到的行会留 7 天,期间某轮 scan 偶发漏采也不会立刻消失。

---

## 修复 + 运维记录 · 精选扩充 59 指标(2026-05-31 · 已上线)

精选扩充把采集清单从 24 → **52 yfinance**(22 指数 / 13 商品 / 9 外汇 / 4 债券 / **4 市场情绪 sentiment(全新 category)**)+ 加密 2 → 7,合计 **59 指标**。两件事沉淀存档。

### 1. 加密组修复 · `select_crypto_overview` 读 `instrument='perp'`(原读 `'spot'`)

**现象**:精选扩充前真机抽查,`/global` **加密组整组消失**(只剩 index/commodity/forex/bond 四组,crypto 组空)。比阶段A 的 500 更隐蔽 —— **不报错、静默消失**。

**根因**:`select_crypto_overview` 原查 `crypto_ticker_24h WHERE instrument='spot'`,但**现货采集从未常态化** —— 只有 M2 早期一次性种子行(2026-05-23),`crypto_ticker_24h` 的 `TTL 2 DAY` 早把过期种子清光 → spot 行全无 → 加密组查不到任何行 → 空组。

**修**(`clickhouse_overview.py` `select_crypto_overview`):改读 `instrument='perp'`(永续)。perp 是 `crypto_metrics_ingest`(`_all_usdt_perp_symbols()` · 全市场 ~300 USDT 永续)的 **bulk 常态采集**,每轮刷新、数据新鲜、覆盖全部主流币;**对齐产品「加密以合约(perp)为主体、现货为辅」定位基调**(产品负责人拍板)。永续价对主流币 ≈ 现货价(基差极小),概览「仅供参考」展示足够。

**验证**:改后部署即恢复 7 币(BTC / ETH / SOL / BNB / XRP / TRX / DOGE),`last_point` 实数据合理(BTC ~74k / ETH ~2k …)。

**后续**:若将来概览要展示**真现货价**,须**新建独立现货采集任务**(spot ingest 常态化),不能再靠 perp 通道顶替 —— 永续 ≈ 现货只在「仅供参考」精度下成立。

### 2. 首轮采集延迟 · 再证(含全新分类)

上面「§ 运维备注 · 首轮采集延迟」的机制,这次扩 59 指标**又验一次**,补一条新 nuance:

- 采集清单 24 → 52,单轮 `global_overview_scan` 抓 52 个 yfinance(耗时随之略增),仍是 :00/:10/:20… **每 10min 一轮**;**扩充后数据要等下一轮 scan 跑完才进库**,首轮跑完前 `/global` 新指标暂无数据 = **正常**。
- **新分类同样要等一轮**:本次新增 `sentiment`(市场情绪)是**全新 category**,首轮 scan 跑完前,`/global` 上「市场情绪」**整个分组都不出现** = 正常 —— 前端按 API 返回的 category **动态分组**,API 没这组就没这组(不是前端漏渲染)。
- 结论不变:**「新指标 / 新分类不显示」永远先怀疑采集没跑完,而不是前端**;想立刻看用上面的手动触发命令(`celery … call tasks.market.global_overview_scan`),等约 90s。
