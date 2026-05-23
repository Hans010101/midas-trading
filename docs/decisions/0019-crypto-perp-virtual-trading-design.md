# 0019 · 加密合约(永续 perp)虚拟交易设计

## 状态

**Proposed**(2026-05-23)· 待产品负责人审定 **§11「待拍板决策」** 后转 Approved,再按本 ADR 写实现代码。

> 本文档**只做设计**,不含任何已落地的实现代码。文中的表结构 / 函数 / 公式均为「建议」,等审定后才写。

---

## 红线(最高优先级 · 任何实现都不得违背)

1. **全程虚拟资金,永不接任何真实交易 / 下单 / 转账 / 提现通道。** 所有开仓、加仓、平仓、强平、资金费结算都走点金自己的虚拟撮合引擎,**不调用任何交易所下单 API**(ccxt 只用于读行情,绝不用于 `create_order`)。这是产品 DNA(见 CLAUDE.md「项目本质」)。
2. **永续合约只是「带杠杆/做空的虚拟玩法」,不是真钱。** 杠杆、保证金、强平价、资金费全部是模拟教学,目的是让用户零风险理解合约机制,不是诱导高风险交易。
3. **所有下单 / 持仓 / 策略 / 浮盈卡片必带「VIRTUAL · 模拟」帝王金徽章 + 「仅供参考,不构成投资建议」小字。**
4. **「实战策略清单」只给提示,绝不自动下单。** 任何「资金费为正→开多」之类规则都是**只读提示**,必须用户手动点开仓 + 走确认模态,系统永不代替用户下单。

---

## 上下文

### 触发背景

M2-C 启动。加密详情页 `/crypto-preview` 右栏目前是两块占位:

- **「下单指导」**(`OrderGuidance`):开多(虚拟)/ 开空(虚拟)按钮、杠杆、保证金(虚拟 USDT)、预估强平价 —— 全是 `— (待接)`,顶部标「占位 · 待虚拟交易模块接入(M2-C)」。
- **「实战策略清单」**(`StrategyChecklist`):4 条规则文字 + 占位标记。

本 ADR 要把这两块的**真实设计**讲清楚,以及背后的**永续合约虚拟撮合引擎 / 虚拟合约持仓 / 保证金账户**。

### 已有资产(必须先认清,避免重复造轮子)

项目里**已经有一套虚拟交易系统**(ADR-0008,M0 已上线):

| 资产 | 现状 | 能否直接用于 perp |
|---|---|---|
| `VirtualAccount`(per user×market,lazy create) | crypto 子账户 = USDT 钱包,`cash_balance` | ✅ **复用**(作为 perp 保证金钱包,见 §2) |
| `VirtualPosition`(软删 closed_at) | **现货/多头/无符号 quantity/无杠杆** | ❌ 不兼容(perp 要 side/杠杆/保证金/强平) |
| `VirtualOrder` | 现货 buy/sell | ❌ 不兼容(perp 要 open/close × long/short + 杠杆) |
| `VirtualEquitySnapshot` | 每账户权益曲线点 | ✅ **复用**(perp 浮盈并入 crypto 账户权益,见 §4.6) |
| `services/virtual_trading/engine.py` | 现货市价撮合,纯 SQL 原子 | ⚠️ **不改它**,新增 `perp_engine.py` 平行(见 §2) |
| `fees.py` / `equity.py` | 手续费 + 滑点 + 快照 | ✅ 复用思路,perp 费率单列 |

**ADR-0008 明确把「杠杆 / 做空」列为 `M2+ 或永不 · 产品红线考虑`**(0008 撤销路径)。本 ADR 即是对那条「M2+」的正式展开:**在严守「虚拟资金」红线的前提下**做合约玩法。这不违反红线 —— 红线是「不接真实下单」,不是「不做杠杆模拟」。**这一点本身需要产品确认(见 §11 D0)。**

### 数据已就绪(无需新采集)

perp 撮合 / 强平 / 策略所需的实时数据,M2-A/M2-D 已全部采集并有只读端点:

| 端点 | 字段 | 用途 |
|---|---|---|
| `GET /api/v1/crypto/futures/{symbol}/info` | `mark_price` / `index_price` / `last_funding_rate` / `next_funding_time` / `max_leverage` / `open_interest_*` | **撮合价 + 强平价 + 资金费 + 杠杆上限** |
| `GET /api/v1/crypto/futures/metrics-batch` | `funding_rate` / `account_long_short_ratio` / `oi_change_pct_24h` | 实战策略清单驱动 |
| `GET /api/v1/crypto/futures/{symbol}/open-interest` · `/long-short-ratio` | OI / 大户多空比 时序 | 策略 + 详情页维度图(已接) |
| `GET /api/v1/market/kline?instrument=perp` | perp K 线 | 主图 / 缠论 / 最新价兜底 |

