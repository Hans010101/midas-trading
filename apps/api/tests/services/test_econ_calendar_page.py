"""🔴 财经日历页(PR-A)红线机器验证——用户可见事件呈现的可执行证明。

四道锁(对齐 test_econ_redline 的 P0 决策卡锁,这里锁「日历页」输出面):
① 方向词 grep:日历页全部前端文案文件(目录级 glob,拆组件不逃逸)+ 两处导航入口,
   中文全文 grep + 英文字面量分级 grep(buy/sell/bullish/bearish 任意字面量 \\b 全匹配;
   long/short 只查含中文文案串——放行 Intl 'long'/'short' 合法代码值),零方向词。
② 免责完整性:★在剥注释后的源码上断言(否则文件头注释里的红线说明会永久喂饱断言,
   删掉用户可见免责锁也不响——对抗自审实测出的死断言,已修)。
③ 零 LLM 渲染路径:前端日历文件剥注释后零 AI/决策卡/缠论/策略符号(banned 覆盖仓内
   现存 AI 面模块:ai-card/api/chan/strategy/analysis);后端 /econ/calendar 路由零
   services.ai / llm import(库字段直出 + 静态模板,结构性无解读)。
④ 响应客观性钉死:EconEventOut 字段集恰为客观事实字段,加「解读/方向」字段必先过本闸。

CI 从仓库完整 checkout 跑 pytest(apps/api 为 cwd)→ ../../apps/web 可达。
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
# 分级英文锁:strict 组在这批文件里永远不是合法代码值 → 任意字面量 \b 全匹配
_DIRECTION_EN_STRICT = ("buy", "sell", "bullish", "bearish")
# long/short 是 Intl('long'/'short')等合法代码值 → 只查含中文的文案串
_DIRECTION_EN_COPY = ("long", "short")

_WEB = Path(__file__).resolve().parents[3] / "web"

# ★目录级 glob(拆组件自动进锁,硬编码清单会静默逃逸——对抗自审实测)+ API client
_CALENDAR_FILES = tuple(sorted((_WEB / "app" / "calendar").rglob("*.ts*"))) + (
    _WEB / "lib" / "api" / "econ-calendar.ts",
)

_FULL_DISCLAIMER = "仅供参考,不构成投资建议"


def _read(p: Path) -> str:
    assert p.exists(), f"日历页文件缺失(路径漂移?):{p}"
    return p.read_text(encoding="utf-8")


def _copy_literals(src: str) -> str:
    """只取含中文的字面量(本页文案全中文;中文串里嵌英文方向词照样被抓)。"""
    parts = re.findall(r"'([^'\\]*)'|\"([^\"\\]*)\"|`([^`]*)`", src)
    cjk = re.compile(r"[一-鿿]")
    return " ".join(s for tup in parts for s in tup if s and cjk.search(s)).lower()


def _strip_ts_comments(src: str) -> str:
    """剥 TS/TSX 注释(块注释 + 行注释;URL 的 :// 无前导空白不受伤)——
    锁②③断言真实代码/JSX 文本,注释里的红线说明不该喂饱或触发断言。"""
    src = re.sub(r"(?s)/\*.*?\*/", "", src)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", src)


def _strip_py_comments(src: str) -> str:
    src = re.sub(r'(?s)""".*?"""', "", src)
    return re.sub(r"(?m)#.*$", "", src)


def test_calendar_files_glob_anchor():
    """★防空 glob 锚:目录漂移时 rglob 返回空 → 所有 for 循环空转全绿(比硬编码更假绿)。"""
    assert _WEB / "app" / "calendar" / "page.tsx" in _CALENDAR_FILES
    assert len(_CALENDAR_FILES) >= 3


# ── ① 方向词 grep(全部日历前端文件 + 两处导航入口)──────────────────────────


def test_no_direction_words_in_calendar_page_files():
    for p in _CALENDAR_FILES:
        src = _read(p)
        for w in _DIRECTION_WORDS:
            assert w not in src, f"{p.name} 出现方向词:{w}"
        # strict 组在剥注释后的【全源码】上 \b 匹配(交叉审 PoC:JSX 裸文本
        # <p>Buy the dip</p> 与转义字面量 "sell now" 都不进引号字面量语料=绕过;
        # 全源码 \b 两者都抓,sellPrice/buyLimit 等驼峰因 \b 不成立零误伤)
        stripped = _strip_ts_comments(src).lower()
        for w in _DIRECTION_EN_STRICT:
            assert not re.search(rf"\b{w}\b", stripped), f"{p.name} 英文方向词:{w}"
        lits = _copy_literals(src)
        for w in _DIRECTION_EN_COPY:
            assert f" {w} " not in f" {lits} ".replace("-", " "), f"{p.name} 英文方向词:{w}"


def test_nav_entry_labels_clean():
    """两处导航入口(market-switcher + 命令面板)标签零方向词,入口存在。"""
    for rel in (("components", "layout", "market-switcher.tsx"),
                ("lib", "command-palette-nav.ts")):
        src = _read(_WEB.joinpath(*rel))
        assert "财经日历" in src, f"{rel[-1]} 缺「财经日历」入口"
        for w in _DIRECTION_WORDS:
            assert w not in src, f"{rel[-1]} 出现方向词:{w}"


def test_jpkr_bucket_and_country_labels_present():
    """特性钉:「日韩」合并桶 + 单条国别(日本/韩国)+ 韩/日来源标注都在。"""
    page = _read(_WEB / "app" / "calendar" / "page.tsx")
    assert "日韩" in page, "缺「日韩」合并桶标签"
    assert "韩国" in page, "缺韩国国别标注"
    assert "日本" in page, "缺日本国别标注(合并桶内仍标各国)"
    assert "kostat" in page, "缺 KOSTAT 来源标注映射"
    # 日本三指标 event_type 归入 jpkr 桶 + 单条标日本 + 来源(統計局/BOJ)映射
    for et in ("jp_cpi", "jp_unemp", "jp_tankan"):
        assert et in page, f"缺日本 event_type 桶/国别映射:{et}"
    assert "jp_estat" in page, "缺日本統計局来源标注映射"
    assert "boj_xlsx" in page, "缺日本 BOJ 来源标注映射"


def test_i18n_canary_forces_lock_extension():
    """i18n 金丝雀:en 文案落地(next-intl/useTranslations)时英文锁对纯英文串会失明——
    此测逼停静默漏检,届时必须显式扩锁(纯英文文案全量过 strict 组)再放行。"""
    for p in _CALENDAR_FILES:
        src = _read(p)
        assert "next-intl" not in src, f"{p.name} 引入 i18n:先扩英文方向词锁再放行"
        assert "useTranslations" not in src, f"{p.name} 引入 i18n:先扩英文方向词锁再放行"


# ── ② 免责完整性(★剥注释后断言——头注释含免责字样,原始源码断言=死断言)────────


def test_calendar_page_carries_full_disclaimer():
    page = _strip_ts_comments(_read(_WEB / "app" / "calendar" / "page.tsx"))
    assert _FULL_DISCLAIMER in page, "日历页用户可见免责「仅供参考,不构成投资建议」缺失"
    layout = _strip_ts_comments(_read(_WEB / "app" / "calendar" / "layout.tsx"))
    assert "不构成投资建议" in layout  # metadata description 同口径


def test_volatility_note_is_directionless():
    """波动提示允许存在,但必须客观无方向:提示句不得含预测/操作词。"""
    page = _strip_ts_comments(_read(_WEB / "app" / "calendar" / "page.tsx"))
    assert "波动可能放大" in page          # 客观提示在(JSX 文本 · 非注释)
    for banned in ("将上涨", "将下跌", "应当", "建议操作", "布局"):
        assert banned not in page, f"波动提示越界(出现:{banned})"


# ── ③ 零 LLM 渲染路径(前端 + 后端路由)─────────────────────────────────────


def test_calendar_frontend_never_touches_ai():
    """剥注释后扫真实代码引用。banned 覆盖仓内现存 AI 面模块(对抗自审实测:
    import CryptoAiCard / lib/api/chan / lib/api/strategy 对旧六词零命中=假绿)。"""
    banned = ("decision", "analysis", "ai-card", "api/chan", "strategy",
              "deepseek", "llm", "prompt")
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
