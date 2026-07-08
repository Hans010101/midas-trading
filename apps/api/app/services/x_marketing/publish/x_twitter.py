"""X(Twitter)发布 adapter · tweepy OAuth 1.0a user-context 真发。

★接入 = registry 加一行 "x": XTwitterAdapter()(不动币安广场/生产线)。
★凭证:settings.x_consumer_key/secret + x_access_token/secret(4 密钥从 /opt/midas/.env 读),
  任一为空 → enabled=False → 端点拦(不发)。密钥【只进 tweepy client · 绝不进日志/error/返回】。
★字数:X 免费层 280 加权(CJK 算 2 ≈ 140 中文字)。超限【拒发不截断】——截断会砍掉尾部
  免责『仅供参考,不构成投资建议』(红线),故返 failure 让 admin 精简/开 Premium,绝不发丢免责的推。
★图片:本阶段纯文本(image_path 忽略)· X 媒体需 v1.1 media/upload,待后续。
★publish 永不 raise(401/429/403/网络/意外都返 PublishResult(success=False))→ worker 不崩。
★频率/门禁/幂等在上游(端点 compliance_passed + check_rate + upsert_pending),此处只管真发。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import tweepy

from app.core.config import settings
from app.services.x_marketing.publish.base import PublishAdapter, PublishResult

logger = logging.getLogger(__name__)

# ★加权字数上限走 settings.x_tweet_max_weighted(免费 280 / Premium 设 25000)· 见 config.py。
#   仅发布前友好预检;超限【拒发不截断】(保尾部免责红线)· X 端做权威校验。


def _x_weighted_len(text: str) -> int:
    """近似 Twitter/X 加权字数:多数字符 1 · CJK(中日韩全角)算 2。

    只作【发布前友好预检】· X 服务端做权威校验(超限它也会 400)。
    """
    total = 0
    for ch in text:
        o = ord(ch)
        cjk = (
            0x1100 <= o <= 0x11FF        # 韩文字母
            or 0x2E80 <= o <= 0xA4CF     # CJK 部首 / 假名 / 表意 / 扩展A
            or 0xAC00 <= o <= 0xD7A3     # 韩文音节
            or 0xF900 <= o <= 0xFAFF     # CJK 兼容表意
            or 0xFE30 <= o <= 0xFE4F     # CJK 兼容形式
            or 0xFF00 <= o <= 0xFF60     # 全角 ASCII
            or 0xFFE0 <= o <= 0xFFE6     # 全角符号
            or 0x20000 <= o <= 0x3FFFD   # CJK 扩展B+
        )
        total += 2 if cjk else 1
    return total


class XTwitterAdapter(PublishAdapter):
    """X(Twitter)发布适配器 · OAuth 1.0a · tweepy。"""

    platform = "x"

    @property
    def enabled(self) -> bool:
        # ★4 密钥全配才启用(照 binance_square 密钥范式:空 = 禁用)
        return bool(
            settings.x_consumer_key
            and settings.x_consumer_secret
            and settings.x_access_token
            and settings.x_access_token_secret
        )

    def adapt_text(self, text: str) -> str:
        # ★不截断(截断会丢尾部免责红线)· 超限由 publish 拒发。此处原样返回。
        return text

    def _post_sync(self, text: str) -> Any:
        """同步 tweepy 发推(在 asyncio.to_thread 里跑)· OAuth 1.0a user-context。"""
        client = tweepy.Client(
            consumer_key=settings.x_consumer_key,
            consumer_secret=settings.x_consumer_secret,
            access_token=settings.x_access_token,
            access_token_secret=settings.x_access_token_secret,
        )
        # user_auth=True → 用 OAuth 1.0a 用户上下文发推(不传默认 bearer 只读会 403)
        return client.create_tweet(text=text, user_auth=True)

    async def publish(self, *, text: str, image_path: str | None) -> PublishResult:
        _ = image_path  # 本阶段纯文本(X 媒体待 v1.1 media/upload)
        weighted = _x_weighted_len(text)
        limit = settings.x_tweet_max_weighted
        if weighted > limit:
            return PublishResult(
                success=False,
                error=(
                    f"超 X 加权字数上限 {limit}(当前 {weighted})· 未截断以保留免责红线 · "
                    "请精简正文;若已开 X Premium 可把 X_TWEET_MAX_WEIGHTED 设为 25000"
                ),
            )
        try:
            resp = await asyncio.to_thread(self._post_sync, text)
        except tweepy.TooManyRequests:
            logger.warning("[x-twitter] 限流 429")
            return PublishResult(success=False, error="X 限流(429)· 稍后再试")
        except tweepy.Unauthorized:
            logger.warning("[x-twitter] 认证失败 401")
            return PublishResult(
                success=False, error="X 认证失败(401)· 检查 4 密钥 / 权限须 Read and write",
            )
        except tweepy.Forbidden as exc:
            logger.warning("[x-twitter] 403 拒绝")
            return PublishResult(
                success=False,
                error=f"X 拒绝(403 · 可能重复内容 / 权限不足):{_short_err(exc)}",
            )
        except tweepy.HTTPException as exc:
            logger.warning("[x-twitter] HTTP 错误")
            return PublishResult(success=False, error=f"X API 错误:{_short_err(exc)}")
        except Exception as exc:  # noqa: BLE001 · 兜底:任何意外不让 worker 崩
            logger.warning("[x-twitter] 意外错 · %s", type(exc).__name__)
            return PublishResult(success=False, error=f"意外错:{type(exc).__name__}")

        data = getattr(resp, "data", None)
        tid = data.get("id") if isinstance(data, dict) else None
        if not tid:
            logger.warning("[x-twitter] 发布响应无 tweet id · data=%s", data)
            return PublishResult(success=False, error="X 发布返回无 tweet id")
        logger.info("[x-twitter] 发布成功 · id=%s", tid)
        return PublishResult(
            success=True,
            platform_post_id=str(tid),
            url=f"https://x.com/i/web/status/{tid}",
        )


def _short_err(exc: Exception) -> str:
    """取异常简短信息(★绝不含密钥)· tweepy 异常 message 是 X 返回的错误文案,不含凭证。"""
    msg = str(exc)
    return msg[:160] if msg else type(exc).__name__
