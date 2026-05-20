# 0008 · 虚拟交易(Virtual Trading)设计

## 状态
Approved (2026-05-20 v2 · 三独立子账户方案 · 删汇率,见末尾「修订记录」)

## 上下文

Task 5(M0 验收链路第 3 步:陌生人能下虚拟单)启动。

**产品负责人核心决策(v2 修订):**

放弃「单货币 CNY + 静态汇率 7.2」方案 · **彻底删掉所有汇率概念**。
改为「三个独立子账户,各用各的货币,绝不折算」。

**6 条已拍板细节:**

1. **三子账户互不互转资金** — 一旦能互转就需要汇率,破坏清晰性。某市场亏光了就是亏光了 — 这正是模拟交易该教的教训
2. **不给默认金额,用户注册后自己填** — 在 `/settings/wallet` 设置页填入每个市场想用多少;未设置 = 该市场按钮 disabled + 引导跳设置页
3. **账户/曲线按「用户实际有无」动态显示** — 只玩 A 股的用户:`/portfolio` 只一条 A 股曲线 + 一个 A 股账户卡;完全没设置 = 空态卡
4. **工作台顶部「当前市场 = 当前钱包」** — 顶部市场 Tab 切换时,顶部显示的「可用资金 / 持仓摘要」跟着切到对应市场子账户;右栏持仓摘要同理
5. **手续费/滑点用各市场自己的货币** — A 股扣 CNY / 美股零佣 / 加密扣 USDT,无折算
6. **持仓清仓改软删 · `closed_at`** — `VirtualPosition.closed_at` nullable,清仓时填 now,realized_pnl 一次性算好写到 position row · 复盘价值优先

**M0 范围(产品决策保留):**
- 必做:手动市价单 + 持仓 + 盈亏 + 权益曲线 + 余额 + 设置页
- 不做:限价单/止损单(M1)、策略自动交易(M2)、杠杆/做空(M2+ 或永不)、多账户

**红线沿用项目本质:**仅虚拟资金 · 永不接真实下单。

## 决策

### 1. 三独立子账户 · 不折算 · 不混算 · 不展示假总数

**核心原则:** 凡是要展示给用户的金额,**宁可三个真数字并列,不要一个折算的假数字。**

**总账户摘要展示(顶部 / portfolio 头部):**

```
✅  ¥500,000  +  $98,234  +  100,000 USDT      ← 三个独立数字并列
❌  ¥1,720,123(约等于...)                       ← 永不做这种折算
```

**只激活了 A 股的用户:**

```
✅  ¥500,000                                    ← 只显示已激活市场
❌  ¥500,000 + $0 + 0 USDT                      ← 不要 0 占位
```

理由:静态汇率是谎报数字,会把假汇率噪音混进盈亏。三个市场本来就是三个独立资金池,分开记最诚实,呼应产品定位 — 用户练的是「某个市场里的交易能力」,不是「全球资产配置」。

### 2. Schema · 4 张表 · 三子账户模型

