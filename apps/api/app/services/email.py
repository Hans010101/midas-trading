"""邮件 service · 主用 Resend(0006 决策)。

设计:
- Resend HTTP API(无 SDK 依赖,httpx 调)
- 邮件模板:衬线 + 中国红 + 帝王金签名(0006 视觉)
- 不可达时记 stdout(P1 接缝处必有翻车 · Task 6 接告警时 grep)

env:
- RESEND_API_KEY:Resend API key
- EMAIL_FROM:发件人(如 'Midas <noreply@midas.example>')
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailDeliveryError(Exception):
    """邮件投递失败。"""


def _api_key() -> str | None:
    return os.getenv("RESEND_API_KEY") or None


def _from_addr() -> str:
    return os.getenv("EMAIL_FROM", "Midas <onboarding@resend.dev>")


def _verification_email_html(verify_url: str) -> str:
    """中国红 + 帝王金 + 衬线;内联样式(邮件客户端兼容)。"""
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>验证邮箱 · 点金 Midas</title></head>
<body style="margin:0;padding:40px 20px;background:#FCFCF9;font-family:'Noto Sans SC',sans-serif;color:#1A1A1A;">
  <div style="max-width:520px;margin:0 auto;background:#FFFFFF;border:1px solid #F7F6F1;padding:40px;">
    <h1 style="margin:0 0 24px;font-family:'Noto Serif SC',serif;font-size:28px;color:#1A1A1A;">
      点金 <span style="color:#C8102E;">Midas</span>
    </h1>
    <p style="margin:0 0 20px;font-size:16px;line-height:1.6;">
      欢迎注册点金 Midas。请点击下面按钮完成邮箱验证(链接 24 小时有效):
    </p>
    <p style="margin:32px 0;text-align:center;">
      <a href="{verify_url}" style="display:inline-block;padding:12px 32px;background:#C8102E;color:#FFFFFF;text-decoration:none;font-size:15px;font-weight:500;">
        验证邮箱
      </a>
    </p>
    <p style="margin:0 0 12px;font-size:13px;color:#5A5A62;">
      如果按钮无法点击,请复制下面链接到浏览器:
    </p>
    <p style="margin:0 0 24px;font-size:12px;color:#94949C;word-break:break-all;font-family:'JetBrains Mono',monospace;">
      {verify_url}
    </p>
    <hr style="border:none;border-top:1px solid #F7F6F1;margin:32px 0;">
    <p style="margin:0;font-size:12px;color:#94949C;">
      <span style="color:#B8860B;font-weight:500;">点金 Midas · 模拟交易终端</span><br>
      仅虚拟资金,不构成投资建议。<br>
      如非本人操作,忽略本邮件即可。
    </p>
  </div>
</body>
</html>"""


async def send_verification_email(*, to: str, verify_url: str) -> None:
    """发邮箱验证链接。失败抛 EmailDeliveryError(让上层决定如何告警)。"""
    api_key = _api_key()
    if not api_key:
        # Dev 环境 / 没配 Resend:打 stdout,跳过实际投递。
        # 这样开发者复制 URL 即可继续手动测试。
        logger.warning(
            "RESEND_API_KEY 未配置 · 模拟投递 · to=%s · verify_url=%s",
            to, verify_url,
        )
        return

    body = {
        "from": _from_addr(),
        "to": [to],
        "subject": "验证你的邮箱 · 点金 Midas",
        "html": _verification_email_html(verify_url),
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                RESEND_ENDPOINT,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
    except httpx.HTTPError as e:
        logger.exception("Resend 投递失败 to=%s", to)
        msg = f"Resend 投递失败:{e}"
        raise EmailDeliveryError(msg) from e

    logger.info("verification email 已发 to=%s", to)
