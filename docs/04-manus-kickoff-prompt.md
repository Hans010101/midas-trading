# Manus 启动 Prompt · 点金 Midas M0

> **使用方式：** 把这份文件全文复制给 Manus,作为第一个任务 (one-shot)。  
> **预期工时：** 170h (Manus 跑 3-4 周)  
> **预期产出：** 一个本地能跑、可注册、可看跨市场 K 线、可下虚拟单、可推送飞书/TG 的完整骨架。  
> **代码语言：** Python + TypeScript,所有代码必须用 2025 年的最新语法。

---

## ⚙️ 项目身份

你正在为我搭建一个名为 **点金 Midas** 的金融分析终端,产品定位:

- **面向跨市场散户的 AI 原生分析终端**(A 股 + 美股 + 加密三市场)
- **仅虚拟资金交易,永不接入真实交易通道**(合规边界,产品 DNA)
- 用户体验类似中国的"观潮 TideView"工具,但增加美股 + 加密 + 虚拟交易闭环
- 视觉风格:**白底 + 中国红主色 + 帝王金点缀 + 衬线中文**

你的角色:从 0 搭建项目的全部基础设施和"基本能用"的工作流。M0 之后会有 M1(缠论 + AI Agent)、M2(策略与回测)等里程碑,所以你写的代码需要为后续扩展留好接口。

---

## 🎯 M0 验收标准 (最重要)

完成 M0 之后,**陌生人在自己电脑上**应该能完成下面这条完整链路:

1. `git clone` 项目 → `docker-compose up` → 浏览器打开 localhost:3000
2. 注册账号 → 邮箱验证 → 登录
3. 切换市场 Tab (A 股 / 美股 / 加密) → 搜索任意标的(如 600519 / NVDA / BTC) → 看到 K 线图 + 4 个指标
4. 把标的加入自选股池 → 自选股列表实时刷新报价(涨用朱红、跌用墨绿)
5. 在 K 线上右键 → "建立虚拟买单" → 弹出对话框确认数量 → 写入虚拟账户
6. 个人设置页填写飞书 webhook + TG bot token → 一键测试,立即收到测试消息
7. 刚才那笔虚拟买单触发推送 → 飞书 / TG 收到结构化卡片
8. 个人主页 → 看到权益曲线 + 持仓饼图

**如果这条链路全程顺滑且视觉精美,M0 完成。**

---

## 📐 技术栈(不可更改)

### 前端

- **Next.js 15** App Router + React 19 + TypeScript 5.6+
- **Tailwind CSS 3.4** + **shadcn/ui** (用 latest CLI 安装)
- **KLineChart Pro** (npm: `@klinecharts/pro`) 用于 K 线图表
- **TanStack Query v5** 用于数据获取与缓存
- **Zustand** 用于客户端状态管理
- **NextAuth.js v5 (Auth.js)** 用于认证
- **next-themes** 暗黑模式 token 预留(本期不实现切换)

### 后端

- **Python 3.11+** (不要用 3.12 之前的)
- **FastAPI 0.115+** + **Pydantic v2** + **SQLAlchemy 2.0 (async)**
- **Celery 5.4** + **Redis** 作为 broker
- **alembic** 数据库迁移
- **httpx** 用于外部 HTTP 调用

### 数据

- **PostgreSQL 16** — 业务数据(用户/订阅/虚拟账户/订单等)
- **ClickHouse latest** — K 线时序数据
- **Redis 7** — 缓存 + Celery broker + WebSocket pub/sub

### 数据源 SDK

- **AKShare** (`akshare`) — A 股
- **yfinance** — 美股
- **ccxt** — 加密(Binance 现货)

### 工具

- **Turborepo** 单仓管理
- **pnpm** 包管理器
- **docker-compose** 本地编排
- **GitHub Actions** CI/CD

---

## 📁 仓库结构

