"""应用日志配置。

把 `app.*` 命名空间的 logger 路由到 stdout,**详细格式**:
时间 / 级别 / logger 名 / 消息体。

Task 6(飞书 + TG 推送)以后接告警时,grep stdout 这种格式直接可用。
"""

import logging
import sys


def configure_logging(level: int = logging.INFO) -> None:
    """初始化应用 logger。在 app.main 启动时调用一次。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s · %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ),
    )

    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    # 防止重复加 handler(uvicorn --reload 时模块会被多次 import)
    if not any(isinstance(h, logging.StreamHandler) for h in app_logger.handlers):
        app_logger.addHandler(handler)
    app_logger.propagate = False