**关键点:`futures/{symbol}/info.mark_price` 是 perp 撮合与强平的正确价源**(标记价,非最新成交价 —— 防插针),而且该响应自带 `max_leverage`(交易所真实上限,1–125),杠杆上限可直接取真值。

---

## 1. 范围界定(M2-C 做什么 / 不做什么)

### ✅ M2-C 必做

1. **永续合约虚拟撮合引擎**:开多 / 开空 / 加仓 / 减仓 / 平仓 / 反手,逐仓保证金,市价单。
2. **虚拟合约持仓**:side(long/short)、杠杆、入场均价、保证金、强平价、浮动盈亏、已实现盈亏。
3. **保证金钱包**:复用 crypto 的 `VirtualAccount`(USDT)。开仓冻结保证金,平仓释放 + 结算盈亏。
4. **强平**:mark price 触及强平价 → 自动平仓、保证金归零、记一笔强平流水。
5. **详情页「下单指导」接真实**:杠杆 slider、保证金输入、**预估强平价/预估强平距离实时计算**、开多/开空按钮 → 确认模态 → 下单。
6. **详情页「实战策略清单」接真实**:4 条规则由实时指标(资金费率/OI/多空比/缠论)驱动,**只读提示**。
7. **持仓 / 流水展示**:详情页当前标的活仓卡 + `/portfolio` 加「加密合约」区块(活仓 / 历史 / 强平记录)。

### ❌ M2-C 不做(留后续或永不)

- **限价单 / 止盈止损单 / 条件单**(M2-C 只市价单;TP/SL 留 M2-C.3 或 M3)。
- **全仓保证金(cross margin)**(M2-C 仅逐仓 isolated,见 §11 D2)。
- **自动交易 / 策略自动下单**(永不 · 红线 §4)。
- **多空对锁(hedge 双向持仓)**(M2-C 单向净持仓,见 §11 D6)。
- **A 股 / 美股的杠杆**(杠杆只给 crypto perp;cn/us 永远现货 0008 那套)。
- **资金费结算**(是否进 M2-C.1 待定,见 §11 D5)。

---

## 2. 复用 vs 新增(与 0008 的边界)

**原则:不动 0008 现货那套(已上线、有测试、在跑),perp 平行新增一套,只共享 USDT 钱包。**

```
                 ┌─────────────────────────────┐
                 │  VirtualAccount (crypto)     │  ← 复用 · USDT 统一钱包
                 │  cash_balance = 可用 USDT     │     (现货 + 合约共用,见 D1)
                 └──────────────┬──────────────┘
            ┌───────────────────┴───────────────────┐
   现货(0008,不动)                          合约(M2-C,新增)
   VirtualPosition / VirtualOrder            VirtualPerpPosition / VirtualPerpOrder
   engine.place_market_order()               perp_engine.open / close / liquidate()
```

- **复用**:`VirtualAccount`(crypto/USDT)、`VirtualEquitySnapshot`(perp 浮盈并入 crypto 权益)、`fees.py` 的滑点思路、`futures/{sym}/info` 价源、确认模态/徽章/toast 等前端组件。
- **新增**:`VirtualPerpPosition` / `VirtualPerpOrder` 两张表、`services/virtual_trading/perp_engine.py`、perp REST 路由、强平监控 worker(若选实时方案)、详情页两块面板的真实实现。

> **D1 待拍板:** perp 与现货是否**共用** crypto 的 `cash_balance`(统一 USDT 钱包,贴近 Binance 统一账户),还是 perp 用**独立保证金子账户**。推荐共用(简单、真实、用户只填一次 USDT),代价是现货持仓与合约保证金抢同一池子。

---

## 3. 数据模型(PostgreSQL · 新增 2 张表)

> 金额一律 `Numeric(20,8)`(USDT 计价)· tz-aware datetime(遵守项目铁律,clickhouse 那条同理) · 软删 `closed_at` 沿用 0008 风格。

### 3.1 `virtual_perp_position` · 合约持仓

