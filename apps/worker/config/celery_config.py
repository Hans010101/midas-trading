"""Celery 配置。

序列化、时区、beat 调度。
"""

import os

from celery.schedules import crontab

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")

task_serializer = "json"
result_serializer = "json"
accept_content = ["json"]
timezone = "Asia/Shanghai"
enable_utc = True

# ── 队列路由(P1-4b · 方案戊)─────────────────────────────────────────────────
# 主 worker 启动【无 -Q】→ 只消费默认队列 "celery"(此处显式化)· ★绝不订阅 backtest。
# vibe 回测任务路由到 backtest 队列 → 由 midas-vibe 容器内的 vibe-worker(-Q backtest)消费。
# 主 worker 没装 vibe;若误给它加 -Q backtest 会 import 崩 → 主 worker 命令永不加 -Q backtest。
# 注:task_routes 只影响【发送时】落哪个队列,不会让主 worker 去消费 backtest(消费由 -Q 决定)。
task_default_queue = "celery"
task_routes = {
    "vibe.run_backtest_job": {"queue": "backtest"},
}

# Beat schedule(时刻是 CN 本地)
# TODO(Task 4.3): 加密增量从 5 分钟轮询升级为 WebSocket 实时推送 + 1 分钟 K 落库
beat_schedule = {
    "update-cn-demo": {
        "task": "tasks.incremental.update_cn_demo",
        # A 股每个交易日 15:30 收盘后跑
        "schedule": crontab(hour="15", minute="30", day_of_week="mon-fri"),
    },
    "update-us-demo": {
        "task": "tasks.incremental.update_us_demo",
        # 美股每个交易日北京时间 05:30 跑(对应美东闭市后约 30 分钟)
        "schedule": crontab(hour="5", minute="30", day_of_week="tue-sat"),
    },
    "update-crypto-demo": {
        "task": "tasks.incremental.update_crypto_demo",
        # 加密 7×24 市场,每 5 分钟一次
        "schedule": crontab(minute="*/5"),
    },
    "flush-visit-stats": {
        "task": "tasks.visit.flush_visit_stats",
        # 访问看板:每 10 分钟把 Redis 实时 PV/UV 落库 daily_visit_stat(今/昨两天)
        "schedule": crontab(minute="*/10"),
        "options": {"expires": 540},
    },
    "update-crypto-15m": {
        "task": "tasks.incremental.update_crypto_15m",
        # 加密主流 5 币 15m 已收盘 K线 · 每 5 分钟(15m 根 15min 收一次 · 5min 轮询冗余覆盖收盘)·
        # drop_unclosed 只写已收盘根 · expires 280 防堆积(下个 5min beat 会补)
        "schedule": crontab(minute="*/5"),
        "options": {"expires": 280},
    },
    "warm-popular-klines": {
        "task": "tasks.incremental.warm_popular_klines",
        # KLINE-001 性能 B:预热热门标的 1d K线(bot K线命中缓存秒出图)· 每 30 分钟刷新保鲜
        # (worker_ready 部署即预热一次 · 此 beat 保持新鲜)· ~11 只 + sleep 错峰 · expires 防堆积
        "schedule": crontab(minute="*/30"),
        "options": {"expires": 1500},
    },
    "update-hk-pool": {
        "task": "tasks.incremental.update_hk_pool",
        # 港股策展池日 K · 每交易日 16:30 HKT 收盘后(timezone Asia/Shanghai · 16:30 CST = 16:30 HKT)
        # ADR 0034a P1-3 · 港股日 K 一天一根,收盘后采一次;循环 ~18 只 + sleep 错峰
        "schedule": crontab(hour="16", minute="30", day_of_week="mon-fri"),
        "options": {"expires": 3000},
    },
    "update-hk-board-lot": {
        "task": "tasks.market.hk_board_lot_scan",
        # 港股每手股数(下单池扩量 A2)· 每日一次(HKEX ListOfSecurities 每日更新 · 别高频)·
        # 16:45 HKT 收盘后(错开 update-hk-pool 16:30)· 自动跟港交所每手框架改革
        "schedule": crontab(hour="16", minute="45", day_of_week="mon-fri"),
        "options": {"expires": 3600},
    },
    "update-hk-sector": {
        "task": "tasks.market.hk_sector_scan",
        # 港股行业分类(板块 A2)· 周级(GICS 行业稳定 · 不需每日)· 周一 17:00 HKT 收盘后 ·
        # yfinance .info 采行情池 ~900(实测 ~35s 不限流)· worker_ready 启动也采一次(部署即填)
        "schedule": crontab(hour="17", minute="0", day_of_week="mon"),
        "options": {"expires": 3600},
    },
    "daily-equity-snapshot": {
        "task": "tasks.equity_snapshot.take_daily_snapshots",
        # 每日 23:59 给所有激活子账户写一条 daily 快照
        # 时区按 Asia/Shanghai · A 股日盘已收 + 美股次日早盘前 · 合理快照点
        "schedule": crontab(hour="23", minute="59"),
    },
    "daily-ai-reflection": {
        "task": "tasks.ai.reflect_decisions",
        # ADR 0036 批次乙 · 每日 04:30 CST 回填 N 天前 AI 历史判断的实测涨跌验证。
        # 夜间低峰 · 只读已采 CH 历史价(不打实时上游)· reflect_pending 幂等(reflected_at
        # 标记)· expires 3600:没及时领走就丢,下一天再跑(积压一天无害,幂等防重)。
        "schedule": crontab(hour="4", minute="30"),
        "options": {"expires": 3600},
    },
    "scan-price-anomalies": {
        "task": "tasks.price_alerts.scan_price_anomalies",
        # 0009 § 4 · 每 1 分钟扫所有自选股 · 涨跌 ±5% 触发 · Redis 5 分钟去重
        # DP13:0025 告警引擎上线后保留此任务并行(不替代)
        "schedule": crontab(minute="*"),
    },
    "scan-alert-rules": {
        "task": "tasks.alerts.scan_alert_rules",
        # 0025 G2b · 每 1 分钟扫所有启用告警规则 · 指标分类频率分层(DP6)·
        # 命中经统一 bot 推送 · Redis 按 rule.cooldown_sec 去重
        "schedule": crontab(minute="*"),
        "options": {"expires": 50},
    },
    "perp-liquidation-scan": {
        "task": "tasks.perp.scan_liquidations",
        # ADR-0019 §4.7 / D4 · 混合方案的 60s 强平监控 · 只在有 perp 活仓时才有实际工作
        # expires 50:本轮没被及时领走就丢(下一分钟还会再扫,不堆任务)
        "schedule": crontab(minute="*"),
        "options": {"expires": 50},
    },
    "conditional-orders-scan": {
        "task": "tasks.conditional.scan_triggers",
        # ADR 0041 刀2 · 条件单触发扫描(照强平 60s 母版)· 无 ACTIVE 单早退零成本 ·
        # 股票休市整组跳过(compute_market_status)· 成交只走唯一入口(红线见内核)
        "schedule": crontab(minute="*"),
        "options": {"expires": 50},
    },
    "perp-cross-liquidation-scan": {
        "task": "tasks.perp.scan_cross_liquidations",
        # ADR-0027 MC-3 · 全仓账户级强平监控 · 独立于逐仓那条(只扫 margin_mode='cross')
        # 60s 一轮 · 只在有 cross 活仓时才有实际工作 · expires 50 同逐仓(不堆任务)
        "schedule": crontab(minute="*"),
        "options": {"expires": 50},
    },
    "perp-funding-settle": {
        "task": "tasks.perp.settle_funding",
        # ADR-0020 Block1 / M2-C.2.2 · 资金费结算 · 每 UTC 整点跑一次,
        # 按每币各自周期对齐(hour % interval == 0)结算 1h/2h/4h/8h 全部周期。
        # crontab minute=0 → 每小时第 0 分;只在有 perp 活仓时才有实际工作。
        # expires 600:整点附近没被领走就丢(下个整点再结;幂等键防漏结/重结)。
        "schedule": crontab(minute="0"),
        "options": {"expires": 600},
    },
    # ── 0023 阶段③ · A股/美股 市场首页数据采集(3.1 · 大盘指数 + 交易日历)──────────
    # 指数只在各自交易时段采(非交易时段没新数据 · 省上游 + 省 CH 写)· 错峰 crypto。
    "market-cn-index-scan": {
        "task": "tasks.market.cn_index_scan",
        # A股日盘(CST 9:30–15:00 · 含午休)· 每 2 分钟刷 Sina 指数快照 · 工作日。
        "schedule": crontab(minute="*/2", hour="9-15", day_of_week="mon-fri"),
        "options": {"expires": 110},
    },
    "market-us-index-scan": {
        "task": "tasks.market.us_index_scan",
        # 美股盘前+盘中+盘后(对国内 = 夜间 · 含 DST 偏移)· 覆盖 CST 20:00–次日 05:00。
        "schedule": crontab(minute="*/2", hour="20-23,0-5"),
        "options": {"expires": 110},
    },
    "market-global-overview-scan": {
        "task": "tasks.market.global_overview_scan",
        # 全球指标跨时区(指数/商品/外汇/债券)· 每 10 分钟刷一次 · 概览容忍 ~15min 延迟(ADR 0035)。
        "schedule": crontab(minute="*/10"),
        "options": {"expires": 590},
    },
    "market-cn-calendar-refresh": {
        "task": "tasks.market.cn_calendar_refresh",
        # 交易日历慢变 · 每日 08:00 CST 开盘前刷一次(全年交易日 · 给状态机判交易日)。
        "schedule": crontab(hour="8", minute="0"),
        "options": {"expires": 3000},
    },
    "market-cn-board-scan": {
        "task": "tasks.market.cn_board_scan",
        # A股榜单(3.2)· 全市场 spot 快照 + 情绪条 + 行业板块 · A股日盘每 3 分钟(工作日)。
        # 全 Sina(东财 _em 不可达)· 比指数(*/2)略重(5500 行),错开放 */3。
        "schedule": crontab(minute="*/3", hour="9-15", day_of_week="mon-fri"),
        "options": {"expires": 170},
    },
    "market-us-board-scan": {
        "task": "tasks.market.us_board_scan",
        # 美股榜单(3.3)· yfinance 批量拉策展池(~128)+ 行业/中概板块 · 美股时段每 5 分钟。
        # 分块错峰(40/块 + sleep)· 单轮 ~30s · 每 5min 留足余量 · 避免 yfinance 限流。
        "schedule": crontab(minute="*/5", hour="20-23,0-5"),
        "options": {"expires": 280},
    },
    "market-hk-board-scan": {
        "task": "tasks.market.hk_board_scan",
        # 港股榜单(首页全市场)· 新浪 stock_hk_spot(~2764)→ 情绪条 + 榜单 · 港股时段每 3 分钟。
        # ★ 源用新浪(生产已验)· 绝不用东财 _em(生产被拒)· 频率对齐 cn_board_scan(防封 IP)。
        # 港股时段 9:30–16:00 HKT(timezone Asia/Shanghai · HKT=CST)· hour 9-16 覆盖含午休。
        "schedule": crontab(minute="*/3", hour="9-16", day_of_week="mon-fri"),
        "options": {"expires": 170},
    },
    # ── M2-A · Crypto Pro 数据采集(0017 ADR)· 常驻定时刷新 ────────────────────
    # 错峰原则:Binance 四个采集(ticker/oi/longshort/funding)分钟数互不重叠,避免
    #   同一刻对 Binance 合约接口集中打请求(IP 权重限流)。oi 落在 5 的倍数;
    #   longshort 落在 2,12,22…;funding 落在 3,18,33,48;ticker 落在 6,16,26… —— 四者无交集。
    # CoinGecko / alternative.me 是不同上游主机且数据慢变,频率更低。
    # expires:本轮没被 worker 及时领走就丢弃(宕机/积压时不堆任务,避免补跑风暴)。
    "crypto-ticker-24h-scan": {
        "task": "tasks.crypto.ticker_24h_scan",
        # 24H 滚动行情(慢变)· 单次 1 个 /fapi/v1/ticker/24hr 请求拉全市场 perp(~300)· 极轻
        # 加密市场列表页 + BTC/ETH 价格卡的数据源 · 每 10 分钟(错峰 6,16,26,36,46,56)
        "schedule": crontab(minute="6-59/10"),
        "options": {"expires": 540},
    },
    "crypto-open-interest-scan": {
        "task": "tasks.crypto.open_interest_scan",
        # OI 是 5min 栅格 · 详情页最需要新鲜的维度 · 每 5 分钟 · 30 标的轻量 GET
        "schedule": crontab(minute="*/5"),
        "options": {"expires": 240},
    },
    "crypto-premium-index-scan": {
        "task": "tasks.crypto.premium_index_scan",
        # M2-C.2.1 · 标记价/指数价/资金费 实时快照 · 撮合/强平价源(perp-liquidation 每分钟读)·
        # 单请求拉全市场(/fapi/v1/premiumIndex 无 symbol · 权重极低)· 每 1 分钟保证 ≤1min 新鲜。
        # 不与四个错峰采集冲突:单个轻量 endpoint,即便偶尔同分钟也只多一个低权重请求。
        # expires 50:本轮没及时领走就丢(下一分钟再拉),不堆任务。
        "schedule": crontab(minute="*"),
        "options": {"expires": 50},
    },
    "crypto-orderbook-depth-scan": {
        "task": "tasks.crypto.orderbook_depth_scan",
        # 沙盘三期第二批 · 刀1 · 盘口深度 top-10 档 · 逐币 ~527 个轻量 GET · 每 5 分钟错峰(2,7,…)
        # (沙盘快照 1h 缓存 · 5min 新鲜度足够,不必 1min)· 7d TTL 稳态 ~190MB(磁盘纪律)。
        # expires 240:本轮没及时领走就丢(下一个 5min 再拉),不堆任务。
        "schedule": crontab(minute="2-59/5"),
        "options": {"expires": 240},
    },
    "crypto-long-short-scan": {
        "task": "tasks.crypto.long_short_scan",
        # ADR-0018 配套③:全量(~527)后单轮 3 上游×全量较重 · 10min → 15min 降频。
        # 错峰 9,24,39,54 —— 避开 OI(*/5 的 :0/:5 栅格)、funding(3,18,33,48)、
        # ticker(6,16,26,36,46,56),防 concurrency=4 下同分钟叠加打爆 Binance 限流。
        # 配套①(limit 96→4)已大幅缩短单轮耗时,15min 间隔 + 840s expires 充裕。
        "schedule": crontab(minute="9-59/15"),
        "options": {"expires": 840},
    },
    "crypto-funding-rate-refresh": {
        "task": "tasks.crypto.funding_rate_refresh",
        # 资金费率 8h 结算(慢变)· 顺带刷标记价 · 每 15 分钟足够(错峰 3,18,33,48)
        "schedule": crontab(minute="3-59/15"),
        "options": {"expires": 840},
    },
    "crypto-global-overview-refresh": {
        "task": "tasks.crypto.global_overview_refresh",
        # CoinGecko /global · 总市值/dominance 慢变 + 免费档限流严 · 每 30 分钟(错峰 7,37)
        "schedule": crontab(minute="7-59/30"),
        "options": {"expires": 1500},
    },
    # ── 布林做T扫描器 M1(★影子模式 · 只打日志不发 TG)──────────────────────────────
    "crypto-boll-scan": {
        "task": "tasks.crypto.boll_scan",
        # 15m bar 收盘后 3 分钟扫(:03/:18/:33/:48 · 留 15m 采集写入余量)· 纯读 CH(klines/tickers)
        # 不打 Binance(无权重冲突)· 状态/冷却进 Redis · 影子模式只 logger.info 本该推送的文案。
        # expires 600:本轮没及时领走就丢(下个 15m 周期再扫,不堆任务)。
        "schedule": crontab(minute="3,18,33,48"),
        "options": {"expires": 600},
    },
    "crypto-boll-hourly-digest": {
        "task": "tasks.crypto.boll_hourly_digest",
        # 做T 体系1(M2-3a · ★影子)· 每小时整点读 A-1 快照 → 分偏多/中性/偏空三组 → 每组前 5(按 %B)
        # → 组装图1 分组全景(SYMBOL 超链接)· 只 logger.info,绝不真发 TG(真发 M2-5)。
        # 夜间安静时段任务内跳过 · expires 600 整点附近没领走就丢(下个整点再来)。
        "schedule": crontab(minute="0"),
        "options": {"expires": 600},
    },
    "crypto-fear-greed-refresh": {
        "task": "tasks.crypto.fear_greed_refresh",
        # alternative.me FGI 每日更新一次 · 每 6 小时一轮即可保证当日值及时合并入 overview
        "schedule": crontab(minute="47", hour="*/6"),
        "options": {"expires": 3000},
    },
    # ── P1-4b-2 研究室回测兜底(默认 celery 队列 · 主 worker 跑 · 不碰 backtest 队列)──────
    "backtest-scan-stale-pending": {
        "task": "tasks.backtest.scan_stale_pending",
        # 超时③:每 5 分钟扫 pending 超 10min 的回测行 → 标 error(vibe-worker 抖动/丢任务兜底)
        "schedule": crontab(minute="*/5"),
        "options": {"expires": 280},
    },
    "backtest-cleanup-run-dirs": {
        "task": "tasks.backtest.cleanup_run_dirs",
        # 清孤儿 run_dir:vibe-worker 异常退出残留、超 6h 的目录 · 每 2 小时清(防撑爆共享卷)
        "schedule": crontab(minute="15", hour="*/2"),
        "options": {"expires": 3000},
    },
    # ── 标准化市场周报(P1 第一刀)· 每周一 9:00 CST 生成草稿 → admin 复核 ──────────────
    # ★AI 生成周报 beat 已停用(内容侧改为运营上传成品 weekly_dispatch)· 任务函数 generate_weekly_report
    #   + generate.py 代码保留不删(未来可能重启用),仅移除此定时条目使其不再触发。
    "cleanup-report-materials": {
        "task": "tasks.report.cleanup_materials",
        # 每天凌晨 4:00 删 7 天前周报素材行(第三刀)· OSS 对象靠桶 lifecycle 自动过期
        "schedule": crontab(hour="4", minute="0"),
        "options": {"expires": 3600},
    },
    "send-weekly-dispatch": {
        "task": "tasks.report.send_weekly_dispatch",
        # ★每周日 21:00 CST(timezone Asia/Shanghai)· 本周有上传则发,无则提醒 admin
        "schedule": crontab(hour="21", minute="0", day_of_week="sun"),
        "options": {"expires": 3600},
    },
}
