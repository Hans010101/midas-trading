"""周报 md 解析 · frontmatter(YAML)+ 固定标题切分 → 结构化数据 + 缺失标记。

约定格式(运营者严格遵守):
  frontmatter(--- 包裹):week / period_start / period_end / title
  ## 一句话导语   → 标题下 1 段
  ## 核心结论     → 有序列表 1. 2. …
  ## 行业强弱     → ### 走强 / ### 走弱(各无序列表 -)
  ## 下周关注     → 无序列表 -

★容错:关键标题缺失 → 该字段留空 + 记入 missing,不崩。frontmatter 缺关键字段 → WeeklyMdError(422)。
★只解析上面 4 个关键模块填邮件;md 里其余模块(宏观/资金流向/…)照常有但本服务不解析。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import yaml


class WeeklyMdError(Exception):
    """frontmatter 缺失 / 格式错(上传端点 422)。"""


@dataclass
class WeeklyExtract:
    week: int
    period_start: date
    period_end: date
    title: str
    lead: str  # 一句话导语
    conclusions: list[str]  # 核心结论
    strong: list[str]  # 行业走强
    weak: list[str]  # 行业走弱
    next_week: list[str]  # 下周关注
    missing: list[str]  # 缺失的关键模块(标记给前端)


_FM_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_H2_RE = re.compile(r"^##(?!#)\s*(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s*(.+?)\s*$", re.MULTILINE)
_OL_RE = re.compile(r"^\s*\d+[.、]\s+(.+?)\s*$", re.MULTILINE)
_UL_RE = re.compile(r"^\s*[-*]\s+(.+?)\s*$", re.MULTILINE)


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    m = _FM_RE.match(text)
    if not m:
        msg = "缺少 frontmatter(--- 包裹的 YAML 头)"
        raise WeeklyMdError(msg)
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        msg = f"frontmatter YAML 解析失败:{e}"
        raise WeeklyMdError(msg) from e
    if not isinstance(fm, dict):
        msg = "frontmatter 不是合法 YAML 映射"
        raise WeeklyMdError(msg)
    return fm, text[m.end() :]


def _sections(body: str) -> dict[str, str]:
    """切 ## 二级标题 → {heading: content(到下一个 ## 前)}。"""
    parts = _H2_RE.split(body)
    out: dict[str, str] = {}
    for i in range(1, len(parts) - 1, 2):
        out[parts[i].strip()] = parts[i + 1]
    return out


def _ordered_items(text: str) -> list[str]:
    return [m.group(1).strip() for m in _OL_RE.finditer(text)]


def _bullet_items(text: str) -> list[str]:
    return [m.group(1).strip() for m in _UL_RE.finditer(text)]


def _first_paragraph(text: str) -> str:
    """标题下第一段非空文本(遇空行 / 列表 / 子标题截断)。"""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if lines:
                break
            continue
        if line.startswith(("#", "-", "*")) or re.match(r"^\d+[.、]", line):
            if lines:
                break
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _strong_weak(text: str) -> tuple[list[str], list[str]]:
    """行业强弱区 → ### 走强 / ### 走弱 各自的无序列表。"""
    subs = _H3_RE.split(text)
    strong: list[str] = []
    weak: list[str] = []
    for i in range(1, len(subs) - 1, 2):
        heading = subs[i].strip()
        content = subs[i + 1]
        if "走强" in heading:
            strong = _bullet_items(content)
        elif "走弱" in heading:
            weak = _bullet_items(content)
    return strong, weak


def parse_weekly_md(text: str) -> WeeklyExtract:
    """解析周报 md → WeeklyExtract · frontmatter 缺关键字段 → WeeklyMdError;正文缺失 → missing。"""
    fm, body = _split_frontmatter(text)

    week = fm.get("week")
    if not isinstance(week, int):
        msg = "frontmatter 缺 week(整数 ISO 周次)"
        raise WeeklyMdError(msg)
    period_start = _as_date(fm.get("period_start"))
    period_end = _as_date(fm.get("period_end"))
    if period_start is None or period_end is None:
        msg = "frontmatter 缺 period_start / period_end(YYYY-MM-DD)"
        raise WeeklyMdError(msg)
    title = str(fm.get("title") or "全球市场与行业机会周报")

    secs = _sections(body)
    missing: list[str] = []

    lead = _first_paragraph(secs.get("一句话导语", ""))
    if not lead:
        missing.append("一句话导语")
    conclusions = _ordered_items(secs.get("核心结论", ""))
    if not conclusions:
        missing.append("核心结论")
    strong, weak = _strong_weak(secs.get("行业强弱", ""))
    if not strong and not weak:
        missing.append("行业强弱")
    next_week = _bullet_items(secs.get("下周关注", ""))
    if not next_week:
        missing.append("下周关注")

    return WeeklyExtract(
        week=week,
        period_start=period_start,
        period_end=period_end,
        title=title,
        lead=lead,
        conclusions=conclusions,
        strong=strong,
        weak=weak,
        next_week=next_week,
        missing=missing,
    )


def extract_to_json(ex: WeeklyExtract) -> dict[str, Any]:
    """WeeklyExtract → 可存 JSON 列的 dict(date → isoformat)。"""
    return {
        "week": ex.week,
        "period_start": ex.period_start.isoformat(),
        "period_end": ex.period_end.isoformat(),
        "title": ex.title,
        "lead": ex.lead,
        "conclusions": ex.conclusions,
        "strong": ex.strong,
        "weak": ex.weak,
        "next_week": ex.next_week,
        "missing": ex.missing,
    }
