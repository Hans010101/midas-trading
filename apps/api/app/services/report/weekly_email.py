"""周报邮件渲染 · 定稿模板填提取数据 → HTML 正文 + 邮件标题。

结构(《周报邮件模板_定稿》):品牌头部 → 标题区(周次/周期)→ 一句话导语 → 📌核心结论框 →
行业强弱(▲走强红/▼走弱绿双栏)→ 下周关注 → CTA(进入 midastrade.asia)→ 免责 → 退订。

🔴 免责(定稿 · 固定不可省):本报告……不构成任何投资建议。退订链接 {unsubscribe_url} 由发送侧填。
★邮件正文是运营成品的【提取摘要】,完整精排在 PDF 附件;系统不改写内容。
"""

from __future__ import annotations

import html
from datetime import date
from typing import Any

RED = "#C8102E"
GOLD = "#B8860B"
STRONG = "#C8102E"  # 走强(红 · A股涨红)
WEAK = "#0F6E5F"  # 走弱(墨绿 · A股跌绿)
SITE_URL = "https://midastrade.asia/"

DISCLAIMER = (
    "本报告基于公开市场数据、平台行情数据与研究素材整理生成,所有描述均为客观陈述,"
    "所列「机会」与「风险」仅为分析视角,不构成任何投资建议。"
)


def build_subject(ex: dict[str, Any]) -> str:
    ps = date.fromisoformat(ex["period_start"])
    pe = date.fromisoformat(ex["period_end"])
    return (
        f"点金 Midas 全球市场与行业机会周报 | {ps.year} 第 {ex['week']} 周"
        f"({ps.month}/{ps.day}–{pe.month}/{pe.day})"
    )


def _esc(text: str) -> str:
    return html.escape(str(text))


def _ol(items: list[str]) -> str:
    lis = "".join(
        f"<li style='margin:0 0 8px;line-height:1.7'>{_esc(it)}</li>" for it in items
    )
    return f"<ol style='margin:0;padding-left:22px;color:#1a1a1a'>{lis}</ol>"


def _ul(items: list[str], *, color: str) -> str:
    if not items:
        return "<p style='margin:0;color:#999;font-size:13px'>—</p>"
    lis = "".join(
        f"<li style='margin:0 0 6px;line-height:1.6;color:{color}'>{_esc(it)}</li>"
        for it in items
    )
    return f"<ul style='margin:0;padding-left:18px'>{lis}</ul>"


def render_email_html(ex: dict[str, Any], *, unsubscribe_url: str) -> str:
    ps = date.fromisoformat(ex["period_start"])
    pe = date.fromisoformat(ex["period_end"])
    title = _esc(ex.get("title") or "全球市场与行业机会周报")
    period_line = f"{ps.year} 第 {ex['week']} 周 · {ps.isoformat()} ~ {pe.isoformat()}"

    lead = ex.get("lead") or ""
    lead_block = (
        f"<p style='font-size:15px;line-height:1.8;color:#333;margin:0 0 24px'>{_esc(lead)}</p>"
        if lead
        else ""
    )

    conclusions_block = (
        "<div style='background:#FCFCF9;border:1px solid #EDEAE0;border-radius:10px;"
        "padding:16px 18px;margin:0 0 24px'>"
        f"<div style='font-weight:bold;color:{RED};margin:0 0 10px'>📌 核心结论</div>"
        f"{_ol(ex.get('conclusions') or [])}"
        "</div>"
    )

    industry_block = (
        "<div style='margin:0 0 24px'>"
        "<div style='font-weight:bold;color:#1a1a1a;margin:0 0 10px'>行业强弱</div>"
        "<table width='100%' cellpadding='0' cellspacing='0' style='border-collapse:collapse'>"
        "<tr>"
        "<td valign='top' width='50%' style='padding-right:8px'>"
        f"<div style='font-weight:bold;color:{STRONG};margin:0 0 6px'>▲ 走强</div>"
        f"{_ul(ex.get('strong') or [], color=STRONG)}"
        "</td>"
        "<td valign='top' width='50%' style='padding-left:8px'>"
        f"<div style='font-weight:bold;color:{WEAK};margin:0 0 6px'>▼ 走弱</div>"
        f"{_ul(ex.get('weak') or [], color=WEAK)}"
        "</td>"
        "</tr></table>"
        "</div>"
    )

    next_block = (
        "<div style='margin:0 0 24px'>"
        "<div style='font-weight:bold;color:#1a1a1a;margin:0 0 10px'>下周关注</div>"
        f"{_ul(ex.get('next_week') or [], color='#1a1a1a')}"
        "</div>"
    )

    return f"""<div style="font-family:'Noto Serif SC',serif;max-width:640px;margin:0 auto;\
background:#ffffff;padding:0">
  <div style="background:{RED};padding:18px 24px">
    <span style="color:#fff;font-size:18px;font-weight:bold;letter-spacing:1px">点金 Midas</span>
    <span style="color:#F7D9DE;font-size:13px;margin-left:8px">全球市场与行业机会周报</span>
  </div>
  <div style="padding:24px">
    <h1 style="font-size:20px;color:#1a1a1a;margin:0 0 4px">{title}</h1>
    <p style="font-size:12px;color:{GOLD};margin:0 0 20px">{_esc(period_line)}</p>
    {lead_block}
    {conclusions_block}
    {industry_block}
    {next_block}
    <div style="text-align:center;margin:8px 0 24px">
      <a href="{SITE_URL}" style="display:inline-block;background:{RED};color:#fff;\
text-decoration:none;padding:10px 22px;border-radius:8px;font-size:14px">
        进入点金 Midas 看完整行情 →
      </a>
      <p style="font-size:12px;color:#999;margin:10px 0 0">完整精排版见本邮件 PDF 附件</p>
    </div>
    <p style="font-size:11px;line-height:1.7;color:#999;border-top:1px solid #EDEAE0;\
padding-top:14px;margin:0 0 10px">{DISCLAIMER}</p>
    <p style="font-size:11px;color:#bbb;margin:0">
      不想再收到市场周报?<a href="{_esc(unsubscribe_url)}" style="color:#999">退订</a>
    </p>
  </div>
</div>"""
