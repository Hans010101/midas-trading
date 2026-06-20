"""市场周报 · PDF 生成(P3 第二刀)。

reportlab platypus · 中文用自带 CID 字体 STSong-Light(★免 bundle 字体 · 无需 Docker 系统字体)。
基础模板:标题 + 正文段落 + 免责。★版式精排(图表/表格/品牌)留【内容设计立项】,本刀先出可用 PDF。

🔴 报告内容已在生成时过 validate_advisory + 免责兜底(第一刀);PDF 渲染该内容 → 自带免责。
"""

from __future__ import annotations

import io

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_FONT = "STSong-Light"  # reportlab 自带简体中文 CID 字体(CMap 随包 · 不外挂 .ttf)
_font_registered = False


def _ensure_font() -> None:
    global _font_registered  # noqa: PLW0603
    if not _font_registered:
        pdfmetrics.registerFont(UnicodeCIDFont(_FONT))
        _font_registered = True


def _esc(text: str) -> str:
    """platypus Paragraph 用简化 HTML 标记 → 转义 & < > 防解析错乱。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_report_pdf(title: str, content: str) -> bytes:
    """报告 title + content → PDF bytes。中文走 STSong-Light · 段落自动换行(platypus)。"""
    _ensure_font()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=title,
    )
    title_style = ParagraphStyle(
        "ReportTitle", fontName=_FONT, fontSize=18, leading=24,
        spaceAfter=14, textColor=HexColor("#C8102E"),
    )
    body_style = ParagraphStyle(
        "ReportBody", fontName=_FONT, fontSize=11, leading=18, spaceAfter=8,
    )
    foot_style = ParagraphStyle(
        "ReportFoot", fontName=_FONT, fontSize=9, leading=14,
        textColor=HexColor("#888888"), spaceBefore=16,
    )

    story: list[object] = [Paragraph(_esc(title), title_style), Spacer(1, 6)]
    for para in content.split("\n"):
        text = para.strip()
        if text:
            story.append(Paragraph(_esc(text), body_style))
        else:
            story.append(Spacer(1, 6))
    # ★免责兜底:content 通常已含(第一刀);若漏则补一行(双保险红线)
    if "不构成投资建议" not in content:
        story.append(Paragraph("仅供参考,不构成投资建议。", foot_style))

    doc.build(story)
    return buf.getvalue()
