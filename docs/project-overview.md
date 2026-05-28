# 点金 Midas · 项目现状全景

**生成日期**:2026-05-28
**生成方式**:Claude Code 通读 main 分支代码 + 全部 28 个 ADR(0001-0031 · 缺号 0017-0020 在 feature 分支 — 见 §1.7)
**用途**:给产品方做"先完成再完美 · 补模块骨架"规划用的全局地图
**红线**:基于**实际代码**而非猜测 · 不确定处明确标 "⚠️ 待确认"

---

## 0. 一句话定位

> **面向 A 股 / 美股 / 加密 三市场的 AI 原生分析终端**
> **仅虚拟资金交易 · 永不接真实下单**(产品 DNA · 任何场景下都不变)
> 网页 · Telegram bot 双通道 · 全程虚拟教学

**当前阶段**:M0 验收已过(注册→看 K 线→虚拟单→TG 推送 全链路通)+ M1 全期(缠论+AI+前端首页+TG bot)+ M2 加密 Pro(数据层+REST+虚拟永续合约 逐仓+全仓+资金费)+ N1-N4 告警降噪 上线 main 并部署到生产。

**生产部署**:`api.midastrade.asia`(API)· `midastrade.asia`(Web)· 香港 VPS · 模式 B 全栈 · GitHub Actions 自动部署。

---

## 1. 已建模块清单

### 1.1 跨市场行情终端(M0+M1 · 完整上线)

| 模块 | 做了什么 | 核心文件 | ADR | 成熟度 |
|---|---|---|---|---|
| **A 股行情** | K线 + 日K增量 + 列表榜单 + 行业板块 + 情绪条 + 大盘指数 + 交易日历 | `services/data_sources/cn_source.py`(508 行 · akshare)· `clickhouse_cn_market.py` · `cn_market.py`(纯逻辑)· `api/v1/cn.py` | 0023 § 阶段③(3.1+3.2) | ✅ 完整 |
| **美股行情** | K线 + 列表榜单 + GICS 行业板块 + 中概股板块 + 策展池 ~128(yfinance) | `services/data_sources/us_source.py`(306 行)· `us_pool.py` · `clickhouse_us_market.py` · `us_market.py` · `api/v1/us.py` | 0023 § 阶段③(3.3) | ✅ 完整 |
| **加密行情** | K 线(spot + perp)+ 24h ticker + OI + funding rate + long/short(账户/持仓)+ taker buy/sell + premium index + Fear&Greed + 全市场总市值 | `services/data_sources/crypto_source.py`(208 行 · ccxt Binance Spot)+ `binance_futures_source.py`(588 行 · Futures 直连)+ `coingecko_source.py`+ `alternative_me_source.py` · `clickhouse_crypto.py` · `api/v1/crypto.py` | 0017(feat 分支)+ 0018 | ✅ 完整(数据维度最全) |
| **缠论引擎** | 笔 + 顶/底分型 + 中枢(czsc 集成)· REST 端点 + 前端 K 线标注层 + 工具栏开关 + 五色专用配色 | `services/analysis/chan.py`(402 行 · czsc adapter)· `api/v1/analysis.py` · `components/chart/` | 0011 | ✅ M1 一波(笔/分型/中枢);M1 二波(段/买卖点/中枢扩展)defer |
| **AI 决策卡** | LangGraph 单 Agent(M1 二波)· DeepSeek 主 LLM · 技术面分析卡 · 缓存 · usage 记账 · validator | `services/ai/workflow.py`(268 行 · 6 节点 graph)· `llm.py` · `indicators.py` · `cache.py` · `validator.py` · `usage.py`(923 行 total)· `api/v1/analysis.py /decision-card` | 0012 + 0003 | ✅ M1 二波单 Agent 上线;M2 扩 4 Agent 并行未做 |
| **K 线图前端** | klinecharts@10 + React 19 薄 wrapper + 4 周期(15m/1h/1d/1w)+ MA/MACD/RSI/BOLL + 标的切换 + 工作台三栏布局 | `apps/web/components/chart/` · `components/workbench/` · `app/workbench/page.tsx` | 0004 + 0005 | ✅ 完整 |
| **首页 / 官网** | 9 板块(TopNav/Hero/Showcase/Markets/Features/AiChan/Pricing/CTA/Footer)· SSG · 水墨视觉 · 印章 SVG | `apps/web/app/page.tsx`(623 行 · `dynamic = 'force-static'`) | — | ✅ M1-E v3 完整 |
| **市场首页**(三市场) | `/cn-market` · `/us-market` · `/crypto-market` · 大盘指数 + 交易状态机 + 榜单 + 板块 | `apps/web/app/{cn,us,crypto}-market/` · `components/market-home/` | 0023 § 3.1-3.3 | ✅ 完整(crypto 最厚 411 行)|
| **个股详情**(spot) | `/cn-preview` · `/us-preview` · 单标的 K 线 + 缠论 + 自选 + 下单 | `apps/web/app/{cn,us}-preview/` · `components/spot-preview/` | 0023 | ⚠️ 待确认页面行为(`page.tsx` 仅 20 行,可能引用组件实现) |
| **加密详情**(perp) | `/crypto-preview` · 含资金费 / OI / 多空比 / 基差 / 24h 等衍生指标 | `apps/web/app/crypto-preview/` · `components/crypto-preview/`(24.3 kB First Load) | 0017 + 0019 + 0020 | ✅ 完整(本期数据维度最全) |

