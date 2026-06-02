# 港股下单池扩量 · 每手股数(board lot)批量源调研

> 性质:**纯调研 · 不动代码**。供产品负责人定下单池扩到多大、用什么源拿每手股数。
> 日期:2026-06-02 · 背景:下单池现 18 只(手核 HKEX),要扩大;卡点 = board lot 必须准(填错=下单量错=误导用户,红线)。

---

## TL;DR

- ★★ **决定性发现:HKEX 官方「List of Securities」xlsx 一个文件给全市场每手股数**,本机实测下载成功(HTTP 200 · 1.4MB · 3.2s · 合法 Excel),含 `Board Lot` 列,**Equity 普通股 2773 只 board lot 解析零失败**,且文件 **每日更新**(row1「Updated as at 02/06/2026」)。
- 源 = **港交所官方**(hkex.com.hk),**权威性最高**(它就是交易所的官方证券名册)。服务器在**香港 VPS**,访问 HKEX 香港本地 = 可达性极高(区别于 akshare 东财被拒)。
- ★ **顺带查出一个生产数据错误**:现 18 只里 **BYD 01211 手核填了 500,HKEX 官方=100**(now.com 三角验证也是 100)。说明**人工 WebSearch 核 1/18 就错**,HKEX 官方批量源是必需的。
- akshare 无可靠 board lot 接口(新浪 `stock_hk_spot` 只价格,实测确认);富途有 lot_size 但要 OpenD 网关+登录,生产不适合无人值守。
- **推荐方案 A**:接 HKEX 官方 xlsx(每日采)→ 下单池可扩到全市场普通股(~2406 主板 HKD),每手股数权威+自动跟改革变动。

---

## 1. 批量 board lot 源对比(生产可达性 + 准确性)

| 源 | 拿法 | 含 board lot? | 量级 | 生产可达性(香港 VPS) | 准确性 |
|---|---|---|---|---|---|
| ★ **HKEX 官方 List of Securities** | 下载 `ListOfSecurities.xlsx`(一个文件) | ✅ **`Board Lot` 列** | **全市场 17880 证券 / Equity 2773** | ★★ **极高**(HKEX 香港官方 · 港 VPS 本地 · 本机已实测 3.2s 通)· 需生产实测 | ★★★ **官方权威**(交易所名册)· **每日更新** |
| akshare `stock_hk_spot`(新浪) | 接口 | ❌ 只价格(实测确认) | 2764 | 高(新浪,同 A股) | — 无 lot |
| akshare 东财系 HK | 接口 | ❌ | — | ❌ 本地都 RemoteDisconnected | — |
| 富途 OpenAPI `lot_size` | futu-api | ✅ 有 | 全市场 | ❌ 要 OpenD 网关常驻 + 登录 + 客户端 · 无人值守生产不适合 | 高 |
| 个股页(now.com/aastocks) | WebFetch 逐个 | ✅ 渲染「每手股數」 | 逐个(慢) | 中 | 高(单元3 三角验证用过) |

**判据(吸取 akshare 东财翻车 + 全球概览教训)**:HKEX 是港交所**自家**公开文件、香港本地、静态下载(非反爬 scraper 目标)→ 可达性风险远低于东财那类。**但仍须生产 VPS 实测**(本机可达 ≠ 生产可达,铁律)。

## 2. HKEX List of Securities 文件实证(本机已下载解析)

- URL:`https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx`
- 表头(第 3 行):`Stock Code | Name of Securities | Category | Sub-Category | Board Lot | ISIN | Expiry Date | Subject to Stamp Duty | Shortsell Eligible | ... | Trading Currency | RMB Counter`
- Category 分布:Derivative Warrants 7531 / CBBC 5821 / **Equity 2773** / Debt 1330 / ETP 408 / REITs 11 / ...
- **Equity 普通股 2773**:主板 2431 + GEM 313 + 投资公司 22 + Trading Only 6 + 预托证券 1。
- **主板普通股 2431 只**,计价货币:**HKD 2406** / RMB counter 24 / USD 1。
- **Board Lot 解析零失败**(2773 只去逗号转 int 全成功)· 分布 100~100000 多档(对应改革文件说的 44 档)。
- 附带可直接用的列:`Subject to Stamp Duty`(Y/N,印花税口径)、`Trading Currency`、`Shortsell Eligible` 等。
- 准确性交叉验证:18 只手核 vs 官方 = **17 一致**;唯一不一致 BYD(我手核 500 错 / 官方 100,now.com 三角确认 100)→ **官方文件赢,人工核会错**。