```
midas/
├── apps/
│   ├── web/                  # Next.js 15 前端
│   │   ├── app/              # App Router
│   │   ├── components/       # 业务组件
│   │   ├── lib/              # 工具函数 / API client
│   │   ├── hooks/            # React hooks
│   │   ├── styles/           # Tailwind + 全局 CSS
│   │   ├── public/fonts/     # Noto Serif SC, Noto Sans SC, JetBrains Mono (子集化)
│   │   └── package.json
│   ├── api/                  # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/v1/       # API 路由
│   │   │   ├── core/         # 配置 / 数据库 / 认证
│   │   │   ├── models/       # SQLAlchemy 模型
│   │   │   ├── schemas/      # Pydantic schemas
│   │   │   ├── services/     # 业务逻辑
│   │   │   └── deps.py       # 依赖注入
│   │   ├── alembic/          # 数据库迁移
│   │   └── pyproject.toml
│   └── worker/               # Celery worker
│       ├── tasks/
│       │   ├── data_ingest.py    # 数据同步
│       │   ├── notification.py   # 飞书/TG 推送
│       │   └── monitoring.py     # 数据健康检查
│       └── celery_app.py
├── packages/
│   ├── shared/               # 前后端共享 TypeScript 类型 (从 OpenAPI 自动生成)
│   └── eslint-config/        # 统一 lint 配置
├── docker/
│   ├── docker-compose.yml
│   ├── postgres.Dockerfile
│   └── clickhouse-init.sql
├── .github/workflows/
│   ├── ci.yml                # 测试 + lint
│   └── deploy.yml            # 部署到 Vercel + Cloud Run
├── turbo.json
├── pnpm-workspace.yaml
└── README.md                 # 包含完整启动步骤
```

---

## 🎨 视觉系统(严格执行)

### Tailwind config 主题变量

完全照下面这套写到 `apps/web/tailwind.config.ts`:

```typescript
import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 主色系
        midas: {
          red: '#C8102E',           // 主色 · 中国红
          'red-deep': '#9E1024',    // 主色 hover
          'red-soft': '#E84560',
          'red-glow': 'rgba(200,16,46,0.06)',
          'red-tint': 'rgba(200,16,46,0.12)',
        },
        gold: {
          DEFAULT: '#B8860B',       // 辅色 · 帝王金
          soft: '#D4A72C',
          glow: 'rgba(184,134,11,0.08)',
        },
        // 中性
        ink: {
          DEFAULT: '#1A1A1A',
          dim: '#5A5A62',
          faint: '#94949C',
        },
        // 背景
        paper: '#F7F6F1',
        cream: '#FCFCF9',
        // 涨跌(A 股传统)
        bull: '#DC143C',            // 涨用朱红
        bear: '#0F6E5F',            // 跌用墨绿
        // 警告 / 警示
        warn: '#B45309',
      },
      fontFamily: {
        serif: ['"Noto Serif SC"', 'serif'],
        sans: ['"Noto Sans SC"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        sm: '2px',
        DEFAULT: '4px',
        md: '6px',
        lg: '8px',
      },
    },
  },
}

export default config
```

### shadcn/ui 主题

在 `apps/web/app/globals.css` 设置 CSS 变量,把 shadcn 默认 primary 改成 `--midas-red`。提供完整可用的 light theme 主题,**不实现 dark theme**(预留 token 即可)。

### 字体加载

- 用 `next/font/google` 加载 Noto Serif SC、Noto Sans SC、JetBrains Mono
- 子集化只加载常用 3500 字 + 标点
- 用 `display: swap` 避免 FOIT

### 设计原则

1. **白底为主**,纯白 `#FFFFFF` 主背景 + 暖米白 `#FCFCF9` 卡片背景
2. **中国红强调** —— 标题、CTA、印章、强调标签
3. **帝王金点缀** —— 标签、徽章、辅助强调
4. **衬线中文标题** —— 所有 h1-h3 用 Noto Serif SC,正文用 Noto Sans SC
5. **数据等宽字体** —— 所有数字(价格、K 线刻度、订单 ID)用 JetBrains Mono
6. **印章风元素** —— Hero 区右上角放红底白字"点金"印章 (110x110, 旋转 -4 度, 内描边)
7. **VIRTUAL 徽章** —— 所有虚拟交易元素必带帝王金边框徽章,文字"VIRTUAL · 模拟"

---

## 🛠 详细任务清单

### Task 1 · 基础设施(~25h)

#### 1.1 Monorepo 初始化

- 用 Turborepo 初始化,pnpm 作为包管理器
- `turbo.json` 配置好 dev / build / lint / test 流水线
- `packages/shared` 用 `openapi-typescript` 从 FastAPI 自动生成的 OpenAPI schema 生成 TypeScript 类型,前后端共享类型契约

