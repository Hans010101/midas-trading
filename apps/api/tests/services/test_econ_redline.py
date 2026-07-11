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
from app.services.econ_calendar.fetchers import (
    BEA_RELEASES,
    BOJ_STATS,
    DSBB_CATEGORIES,
    DSBB_COUNTRIES,
    JP_ESTAT_SPECS,
    KOSTAT_INDICATORS,
    parse_bea_events,
    parse_boj_rows,
    parse_dsbb_records,
    parse_estat_xml,
    parse_fed_events,
    parse_kostat_rows,
)
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
# KOSTAT 年表行(实测形状:보도일자/보도시간/보도자료명)· 三大指标各一样本 → 进方向词语料
_KOSTAT_FIXTURE = [
    ("8.4.(화)", "08:00", "2026년 7월 소비자물가동향", "물가동향과"),
    ("8.12.(수)", "08:00", "2026년 7월 고용동향", "고용통계과"),
    ("8.31.(월)", "08:00", "2026년 7월 산업활동동향", "산업동향과"),
]


def _estat_fixture(os_name: str, class1: str, class2: str) -> bytes:
    """最小 e-Stat 公表予定 XML fixture(★UTF-16 编码 · 同真源)· 解出 1 条未来发布。"""
    xml = (
        '<?xml version="1.0" encoding="UTF-16" ?>'
        f'<e-stat><os_code name="{os_name}"><class_1 name="{class1}">'
        f'<class_2 name="{class2}"><class_3 name=""><class_4 name=""><class_5 name="">'
        "<release_year>2026</release_year><release_month>8</release_month>"
        "<release_day>21</release_day><release_hour>8</release_hour>"
        "<release_minute>30</release_minute>"
        "</class_5></class_4></class_3></class_2></class_1></os_code></e-stat>"
    )
    return xml.encode("utf-16")


# BOJ 統計データ行(实测形状:col1 分类/col2 統計名/col3 时刻或频度/col4+ 月列 datetime)
_BOJ_FIXTURE = [
    ("８．短観", "短観（全国企業短期経済観測調査）／概要及び要旨", "", "08:50:00", "(9月調査)"),
    # openpyxl 返回 naive datetime(与真 xlsx 一致 · parse 只取 .date())
    ("８．短観", "短観（全国企業短期経済観測調査）／概要及び要旨", "", "(四半期)",
     datetime(2026, 10, 1)),  # noqa: DTZ001
]


# event_type → 能过该 spec keep 的 (class_1, class_2) fixture 参数(仅测试造数据用)
_JP_ESTAT_FIXTURE_CLASS = {
    "jp_cpi": ("全国", "2026年7月分"),
    "jp_unemp": ("2026年7月分", "基本集計（2026年7月分）"),
}


def _jp_events() -> list[dict]:
    """日本三指标解析产物 · ★title 从生产注册表 JP_ESTAT_SPECS / BOJ_STATS 取(绝不硬编码
    ——否则改坏 title 常量注入方向词时红线语料锁不响,对抗自审 P2 假绿)。"""
    out: list[dict] = []
    for os_name, etype, title, keep in JP_ESTAT_SPECS:
        c1, c2 = _JP_ESTAT_FIXTURE_CLASS[etype]
        out += parse_estat_xml(_estat_fixture(os_name, c1, c2), os_name=os_name,
                               event_type=etype, title=title, keep=keep)
    out += parse_boj_rows(_BOJ_FIXTURE)  # parse_boj_rows 内部从 BOJ_STATS 常量取 title
    return out


def _dsbb_events() -> list[dict]:
    """DSBB 四国×三指标解析产物 · ★title 从 DSBB_COUNTRIES/DSBB_CATEGORIES 注册表流出
    (改坏国名/指标名常量注入方向词时红线语料/源头锁都要响)。"""
    recs = []
    for iso, _pre, _zh, _tz in DSBB_COUNTRIES:
        for code, _suf, _czh in DSBB_CATEGORIES:
            mv: list = [None] * 13
            mv[7] = {"Day": "15", "Period": "Jun/26"}   # 槽7=7月
            recs.append({"CountryCode": iso, "CategoryCode": code, "MonthValues": mv})
    return parse_dsbb_records(recs, {7: 2026})


