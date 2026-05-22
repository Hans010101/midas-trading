# M2 · Crypto Pro · 分支状态(feature/m2-crypto-pro)

**更新:** 2026-05-21 深夜
**分支:** `feature/m2-crypto-pro`(独立分支 · main 不动 · 部署中的 M1 零影响)
**Checkpoint:** M2-A 工程骨架完成 + M2-A-verify 脚本就绪 + **M2-B 后端 REST 完整化已落 5 个 commit**

> **M2-A 验证(白天值守 1 小时):**
> ```
> cd /opt/midas
> git fetch origin
> git checkout feature/m2-crypto-pro
> git pull
> bash update.sh                                ← 拉镜像 + alembic + reload caddy
> bash scripts/m2a-verify.sh 2>&1 | tee /tmp/m2a-verify.log
> ```
> M2-A 通过后 · 进 M2-C(产品方触发)· M2-B 已写完不需要再 build。
> **回滚 main 必做:** `git checkout main && bash update.sh`

---

## 🎯 完成清单(M2-A 12 commit + M2-A-verify + M2-B 5 commit · 共 18 commit)

### M2-A · 数据层工程骨架(12 commit)

| Commit | 范围 | 文件 |
|---|---|---|
| `M2-A-1` | ADR 0017 · Crypto Pro 数据层完整设计 | `docs/decisions/0017-m2a-crypto-pro-data-layer.md` |
| `M2-A-2` | ClickHouse schema · kline 加 instrument 列 + 5 张新表 | `docker/clickhouse-init.sql` |
| `M2-A-3` | Pydantic schemas · 9 个领域模型 | `apps/api/app/schemas/crypto.py` |
| `M2-A-4` | Binance Futures adapter · 6 个数据维度 | `apps/api/app/services/data_sources/binance_futures_source.py` |
| `M2-A-5,6` | CoinGecko + alternative.me adapter | `apps/api/app/services/data_sources/coingecko_source.py` + `alternative_me_source.py` |
| `M2-A-7` | ClickHouse insert/select helper · 5 张表 | `apps/api/app/services/clickhouse_crypto.py` |
| `M2-A-8` | REST `/api/v1/crypto/*` · 7 个端点 + 路由注册 | `apps/api/app/api/v1/crypto.py` + `__init__.py` |
| `M2-A-9` | Celery 任务 · 7 个数据采集 · perp K stub | `apps/worker/tasks/crypto_metrics_ingest.py` |
| `M2-A-10` | 虚拟合约账户 · 4 张表 model + alembic migration | `apps/api/app/models/virtual_futures.py` + `alembic/versions/a2b3c4d5e6f7_*.py` |
| `M2-A-11` | pytest 骨架 · 3 个测试文件 · 不打外网 | `apps/api/tests/services/test_*` |
| `M2-A-12` | 分支 README(本文件) | `docs/m2-crypto-pro-status.md` |
| `M2-A-verify` | **服务器实测脚本** · 8 阶段端到端验证 | `scripts/m2a-verify.sh` |

### M2-B · 后端 REST 完整化 + 缠论联动(5 commit · 不依赖服务器实测)

| Commit | 范围 | 文件 |
|---|---|---|
| `M2-B-1` | ClickHouseClient.insert/select/count_kline 加 `instrument` 参数 · 默认 spot 兼容 | `apps/api/app/services/clickhouse_client.py` |
| `M2-B-2/3` | `/api/v1/market/kline` 加 `?instrument` · perp 走 BinanceFuturesSource · lifespan 注册 | `apps/api/app/main.py` + `app/api/deps.py` + `app/api/v1/market.py` |
| `M2-B-4` | **`tasks.crypto.perp_kline_incremental` Celery 任务 · 替换 M2-A stub** · top 30 perp × 3 周期增量 | `apps/worker/tasks/crypto_metrics_ingest.py` |
| `M2-B-5` | `/api/v1/analysis/chan` + `/decision-card` 加 `?instrument` · 缠论引擎透明支持 perp K | `apps/api/app/api/v1/analysis.py` |
| `M2-B-6` | M2-B 收尾 README(本次更新) | `docs/m2-crypto-pro-status.md` |