```python
# apps/api/app/models/virtual.py
from decimal import Decimal
from enum import StrEnum

class Currency(StrEnum):
    CNY = "CNY"
    USD = "USD"
    USDT = "USDT"

MARKET_CURRENCY: dict[Market, Currency] = {
    "cn": Currency.CNY,
    "us": Currency.USD,
    "crypto": Currency.USDT,
}


class VirtualAccount(Base):
    """用户 × 市场 一行 · lazy create(用户在设置页填金额时才 INSERT)。

    存在 = 已激活;不存在 = 未激活(对应市场按钮 disabled)。
    """
    __tablename__ = "virtual_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # cn / us / crypto
    currency: Mapped[Currency] = mapped_column(
        Enum(Currency, name="currency"), nullable=False,
    )
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0"),
    )
    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "market", name="uq_virtual_account_user_market"),
        Index("ix_virtual_account_user", "user_id"),
    )


class VirtualPosition(Base):
    """持仓 · 软删 · closed_at IS NULL 为活仓,NOT NULL 为历史。

    清仓时写入 closed_at + realized_pnl,不删除 row(复盘价值)。
    """
    __tablename__ = "virtual_position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    # 当前持仓量(部分平仓时减少;全部平仓时归 0 + closed_at 填值)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 加权平均成本(原币种,不转 CNY)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # 已实现盈亏(原币种,清仓时一次性算好)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # partial unique:同账户同标的最多一个活仓(closed_at IS NULL)
        # 历史仓可有多条(每次"完整买卖回合"一条)
        Index(
            "uq_virtual_position_active",
            "account_id", "symbol",
            unique=True,
            postgresql_where=text("closed_at IS NULL"),
        ),
        Index("ix_virtual_position_account_closed", "account_id", "closed_at"),
    )


class VirtualOrder(Base):
    """订单流水 · 不可变 · status: filled / rejected。"""
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
    )
    order_type: Mapped[OrderType] = mapped_column(
        Enum(OrderType, name="order_type"), nullable=False, default=OrderType.MARKET,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))  # 成交价(原币种,rejected 时 NULL)
    notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))  # quantity × price
    commission: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    slippage_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))  # 滑点损耗 = (fill-market)×qty
    # sell 时填(本笔贡献的已实现 in market currency)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), nullable=False,
    )
    reject_reason: Mapped[str | None] = mapped_column(String(128))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_virtual_order_account_placed", "account_id", "placed_at"),
    )


class VirtualEquitySnapshot(Base):
    """权益快照 · 每市场一条曲线。"""
    __tablename__ = "virtual_equity_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("virtual_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # 冗余,加速 time-series 查询
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    positions_value: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)  # cash + positions_value
    realized_pnl_cumulative: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    trigger_kind: Mapped[SnapshotTrigger] = mapped_column(
        Enum(SnapshotTrigger, name="snapshot_trigger"), nullable=False,
    )
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

**为什么选 lazy create(方案 A)而不是 is_activated 字段(方案 B):**

| 维度 | 方案 A · lazy create | 方案 B · 3 行 + is_activated |
|---|---|---|
| 「该用户激活了哪些市场」查询 | `SELECT market FROM virtual_account WHERE user_id=?` | 加 `WHERE is_activated=true` |
| 「能交易 X 市场吗」查询 | `EXISTS(SELECT 1 WHERE user_id=? AND market=?)` | `WHERE user_id=? AND market=? AND is_activated=true` |
| 路由代码 | 404 if not exists | 200 + activated=false |
| 注册时数据库写入 | 0 行 | 3 行占位 |
| 「激活某市场」操作 | `INSERT ON CONFLICT DO UPDATE` | `UPDATE SET is_activated=true, initial_capital=...` |
| 数据库自然语义 | 「行存在 = 真激活」 | 「is_activated 列控制」(列冗余) |

**选 A:** 数据库结构自然表达激活状态,所有查询都不需要额外 WHERE 过滤,SQL 短一行,长期维护更直观。
重置市场资金时用 SQL `INSERT ... ON CONFLICT (user_id, market) DO UPDATE SET initial_capital=..., cash_balance=..., realized_pnl=0` 一句搞定。

### 3. 撮合逻辑 · 市价单(M0 唯一)

**输入:** `(user_id, symbol, market, side, quantity)`

```python
async def place_market_order(user_id, symbol, market, side, quantity):
    async with db.begin():
        # 1. 找子账户(未激活市场直接拒)
        account = await db.scalar(
            select(VirtualAccount).where(
                VirtualAccount.user_id == user_id,
                VirtualAccount.market == market,
            )
        )
        if account is None:
            return reject("该市场虚拟资金未设置 · 请先去个人设置页填写")

        # 2. 拿当前市场价(走 cache-aside,跟 watchlist quote 同源)
        market_price = await get_latest_close(symbol, market)
        if market_price is None:
            return reject("无最新报价 · 标的可能停牌或数据未到达")

        # 3. 滑点 → 成交价(原币种)
        slip_bp = SLIPPAGE_BPS[market]  # cn=5 / us=3 / crypto=10
        fill_price = (
            market_price * (Decimal("1") + Decimal(slip_bp) / Decimal("10000"))
            if side == OrderSide.BUY
            else market_price * (Decimal("1") - Decimal(slip_bp) / Decimal("10000"))
        )
        notional = quantity * fill_price  # 原币种
        commission = calc_commission(market, side, notional)
        slippage_cost = abs(fill_price - market_price) * quantity

        if side == OrderSide.BUY:
            total_cost = notional + commission
            # 4a. 原子扣钱(WHERE cash >= total_cost)
            r = await db.execute(
                update(VirtualAccount)
                .where(
                    VirtualAccount.id == account.id,
                    VirtualAccount.cash_balance >= total_cost,
                )
                .values(cash_balance=VirtualAccount.cash_balance - total_cost)
                .returning(VirtualAccount.id)
            )
            if r.scalar_one_or_none() is None:
                return reject(
                    f"余额不足 · 需要 {format_money(total_cost, account.currency)}",
                )
            # 5a. UPSERT 活仓(加权平均成本)
            await upsert_active_position_buy(
                account.id, symbol, market, quantity, fill_price,
            )
            realized_pnl_this = None

        else:  # SELL
            # 4b. 锁活仓 + 减持仓 + 算 realized
            position = await db.scalar(
                select(VirtualPosition)
                .where(
                    VirtualPosition.account_id == account.id,
                    VirtualPosition.symbol == symbol,
                    VirtualPosition.closed_at.is_(None),
                )
                .with_for_update(),
            )
            if position is None or position.quantity < quantity:
                return reject("持仓不足")

            proceeds = notional - commission
            realized_pnl_this = (
                (fill_price - position.avg_entry_price) * quantity - commission
            )

            new_qty = position.quantity - quantity
            if new_qty == 0:
                # 完整平仓 → 软删 + realized_pnl 一次性写
                position.quantity = Decimal("0")
                position.closed_at = datetime.now(UTC)
                position.realized_pnl = (
                    (position.realized_pnl or Decimal("0")) + realized_pnl_this
                )
            else:
                position.quantity = new_qty
                # 部分平仓:累积 realized 到 position(供复盘时看到全程)
                position.realized_pnl = (
                    (position.realized_pnl or Decimal("0")) + realized_pnl_this
                )

            # 5b. 加钱 + 累计 realized
            await db.execute(
                update(VirtualAccount)
                .where(VirtualAccount.id == account.id)
                .values(
                    cash_balance=VirtualAccount.cash_balance + proceeds,
                    realized_pnl=VirtualAccount.realized_pnl + realized_pnl_this,
                )
            )

        # 6. 写订单流水
        order = VirtualOrder(
            account_id=account.id, symbol=symbol, market=market,
            side=side, order_type=OrderType.MARKET,
            quantity=quantity, price=fill_price, notional=notional,
            commission=commission, slippage_cost=slippage_cost,
            realized_pnl=realized_pnl_this,
            status=OrderStatus.FILLED, filled_at=datetime.now(UTC),
        )
        db.add(order)

        # 7. 写权益快照(trigger=order_filled)
        await snapshot_equity(account, trigger=SnapshotTrigger.ORDER_FILLED)

    return order  # FILLED
