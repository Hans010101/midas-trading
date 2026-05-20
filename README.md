# 点金 Midas

> 面向 **A 股 / 美股 / 加密** 三市场的 AI 原生分析终端。
> **仅虚拟资金交易,永不接真实下单。**

[![Status](https://img.shields.io/badge/M0-near%20complete-C8102E)]() [![License](https://img.shields.io/badge/license-Private-B8860B)]()

跨市场看图 → 自选股管理 → 虚拟下单 → 持仓盈亏 → 飞书 / Telegram 推送,M0 阶段端到端打通。

---

## 这是什么

「点金 Midas」是一个**模拟交易终端**:你能在同一界面看 A 股、美股、加密三市场的 K 线,用虚拟资金练习买卖,看真实手续费 + 滑点扣除下的盈亏,把成交通知推到飞书 / Telegram。

**不是什么:** 不是真实交易系统,不接券商通道。AI 决策 / 信号条目前是 M0 占位,M1 会接 DeepSeek + 缠论。

详细产品定位见 `docs/03-midas-project-plan.md` · 设计决策见 `docs/decisions/`。

---

## 前置要求

| 工具 | 版本 |
|---|---|
| **Docker Desktop** | 4.30+ · 内置 docker compose v2 |
| **Node.js** | 20 LTS |
| **pnpm** | 10.x · `corepack enable && corepack prepare pnpm@latest --activate` |
| **Python** | 3.11+(本地 venv 跑 pytest 用 · 不用本地启服务可跳过)|

**网络:** Binance(加密)/ AKShare(A 股)/ yfinance(美股)需要能直连。2026-05 实测国内直连可用;不行时用 `HTTPS_PROXY` 环境变量。

**资源:** 8GB RAM / 10GB 磁盘(ClickHouse + Postgres + 演示数据)。

---

## 快速启动(陌生人版)

```bash
# 1. 克隆
git clone <repo-url> midas
cd midas

# 2. 环境变量
cp .env.example .env
# 编辑 .env 填:
#   - SECRET_KEY(随机 32+ 字符,JWT 签名用)
#   - 其他保持默认即可

# 3. 启动全栈(Postgres + ClickHouse + Redis + api + worker + web)
docker compose -f docker/docker-compose.yaml up -d

# 4. 等所有容器 healthy(约 60-90s)
docker compose -f docker/docker-compose.yaml ps

# 5. 运行数据库迁移
docker compose -f docker/docker-compose.yaml exec api alembic upgrade head

# 6. 回填演示数据(3 标的 × 5 年日 K · ~3 分钟)
docker compose -f docker/docker-compose.yaml exec worker python -m tasks.data_ingest

# 7. 访问
open http://localhost:3000
```

**测试账号(本地开发免邮箱验证):**

如果没配 `RESEND_API_KEY`,直接 DB 造已验证账号:

```bash
HASH=$(docker compose -f docker/docker-compose.yaml exec -T api \
  python -c "from app.services.auth import hash_password; print(hash_password('Test123456'))")

docker compose -f docker/docker-compose.yaml exec -T postgres psql -U midas -d midas -c "
INSERT INTO \"user\" (id, email, password_hash, email_verified_at, age_confirmed, demo_prefilled, created_at, updated_at)
VALUES (gen_random_uuid(), 'hans@test.com', '$HASH', NOW(), true, false, NOW(), NOW())
ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, email_verified_at = NOW();
"
```

登录:`hans@test.com` / `Test123456`

---

## 服务端口

| 服务 | 端口 | 用途 |
|---|---|---|
| web | `:3000` | Next.js 前端 |
| api | `:8000` | FastAPI 后端(`/docs` Swagger UI) |
| postgres | `:5432` | 业务数据(用户 / 自选股 / 虚拟交易 / 通知配置) |
| clickhouse | `:8123` / `:9000` | K 线时序数据 |
| redis | `:6380` | Celery broker + 通知去重(注意:**6380** 不是 6379,避开本地其他项目占用) |

---

## 技术栈

- **前端:** Next.js 15 (App Router) · React 19 · TypeScript · Tailwind · shadcn/ui · KLineChart 10 · TanStack Query · NextAuth v5 · Zustand v5 · Sonner · recharts
- **后端:** FastAPI · Pydantic v2 · SQLAlchemy 2.0 async · Celery · Alembic · python-jose · passlib argon2id · httpx
- **数据:** PostgreSQL 16 · ClickHouse · Redis 7
- **数据源:** AKShare(A 股)· yfinance(美股)· ccxt(加密)
- **邮件:** Resend HTTP API(开发可用 mock)
- **测试:** pytest + httpx MockTransport · playwright

---

## 验收链路(M0)

1. **注册 → 邮箱验证 → 登录** · /register · /verify-email?token=... · /login
2. **看跨市场 K 线** · /workbench · 三市场 Tab + 4 周期 + 4 指标 + 顶部 SymbolSwitcher 临时切标的
3. **管理自选股** · 右栏列表 · ⌘K 搜索 · 拖拽排序 · 30s 静态报价
4. **设置虚拟资金** · /account · 每市场各币种独立(¥/$/USDT)· 不折算
5. **下单交易** · 顶部按钮 / Cmd+B/S 快捷键 · confirm 模态 · 滑点 + 手续费扣除
6. **看持仓 / 权益曲线** · /account · 动态显示已激活市场 · 软删历史持仓
7. **配置推送** · /settings · 飞书 webhook / TG bot · 测试按钮验证可达
8. **收成交通知** · 飞书 / TG 实时收到(需真实凭证)

完整自查报告见 `docs/M0-acceptance-report.md`。

---

## 视觉系统(严格执行)

- 主色 **中国红 #C8102E** · 辅 **帝王金 #B8860B**
- 涨用 **朱红 #DC143C** · 跌用 **墨绿 #0F6E5F**(A 股传统)
- 操作成功用帝王金 · **绝不绿色**(避涨跌色冲突)
- 衬线 Noto Serif SC · 正文 Noto Sans SC · 数据 JetBrains Mono
- 白底 + 米白卡 `#FCFCF9` · 米色边 `#F7F6F1`
- 虚拟交易元素必带「VIRTUAL · 模拟」帝王金徽章

详情见 `docs/decisions/0001-visual-direction.md`。

---

## 开发指南

### 跑测试

```bash
# Python 后端单元测试(本地 venv)
cd apps/api && .venv/bin/python -m pytest

# Python 后端测试(用容器跑,无需本地 venv)
docker compose -f docker/docker-compose.yaml exec api pytest

# 前端 type check
cd apps/web && pnpm tsc --noEmit

# 前端 lint
cd apps/web && pnpm lint
```

### 改 schema

```bash
# 改 app/models/*.py
# 然后 autogenerate migration:
cd apps/api && .venv/bin/alembic revision --autogenerate -m "describe change"

# 应用迁移:
docker compose -f docker/docker-compose.yaml exec api alembic upgrade head

# 同时迁移 test 数据库:
docker compose -f docker/docker-compose.yaml exec -e DATABASE_URL=postgresql+asyncpg://midas:midas_dev@postgres:5432/midas_test api alembic upgrade head
```

### 数据预热

```bash
# 演示数据(3 标的 × 5 年日 K · 首次启动必跑)
docker compose -f docker/docker-compose.yaml exec worker python -m tasks.data_ingest

# 多周期预热(15m / 1h / 1d / 1w · 速度较慢)
docker compose -f docker/docker-compose.yaml exec worker python -m tasks.data_ingest --periods 15m,1h,1d,1w
```

---

## 已知限制(M0 范围)

| 限制 | 影响 | 何时解决 |
|---|---|---|
| **数据精度** | NVDA / 600519 等 K 线价格跟实时市场可能不一致 | M1 数据审计 |
| **AKShare EM 接口不稳** | A 股 15m / 1h / 1w 周期偶尔 EmptyKline | 0002 翻车 4 · 已切 Sina 部分缓解 |
| **AI 决策卡 / 信号条** | M0 占位,无实际功能 | M1 接 DeepSeek + 缠论 |
| **专业绘图工具栏** | 左栏占位,无功能 | M1 缠论笔/段/枢纽标注 |
| **WebSocket 实时报价** | 当前 30s 客户端轮询 | Task 4-B |
| **右键 K 线下单** | 当前只有顶部按钮 + Cmd+B/S 快捷键 | 0008 ADR 已设计 · M0 后补 |
| **Google OAuth** | M0 仅邮箱密码登录 | Task 7.1 上线准备(产品决策)|
| **Token 加密存储** | 飞书 webhook / TG bot token 明文 | M1 用 Fernet 加密 |
| **真实推送测试** | 后端 mock 全覆盖,但真飞书 / TG 凭证需用户自配后才能端到端测 | 用户配置后即可测 |
| **A 股 100 股整数倍** | 当前撮合允许任意股数 | M1 严格化 |
| **T+1 限制** | 当前 A 股买入当天可卖 | M1 严格化(教学优先,M0 简化)|

完整 defer 清单见 `docs/M0-acceptance-report.md`。

---

## 文档导览

- `docs/04-manus-kickoff-prompt.md` — M0 启动文档(原始需求)
- `docs/03-midas-project-plan.md` — 项目计划 v2
- `docs/decisions/` — 9 份 ADR(0001 视觉 / 0002 数据源翻车 / 0003 LLM / 0004 K 线选型 / 0005 空数据态 / 0006 鉴权 / 0007 自选股 / 0008 虚拟交易 / 0009 推送)
- `docs/screenshots/` — 各 Checkpoint 视觉验证截图
- `docs/M0-acceptance-report.md` — M0 终验自查报告
- `CLAUDE.md` — Claude Code 协作规范 + 项目铁律

---

## 红线

- 永不接入真实交易通道
- AI / 策略 / 交易输出必带「仅供参考,不构成投资建议」
- 不在前端塞 API Key
- 推送 emit 必须异步,绝不阻塞下单
- 操作成功用帝王金,绝不绿色

---

## License

Private(M0 内部开发阶段)。
