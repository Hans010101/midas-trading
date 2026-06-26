"""发布 adapter 抽象接口(发布层 PR-1)· 加新平台 = 加一个 adapter 实现,不动生产线/其他平台。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PublishResult:
    """adapter 发布结果(统一返回 · 各平台 adapter 自行填)。"""

    success: bool
    platform_post_id: str | None = None
    url: str | None = None
    error: str | None = None


class PublishAdapter(ABC):
    """发布适配器抽象 · 统一接口 publish(text, image) → PublishResult。"""

    platform: str  # 平台标识 · 与 platform_dispatch.platform 一致(e.g. "binance_square")

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """是否就绪(API Key 配了才 True · 空=禁用)· 端点据此拦未配置平台。"""

    def adapt_text(self, text: str) -> str:
        """★平台特定格式适配位(限字数 / 禁外链等)· 非重做门禁(门禁阶段2 已平台无关地过)。

        默认原样返回;各平台 adapter 按需覆写(如截断到平台上限)。
        """
        return text

    @abstractmethod
    async def publish(self, *, text: str, image_path: str | None) -> PublishResult:
        """发布到该平台 · 调各自 API · 返回统一 PublishResult。"""
