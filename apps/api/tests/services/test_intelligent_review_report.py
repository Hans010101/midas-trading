"""智能交易复盘 · 纯函数测(★本地真跑 · build_review_prompt + is_last_day_of_month)。

PR-8:验 ★Hans 复盘 Prompt 组装(含原则 + 插入具体数据数字 + 周/月报上期对比)+ 月末判定边界。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.services.virtual_trading.intelligent import review_report as rr


def _data() -> dict:
    return {
        "period": "day",
        "trade_count": 5,
        "overall": {"win_rate": 0.288, "profit_factor": 0.52, "total_pnl": -1234.5},
        "by_side": {"long": {"win_rate": 0.4}, "short": {"win_rate": 0.1}},
        "by_reason_pct": {"stop_loss": 0.4, "take_profit": 0.1, "signal_reversal": 0.5},
        "signal_quality": {"by_indicator": {}, "by_score_band": {}},
    }


# ── build_review_prompt(★Hans 原文 + 插数据)──────────────────────────
def test_prompt_includes_hans_principles() -> None:
    prompt = rr.build_review_prompt(_data(), "day")
    # ★Hans 设计的核心原则/机制必须在(不被改成套话)
    assert "复盘分析师" in prompt
    assert "严禁空洞套话" in prompt
    assert "理论盈亏比2:1" in prompt
    assert "针对当前可调参数" in prompt


def test_prompt_injects_concrete_numbers() -> None:
    prompt = rr.build_review_prompt(_data(), "day")
    # ★具体数据数字插入(原则2:基于具体数据说话)
    assert "0.288" in prompt
    assert "0.52" in prompt
    assert "{{REVIEW_DATA}}" not in prompt  # 占位被替换


def test_prompt_day_no_prev_compare() -> None:
    # 日报不加上期对比(仅周/月报)
    prompt = rr.build_review_prompt(_data(), "day", prev_content="上期内容")
    assert "对比本期 vs 上期" not in prompt


def test_prompt_week_with_prev_compare() -> None:
    prompt = rr.build_review_prompt(_data(), "week", prev_content="上周胜率 30%")
    assert "对比本期 vs 上期" in prompt
    assert "上周胜率 30%" in prompt


def test_prompt_month_without_prev() -> None:
    # 月报但无上期 → 不加对比段(首期)
    prompt = rr.build_review_prompt(_data(), "month", prev_content=None)
    assert "对比本期 vs 上期" not in prompt


# ── _strip_markdown(★复盘标准 MD → TG 纯文本·去 **/### 避 TG 400)──────────
def test_strip_markdown_bold() -> None:
    assert rr._strip_markdown("**诊断结论：** 做空更准") == "诊断结论： 做空更准"


def test_strip_markdown_heading() -> None:
    assert rr._strip_markdown("### 整体表现诊断") == "整体表现诊断"
    assert rr._strip_markdown("#### 1. 子标题") == "1. 子标题"


def test_strip_markdown_list_and_rule() -> None:
    assert rr._strip_markdown("- 胜率 30%") == "· 胜率 30%"
    assert rr._strip_markdown("---") == "──────────"


def test_strip_markdown_no_residual_markers() -> None:
    # ★综合:去掉触发 TG 400 的 **/### 符号
    out = rr._strip_markdown("### 标题\n**粗体**正文\n- 列表项")
    assert "**" not in out
    assert "###" not in out
    assert "粗体正文" in out


# ── is_last_day_of_month(各月边界 28/29/30/31)──────────────────────────
def test_is_last_day_31() -> None:
    assert rr.is_last_day_of_month(datetime(2026, 1, 31, 21, 0, tzinfo=UTC)) is True
    assert rr.is_last_day_of_month(datetime(2026, 1, 30, 21, 0, tzinfo=UTC)) is False


def test_is_last_day_feb_non_leap() -> None:
    assert rr.is_last_day_of_month(datetime(2026, 2, 28, 21, 0, tzinfo=UTC)) is True  # 2026 非闰


def test_is_last_day_feb_leap() -> None:
    assert rr.is_last_day_of_month(datetime(2024, 2, 29, 21, 0, tzinfo=UTC)) is True  # 2024 闰
    assert rr.is_last_day_of_month(datetime(2024, 2, 28, 21, 0, tzinfo=UTC)) is False  # 闰年 28 非末


def test_is_last_day_30() -> None:
    assert rr.is_last_day_of_month(datetime(2026, 4, 30, 21, 0, tzinfo=UTC)) is True
    assert rr.is_last_day_of_month(datetime(2026, 4, 29, 21, 0, tzinfo=UTC)) is False


def test_is_last_day_year_end() -> None:
    assert rr.is_last_day_of_month(datetime(2026, 12, 31, 21, 0, tzinfo=UTC)) is True  # 跨年
