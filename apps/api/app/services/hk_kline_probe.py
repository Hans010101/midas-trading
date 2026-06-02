"""港股 K线数据源探测(方案A 阶段1 · 生产实测可达 · 只读不改降级链)。

诊断 hk-kline-source-diagnosis.md:东财 stock_hk_hist 生产死 → 单点靠 yfinance → 冷门股抖动 503。
方案A:换新浪 stock_hk_daily 主源。但「本机可达 ≠ 生产可达」(铁律,同 spot 那次)→ 先探测。

本模块:在生产香港 VPS 探测【新浪 stock_hk_daily】+【yfinance】对同一冷门股的可达性 + 行数,
不碰现有 hk_source.fetch_kline 降级链(零回归)· 实测确认新浪生产可达后,阶段2 再正式接入主源。
★ 只读行情探测 · 不写库、不下单、不喂下单数量(下单按手取整走 HKEX 官方 lot)。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import akshare as ak
import yfinance as yf

from app.services.hk_pool import normalize_hk_code

logger = logging.getLogger(__name__)

_ERR_CLAMP = 160


@dataclass(frozen=True)
class HkKlineProbeResult:
    """单标的两源探测结果(新浪 stock_hk_daily 主源候选 + yfinance 现备用)。"""

    symbol: str
    sina_ok: bool
    sina_rows: int
    sina_last: str | None  # 最后一根「date close」· 证可解析 + 数据新鲜
    sina_error: str | None
    yfinance_ok: bool
    yfinance_rows: int
    yfinance_error: str | None


def _to_yf_code(symbol: str) -> str:
    # 同 hk_source._to_yf_code:00980 → 0980.HK
    return normalize_hk_code(symbol).lstrip("0").zfill(4) + ".HK"


def probe_hk_kline_sources(symbol: str) -> HkKlineProbeResult:
    """阻塞:探测新浪 stock_hk_daily + yfinance 对该标的的可达性。

    ★ 同步阻塞(akshare + yfinance 网络)· 调用方须经 asyncio.to_thread 跑。
    """
    code = normalize_hk_code(symbol)

    sina_ok, sina_rows, sina_last, sina_err = False, 0, None, None
    try:
        df = ak.stock_hk_daily(symbol=code, adjust="qfq")
        if df is not None and not df.empty:
            sina_ok = True
            sina_rows = int(len(df))
            last = df.iloc[-1]
            sina_last = f"{last['date']} close={last['close']}"
        else:
            sina_err = "empty"
    except Exception as e:  # noqa: BLE001 · 探测要如实记任何失败(连接/协议)
        sina_err = f"{type(e).__name__}: {e}"[:_ERR_CLAMP]

    yf_ok, yf_rows, yf_err = False, 0, None
    try:
        # 探测用轻量 period=1mo(只验可达 · 不拉全量 max 免给 yfinance 加压)
        ydf = yf.Ticker(_to_yf_code(symbol)).history(
            period="1mo", interval="1d", auto_adjust=True,
        )
        if ydf is not None and not ydf.empty:
            yf_ok = True
            yf_rows = int(len(ydf))
        else:
            yf_err = "empty"
    except Exception as e:  # noqa: BLE001
        yf_err = f"{type(e).__name__}: {e}"[:_ERR_CLAMP]

    logger.info(
        "[hk-kline-probe] %s sina_ok=%s rows=%s | yf_ok=%s rows=%s",
        code, sina_ok, sina_rows, yf_ok, yf_rows,
    )
    return HkKlineProbeResult(
        symbol=code, sina_ok=sina_ok, sina_rows=sina_rows, sina_last=sina_last,
        sina_error=sina_err, yfinance_ok=yf_ok, yfinance_rows=yf_rows,
        yfinance_error=yf_err,
    )
