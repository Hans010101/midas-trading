# 0007 · 自选股(Watchlist)设计

## 状态
Approved-pending-review (2026-05-20)

## 上下文

Task 4 自选股(M0 验收链路第 4 步)进入设计阶段。产品负责人决定**拆成 4-A REST + 4-B WebSocket** 两段独立 ship,以下范围只盖 4-A。

技术要求:
- 后端 `WatchlistGroup` + `WatchlistItem` SQLAlchemy + Postgres
- REST 6 个路由(groups/items/reorder)
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

### 1. Postgres Schema

```python
# apps/api/app/models/watchlist.py

class WatchlistGroup(Base):
    __tablename__ = "watchlist_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("watchlist_group.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # cn / us / crypto
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("group_id", "symbol", "market", name="uq_watchlist_item_unique"),
        Index("idx_watchlist_item_group_sort", "group_id", "sort_order"),
    )
```

**字段决策:**
- `id` 用 `Integer autoincrement`(不是 UUID):自选股是用户私有数据,不需要全局唯一,顺序整数更好排序 + 索引更小
- `name` 限 64 字符:用户起名 "我的茅台" 这种远远够用
- `sort_order` `Integer`:支持拖拽时整数 reorder(可考虑后期换 fractional indexing 避免全量更新,M0 不做)
- `is_default`:用户注册后自动建 1 个 `name="默认"` + `is_default=true` 的 group(M0 简化:每用户 1 个分组够用,M1+ 多分组)
- `UniqueConstraint(group_id, symbol, market)`:同分组里同标的不重复

**删除策略:**
- `user.id` 删 → CASCADE `watchlist_group` → CASCADE `watchlist_item`
  (用户注销账户,自选股完全清理)
- `watchlist_group.id` 删 → CASCADE `watchlist_item`
- 自选股 item 删:硬删(不 soft delete · M0 简化)

### 2. REST 路由

| Method | Path | 输入 | 输出 | 备注 |
|---|---|---|---|---|
| GET | `/api/v1/watchlist/groups` | (Bearer JWT) | `[WatchlistGroupResponse]` | 当前用户所有 group |
| POST | `/api/v1/watchlist/groups` | `{name}` | `WatchlistGroupResponse` | 创建 group · 自动 sort_order = max+1 |
| DELETE | `/api/v1/watchlist/groups/{id}` | — | 204 | 仅本人 + 拒绝删 is_default |
| POST | `/api/v1/watchlist/items` | `{group_id, symbol, market}` | `WatchlistItemResponse` | 加自选 |
| DELETE | `/api/v1/watchlist/items/{id}` | — | 204 | 仅本人 group 下的 item |
| PUT | `/api/v1/watchlist/items/reorder` | `{group_id, item_ids: [int]}` | 200 | 批量更新 sort_order |

**鉴权:** 所有路由用 `CurrentUserDep`(N 阶段已实装),后端 SQL `WHERE user_id = ?` 强隔离

**reorder 实现:**单次 transaction,按位置写回 sort_order,失败回滚

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
- 选中后调 `POST /watchlist/items` 加进默认 group

### 5. 静态报价更新策略(M0)

- 每个 watchlist item 通过 `useQuery(['quote', market, symbol])` 拉最新价
- 实现:`GET /api/v1/market/kline?symbol=X&market=Y&period=1d&limit=1` 取末尾一根 K 的 `close`
- **客户端 30s 轮询**:`refetchInterval: 30_000`(M0 demo 接受 30s 延迟)
- 涨用 `text-bull` 朱红 / 跌用 `text-bear` 墨绿,无闪烁动画(动画是 Task 4-B 范围)
- 用 `useQueries` 批量并发,避免逐个 await

**为什么不做后端聚合 `/api/v1/quotes?symbols=...`(批量):**
- M0 demo 自选股最多 10 个 symbol,前端并发 10 个 query 没压力
- 后端聚合接口需要额外路由 + 跨市场 join 逻辑,工程量超 M0 范围
- TanStack Query 自带缓存,30s 内自动复用

### 6. 默认 group 自动创建

- 用户注册成功(`POST /auth/register` 流程末尾)→ 自动创建一个 group:
  - `name="默认"`,`is_default=True`,`sort_order=0`
- 注册后用户进 /workbench → 自选股栏显示「默认」分组(空态)
- **不要预填 demo symbols**(产品决策:让用户自己加,体验更亲身)

### 7. 空态视觉(沿用 0005 EmptyKline 风格)

```
📋(灰色)
还没有自选股
搜索一只标的开始关注
[搜索标的]  ← 中国红 CTA,触发 Cmd+K 弹窗
```

## Task 4-A Checkpoint O 切分

| Sub-task | 范围 | 估时(Claude Code 实跑)|
|---|---|---|
| O1 | watchlist model + alembic migration | 30 min |
| O2 | 后端 REST 路由 6 个 + 测试 | 1.5h |
| O3 | 注册时自动建默认 group(hook 进 auth.py register) | 15 min |
| O4 | 装 shadcn command + @dnd-kit/sortable | 15 min |
| O5 | 替换右栏占位:列表 + 删除 + 拖拽 + 空态(0005 风格)| 1.5h |
| O6 | Cmd+K SymbolSearch 组件 + 全局快捷键 | 1h |
| O7 | 静态报价集成(useQueries 30s 轮询)| 1h |
| O8 | playwright 截图 + 端到端验证 + commit + tag | 1h |
| **合计** | | **~7h** |

跟用户估的 5-7h 一致 · 上限。

## Task 4-B 边界(本 ADR 不实装,留档)

- WebSocket `/ws/quotes` + Redis pub/sub + 后端 30s 推 + 前端订阅
- 闪烁动画(涨朱红 / 跌墨绿,300ms)
- 降级:WebSocket 不可达 → 退到 30s 轮询(Task 4-A 已经默认走轮询)
- 跨用户隔离(WebSocket 握手验证 user_id)

## 撤销路径

- **schema 改动:** Postgres 列加减用 alembic revision · `sort_order` 后期可换 fractional indexing
- **拖拽换库:** dnd-kit 接口稳定,如换库重写 5 个 hook 即可
- **轮询换 WebSocket:** Task 4-B 落地后,把 `useQueries` 的 `refetchInterval` 删了,改用 WebSocket subscribe
- **取消 Cmd+K:** 退到右栏顶部一个传统 search input,M2+ 再优化

## 备注

- 不做拼音搜索(`pypinyin` 后端预生成)· Task 4.4(M1)再做
- 不做"按 24h 涨幅排序" / "按市值排序"等 watchlist 高级功能 · M2+ 再做
- 不做飞书/TG 推送配置(那是 Task 6)
- 多分组(`name="科技股"` / `name="价值股"`)M0 不做,默认 1 个 group · UI 隐藏分组切换器(group 是后端架构,前端只显示默认 group 的 items)
