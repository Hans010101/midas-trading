"""通知配置 Pydantic 契约 · 0009 § 6 → 0025 G2a 统一 bot。

GET 返回绑定状态 + 总开关(不再有飞书 / per-user token)。
PUT 只更新总开关;Telegram 绑定经 bot 内 /start,不在此手填。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class NotificationConfigResponse(BaseModel):
    """GET 响应 · 用户通知配置(未配置 → 默认对象)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # 已绑定的 Telegram chat_id(只读 · 由 /start 写入)· 未绑定为 None
    tg_chat_id: str | None
    trade_alert_enabled: bool
    price_alert_enabled: bool
    # 服务端只读 · 给前端展示是否已绑定 Telegram
    has_telegram: bool


class NotificationConfigUpdate(BaseModel):
    """PUT 入参 · 只更新总开关(None = 不动)。

    Telegram 绑定不在此手填 —— 经 bot 内 /start 完成(0025 统一 bot)。
    """

    model_config = ConfigDict(extra="forbid")

    trade_alert_enabled: bool | None = None
    price_alert_enabled: bool | None = None


class NotificationTestResult(BaseModel):
    """POST /test 响应。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: str
    ok: bool
    error: str | None = None


def serialize_config_response(config) -> NotificationConfigResponse:  # type: ignore[no-untyped-def]
    """统一序列化。"""
    return NotificationConfigResponse(
        tg_chat_id=config.tg_chat_id,
        trade_alert_enabled=config.trade_alert_enabled,
        price_alert_enabled=config.price_alert_enabled,
        has_telegram=bool(config.tg_chat_id),
    )


def default_config_response() -> NotificationConfigResponse:
    """未配置用户的默认响应(避免 GET 404 让前端难写)。"""
    return NotificationConfigResponse(
        tg_chat_id=None,
        trade_alert_enabled=True,
        price_alert_enabled=True,
        has_telegram=False,
    )
