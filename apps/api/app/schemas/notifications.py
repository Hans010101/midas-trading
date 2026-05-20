"""通知配置 Pydantic 契约 · 0009 § 6。

GET response 里 tg_bot_token 做截断展示(前 10 + 后 4 字符)· 全文不出后端。
PUT 接受 partial update · 不传字段保持原值;空字符串("")显式清空。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


def _truncate_token(token: str | None) -> str | None:
    """token 安全截断 · 防前端拿到完整 token · 0009 § 6。"""
    if token is None or len(token) <= 14:
        return token
    return f"{token[:10]}...{token[-4:]}"


class NotificationConfigResponse(BaseModel):
    """GET 响应 · 用户配置(未配置过 → 默认对象 · 全 None / 默认 true)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    feishu_webhook_url: str | None
    # token 截断展示 · 真实 token 仅存 DB
    tg_bot_token: str | None
    tg_chat_id: str | None
    trade_alert_enabled: bool
    price_alert_enabled: bool
    # 服务端只读 · 给前端展示是否已激活
    has_feishu: bool
    has_telegram: bool


class NotificationConfigUpdate(BaseModel):
    """PUT 入参 · 部分更新 · 空字符串 = 清空 · None = 不动。"""

    model_config = ConfigDict(extra="forbid")

    feishu_webhook_url: str | None = Field(default=None, max_length=512)
    tg_bot_token: str | None = Field(default=None, max_length=128)
    tg_chat_id: str | None = Field(default=None, max_length=64)
    trade_alert_enabled: bool | None = None
    price_alert_enabled: bool | None = None


class NotificationTestResult(BaseModel):
    """POST /test 响应。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    channel: str
    ok: bool
    error: str | None = None


def serialize_config_response(config) -> NotificationConfigResponse:  # type: ignore[no-untyped-def]
    """统一序列化 · 截断 token。"""
    return NotificationConfigResponse(
        feishu_webhook_url=config.feishu_webhook_url,
        tg_bot_token=_truncate_token(config.tg_bot_token),
        tg_chat_id=config.tg_chat_id,
        trade_alert_enabled=config.trade_alert_enabled,
        price_alert_enabled=config.price_alert_enabled,
        has_feishu=bool(config.feishu_webhook_url),
        has_telegram=bool(config.tg_bot_token and config.tg_chat_id),
    )


def default_config_response() -> NotificationConfigResponse:
    """未配置用户的默认响应(避免 GET 404 让前端难写)。"""
    return NotificationConfigResponse(
        feishu_webhook_url=None,
        tg_bot_token=None,
        tg_chat_id=None,
        trade_alert_enabled=True,
        price_alert_enabled=True,
        has_feishu=False,
        has_telegram=False,
    )
