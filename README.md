# 点金 Midas

> 面向 A 股 / 美股 / 加密三市场的 AI 原生分析终端 · **仅虚拟资金交易,永不接真实下单**

## 状态

M0 开发中。完整启动文档(陌生人也能照着跑起来)会在 Task 1.4 落地。

## 仓库

```
midas/
├── apps/
│   ├── web/      Next.js 15 前端
│   ├── api/      FastAPI 后端
│   └── worker/   Celery worker
├── packages/
│   └── shared/   前后端共享类型契约
├── docker/       docker-compose + 初始化 SQL
└── docs/         产品 / 启动 / 调研文档
```

## 技术栈

- **前端** Next.js 15 + React 19 + TypeScript + Tailwind + shadcn/ui + KLineChart Pro
- **后端** FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) + Celery
- **数据** PostgreSQL 16 + ClickHouse + Redis
- **数据源** AKShare(A 股) + yfinance(美股) + ccxt(加密)

## 合规

模拟交易,不构成投资建议。
