"""🔴 财经日历页(PR-A)红线机器验证——用户可见事件呈现的可执行证明。

四道锁(对齐 test_econ_redline 的 P0 决策卡锁,这里锁「日历页」输出面):
① 方向词 grep:日历页全部前端文案文件(page/layout/api client)+ 导航入口标签,
   中文全文 grep + 英文串字面量 grep,零方向词。
② 免责完整性:页面含完整「仅供参考,不构成投资建议」;layout metadata 同口径。
③ 零 LLM 渲染路径:前端日历文件零 AI/决策卡/LLM 引用;后端 /econ/calendar 路由
   源码零 services.ai / llm import(库字段直出 + 静态模板,结构性无解读)。
④ 响应客观性钉死:EconEventOut 字段集恰为客观事实字段(时间/名/市场/星级/来源),
   加任何「解读/建议/方向」类字段必须先过本测(红线闸)。

CI 从仓库完整 checkout 跑 pytest(apps/api 为 cwd)→ ../..*/apps/web 可达。
"""

from __future__ import annotations

import re
from pathlib import Path

# 与 test_econ_redline 同源的方向词黑名单(用户可见面一个都不许出现)
_DIRECTION_WORDS = (
    "买入", "卖出", "做多", "做空", "抄底", "逃顶", "加仓", "减仓",
    "建仓", "清仓", "入场", "离场", "上车", "止盈", "止损",
    "看多", "看空", "买进", "卖掉", "利好", "利空",
)
_DIRECTION_WORDS_EN = ("buy", "sell", "long", "short", "bullish", "bearish")

_WEB = Path(__file__).resolve().parents[3] / "web"

# 日历页全部前端文案文件(新增文件必须同步进这份清单——锁③④的静态扫描范围)
_CALENDAR_FILES = (
    _WEB / "app" / "calendar" / "page.tsx",
    _WEB / "app" / "calendar" / "layout.tsx",
    _WEB / "lib" / "api" / "econ-calendar.ts",
)

_FULL_DISCLAIMER = "仅供参考,不构成投资建议"


def _read(p: Path) -> str:
    assert p.exists(), f"日历页文件缺失(路径漂移?更新 _CALENDAR_FILES):{p}"
    return p.read_text(encoding="utf-8")


def _copy_literals(src: str) -> str:
    """抽取 TS/TSX 里的【用户文案】字面量:只取含中文的串(本页文案全中文)。

    纯代码值串(Intl 的 'short'/'long'、CSS class 等)排除——那不是用户可见文案,
    真正的红线是文案面;中文串里嵌英文方向词照样会被抓到。
    """
    parts = re.findall(r"'([^'\\]*)'|\"([^\"\\]*)\"|`([^`]*)`", src)
    cjk = re.compile(r"[一-鿿]")
    return " ".join(s for tup in parts for s in tup if s and cjk.search(s)).lower()


def _strip_ts_comments(src: str) -> str:
    """剥 TS/TSX 注释(块注释 + 行注释;URL 的 :// 无前导空白不受伤)——
    锁③扫的是真实代码引用(import/标识符),注释里的中文说明不该触发。"""
    src = re.sub(r"(?s)/\*.*?\*/", "", src)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", src)


def _strip_py_comments(src: str) -> str:
    src = re.sub(r'(?s)""".*?"""', "", src)
    return re.sub(r"(?m)#.*$", "", src)


# ── ① 方向词 grep(全部日历前端文件 + 导航标签)────────────────────────────


def test_no_direction_words_in_calendar_page_files():
    for p in _CALENDAR_FILES:
        src = _read(p)
        for w in _DIRECTION_WORDS:
            assert w not in src, f"{p.name} 出现方向词:{w}"
        lits = _copy_literals(src)
        for w in _DIRECTION_WORDS_EN:
            assert f" {w} " not in f" {lits} ".replace("-", " "), f"{p.name} 英文方向词:{w}"


def test_nav_entry_label_clean():
    """导航入口标签「财经日历」本身零方向词(market-switcher 只查我们新增的标签行)。"""
    src = _read(_WEB / "components" / "layout" / "market-switcher.tsx")
    assert "财经日历" in src  # 入口存在
    for w in _DIRECTION_WORDS:
        assert w not in src, f"market-switcher 出现方向词:{w}"


# ── ② 免责完整性 ─────────────────────────────────────────────────────────


def test_calendar_page_carries_full_disclaimer():
    page = _read(_CALENDAR_FILES[0])
    assert _FULL_DISCLAIMER in page, "日历页缺完整免责「仅供参考,不构成投资建议」"
    layout = _read(_CALENDAR_FILES[1])
    assert "不构成投资建议" in layout  # metadata description 同口径


def test_volatility_note_is_directionless():
    """波动提示允许存在,但必须客观无方向:提示句不得含预测/操作词。"""
    page = _read(_CALENDAR_FILES[0])
    assert "波动可能放大" in page          # 客观提示在
    for banned in ("将上涨", "将下跌", "应当", "建议操作", "布局"):
        assert banned not in page, f"波动提示越界(出现:{banned})"


# ── ③ 零 LLM 渲染路径(前端 + 后端路由)─────────────────────────────────────


def test_calendar_frontend_never_touches_ai():
    """剥注释后扫真实代码引用(import 藏不进注释;注释里的红线说明不误伤)。"""
    banned = ("decision", "/analysis/", "ai-decision", "deepseek", "llm", "prompt")
    for p in _CALENDAR_FILES:
        src = _strip_ts_comments(_read(p)).lower()
        for token in banned:
            assert token not in src, f"{p.name} 引用了 AI/决策卡相关符号:{token}"


def test_calendar_backend_route_never_imports_llm():
    src = _strip_py_comments(Path("app/api/v1/econ.py").read_text(encoding="utf-8"))
    banned = ("services.ai", "langgraph", "deepseek", "llm", "openai",
              "virtual_trading", "place_market_order")
    low = src.lower()
    for token in banned:
        assert token not in low, f"econ.py 引用了 AI/交易相关符号:{token}"


# ── ④ 响应客观性钉死(加解读字段必须先过这道闸)──────────────────────────────


def test_calendar_response_fields_are_objective_facts_only():
    from app.schemas.econ_calendar import EconCalendarResponse, EconEventOut

    assert set(EconEventOut.model_fields) == {
        "event_key", "event_type", "title", "markets", "importance",
        "scheduled_at", "time_confirmed", "source",
    }, "EconEventOut 字段集变了——若在加『解读/方向』类字段,这是红线,停"
    assert set(EconCalendarResponse.model_fields) == {
        "events", "sources", "updated_at", "any_stale",
    }
