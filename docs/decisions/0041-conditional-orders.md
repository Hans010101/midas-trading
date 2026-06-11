# ADR 0041 · 条件单(限价 / 止损 / 止盈)架构决策

- 状态:**Accepted**(三个架构决策已由产品负责人拍板 · 本 ADR 为刀1-3 的架构契约;实现尚未开始)
- 日期:2026-06-11(刀0 · 设计归档)
- 相关:0008(虚拟交易引擎 · OrderType 预留位)· ADR-0019(perp 强平监控 = 本架构活先例)·
  #296(通知去重 · 成交通知经唯一入口自动继承)· 引擎现状只读诊断(2026-06-11 本会话)

## 背景

- **现状(诊断实证)**:虚拟引擎 market-only —— `place_market_order` 同步立即成交
  (取最新价 → 滑点 → 手续费 → 落库 FILLED/REJECTED,零等待);`VirtualOrder.order_type`
  列 + `OrderType` enum 扩展位是 0008 设计期预留(枚举注释明示「LIMIT 等订单类型留增量空间」),
  但**无 PENDING 状态、无挂单触发机制、无任何止损止盈实现**(全仓 grep 零命中,perp 仅有强平)。
- **需求**:股票(spot 四市场:cn/us/hk/crypto-spot,共用同一 `place_market_order`)限价单 +
  止损止盈;crypto perp 止损止盈(perp 现仅被动强平,无用户挂单 SL/TP)。

## 红线(不可逾越)

- ★ **所有真实成交仍只走 `virtual_trading/engine.py` 的 `place_market_order`** —— 条件单只是
  「延迟触发器」:触发那一刻构造 `PlaceOrderRequest` 调 `place_market_order` 完成成交,
  **engine 核心零改**(engine 不需要知道条件单的存在;挂单行状态由触发器在成交后自行更新)。
- 成交后的滑点 / 手续费 / 持仓 / 快照 / VIRTUAL 标识 / **成交通知(notify=True 自动继承)**
  全部复用唯一入口,不另起炉灶、不复制任何撮合逻辑。
- **perp 强平(perp_liquidation)是本架构的活先例**:「外部周期任务检测价格 → 调引擎入口完成交易」
  已被生产验证(beat 60s · 真标记价 · FOR UPDATE 防竞争 · 取不到价绝不误杀)。
- 一切全程虚拟资金,绝不接真实交易通道(项目第一红线,不因新单型松动)。

## 决策一:挂单存储 = 独立 `conditional_orders` 表(非给 VirtualOrder 加 PENDING)

- **理由**:`VirtualOrder` 保持 FILLED/REJECTED **二元终态语义不变**;条件单触发成交时才产生
  真 VirtualOrder;全站读侧(账户订单列表 / bot 富回执 / 通知事件 / equity 快照 trigger)
  **零回归**。给 VirtualOrder 加 PENDING 会把改造面铺到全站每一个假设"订单=终态"的读取点(已否决)。
- **状态机**:`active`(挂着)→ `triggered`(已触发并成交)/ `cancelled`(用户撤单)/
  `expired`(可选 · 触发时校验失败或超时)。

## 决策二:资金占用 = 不冻结,触发时校验余额

- limit buy 挂单期间**不预冻结现金**;触发、真要成交那一刻由 `place_market_order` 现有的
  余额校验把关,不足则拒(挂单转 rejected/expired,原因落档)。
- **理由**:现引擎 cash 直扣、无冻结概念;加冻结 = 新字段 + 下单/平仓/快照全链改(大)。
  虚拟盘语义下「挂单不占款、成交时校验」成立,且与「成交仍走唯一入口」红线天然一致
  (校验逻辑零新建,就是 engine 现有的拒单路径)。
- 真冻结(frozen balance)列为 **v2 优化**,v1 不做。

## 决策三:触发机制 = 新建 scan 任务,照抄 perp_liquidation 范式

- beat 周期任务(频率参考强平 60s,可调)扫 `active` 条件单 × 真实价格源 → 条件满足 →
  `SELECT … FOR UPDATE` 防与用户撤单竞争 → 构造 `PlaceOrderRequest` 调 `place_market_order`
  → 成交后挂单转 `triggered`(成交失败转 expired + 原因)。
- **取不到价 → 跳过,绝不误触发**(照强平「不误杀」原则:价格源缺失/停牌不动挂单)。
- **limit 与止损止盈共用同一触发器**,条件方向不同:limit = 到价开/平仓;
  SL/TP = 持仓后反向价格触发平仓。一次建好,两类单型共用。

## 分刀计划

- **刀1**:`conditional_orders` 模型 + Alembic 迁移 + 挂单/撤单/列表 API(纯增量,不碰 engine)。
- **刀2**:触发扫描器(抄 perp_liquidation 范式)+ 成交联动(触发调 `place_market_order`)。
  ← 碰红线最近的一刀:**只调用、不改 engine**,review 重点。
- **刀3**:前端(下单面板加限价 & SL/TP 选项 + 挂单管理界面:列表/撤单)。

## 未决 / 待后续刀细化(列出 · 不在本 ADR 定)

- `conditional_orders` 具体字段(symbol / market / side / trigger_price /
  order_kind[limit / stop_loss / take_profit] / quantity / position_side / status /
  created_at 等)→ 刀1 设计。
- stop_loss / take_profit 是「持仓后挂」还是「下单时附带」→ 刀1 细化。
- 触发扫描频率、是否分市场(股票休市时段不扫?crypto 7×24)→ 刀2。
- perp 的 SL/TP 触发成交走 perp_dispatcher 还是同样收口(perp 平仓入口为 route_close_perp)→ 刀2
  与红线条款对齐(perp 域的「唯一入口」= perp_engine/route_*,同精神)。