```python
class PerpSide(StrEnum):
    LONG = "long"
    SHORT = "short"

class MarginMode(StrEnum):
    ISOLATED = "isolated"   # M2-C 只做逐仓
    # CROSS = "cross"       # 留 D2

class PerpCloseReason(StrEnum):
    MANUAL = "manual"           # 用户手动平
    LIQUIDATED = "liquidated"   # 强平
    RESET = "reset"             # 账户重置清仓

class VirtualPerpPosition(Base):
    __tablename__ = "virtual_perp_position"

    id:            int        # PK
    account_id:    int        # FK virtual_account.id (crypto 账户) ON DELETE CASCADE
    symbol:        str        # Binance 风格 'BTCUSDT'(与采集表 / info 端点一致)
    side:          PerpSide   # long / short
    margin_mode:   MarginMode # isolated
    leverage:      int        # 开仓杠杆(1..max_leverage)
    quantity:      Decimal    # 持仓量(币,Numeric(20,8));净持仓,部分平仓递减
    entry_price:   Decimal    # 加权入场均价
    initial_margin: Decimal   # 已冻结保证金(USDT) = notional/leverage,加仓累加
    maintenance_margin_rate: Decimal  # MMR 快照(开仓时记,默认 0.005)
    liquidation_price: Decimal        # 强平价(每次加/减仓后重算,见 §4.5)
    realized_pnl:  Decimal | None     # 已实现盈亏(平仓累计,USDT)
    fee_paid:      Decimal            # 累计手续费(USDT)
    funding_paid:  Decimal            # 累计资金费(USDT,+付出 / −收到;D5 决定是否启用)
    opened_at:     datetime
    closed_at:     datetime | None    # 软删:NULL=活仓
    close_reason:  PerpCloseReason | None

    # partial unique:同账户同 symbol 同 side 最多一个活仓(closed_at IS NULL)
    # 单向净持仓模式(D6)下其实是「同账户同 symbol 一个活仓」,side 由活仓决定
```

**索引**:`uq_perp_position_active (account_id, symbol) WHERE closed_at IS NULL`(单向持仓 D6)· `ix (account_id, closed_at)`。

> **注意未存的字段**:`unrealized_pnl` / `margin_ratio` / 强平距离 **不入库**(随 mark price 实时变),由读接口现算。`liquidation_price` **入库**(只在加/减仓时变,强平 worker 要靠它快速比对,不能每次现算全表)。

### 3.2 `virtual_perp_order` · 合约订单流水(不可变)

```python
class PerpAction(StrEnum):
    OPEN_LONG  = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE_LONG  = "close_long"    # 平多(可部分)
    CLOSE_SHORT = "close_short"   # 平空(可部分)

class VirtualPerpOrder(Base):
    __tablename__ = "virtual_perp_order"

    id:            int
    account_id:    int        # FK
    position_id:   int | None # 关联持仓(rejected 时可空)
    symbol:        str
    action:        PerpAction
    leverage:      int | None # 仅 open 填
    quantity:      Decimal    # 本笔数量(币)
    price:         Decimal | None  # 成交价(mark+滑点),rejected NULL
    notional:      Decimal | None  # price × quantity (USDT)
    margin_delta:  Decimal | None  # 本笔冻结/释放的保证金(USDT)
    fee:           Decimal | None  # 手续费(USDT)
    realized_pnl:  Decimal | None  # 平仓笔填
    status:        OrderStatus     # filled / rejected(复用 0008 enum)
    reject_reason: str | None
    is_liquidation: bool      # 是否强平触发(区分手动平 vs 强平)
    placed_at:     datetime
    filled_at:     datetime | None
```

**索引**:`ix (account_id, placed_at desc)`。

### 3.3 权益曲线(复用 `VirtualEquitySnapshot`)

crypto 账户的一条权益曲线 = `cash_balance` + 现货持仓市值 + **Σ(perp 活仓:initial_margin + unrealized_pnl)**。即 perp 浮盈实时并入 crypto 账户 equity,**不新增曲线表**,只在 `aggregate_portfolio` / 快照计算里加 perp 项。

---

## 4. 撮合与计算逻辑(逐项算法)

> 全部 USDT 本位线性合约(linear / USDT-margined)。币本位反向合约不做。

### 4.1 价源 · mark price

- 撮合价 / 浮盈 / 强平**统一用 `futures/{symbol}/info.mark_price`**(标记价,抗插针),不用最新成交价。
- 注入式 `PerpMarkPriceFetcher(symbol) -> Decimal | None`(对齐 0008 的注入式 `PriceFetcher`,便于 mock 测试)。
- 取不到 mark price(标的下架/数据未到)→ **拒单**(`reject_reason="无标记价 · 标的可能下架或数据未到达"`),绝不用 0 或猜测价(CLAUDE.md 红线 + 0010 数据精度教训)。

