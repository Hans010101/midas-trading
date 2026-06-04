"""K线图渲染 → PNG(mplfinance)· KLINE-001 · 对标 CryptoSharp。

主图:蜡烛 + MA5/MA20 · 副图:成交量 · 副图:RSI(30/70 参考线)· 副图:MACD(DIF/DEA + 柱)。
顶部标题嵌指标快照(RSI / MACD 金叉死叉 / 量比 / ATR)。朱红涨 / 墨绿跌(A股传统 · 视觉系统)。
CJK 字体:slim 镜像 fonts-noto-cjk → Noto * CJK(已 docker 实测中文不豆腐)· 默认 DejaVu 会渲豆腐块。

红线:只读已有 K线数据画图 · 不碰下单/撮合/红线。
"""

from __future__ import annotations

import asyncio
import io
import threading

import matplotlib as mpl

mpl.use("Agg")  # headless · 无显示后端(slim 镜像无 X)
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import mplfinance as mpf  # noqa: E402
import pandas as pd  # noqa: E402

from app.schemas.market import Kline  # noqa: E402
from app.services.ai import indicators  # noqa: E402

_UP = "#DC143C"  # 朱红涨(视觉系统)
_DOWN = "#0F6E5F"  # 墨绿跌
_GOLD = "#B8860B"  # 帝王金(RSI / DEA 线)
_RED = "#C8102E"  # 中国红(DIF 线)

_MARKET_LABEL = {"cn": "A股", "us": "美股", "hk": "港股", "crypto": "加密"}
_MIN_KLINES = 30  # 少于此画不出有意义的 MA20/MACD → 调用方应回退链接

_font_lock = threading.Lock()
_cjk_font: str | None = None
_font_done = False

# 按【已知全字库 CJK 族】优先选 · 排除「Symbols/Fallback」回退字(只有符号无汉字/拉丁,选了全豆腐)。
# 生产 docker slim = fonts-noto-cjk → "Noto Sans CJK JP"(放第一);其余是本机/其它环境兜底。
_CJK_PREFER = (
    "Noto Sans CJK",
    "Source Han Sans",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Microsoft YaHei",
    "PingFang",
    "Hiragino Sans",
    "Heiti",
    "Songti",
    "STHeiti",
    "SimHei",
    "Arial Unicode",
    "Noto Serif CJK",
    "Source Han Serif",
)


def _configure_cjk_font() -> str | None:
    """设 matplotlib 中文字体(幂等 · 线程安全)· 返回选用字体名(无则 None)。

    按 _CJK_PREFER 顺序找第一个【已注册的全字库 CJK 族】· 排除 Symbols/Fallback 回退字。
    默认 DejaVu 无中文字形 → 不设会豆腐块(已 docker 实测 · slim 选到 Noto Sans CJK JP 正常)。
    都没有(无 CJK 字体的环境)→ 保持默认(中文豆腐 · 仅本机外裸环境,生产 docker 已装字体)。
    """
    global _font_done, _cjk_font
    if _font_done:
        return _cjk_font
    with _font_lock:
        if _font_done:
            return _cjk_font
        names = {
            f.name
            for f in fm.fontManager.ttflist
            if "Symbols" not in f.name and "Fallback" not in f.name
        }
        chosen: str | None = None
        for pref in _CJK_PREFER:
            match = sorted(n for n in names if pref in n)
            if match:
                chosen = match[0]
                break
        _cjk_font = chosen
        if _cjk_font:
            mpl.rcParams["font.family"] = "sans-serif"
            mpl.rcParams["font.sans-serif"] = [_cjk_font, "DejaVu Sans"]
        mpl.rcParams["axes.unicode_minus"] = False  # 负号不豆腐
        _font_done = True
        return _cjk_font


def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI 序列(Wilder 平滑 ≈ ewm alpha=1/period)· 前 period 根为 NaN(图自动跳过)。"""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    rsi[avg_loss == 0] = 100.0  # 全涨无跌 → RSI 100
    return rsi


def _macd_series(close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD(12,26,9)序列 · 返回 (DIF, DEA, 柱)。画线/画柱要序列,非最新值。"""
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    hist = (dif - dea) * 2
    return dif, dea, hist


