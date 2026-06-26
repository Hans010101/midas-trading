"""币安广场 adapter(发布层 PR-1 = stub · PR-2 接真 API)。

★PR-1 = stub:enabled 看 key 配没配,publish 返回【假成功】—— 让整条发布流程(端点→任务→台账→前端)
  端到端可测,但【不调任何真实 API】(零外部副作用)。真实 HTTP 实现 = PR-2(需 Hans 配 Key 真机验)。
★PR-2 真实接口(已调研):
  POST https://www.binance.com/bapi/composite/v1/public/pgc/openApi/content/add
  Header: X-Square-OpenAPI-Key=<key> · Content-Type: application/json · clienttype: binanceSkill
  Body:  {"bodyTextOnly": <文本>}(官方文档纯文本 · 图片支持待 Hans 拿 Key 实测 uploads 端点)
  错误码: 20002 敏感词 / 100条/天 / 20+ 码 → 映射成可读 error 存 dispatch.error
"""

from __future__ import annotations

from app.core.config import settings
from app.services.x_marketing.publish.base import PublishAdapter, PublishResult


class BinanceSquareAdapter(PublishAdapter):
    """币安广场发布适配器。"""

    platform = "binance_square"
    _MAX_LEN = 4000  # 币安广场字数上限(占位 · PR-2 按官方实际校准)

    @property
    def enabled(self) -> bool:
        # ★key 在 .env(与交易 API 隔离)· 空=禁用 · 照 oxapay/feishu 密钥范式
        return bool(settings.binance_square_openapi_key)

    def adapt_text(self, text: str) -> str:
        # 平台特定:超长截断(非重做门禁)· PR-2 按币安实际上限校准
        return text if len(text) <= self._MAX_LEN else text[: self._MAX_LEN]

    async def publish(self, *, text: str, image_path: str | None) -> PublishResult:
        # ★★PR-1 stub:不调真 API · 返回假成功(整条流程可测)。
        #   PR-2 换真实 httpx.AsyncClient POST + Header 鉴权 + 错误码处理 + 解析帖子 id/url。
        _ = (text, image_path)  # PR-2 用:adapt 后文本 + 截图(图片支持待实测)
        return PublishResult(
            success=True,
            platform_post_id="stub-pending-pr2",
            url="https://www.binance.com/square/post/stub-pending-pr2",
            error=None,
        )
