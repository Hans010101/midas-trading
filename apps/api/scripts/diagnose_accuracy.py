"""数据精度诊断脚本 · 0010 报告产出器。

跑法:
  cd apps/api && .venv/bin/python scripts/diagnose_accuracy.py

输出:
  - 三市场各取最新 K 线跟权威源对比
  - 偏差 % · 根因诊断
  - 印出 markdown 表格便于贴到 0010 ADR
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# 让脚本能 import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "diag-only")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://midas:midas_dev@localhost:5432/midas",
)
os.environ.setdefault("CLICKHOUSE_HOST", "localhost")
os.environ.setdefault("CLICKHOUSE_USER", "midas")
os.environ.setdefault("CLICKHOUSE_PASSWORD", "midas_dev")


def pct(ours: float, ref: float) -> str:
    if ref == 0:
        return "n/a"
    return f"{(ours - ref) / ref * 100:+.2f}%"


async def main() -> None:  # noqa: C901
    from app.services.clickhouse_client import ClickHouseClient

    ch = await ClickHouseClient.create()

    print("=" * 70)
    print("数据精度诊断 · 三市场最新 K 线 vs 权威源")
    print("=" * 70)

    # ===== NVDA =====
    print("\n## 美股 NVDA")
    print()
    rows = await ch.select_kline(
        symbol="NVDA", market="us", period="1d", limit=1,
    )
    if not rows:
        print("  ❌ CH 无数据")
    else:
        k = rows[-1]
        print(f"  CH(修复后,latest=ts DESC LIMIT 1 + reverse)· {k.ts.date()}")
        print(f"    Open: ${float(k.open):.2f} High: ${float(k.high):.2f}")
        print(f"    Low:  ${float(k.low):.2f} Close: ${float(k.close):.2f}")
        print(f"    Volume: {int(k.volume):,}")

    # 从 yfinance 直拉对比
    try:
        import yfinance as yf
        t = yf.Ticker("NVDA")
        info = t.info
        hist = t.history(period="2d", auto_adjust=True)
        print()
        print("  Yahoo Finance(权威)· auto_adjust=True(yfinance 默认)")
        if not hist.empty:
            last_row = hist.iloc[-1]
            print(f"    Date: {hist.index[-1].date()}")
            print(f"    Open: ${last_row['Open']:.2f}")
            print(f"    High: ${last_row['High']:.2f}")
            print(f"    Low:  ${last_row['Low']:.2f}")
            print(f"    Close: ${last_row['Close']:.2f}")
        print(f"    info.regularMarketPrice: ${info.get('regularMarketPrice')}")

        if rows:
            ours = float(rows[-1].close)
            ref = float(hist.iloc[-1]["Close"]) if not hist.empty else 0
            print(f"\n  偏差 close: {pct(ours, ref)}  · 可接受阈值 ±0.5%")
    except Exception as e:  # noqa: BLE001
        print(f"  yfinance 拉取失败: {e}")

    # ===== BTC/USDT =====
    print("\n## 加密 BTC/USDT")
    print()
    rows = await ch.select_kline(
        symbol="BTC/USDT", market="crypto", period="1d", limit=1,
    )
    if not rows:
        print("  ❌ CH 无数据")
    else:
        k = rows[-1]
        print(f"  CH · {k.ts.date()}")
        print(f"    Open: ${float(k.open):,.2f}  Close: ${float(k.close):,.2f}")

    try:
        import ccxt
        ex = ccxt.binance()
        ohlcv = ex.fetch_ohlcv("BTC/USDT", timeframe="1d", limit=2)
        ticker = ex.fetch_ticker("BTC/USDT")
        print()
        print("  Binance 官方 API(权威)")
        if ohlcv:
            last = ohlcv[-1]
            d = datetime.fromtimestamp(last[0] / 1000, tz=UTC).date()
            print(f"    Date: {d}")
            print(f"    Open: ${last[1]:,.2f}  High: ${last[2]:,.2f}")
            print(f"    Low:  ${last[3]:,.2f}  Close: ${last[4]:,.2f}")
        print(f"    ticker.last: ${ticker['last']:,.2f}")

        if rows:
            ours = float(rows[-1].close)
            ref = float(ohlcv[-1][4]) if ohlcv else 0
            print(f"\n  偏差 close: {pct(ours, ref)}  · 可接受阈值 ±0.1%")
    except Exception as e:  # noqa: BLE001
        print(f"  ccxt 拉取失败: {e}")

    # ===== 600519(贵州茅台)=====
    print("\n## A 股 600519(贵州茅台)")
    print()
    rows = await ch.select_kline(
        symbol="600519", market="cn", period="1d", limit=1,
    )
    if not rows:
        print("  ❌ CH 无数据")
    else:
        k = rows[-1]
        print(f"  CH · {k.ts.date()}")
        print(f"    Open: ¥{float(k.open):.2f}  Close: ¥{float(k.close):.2f}")

    try:
        import akshare as ak
        # 拉最近 5 天数据(Sina 接口,跟我们用的源一样)
        df = ak.stock_zh_a_daily(symbol="sh600519")
        if not df.empty:
            last = df.iloc[-1]
            print()
            print("  AKShare Sina(我们用的源)")
            print(f"    Date: {last['date']}")
            print(f"    Open: ¥{last['open']:.2f}  Close: ¥{last['close']:.2f}")

            if rows:
                ours = float(rows[-1].close)
                ref = float(last["close"])
                print(f"\n  偏差 close: {pct(ours, ref)}  · 可接受阈值 ±0.2%")

        # 再用东方财富做交叉验证 · 权威性更高
        try:
            df2 = ak.stock_zh_a_hist(
                symbol="600519",
                period="daily",
                # 诊断脚本 · 用 CN 本地日期查 A 股(naive 故意 · tz=UTC 边界会漏当日)
                start_date=(datetime.now() - timedelta(days=10)).strftime("%Y%m%d"),  # noqa: DTZ005
                end_date=datetime.now().strftime("%Y%m%d"),  # noqa: DTZ005
                adjust="",  # 不复权 · 跟现价对齐
            )
            if not df2.empty:
                last_em = df2.iloc[-1]
                print()
                print("  AKShare 东方财富(交叉验证 · 不复权)")
                print(f"    Date: {last_em['日期']}")
                print(f"    Close: ¥{last_em['收盘']:.2f}")
        except Exception as e:  # noqa: BLE001
            print(f"  东财交叉验证失败: {e}")

    except Exception as e:  # noqa: BLE001
        print(f"  akshare 拉取失败: {e}")

    await ch.close()
    print("\n" + "=" * 70)
    print("诊断完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