### 4.2 开仓(开多 / 开空)· 市价

输入:`(user_id, symbol, side, quantity_or_margin, leverage)`。
> 前端两种输入模式二选一(D8):按「币数量」开 或 按「保证金 USDT」开。建议 UI 用**保证金 + 杠杆**输入(更贴近用户「我想投入 X USDT」),后端换算 `quantity = margin × leverage / mark_price`。

```
1. 校验:leverage ∈ [1, info.max_leverage 上限封顶到 §11 D3 的产品上限]
2. mark = fetch_mark_price(symbol);取不到 → reject
3. fill_price = apply_slippage(mark, side)        # 开多上浮 / 开空下浮,bps 见 §4.9
4. notional = quantity × fill_price               # USDT
5. required_margin = notional / leverage
6. fee = notional × TAKER_FEE_RATE                # 见 §4.9
7. 原子扣钱:UPDATE virtual_account
       SET cash_balance = cash_balance - (required_margin + fee)
       WHERE id=? AND cash_balance >= required_margin + fee
       RETURNING id                               # 失败 → reject「保证金不足」
8. UPSERT 活仓(单向净持仓 D6):
   - 无活仓 → INSERT(side, leverage, quantity, entry_price=fill_price,
                     initial_margin=required_margin, MMR, liquidation_price=§4.5)
   - 有同向活仓 → 加仓:加权 entry_price、quantity += q、initial_margin += required_margin、
                       重算 liquidation_price
   - 有反向活仓 → 见 §4.4 反手逻辑
9. 写 VirtualPerpOrder(action=open_long/short, filled)
10. 同事务写 equity snapshot(trigger=order_filled)· emit 通知(0009 复用)
```

### 4.3 平仓(部分 / 全部)· 市价

```
1. 锁活仓:SELECT ... FOR UPDATE WHERE account_id,symbol,closed_at IS NULL
   无活仓 / quantity 不足 → reject
2. mark → fill_price = apply_slippage(mark, 反方向)   # 平多按卖出下浮,平空按买回上浮
3. 本笔已实现盈亏(线性合约):
     long :  pnl = (fill_price - entry_price) × close_qty
     short:  pnl = (entry_price - fill_price) × close_qty
   再扣本笔平仓手续费:pnl_net = pnl - close_fee
4. 释放保证金:released_margin = initial_margin × (close_qty / quantity)
5. 回钱:UPDATE virtual_account
       SET cash_balance = cash_balance + released_margin + pnl_net,
           realized_pnl = realized_pnl + pnl_net
6. 更新持仓:
   - 部分平:quantity -= close_qty;initial_margin -= released_margin;
            realized_pnl 累加;重算 liquidation_price(entry 不变 → 强平价不变,但 MMR 档位可能变,简化下不变)
   - 全平:quantity=0,closed_at=now,close_reason=manual,realized_pnl 累加
7. 写 VirtualPerpOrder(action=close_*, realized_pnl=pnl_net)
8. equity snapshot + emit
```

### 4.4 反手(持多时下「开空」且数量 > 当前多仓)

单向净持仓模式(D6)下,反向开仓**先平掉现有活仓,再用剩余数量反向开新仓**:

```
开空 q,当前持多 p:
  q ≤ p → 视作平多 q(§4.3)
  q > p → 先平多 p(§4.3 全平)→ 再开空 (q - p)(§4.2),新仓 entry=fill_price
```

### 4.5 强平价公式(逐仓 · 线性 · 简化教学版)

逐仓下,持仓权益 = 保证金 + 浮盈;当权益 ≤ 维持保证金时强平。忽略平仓手续费的简化闭式解(MMR = 维持保证金率,默认 0.5%):

```
开多:  liq_price = entry_price × (1 − 1/leverage + MMR)
开空:  liq_price = entry_price × (1 + 1/leverage − MMR)
```

推导(多仓,逐仓):`initial_margin + (liq − entry)×qty = MMR × entry × qty`,且 `initial_margin = entry×qty/leverage`,两边除 `qty` 解得上式。

- **MMR 取值**:M2-C.1 用**全局常量 0.5%**(`MAINTENANCE_MARGIN_RATE = Decimal("0.005")`)。真实交易所是按名义额分档(tiered),教学版不做分档(见 §11 D3 备注)。
- 加仓后用新的加权 `entry_price` + 合并后的 `leverage`(加仓若用不同杠杆,取保证金加权或锁定首仓杠杆 —— 建议**锁定首仓杠杆**,加仓必须同杠杆,UI 限制)。
- `liquidation_price` 入库,强平 worker 只需比 `mark` 与该列,O(活仓数)。