def render_kline_png(
    *,
    symbol: str,
    name: str,
    market: str,
    klines: list[Kline],
    period_label: str = "日K",
) -> bytes:
    """渲染 K线图 PNG bytes(阻塞 · 调用方用 render_kline_png_async 走 to_thread)。

    数据不足(< _MIN_KLINES)→ ValueError(调用方捕获 → 回退网页链接)。
    """
    if len(klines) < _MIN_KLINES:
        msg = f"K线数据不足({len(klines)} < {_MIN_KLINES})"
        raise ValueError(msg)
    _configure_cjk_font()

    df = pd.DataFrame(
        {
            "Open": [k.open for k in klines],
            "High": [k.high for k in klines],
            "Low": [k.low for k in klines],
            "Close": [k.close for k in klines],
            "Volume": [k.volume for k in klines],
        },
        index=pd.DatetimeIndex([k.ts for k in klines]),
    )

    rsi = _rsi_series(df["Close"])
    dif, dea, hist = _macd_series(df["Close"])
    hist_up = hist.where(hist >= 0)
    hist_down = hist.where(hist < 0)

    # 标题指标快照(对标 CryptoSharp)· 用 indicators 现成口径(单一事实源)
    rsi_val = indicators.compute_rsi(klines).get(14, 50.0)
    macd = indicators.compute_macd(klines)
    macd_state = "金叉" if macd["dif"] >= macd["dea"] else "死叉"
    atr = indicators.compute_atr(klines)
    vr = indicators.compute_volume_ratio(klines)
    mlabel = _MARKET_LABEL.get(market, market)
    title = (
        f"{name}({symbol}) · {mlabel} · {period_label}\n"
        f"RSI {rsi_val:.0f} · MACD {macd_state} · 量比 {vr:.2f} · ATR {atr:.2f}"
    )

    rc: dict[str, object] = {"axes.unicode_minus": False}
    if _cjk_font:
        rc["font.family"] = "sans-serif"
        rc["font.sans-serif"] = [_cjk_font, "DejaVu Sans"]
    mc = mpf.make_marketcolors(
        up=_UP, down=_DOWN, edge="inherit", wick="inherit", volume="inherit",
    )
    style = mpf.make_mpf_style(
        marketcolors=mc, gridstyle=":", facecolor="white", figcolor="white", rc=rc,
    )

    n = len(df)
    apds = [
        # RSI 面板(panel 2)+ 70/30 参考线
        mpf.make_addplot(rsi, panel=2, color=_GOLD, width=1.0, ylabel="RSI"),
        mpf.make_addplot([70] * n, panel=2, color="#BBBBBB", width=0.6, linestyle="--"),
        mpf.make_addplot([30] * n, panel=2, color="#BBBBBB", width=0.6, linestyle="--"),
        # MACD 面板(panel 3):柱(红涨绿跌)+ DIF/DEA 线
        mpf.make_addplot(hist_up, type="bar", panel=3, color=_UP, ylabel="MACD"),
        mpf.make_addplot(hist_down, type="bar", panel=3, color=_DOWN),
        mpf.make_addplot(dif, panel=3, color=_RED, width=0.9),
        mpf.make_addplot(dea, panel=3, color=_GOLD, width=0.9),
    ]

    buf = io.BytesIO()
    fig, _axes = mpf.plot(
        df,
        type="candle",
        style=style,
        mav=(5, 20),
        volume=True,
        addplot=apds,
        panel_ratios=(6, 2, 2, 2),
        figratio=(16, 11),
        figscale=1.15,
        title=title,
        datetime_format="%m-%d",
        xrotation=0,
        returnfig=True,
        tight_layout=True,
    )
    try:
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    finally:
        plt.close(fig)
    return buf.getvalue()


async def render_kline_png_async(
    *,
    symbol: str,
    name: str,
    market: str,
    klines: list[Kline],
    period_label: str = "日K",
) -> bytes:
    """异步包装:matplotlib 阻塞 → asyncio.to_thread,不卡 event loop。"""
    return await asyncio.to_thread(
        render_kline_png,
        symbol=symbol,
        name=name,
        market=market,
        klines=klines,
        period_label=period_label,
    )
