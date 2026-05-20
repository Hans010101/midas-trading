# 0007 · 自选股(Watchlist)设计

## 状态
Approved (2026-05-20 · 修订版砍掉 group 抽象,扁平方案 · 见末尾「修订记录」)

## 上下文

Task 4 自选股(M0 验收链路第 4 步)进入设计阶段。产品负责人决定**拆成 4-A REST + 4-B WebSocket** 两段独立 ship,以下范围只盖 4-A。

技术要求:
- 后端 `WatchlistItem` SQLAlchemy + Postgres(**扁平结构,直接挂 user_id**)
- REST 4 个路由(list / add / delete / reorder)
- 前端:右侧栏占位 → 真实自选股列表 + Cmd+K 搜索 + 拖拽排序 + 删除 + 空态
- **静态报价**(M0 demo):从 `/api/v1/market/kline?limit=1` 拉最新价,客户端 30s 轮询
- 实时 WebSocket 推送是 Task 4-B 范围,本 ADR 不覆盖

## 依赖调研(实测 2026-05-20)

| 包 | 版本 | License | React 19 兼容 | 实测命令 |
|---|---|---|---|---|
| `@dnd-kit/core` | 6.3.1 | MIT | ✓(peerDeps `react >=16.8.0`)| `npm view @dnd-kit/core peerDependencies` |
| `@dnd-kit/sortable` | 10.0.0 | MIT | ✓ | `npm view @dnd-kit/sortable peerDependencies` |
| `cmdk` | 1.1.1 | MIT | ✓(已是 React 19 时代主版本)| `npm view cmdk` |
| shadcn `command` 注册表 | 当前 latest | (从 ui.shadcn.com 拉)| ✓ | `curl https://ui.shadcn.com/r/styles/default/command.json` |

**结论:**4 个依赖全部 MIT / React 19 兼容,无 license 风险,可放手用。

## 决策

### 1. Postgres Schema · 扁平结构

```python
# apps/api/app/models/watchlist.py

class WatchlistItem(Base):
    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # cn / us / crypto
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "market", name="uq_watchlist_user_symbol"),
        Index("ix_watchlist_user_sort", "user_id", "sort_order"),
    )
```

**字段决策:**
- `id` 用 `Integer autoincrement`(不是 UUID):自选股是用户私有数据,不需要全局唯一,顺序整数更好排序 + 索引更小
- `user_id` 直接 FK 到 `users.id`,**无中间 group 表**
- `sort_order` `Integer`:支持拖拽时整数 reorder(可考虑后期换 fractional indexing 避免全量更新,M0 不做)
- `UniqueConstraint(user_id, symbol, market)`:同用户同标的不重复(跨市场 600519 与 BTC/USDT 可共存)
- `Index(user_id, sort_order)`:列表查询主索引

**为什么砍掉 `WatchlistGroup`:**
- M0 demo 用户 5-10 个标的,完全用不到分组
- 「为未来留架构」经常错估未来 — 真要分组,加 `group_id` 列 + 新表即可,不是 breaking change
- 表少一张 = migration 少一次,UI 少一层切换器,产品负责人决策:**简洁优先**

**删除策略:**
- `user.id` 删 → CASCADE `watchlist_item`(用户注销账户,自选股完全清理)
- 自选股 item 删:硬删(不 soft delete · M0 简化)

### 2. REST 路由(4 个)

| Method | Path | 输入 | 输出 | 备注 |
|---|---|---|---|---|
| GET | `/api/v1/watchlist` | (Bearer JWT) | `[WatchlistItemResponse]` | 当前用户所有自选 · 按 sort_order ASC |
| POST | `/api/v1/watchlist` | `{symbol, market}` | `WatchlistItemResponse` | 加自选 · 自动 sort_order = max+1 |
| DELETE | `/api/v1/watchlist/{id}` | — | 204 | 仅本人 item |
| PUT | `/api/v1/watchlist/reorder` | `{item_ids: [int]}` | 200 | 批量更新 sort_order |

**鉴权:** 所有路由用 `CurrentUserDep`(N 阶段已实装),后端 SQL `WHERE user_id = ?` 强隔离

**reorder 实现:** 单次 transaction,按位置写回 sort_order,失败回滚

**重复加策略:** POST 收到已存在的 `(user_id, symbol, market)` → 409 Conflict + 现有 item 信息(前端可优雅提示「已在自选」)