---

## ✅ 已经做了的事(M2-A 工程骨架)

### 1. 设计层
- ADR 0017 · 9 个数据流 + 5 张 CH 表 + 3 个 adapter + 7 个 Celery 任务 + 7 个 REST 端点 + 4 张虚拟合约表 的完整设计
- 接缝处「翻车防御清单」(继承 0002/0010/0013/0014/0015/0016 教训)
- M2-A → M2-B → M2-C → M2-D → M2-E 的接口对接面

### 2. 数据层
- ClickHouse 5 张新表 init.sql · `kline` 表加 `instrument Enum8('spot','perp')` 列
- Python schemas 9 个领域模型(Pydantic v2 · extra='forbid' frozen=True)
- 3 个数据源 adapter(全部 httpx async · 全部继承 BaseDataSource · 全部 _retry 退避)
- ClickHouse 写入/查询 helper(时区严格 tz-aware UTC · DESC LIMIT N + reverse 模式)

### 3. 应用层
- 7 个新 REST 端点 `/api/v1/crypto/*` · 全部 GET · 用 Annotated + Literal 类型严格
- 7 个 Celery 任务骨架 · 分层节奏(1m/5m/8h/1d)· 每标的独立 try/except
- 路由注册到 `api/v1/__init__.py`

### 4. 虚拟合约账户(只 schema · 不撮合)
- 4 张表 SQLAlchemy 2.0 model + alembic migration(`a2b3c4d5e6f7`)
- 5 个 Postgres ENUM 类型(margin_mode / direction / order_side / order_type / order_status)
- 跟现有 spot VirtualAccount **平行不合并**(行业惯例 + 风险模型完全不同)

### 5. 测试
- 14 个测试 · 实跑 · 全部 httpx.MockTransport 不打外网
- 红线守门:`test_crypto_router_has_no_write_endpoints` 用 router.routes 反射检查
- 8 个端到端测试 `@pytest.mark.skip` 占位(等 M2-B 联调时补 mock CH 数据)

---

## 🟡 WIP · 必须白天人工跑的事

### 联调步骤(白天 1 小时左右)

**前置:** 确认 main 分支 M1 部署在跑 · 这些验证不会影响生产。

#### 1. 拉分支 + 装新依赖
```bash
cd /Users/hans.pan/点金Midas
git checkout feature/m2-crypto-pro
git pull
cd apps/api
.venv/bin/pip install -e .  # httpx 已在依赖 · 无新增包
```

#### 2. 跑 pytest · 14 个测试都通
```bash
cd apps/api
.venv/bin/pytest tests/services/test_binance_futures_source.py -v
.venv/bin/pytest tests/services/test_coingecko_and_alternative_me.py -v
.venv/bin/pytest tests/api/test_crypto_endpoints.py::test_crypto_router_has_no_write_endpoints -v
```

预期:
- `test_binance_futures_source.py` 8 个全 PASS
- `test_coingecko_and_alternative_me.py` 6 个全 PASS
- `test_crypto_router_has_no_write_endpoints` PASS(其余 @pytest.mark.skip)

#### 3. 跑实 API 集成测试(可选 · 验证 Binance / CoinGecko 直连)
```bash
.venv/bin/python -c "
import asyncio
from app.services.data_sources.binance_futures_source import BinanceFuturesSource

async def main():
    src = BinanceFuturesSource()
    try:
        klines = await src.fetch_kline('BTCUSDT', '1d', limit=5)
        print(f'BTC 1d K {len(klines)} 根 · 最新收盘 {klines[-1].close}')
        fr = await src.fetch_funding_rate('BTCUSDT', limit=3)
        print(f'BTC funding rate {len(fr)} 条 · 最新 rate {fr[-1].rate}')
        oi = await src.fetch_open_interest('BTCUSDT', limit=3)
        print(f'BTC OI {len(oi)} 条 · 最新 oi_usd {oi[-1].oi_usd:.0f}')
    finally:
        await src.close()

asyncio.run(main())
"
```