### 4.6 浮动盈亏 / 保证金率 / 强平距离(读时现算,不入库)

```
unrealized_pnl = (mark − entry)×qty   (long) / (entry − mark)×qty  (short)
position_value = initial_margin + unrealized_pnl      # 逐仓持仓权益
margin_ratio   = maintenance_margin / position_value  # 越接近 1 越危险
强平距离%      = |mark − liq_price| / mark × 100
ROE%           = unrealized_pnl / initial_margin × 100 # 杠杆放大后的收益率
```

crypto 账户总权益(并入 portfolio / 快照):
```
equity_crypto = cash_balance
              + Σ现货持仓市值
              + Σperp活仓(initial_margin + unrealized_pnl)
```

### 4.7 强平触发(谁监控 mark price)· **核心待拍板 D4**

三种方案:

| 方案 | 机制 | 优点 | 缺点 |
|---|---|---|---|
| A 实时 worker | Celery beat 每 30–60s 扫所有「有 perp 活仓」的账户,逐仓比 `mark` vs `liquidation_price`,触发即平 | 接近真实、用户离线也强平 | 多一个 worker + 周期拉 mark price(只拉有活仓的 symbol,集合小) |
| B 惰性检查 | 只在用户每次查持仓 / 下单时检查并补强平 | 零额外 worker | 用户不打开页面就不强平,曲线失真;教学体验差 |
| C 混合(**推荐**) | A 的周期 worker(60s,只扫有活仓 symbol)+ B 的交互兜底 | 体验接近真实 + 成本可控 | 实现量中等 |

强平执行:`mark` 触及 `liq_price` → 按 `mark`(或更差的 `liq_price`)市价全平,`cash_balance += 剩余权益(≈0 或维持保证金残值)`,`close_reason=liquidated`,写 `is_liquidation=true` 流水,**emit 强平通知**(0009 推送复用),前端 toast「⚠️ 虚拟仓位已强平」。

### 4.8 资金费结算(perp 专属)· **待拍板 D5**

真实 perp 每 8h(UTC 00/08/16)按 `funding_rate × notional` 在多空间转移:
```
funding_payment = funding_rate × mark × qty
  rate > 0:多付空收;rate < 0:空付多收
对持仓:cash_balance -= sign × funding_payment(long sign=+1, short sign=−1)
       funding_paid 累加
```
- **建议**:M2-C.1 **先不做**资金费(UI 标注「资金费教学版暂不计入盈亏」),M2-C.2 再加一个 8h Celery beat job 遍历活仓结算。理由:资金费要额外 worker + 改变「持有成本」叙事,先把开/平/强平主链路跑通更重要。

### 4.9 手续费 + 滑点

```
TAKER_FEE_RATE = Decimal("0.0005")     # perp taker 0.05%(建议;D8 拍板)
PERP_SLIPPAGE_BPS = 10                  # 10 bps,沿用 0008 crypto 滑点
```
- 开仓 / 平仓 / 强平都收 taker 费(USDT)。滑点方向:开多/平空上浮,开空/平多下浮。
- 与 0008 一致:费 + 滑点都在 USDT 上算,无跨币种。

### 4.10 并发安全(沿用 0008 的「纯 SQL 原子语义」)

| 场景 | 处理 |
|---|---|
| 同账户并发开仓抢保证金 | `UPDATE ... WHERE cash_balance >= margin+fee RETURNING` 原子扣 |
| 同活仓并发平仓 | `SELECT ... FOR UPDATE` 锁活仓 row |
| 强平 worker 与用户手动平撞车 | 强平也走 `SELECT FOR UPDATE`;先拿到锁者执行,另一方看到 closed_at 已填 → 跳过 |
| 账户重置(改 USDT)与持仓 | 单事务 DELETE 活仓 + 重写 cash;同 0008 |

不用 Redis lock / 应用层 mutex。

---

## 5. 「下单指导」/「实战策略清单」逻辑

### 5.1 下单指导面板(`OrderGuidance` 接真实)

```
┌─ 下单指导  [VIRTUAL·模拟] ──────────────┐
│  [ 开多(虚拟) ]   [ 开空(虚拟) ]        │  ← 中国红填充 / 中国红 outline(不用涨跌色)
│  杠杆   [—●———————] 10x   (1 .. max_lev) │  ← slider,上限取 info.max_leverage∧产品上限
│  保证金 [ 1,000 ] USDT                   │  ← 输入;或切「按数量」
│  ───────────────────────                │
│  预估开仓量   0.0102 BTC                 │  ← margin×lev/mark 实时算
│  预估强平价   $86,540  (距现价 −11.8%)   │  ← §4.5 实时算(纯前端预览,不落库)
│  预估手续费   $0.51                      │
│  可用 USDT    $9,488                     │
│  [ 确认开多 ]  ← 走 0008 同款确认模态     │
└──────────────────────────────────────────┘
```