#### 1.2 Docker Compose

`docker/docker-compose.yml` 包含:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: midas
      POSTGRES_USER: midas
      POSTGRES_PASSWORD: midas_dev
    ports: ["5432:5432"]
    volumes: [postgres_data:/var/lib/postgresql/data]
  
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports: ["8123:8123", "9000:9000"]
    volumes:
      - clickhouse_data:/var/lib/clickhouse
      - ./clickhouse-init.sql:/docker-entrypoint-initdb.d/init.sql
  
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  
  api:
    build: ../apps/api
    depends_on: [postgres, clickhouse, redis]
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://midas:midas_dev@postgres:5432/midas
      CLICKHOUSE_URL: clickhouse://clickhouse:9000/default
      REDIS_URL: redis://redis:6379/0
  
  worker:
    build: ../apps/worker
    depends_on: [api, redis]
    environment:
      CELERY_BROKER_URL: redis://redis:6379/1
  
  web:
    build: ../apps/web
    depends_on: [api]
    ports: ["3000:3000"]
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
```

#### 1.3 CI/CD

`.github/workflows/ci.yml`:

- Lint 所有代码 (`eslint`, `ruff`)
- Type-check (`tsc --noEmit`, `mypy`)
- 跑单元测试 (`vitest` 前端, `pytest` 后端)
- 构建产物
- 在 PR 上自动跑

#### 1.4 README

完整启动文档,确保陌生人按步骤能跑起来。最少包含:

1. 前置要求 (Docker, Node 20+, Python 3.11+, pnpm 9+)
2. 克隆 + 安装 (`pnpm install`)
3. 起服务 (`docker-compose up -d`)
4. 跑数据库迁移 (`pnpm migrate`)
5. 初次数据回填 (`pnpm seed`)
6. 启动开发 (`pnpm dev`)
7. 访问 http://localhost:3000

---

### Task 2 · 数据层全接通(~40h)

#### 2.1 统一行情接口设计

`apps/api/app/api/v1/market.py`:

```python
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Literal
from datetime import datetime

router = APIRouter(prefix="/market", tags=["market"])

Market = Literal["cn", "us", "crypto"]
Period = Literal["1m", "5m", "15m", "30m", "1h", "1d", "1w"]