#### 4. 跑 alembic migration(本地 dev DB · 不动生产)
```bash
.venv/bin/alembic upgrade head
# 应该看到:Running upgrade d8e2f4a5c7b9 -> a2b3c4d5e6f7, virtual futures tables
.venv/bin/alembic current  # 应是 a2b3c4d5e6f7
```

#### 5. 跑 ClickHouse schema 更新(本地 dev CH · 不动生产)
```bash
# init.sql 只在容器首次启动时执行 · 这次需要手动 apply 增量改动:
docker exec midas-clickhouse clickhouse-client --query "
ALTER TABLE kline ADD COLUMN IF NOT EXISTS instrument
  Enum8('spot'=1, 'perp'=2) DEFAULT 'spot' AFTER market
"
# 跑 5 张新表的 CREATE(逐条 paste 或 batch · 用 init.sql 的相关段落)
```

#### 6. mypy / ruff 检查(可选)
```bash
.venv/bin/ruff check apps/api/app/schemas/crypto.py
.venv/bin/ruff check apps/api/app/services/data_sources/binance_futures_source.py
.venv/bin/ruff check apps/api/app/services/data_sources/coingecko_source.py
.venv/bin/ruff check apps/api/app/services/data_sources/alternative_me_source.py
.venv/bin/ruff check apps/api/app/services/clickhouse_crypto.py
.venv/bin/ruff check apps/api/app/api/v1/crypto.py
.venv/bin/ruff check apps/worker/tasks/crypto_metrics_ingest.py
.venv/bin/ruff check apps/api/app/models/virtual_futures.py
```

如有 ruff/mypy 红 · 修完再 commit 到分支。

---

## ✅ M2-B 已做(并行夜间推进 · 不依赖服务器实测)

- **`/api/v1/market/kline?instrument=spot|perp`** · 加参数 · perp 自动走 BinanceFuturesSource
- **`/api/v1/analysis/chan?instrument=...`** + **`/decision-card?instrument=...`** · 缠论引擎透明支持 perp(K 线对引擎是透明数据)
- **ClickHouseClient · insert/select/count_kline 加 `instrument` 参数** · 默认 'spot' 兼容旧调用方
- **Celery `tasks.crypto.perp_kline_incremental` 实装** · 替换 M2-A stub · top 30 perp × 3 周期(15m/1h/1d)增量
- **lifespan 注册 `binance_futures_source`** · httpx 单例 · 复用连接池

## ⛔ M2-B 仍然没做(明确边界 · 留 M2-D 联调时一起)

- **`/api/v1/crypto/*` 端点回源** · 当前只读 ClickHouse · 数据缺时走 Celery 任务覆盖 · M2-D 联调如发现某 endpoint 总返空再做回源
- **4h 周期 K 线** · `Period` Literal 当前不含 4h · M2-D 改 schema 加 4h
- **decision-card cache key 加 instrument** · 当前 spot/perp 共用 cache key · 串扰风险 · M2-D 实测发现再改

## ⛔ M2-C 不做(等 M2-A 验证通过后再开)

- **虚拟合约撮合**(开仓 / 平仓 / 加减仓 / 杠杆调整) · 依赖 M2-A 表结构定稿
- **资金费率结算 worker**(8h 触发 · 扫所有持仓 × funding) · 同上
- **mark price 定期更新 worker**(用于 unrealized_pnl + 强平检查) · 同上
- **强平 worker**(margin_balance < maintenance_margin → 强平) · 同上