def _fake_events() -> list:
    """规则+种子+全解析器产物(美/中/韩/日/欧)全语料 → 伪 EconEvent(每标题过一遍输出面)。"""
    corpus = [
        *gen_rule_and_seed_events(_NOW),
        *parse_fed_events(_FED_FIXTURE),
        *parse_bea_events(_BEA_FIXTURE),
        *parse_kostat_rows(_KOSTAT_FIXTURE, 2026),
        *_jp_events(),
        *_dsbb_events(),
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
    """标题白名单本身零方向词(纯模板拼接的源头保证)· 含 KOSTAT + 日本解析产物。"""
    corpus = [*gen_rule_and_seed_events(_NOW), *parse_kostat_rows(_KOSTAT_FIXTURE, 2026),
              *_jp_events(), *_dsbb_events()]
    assert any(e["event_type"].startswith("jp_") for e in corpus)  # 日本产物真进语料
    assert any(e["event_type"].startswith(("gb_", "de_", "fr_", "it_")) for e in corpus)  # 欧洲
    for e in corpus:
        for w in _DIRECTION_WORDS:
            assert w not in e["title"], f"事件标题含方向词:{e['title']}"


def test_source_title_constants_have_no_direction_words():
    """🔴 直接锁源头 title 常量(注册表 · 比语料流转更硬 · 对抗自审 P2):韩/日事件标题
    零方向词。KOSTAT_INDICATORS / JP_ESTAT_SPECS / BOJ_STATS 的中文 title 都在 idx 2。
    """
    titles = ([k[2] for k in KOSTAT_INDICATORS]
              + [s[2] for s in JP_ESTAT_SPECS]
              + [b[2] for b in BOJ_STATS]
              + [c[2] for c in DSBB_COUNTRIES]      # 欧洲四国国名(DSBB title = 国名+指标名)
              + [c[2] for c in DSBB_CATEGORIES])    # 指标名 CPI/GDP/失业率
    assert titles  # 注册表非空(防路径漂移后空转全绿)
    for t in titles:
        for w in _DIRECTION_WORDS:
            assert w not in t, f"源 title 常量含方向词:{t}"


def test_kr_events_never_injectable_into_decision_card():
    """🔴 韩国红线(写死):全部韩国事件 importance==1 且 markets 不含任何可注入市场
    (cn/us/crypto/hk)——双重焊死决策卡永不注入韩国。绝不因『想让韩国在★2+下显示』提到 2
    (提 2 会穿透注入 · 那是 importance 旋钮本尊,红线级,本模块不碰)。
    """
    corpus = [*gen_rule_and_seed_events(_NOW), *parse_kostat_rows(_KOSTAT_FIXTURE, 2026)]
    kr = [e for e in corpus if e["event_type"] == "bok" or e["event_type"].startswith("kr_")]
    assert kr, "语料里应有韩国事件(BOK 种子 + KOSTAT)"
    injectable = {"cn", "us", "crypto", "hk"}
    for e in kr:
        assert e["importance"] == 1, f"韩国事件 importance 必须=1:{e['event_key']}"
        assert not (set(e["markets"]) & injectable), (
            f"韩国事件 markets 不得含可注入市场:{e['event_key']} {e['markets']}"
        )


def test_jp_events_never_injectable_into_decision_card():
    """🔴 日本红线(写死 · 同韩国双重焊死):全部日本事件 importance==1 且 markets=["jp"]
    (非 cn/us/crypto/hk)——决策卡永不注入日本。绝不因『想让日本在★2+下显示』提到 2。
    """
    jp = _jp_events()
    assert jp, "语料里应有日本事件(CPI/失業率/短観)"
    injectable = {"cn", "us", "crypto", "hk"}
    for e in jp:
        assert e["event_type"].startswith("jp_"), f"非日本类型混入:{e['event_key']}"
        assert e["importance"] == 1, f"日本事件 importance 必须=1:{e['event_key']}"
        assert e["markets"] == ["jp"], f"日本事件 markets 必须=['jp']:{e['event_key']}"
        assert not (set(e["markets"]) & injectable)


def test_eu_events_never_injectable_into_decision_card():
    """🔴 欧洲四国红线(写死 · 同韩日双重焊死):全部欧洲事件(DSBB 四国 + BoE 种子)
    importance==1 且 markets=["eu"](非 cn/us/crypto/hk)——决策卡永不注入。绝不提到 2。
    """
    boe = [e for e in gen_rule_and_seed_events(_NOW) if e["event_type"] == "gb_boe"]
    eu = [*_dsbb_events(), *boe]
    assert eu, "语料里应有欧洲事件(DSBB 四国 + BoE 种子)"
    assert boe, "语料里应有 BoE 种子"
    injectable = {"cn", "us", "crypto", "hk"}
    prefixes = ("gb_", "de_", "fr_", "it_")
    for e in eu:
        assert e["event_type"].startswith(prefixes), f"非欧洲类型混入:{e['event_key']}"
        assert e["importance"] == 1, f"欧洲事件 importance 必须=1:{e['event_key']}"
        assert e["markets"] == ["eu"], f"欧洲事件 markets 必须=['eu']:{e['event_key']}"
        assert not (set(e["markets"]) & injectable)


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
