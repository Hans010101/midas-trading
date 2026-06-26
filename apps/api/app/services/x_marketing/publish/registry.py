"""发布 adapter 注册表(发布层 PR-1)· ADAPTERS = 平台标识 → adapter 实例。

★第一阶段聚焦 X + 币安广场(有官方 API 能自动发):
  - binance_square:API 现成 → 本阶段落地(PR-1 stub / PR-2 真 API)
  - x:等 Hans 的 X API → adapter 待加(加进 ADAPTERS 即接入,不动其他)
★MEXC/Gate/OKX:已调研【无官方发帖 API】→ 不做 · 绝不浏览器模拟(违反 ToS + 封号)·
  接口已留,将来谁开 API 谁加一个 adapter。
"""

from __future__ import annotations

from app.services.x_marketing.publish.base import PublishAdapter
from app.services.x_marketing.publish.binance_square import BinanceSquareAdapter

# 已实现的 adapter(能发的平台)· 加平台 = 加一行。
# ★x 平台待 X API:届时新增 XAdapter 并在此登记一行即接入(不动生产线/其他平台)。
ADAPTERS: dict[str, PublishAdapter] = {
    "binance_square": BinanceSquareAdapter(),
}


def get_adapter(platform: str) -> PublishAdapter | None:
    """取平台 adapter · 未实现/不支持返回 None(端点据此拦)。"""
    return ADAPTERS.get(platform)