- 杠杆 / 保证金任一变化 → **前端实时重算**预估开仓量、强平价、强平距离、手续费(用当前 mark price)。这些是**预览**,真正数值以下单返回为准。
- 未激活 crypto 账户 → 按钮 disabled + 「去设置页填 USDT」(复用 0008 未激活引导)。
- 有活仓时面板顶部显示当前活仓摘要 + 「平仓 / 加仓」。

### 5.2 实战策略清单(`StrategyChecklist` 接真实)· 只读提示

4 条规则(占位页已列),改为**由实时指标点亮/置灰**,命中给提示,**绝不自动下单**:

| # | 规则 | 触发条件(实时指标来源) | 命中提示 |
|---|---|---|---|
| ① | 资金费为正且 OI 增 → 顺势虚拟开多 | `metrics.funding_rate > 0` **且** `metrics.oi_change_pct_24h > 0` | 🟢「资金费 +x% · OI 24h +y% · 多头情绪占优,可考虑顺势开多(虚拟)」 |
| ② | 大户多空比极端 → 反向预警 | `metrics.account_long_short_ratio > 2`(过度看多)**或** `< 0.5`(过度看空) | 🟡「大户多空比 z · 情绪过热,警惕反向」 |
| ③ | 缠论一卖 + 基差走弱 → 虚拟减仓 | 缠论卖点(0011/0012 analysis 端点) **且** 基差走弱 | 见下方降级说明 |
| ④ | 强平价距现价 < 5% → 降杠杆提示 | 当前**活仓**:`强平距离% < 5` | 🔴「强平距离仅 a% · 建议降杠杆 / 加保证金」(只对已有活仓) |

- 每条带「仅供参考,不构成投资建议」。规则是**展示层逻辑**,可纯前端用已取的 metrics/info 算,也可后端出一个 `GET /perp/strategy-signals?symbol=` 聚合(建议前端算,少一个端点,见 §6)。
- **③ 的降级(D10)**:基差(basis)数据 M2-B 未采集(详情页⑥基差是占位示意)。所以规则③要么**降级为「只看缠论卖点」**,要么标注「基差待补」。建议 M2-C 降级为只看缠论卖点 + 标注。

---

## 6. 前后端改动范围 + API 设计 + 衔接点

### 6.1 后端新增

- **models**:`virtual_perp_position` / `virtual_perp_order`(§3)+ 1 个 alembic migration(含 partial unique)。
- **service**:`services/virtual_trading/perp_engine.py`(open / close / liquidate / 加权均价 / 强平价 / 浮盈)+ `perp_fees.py`(或并进 fees.py)。
- **强平 worker**(若选 D4-C):`tasks/perp_liquidation.py` + celery beat(60s,只扫有活仓 symbol;遵守 0015 worker 并发/OOM 教训)。
- **REST**(新前缀 `/api/v1/virtual/perp`,与 0008 `/virtual` 并列):

| Method | Path | 说明 |
|---|---|---|
| POST | `/virtual/perp/orders` | 下单 `{symbol, side, action, quantity?/margin?, leverage}` → 200 filled/rejected |
| GET | `/virtual/perp/positions?include_closed=` | 合约持仓(默认活仓 · 含实时浮盈/强平距离,后端注 mark price) |
| GET | `/virtual/perp/orders?symbol=&limit=&before_id=` | 合约流水 cursor 翻页 |
| (可选) GET | `/virtual/perp/preview?symbol=&side=&margin=&leverage=` | 服务端预估开仓量/强平价(若不想前端算) |

- price fetcher:新增 `make_perp_mark_fetcher(...)` 走 `futures/{sym}/info` 或 ClickHouse perp ticker;**注意** `select_kline` 要传 `instrument="perp"`(0008 的 fetcher 默认 spot,perp 不能复用那个)。

### 6.2 前端改动