```

**并发安全:**
- BUY 走原子 `UPDATE WHERE cash >= total_cost RETURNING` · Postgres 内部对该 row 串行化
- SELL 走 `SELECT ... FOR UPDATE` 锁活仓 row · 防止双卖打负
- 整个流程一个 transaction,失败回滚干净
- 不用应用层 lock / Redis lock / Celery queue · **纯 SQL 原子语义**

### 4. 手续费 + 滑点(原币种)

```python
# apps/api/app/services/virtual_trading/fees.py
from decimal import Decimal

SLIPPAGE_BPS: dict[Market, int] = {
    "cn": 5,
    "us": 3,
    "crypto": 10,
}

COMMISSION_RATES: dict[Market, dict[OrderSide, Decimal]] = {
    "cn": {
        OrderSide.BUY: Decimal("0.0003"),   # 佣金
        OrderSide.SELL: Decimal("0.0013"),  # 佣金 + 印花税
    },
    "us": {
        OrderSide.BUY: Decimal("0"),
        OrderSide.SELL: Decimal("0"),
    },
    "crypto": {
        OrderSide.BUY: Decimal("0.001"),
        OrderSide.SELL: Decimal("0.001"),
    },
}

def calc_commission(market: Market, side: OrderSide, notional: Decimal) -> Decimal:
    rate = COMMISSION_RATES[market][side]
    return (notional * rate).quantize(Decimal("0.0001"))
