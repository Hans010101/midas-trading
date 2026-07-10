"""🔴 事件日程层红线机器验证(碰决策卡=红线级 · 本文件是红线的可执行证明)。

四道锁:
① 方向词 grep:事件注入的全部输出面(prompt 段 + 卡面 event_risk · zh/en · 全量
   规则+种子语料)零方向词(买/卖/做多/做空/抄底/逃顶/加仓/减仓/入场/离场/上车/清仓/建仓)。
② 免责口径不变:卡面 event_risk 尾带完整「仅供参考,不构成投资建议」(产品 AI 输出红线 ·
   ADR0049 精简仅限 x_short 营销文案,不适用于此)。
③ prompt 红线:_SYSTEM_BASE 含「事件仅风险背景·绝不给方向」新句,且既有禁祈使约束未破。
④ spy/never:事件层(格式化+决策卡组装路径)绝不触发任何下单/交易逻辑——
   运行时 spy(monkeypatch 下单入口 → 断言 never called)+ 静态锁(econ_calendar 包
   源码零 import 交易模块)。

全纯逻辑(无 DB/网络)· 本地秒跑 · CI 硬卡。
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.services.ai.agents.technical import _SYSTEM_BASE, _format_snapshot
from app.services.ai.prompts_en import TECHNICAL_SYSTEM_EN
from app.services.econ_calendar.fetchers import BEA_RELEASES, parse_bea_events, parse_fed_events
from app.services.econ_calendar.format import build_event_risk, format_events_for_prompt
from app.services.econ_calendar.rules import gen_rule_and_seed_events

# 🔴 方向词黑名单(Hans 钦定 + 补齐同义)· 事件输出面一个都不许出现
_DIRECTION_WORDS = (
    "买入", "卖出", "做多", "做空", "抄底", "逃顶", "加仓", "减仓",
    "建仓", "清仓", "入场", "离场", "上车", "止盈", "止损",
    "看多", "看空", "买进", "卖掉",
)
_DIRECTION_WORDS_EN = ("buy", "sell", "long", "short", "enter", "exit")

_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)

# 交叉审补强A(点金-3):fetcher 解析产物的标题也必须进方向词语料——否则改
# parse_fed_events 标题常量 / BEA_RELEASES 加脏标题时机器锁不响,「全语料」承诺不满。
_FED_FIXTURE = {"events": [
    {"type": "FOMC", "title": " FOMC Meeting", "month": "2026-09", "days": "15-16",
     "time": "2:00 p.m."},
]}
# ★从注册表动态生成:今后往 BEA_RELEASES 加条目自动进语料,零人工同步
_BEA_FIXTURE = {
    name: {"release_dates": ["2026-08-27T08:30:00-04:00"]} for name in BEA_RELEASES
}


def _fake_events() -> list:
    """规则+种子+两解析器产物全语料 → 伪 EconEvent(每个标题都过一遍输出面)。"""
    corpus = [
        *gen_rule_and_seed_events(_NOW),
        *parse_fed_events(_FED_FIXTURE),
        *parse_bea_events(_BEA_FIXTURE),
    ]
    assert len(corpus) > len(gen_rule_and_seed_events(_NOW))  # fixture 真解析出了事件
    return [
        SimpleNamespace(
            title=e["title"], scheduled_at=e["scheduled_at"],
            time_confirmed=e["time_confirmed"],
        )
        for e in corpus
    ]


# ── ① 方向词 grep(全语料 · 两输出面 · 两语言)──────────────────────────────


def test_no_direction_words_in_prompt_section():
    events = _fake_events()
    zh = format_events_for_prompt(events, "zh")
    for w in _DIRECTION_WORDS:
        assert w not in zh, f"prompt 事件段出现方向词:{w}"
    en = format_events_for_prompt(events, "en").lower()
    for w in _DIRECTION_WORDS_EN:
        assert f" {w} " not in en, f"en 事件段方向词:{w}"
        assert not en.startswith(f"{w} "), f"en 事件段以方向词开头:{w}"


def test_no_direction_words_in_event_risk():
    events = _fake_events()
    # 滑窗打散:任意 3 条组合都干净(卡面最多显 3 条)· 交叉审补强B:en 面同锁
    for i in range(0, len(events), 3):
        zh = build_event_risk(events[i : i + 3], "zh") or ""
        for w in _DIRECTION_WORDS:
            assert w not in zh, f"event_risk 出现方向词:{w}"
        en = (build_event_risk(events[i : i + 3], "en") or "").lower()
        for w in _DIRECTION_WORDS_EN:
            assert f" {w} " not in en, f"en event_risk 方向词:{w}"
            assert not en.startswith(f"{w} "), f"en event_risk 以方向词开头:{w}"


def test_event_titles_whitelist_clean():
    """标题白名单本身零方向词(纯模板拼接的源头保证)。"""
    for e in gen_rule_and_seed_events(_NOW):
        for w in _DIRECTION_WORDS:
            assert w not in e["title"], f"事件标题含方向词:{e['title']}"


# ── ② 免责口径不变 ─────────────────────────────────────────────────────


def test_event_risk_carries_full_disclaimer():
    events = _fake_events()[:3]
    zh = build_event_risk(events, "zh")
    assert zh is not None
    assert "仅供参考,不构成投资建议" in zh  # ★完整免责(非 x_short 精简版)
    assert build_event_risk([], "zh") is None  # 无事件 = None(不渲染)
    # 交叉审补强B:en 面免责同锁
    en = build_event_risk(events, "en")
    assert en is not None
    assert "not investment advice" in en
    assert build_event_risk([], "en") is None


# ── ③ prompt 红线句 + 既有约束未破 ────────────────────────────────────────


def test_system_prompts_carry_event_redline():
    assert "绝不能据此给出任何方向判断或操作暗示" in _SYSTEM_BASE   # zh 新红线句
    # en:TECHNICAL_SYSTEM_EN 是 dict[Market, str],红线句必须进【每个】市场变体
    for market, prompt in TECHNICAL_SYSTEM_EN.items():
        assert "NEVER derive any directional view" in prompt, f"en 红线句缺席:{market}"
    # 既有禁祈使约束未被本次改动挤掉(test_prompt_invariants 也钉·此处双保险)
    assert "绝对不能出现" in _SYSTEM_BASE
    assert "建议买入" in _SYSTEM_BASE


def test_snapshot_passthrough_only_when_present():
    """事件段只在非空时进 prompt;空串 = prompt 逐字节零变化(旧行为不破)。"""
    base = {
        "last_close": 100.0, "last_ts": _NOW, "ma": {5: 1.0, 20: 1.0, 60: 1.0},
        "macd": {"dif": 0.0, "dea": 0.0, "macd": 0.0}, "rsi": {14: 50.0},
        "boll": {"upper": 1.0, "mid": 1.0, "lower": 1.0}, "trend_5d": "sideways",
        "chan_bi_count": 0, "chan_last_bi_direction": None, "chan_zhongshu_count": 0,
        "chan_recent_buy_sell_points": [],
    }
    from app.schemas.ai_decision import TechnicalSnapshot

    empty = _format_snapshot(TechnicalSnapshot(**base))
    assert "重大事件" not in empty
    section = format_events_for_prompt(_fake_events()[:2], "zh")
    with_events = _format_snapshot(TechnicalSnapshot(**base, econ_events_context=section))
    assert with_events.startswith(empty)          # 旧内容逐字节保留
    assert "未来7天重大事件" in with_events
    assert "绝不能据此给出方向判断或操作暗示" in with_events  # 段内红线尾句


# ── ④ spy/never:事件不触发任何下单/交易逻辑 ────────────────────────────────


def test_spy_event_layer_never_touches_trading(monkeypatch) -> None:  # noqa: ANN001
    """运行时 spy:monkeypatch 三个下单入口 → 跑事件全输出面 → 断言 never called。"""
    calls: list[str] = []

    def _spy(name):  # noqa: ANN001, ANN202
        def _boom(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
            calls.append(name)
            raise AssertionError(f"事件层触发了交易入口:{name}")
        return _boom

    import app.services.virtual_trading.conditional_trigger as trigger_mod  # noqa: PLC0415
    import app.services.virtual_trading.engine as engine_mod  # noqa: PLC0415

    for mod, fn in (
        (engine_mod, "place_market_order"),              # 撮合唯一入口
        (trigger_mod, "process_active_conditionals"),    # 条件单触发器
    ):
        if hasattr(mod, fn):  # 防重构改名后 spy 落空(名字漂移时此测显式失败)
            monkeypatch.setattr(mod, fn, _spy(fn))
        else:
            raise AssertionError(f"spy 目标不存在:{mod.__name__}.{fn}(下单入口改名?更新本测)")

    events = _fake_events()
    format_events_for_prompt(events, "zh")
    format_events_for_prompt(events, "en")
    build_event_risk(events, "zh")
    build_event_risk(events, "en")
    assert calls == []  # ★never:全输出面跑完,零下单调用


def test_static_econ_package_never_imports_trading():
    """静态锁:econ_calendar 包源码零交易模块 import(结构性不可能触发下单)。"""
    pkg = Path("app/services/econ_calendar")
    banned = ("virtual_trading", "conditional_orders", "place_market_order",
              "create_conditional_order", "route_open", "engine")
    for f in pkg.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        for token in banned:
            assert token not in src, f"{f.name} 引用了交易相关符号:{token}"


def test_workflow_state_key_matches_snapshot_field():
    """契约钉死:state 键名与 snapshot 字段名一致(econ_events_context)· 防重构漂移静默断链。"""
    import inspect

    from app.schemas.ai_decision import TechnicalSnapshot
    from app.services.ai import workflow as wf

    assert "econ_events_context" in TechnicalSnapshot.model_fields
    src = inspect.getsource(wf._node_data_prepare)
    assert 'state.get("econ_events_context"' in src