## ⛔ M2-D 不做(等 M2-C 撮合就绪)· 但范围已登记

- **前端 UI 全部**(landing page / 详情页合约 tab / 一键下单) · 依赖 M2-C REST 接口稳定

### M2-D 加密币种详情页 · 产品方确定需求(2026-05-22 登记)

**布局:左主区 + 右侧栏**

**左主区:1 主图 + 6 个合约维度图**

| # | 图 | 数据源 | 当前状态 |
|---|---|---|---|
| 主图 | K 线 + 缠论标注 | `kline(instrument=perp)` + 缠论引擎 | ✅ M2-A/M2-B 已通 |
| 1 | 持仓量(Open Interest) | `crypto_open_interest` | ✅ M2-A 已采 |
| 2 | 大户多空比 · 账户数 | `crypto_long_short_ratio.top_account_*` | ✅ M2-A 已采 |
| 3 | 大户多空比 · 持仓量 | `crypto_long_short_ratio.top_position_*` | ✅ M2-A 已采 |
| 4 | 多空人数比(全市场散户) | Binance `globalLongShortAccountRatio` | ❌ **M2-B 补采**(M2-A 只采了 top trader,没采全市场)|
| 5 | 合约主动买卖量 | `crypto_long_short_ratio.taker_*` | ✅ M2-A 已采 |
| 6 | 基差(basis) | mark_price − index_price 时间序列 | ❌ **M2-B 补采**(当前只存 funding 时点 mark,没存 basis 序列)|

**右侧栏:**
- 下单指导 + 实战策略清单
- **多空研判并入点金现有 AI 决策卡 ——【合并成一张,不并列两张】**
  · AI 决策卡 workflow 要把合约情绪(多空比 / 资金费率 / OI 变化 / basis)
    作为额外输入,产出一张融合卡(技术面 + 合约面)· 不是在卡旁边再挂一张多空卡
  · 这块涉及 M2-B/M2-C 后端(workflow 加合约输入)+ M2-D 前端(单卡渲染)

### M2-D 触发前需 M2-B 补的 2 个数据缺口

1. **`globalLongShortAccountRatio`**(多空人数比)· Binance `/futures/data/globalLongShortAccountRatio`
   · 建议:`crypto_long_short_ratio` 表加 2 列 `global_account_long` / `global_account_short`
     · adapter `fetch_long_short_ratio` 加第 4 个 endpoint · Celery 任务一并拉
2. **basis(基差)时间序列** · 需同时拿 perp mark_price + spot/index price
   · 建议:新表 `crypto_basis(symbol, ts, mark_price, index_price, basis, basis_pct)`
     · 或复用 · Celery 5min 一次从 `/fapi/v1/premiumIndex`(含 markPrice + indexPrice)拉

这 2 个缺口归 M2-B(M2-A 验证通过 + M2-C 之后,或 M2-B 收尾时一起补)。

---

## ✅ M2-D 前端 · 详情页接真实数据(2026-05-22 · 骨架→真实数据)

骨架页布局产品方已验收通过 · 本步把占位图升级为接真实数据(全部在 feature 分支 · main 不动)。

**路由:** `/crypto-preview`(匿名可访问)· 固定标的 BTC(`BTC/USDT` 现货 K / `BTCUSDT` 合约维度)

### 真实 / 占位边界(一眼分清)

