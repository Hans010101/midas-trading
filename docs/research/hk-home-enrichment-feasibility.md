# 港股首页丰富化 · 可行性调研

> 性质:**纯调研 · 不动代码**。供产品负责人定首页做到什么程度,确认后再开工。
> 日期:2026-06-01 · 前置:港股阶段二已收口(详情页 + 行情页 18 只列表 + 市场维度,生产验过)。
> 目标:对齐 A股/美股首页(大盘指数 + 榜单 + 板块),评估港股数据能撑到什么程度。

---

## TL;DR

- **港股首页 = 完全复用美股(us)的「策展池」模式**,不是复用 A股(cn)的全市场模式。
- ★★ **关键洞察**:美股 us 首页**本来就是策展池(US_POOL 128 只)非全市场**(决策⑥),**本来就不做涨跌家数 breadth**,顶部诚实标注「策展非全市场」。港股 18 只是**同一模式的更小池** → 直接套 us,不是「港股残缺」。
- 产品负责人担心的「涨跌分布/全市场榜做不了」——**us 也不做**,所以不影响「对齐美股首页」。
- 数据已就位:恒生指数(已采,生产 `/overview/global` 验证含恒生)+ 18 只 kline(已采)+ hk_pool sector(科技/金融/电信/汽车)。
- 工作量:中等(高复用 us,但要新建后端采集 task + 2 张快照表 + 2 个接口 + 前端 HkSections)。

---

## 1. A股 vs 美股首页构成对比(关键:两套不同数据模式)

| 板块 | A股 cn | 美股 us | 数据来源 |
|---|---|---|---|
| 状态条(交易时段) | ✓ | ✓ | 市场日历状态机 |
| 大盘指数卡 | 4 张 | 4 张 | `select_latest_indices(market)` ← `market_index_snapshot` 表 |
| 榜单(涨/跌/额 3 Tab) | **全市场 5000+** | **策展池 128** | cn=`cn_spot_snapshot` / us=`us_spot_snapshot` |
| 行业板块 | 全市场行业 | 池内行业 + 中概股 | cn=Sina行业 / us=`us_sector_snapshot`(池内等权) |
| 涨跌家数 breadth | ✓(全市场) | **❌ us 不做** | cn=`cn_market_breadth` / us 无 |
| 涨跌停估算 | ✓ | **❌ us 不做** | cn 按阈值估 / us 无 |

**采集任务**:
- cn:`cn_board_scan`(Sina 全市场 spot,5000+)→ cn_spot_snapshot + cn_market_breadth
- us:`us_board_scan`(**yfinance 批量拉 US_POOL 128 只策展池**)→ us_spot_snapshot + us_sector_snapshot
- 港股现状:只 18 只 kline(日线)+ 恒生指数(全球概览采)· **无任何全市场 spot 采集**

## 2. ★ 港股套哪套:套 us(策展池),不套 cn(全市场)

港股只有 18 只策展池 + 恒生,**没有全市场港股 spot**。所以:
- ❌ **套 cn 不行**:cn 靠 Sina 全市场 5000+ 只 → 港股没这数据,做不了全市场 breadth/榜单/行业。
- ✅ **套 us 完美**:us 本就是策展池(128 只)非全市场,模式与港股 18 只**完全同构**,只是池更小。

`UsSections` 前端已有现成的「策展池」诚实表达:顶部「热门美股 · 重点关注池 · 池内 128 只 · 策展非全市场」。港股照抄 → 「港股 · 精选 · 池内 18 只 · 策展非全市场」。

## 3. ★ 诚实评估:港股数据能撑起哪些板块

| 板块 | 港股能做? | 说明 |
|---|---|---|
| **状态条** | ✅ 能 | 港股交易日历状态机已有(阶段一) |
| **大盘指数卡** | ✅ 能(恒生 1 张) | 恒生 ^HSI 已采(全球概览 → `market_index_snapshot` market=hk)· `/overview/global` 生产验证含恒生 · **可用 `select_latest_indices(market="hk")` 现成拿** · 想凑 2-3 张需扩采国企 ^HSCE / 恒生科技 ^HSTECH(yfinance · 可选) |
| **策展池榜单(涨/跌/额)** | ✅ 能(18 只) | 照 `us_board_scan`:yfinance 批量拉 HK_POOL 18 只 spot → 排序 3 榜 · 标注「精选 18 只」 |
| **板块** | ✅ 能(4 板块) | HK_POOL 已有 sector(科技/金融/电信/汽车)· 照 `us_sector` 池内等权聚合 |
| **涨跌家数 breadth** | ❌ 不做 | 无全市场港股数据 · **但 us 也不做**(策展池模式)· 不是缺陷 |
| **涨跌停估算** | ❌ 不做 | 港股**无涨跌停制度** + 无全市场 · us 也不做 |
| **两市成交额** | ❌ 不做 | 18 只加总 ≠ 全市场 · 误导 · 不做 |

