#!/usr/bin/env python3
"""ADR 0034 · 港股接入 · 阶段零-B/C:港股数据源【只读探测】(akshare + yfinance · 0700.HK 腾讯)。

★★ 本脚本只读探测 ★★
  - 只【拉取上游行情】(akshare / yfinance),用于一次性评估数据源质量。
  - 绝不写我们的任何库(不连 ClickHouse / Postgres / Redis)、不改任何配置、不落盘数据。
  - 这是 Hans 在服务器一次性手动跑的探测,不是生产 app 的实时轮询(不违反"只读 CH"红线)。

探测目标:
  零-B:akshare 港股接口 vs yfinance .HK —— 历史 K 线质量/字段、实时/最新价、延迟、复权。
  零-C:akshare 港股快照里【有没有"每手股数"字段】(决定决策②每手兜底要不要手动策展)。

运行(在 api 容器里跑 · 容器已装 akshare/yfinance · 从宿主机管道喂入,无需把脚本拷进镜像):
  docker exec -i midas-api python - < scripts/hk-phase0/probe_hk_data.py
输出:清晰的对比报告(人工据此定主源 + 延迟 + 每手字段有无)。
"""

from __future__ import annotations

import datetime as dt
import traceback

SYMBOL_AK = "00700"      # akshare 港股代码(腾讯)
SYMBOL_YF = "0700.HK"    # yfinance ticker(腾讯)
LOT_HINTS = ("每手", "手", "最小", "lot", "board", "成交单位", "买入单位")


def section(title: str) -> None:
    print("\n" + "=" * 64 + f"\n{title}\n" + "=" * 64)


def safe(fn_desc: str):
    """装饰:任一探测块失败只打印异常、不中断整体。"""
    def deco(fn):
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {fn_desc} 失败:{e!r}")
                traceback.print_exc()
                return None
        return wrapper
    return deco


# ── akshare ──────────────────────────────────────────────────────────


@safe("akshare 可用港股函数枚举")
def ak_list_hk_functions() -> None:
    import akshare as ak
    hk = sorted(f for f in dir(ak) if "hk" in f.lower() and not f.startswith("_"))
    print(f"  akshare 版本:{getattr(ak, '__version__', '?')}")
    print(f"  含 'hk' 的函数 {len(hk)} 个:")
    for f in hk:
        print(f"    - {f}")


@safe("akshare 历史 K 线 stock_hk_hist")
def ak_history() -> None:
    import akshare as ak
    raw = ak.stock_hk_hist(symbol=SYMBOL_AK, period="daily", adjust="")
    print(f"  不复权 shape={raw.shape} 列={list(raw.columns)}")
    print(f"  最近 2 行:\n{raw.tail(2).to_string(index=False)}")
    try:
        qfq = ak.stock_hk_hist(symbol=SYMBOL_AK, period="daily", adjust="qfq")
        close_col = "收盘" if "收盘" in raw.columns else raw.columns[2]
        print(f"  前复权(qfq)首/尾 {close_col}:{qfq.iloc[0][close_col]} → {qfq.iloc[-1][close_col]}")
        diff = (raw.iloc[0][close_col] != qfq.iloc[0][close_col])
        print(f"  ★ 复权是否生效(不复权 vs 前复权 早期值不同):{'是' if diff else '否(可能本身无除权)'}")
    except Exception as e:  # noqa: BLE001
        print(f"  复权探测失败:{e!r}")


@safe("akshare 实时快照 + 每手字段(零-C)")
def ak_spot_and_lot() -> None:
    import akshare as ak
    spot = ak.stock_hk_spot_em()
    print(f"  快照 shape={spot.shape}")
    print(f"  ★ 全部列(找'每手'类字段):{list(spot.columns)}")
    # 找 00700 行(代码列名可能是 '代码' / 'symbol')
    code_col = next((c for c in spot.columns if c in ("代码", "symbol", "code")), spot.columns[0])
    hit = spot[spot[code_col].astype(str).str.contains("00700")]
    if len(hit):
        print(f"  00700 快照行:\n{hit.to_string(index=False)}")
    else:
        print(f"  未在快照里找到 00700(列 {code_col})· 看上面列名手动核对")
    lot_cols = [c for c in spot.columns if any(h in str(c) for h in LOT_HINTS)]
    print(f"  ★★ 零-C · 疑似【每手股数】字段:{lot_cols or '无 —— akshare 快照不含每手,需手动策展兜底(决策②)'}")


# ── yfinance ─────────────────────────────────────────────────────────


@safe("yfinance 0700.HK history + info + 延迟")
def yf_probe() -> None:
    import yfinance as yf
    t = yf.Ticker(SYMBOL_YF)
    hist = t.history(period="1mo")
    print(f"  yfinance 版本:{getattr(yf, '__version__', '?')}")
    print(f"  history shape={hist.shape} 列={list(hist.columns)}")
    if len(hist):
        print(f"  最后日期:{hist.index[-1]} · 收盘:{hist['Close'].iloc[-1]:.3f}")
    info = {}
    try:
        info = t.info or {}
    except Exception as e:  # noqa: BLE001
        print(f"  .info 取失败(yfinance 常见):{e!r}")
    for k in ("currency", "exchange", "quoteType", "regularMarketPrice", "previousClose"):
        print(f"  info[{k}] = {info.get(k)}")
    # 延迟:regularMarketTime 是 epoch 秒
    mt = info.get("regularMarketTime")
    if mt:
        ts = dt.datetime.fromtimestamp(mt, tz=dt.UTC)
        now = dt.datetime.now(tz=dt.UTC)
        print(f"  ★ 最新价时间 regularMarketTime={ts.isoformat()} · 距现在 {(now - ts).total_seconds() / 60:.1f} 分钟(延迟参考)")
    lot_keys = {k: v for k, v in info.items() if "lot" in k.lower() or "share" in k.lower()}
    print(f"  ★★ 零-C · yfinance info 含 lot/share 的键:{lot_keys or '无明显每手字段'}")


# ── 主流程 ───────────────────────────────────────────────────────────


def main() -> None:
    print("ADR0034 零-B/C · 港股数据源只读探测 · 标的 00700 / 0700.HK(腾讯)")
    print("★ 只拉上游行情、绝不写任何库/配置/落盘")

    section("【akshare】① 可用港股函数")
    ak_list_hk_functions()
    section("【akshare】② 历史 K 线 + 复权")
    ak_history()
    section("【akshare】③ 实时快照 + 每手字段(零-C)")
    ak_spot_and_lot()

    section("【yfinance】④ 历史 + info + 延迟 + 每手键(零-C)")
    yf_probe()

    section("结论模板(人工据上面输出填)")
    print("""  零-B 主源选型(决策①):
    · 历史K线字段完整度:akshare ___ vs yfinance ___
    · 实时/最新价覆盖 + 延迟:akshare ___ 分钟 · yfinance ___ 分钟(15min 内可接受)
    · 复权可用:akshare qfq ___ · yfinance(history 默认 auto_adjust)___
    → 建议主源:______
  零-C 每手字段(决策②):
    · akshare 快照含每手字段?______ · yfinance info 含每手?______
    → 若都无 → 走【手动策展配置】覆盖热门港股(腾讯/阿里/美团…一手股数表)
  整体:免费源是否够用(决策③接受 15min 延迟)?______
  ✅ 探测完成(只读)· 未写任何库""")


if __name__ == "__main__":
    main()