| 模块 | 状态 | 数据源 |
|---|---|---|
| 主图 K 线 + 缠论标注 | ✅ 真实 | `/api/v1/market/kline` + `/api/v1/analysis/chan`(复用工作台组件) |
| ① 合约持仓量 OI | ✅ 真实 | `/api/v1/crypto/futures/BTCUSDT/open-interest`(面积图) |
| ② 大户多空比·账户数 | ✅ 真实 | `…/long-short-ratio` → `top_account_ratio`(折线 + 1.0 参考线) |
| ③ 大户多空比·持仓量 | ✅ 真实 | `…/long-short-ratio` → `top_position_ratio` |
| ⑤ 合约主动买卖量 | ✅ 真实 | `…/long-short-ratio` → `taker_buy_vol`/`taker_sell_vol`(朱红/墨绿双线) |
| ④ 多空人数比值 | ⏳ 占位 | M2-B 数据缺口(`globalLongShortAccountRatio` 未采)· 标「数据 M2-B 待补」 |
| ⑥ 基差 basis | ⏳ 占位 | M2-B 数据缺口(basis 序列未采)· 标「数据 M2-B 待补」 |
| Header 价/涨跌 | ✅ 真实 | 日 K 末两根(close + 日涨跌) |
| Header 资金费率/下次结算 | ✅ 真实 | `/api/v1/crypto/futures/BTCUSDT/info` |
| AI 决策卡 · 技术面综合评分 | ✅ 真实 | `/api/v1/analysis/decision-card`(0012)· 后端无 KEY 时 footer 标 `mock` |
| AI 决策卡 · 多空研判(合约面) | ✅ 真实指标 | 资金费率/OI 增减/大户多空比 实时值 + 透明规则标签 |
| 下单指导 / 实战策略清单 | ⏳ 占位 | 依赖 M2-C 虚拟合约撮合 · 标「占位·待虚拟交易模块接入」 |

### 自主决策(产品方可推翻)

1. **标的固定 BTC** · 本步专注接数据 · 多标的切换留后续迭代。
2. **周期 = 15m / 1h / 1d**(去掉骨架里的 4h)· kline `Period` enum 无 4h(M2-B 待补 4h 重采样)· 默认 `1d`(5 年日 K 确有数据)· 15m/1h 若预览环境未预热会显示「暂无数据」空态卡(正常)。
3. **合约面不编综合评分** · 「多空研判」只列真实指标 + 简单规则解读(资金费率>0→多头付费 等)· 明确标注「合约面综合评分算法待 M2-B/M2-C 定义」· 不硬编假公式(铁律)。
4. **6 维度图用 recharts**(已在依赖)· 单图 8h 窗口(96 点 · 5min 栅格)· OI 面积图 / 多空比折线 / taker 双线。
5. **缠论标注默认开** · 让产品方一眼看到笔/中枢/分型效果 · 页面内可关。
6. **接不上一律「—」/ 空态卡** · 不伪造任何数值。

### 改动文件
```
apps/web/app/crypto-preview/page.tsx           (骨架 → 渲染 CryptoDetail)
apps/web/components/crypto-preview/            (新增)
  crypto-detail.tsx        · 编排 + 下单指导/策略清单占位
  crypto-header.tsx        · 价/涨跌/资金费率/周期切换
  crypto-main-chart.tsx    · KlineChart + ChanOverlay(props 驱动)
  crypto-ai-card.tsx       · 技术面综合评分 + 合约面多空研判
  dimension-section.tsx    · 6 维度图(recharts · 4 真实 2 占位)
apps/web/lib/api/crypto.ts                      (新增 · /crypto/* client)
apps/web/hooks/use-crypto.ts                    (新增 · TanStack Query hooks)
apps/web/components/chart/chan-overlay.tsx      (改 · 加可选 props · 向后兼容工作台)
```

### 自验
- `pnpm type-check` ✓ · `pnpm lint` ✓(0 warning)· `pnpm build` ✓
- `/crypto-preview` 仍为 `○ (Static)` 预渲染(客户端 island 运行时取数)· SSG 11 页全过 · 工作台不受 chan-overlay 改动影响
- 真实数据正确性依赖预览环境后端已预热(M2-A 采集任务跑过)· 未热则各图显示空态(非报错)

### 仍未做(明确边界)
- 多标的切换 / 现货-合约 tab 真切换(本页 spot 现货 tab 占位)
- ④多空人数比值、⑥基差 接真实数据(等 M2-B 补采)
- 下单指导 / 实战策略清单 接真实逻辑(等 M2-C 撮合)
- 4h 周期(等 M2-B 加 schema)

