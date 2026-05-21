# M2 · Crypto Pro · 分支状态(feature/m2-crypto-pro)

**更新:** 2026-05-21 夜
**分支:** `feature/m2-crypto-pro`(独立分支 · main 不动 · 部署中的 M1 零影响)
**Checkpoint:** M2-A · 数据层 · 工程骨架完成 · 待白天联调验证

---

## 🎯 完成清单(11 个 commit 落在分支)

| Commit | 范围 | 文件 |
|---|---|---|
| `M2-A-1` | ADR 0017 · Crypto Pro 数据层完整设计 | `docs/decisions/0017-m2a-crypto-pro-data-layer.md` |
| `M2-A-2` | ClickHouse schema · kline 加 instrument 列 + 5 张新表 | `docker/clickhouse-init.sql` |
| `M2-A-3` | Pydantic schemas · 9 个领域模型 | `apps/api/app/schemas/crypto.py` |
| `M2-A-4` | Binance Futures adapter · 6 个数据维度 | `apps/api/app/services/data_sources/binance_futures_source.py` |
| `M2-A-5,6` | CoinGecko + alternative.me adapter | `apps/api/app/services/data_sources/coingecko_source.py` + `alternative_me_source.py` |
| `M2-A-7` | ClickHouse insert/select helper · 5 张表 | `apps/api/app/services/clickhouse_crypto.py` |
| `M2-A-8` | REST `/api/v1/crypto/*` · 7 个端点 + 路由注册 | `apps/api/app/api/v1/crypto.py` + `__init__.py` |
| `M2-A-9` | Celery 任务 · 7 个数据采集 | `apps/worker/tasks/crypto_metrics_ingest.py` |
| `M2-A-10` | 虚拟合约账户 · 4 张表 model + alembic migration | `apps/api/app/models/virtual_futures.py` + `alembic/versions/a2b3c4d5e6f7_*.py` |
| `M2-A-11` | pytest 骨架 · 3 个测试文件 · 不打外网 | `apps/api/tests/services/test_binance_futures_source.py` + 2 个 |
| `M2-A-12` | 分支 README(本文件) | `docs/m2-crypto-pro-status.md` |

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

## ⛔ M2-A 没做(明确边界)

- **回源逻辑**(`/api/v1/crypto/*` 端点缺数据时回源 Binance) · 留 M2-B
- **缠论联动 perp K 线**(kline 表 instrument='perp' 入缠论引擎) · 留 M2-B
- **虚拟合约撮合**(开仓 / 平仓 / 加减仓 / 杠杆调整) · 留 M2-C
- **资金费率结算 worker**(8h 触发 · 扫所有持仓 × funding) · 留 M2-C
- **mark price 定期更新 worker**(用于 unrealized_pnl + 强平检查) · 留 M2-C
- **强平 worker**(margin_balance < maintenance_margin → 强平) · 留 M2-C
- **前端 UI 全部**(landing page / 详情页合约 tab / 一键下单) · 留 M2-D
- **perp K 线增量 Celery 任务**(M2-A-9 留 stub) · 留 M2-B

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
