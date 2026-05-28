"""通知配置 Pydantic 契约 · 0009 § 6 → 0025 G2a 统一 bot → 0028 N2 quiet_hours 暴露。

GET 返回绑定状态 + 总开关 + 安静时段(不再有飞书 / per-user token)。
PUT 更新总开关 + 安静时段;Telegram 绑定经 bot 内 /start,不在此手填。

0028 N2:把 N1 已落地的 quiet_hours_{enabled,start,end,tz} 4 个字段
对前端暴露(GET 返 + PUT 接受 + 校验)· 不动告警判定 / 边沿触发 / dispatcher。
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class NotificationConfigResponse(BaseModel):
    """GET 响应 · 用户通知配置(未配置 → 默认对象)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # 已绑定的 Telegram chat_id(只读 · 由 /start 写入)· 未绑定为 None
    tg_chat_id: str | None
    trade_alert_enabled: bool
    price_alert_enabled: bool
    # 服务端只读 · 给前端展示是否已绑定 Telegram
    has_telegram: bool
    # 0028 N2 · 安静时段(N1 已落 DB 字段 · 本期暴露给前端)
    # 在该窗口内吞掉普通告警;紧急豁免事件(成交 / 强平 · quiet_exempt=True)照常发。
    quiet_hours_enabled: bool
    # 起止小时 0-23 · start > end 表示跨夜(如 23-7)
    quiet_hours_start: int
    quiet_hours_end: int
    # IANA tz 名(如 "Asia/Shanghai")
    quiet_hours_tz: str


class NotificationConfigUpdate(BaseModel):
    """PUT 入参 · 各字段 None = 不动(局部更新语义)。

    Telegram 绑定不在此手填 —— 经 bot 内 /start 完成(0025 统一 bot)。
    """

    model_config = ConfigDict(extra="forbid")

    trade_alert_enabled: bool | None = None
    price_alert_enabled: bool | None = None
    # 0028 N2 · 安静时段(4 个独立字段 · 各自可选 · 跨夜由 start > end 表达)
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_end: int | None = Field(default=None, ge=0, le=23)
    quiet_hours_tz: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("quiet_hours_tz")
    @classmethod
    def _validate_tz(cls, v: str | None) -> str | None:
        """校验 IANA 时区名(由 stdlib zoneinfo 解析,不通则 422)。"""
        if v is None:
            return None
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError as e:
            msg = f"非法时区 '{v}' · 需 IANA 格式如 Asia/Shanghai / UTC / America/New_York"
            raise ValueError(msg) from e
        return v


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
        quiet_hours_enabled=config.quiet_hours_enabled,
        quiet_hours_start=config.quiet_hours_start,
        quiet_hours_end=config.quiet_hours_end,
        quiet_hours_tz=config.quiet_hours_tz,
    )


def default_config_response() -> NotificationConfigResponse:
    """未配置用户的默认响应(避免 GET 404 让前端难写)。

    quiet_hours 默认值跟 model 的 server_default 对齐(DP4 + DP5):
    23-7 / Asia/Shanghai / 启用。
    """
    return NotificationConfigResponse(
        tg_chat_id=None,
        trade_alert_enabled=True,
        price_alert_enabled=True,
        has_telegram=False,
        quiet_hours_enabled=True,
        quiet_hours_start=23,
        quiet_hours_end=7,
        quiet_hours_tz="Asia/Shanghai",
    )