class Kline(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float | None = None

class KlineResponse(BaseModel):
    symbol: str
    market: Market
    period: Period
    items: list[Kline]

@router.get("/kline", response_model=KlineResponse)
async def get_kline(
    symbol: str = Query(..., examples=["600519", "NVDA", "BTC/USDT"]),
    market: Market = Query(...),
    period: Period = Query("1d"),
    limit: int = Query(500, ge=1, le=5000),
):
    """统一行情接口,三市场抹平差异"""
    # 实现:先查 ClickHouse,缺失再回源
    pass
```

#### 2.2 数据源适配层

`apps/api/app/services/data_sources/`:

- `cn_source.py` 封装 AKShare 调用
- `us_source.py` 封装 yfinance 调用
- `crypto_source.py` 封装 ccxt(Binance 现货)

每个适配器返回**标准化的 `Kline` 列表**,抹平差异。

#### 2.3 ClickHouse K 线表

`docker/clickhouse-init.sql`:

```sql
CREATE TABLE IF NOT EXISTS kline (
    symbol String,
    market Enum8('cn'=1, 'us'=2, 'crypto'=3),
    period Enum8('1m'=1, '5m'=2, '15m'=3, '30m'=4, '1h'=5, '1d'=6, '1w'=7),
    ts DateTime,
    open Float64,
    high Float64,
    low Float64,
    close Float64,
    volume Float64,
    amount Float64
) ENGINE = MergeTree
PARTITION BY (market, toYear(ts))
ORDER BY (symbol, period, ts)
SETTINGS index_granularity = 8192;

CREATE TABLE IF NOT EXISTS symbol_meta (
    symbol String,
    market Enum8('cn'=1, 'us'=2, 'crypto'=3),
    name String,
    name_en String,
    listed_date Date,
    is_active UInt8 DEFAULT 1,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (market, symbol);
```

#### 2.4 历史回填 worker

`apps/worker/tasks/data_ingest.py`:

- A 股全市场 5 年日 K (从 AKShare 拉股票列表,逐只回填)
- 美股 Top 500 (S&P 500) + 热门 ETF (QQQ/SPY/VOO等)
- 加密 Top 100 USDT 永续 + 现货
- 每个标的回填后写入 `symbol_meta`
- 用 Celery `chord` 并发回填,带进度展示(写入 Redis,前端可查询进度)

#### 2.5 增量更新 worker

`apps/worker/tasks/data_ingest.py` 中:

- A 股:每个交易日 15:30 (北京时间) 跑一次 (Celery beat schedule)
- 美股:每个交易日 5:30 (北京时间) 跑一次
- 加密:每分钟跑一次 (订阅 ccxt websocket 实时推送 + 每分钟落库的混合方案)
- 增量更新失败要自动重试 3 次

#### 2.6 数据健康监控

`apps/worker/tasks/monitoring.py`:

- 每小时检查 ClickHouse 数据缺口 (按预期 K 线数对比)
- 缺口超过 5% 触发飞书 / TG 告警
- 数据源失效检测 (AKShare/yfinance/ccxt 任一连续失败) 触发告警

---

### Task 3 · K 线工作台(~30h)

#### 3.1 KLineChart Pro 封装

`apps/web/components/chart/KlineChart.tsx`:

- 用 `@klinecharts/pro` 初始化
- props: `symbol`, `market`, `period`, `indicators?`
- 接收 props 后自动调用 API 拿数据并渲染
- 暴露 overlay API (`addAnnotation`, `removeAnnotation`) 给后续 M1 缠论标注用
- 涨用朱红 `#DC143C`,跌用墨绿 `#0F6E5F`
- 十字光标颜色用主色 `#C8102E`
- 网格线极淡 `#F0EEE8`
- 价格刻度用 JetBrains Mono 字体

#### 3.2 周期切换器

`apps/web/components/chart/PeriodSwitcher.tsx`:

- 4 个 tab: 15分 / 1小时 / 日 / 周
- 用 Tailwind + shadcn `<Tabs />` 组件
- 选中状态:主色背景 + 白字
- 未选中:幽灵按钮风格,hover 帝王金

#### 3.3 4 个指标(MA / MACD / RSI / BOLL)

- MA: 主图叠加,5/10/20/60 四条均线,颜色帝王金渐变
- MACD: 副图,DIF/DEA/MACD 三条
- RSI: 副图,14 周期,70/30 超买超卖线
- BOLL: 主图,布林带上中下三轨

每个指标:可叠加可关闭,关闭状态用 localStorage 持久化用户偏好(注意 NextJS 中要在 useEffect 里读)。

#### 3.4 工作台三栏布局

`apps/web/app/workbench/page.tsx`:

```
┌─────────────────────────────────────────────────┐
│ Header: Logo "点金" + 市场Tab + 用户菜单         │
├─────┬─────────────────────────────────┬─────────┤
│ 左  │                                  │   右   │
│ 绘  │  K 线 + 4 指标                    │ 自选股 │
│ 图  │                                  │  列表  │
│ 工  │  顶部信号条占位                    │       │
│ 具  │                                  │ AI 决策│
│ 栏  │                                  │ 卡占位 │
│     │                                  │       │
└─────┴─────────────────────────────────┴─────────┘
```

- 左侧绘图工具栏 60px 宽,垂直排列工具按钮 (本期占位即可,M1 实装)
- 中央 K 线区自适应,顶部留 40px 信号条占位 (M1 实装)
- 右侧 280px,上半自选股,下半 AI 决策卡占位 (M1 实装)

---

### Task 4 · 自选股(~15h)

#### 4.1 数据模型

```python
# apps/api/app/models/watchlist.py
class WatchlistGroup(Base):
    __tablename__ = "watchlist_group"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str]
    sort_order: Mapped[int] = mapped_column(default=0)
    is_default: Mapped[bool] = mapped_column(default=False)

class WatchlistItem(Base):
    __tablename__ = "watchlist_item"
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("watchlist_group.id"))
    symbol: Mapped[str]
    market: Mapped[str]  # cn/us/crypto
    sort_order: Mapped[int] = mapped_column(default=0)
    added_at: Mapped[datetime]
```

#### 4.2 API

- `GET /api/v1/watchlist/groups` 用户所有分组
- `POST /api/v1/watchlist/groups` 新建分组
- `POST /api/v1/watchlist/items` 加入自选
- `DELETE /api/v1/watchlist/items/{id}` 移除
- `PUT /api/v1/watchlist/items/reorder` 拖拽排序

#### 4.3 实时报价

- 前端 WebSocket 连接 `/ws/quotes?symbols=600519.cn,NVDA.us,BTC/USDT.crypto`
- 后端 Worker 每秒从 ClickHouse 拉最新报价 → Redis pub
- WebSocket 服务订阅 Redis pub → 推送给所有订阅了该 symbol 的客户端
- 价格变化时:
  - 涨 → 数字短暂闪烁朱红背景
  - 跌 → 数字短暂闪烁墨绿背景

#### 4.4 搜索

`apps/web/components/watchlist/SymbolSearch.tsx`:

- 输入框,Cmd+K 唤起 (用 `cmdk` 库)
- 支持三种输入:
  - 代码 (600519, NVDA, BTC)
  - 中文名 (贵州茅台, 英伟达)
  - 拼音 (gzmt, yiweida)
- 搜索接口 `GET /api/v1/search?q=xxx` 返回跨市场结果
- 结果按 market 分组展示

---

### Task 5 · 虚拟交易骨架(~20h)

#### 5.1 数据模型(沿用 CryptoSharp 设计经验)

```python
# apps/api/app/models/virtual.py
class VirtualAccount(Base):
    __tablename__ = "virtual_account"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True)
    initial_capital: Mapped[Decimal]  # 初始资金,默认 100万
    cash_balance: Mapped[Decimal]
    market_value: Mapped[Decimal]      # 总持仓市值
    total_equity: Mapped[Decimal]      # 总权益 = cash + market_value
    total_pnl: Mapped[Decimal]         # 累计盈亏
    created_at: Mapped[datetime]

class VirtualPosition(Base):
    __tablename__ = "virtual_position"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("virtual_account.id"))
    symbol: Mapped[str]
    market: Mapped[str]
    quantity: Mapped[Decimal]
    avg_cost: Mapped[Decimal]
    current_price: Mapped[Decimal]
    market_value: Mapped[Decimal]
    unrealized_pnl: Mapped[Decimal]

class VirtualOrder(Base):
    __tablename__ = "virtual_order"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("virtual_account.id"))
    symbol: Mapped[str]
    market: Mapped[str]
    side: Mapped[str]  # buy/sell
    order_type: Mapped[str]  # market/limit
    quantity: Mapped[Decimal]
    price: Mapped[Decimal]
    filled_price: Mapped[Decimal | None]
    fee: Mapped[Decimal]
    slippage: Mapped[Decimal]
    status: Mapped[str]  # pending/filled/cancelled
    source: Mapped[str]  # manual/strategy/ai
    created_at: Mapped[datetime]
    filled_at: Mapped[datetime | None]

class VirtualEquityCurve(Base):
    __tablename__ = "virtual_equity_curve"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("virtual_account.id"))
    ts: Mapped[datetime]  # 每日 15:00 + 每次成交时
    total_equity: Mapped[Decimal]
    cash_balance: Mapped[Decimal]
    market_value: Mapped[Decimal]
```

#### 5.2 手动下单 demo

`apps/web/components/chart/OrderDialog.tsx`:

- 在 K 线上右键 → 弹出菜单 → 选"建立虚拟买单" / "建立虚拟卖单"
- 对话框:
  - 标的(自动带入)
  - 方向(自动带入)
  - 数量(可输入)
  - 当前价(自动)
  - 预估成交价 = 当前价 + 滑点
  - 预估手续费 (按市场)
  - 总成本
  - **顶部必带帝王金徽章 "VIRTUAL · 模拟交易"**
  - "确认建仓"按钮(主色中国红)

#### 5.3 滑点 + 手续费规则

```python
# apps/api/app/services/virtual_trading.py
FEE_RATES = {
    "cn": {"buy": 0.0003, "sell": 0.0013},   # 含印花税
    "us": {"buy": 0, "sell": 0},              # 零佣
    "crypto": {"buy": 0.001, "sell": 0.001},  # Binance 现货
}

SLIPPAGE_BPS = {
    "cn": 5,        # 5 个基点
    "us": 3,
    "crypto": 10,
}
```

#### 5.4 权益曲线展示

`apps/web/app/dashboard/page.tsx`:

- 用 Recharts 画一张折线图
- X 轴:时间(支持 1D/1W/1M/3M/1Y/全部)
- Y 轴:总权益
- 主色折线 + 半透明红色填充
- 旁边一张持仓占比饼图:按 market 分组(A 股 / 美股 / 加密)

---

### Task 6 · 飞书 + TG 推送(~15h)

#### 6.1 用户配置面板

`apps/web/app/settings/notifications/page.tsx`:

- 飞书 webhook URL 输入框 + 测试按钮
- TG bot token + chat ID 输入框 + 测试按钮
- 测试按钮点击:
  - 调 `POST /api/v1/notifications/test?channel=feishu`
  - 后端发"🔔 这是来自点金 Midas 的测试消息" 到对应渠道
  - 成功显示绿色 ✓,失败显示具体错误

#### 6.2 通知事件系统

`apps/api/app/services/notification.py`:

- 定义 Event 类型:
  - `VirtualOrderCreated` (建仓)
  - `VirtualOrderClosed` (平仓)
  - `WatchlistPriceAlert` (自选股价格异动 ≥3%)
- 每个 Event 触发后,Worker 异步推送
- 用户可在设置里勾选订阅哪些 Event

#### 6.3 消息模板

飞书富文本卡片(沿用 CryptoSharp 风格):

```python
# 建仓推送示例
FEISHU_ORDER_CREATED = {
    "msg_type": "interactive",
    "card": {
        "header": {
            "title": {"tag": "plain_text", "content": "🟢 虚拟建仓 · {symbol_name}"},
            "template": "red"  # 红色头部
        },
        "elements": [
            {
                "tag": "div",
                "fields": [
                    {"is_short": True, "text": {"tag": "lark_md", "content": "**标的**\n{symbol}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "**方向**\n买入"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "**价格**\n¥{price}"}},
                    {"is_short": True, "text": {"tag": "lark_md", "content": "**数量**\n{quantity}"}},
                ]
            },
            {"tag": "hr"},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": "VIRTUAL · 模拟交易,不构成投资建议"}]}
        ]
    }
}
```

TG 用 Markdown:

```markdown
🟢 *虚拟建仓 · {symbol_name}*

标的: `{symbol}`
方向: 买入
价格: ¥{price}
数量: {quantity}

_VIRTUAL · 模拟交易,不构成投资建议_
```

---

### Task 7 · 中国红视觉系统(~25h)

#### 7.1 首页 (apps/web/app/page.tsx)

- Hero 区:
  - 右上角红底白字"点金"印章,旋转 -4 度
  - 大标题"点金 Midas · 让模糊的市场信号点石成金"(衬线字体)
  - 副标题"面向 A 股 / 美股 / 加密的 AI 原生分析终端"
  - 两个 CTA:"立即体验"(主色红) + "查看演示"(描边红)
- 三市场展示区:三张卡片,每张展示一个市场样例
- 功能预览区:K 线 + AI + 虚拟交易 + 推送 四个核心特性
- 定价区(本期占位,M3 实装)
- 合规外壳:全站 footer 写"模拟交易,不构成投资建议"

#### 7.2 工作台 (apps/web/app/workbench/page.tsx)

按 Task 3.4 描述的三栏布局实装。视觉要求:

- 顶部 header 白底 + 1px 红色 border-bottom
- 左侧绘图工具栏纯白背景 + 工具按钮米白底
- 中央 K 线区暖米白 (#FCFCF9) 背景 + 白色 K 线卡片
- 右侧自选股 + AI 卡区域纯白背景 + 1px 红色 border-left
- 所有 hover 状态用 `red-glow` 背景

#### 7.3 shadcn/ui 主题定制

下面这些 shadcn 组件全部染色:

- `<Button variant="default">` → 主色中国红 + 白字
- `<Button variant="outline">` → 白底红边红字
- `<Button variant="ghost">` → 透明底 hover 米白
- `<Input>` → focus 红色 ring
- `<Dialog>` → 顶部 1px 红色 border
- `<Tabs>` → 选中 tab 红色 underline
- `<Card>` → 暖米白背景 + 1px 米色 border

#### 7.4 VIRTUAL 徽章组件

`apps/web/components/ui/VirtualBadge.tsx`:

```tsx
export function VirtualBadge({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  return (
    <span className={cn(
      "inline-flex items-center font-mono tracking-wider",
      "bg-gold/8 border border-gold/40 text-gold rounded-full",
      size === 'sm' && "text-[10px] px-2 py-0.5",
      size === 'md' && "text-xs px-2.5 py-1",
      size === 'lg' && "text-sm px-3 py-1.5",
    )}>
      VIRTUAL · 模拟
    </span>
  )
}
```

在所有跟虚拟交易相关的位置(订单页、持仓页、对话框、推送)都强制带上这个徽章。

---

## 📋 CryptoSharp 业务知识嫁接清单

下面这些是我从 CryptoSharp 项目积累的实战经验,你需要在写代码时把这些规则内化:

### 风控规则(虚拟交易引擎必须遵守)

1. **单笔仓位上限**:任意单笔订单的金额不超过账户总权益的 20%
2. **单标的持仓上限**:任意单一标的的持仓不超过账户总权益的 30%
3. **同向连续亏损熔断**:连续 3 笔同向交易亏损 → 暂停该标的当日交易
4. **价格异常检测**:如果成交价偏离当前价 >5%,拒绝订单
5. **市场休市检测**:A 股 / 美股非交易时段,只允许加密交易

### 推送的"好实践"

1. **频率限制**:同一标的同类型告警,5 分钟内只推 1 次
2. **静默时段**:用户可设置"22:00-08:00 不打扰"(非紧急消息)
3. **聚合推送**:同时发生 3 件以上事件 → 聚合成一条
4. **失败重试**:推送失败自动重试 3 次,间隔 1/5/15 分钟

### 用户体验细节

1. **下单确认快速通道**:对老用户,允许在设置里关闭"二次确认"对话框
2. **K 线持久化**:用户在某只标的的图上画过线、加过指标 → 切换标的回来时保留
3. **首屏自选股**:默认按"最近活跃"排序,而非按"添加时间"
4. **数字千分位**:所有 4 位以上数字加千分位逗号

---

## ✅ 交付物 Checklist

完成后,你需要提供:

- [ ] 完整 Git 仓库,所有代码通过 lint + type-check + 测试
- [ ] `README.md` 详细到陌生人跟着能跑起来
- [ ] 一份截图清单(放在 `docs/screenshots/`),证明 M0 验收链路全部走通
- [ ] OpenAPI 文档自动生成到 `/docs` 路由可访问
- [ ] 至少 80% 测试覆盖率(后端核心服务)
- [ ] 部署文档:如何部署到 Vercel(前端) + Cloud Run(后端) + 自建数据库

---

## 🚫 不要做的事

1. **不要**接入任何真实交易通道(币安/券商/Coinbase 等的下单 API)
2. **不要**生成任何"必赚 / 必涨 / 保证收益"的营销文案
3. **不要**用过时语法(class component / pages router / Pydantic v1)
4. **不要**在前端塞 API Key 等机密
5. **不要**未经讨论引入新依赖(Tauri/Electron/桌面端等都是 M5 的事)
6. **不要**实现暗黑模式(M0 只做白天主题,token 预留即可)
7. **不要**实现 M1 之后的功能(缠论、AI Agent、回测、支付都不在 M0 范围内)

---

## 📞 沟通约定

跑这份 Prompt 期间:

1. **每完成一个 Task 暂停一次,等我 Review** —— 不要 7 个 Task 一口气跑完
2. **遇到歧义先问,不要凭猜测**写代码
3. **每天结束时给我一份进度报告**:已完成、进行中、明日计划、阻塞点
4. **commit message 用中文** + 任务编号前缀,如 `[Task 2.3] 实现 ClickHouse K 线表`
5. **小步提交**,每个功能点一个 commit,方便我 Review

---

**最后:** 这份 Prompt 大概可以驱动 170 工时的工作。你不需要一次性写完所有代码,而是按 Task 顺序逐步推进,每个 Task 完成后 commit + push,等我确认再进下一个。

Ready? Begin with Task 1.1.

---

*◆ 点金 MIDAS · M0 Manus Kickoff Prompt · 2026.05.19 ◆*