### 3. 拖拽实现选型 · `@dnd-kit/sortable`

- 装:`pnpm add @dnd-kit/core @dnd-kit/sortable`
- 用 `<SortableContext strategy={verticalListSortingStrategy}>` + `useSortable` hook
- 视觉:拖拽中 item `opacity-50 cursor-grabbing`,放下时 reorder API 调用
- **不用 react-beautiful-dnd**:那个 ATL 项目已停止维护
- **不用 react-dnd**:dnd-kit 在 React 19 上更现代 + a11y 更好

### 4. Cmd+K 搜索 · `cmdk` via shadcn `command`

- 装命令:`pnpm dlx shadcn@latest add command`(会自动安装 cmdk)
- 触发:全局 `Cmd/Ctrl+K` 快捷键 → `<CommandDialog>` 弹出
- 数据源:沿用 `/api/v1/market/symbols?q=...&market=...`
- 结果按 market 分组(A 股 / 美股 / 加密)
- 选中后调 `POST /watchlist` 加进列表

### 5. 静态报价更新策略(M0)

- 每个 watchlist item 通过 `useQueries` 拉最新价
- 实现:`GET /api/v1/market/kline?symbol=X&market=Y&period=1d&limit=1` 取末尾一根 K 的 `close`
- **客户端 30s 轮询 + 25s staleTime**(防止组件重渲发额外请求):

  ```ts
  useQueries({
    queries: items.map((s) => ({
      queryKey: ['quote', s.market, s.symbol],
      queryFn: () => fetchLatestKline(s),
      refetchInterval: 30_000,
      staleTime: 25_000, // 防 re-render 重复发请求
    })),
  })
  ```

- 涨用 `text-bull` 朱红 / 跌用 `text-bear` 墨绿,无闪烁动画(动画是 Task 4-B 范围)

**为什么不做后端聚合 `/api/v1/quotes?symbols=...`(批量):**
- M0 demo 自选股最多 10 个 symbol,前端并发 10 个 query 没压力
- 后端聚合接口需要额外路由 + 跨市场 join 逻辑,工程量超 M0 范围
- TanStack Query 自带缓存,30s 内自动复用(`staleTime: 25s`)

### 6. 首次登录预填 3 个 demo symbols

**策略:** 用户邮箱验证成功后(首次登录 `/workbench` 时,触发 `GET /api/v1/watchlist`),如果列表为空 → 自动 insert 3 个 demo symbols。

```python
# apps/api/app/api/v1/watchlist.py · GET /watchlist 内部
DEMO_WATCHLIST = [
    ("BTC/USDT", "crypto"),
    ("NVDA", "us"),
    ("600519", "cn"),
]

# 实现位置:GET /watchlist 入口
# 1. 查当前用户 watchlist
# 2. 如果为空 且 user.email_verified_at IS NOT NULL → insert DEMO_WATCHLIST
# 3. 再返回列表
# 4. 用 SQL UNIQUE 约束 + ON CONFLICT DO NOTHING 兜底并发场景
```

**理由:**
- M0 demo 阶段,用户注册完看到空白栏 + 中间随便一根 K 线会迷茫
- 预填三市场代表标的(NVIDIA / 茅台 / BTC),**60 秒内传达「跨市场」产品价值**
- 不喜欢的用户可以删掉(/api/v1/watchlist/{id} DELETE)

**为什么挂在 GET 而不是 register / verify:**
- register 时用户还没 verify,不发 demo 也没场景看
- verify endpoint 触发预填会让 verify 响应耦合业务逻辑(verify 本职是邮箱状态变更)
- 挂在 GET /watchlist:**懒填充 + 幂等**,反复登出登入也不会重复插

### 7. 空态视觉(沿用 0005 EmptyKline 风格)

用户主动清空自选股(把 3 个 demo 都删了)→ 显示空态卡:

```
📋(灰色 + 米白卡背景)
还没有自选股
搜索一只标的开始关注
[搜索标的]  ← 中国红 CTA,触发 Cmd+K 弹窗
```

## Task 4-A Checkpoint O 切分