### 1.2 用户系统(认证 + 自选 + 钱包)

| 模块 | 做了什么 | 核心文件 | ADR | 成熟度 |
|---|---|---|---|---|
| **认证** | 邮箱注册 + 18+ 强制勾选 + argon2id + Resend 邮件验证 + JWT session + 路由保护中间件 + Session DB 表(M1-A 后) | `services/auth.py` · `services/email.py` · `api/v1/auth.py` · `models/{user,verification_token,session}.py` · `apps/web/app/{login,register,verify-email}/` · `auth.ts` + `middleware.ts` | 0006 | ✅ 完整(M0 第 1-2 步 · NextAuth v5) |
| **Google OAuth** | Google 登录 / 注册 · `user.google_sub` 字段 + alembic d8e2f4a5c7b9 | `services/auth.py` · 迁移 `user_google_oauth` | 0006(Task 7.1)| ⚠️ 待确认 UI 入口是否接 |
| **自选股**(Watchlist) | 三市场扁平表 + 增删改查 + 拖拽排序 + Cmd+K 搜索 + 30s 静态报价 + 空表预填 3 demo | `models/watchlist.py` · `services/.../`(没单独 dir)· `api/v1/watchlist.py` · `apps/web/components/watchlist/` | 0007 | ✅ 完整 |
| **虚拟现货钱包** | 三独立子账户(CN/US/CRYPTO)+ daily snapshot(23:59:30 worker)+ 重置/激活 + REST 8 路由 | `models/virtual.py` · `services/virtual_trading/{engine,equity,fees}.py`(520+201+52 行)· `api/v1/virtual.py` · `worker/tasks/equity_snapshot.py` · `/settings/wallet` | 0008 | ✅ 完整(M0 第 3 步) |
| **/portfolio 账户页** | 动态卡 + 多曲线 + 持仓 + 资金费记录 | `apps/web/app/account/page.tsx`(563 行) | — | ✅ |

### 1.3 加密虚拟永续合约(M2-C · 上线)

代码全在 main · ADR 0019(逐仓)+ 0020(资金费)+ 0027(全仓)三份,**0019/0020 ADR 在 feature 分支未合 main**(见 §1.7)。

