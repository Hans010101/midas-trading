# 0008 · 虚拟交易(Virtual Trading)设计

## 状态
Approved-pending-review (2026-05-20)

## 上下文

Task 5(M0 验收链路第 3 步:陌生人能下虚拟单)启动。

**产品负责人 4 项决策已拍板:**

1. **初始资金:¥1,000,000**(三市场场景,茅台 1 手 ~¥17 万 / NVDA 1 股 ~$140 / BTC 1 个 ~$98K,10 万玩不开)
2. **滑点 + 手续费都模拟**(产品核心 = 「安全区演练真实交易」,不模拟成本练出的盈利是虚假的)
3. **持仓显示在独立 `/portfolio` 页**(看图 vs 看账户是两件事;工作台右栏只显示「当前标的持仓摘要」一小块)
4. **M0 范围:** 必做手动市价单 + 持仓 + 盈亏 + 权益曲线 + 余额;不做限价单/止损单(M1)/ 策略自动交易(M2)/ 杠杆做空(M2+ 或永不)/ 多账户

**红线沿用项目本质:**仅虚拟资金 · 永不接真实下单。

## 决策

### 1. 单货币基础 · CNY · M0 静态汇率

**决策:** 所有金额最终落 `*_cny` 字段(CNY 4 位小数),美股 / 加密市场内部用各自原币(USD / USDT)记账,撮合时一次性换算到 CNY。

**M0 静态汇率(写常量 / 不查接口):**

```python
# apps/api/app/services/virtual_trading/fx.py
FX_RATES_CNY: dict[str, Decimal] = {
    "CNY": Decimal("1.0"),
    "USD": Decimal("7.2"),
    "USDT": Decimal("7.2"),  # USDT 锚定 USD,1:1 近似
}

MARKET_CURRENCY: dict[Market, str] = {
    "cn": "CNY",
    "us": "USD",
    "crypto": "USDT",
}
```

**撤销路径:**
- M1 改 `exchange_rate` 表 + Celery worker 每日拉 akshare 收盘价
- 历史订单已存 `fx_rate_used` 字段,改汇率不影响过去成交

**为什么不做多币种持仓:**
- M0 demo 用户不关心「我有 ¥X CNY + $Y USD」三个钱包
- 单一 CNY 现金池 + 跨市场买卖 = 最简心智模型
- CryptoSharp 多币种钱包是为了真实做市场,Midas 是教学模拟,简化优先

### 2. Schema · 4 张表

```python
# apps/api/app/models/virtual.py

class VirtualAccount(Base):
    """一个用户一个虚拟账户(M0 不支持多账户)。"""
    __tablename__ = "virtual_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False, unique=True,  # 一对一
    )
    cash_balance_cny: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("1000000.0000"),
    )
    realized_pnl_cny: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000"),
    )
    created_at, updated_at  # 略,跟其他表一致 tz-aware


class VirtualPosition(Base):
    """开仓中的持仓 · 全部清仓 → 硬删 row · M0 仅 long。"""
    __tablename__ = "virtual_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 加权平均成本(原币种,A股一手 100 股的逻辑在外层 service 处理)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    avg_entry_price_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    created_at, updated_at

    __table_args__ = (
        UniqueConstraint("account_id", "symbol", "market",
                         name="uq_virtual_position_unique"),
        Index("ix_virtual_position_account", "account_id"),
    )


class VirtualOrder(Base):
    """订单流水 · 每次成交一条 · status: filled / rejected。"""
    __tablename__ = "virtual_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[OrderSide] = mapped_column(
        Enum(OrderSide, name="order_side"), nullable=False,
    )  # buy / sell
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type"), nullable=False,
        default=OrderType.MARKET,
    )  # M0 only market
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 成交价(已含滑点,原币种)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    notional_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    commission_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    # 仅 sell 填(本笔触发的已实现盈亏 in CNY)
    realized_pnl_cny: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    fx_rate_used: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False,
    )  # filled / rejected
    reject_reason: Mapped[str | None] = mapped_column(String(128))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_virtual_order_account_placed", "account_id", "placed_at"),
    )


class VirtualEquitySnapshot(Base):
    """权益曲线快照点(每次成交触发 + 每日定时)。"""
    __tablename__ = "virtual_equity_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    equity_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cash_cny: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    positions_value_cny: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False,
    )
    realized_pnl_cumulative_cny: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False,
    )
    trigger_kind: Mapped[SnapshotTrigger] = mapped_column(
        Enum(SnapshotTrigger, name="snapshot_trigger"), nullable=False,
    )  # order_filled / daily
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_virtual_equity_account_at", "account_id", "snapshot_at"),
    )


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"

class OrderType(StrEnum):
    MARKET = "market"
    # LIMIT = "limit"  # M1 再加

class OrderStatus(StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"

class SnapshotTrigger(StrEnum):
    ORDER_FILLED = "order_filled"
    DAILY = "daily"
```

