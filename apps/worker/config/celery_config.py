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
}