- `components/crypto-preview/crypto-detail.tsx` 的 `OrderGuidance` / `StrategyChecklist`:占位 → 真实(§5)。
- `lib/api/virtual.ts` + `hooks/use-virtual.ts`:加 perp 下单/持仓/流水 hooks(复用现有结构)。
- 复用:确认模态(0008 `order-confirm-dialog`,加杠杆/保证金/强平价字段)、`VirtualBadge`、sonner toast、未激活引导。
- `/portfolio`(或 `/account`):加「加密合约」区块(活仓表含 side/杠杆/强平价/浮盈、历史、强平记录)。
- **不碰**:列表页 `/crypto-market`(刚修完)、详情页 6 维度图、0008 现货那套 UI。

### 6.3 衔接点(零新增采集)

- mark price / funding / max_leverage ← `futures/{sym}/info`(详情页 Header 已在用)。
- 策略指标 ← `metrics-batch` / OI / LSR(详情页维度图已在用)。
- 缠论卖点 ← `/api/v1/analysis/*`(0011/0012,AI 卡已在用)。
- 钱包 ← `VirtualAccount` crypto(0008 设置页已能填 USDT)。

---

## 7. 分期建议(若一期做不完)

| 期 | 范围 | 产出 |
|---|---|---|
| **M2-C.1**(核心闭环) | 2 表 + migration · perp_engine 开/平/反手 + 逐仓保证金 + 强平价 · 强平 worker(D4-C)· REST(orders/positions/orders 列表)· 下单指导接真实(开多/开空/杠杆/保证金/强平价预估)· pytest(撮合数值/保证金/强平/并发) | 用户能在详情页开/平虚拟合约单,看浮盈、强平价、被强平 |
| **M2-C.2**(策略 + 资金费) | 实战策略清单接真实(4 规则 · ③降级)· 资金费 8h 结算(D5)· 详情页活仓卡 + 强平 toast | 策略提示 + 资金费教学 |
| **M2-C.3**(组合 + 进阶单) | `/portfolio` 加合约区块(活仓/历史/强平记录/曲线并入)· 止盈止损单(可选) | 复盘 + 风控单 |

**建议至少把 M2-C.1 当作一个不可分的闭环**(没强平的合约不成立)。

---

## 8. 风险点

1. **强平时机/价格的真实性 vs 实现成本**:60s 轮询 worker 下,极端行情里强平价会比真实交易所滞后几十秒;教学可接受,但要在 UI 标注「模拟强平按 ~1min 标记价检查」。
2. **mark price 数据新鲜度**:`futures/{sym}/info` 若预热/采集延迟,强平判断会用到旧 mark;需校验数据时效(stale 超阈值则跳过该轮强平,不误杀)。
3. **共用钱包的耦合(D1)**:现货持仓占用 USDT 会减少可开合约保证金,反之亦然;用户可能困惑。需 UI 把「可用 USDT / 已用保证金 / 现货占用」拆清。
4. **杠杆放大导致瞬间爆负**:必须保证 `cash_balance` 不会因强平滞后被打成负数 —— 逐仓下亏损上限 = initial_margin,强平及时即可;worker 滞后极端情况要兜底「最多亏光保证金,不倒扣钱包」(穿仓由平台虚拟承担,符合逐仓语义)。
5. **Decimal 精度 / 量纲**:quantity `Numeric(20,8)`、价格高低跨度大(BTC 11万 vs 某些币 0.000001),强平价/保证金计算要全程 Decimal + 统一 quantize,避免浮点误差(0002 教训)。
6. **「做杠杆」与产品红线的观感**:虽不接真实下单,但「125x 合约」对一个「教用户练交易直觉」的产品是否合适?→ 这是 D0/D3,产品要拍。
7. **反手 / 加仓的均价与强平价重算**:边界 case 多(加仓不同杠杆、反手跨越、部分平后强平价),测试要覆盖。

---

## 9. 自主决策(小事,已定 · 事后审计)

| # | 决策 | 理由 |
|---|---|---|
| 1 | perp 单独建 2 表,不改 0008 现货表 | 现货表无符号/无杠杆,硬塞 nullable 列会污染已上线模型 |
| 2 | perp symbol 用 Binance 风格 `BTCUSDT` | 与采集表 / `futures/info` / 详情页 futuresSymbol 一致,免转换 |
| 3 | `liquidation_price` 入库,浮盈/保证金率读时算 | 强平 worker 要快速比对(入库);浮盈随 mark 变(算) |
| 4 | 业务拒单 200 + `status=rejected`(沿用 0008) | 拒单是预期路径 |
| 5 | 开多/开空按钮用中国红(填充/outline 区分),不用涨跌色 | 沿用 0008,涨跌色留给行情 |
| 6 | 策略信号前端算(用已取的 metrics/info) | 少一个端点;数据详情页已在取 |
| 7 | MMR 教学版用全局 0.5% 常量,不分档 | 分档 tiered margin 是真实交易所细节,教学不需要 |