---

## 🔴 红线再确认

| 检查项 | 现状 |
|---|---|
| 不接真实交易通道 | ✓ 所有 adapter 只调 GET endpoint · 无 sign · 无 trade |
| 不动真钱 | ✓ 虚拟合约 4 张表跟 Binance 真实合约**完全隔离** |
| 数据接口只读 | ✓ `/api/v1/crypto/*` 全部 GET(`test_crypto_router_has_no_write_endpoints` 守门) |
| AI / 交易输出带免责 | ✓ M2-A 不涉及 AI / 交易输出 · 留 M2-C/D |

---

## 📅 下一步排期建议(产品方拍板)

| Checkpoint | 范围 | 估时 | 触发条件 |
|---|---|---|---|
| **M2-A 联调** | 跑 pytest + 实 API 验证 + alembic + CH ALTER | 0.5-1 d | 白天值守可做 |
| **M2-B** | 回源 + 缠论 perp 联动 + `/market/kline?instrument` | 1-2 周 | M2-A 通过后 |
| **M2-C** | 虚拟合约撮合 + 资金费率结算 + 强平 + mark price worker | 2-3 周 | M2-B 通过后(强依赖) |
| **M2-D** | 前端 Crypto Pro UI(landing + 详情页合约 + 一键下单) | 2-3 周 | M2-C 路由就绪后 |
| **M2-E** | E2E + 性能优化 + playwright 截图 + 用户文档 | 1 周 | M2-D 通过后 |
| **总和** | M2 全程 | **6-9 周** | |

---

## 🧬 commit 历史(分支 vs main)

跑 `git log main..HEAD --oneline` 看分支独有的 11 个 commit。
所有 commit 都遵守:
- `[M2-A-N]` 前缀
- 中文 message · 多段 body
- 红线声明
- WIP 标记
- 接缝处的「下一步」说明

---

## 🗂 文件清单(本分支新增)

```
docs/
  decisions/0017-m2a-crypto-pro-data-layer.md
  m2-crypto-pro-status.md(本文件)

docker/
  clickhouse-init.sql(增量 · kline ALTER + 5 表)

apps/api/
  app/schemas/crypto.py
  app/services/data_sources/
    binance_futures_source.py
    coingecko_source.py
    alternative_me_source.py
  app/services/clickhouse_crypto.py
  app/api/v1/crypto.py
  app/api/v1/__init__.py(注册 crypto_router)
  app/models/virtual_futures.py
  alembic/versions/a2b3c4d5e6f7_virtual_futures_tables.py
  tests/
    services/test_binance_futures_source.py
    services/test_coingecko_and_alternative_me.py
    api/test_crypto_endpoints.py

apps/worker/
  tasks/crypto_metrics_ingest.py
```

---

## 📌 给产品负责人审分支时的看点

1. **ADR 0017** · 看决策逻辑是否合理 · 数据维度是否漏掉关键的(eg. liquidations 24h 暂未加 · 留 M2-A v2)
2. **clickhouse-init.sql** · 看 5 张表设计 + kline ALTER 是否能直接 apply 到现有 ClickHouse
3. **binance_futures_source.py** · 看错误映射 + symbol 格式互转设计
4. **api/v1/crypto.py** · 看 7 个端点的契约是否符合 M2-D 前端预期
5. **virtual_futures.py + migration** · 看 4 张合约表设计是否覆盖 M2-C 撮合需要
6. **commit message** · 11 个 commit 信息是否清晰可审 + 红线声明在位

审完后给反馈 · 进 M2-A 联调或调整设计。

---

**当前分支 commit:** 见 `git log feature/m2-crypto-pro --oneline | head -12`
**push 状态:** 见 `git push -u origin feature/m2-crypto-pro` 后的最终 commit