**结论**:港股首页 = 状态条 + 恒生指数卡(1-3 张)+ 策展池 18 只榜单(涨/跌/额)+ 4 板块。**与 us 首页同构**,只是无 breadth(us 本就无)。不硬做数据撑不起的全市场涨跌分布/涨跌停。

## 4. 复用度 + 新建清单

**复用度:极高(港股首页 ≈ 美股首页)**

| 层 | 复用 | 新建 |
|---|---|---|
| 前端骨架 `MarketHomePage` | ✅ 95%(状态条 + 指数卡 + Sections 分叉)· 扩 `MarketKind` 加 hk | market==='hk' 渲染 `<HkSections/>` |
| 指数卡 `QuoteCard` | ✅ 100% 共用 | — |
| 榜单/板块 `HkSections` | ✅ 照 `UsSections`(~90%) | 新建(改 18 只 + hk 板块 + /hk-preview 跳转) |
| 后端 `/hk/overview` | ✅ 照 `/cn/overview`(`select_latest_indices(market="hk")`) | 新建路由(~照抄) |
| 后端 `/hk/board` | ✅ 照 `/us/board` | 新建路由 + schema |
| 采集 `hk_board_scan` | ✅ 照 `us_board_scan` | 新建 task(yfinance/akshare 批量拉 HK_POOL spot + 板块聚合)+ beat |
| 快照表 | ✅ 照 us | `hk_spot_snapshot` + `hk_sector_snapshot`(CH 建表) |

**关键复用点**:大盘指数后端**几乎零成本**——恒生已在 `market_index_snapshot`(全球概览采,market=hk),`/hk/overview` 直接 `select_latest_indices(market="hk")`。

## 5. 分单元建议

| 单元 | 内容 | 复用 | 验收 |
|---|---|---|---|
| **单元1 · 后端**(中) | `hk_board_scan` task(yfinance 批量拉 18 只 spot + 板块聚合)→ `hk_spot_snapshot`/`hk_sector_snapshot` 表 + `/hk/overview`(恒生)+ `/hk/board`(榜单+板块)接口 + beat 注册 | 照 us_board_scan / us.py | curl /hk/overview 返恒生 · /hk/board 返 18 只榜单 + 板块 |
| **单元2 · 前端**(中) | `MarketHomePage` 扩 hk + `HkSections`(照 UsSections)+ `/hk-market` 升级为完整首页(指数卡 + 榜单 + 板块,吸收阶段二单元3 的简化列表) | 照 UsSections · MarketHomePage 95% | 生产逐入口:指数卡(恒生)+ 榜单(18只带价)+ 板块 + 点进详情 + cn/us/crypto 零回归 |
| (可选) | 扩采恒生国企 ^HSCE / 恒生科技 ^HSTECH 指数(凑 2-3 张指数卡) | 照全球概览指数采集 | — |

**工作量**:~2 单元,比港股阶段二略重(阶段二是详情页纯复用;本次要新建后端采集 + 表 + 接口)。

## 6. 边界(同港股阶段二)

- 首页**只读展示**:大盘指数 + 榜单 + 板块,**不碰下单 / AI**(那是港股阶段三的「详情页配下单+AI」,本次明确不做)。
- **不碰现有 cn/us/crypto 首页**:`MarketHomePage` 加 hk 分支,cn/us 路径零改动(git diff 守)。
- 港股 = 行情展示 · 只读 · 不可交易 · 全程虚拟。

---

## 待产品负责人拍板点

1. **指数卡数量**:只恒生 1 张(零扩采,最快)· 还是扩采国企 ^HSCE + 恒生科技 ^HSTECH 凑 2-3 张(更像 A股 4 卡,需加采集)?
2. **/hk-market 怎么改**:阶段二单元3 的 18 只简化列表 → 升级为完整首页(指数卡 + 榜单 + 板块)· 列表被榜单吸收(榜单就是带排序的列表)。确认这个升级方向?
3. **板块要不要做**:港股 4 板块(科技/金融/电信/汽车)池内等权 · 还是先只做指数卡 + 榜单(板块留后续)?
4. **分单元节奏**:单元1(后端采集+接口)→ 单元2(前端首页)· 是否这个顺序?
5. **采集源**:hk_board_scan 用 yfinance(港股可达,同详情页降级源)批量拉 18 只 spot · 确认?

> 本轮只调研,未动代码。产品负责人确认范围 + 拍板后,按单元开工(每单元 feature 分支 + 合 main + 生产逐入口真机验,延续港股阶段二模式)。