| Sub-task | 范围 | 估时(Claude Code 实跑)|
|---|---|---|
| O1 | watchlist model(扁平)+ alembic migration | 30 min |
| O2 | 后端 REST 路由 4 个 + 测试 | 1.5h |
| O3 | GET /watchlist 内置「首次空 → 预填 3 demo symbols」逻辑 | 20 min |
| O4 | 装 shadcn command + @dnd-kit/sortable | 15 min |
| O5 | 替换右栏占位:列表 + 删除 + 拖拽 + 空态(0005 风格)| 1.5h |
| O6 | Cmd+K SymbolSearch 组件 + 全局快捷键 | 1h |
| O7 | 静态报价集成(useQueries 30s 轮询 + 25s staleTime)| 1h |
| O8 | playwright 截图 + 端到端验证 + commit + tag | 1h |
| **合计** | | **~7h** |

跟产品负责人估的 5-7h 一致 · 上限。

## Task 4-B 边界(本 ADR 不实装,留档)

- WebSocket `/ws/quotes` + Redis pub/sub + 后端 30s 推 + 前端订阅
- 闪烁动画(涨朱红 / 跌墨绿,300ms)
- 降级:WebSocket 不可达 → 退到 30s 轮询(Task 4-A 已经默认走轮询)
- 跨用户隔离(WebSocket 握手验证 user_id)

## 已知边界与扩展路径

### 当前 M0 已知边界
- **客户端轮询不解耦标的数量**:N 个标的 = N 个 HTTP 请求,N>50 时会成为瓶颈
- **多用户同 symbol 无共享缓存**:每个用户的 30s 轮询独立打后端 cache-aside,Redis 层会命中但路由仍走
- **无价格变化推送**:即便价格不变,30s 也会拉一次(可忽略,后端 ClickHouse 查询轻量)

### 扩展路径(按优先级)
1. **Task 4-B · WebSocket 推送**(M0→M1 平滑)
   - 后端 30s tick 一次 → 推给所有订阅该 symbol 的连接
   - 标的数量与请求量解耦(O(1) 连接 + O(N) symbols per push)
   - 前端 `useQueries` 改为 `subscribe to ws`,refetchInterval 删
2. **多分组(M2+)**
   - 加 `group_id` 列 + `watchlist_group` 表
   - 现有 item 全部归入 default group(migration 自动)
   - 不是 breaking change(API 多一个可选 `group_id` query 参数)
3. **拼音搜索**(M1)
   - `pypinyin` 后端预生成 `symbol_pinyin` 索引字段
   - 当前 `/api/v1/market/symbols?q=...` ASCII match → 改成 LIKE %q% OR pinyin LIKE %q%
4. **fractional sort_order**(M2+)
   - 现在 reorder 全量重写,N=10 没压力,N>100 时换 `String("a", "h", "m", ...)` 字典序 ID

## 撤销路径

- **schema 改动:** Postgres 列加减用 alembic revision · `sort_order` 后期可换 fractional indexing
- **拖拽换库:** dnd-kit 接口稳定,如换库重写 5 个 hook 即可
- **轮询换 WebSocket:** Task 4-B 落地后,把 `useQueries` 的 `refetchInterval` 删了,改用 WebSocket subscribe
- **取消 Cmd+K:** 退到右栏顶部一个传统 search input,M2+ 再优化
- **取消预填 demo:** 删 GET /watchlist 里的 lazy-fill 分支,空注册用户进 /workbench 看到空态卡

## 备注

- 不做拼音搜索(`pypinyin` 后端预生成)· Task 4.4(M1)再做
- 不做"按 24h 涨幅排序" / "按市值排序"等 watchlist 高级功能 · M2+ 再做
- 不做飞书/TG 推送配置(那是 Task 6)
- 不做多分组(`name="科技股"` / `name="价值股"`)· M2+ 再实装

## 修订记录

### 2026-05-20 修订 v2 · 砍掉 group 抽象

**变更:**
1. 删 `WatchlistGroup` 表,`WatchlistItem` 直接挂 `user_id`
2. REST 路由从 6 个减到 4 个(去掉 group CRUD)
3. 取消「注册时自动建默认 group」,改为「首次登录时 GET /watchlist 内置预填 3 demo symbols」
4. 静态报价加 `staleTime: 25_000` 防 re-render 重复请求
5. 新增「## 已知边界与扩展路径」小节,记录 Task 4-B WebSocket 解耦数量 + 多分组 M2+ 路径

**产品负责人理由:**
- M0 demo 用户 5-10 个标的,完全用不到分组
- 「为未来留架构」经常错估未来 · 真要分组,加 `group_id` + 新表不是 breaking change
- 简洁优先:表少一张 + UI 无分组切换器 + 用户少一个心智负担