## 3. 现实评估(诚实)

- **能扩多少**:下单池可扩到**全市场普通股**(2773),或收窄到**主板 HKD 2406**(剔除 GEM/RMB counter 复杂度)。lot 全部来自官方、零人工。
- **生产可达吗**:香港 VPS 访问 HKEX 香港官方文件,可达性极高(本机 3.2s 通)· **必须生产实测一次**(下载 + 解析跑通)再放量。
- **数据准吗**:官方名册 = 最权威;**每日更新** → board lot 任何变动(含港交所 2025-12 在咨询的「精简每手框架」一旦实施)**自动跟上**,无需人工重核。这是方案 A 对人工核的碾压优势。
- **人工核的现实**:已证人工 WebSearch 核 1/18 就错(BYD)· 扩到 50-100 只人工核 = 半天+高出错率+改革后还要重核 → 不可持续。

## 4. 分档方案(给产品负责人选)

| 方案 | 每手股数来源 | 下单池量 | 生产可达 | 准确性保证 | 工作量 |
|---|---|---|---|---|---|
| **A(推荐)· HKEX 官方批量** | 每日采 `ListOfSecurities.xlsx` → 解析 Equity 行 → lot 表 | **全市场普通股(~2406 主板 HKD,可加流动性/市值过滤)** | ★极高(港 VPS 本地 · 需实测) | ★官方+每日刷新·自动跟改革 | 一个采集 task + lot 表 + `hk_lot_size()` 改读表(中) |
| B · HKEX 官方 + 收窄池 | 同 A 的源 | 主板精选(如市值/成交额 top N) | 同 A | 同 A | A + 一个筛选规则(中) |
| C · 维持 18(仅修 BYD) | 现手核 + BYD 改 100 | 18 | 已有 | 改革后要人工重核 | 仅改 1 个值(小)· 但扩不动 |

**依赖关系**:B = A 的子集(同源,只是下单池范围收窄做风控);C 是"不接批量源"的保守档。

## 5. ★ 红线核对

1. **每手股数必须准**:✅ 方案 A/B 用 HKEX 官方名册(交易所自家 · 每日更新)· 比人工核更准(已证人工会错)。
2. **不准的不放进下单池**:✅ 采集失败/解析不出 lot 的标的 → 不进下单池(`hk_lot_size()` 返 None = 不可下单,现有兜底)。只读行情可全市场(新浪 2764),下单池只放 lot 核准的。
3. **改革跟进**:✅ 每日刷新自动跟;无源时保留上一份 good(不因当日下载失败而下单中断)。
4. **★ 现存 BYD 错误**:不论选哪个方案,**BYD 01211 现生产 500 是错的(应 100)必须修**(方案 A 全量替换自然修掉;方案 C 需单独改这一个值)。

## 6. 方案 A 落地要点(若选 A · 供后续单元参考 · 本轮不实现)

- Celery beat 每日任务:下载 xlsx → `pd.read_excel(header=2)` 解析 → 取 `Category=='Equity'` 行 → upsert 到 `hk_board_lot` 表(code, name, lot, trading_currency, stamp_duty, updated_at)。openpyxl/pandas 已是依赖。
- `hk_lot_size()` 改读该表(替代 `hk_pool.py` 硬编码 lot);下单池 = 表内 lot 有效 + 主板 + HKD(+ 可选流动性过滤)。
- 下单 board-lot 端点 `/virtual/hk-board-lot` 改读表。
- 容错:下载/解析失败 → 用上一份 good,记日志告警,不阻断下单。
- ★生产实测:第一步先在港 VPS 真跑一次下载+解析(像新浪那次 · 本机可达≠生产可达)。

---

## 待产品负责人拍板

1. **下单池扩到多大**:全市场普通股(~2406 主板 HKD)/ 收窄精选(top N)/ 维持 18?
2. **用 HKEX 官方 xlsx 批量源**(方案 A · 推荐)确认?
3. **BYD 01211 错误**(生产 500→应 100):随方案 A 全量替换修 · 还是先单独热修一个值?

> 本轮纯调研,未动代码。HKEX 文件已本机实证(下载+解析+18只交叉验证)· 生产可达性须开工第一步实测。