**字段决策:**
- `id` 全部 `Integer autoincrement`(私有账户数据,跟 0007 watchlist 一致策略)
- `Numeric(20, 8)` for quantity(BTC 满足 8 位小数);`Numeric(20, 4)` for CNY 金额(够用)
- `realized_pnl_cny` 只在 sell 订单填,buy 永远 NULL(平账时累计到 account.realized_pnl_cny)
- 没有 `unrealized_pnl_cny` 列:这是动态值,按当前价 + 持仓量算,不存数据库

**清仓策略:** 持仓 quantity 减到 0 → 硬删 position row。历史盈亏走 `account.realized_pnl_cny` + 订单流水追溯。

### 3. 撮合逻辑 · 市价单(M0 唯一)

**输入:** `(account_id, symbol, market, side, quantity)`

**关键步骤(全部在单事务内):**

```python
async def place_market_order(...):
    async with db.begin():
        # 1. 拿当前市场价(走 cache-aside,跟 watchlist quote 同源)
        market_price = await get_latest_close(symbol, market)
        if market_price is None:
            return reject("无最新报价 · 标的可能停牌或数据未到达")

        # 2. 计算滑点 + 成交价(原币种)
        slip_bp = SLIPPAGE_BPS[market]  # cn=5 / us=3 / crypto=10
        fill_price = market_price * (1 + slip_bp/10000 if side==BUY else 1 - slip_bp/10000)

        # 3. 换 CNY
        fx = FX_RATES_CNY[MARKET_CURRENCY[market]]
        fill_price_cny = fill_price * fx
        notional_cny = quantity * fill_price_cny

        # 4. 算手续费
        commission_cny = calc_commission(market, side, notional_cny)
        # cn 买 0.0003 / cn 卖 0.0013(含印花税)
        # us 0
        # crypto 0.001 双向

        if side == BUY:
            total_cost = notional_cny + commission_cny
            # 5a. 原子扣钱(WHERE cash >= total_cost)
            r = await db.execute(
                update(VirtualAccount)
                .where(VirtualAccount.id == account_id,
                       VirtualAccount.cash_balance_cny >= total_cost)
                .values(cash_balance_cny=VirtualAccount.cash_balance_cny - total_cost)
                .returning(VirtualAccount.id)
            )
            if r.scalar_one_or_none() is None:
                return reject(f"余额不足 · 需要 ¥{total_cost}")

            # 6a. UPSERT position(加权平均成本)
            await upsert_position_buy(account_id, symbol, market,
                                       quantity, fill_price, fill_price_cny)

            realized_pnl_cny = None  # buy 不产生 realized

        else:  # SELL
            # 5b. 扣持仓(WHERE quantity >= sell_qty)+ 算 realized
            position = await get_position_for_update(account_id, symbol, market)
            if position is None or position.quantity < quantity:
                return reject("持仓不足")

            # 已实现盈亏(CNY)= (卖价 - 成本)× 数量 - 手续费(也算到 realized 里)
            realized_pnl_cny = (
                (fill_price_cny - position.avg_entry_price_cny) * quantity
                - commission_cny
            )
            proceeds_cny = notional_cny - commission_cny

            # 减持仓
            new_qty = position.quantity - quantity
            if new_qty == 0:
                await db.execute(delete(VirtualPosition).where(VirtualPosition.id == position.id))
            else:
                await db.execute(
                    update(VirtualPosition)
                    .where(VirtualPosition.id == position.id)
                    .values(quantity=new_qty)
                )

            # 6b. 加钱 + 累计 realized
            await db.execute(
                update(VirtualAccount)
                .where(VirtualAccount.id == account_id)
                .values(
                    cash_balance_cny=VirtualAccount.cash_balance_cny + proceeds_cny,
                    realized_pnl_cny=VirtualAccount.realized_pnl_cny + realized_pnl_cny,
                )
            )

        # 7. 写订单流水
        order = VirtualOrder(
            account_id=account_id, symbol=symbol, market=market,
            side=side, order_type=OrderType.MARKET,
            quantity=quantity, price=fill_price, price_cny=fill_price_cny,
            notional_cny=notional_cny, commission_cny=commission_cny,
            realized_pnl_cny=realized_pnl_cny,
            fx_rate_used=fx,
            status=OrderStatus.FILLED, filled_at=datetime.now(UTC),
        )
        db.add(order)

        # 8. 写权益快照(trigger=order_filled)
        await snapshot_equity(account_id, trigger=SnapshotTrigger.ORDER_FILLED)

    return order  # FILLED
```

