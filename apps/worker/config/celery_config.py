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
    "daily-equity-snapshot": {
        "task": "tasks.equity_snapshot.take_daily_snapshots",
        # 每日 23:59 给所有激活子账户写一条 daily 快照
        # 时区按 Asia/Shanghai · A 股日盘已收 + 美股次日早盘前 · 合理快照点
        "schedule": crontab(hour="23", minute="59"),
    },
    "scan-price-anomalies": {
        "task": "tasks.price_alerts.scan_price_anomalies",
        # 0009 § 4 · 每 1 分钟扫所有自选股 · 涨跌 ±5% 触发 · Redis 5 分钟去重
        "schedule": crontab(minute="*"),
    },
    "perp-liquidation-scan": {
        "task": "tasks.perp.scan_liquidations",
        # ADR-0019 §4.7 / D4 · 混合方案的 60s 强平监控 · 只在有 perp 活仓时才有实际工作
        # expires 50:本轮没被及时领走就丢(下一分钟还会再扫,不堆任务)
        "schedule": crontab(minute="*"),
        "options": {"expires": 50},
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
    "crypto-fear-greed-refresh": {
        "task": "tasks.crypto.fear_greed_refresh",
        # alternative.me FGI 每日更新一次 · 每 6 小时一轮即可保证当日值及时合并入 overview
        "schedule": crontab(minute="47", hour="*/6"),
        "options": {"expires": 3000},
    },
}