| 模块 | 做了什么 | 核心文件 | ADR | 成熟度 |
|---|---|---|---|---|
| **逐仓 perp 引擎**(isolated) | 开/平/加/反手 · 杠杆 · 标记价撮合(`crypto_premium_index` 每分钟刷)· 资金费独立扣除现金 · 不联动强平 | `services/virtual_trading/perp_engine.py`(542 行)· `perp_fees.py`(96 行) | 0019 v2 | ✅ M2-C.1 完整 |
| **全仓 perp 引擎**(cross) | 共担保证金池 · 同账户允许逐仓+全仓共存(不同 symbol)· 同 symbol 拒混仓 · 跨用户隔离 | `services/virtual_trading/perp_cross_engine.py`(588 行 · 纯新增不动逐仓核心) | 0027 MC-2 | ✅ M2-C 全期完整 |
| **强平监控** | 逐仓 worker(60s)+ 全仓账户级 worker(独立 60s · `margin_mode='cross'` 过滤)· 单事务全平 · 穿仓地板 | `services/virtual_trading/perp_cross_liquidation.py`(216 行)· `worker/tasks/perp_liquidation.py` + `perp_cross_liquidation.py` | 0027 MC-3 | ✅ MC-3 完整(留 backlog #256 精度二测) |
| **资金费结算** | per-symbol 周期采集(1h/2h/4h/8h)+ 按币周期对齐结算(crontab minute=0)· 只扣现金不联动强平 · 幂等键防漏结 | `services/virtual_trading/perp_funding.py`(146 行)· `worker/tasks/perp_funding.py` · `models/perp.py` + `virtual_perp_funding` 表 | 0020 + M2-C.2.2 | ✅ 完整 |
| **下单分流**(margin_mode dispatcher) | bot/网页下单时根据 margin_mode 分流到 cross/isolated 引擎(纯新增 · 引擎核心零改动) | `services/virtual_trading/perp_dispatcher.py`(184 行) | 0027 MC-4 | ✅ 完整 |
| **margin_mode 数据迁移** | Enum → VARCHAR(16) + 预定义 'isolated' / 'cross' + 可逆迁移 + lower 归一 | 迁移 `d4e5f6a7b8c9_perp_margin_mode_to_string.py` | 0027 MC-1 | ✅ |

### 1.4 Telegram 迷你交易终端(M1-G · ADR 0025 Closed)

| 模块 | 做了什么 | 核心文件 | ADR | 成熟度 |
|---|---|---|---|---|
| **统一 bot + 绑定** | `/start` 一次性绑定 token · webhook secret 校验 · 解绑 · 重绑提示 · QR + deep link | `services/notifications/telegram_bind.py` · `api/v1/telegram.py` · 设置页 Telegram 绑定 UI | 0024(Superseded)+ 0025 G1/G3 | ✅ |
| **bot 行情查询** | `/menu` 主菜单 · `/price <代码>` · 自选 / 持仓查看 · K 线网页深链(DP14) | `services/bot/{query,telegram_ui,session,router,identity,ratelimit}.py`(1763 行 total)· `query_alert_rules` 等 dataclass | 0025 G3 | ✅ |
| **bot 虚拟下单** | 必经二次确认按钮(ordok/ordno) · 现货 + 永续 · 用户身份从已验证 chat.id 解析 · 限流 ≤10/min | `services/bot/order.py`(427 行) | 0025 G4 | ✅ |
| **bot 告警规则** | 查看 / 启停 / 一键应用推荐规则 · ownership-scoped 隔离 · 全量新建留网页 | `services/bot/router.py` `rules:*` callbacks · `api/v1/alert_rules.py` | 0026 G5 | ✅ |
| **bot 安静时段**(N3) | 主菜单 [🌙 安静时段] · 查看 + 启停 + 起止小时步进 (0-23 mod 24) · 时区切换留网页 · 紧急豁免文案 | `services/bot/quiet.py`(134 行)· `telegram_ui.py render_quiet_hours` | 0028 N3 | ✅ 完整(21 pytest · 2 跨用户隔离) |
| **bot 下单默认参数预设** | per-user `bot_order_preset` 表 · 杠杆 / margin_mode / 现货金额 等默认值 · 网页配 | `models/bot_order_preset.py` · `api/v1/bot_preset.py` · 设置页 section | 0026 G5 | ✅ |
| **setMyCommands** | 启动期同步 `/menu`、`/price`、`/start` 命令菜单 | `services/notifications/telegram_bind.py` `_BOT_COMMANDS` | 0026 G5 | ✅ |

### 1.5 告警降噪系统(N1-N4 · ADR 0028 Closed)

| 模块 | 做了什么 | 核心文件 | ADR | 成熟度 |
|---|---|---|---|---|
| **N1 后端边沿触发** | 告警规则引擎(`alert_scan` 状态机:not_triggered → triggered = edge fire / triggered → not_triggered = 复位 / 持续态不动)+ 价格异动 worker 同款改造 + dispatcher quiet 拦截 + 紧急豁免 ClassVar(`TradeFilledEvent.quiet_exempt=True`)+ 阈值轻调 | `worker/tasks/alert_scan.py` · `price_alerts.py` · `services/notifications/{dispatcher,quiet,emit,events}.py` · `services/alerts/{engine,recommended,registry}.py`(427 行) | 0028 N1 | ✅ 完整(26 pytest) |
| **N2 网页设置** | `/settings → 告警安静时段` section · GET/PUT `/notifications/config` 暴露 quiet_hours 4 字段 · zoneinfo 真校验 IANA 时区 · 跨夜文案 · 紧急豁免说明 | `apps/web/components/settings/notifications-config-section.tsx` · `api/v1/notifications.py` · `schemas/notifications.py` | 0028 N2 | ✅(16 pytest · 6 越界 parametrize) |
| **N3 bot 配置** | bot 主菜单 [🌙 安静时段] + 查看+启停+起止小时步进 + 时区留网页 + 紧急豁免文案对齐 N2 | 同 §1.4 bot 安静时段 | 0028 N3 | ✅(21 pytest · 2 跨用户隔离) |
| **N4 真机走查** | bot 截图确认 6 按钮齐全 · 网页 section · quiet 时区 · `alert_rule:state:*` 不卡死 · 推送通路实证 · "数小时无告警"查实是降噪生效正常表现 | (无 commit · 走查报告) | 0028 N4 | ✅ 收口 |
| **告警规则 9 条推荐** | A 股 4 条 + 美股 3 条 + crypto 2 条 · 一键应用机制(bot 和网页都接) | `services/alerts/recommended.py` | 0026 G5(DP-G5-2) | ✅ |

### 1.6 部署运维基建(0029-0031 · 一天连治 6 个坑)

| 项 | 做了什么 | 核心文件 | ADR | 成熟度 |
|---|---|---|---|---|
| **Dockerfile BuildKit cache** | api/worker pip cache mount + Aliyun PyPI mirror 主 + pypi.org extra-index 兜底 | `apps/api/Dockerfile` + `apps/worker/Dockerfile`(syntax 1.7) | 0029 DP1 | ✅ |
| **web Dockerfile BuildKit cache** | pnpm store + .next/cache cache mount | `apps/web/Dockerfile`(syntax 1.7) | 0031 DP3 | ✅(实证 web build 5min → 2-3min rebuild) |
| **update.sh 7/7 银包** | banner 1/7..7/7 · timeout 1500s · BUILDKIT_PROGRESS=plain · 失败诊断(磁盘/缓存/进程)· trap on_err git HEAD 回滚 · 7/7 温和 prune `--filter "until=168h"` | `update.sh` | 0029 DP2 + 0031 hotfix | ✅ |
| **deploy.yml force_rebuild** | `workflow_dispatch.inputs.force_rebuild` 救场总开关 · FORCE_REBUILD env 跳 fast-path | `.github/workflows/deploy.yml` | 0029 DP4 | ✅ |
| **deploy.yml git reset --hard** | SSH 命令 `git reset --hard origin/main` 替代 `git checkout -f main` · 让 update.sh 自身改动立即生效 | `.github/workflows/deploy.yml` | 0029 hotfix-2(2fc1c21) | ✅ |
| **fast-path 误判修复** | deploy.yml 在 reset 前算 OLD_HEAD · reset 后算 NEW_HEAD · 一起 env 传给 update.sh · update.sh fallback to disk 自算 | `.github/workflows/deploy.yml` + `update.sh` | 0031 DP1 | ✅ 实证场景②③④全过 |
| **BuildKit GC daemon.json** | `keepStorage: 20GB` 地板 · `live-restore: true` · 防 cache 清到 0 + 防 docker 重启时容器停转 | 服务器 `/etc/docker/daemon.json` | 0029 N2 | ✅(产品方 SSH 实施) |
| **字体本地化** | `next/font/google` → `next/font/local` · 8 个 latin subset woff2 ~143 KB check in repo · 防 Google Fonts 港/陆 build timeout | `apps/web/app/layout.tsx` + `apps/web/app/fonts/*.woff2` | 0030 | ✅ |
| **OSS 备份脚本** | 部署准备文档 + OSS 备份机制 | `docs/deployment-*.md` + `scripts/` | M1-D | ⚠️ 待确认 OSS 备份脚本是否真在跑(可能还是 manual) |

### 1.7 关键说明 · ADR 0017-0020 不在 main

| ADR | 范围 | 位置 |
|---|---|---|
| **0017** Crypto Pro 数据层 | 9 个数据流 · 5 张 CH 表 · Binance Futures + CoinGecko + alternative.me 三 adapter | `feature/m2-crypto-pro` 分支(commit `8ae7460`) |
| **0018** 全覆盖采集 | crypto 全市场扫描策略 | `feature/m2-crypto-pro` 分支 |
| **0019** v2 加密永续虚拟交易 | 逐仓 perp 引擎设计 | `feature/m2c-perp-virtual-trading` 分支(commit `f8af7c1`) |
| **0020** 资金费 + 真标记价 + 实战策略清单 | M2-C.2 设计 | `feature/m2c2-funding-strategy` 分支(commit `3ef2911`) |

**事实**:**代码已经在 main(M2-A/B/C 全部 completed),ADR 文档没合 main**。
**风险**:产品方读 main 上的 ADR 列表会缺这 4 份关键设计文档。
**建议**:cherry-pick 这 4 份 ADR 文档到 main(纯 docs · 不触发部署),让 main 上的 ADR 链路完整。**优先级 P2 · 不阻塞当前**。

---

## 2. 技术架构

### 2.1 服务编排(`docker/docker-compose.yaml`)

```
                          ┌──────────────┐
                          │   Caddy(server)
                          │  /etc/caddy  │
                          │  TLS · DNS   │
                          └──────┬───────┘
                                 │
              ┌──────────────────┴───────────────────┐
              │                                       │
         api.midastrade.asia                  midastrade.asia
              │                                       │
              ▼                                       ▼
       ┌──────────────┐                       ┌──────────────┐
       │ midas-api    │                       │ midas-web    │
       │ uvicorn FastAPI                      │ Next.js 15   │
       │ :8000        │                       │ :3000        │
       └──────┬───────┘                       └──────────────┘
              │
   ┌──────────┼──────────┬─────────────┐
   │          │          │             │
   ▼          ▼          ▼             ▼
┌─────┐  ┌────────┐  ┌────────┐  ┌────────────┐
│PG 16│  │CH      │  │Redis 7 │  │midas-worker│
│:5432│  │:8123   │  │:6379   │  │celery+beat │
└─────┘  └────────┘  └────────┘  └─────┬──────┘
                                       │
                                       └─ 调用 api 服务的 model/service · 直接连 PG/CH/Redis
```

| 容器 | 镜像 / 入口 | 职责 |
|---|---|---|
| `midas-postgres` | `postgres:16-alpine` | **业务关系数据**(user · watchlist · virtual account/position · perp · alert_rule · notification_config · ai_usage · session · 17 个 alembic migrations) |
| `midas-clickhouse` | `clickhouse/clickhouse-server:latest` | **行情时序数据**(K 线三市场 · crypto 衍生指标 · CN/US spot snapshot · 指数 / 交易日历 / 板块快照)· `docker/clickhouse-init.sql` 初始化 |
| `midas-redis` | `redis:7-alpine` | **会话+缓存+broker**(Celery broker DB1 + result DB2 · bot 会话态 · 限流计数 · 告警边沿状态 `alert_rule:state:*` + cooldown `alert_rule:cool:*` · TG 一次性绑定 token · AI 缓存) |
| `midas-api` | FastAPI + uvicorn(单进程 · lifespan 单例) | REST API · webhook(Telegram)· OpenAPI /docs · 13 个 v1 路由模块 |
| `midas-worker` | celery worker + beat 合一 | 17 个 beat 任务(数据采集 / 增量 / 告警扫描 / 强平 / 资金费 / 快照)· 显式 import 11 个 task 模块(`tasks/{alert_scan, crypto_metrics_ingest, data_ingest, equity_snapshot, incremental, market_home_ingest, notifications, perp_cross_liquidation, perp_funding, perp_liquidation, price_alerts}.py`) |
| `midas-web` | Next.js 15 App Router(production) | 14 个页面 · SSR + SSG 混合 · localFont · NextAuth v5 |

### 2.2 关键数据流 · A:一条告警的完整链路

```
1. 用户在 /settings → 告警规则 section 配规则(或 bot 一键推荐)
   → POST /api/v1/alert-rules → PG `alert_rule` 表
                                   ↓
2. worker 每分钟 beat scan_alert_rules:
   → 遍历所有 enabled rules
   → 按 indicator category 分层(price/volume/technical 每分钟 · market_structure 3min · derivative 5min · chan 30min)
   → 调 services/alerts/engine.evaluate_rule(ctx, rule) 求值(只读 CH 不打实时上游)
                                   ↓
3. N1 边沿触发去重(Redis 状态机):
   - prev_state = redis.get(alert_rule:state:{id})
   - curr_state = "triggered" if ev.triggered and ev.value is not None else "not_triggered"
   - 4 种过渡:
       not_triggered→triggered = edge fire 候选
       triggered→not_triggered = 状态复位写 state · 不推
       持续 triggered = 不动
       持续 not_triggered = 不动
                                   ↓
4. cooldown 护栏(Redis cool key · TTL = rule.cooldown_sec)
   - 仍受 cooldown 压住(防 mark 抖动反复跨阈值)
                                   ↓
5. dispatcher.dispatch(db, user_id, AlertTriggeredEvent):
   - 取 NotificationConfig(per-user)
   - kind_enabled 检查
   - is_quiet_exempt(event) · is_in_quiet_now(config) → 安静时段拦截(N1)
   - tg_chat_id + 全局 tg_bot_token → telegram adapter
                                   ↓
6. Telegram bot send → 用户收到推送 + render 模板 + 必带"仅供参考,不构成投资建议"
   - 派发成功 → redis.set state=triggered + cool key
   - 派发失败 → 不写 state · 下次重试
   - quiet 拦截 → 写 state=triggered 防空转(0028 DP10)
```

### 2.3 关键数据流 · B:一笔虚拟下单(crypto perp)

```
1. 用户路径(任一):
   网页:/crypto-preview → 下单确认模态 (mode 选 cross/isolated)
   bot:  /menu → 🛒下单 → 选 USDT 永续 → 输 symbol → 选方向 → 二次确认按钮 ordok
                                   ↓
2. POST /api/v1/perp/orders (or bot/order.execute)
                                   ↓
3. services/virtual_trading/perp_dispatcher.execute(intent):
   - 根据 intent.margin_mode 分流:
       'isolated' → perp_engine.open_or_close()
       'cross'    → perp_cross_engine.open_or_close()
   - 引擎核心零改动(MC-4 接入临界点设计)
                                   ↓
4. 撮合价格:从 ClickHouse crypto_premium_index 表读 mark_price(每分钟 worker 刷)
                                   ↓
5. 写 PG:
   - virtual_perp_position(新增/修改/平掉)
   - virtual_perp_funding(若涉及 funding 结算)
   - virtual_account(扣 / 释放 margin)
   - 单事务原子提交
                                   ↓
6. 返回 OrderResult → 渲染前端 toast(success 帝王金 / failed 中国红)
   或 bot 渲染 BotReply markdown · 必带 VIRTUAL · 模拟 徽章
                                   ↓
7. ⚠️ 当前 TradeFilledEvent emit 入口未接(见 §4 待办)
   N1 quiet_exempt 机制就绪但 TG 通知没真正发
                                   ↓
8. 独立 worker 每 60s scan_liquidations(逐仓)+ scan_cross_liquidations(全仓 margin_mode='cross' 过滤):
   - 读 mark_price · 计算 maintenance margin · 判强平
   - 若强平 → 全平 + 写 funding · 单事务原子
```

### 2.4 关键数据流 · C:加密 Pro 数据采集

`beat_schedule`(`worker/config/celery_config.py`)17 个定时任务,**四上游错峰**(防 Binance 限流):

```
分钟数错峰:
  ticker_24h_scan        每 10min · 6,16,26,36,46,56
  open_interest_scan     每 5min  · 0,5,10,15,20,...
  premium_index_scan     每 1min  · *(全市场轻量 endpoint)
  long_short_scan        每 15min · 9,24,39,54
  funding_rate_refresh   每 15min · 3,18,33,48
  global_overview        每 30min · 7,37
  fear_greed             每 6h    · :47
  perp_funding_settle    每整点
  perp_liquidation       每分钟(各 margin_mode 独立 worker)
  alert_scan             每分钟
  price_alerts (±5%)     每分钟
  cn_index_scan          A 股盘中 */2(9-15)
  us_index_scan          美股时段 */2(20-23,0-5)
  cn_board_scan          A 股盘中 */3(9-15)
  us_board_scan          美股时段 */5(20-23,0-5)
  cn_calendar_refresh    每日 08:00 CST
  daily_equity_snapshot  每日 23:59
```

---

## 3. 模块依赖关系

```
        ┌──────────────────────────────────────────────────────────────┐
        │                     用户触达层                                │
        │  Web(Next.js)│ Telegram bot │ Email(Resend)│ 飞书(未接) │
        └────┬───────────────┬──────────────┬──────────────┬───────────┘
             │               │              │              │
             ▼               ▼              ▼              ▼
        ┌────────────────────────────────────────────────────────┐
        │                FastAPI REST 路由 + Webhook              │
        │  auth · market · watchlist · virtual · perp ·          │
        │  notifications · telegram · analysis · alert_rules ·   │
        │  bot_preset · crypto · cn · us                         │
        └────┬───────────────────────────────────────────────────┘
             │
             ▼
        ┌────────────────────────────────────────────────────────┐
        │                 业务服务层(services/)                 │
        │                                                         │
        │  ┌─────────────────────────────────────┐               │
        │  │ AI workflow (LangGraph 单 Agent)    │←─缠论 chan.py │
        │  └────────┬────────────────────────────┘               │
        │           │                                             │
        │  ┌────────▼────────────────┐                           │
        │  │ alerts engine + 9 推荐    │←─┬─ Notifications        │
        │  └────────┬────────────────┘   │   dispatcher (TG 统一 │
        │           │                     │   bot · quiet 拦截)  │
        │           │   ┌─────────────────┴─┐                   │
        │  ┌────────▼───▼─────────────────┐  └─→ TG send_event │
        │  │ Virtual Trading(现货 / perp)│                     │
        │  │  · engine / cross_engine     │  ┌─→ bot/router     │
        │  │  · liquidation worker        │  │   (callback)     │
        │  │  · funding worker            │  ├─→ bot/quiet      │
        │  │  · perp_dispatcher           │  ├─→ bot/order      │
        │  └────────┬─────────────────────┘  └─→ bot/query      │
        │           │                                             │
        │  ┌────────▼─────────────────────┐                      │
        │  │ data_sources(纯读上游 · 不打实时)                  │
        │  │  cn_source · us_source · crypto_source ·            │
        │  │  binance_futures_source · coingecko ·               │
        │  │  alternative_me                                     │
        │  └──────────┬───────────────────┘                      │
        └─────────────┼──────────────────────────────────────────┘
                      │
        ┌─────────────▼──────────────────────────────────────────┐
        │              持久化层                                    │
        │  PostgreSQL 16 ─────── business state + per-user        │
        │  ClickHouse  ────────── 行情时序 + 板块快照               │
        │  Redis 7    ─────────── celery broker + 会话 + 限流 +    │
        │                          告警边沿状态 + 一次性 token     │
        └────────────────────────────────────────────────────────┘
```

**关键依赖说明**:
- **告警依赖行情数据**:`alert_scan` worker → `services/alerts/engine.evaluate_rule` → ClickHouse(指标值)+ PG(规则)
- **bot 交易依赖虚拟交易引擎**:`bot/order.py` → `services/virtual_trading/perp_dispatcher` → engine / cross_engine
- **AI 决策依赖缠论 + 数据源**:`ai/workflow` 6 节点 → 调 `analysis/chan.py` + `indicators.py`
- **N2/N3 都依赖 N1**:网页 + bot 配置 quiet_hours → 写 `notification_config` 表 → `dispatcher.is_in_quiet_now` 读
- **强平 worker 严格隔离**:`tasks/perp_liquidation`(isolated)+ `perp_cross_liquidation`(cross)分两个 worker · 各自只扫自己 margin_mode 的活仓(MC-1 隔离过滤)

---

## 4. 明显空白 / 缺口(诚实列)

### 4.1 数据源瓶颈(用户已点出 · 实地确认)

| 项 | 现状 | 卡点 |
|---|---|---|
| **A 股多空人数** | ❌ 没做 | 免费数据源缺(沪深通持仓人数等需付费 / 受限) |
| **A 股换手率榜** | ❌ 没做(task #196 pending) | EM(东方财富)免费通道不稳 / 限制 |
| **A 股量比榜** | ❌ 没做(task #196 pending) | 同上 |
| **美股多空人数** | ❌ 没做 | 加密通过 Binance topLongShortAccountRatio 实现 · 美股没免费等价上游 |

### 4.2 股票交易深度(用户已点出 · 实地确认)

**事实**:**交易能力几乎都在加密 perp**(M2-C 完整)。股票现货侧:
- `virtual_trading/engine.py`(520 行)有现货撮合,但只是简化版(限价单 / 市价单 / 止损单 等没看到独立实现)
- ⚠️ 待确认是否支持限价单/止损止盈,看代码似乎只支持市价单(`engine.py` 详细需查)
- 无做空 · 无杠杆现货(stocks 不该有)· 无两融 · 无 T+1 / T+0 限制模拟

### 4.3 分析层缺口(用户问 · 实地确认)

| 项 | 现状 |
|---|---|
| **回测引擎** | ❌ 完全空白(无 backtest service) |
| **策略 IDE / 编辑器** | ❌ 完全空白 |
| **量化选股器** | ❌ 完全空白(filter / screener UI 没看到) |
| **多因子模型** | ❌ 完全空白 |
| **持仓诊断 / 风险分析** | ❌ 完全空白 |
| **AI Agent 多 Agent 并行** | ⚠️ 半成品 — workflow.py 设计预留 4 Agent 接口,M1 实际只跑单 Agent(技术面),情绪面 / 资金面 / 基本面 Agent 待 M2 |

### 4.4 用户 / 社交层缺口(用户问 · 实地确认)

| 项 | 现状 |
|---|---|
| **公开排行榜**(收益率 / 胜率) | ❌ 完全空白(daily_equity_snapshot 数据已采但无聚合排行视图) |
| **虚拟交易竞赛 / 周赛** | ❌ 完全空白 |
| **跟单 / Copy trading** | ❌ 完全空白 |
| **社区 / 评论 / 心得** | ❌ 完全空白 |
| **关注其他用户** | ❌ 完全空白(WatchlistItem 是关注标的,不是关注用户) |
| **公开持仓秀** | ❌ 完全空白(无 public_profile 类设施) |

### 4.5 商业化层缺口(用户问 · 实地确认)

| 项 | 现状 |
|---|---|
| **会员 / 订阅** | ❌ 完全空白 |
| **付费分层**(免费 / Pro / Premium) | ❌ 完全空白 · 首页 `Pricing` 板块只是占位(`apps/web/app/page.tsx` 第 7 板块 · "M1 限时免费 · 不写价格") |
| **AI 用量结算** | ⚠️ 半成品 — `models/ai_usage.py` + `services/ai/usage.py` 记账已做,但没接付费 / quota 上限 |
| **支付集成** | ❌ 完全空白 |
| **优惠券 / 邀请码** | ❌ 完全空白 |

### 4.6 触达层缺口(用户问 · 实地确认)

| 项 | 现状 |
|---|---|
| **飞书扩展位** | ❌ 0024 ADR 把飞书移除了(superseded by 0025 统一 Telegram bot)· 飞书需要重新设计接入 |
| **Web Push**(浏览器原生推送) | ❌ 完全空白 |
| **邮件推送告警**(不是验证邮件) | ❌ 完全空白(email.py 只用于 verify_email · 没有 alert email) |
| **App / 移动端** | ❌ 完全空白(没有 iOS/Android app)· 当前移动端走 web responsive |
| **微信 / QQ / 企微通知** | ❌ 完全空白 |
| **强平 / 成交 TG 通知** | ⚠️ 半成品 — `TradeFilledEvent.quiet_exempt=True` 豁免机制就绪(N1)、dispatcher 能正确识别,**但 emit 入口未接**(撮合成功后没调 emit) · task #296 |

### 4.7 ADR 治理小坑(meta)

- ADR 0017-0020(M2-A/B/C 数据层 + 永续设计 + 资金费)**在 feature 分支没合 main** · 代码已合 · 文档脱钩
- ⚠️ 影响:产品方读 main 上 ADR 列表会看不到关键设计依据

### 4.8 部署运维剩余尾巴

- task #273:若 N2 keepStorage 后仍冷启动 build · 拆 midas-api-base 镜像 + CI 双 build · 触发条件式 backlog
- ⚠️ 暂无监控告警(uptime / 错误率 / 资源水位)· 全靠产品方手动 / GitHub Actions 报错
- ⚠️ 暂无日志聚合(stdout 留在容器 · docker logs 看)
- ⚠️ 暂无备份验证机制(M1-D OSS 备份脚本是否真在跑 · 是否做过 restore 演练 · 待确认)

---

## 5. 红线与约束(后续开发的硬约束)

源自 `CLAUDE.md` + 各 ADR 反复声明,**永远不可破**:

### 5.1 产品 DNA(永不可破)

1. **永不接真实交易通道** · 全程虚拟资金 · 虚拟撮合引擎 · 虚拟教学
2. **任何 AI / 策略 / 交易输出必带**「仅供参考,不构成投资建议」(`services/notifications/templates.py` + bot `_tail()` + 前端 `DISCLAIMER`)
3. **虚拟交易元素必带帝王金 "VIRTUAL · 模拟" 徽章**(`apps/web/components/ui/VirtualBadge.tsx`)
4. **18+ 强制勾选**(注册必经)

### 5.2 加密侧定位

- **以合约 perp 为主体 · 现货为辅**(M2-A/B/C 重心在 perp)
- USDT 本位永续(过滤非 USDT 交易对 · commit 80b8675 / 2df58ee)
- 不展示 OKX/Bybit/Bitget 等(只 Binance Futures 作为合约数据源)

### 5.3 身份与数据隔离(技术红线)

- **bot 身份只从已验证 chat.id 取**:`resolve_user_id(db, chat_id)` 是唯一入口(0025 R1) · 所有 bot 操作模块(`bot/query.py` / `order.py` / `quiet.py`)函数签名都不接受 `chat_id` / `target_user_id` 入参 · 物理上不可能跨用户
- **下单二次确认必经**(ordok/ordno · DP11) · 一点即成交禁止
- **告警规则 ownership-scoped**:任何 alert_rule 操作按 `(id, user_id)` 双键查询
- **强平 worker margin_mode 严格过滤**(MC-1)· 逐仓 worker 不动 cross 仓 · 反之亦然
- **限流**:bot 命令 ≤20/min · 下单 ≤10/min(per-chat 顶部拦截 · DP11)

### 5.4 数据源 / 引擎使用约束

- **绝不打实时上游**:告警 / 缠论 / AI 等模块只读已采集的 ClickHouse(`select_kline` / `select_*_snapshot`)· 防 akshare 卡死之类的事故(0025 R4)
- **clickhouse-connect 永远传 tz-aware datetime**(0002 翻车 3)
- **SQL "最新 N 条" 必须 `DESC LIMIT N` + Python `reverse`**(0010 / `CLAUDE.md` 项目铁律)
- **retry 只在最贴 transport 那层**(0002 翻车 8)

### 5.5 部署链路约束(2026-05-28 一天 6 坑后立的规)

- BuildKit cache + Aliyun mirror(0029 + 0031)
- daemon.json keepStorage 20GB + live-restore(0029 N2)
- update.sh 1/7..7/7 + trap on_err + git HEAD 回滚(0029 + 0031)
- deploy.yml SSH 命令在 reset 前后算 OLD/NEW_HEAD env(0031)
- web 字体走本地 woff2(0030)
- ⭐ **绝不在 main 直接改运行中代码**:全部走 feature 分支 → 等审 → cherry-pick · 中风险以上必须

---

## 6. 待办池快照(基于 task list 当前状态)

### 6.1 backlog · 用户级功能(数据源 / 体验类)

| Task | 项 | 状态 | 卡点 |
|---|---|---|---|
| #186 | 自选/收藏多标的概览(重做 watchlist 形态) | pending | 设计决策 |
| #196 | 换手率榜 / 量比榜 | pending | **外部依赖**:东财 EM 通道不稳 / 引入新数据源 |
| #256 | M2-C 全仓强平精度二测 | pending | 时间 / 测试矩阵 |
| #295 | render_main_menu 文字老旧 P2 | pending | 下次碰 bot 一起修(低优先) |
| #296 | 强平 / 成交 TG 通知 emit 入口接入 | pending | 业务决策 + 实施 |

### 6.2 backlog · 部署链路(运维基础)

| Task | 项 | 状态 | 触发条件 |
|---|---|---|---|
| #273 | 拆 midas-api-base 镜像 + CI 双 build | pending | server 换机 / cache 失效 / 冷 build ≥30min 复发 |
| (已修)#282 | web Dockerfile cache mount | ✅ 0031 已实施 | — |
| (已修)#293 | fast-path 误判 | ✅ 0031 已实施 | — |

### 6.3 完全空白(本文 §4 列出 · 没单独 task ID · 待规划)

- 回测引擎 / 策略 IDE / 量化选股器
- 排行榜 / 竞赛 / 跟单 / 社区 / 关注用户
- 会员 / 付费分层 / 支付集成
- Web Push / 邮件告警(非验证邮件)/ 飞书 / App
- 监控告警 / 日志聚合 / 备份验证
- AI 4 Agent 并行(M2 升级)
- 缠论 M1 二波(段 / 买卖点 / 中枢扩展)
- 股票限价单 / 止损止盈
- ADR 0017-0020 cherry-pick to main

### 6.4 当前活跃 milestone 状态总览

| Milestone | 状态 | 备注 |
|---|---|---|
| **M0**(陌生人→注册→K 线→虚拟单→TG 推送) | ✅ Closed | `docs/M0-acceptance-report.md` |
| **M1**(缠论 + AI + 首页 + TG bot) | ✅ Closed | 0011 + 0012 + 0025 |
| **M2-A/B/C**(加密 Pro 数据 + REST + 永续 + 全仓 + 资金费) | ✅ Closed | 0017-0020(feat 分支)+ 0027(main)|
| **N1-N4**(告警降噪) | ✅ Closed | 0028 |
| **部署健壮性**(0029 / 0030 / 0031) | ✅ Closed | 一天连治 6 个坑 |
| **M3**(三市场首页 / 榜单 / 板块)| ✅ Closed | 0023(3.1+3.2+3.3) |
| **下一阶段?** | 待产品方规划 | 候选见 §4 |

---

## 7. 给产品方:推荐补骨架优先级(我的看法 · 不算决策)

**先完成再完美**视角,基于现状,我倾向的补骨架顺序:

1. **触达层兜底**:强平 / 成交 TG 通知 emit 入口(#296)— 用户对"钱相关"事件最在意 · 豁免机制就绪只差接线 · 工作量低
2. **排行榜**:用 `daily_equity_snapshot` 数据可做(已有 · 不需新采)· 是社交层最小可用骨架 · 给虚拟教学社区性
3. **股票限价单 / 止损止盈**:补齐三市场交易能力一致性 · 改 `engine.py` · 中等工作量
4. **AI 4 Agent 升级**:M2 计划内 · workflow 接口预留 · 工程改造小但接 4 个 LLM Agent 调用要做 cost 评估
5. **回测 / 选股器**:量化深度 · 工作量大但是差异化重要资产 · 看是否做
6. **会员 / 付费**:商业化骨架 · 但要先看用户量再做(过早商业化反而难)
7. **飞书重接 / Web Push**:看用户使用 channel 偏好后再补

**坑别先踩**:
- 不要把"M2 AI 4 Agent"和"回测"挤在一起 · 都很重 · 选一个先
- 不要急于商业化 · 先用户增长
- 数据源瓶颈(多空人数 / 换手率)别死磕 · 看付费数据源是否能买,免费源会一直坑

---

## 8. 文档约束 + 维护说明

- ⚠️ **本文档基于 main 分支 2026-05-28 23:30 时点状态**(commit `e96fb85`)生成
- 任何代码改动应同步更新本文 §1 / §4 / §6
- 不确定的地方明确标 "⚠️ 待确认" · 不编
- 重要的设计依据走 ADR(`docs/decisions/`)· 本文是索引 + 现状 · 不替代 ADR

**生成者**:Claude Code(系统通读 main 分支代码 + 全部 28 个 ADR 后产出)
**审阅记录**:待产品方阅 → 修正 → 定为基线