---

## 10. 撤销 / 演进路径

| 改动 | 路径 |
|---|---|
| 全仓保证金(cross) | 加 `margin_mode=cross`,强平价改为账户级(所有 cross 仓共享 cash);保证金计算改账户维度 |
| 止盈止损 / 限价单 | `virtual_perp_order` 加 `order_type`+`trigger_price`,挂单进 worker 监控触发 |
| 资金费 | 加 8h beat job(D5);`funding_paid` 字段已预留 |
| 双向持仓(hedge) | 改 partial unique 为 `(account_id, symbol, side)`,允许同 symbol 多+空并存 |
| 币本位反向合约 | 新增 inverse 计算分支(PnL 量纲不同);M2-C 不做 |
| 下线现货 crypto 只留 perp | 加密频道只暴露 perp 入口,0008 现货 crypto 保留后端不暴露前端(D11) |

---

## 11. 待产品负责人拍板的设计决策(最重要 · 逐条)

> 这部分定了才动代码。每条给出推荐,但请产品确认。

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| **D0** | **要不要做合约杠杆玩法?**(红线观感:虽是虚拟,但「杠杆/做空/强平」是否符合「教用户练交易直觉、不诱导高风险」的产品调性?) | A 做(本 ADR)· B 不做,加密也只做现货 0008 那套 | **请先拍 D0** —— 这是前提,其余决策都依赖它 |
| **D1** | perp 保证金钱包 | A 与现货**共用** crypto `cash_balance`(统一 USDT)· B perp 独立保证金子账户 | **A**(简单、真实、只填一次 USDT) |
| **D2** | 保证金模式 | A 仅逐仓 isolated · B 逐仓+全仓 cross | **A**(M2-C 只逐仓,cross 留后续) |
| **D3** | 杠杆上限 | A 1–20x(教学防爆)· B 1–50x · C 取交易所 max(1–125x) | **A 1–20x**(教学定位;UI 仍读 info.max_leverage 再 ∧ 20) |
| **D4** | 强平监控 | A 实时 worker · B 惰性检查 · C 混合(60s worker+交互兜底) | **C** |
| **D5** | 资金费结算 | A M2-C.1 就做 · B M2-C.2 再做 · C 永不(只展示费率不计入盈亏) | **B**(先把开/平/强平跑通) |
| **D6** | 持仓方向模式 | A 单向净持仓(同 symbol 一个活仓,反向先减仓/反手)· B 双向对锁(多空并存) | **A**(简单直观) |
| **D7** | 撮合/强平价源 | A `mark_price`(抗插针)· B perp 最新成交价 | **A** |
| **D8** | 费率 / 滑点 / 下单输入 | taker 0.05% + 滑点 10bps;UI 用「保证金+杠杆」还是「币数量」输入 | taker 0.05% + 10bps;**保证金+杠杆**输入 |
| **D9** | 浮盈/强平距离刷新频率(前端) | 5s / 10s / 30s 轮询 `futures/info` | **5–10s**(详情页已有轮询,复用节奏) |
| **D10** | 策略③(缠论一卖+基差走弱) | A 降级为只看缠论卖点 · B 等基差数据(M2-B)采集后再做 | **A 降级 + 标注「基差待补」** |
| **D11** | 现有 workbench 的「crypto 现货买卖」去留 | A 保留(现货+合约并存)· B 加密频道只做 perp,现货 crypto 前端下线 | 倾向 **A 保留**,但请确认产品对「加密频道现货入口」的取舍 |

---

## 12. 红线复述(实现前再读一遍)

- **永不接真实下单** · 所有撮合 / 强平 / 资金费走 `perp_engine` 虚拟逻辑,ccxt 只读行情。
- **杠杆/做空/强平只是虚拟教学**,不是真钱,不诱导高风险。
- **「VIRTUAL · 模拟」徽章 + 「仅供参考,不构成投资建议」** 覆盖下单指导 / 策略清单 / 持仓卡 / 强平 toast。
- **策略清单只读提示,绝不自动下单。**

---

## 修订记录

### v1 (2026-05-23) · 初稿 Proposed

接 ADR-0008(现货虚拟交易,长期上线)之后,展开其当年标注为「M2+ 或永不」的「杠杆/做空」分支,落到加密永续合约虚拟交易(M2-C)。复用 crypto USDT 钱包 + 详情页已有数据端点,新增 perp 专用表/引擎/强平。待 §11 十二条决策审定后转 Approved。