**并发安全:**
- buy 走原子 `UPDATE ... WHERE cash >= total_cost RETURNING` — Postgres 内部对该 row 串行化
- sell 走 `SELECT ... FOR UPDATE` 锁 position row(避免双卖打负)
- 整个流程一个 transaction,失败回滚干净
- 不用应用层 lock / Redis lock / Celery queue,**纯 SQL 原子语义**

### 4. 手续费 + 滑点表(产品负责人决策 2)

```python
# apps/api/app/services/virtual_trading/fees.py
from decimal import Decimal

SLIPPAGE_BPS: dict[Market, int] = {
    "cn": 5,      # A 股流动性 OK,5bp
    "us": 3,      # 美股流动性好,3bp
    "crypto": 10, # 加密波动大 + 撮合粒度小,10bp
}

# 买卖费率(双向不对称 — A股印花税仅卖)
COMMISSION_RATES: dict[Market, dict[OrderSide, Decimal]] = {
    "cn": {
        OrderSide.BUY: Decimal("0.0003"),     # 佣金 0.03%
        OrderSide.SELL: Decimal("0.0013"),    # 佣金 0.03% + 印花税 0.1%
    },
    "us": {
        OrderSide.BUY: Decimal("0"),          # 美股零佣
        OrderSide.SELL: Decimal("0"),
    },
    "crypto": {
        OrderSide.BUY: Decimal("0.001"),      # Binance 现货 0.1%
        OrderSide.SELL: Decimal("0.001"),
    },
}

def calc_commission(market: Market, side: OrderSide, notional_cny: Decimal) -> Decimal:
    rate = COMMISSION_RATES[market][side]
    return (notional_cny * rate).quantize(Decimal("0.0001"))
```

**A 股 1 手 = 100 股** 验证规则:M0 撮合不强制 100 股整数倍(简化),但 UI 默认数量给 100/股(用户可改)。未来如要严格,在 service 层 reject 非整数倍。

### 5. 权益曲线生成

**两条触发线:**

a) **每次成交(`SnapshotTrigger.ORDER_FILLED`)** · 同事务内写一条
   - 现金 = 当前 account.cash_balance_cny
   - 持仓估值 = sum(position.quantity × current_market_price × fx_rate)
   - 权益 = 现金 + 持仓估值
   - 累计已实现 = account.realized_pnl_cny

