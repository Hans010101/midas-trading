"""Celery worker 入口。"""

import logging

from celery import Celery
from celery.signals import worker_ready

app = Celery("midas-worker")
app.config_from_object("config.celery_config")

# 显式 import task 模块,触发 @shared_task 注册到 broker。
# 不用 autodiscover_tasks(那是为 Django-style "<app>/tasks.py" 设计的,
# 我们的布局 `tasks/<feature>.py` 用不上)。
# 在模块加载期(celery 解析 -A celery_app 时 CWD 在 sys.path 上)就 import,
# 缓存进 sys.modules。worker_ready 信号晚于此触发,届时 CWD 可能已不在 sys.path —
# 若把 import 放进 handler 里会 ModuleNotFoundError(实测踩过)。
from ch_schema import ensure_crypto_ch_tables  # noqa: E402
from tasks import (  # noqa: E402, F401
    ai_reflection,
    alert_scan,
    backtest,
    boll_digest,
    boll_scan,
    conditional_orders,
    crypto_metrics_ingest,
    data_ingest,
    econ_calendar,
    equity_snapshot,
    hk_board_lot_ingest,
    hk_sector_ingest,
    incremental,
    intelligent_review,
    intelligent_signals,
    intelligent_trading,
    managed_trading,
    market_home_ingest,
    notifications,
    perp_cross_liquidation,
    perp_funding,
    perp_liquidation,
    price_alerts,
    report,
    system_health,
    visit_flush,
    x_auto,
    x_publish,
    x_tweets,
)

logger = logging.getLogger(__name__)


@worker_ready.connect
def _on_worker_ready(**_kwargs: object) -> None:
    """worker 起来后:① 幂等建 ClickHouse 表(update.sh 无 CH 建表步骤 · M2-C.2.1)·
    ② 入队港股 lot 表采集(部署即填 ~2406,不必等 16:45 beat · 幂等 upsert · A2a)。
    ★ 每步独立 try:① 失败不阻断 ②(否则 ensure_ch 抛异常会吞掉 lot 采集入队)。
    """
    try:
        ensure_crypto_ch_tables()
    except Exception:  # noqa: BLE001
        logger.exception("[worker_ready] ensure_crypto_ch_tables 失败")
    try:
        hk_board_lot_ingest.hk_board_lot_scan.delay()
    except Exception:  # noqa: BLE001
        logger.exception("[worker_ready] 入队 hk_board_lot_scan 失败")
    try:
        # 港股板块 A2:启动采一次行业分类(部署即填 hk_sector,不必等周 beat · ~35s)
        hk_sector_ingest.hk_sector_scan.delay()
    except Exception:  # noqa: BLE001
        logger.exception("[worker_ready] 入队 hk_sector_scan 失败")
    try:
        # KLINE-001 性能 B:部署即预热热门标的 1d K线(bot K线常查 → 命中缓存秒出图 · 免冷拉)
        incremental.warm_popular_klines.delay()
    except Exception:  # noqa: BLE001
        logger.exception("[worker_ready] 入队 warm_popular_klines 失败")
    try:
        # 加密 15m 已收盘 K线部署即预采(bot crypto K线图读 15m · 免冷启动空图 · 5min beat 保鲜)
        incremental.update_crypto_15m.delay()
    except Exception:  # noqa: BLE001
        logger.exception("[worker_ready] 入队 update_crypto_15m 失败")
