#!/usr/bin/env python3
"""ADR 0034a · 港股阶段一前置 · 工作日【实时延迟补测】(只读)。

★★ 只读探测 ★★ 只拉 akshare/yfinance 港股实时/最新价(00700 腾讯),算延迟分钟数。
  不写任何库、不改配置、不落盘。零-B 周末测不准(实时接口被掐 / yfinance 报 1461min)→
  本脚本【工作日港股交易时段 北京时间 09:30–16:00】单跑,确认延迟 ≤ 15min(决策③可接受线)。

运行(api 容器已装 akshare/yfinance · 从宿主机管道喂入):
  docker exec -i midas-api python - < scripts/hk-phase1/probe_hk_latency.py
判定:实时价 + 数据时间戳 + 距当前延迟分钟数;延迟 ≤ 15min → 免费源够用,进 P1。
"""

from __future__ import annotations

import datetime as dt
import traceback

SYMBOL_AK = "00700"
SYMBOL_YF = "0700.HK"
ACCEPT_MIN = 15  # 决策③:延迟 ≤ 15min 可接受


def now_utc() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def verdict(delay_min: float | None) -> str:
    if delay_min is None:
        return "⚠ 拿不到数据时间戳 → 无法判定延迟(实时接口可能被掐,重试或换时段)"
    if delay_min <= ACCEPT_MIN:
        return f"✅ 延迟 {delay_min:.1f}min ≤ {ACCEPT_MIN}min · 可接受"
    return f"⚠ 延迟 {delay_min:.1f}min > {ACCEPT_MIN}min · 超可接受线(看是否非交易时段 / 换源)"


def probe_akshare() -> None:
    print("\n──── akshare 实时(stock_hk_spot_em → 00700)────")
    try:
        import akshare as ak
        spot = ak.stock_hk_spot_em()
        code_col = next((c for c in spot.columns if c in ("代码", "symbol", "code")), spot.columns[0])
        row = spot[spot[code_col].astype(str).str.contains(SYMBOL_AK)]
        if not len(row):
            print(f"  未找到 {SYMBOL_AK}(列 {code_col})· 列名:{list(spot.columns)}")
            return
        r = row.iloc[0]
        price_col = next((c for c in spot.columns if c in ("最新价", "现价", "price")), None)
        print(f"  最新价({price_col}):{r[price_col] if price_col else '?'}")
        # 东财快照常不带逐行时间戳 → 延迟靠人工对比港交所实时报价;若有时间字段则用之
        time_col = next((c for c in spot.columns if any(k in str(c) for k in ("时间", "time", "更新"))), None)
        if time_col:
            print(f"  数据时间字段({time_col}):{r[time_col]}")
            print("  → 用该时间戳与北京时间现在比,算延迟分钟数")
        else:
            print("  快照无逐行时间戳 → 延迟靠【人工对比港交所/券商实时报价】(同一时刻价差/滞后)")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ akshare 实时失败:{e!r}(实时接口常被掐 · 重试 / 换时段)")
        traceback.print_exc()


def probe_yfinance() -> None:
    print("\n──── yfinance 实时(0700.HK · regularMarketTime 算延迟)────")
    try:
        import yfinance as yf
        t = yf.Ticker(SYMBOL_YF)
        info = {}
        try:
            info = t.info or {}
        except Exception as e:  # noqa: BLE001
            print(f"  .info 失败:{e!r}")
        price = info.get("regularMarketPrice")
        mt = info.get("regularMarketTime")
        print(f"  regularMarketPrice = {price}")
        delay_min = None
        if mt:
            ts = dt.datetime.fromtimestamp(mt, tz=dt.UTC)
            delay_min = (now_utc() - ts).total_seconds() / 60
            print(f"  数据时间戳 regularMarketTime = {ts.isoformat()}(UTC)")
            print(f"  现在 = {now_utc().isoformat()}(UTC)")
            print(f"  ★ 延迟 = {delay_min:.1f} 分钟")
        else:
            print("  无 regularMarketTime(非交易时段 / info 取不到)")
        print(f"  判定:{verdict(delay_min)}")
    except Exception as e:  # noqa: BLE001
        print(f"  ✗ yfinance 失败:{e!r}")
        traceback.print_exc()


def main() -> None:
    print("ADR0034a 港股实时延迟补测(只读)· 标的 00700 / 0700.HK")
    print(f"现在:{now_utc().isoformat()}(UTC)· 北京时间约 {(now_utc() + dt.timedelta(hours=8)).strftime('%H:%M')}")
    print("★ 务必在【工作日 · 港股交易时段(北京 09:30–12:00 / 13:00–16:00)】跑,否则延迟不可信")
    probe_akshare()
    probe_yfinance()
    print("\n结论(人工填):主源实时延迟 ___ 分钟 · 是否 ≤15min ___ · 选哪个源 ___")
    print("✅ 探测完成(只读 · 未写任何库)")


if __name__ == "__main__":
    main()