```

注意:手续费用的是「原币种 notional」算出来的「原币种 commission」。不存在跨币种乘法。

### 5. 重置子账户(用户改金额时)

`PUT /api/v1/virtual/accounts/{market}` 入参 `{initial_capital}`:

- **首次激活:** INSERT(initial_capital=X, cash_balance=X, realized_pnl=0)
- **重置:** 用户改金额时:
  - 二次确认弹窗:「这会清空该市场的当前持仓和盈亏,确定?」
  - 后端:
    - `DELETE FROM virtual_position WHERE account_id=? AND closed_at IS NULL`(硬删活仓 · 软删的意义在「完整买卖回合」复盘,reset 直接清零)
    - **保留**历史已平仓 position(closed_at NOT NULL)和订单流水(VirtualOrder)— 复盘价值
    - **删除** 该 account 的 equity_snapshot(新曲线从重置点开始,旧点不展示)
    - UPDATE account SET initial_capital=X, cash_balance=X, realized_pnl=0
- 用 `INSERT ... ON CONFLICT (user_id, market) DO UPDATE SET ...` SQL 句完成

### 6. 权益曲线生成

**两条触发线:**

a) **每次成交(`SnapshotTrigger.ORDER_FILLED`)** · 同事务内写一条
   - cash = account.cash_balance
   - positions_value = sum(active_position.quantity × current_market_price)(原币种)
   - equity = cash + positions_value
   - realized_pnl_cumulative = account.realized_pnl

b) **每日 23:59:30 Celery beat job(`SnapshotTrigger.DAILY`)**
   - 遍历所有激活 account(过去 7 天有 snapshot 或 active position)
   - 每个 account 写一条 daily snapshot

**前端展示(/portfolio):**
- 用户激活了几个市场 → 显示几条独立曲线(各自原币种 Y 轴)
- `GET /api/v1/virtual/equity-curves` → 按 market 分组返回
- 不要把三条曲线叠成一张图 · 各画各的(并列卡片)

### 7. `/settings/wallet` 设置页 IA

```
┌────────────────────────────────────────────────┐
│  Header (导航 / 个人设置)                       │
├────────────────────────────────────────────────┤
│  个人设置 · 虚拟资金                              │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ 🇨🇳 A 股 · CNY                            │   │
│  │ ┌────────────────────────┐ [激活并保存]    │   │
│  │ │ ¥                       │                │   │
│  │ └────────────────────────┘                 │   │
│  │ ⚠ 未设置 · 设置后才能在 A 股下单            │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ 🇺🇸 美股 · USD                            │   │
│  │ ┌────────────────────────┐ [重置(二次确认)] │
│  │ │ $ 100,000               │                │   │
│  │ └────────────────────────┘                 │   │
│  │ ✓ 已激活 · 可用 $98,234 · 持仓 1 笔        │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  ┌──────────────────────────────────────────┐   │
│  │ ₿ 加密 · USDT                              │   │
│  │ ┌────────────────────────┐ [激活并保存]    │   │
│  │ │ USDT                    │                │   │
│  │ └────────────────────────┘                 │   │
│  │ ⚠ 未设置                                   │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  顶部帝王金 VIRTUAL · 模拟 徽章                  │
│  底部小字「模拟交易,不构成投资建议」            │
└────────────────────────────────────────────────┘
```

**输入校验:**
- 必须正数 · 上限 ¥10^9 / $10^9 / 10^9 USDT(给用户上限保护,防误填 100 亿)
- 下限 1(¥1 / $1 / 1 USDT — 太小没意义但允许)
- 用户提交 → POST 完显示确认 toast(帝王金)

### 8. 工作台变化

#### 8.1 顶部「当前钱包」(随 market Tab 切换)

```
┌──────────────────────────────────────────────────────────┐
│ 点金 Midas       A 股 | 美股 | 加密                         │
│            可用 ¥412,567   持仓 ¥87,123   累计盈亏 +¥3,210│
└──────────────────────────────────────────────────────────┘
```

- 切换 market Tab → 立刻切换显示的「可用 / 持仓 / 累计盈亏」(数字 + 货币符号)
- 该市场未激活 → 显示「未设置该市场虚拟资金 [去设置]」 中国红 link

#### 8.2 顶部「买入」「卖出」按钮(主下单入口)

放在「symbol 名称 / 价格 / 周期切换器」那一行:

```
BTC/USDT  $98,234   ▼-0.46%   [15分][1时][日K][周K]   [买入][卖出]
```

- 未激活市场 · 两个按钮 disabled · hover 提示「请先在设置页填写该市场虚拟资金」+ 点 disabled 按钮跳设置页
- 激活市场 · 中国红「买入」+ 墨绿「卖出」(语义反着但是双方向操作不用涨跌色,改为「买中国红 / 卖深灰」更安全)
  - **决定**:都用中国红主色,通过文字「买入」/「卖出」区分,**不用涨绿跌红色域**(避免跟 K 线涨跌色冲突)
  - 「卖入」按钮加 outline 不填充,差异化

#### 8.3 下单确认模态(必经)

点「买入」/「卖出」/ 右键菜单 / Cmd+B / Cmd+S → 弹模态(不直接下单):

```
┌────────────────────────────────────────────┐
│  [VIRTUAL · 模拟] 帝王金徽章顶部置中           │
│                                              │
│  确认下单                                    │
│                                              │
│  标的     NVDA · 美股                        │
│  方向     买入(中国红)                       │
│  数量     [ 10 ] 股   ← 可调整               │
│                                              │
│  预估成交价  $140.04(含 3bp 滑点)           │
│  预估手续费  $0.00(美股零佣)                │
│  滑点成本    $0.42                           │
│  ───────────────────────                    │
│  预估总成本  $1,400.84                       │
│                                              │
│  可用余额    $98,234.00                      │
│                                              │
│  [ 取消 ]              [ 确认买入 ]          │
│                          ↑ 中国红主按钮       │
│                                              │
│  本次为模拟交易,不构成投资建议                │
└────────────────────────────────────────────┘
```

- 用户改数量 → 实时重算预估成本
- 确认按钮 disabled 当 quantity ≤ 0 或预估总成本 > 可用余额
- 取消 / Esc → 关闭模态
- 确认 → POST /orders → 关模态 + sonner toast 反馈

#### 8.4 三个下单入口

1. **主入口** · 工作台顶部按钮(8.2)
2. **快捷入口** · 右键 K 线 ContextMenu(`@radix-ui/react-context-menu`)
   - 菜单项:「买入 NVDA」/「卖出 NVDA」(只在有持仓时显示)/ 一键平仓
3. **老手入口** · `⌘B` 买 / `⌘S` 卖 快捷键

三者都触发同一个确认模态(8.3)· 模态是必经,不能跳过。

#### 8.5 右栏持仓摘要(只显示当前 market)

```
┌─────────────────────────────┐
│ ╔═════════════════════════╗ │
│ ║ [VIRTUAL] NVDA           ║ │ ← 帝王金 border
│ ║ 持仓 10 股                ║ │
│ ║ 均价 $140.04             ║ │
│ ║ 现价 $142.30             ║ │
│ ║ 浮盈 +$22.60 (+1.6%)     ║ │ ← 朱红(涨)/ 墨绿(跌)
│ ║ [一键平仓]                ║ │ ← 中国红按钮
│ ╚═════════════════════════╝ │
│ ─── 自选股 ──────────────── │
│  ...                         │
│ ─── AI 决策卡 占位 (M1) ──── │
└─────────────────────────────┘
```

- 当前 market 切换 → 持仓摘要切换(NVDA 在 us 市场,切到 cn 就不显示;cn 市场看 600519 才显示其持仓)
- 用户当前选中的 symbol 不是该市场任何活仓 → 不显示此卡(留空)

### 9. `/portfolio` 页 IA · 动态显示已激活市场

```
┌──────────────────────────────────────────────────────────┐
│  Header                                                   │
├──────────────────────────────────────────────────────────┤
│  [VIRTUAL · 模拟] 帝王金徽章                                │
│                                                            │
│  ── 用户没激活任何市场 ──                                  │
│  ┌────────────────────────────────────────────────────┐   │
│  │  📊 (灰色 + 米白卡)                                  │   │
│  │  你还没有设置任何市场的虚拟资金                       │   │
│  │  设置后即可在该市场练手 · M0 demo 期不收任何费用      │   │
│  │  [ 去设置页 ] 中国红 CTA                              │   │
│  └────────────────────────────────────────────────────┘   │
│                                                            │
│  ── 用户激活了 N 个市场 → 显示 N 张账户卡 + N 条曲线 ──     │
│                                                            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                    │
│  │ A 股 CNY │  │ 美股 USD│  │ 加密 USDT│                    │
│  │ ¥500K   │  │ $98K   │  │ 100K USDT│                    │
│  │ +1.2%   │  │ -2.1%  │  │ +5.3%   │                    │
│  └─────────┘  └─────────┘  └─────────┘                    │
│                                                            │
│  权益曲线(每市场一个 chart,纵向并排或网格)               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │ A 股 ¥曲线  │  │ US $曲线   │  │加密 USDT 曲线│           │
│  │ recharts    │  │ recharts   │  │ recharts    │           │
│  └────────────┘  └────────────┘  └────────────┘           │
│                                                            │
│  ── 活仓表(全部市场聚合 · market 列区分)──                │
│  symbol | market | 数量 | 均价 | 现价 | 浮盈亏 | [平仓]   │
│                                                            │
│  ── 历史持仓(closed_at NOT NULL · 复盘)──                 │
│  symbol | market | 开仓 | 平仓 | 已实现盈亏                │
│                                                            │
│  ── 订单流水(默认 20 条 · 翻页)──                         │
│  时间 | 方向 | 标的 | 数量 | 成交价 | 手续费 | P/L         │
└──────────────────────────────────────────────────────────┘
```

**关键交互:**
- 用户激活 0 个市场 → 整页只一个空态卡 + CTA
- 用户激活 1 个市场 → 1 张账户卡 + 1 条曲线(占满宽度) · 不留 3 个槽位
- 用户激活 N 个 → N 张卡 + N 条曲线
- 卡 / 曲线宽度自适应(grid `auto-fit`)

### 10. REST 路由

| Method | Path | 说明 |
|---|---|---|
| GET | `/api/v1/virtual/accounts` | 当前用户全部已激活账户列表(0~3 个) |
| GET | `/api/v1/virtual/accounts/{market}` | 单市场账户详情(404 if 未激活) |
| PUT | `/api/v1/virtual/accounts/{market}` | 激活 / 重置(input `{initial_capital}`) |
| GET | `/api/v1/virtual/portfolio` | 聚合 · accounts + 活仓 + 实时估值,按市场分组 |
| POST | `/api/v1/virtual/orders` | 下市价单 `{symbol, market, side, quantity}` |
| GET | `/api/v1/virtual/orders?market=cn&limit=20&before_id=...` | 订单流水 cursor 翻页 |
| GET | `/api/v1/virtual/positions?include_closed=true` | 持仓列表(默认只活仓) |
| GET | `/api/v1/virtual/equity-curves?days=30` | 全部已激活市场的曲线点(按市场分组) |

**全部用 `CurrentUserDep` + SQL `WHERE user_id` 强隔离。**

**业务拒单返回 200 + `status=rejected` + `reject_reason`:**
- 「该市场虚拟资金未设置」
- 「余额不足 · 需要 ¥X」
- 「持仓不足」
- 「无最新报价」

400 仅用于参数级别错误(quantity ≤ 0,unknown market 字符串等)。

### 11. 并发安全总结

| 场景 | 处理 |
|---|---|
| 同账户同时下两买单 | 原子 `UPDATE WHERE cash >= cost RETURNING` · 第二单 reject |
| 同账户同时卖同一活仓 | `SELECT FOR UPDATE` 锁活仓 row · 第二单 reject |
| 用户重置市场金额(并发与下单) | PUT /accounts/{market} 走单事务 + DELETE 活仓 + UPDATE account;同时下单走 SELECT 看到旧数据,UPDATE 时 WHERE 子句失败 → 拒单(误差可接受) |
| 重复激活同一市场 | UniqueConstraint(user_id, market) + ON CONFLICT 兜底 |
| 双标签同时访问 | 每个请求独立事务,Postgres 自动处理 |

不用 Redis lock / Celery queue / 应用层 mutex — **纯 SQL 原子语义**。

### 12. 自主决策(8 条)

| # | 决策 | 理由 |
|---|---|---|
| 1 | **lazy create**(方案 A)| 数据库自然语义 + 查询代码短 + 重置用 ON CONFLICT 一行搞定 |
| 2 | **持仓软删 closed_at + realized_pnl 写 position row** | 用户复盘"这笔买卖赚亏"直接看 position row,不需 join 订单 |
| 3 | **重置市场资金 → 删活仓 + 删 equity_snapshot · 保留订单 + 历史持仓** | 资金重置 = 重新开局,曲线/活仓清零;订单/历史持仓是事实陈述,留作复盘 |
| 4 | **业务拒单返回 200 + `status=rejected`** | 拒单是预期路径,不用异常处理 |
| 5 | **买入卖出按钮都用中国红主色**(不用涨绿跌红)| 双方向操作,涨跌色保留给行情 · 买中国红填充 / 卖中国红 outline 区分 |
| 6 | **下单确认模态必经 · 三入口共用同一模态** | 防误触 + 三个入口体验一致 |
| 7 | **/portfolio 多市场曲线纵向并排,不叠图** | 不同币种不可叠加,叠图就是骗 Y 轴 |
| 8 | **测试基建用 factory_boy + faker · P 阶段一次铺好** | auth + watchlist + virtual 三套测试共用 fixtures |

## Checkpoint 切分 · P / Q / R

### Checkpoint P · 测试基建 + N7 auth 回补 + watchlist 测试补

| Sub | 范围 | 估时 |
|---|---|---|
| P1 | `tests/conftest.py` · async db engine + transaction rollback per test + FastAPI TestClient | 30 min |
| P2 | `tests/factories.py` · factory_boy + faker · UserFactory / VerificationTokenFactory / WatchlistItemFactory / VirtualAccountFactory(占位)| 30 min |
| P3 | N7 回补 · `tests/api/test_auth.py` · register / login / verify / resend / me · 6 个场景 | 1h |
| P4 | watchlist 路由 pytest 补 · 4 路由 · 重复 / 越权 / lazy-fill / reorder 失败回滚 | 30 min |
| P5 | P 自验 · `pytest -v` 全过 + commit + tag `checkpoint-p` | 15 min |
| **小计** | | **~2.75h** |

### Checkpoint Q · 虚拟交易后端 · 三子账户

| Sub | 范围 | 估时 |
|---|---|---|
| Q1 | 4 个 model + alembic migration(包括 partial unique on closed_at IS NULL) | 1h |
| Q2 | `services/virtual_trading/fees.py` + `engine.py` 撮合核心(三子账户,无 FX)| 1.5h |
| Q3 | `services/virtual_trading/equity.py` · 单市场快照 + 多市场 portfolio 聚合 | 1h |
| Q4 | REST 8 路由(/accounts × 3 + /portfolio + /orders × 2 + /positions + /equity-curves) | 1.5h |
| Q5 | Celery beat · 每日 23:59:30 daily snapshot · 遍历活跃 account | 30 min |
| Q6 | pytest · 撮合数值正确 / 余额检查 / 并发 race / 软删 closed_at / 重置市场清持仓 | 1.5h |
| Q7 | smoke test curl · 设置 us 账户 → buy NVDA → sell 部分 → sell 全部 → 查 portfolio | 30 min |
| Q8 | Q 自验 + commit + tag `checkpoint-q` | 30 min |
| **小计** | | **~7.5h** |

### Checkpoint R · 虚拟交易前端 · 设置页 + 下单 UI + /portfolio

| Sub | 范围 | 估时 |
|---|---|---|
| R1 | 装 `@radix-ui/react-context-menu` + `sonner` + shadcn `context-menu` / `sonner` 注册 | 20 min |
| R2 | `lib/api/virtual.ts` + hooks(useAccounts / usePortfolio / usePlaceOrder / useOrders / useEquityCurves) | 1h |
| R3 | `/settings/wallet` 页 · 三市场卡 · 输入校验 · 重置二次确认 · 激活成功 toast | 1.5h |
| R4 | 工作台顶部钱包指示(切换 market 跟着切货币 + 数字) + 未激活提示 + 跳设置页 link | 1h |
| R5 | 工作台顶部「买入 / 卖出」按钮 + disabled 态 + hover 提示 | 30 min |
| R6 | 下单 confirm 模态(7 字段 + 实时算成本 + VIRTUAL 徽章 + 中国红主按钮) | 1.5h |
| R7 | 右键 K 线 ContextMenu + Cmd+B/S 快捷键 · 都走 confirm 模态 | 1h |
| R8 | 右栏「当前标的持仓摘要」(随 market 切换 + 一键平仓 confirm 模态) | 45 min |
| R9 | `/portfolio` 页 · 动态卡 + 多曲线(recharts) + 活仓表 + 历史持仓表 + 订单流水 + 空态卡 | 2.5h |
| R10 | 下单 toast feedback · sonner · 帝王金成功 / 中国红失败 · 永不绿 | 30 min |
| R11 | Header Tab「自选 K 线 / 我的账户 / 设置」+ 跳转 | 30 min |
| R12 | playwright 截图(6 张):设置页 / 买入 disabled 态 / 下单确认模态 / 成交 toast / /portfolio 单市场曲线 / 右栏持仓摘要 | 1h |
| R13 | R 自验完整链路 + commits + tag `checkpoint-r` + 总汇报 | 1h |
| **小计** | | **~12h** |

**P + Q + R 合计 ~22.25h**(比原计划多 ~4h,主要在 R 新增「设置页 + 未激活引导 + 多入口下单 + 动态曲线」)

## 撤销路径

| 改动 | 撤销路径 |
|---|---|
| **再加多账户(M2+)** | account 表已 per user-market,加 `account_name` + 改 UniqueConstraint 为 `(user_id, market, account_name)` |
| **限价单(M1)** | `order_type` Enum 加 `LIMIT`,加 `limit_price` 字段;撮合服务对未成交订单进 Celery delayed task |
| **真实汇率展示(M1 可选)** | 加 `exchange_rate` 表,但**不是为了折算 portfolio**(那是 v1 设计的错路) · 只为 `/portfolio` 顶部加个「按当前汇率参考折算」可选小字 |
| **杠杆 / 做空(M2+ 或永不)** | position.quantity 改 signed + margin_account 表 · **产品红线考虑**,可能永不做 |
| **WebSocket 实时浮盈推送** | Task 4-B 落地后,把 useQueries 的 polling 改为 ws subscribe |
| **取消软删持仓** | 加 cron job 把 closed_at < N 天前的 position 物理删除 |

## 已知边界(M0 接受)

- **手续费按总金额算,无最小费用** — 真实券商有 5 元最低,M0 简化
- **A 股不强制 100 股整数倍** — 撮合允许任意股数,UI 默认填 100
- **无 T+1 限制** — 真实 A 股买入当天不能卖,M0 自由(教学优先)
- **无开盘 / 收盘时段判断** — 任意时间可下单,用最新 close 作参考价
- **重置市场金额删活仓不软删** — 软删的意义在"完整买卖回合复盘",reset 是"重新开局"语义,不归一类

## 红线沿用项目本质

- **永不接真实下单** · 任何场景都用 `services/virtual_trading/engine.py` 内的撮合
- **AI / 决策 / 交易输出必带「仅供参考,不构成投资建议」** · 全部交易卡片底部小字
- **VIRTUAL · 模拟 徽章** · 设置页 / 下单模态 / KPI 卡 / 订单成功 toast / 持仓摘要 全部带

## 修订记录

### v2 (2026-05-20) · 三独立子账户方案 · 删汇率

**根本变更:** 放弃 v1 的「单货币 CNY + 静态汇率 7.2 折算」,改为「三个独立子账户,各用各的货币,绝不折算合计」。

**v2 引入的新机制:**
- VirtualAccount 改 per user-market(一对多)· lazy create 方案 A
- 撮合 / 持仓 / 订单 / 权益曲线全部按原币种,无 FX 概念
- 用户必须自己去设置页填初始资金(M0 不预设)
- /workbench 顶部「当前市场 = 当前钱包」· market Tab 切换跟着切货币
- 未激活市场:买卖按钮 disabled + 引导跳设置页
- /portfolio 动态显示已激活市场(0 个 = 空态,1 个 = 一张卡一条曲线,N 个 = N 张卡 N 条曲线)
- 持仓改软删 `closed_at`,realized_pnl 写到 position row(复盘价值)
- 下单 confirm 模态必经 + 三个入口(顶部按钮 / 右键 / Cmd+B/S)

**v1 → v2 整体多写 ~4h**(主要 R 阶段:设置页 + 未激活引导 + 多入口 + 动态曲线)

**产品负责人理由:**「凡是要展示给用户的金额,宁可三个真数字并列,不要一个折算的假数字。」