b) **每日 23:59:30 Celery beat job(`SnapshotTrigger.DAILY`)**
   - 遍历所有 active account(过去 30 天有过订单或持仓)
   - 每个账户写一条 daily snapshot
   - 用最新一个市场可用的 close(收盘价)

**前端展示:**
- `GET /api/v1/virtual/equity-curve?days=30` → 返回最近 30 天所有 snapshot 点
- 简单的折线图(klinecharts 也能用,或者用 recharts / visx · 任选)
- X 轴日期,Y 轴权益 CNY

**M0 不做:**
- 实时 tick 推送权益(WebSocket Task 4-B 范围)
- 多时间粒度(周线 / 月线)

### 6. `/portfolio` 页面 IA

```
┌─────────────────────────────────────────────────────┐
│  Header (复用工作台 Header)                            │
├─────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐│
│  │ VIRTUAL · 模拟 徽章                                ││
│  │ 4 个 KPI 卡(衬线大数据)                          ││
│  │ ┌────────┬────────┬────────┬────────────────┐    ││
│  │ │ 总权益  │ 现金    │ 持仓    │ 累计已实现盈亏  │    ││
│  │ │ 衬线 32 │ 衬线 32 │ 衬线 32 │ 衬线 32 + 涨跌色 │    ││
│  │ └────────┴────────┴────────┴────────────────┘    ││
│  └──────────────────────────────────────────────────┘│
│                                                       │
│  ┌──────────────────────────────────────────────────┐│
│  │  权益曲线(过去 30 天 · X 日期 Y CNY · 中国红 line)││
│  └──────────────────────────────────────────────────┘│
│                                                       │
│  ┌──────────────────────────────────────────────────┐│
│  │  持仓表(table)                                    ││
│  │  symbol │ market │ 数量 │ 均价 │ 现价 │ 浮盈亏  │  ││
│  │  AAPL   │ 美股   │ 10   │ ...  │ ...  │ +1,234¥ │ ││
│  │  600519 │ A 股   │ 100  │ ...  │ ...  │ -567 ¥  │ ││
│  │  [平仓] hover 浮现                                ││
│  └──────────────────────────────────────────────────┘│
│                                                       │
│  ┌──────────────────────────────────────────────────┐│
│  │  最近订单(table · 默认 20 条 · "加载更多")        ││
│  │  时间 │ 方向 │ 标的 │ 数量 │ 成交价 │ 手续费 │ P/L││
│  │  ...                                              ││
│  └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

**视觉:**
- 全页 bg-background
- KPI 卡 bg-cream + 米白 border + 衬线大字
- 权益曲线:中国红 line stroke + 米白底色 + JetBrains Mono 数字 tick
- 涨跌色严格(浮盈红 · 浮亏绿 A股传统)
- VIRTUAL · 模拟 徽章顶部置中

**Header 加 Tab:** Header.tsx 加「自选 K 线 | 我的账户」两个 Tab,默认在 /workbench,切到 /portfolio。

### 7. 工作台右栏「当前标的持仓摘要」

只在 `current_symbol + market` 在用户 portfolio.positions 里时显示。位置:在 `WatchlistColumn` 内,**自选股列表上方**(让正在看图的标的的持仓状态最显眼)。

```
┌─────────────────────────────┐
│ ┌──────────────────────────┐│
│ │ 持仓 · NVDA  [VIRTUAL]    ││
│ │ 数量 10 股                ││
│ │ 均价 ¥1,008.32           ││
│ │ 浮盈 +¥234.56 (+2.32%)   ││
│ │ [一键平仓] 中国红          ││
│ └──────────────────────────┘│
│ ─── 自选股 列表 ↓ ───        │
│ ...                          │
└─────────────────────────────┘
```

**视觉:**
- 帝王金 border-2(虚拟交易元素必带徽章 + 显眼)
- "[一键平仓]" 按钮触发市价单卖出全部持仓
- 平仓 confirm 弹窗(防误触)

### 8. 下单 UI · 右键 K 线 + 数量对话框

**操作流程:**
1. 用户右键 K 线 → ContextMenu 弹出
2. 菜单项:
   - **买入** → 弹「下单数量」对话框
   - **卖出** → 弹对话框(仅在该标的有持仓时显示)
   - **一键平仓** → confirm 后 sell all(仅在持仓 > 0 时显示)
3. 对话框输入:
   - 数量(market 默认值:cn=100 / us=1 / crypto=0.01,用户可改)
   - 估算成本(实时:数量 × 现价 × 汇率 + 手续费,展示给用户)
   - 余额(从 account 拿)
   - 确认下单 button(中国红)
4. 下单结果:
   - 成功:**帝王金 toast** 顶部短暂闪烁("买入 10 NVDA 已成交 · ¥7,260.50")
   - 失败:**中国红 toast** + 拒单原因("余额不足 · 差 ¥X")
   - **绝不用绿色**(避免跟涨跌色冲突)
5. 自动刷新右栏持仓摘要 + 自选股价格

**依赖装:**
- `@radix-ui/react-context-menu`(右键菜单 · shadcn 有现成 context-menu 注册表)
- `sonner`(轻量 toast · shadcn 有现成 sonner 注册表)
- 或者 shadcn `toast` · 任选

### 9. 用户注册时自动建虚拟账户

跟 0007 watchlist 的 demo_prefilled 不同,虚拟账户必须**一旦有 user 就建**:

**实现位置:** 邮箱验证完成(`POST /api/v1/auth/verify`)成功后,在同事务内创建 `VirtualAccount`(`cash_balance_cny=1000000`)。

**幂等保护:** `UniqueConstraint(user_id)` 兜底 · `INSERT ... ON CONFLICT DO NOTHING`。

**为什么挂 verify 而不是 register:**
- 跟 0007 watchlist demo_prefilled 不同:那个是「展示性数据」可以懒填,这个是「业务实体」必须有
- 但 unverified 用户都不能登录,所以 register 时也可以建
- 选 verify 是因为:跟 lazy-fill demo symbols 时机一致(都是首次有意义访问),代码组织上更整齐
- **备选:**也可以挂 register,然后 verify 时检查不存在再建。但 register 一旦失败,孤儿账户清理麻烦。verify 是更稳定的"首次成功登录"信号。

### 10. REST 路由

| Method | Path | 描述 |
|---|---|---|
| GET | `/api/v1/virtual/account` | 当前用户账户基础信息(现金 + 累计已实现) |
| GET | `/api/v1/virtual/portfolio` | 聚合 · account + positions + 估值 + total_equity |
| POST | `/api/v1/virtual/orders` | 下市价单 `{symbol, market, side, quantity}` |
| GET | `/api/v1/virtual/orders?limit=20&before_id=...` | 订单流水 · 翻页用 cursor |
| GET | `/api/v1/virtual/equity-curve?days=30` | 权益曲线点列表 |

全部用 `CurrentUserDep` → SQL `WHERE user_id = ?` 强隔离 + CRUD 范围 = 该用户的 account 子树。

**`POST /orders` 错误码:**
- 200 + `status=filled` · 成功
- 200 + `status=rejected` + `reject_reason` · 业务拒单(余额不足 / 持仓不足 / 无报价)
- 400 · 参数非法(quantity ≤ 0 等)
- 401 · 未登录
- 503 · 上游报价不可达(应该极少)

返回 200 而非 4xx 用于业务拒单的原因:**拒单是预期路径**,客户端按订单状态分支处理,而非异常处理。

### 11. 并发安全总结

| 风险 | 处理 |
|---|---|
| 同账户同时下两买单(余额不足以同时支付) | 原子 `UPDATE WHERE cash >= cost RETURNING` · 第二单 reject |
| 同账户同时卖同一持仓(打负) | `SELECT FOR UPDATE` position row + 检查 quantity >= sell_qty |
| 同账户同时下买 + 卖同标的(position 竞争) | 都走 transaction · Postgres row lock 自动串行 |
| 双标签同时访问 /workbench → 双 POST /orders | 同上 · 数据库层兜底 |
| 注册自动建账户竞态 | `UniqueConstraint(user_id)` + `INSERT ON CONFLICT DO NOTHING` |

**不用** Redis lock / Celery queue / 应用层 mutex — **纯 SQL 原子语义**,简单可靠。

## Checkpoint 切分 · P / Q / R

按 G/H/I 和 O 的粒度,3 个 Checkpoint:

### Checkpoint P · 测试基建 + N7 auth 回补 + 虚拟交易 fixtures

| Sub | 范围 | 估时 |
|---|---|---|
| P1 | `tests/conftest.py` · async db engine + transaction rollback per test + FastAPI TestClient | 30 min |
| P2 | `tests/factories.py` · factory_boy + faker · UserFactory / WatchlistItemFactory / VirtualAccountFactory(占位) | 20 min |
| P3 | N7 回补 · `tests/api/test_auth.py` · register / login / verify / resend / me · 6 个场景 | 1h |
| P4 | watchlist 路由 pytest 补 · 4 路由 · 重复 / 越权 / lazy-fill / reorder 失败回滚 | 30 min |
| P5 | P 自验 · `pytest -v` 全过 + commit + tag checkpoint-p | 15 min |
| **小计** | | **~2.5h** |

### Checkpoint Q · 虚拟交易后端 + 撮合 + 权益快照

| Sub | 范围 | 估时 |
|---|---|---|
| Q1 | 4 个 model + alembic migration | 45 min |
| Q2 | `services/virtual_trading/fees.py` + `fx.py` + `engine.py`(撮合核心) | 1.5h |
| Q3 | `services/virtual_trading/equity.py` · 权益快照写入 + 聚合 portfolio | 45 min |
| Q4 | REST 路由 5 个 · /virtual/account, /portfolio, /orders POST/GET, /equity-curve | 1.5h |
| Q5 | verify endpoint hook · 自动建账户(同事务 + ON CONFLICT DO NOTHING) | 20 min |
| Q6 | Celery beat · 每日 23:59:30 daily snapshot job | 30 min |
| Q7 | pytest · 撮合数值正确(滑点 + 手续费) / 余额检查 / 并发 race(2 个并发 buy)/ 持仓不足 reject | 1.5h |
| Q8 | smoke test curl · register → verify → buy NVDA → sell → check portfolio | 30 min |
| Q9 | Q 自验 + commit + tag checkpoint-q | 30 min |
| **小计** | | **~7h** |

### Checkpoint R · 虚拟交易前端 + /portfolio 页 + 右键下单

| Sub | 范围 | 估时 |
|---|---|---|
| R1 | 装 `@radix-ui/react-context-menu` + `sonner` + shadcn 注册 | 15 min |
| R2 | `lib/api/virtual.ts` + 5 个 hook(account / portfolio / orders / placeOrder / equityCurve) | 1h |
| R3 | `/portfolio` 页 · 布局 + 4 KPI 卡 + 权益曲线(用 klinecharts line 或 recharts) | 2h |
| R4 | 持仓表 + 订单表 + 平仓按钮 + 翻页 | 1h |
| R5 | 右键 K 线 ContextMenu + 下单对话框(数量输入 + 估算成本)| 1.5h |
| R6 | 工作台右栏「当前标的持仓摘要」嵌入(帝王金边 + 一键平仓) | 1h |
| R7 | 下单反馈 toast(中国红 失败 / 帝王金 成功 · **绝不用绿色**) | 30 min |
| R8 | Header 加 Tab「自选 K 线 / 我的账户」 | 20 min |
| R9 | playwright 截图 · 6 张 · /portfolio 全景 / 持仓 / 订单 / 右键菜单 / 下单对话框 / 成功 toast | 1h |
| R10 | R 自验 + commits + tag checkpoint-r + 总汇报 | 45 min |
| **小计** | | **~9h** |

**P + Q + R 合计 ~18.5h**(可能上下浮动 ±2h)。

## 撤销路径

| 改动 | 撤销路径 |
|---|---|
| **多账户(M2+)** | account 表已有 user_id FK(非 unique),改 UniqueConstraint 为复合索引 + 加 `account_name` 字段即可 |
| **多币种持仓(M2+)** | account 加 `wallets JSONB` 或拆 `account_wallet` 表 + 撮合服务支持币种参数 |
| **真实汇率(M1)** | 加 `exchange_rate` 表 + worker · `FX_RATES_CNY` 改为 db 查询 |
| **限价单(M1)** | order_type Enum 加 `LIMIT`,加 `limit_price` 字段;撮合服务对未成交订单进 Celery delayed task |
| **杠杆 / 做空(M2+ 或永不)** | position.quantity 改 signed + margin_account 表 · **产品红线考虑**,可能永不做 |
| **WebSocket 实时浮盈推送** | Task 4-B 落地后,把 useQueries 的 polling 改为 ws subscribe |

## 已知边界(M0 接受)

- **手续费按总金额算,不按笔最小费用** — 真实券商有 5 元最低,M0 简化
- **A 股不强制 100 股整数倍** — 撮合允许任意股数,UI 默认填 100 提示用户
- **无 T+1 限制** — 真实 A 股买入当天不能卖,M0 自由(教学体验优先)
- **无开盘/收盘时段判断** — 任意时间可下单(用最新 close 作为参考价)
- **汇率静态 7.2** — M0 demo 用户不在意,M1 改

## 红线沿用项目本质

- **永不接真实下单** · 任何场景都用 `services/virtual_trading/engine.py` 内的撮合,**不接券商接口**
- **AI 输出必带「仅供参考,不构成投资建议」** · 已在视觉系统 + token,Task 5 实装时所有交易卡片底部带这行小字
- **VIRTUAL · 模拟 徽章** · 持仓摘要 / KPI 卡 / 订单成功 toast 全部必带

## 自主决策待审

下面 8 条是我准备直接落 commit 的设计,如有疑问请反馈:

1. **单货币 CNY + 静态汇率 USD/USDT → 7.2** · 简化 M0 心智模型
2. **持仓全部清仓 → 硬删 position row** · 不软删,realized P/L 走 order 流水 + account 累计
3. **`order_type` Enum 留接口但 M0 只有 'market'** · 未来加 LIMIT 不改表结构
4. **业务拒单返回 200 + `status=rejected`** · 不返 4xx,客户端按状态字段分支
5. **下单反馈用 `sonner` toast · 帝王金成功 / 中国红失败 · 绝不绿色**
6. **右键 K 线 ContextMenu(@radix-ui/react-context-menu)** · 比 Buy/Sell 大按钮更原生
7. **工作台右栏「当前持仓」嵌在自选股上方** · 让正在看图的标的最显眼
8. **测试基建用 factory_boy + faker** · 跟 watchlist + auth 共用 fixtures,一次到位

如果某条有不同想法,告诉我;否则按上面 P/Q/R 切分跑。

## 备注

- Task 5 的「AI 决策卡」右栏占位(M1)沿用 H5 阶段已就位的占位,不在本 ADR 范围
- /portfolio 没有自己的 AI 决策模块(账户视图是事实陈述,不是预测)
- 飞书 / TG 推送(Task 6)依赖订单 filled 事件,Q4 路由实装时**埋好 hook 点**(不实装推送,只留接口),Task 6 直接接
