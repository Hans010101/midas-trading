"""策略信号序列扫描器 · 模拟交易第二层形态A 单元1(ADR 0037 §2/§3)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线(焊死):
   - 只算信号 · 不下单 · 不执行 · 不撮合 · 不碰任何 virtual_trading 引擎。
   - 只读 K 线(调用方从 select_kline 拿历史 K 线传入)· 绝不打实时上游。
   - 复用 indicators.py 数学基础(_sma / _stdev / Wilder RSI 逻辑),
     但【不改任何现有 compute_* 契约】—— 现有 AI 决策卡指标零回归。
   - 不碰现有 AI 管线(workflow / technical agent)/ 缠论 / 第一层。
═══════════════════════════════════════════════════════════════════════════

三策略(穿越式离散信号 · 拍板①②③ · 纯 OHLCV 四市场通用):
- ma_cross       · MA5 上穿 MA20 = buy / 下穿 = sell(金叉/死叉)
- rsi_reversal   · RSI(14) 上穿 30 = buy / 下穿 70 = sell(反弹确认式 · 拍板①)
- boll_reversion · 收盘价下穿布林下轨 = buy / 上穿上轨 = sell(均值回归 · 收盘价穿越 · 拍板②)

为什么穿越式(crossover)而非状态式:穿越只在「状态切换的那一根」标一个点,天然离散,
不会在 RSI 持续 < 30 / 价格持续在轨外时连续刷点,完美匹配 K 线信号点标注(midas-fractal)。
"""

from __future__ import annotations

from collections.abc import Callable

from app.schemas.market import Kline
from app.schemas.strategy import SignalKind, StrategyKind, StrategySignal

# ★ 复用 indicators 的纯数学基础(不改其对外 compute_* 契约 · 现有指标零回归)
from app.services.ai.indicators import _sma, _stdev

# ===== 默认参数(拍板⑤ · MVP 固定)=====
_MA_FAST = 5
_MA_SLOW = 20
_RSI_PERIOD = 14
_RSI_OVERSOLD = 30.0
_RSI_OVERBOUGHT = 70.0
_BOLL_PERIOD = 20
_BOLL_K = 2.0

# ===== 极端信号阈值(第二刀 · 仅 crypto perp · 合理默认避免频繁误触发 · 便于后续调)=====
_FUNDING_EXTREME = 0.0005   # |资金费率| > 0.05%/8h = 极端(Binance 常态 ~0.01%)· 正高=多头拥挤偏空
_LS_HIGH = 2.0              # 大户多空比 > 2 = 过度做多 → 反向偏空
_LS_LOW = 0.5               # 大户多空比 < 0.5 = 过度做空 → 反向偏多
_OI_CHANGE = 0.10           # 近窗口 OI(USD)变动 ≥ ±10% = 异动(情绪转折)
_OI_WINDOW = 12             # OI 异动回看窗口点数(5min 粒度 ≈ 近 1h)


# ===== 序列指标(复用 indicators 数学 · 吐整段序列 · 未预热位 = None)=====


def _sma_series(closes: list[float], period: int) -> list[float | None]:
    """逐根 SMA 序列 · 前 period-1 位未预热为 None · 之后复用 indicators._sma。"""
    out: list[float | None] = []
    for i in range(len(closes)):
        if i + 1 < period:
            out.append(None)
        else:
            # _sma 取 window[-period:],此处 window=closes[:i+1] 末 period 根即该位窗口
            out.append(_sma(closes[: i + 1], period))
    return out


def _boll_series(
    closes: list[float], period: int, k: float,
) -> list[tuple[float, float, float] | None]:
    """逐根布林带序列 (mid, upper, lower) · 未预热 None · 复用 _sma + _stdev。"""
    out: list[tuple[float, float, float] | None] = []
    for i in range(len(closes)):
        if i + 1 < period:
            out.append(None)
        else:
            window = closes[: i + 1]
            mid = _sma(window, period)
            sd = _stdev(window, period)
            out.append((mid, mid + k * sd, mid - k * sd))
    return out


def _rsi_series(closes: list[float], period: int) -> list[float | None]:
    """逐根 Wilder RSI 序列 · 逻辑与 indicators.compute_rsi 一致(同 Wilder 平滑)。

    一次遍历产全序列(避免逐根调 compute_rsi 的 O(n²) 重算)。
    前 period 位未预热为 None(需 period+1 根收盘价才有第一个 RSI)。
    """
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    def _rsi(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    # 初始均值(前 period 个 gain/loss)· 第一个 RSI 落在 closes 索引 period
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi(avg_gain, avg_loss)

    # Wilder 平滑 · gains[i] 对应 closes[i+1]
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return out


def _ema_full(values: list[float], period: int) -> list[float | None]:
    """逐根 EMA 序列 · 前 period-1 位 None · seed = 前 period 均值(同 indicators._ema 口径)。"""
    n = len(values)
    out: list[float | None] = [None] * n
    if n < period:
        return out
    alpha = 2.0 / (period + 1)
    ema = sum(values[:period]) / period
    out[period - 1] = ema
    for i in range(period, n):
        ema = alpha * values[i] + (1 - alpha) * ema
        out[i] = ema
    return out


def _macd_series(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9,
) -> list[tuple[float, float] | None]:
    """逐根 (DIF, DEA) 序列 · 未预热 None · 与 indicators.compute_macd 同口径。

    DIF = EMA_fast − EMA_slow(从 slow-1 起连续);DEA = EMA_signal(DIF)(再延迟 signal-1 起出值)。
    """
    n = len(closes)
    out: list[tuple[float, float] | None] = [None] * n
    e_fast = _ema_full(closes, fast)
    e_slow = _ema_full(closes, slow)
    dif_start = slow - 1
    dif_vals: list[float] = []
    for i in range(dif_start, n):
        ef, es = e_fast[i], e_slow[i]
        if ef is None or es is None:
            continue
        dif_vals.append(ef - es)
    if len(dif_vals) < signal:
        return out
    alpha = 2.0 / (signal + 1)
    dea = sum(dif_vals[:signal]) / signal
    out[dif_start + signal - 1] = (dif_vals[signal - 1], dea)
    for j in range(signal, len(dif_vals)):
        dea = alpha * dif_vals[j] + (1 - alpha) * dea
        out[dif_start + j] = (dif_vals[j], dea)
    return out


def _kdj_series(
    klines: list[Kline], n: int = 9, m1: int = 3, m2: int = 3,
) -> list[tuple[float, float, float] | None]:
    """逐根 (K, D, J) 序列 · 前 n-1 位 None · 与 indicators.compute_kdj 同口径(K/D 初值 50)。"""
    length = len(klines)
    out: list[tuple[float, float, float] | None] = [None] * length
    if length < n:
        return out
    highs = [float(k.high) for k in klines]
    lows = [float(k.low) for k in klines]
    closes = [float(k.close) for k in klines]
    k_val = 50.0
    d_val = 50.0
    for i in range(n - 1, length):
        hn = max(highs[i - n + 1 : i + 1])
        ln = min(lows[i - n + 1 : i + 1])
        rsv = 0.0 if hn == ln else (closes[i] - ln) / (hn - ln) * 100.0
        k_val = (m1 - 1) / m1 * k_val + 1 / m1 * rsv
        d_val = (m2 - 1) / m2 * d_val + 1 / m2 * k_val
        out[i] = (k_val, d_val, 3 * k_val - 2 * d_val)
    return out


# ===== 穿越检测(相邻两根) =====


def _crosses_up(prev_a: float, prev_b: float, cur_a: float, cur_b: float) -> bool:
    """a 上穿 b:前一根 a ≤ b 且 当前根 a > b。"""
    return prev_a <= prev_b and cur_a > cur_b


def _crosses_down(prev_a: float, prev_b: float, cur_a: float, cur_b: float) -> bool:
    """a 下穿 b:前一根 a ≥ b 且 当前根 a < b。"""
    return prev_a >= prev_b and cur_a < cur_b


# ===== 最近一根穿越判定(选股筛选器 1b 复用 · 复用上面的序列 + 穿越工具,不另算一套)=====


def latest_macd_golden_cross(klines: list[Kline]) -> bool:
    """最近一根 K 是否 MACD 金叉(DIF 上穿 DEA)· 数据不足 → False。"""
    s = _macd_series([float(k.close) for k in klines])
    if len(s) < 2 or s[-1] is None or s[-2] is None:  # noqa: PLR2004
        return False
    p_dif, p_dea = s[-2]
    c_dif, c_dea = s[-1]
    return _crosses_up(p_dif, p_dea, c_dif, c_dea)


def latest_kdj_golden_cross(klines: list[Kline]) -> bool:
    """最近一根 K 是否 KDJ 金叉(K 上穿 D)· 数据不足 → False。"""
    s = _kdj_series(klines)
    if len(s) < 2 or s[-1] is None or s[-2] is None:  # noqa: PLR2004
        return False
    p_k, p_d, _ = s[-2]
    c_k, c_d, _ = s[-1]
    return _crosses_up(p_k, p_d, c_k, c_d)


# ===== 三策略扫描器 =====


def scan_ma_cross(
    klines: list[Kline], fast: int = _MA_FAST, slow: int = _MA_SLOW,
) -> list[StrategySignal]:
    """均线金叉/死叉:MA_fast 上穿 MA_slow = buy / 下穿 = sell。"""
    closes = [float(k.close) for k in klines]
    ma_f = _sma_series(closes, fast)
    ma_s = _sma_series(closes, slow)
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        pf, ps, cf, cs = ma_f[i - 1], ma_s[i - 1], ma_f[i], ma_s[i]
        if pf is None or ps is None or cf is None or cs is None:
            continue
        # ⑤ 关键价位:信号点 MA 值(已算·透出)· ⑥ 成色:ma_cross 不做(穿越本身即信号·产品负责人定)
        levels = {f"MA{fast}": round(cf, 4), f"MA{slow}": round(cs, 4)}
        if _crosses_up(pf, ps, cf, cs):
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="buy",
                reason=f"MA{fast} 上穿 MA{slow}(金叉)", levels=levels,
            ))
        elif _crosses_down(pf, ps, cf, cs):
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="sell",
                reason=f"MA{fast} 下穿 MA{slow}(死叉)", levels=levels,
            ))
    return signals


def scan_rsi_reversal(
    klines: list[Kline],
    period: int = _RSI_PERIOD,
    oversold: float = _RSI_OVERSOLD,
    overbought: float = _RSI_OVERBOUGHT,
) -> list[StrategySignal]:
    """RSI 超卖反弹/超买回落(反弹确认式 · 拍板①):

    RSI 上穿 oversold(30)= buy(超卖后回升确认反弹);
    RSI 下穿 overbought(70)= sell(超买后回落)。
    """
    closes = [float(k.close) for k in klines]
    rsi = _rsi_series(closes, period)
    signals: list[StrategySignal] = []
    trough: float | None = None  # 当前超卖区 RSI 最低值(⑥ 成色:探底越深反弹越强)
    peak: float | None = None    # 当前超买区 RSI 最高值(⑥ 成色:冲顶越高回落越强)
    for i in range(1, len(klines)):
        prev, cur = rsi[i - 1], rsi[i]
        if prev is None or cur is None:
            continue
        # 追踪回穿前的探底/冲顶极值(给 ⑥ 成色用)
        if cur < oversold:
            trough = cur if trough is None else min(trough, cur)
        if cur > overbought:
            peak = cur if peak is None else max(peak, cur)
        # 上穿超卖线 → 反弹买点
        if prev < oversold and cur >= oversold:
            depth = round(oversold - trough, 1) if trough is not None else None
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="buy",
                reason=f"RSI 上穿 {oversold:.0f}(超卖反弹)",
                levels={"RSI": round(cur, 1), "超卖线": oversold},
                strength=depth,
                strength_note=(f"超卖深度 · RSI 探至 {trough:.0f}" if trough is not None else None),
            ))
            trough = None  # 反弹已确认 · 重置等下一轮超卖
        # 下穿超买线 → 回落卖点
        elif prev > overbought and cur <= overbought:
            height = round(peak - overbought, 1) if peak is not None else None
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="sell",
                reason=f"RSI 下穿 {overbought:.0f}(超买回落)",
                levels={"RSI": round(cur, 1), "超买线": overbought},
                strength=height,
                strength_note=(f"超买高度 · RSI 冲至 {peak:.0f}" if peak is not None else None),
            ))
            peak = None
    return signals


def scan_boll_reversion(
    klines: list[Kline], period: int = _BOLL_PERIOD, k: float = _BOLL_K,
) -> list[StrategySignal]:
    """布林带均值回归(收盘价穿越 · 拍板② · ★非突破追涨):

    收盘价下穿下轨 = buy(博回归中轨);收盘价上穿上轨 = sell。
    用收盘价 C 穿越(稳健 · 不被插针/影线误触发)。
    """
    closes = [float(k.close) for k in klines]
    boll = _boll_series(closes, period, k)
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        prev_band, cur_band = boll[i - 1], boll[i]
        if prev_band is None or cur_band is None:
            continue
        _, prev_up, prev_low = prev_band
        cur_mid, cur_up, cur_low = cur_band
        prev_c, cur_c = closes[i - 1], closes[i]
        # ⑤ 关键价位:信号点布林上/中/下轨(已算·透出)· ⑥ 成色:偏离轨道幅度(越远越极端)
        levels = {"上轨": round(cur_up, 4), "中轨": round(cur_mid, 4), "下轨": round(cur_low, 4)}
        # 收盘价下穿下轨 → 均值回归买点
        if prev_c > prev_low and cur_c <= cur_low:
            dev = (cur_low - cur_c) / cur_low if cur_low else 0.0
            signals.append(StrategySignal(
                ts=klines[i].ts, price=cur_c, kind="buy",
                reason="收盘触布林下轨(均值回归买点)", levels=levels,
                strength=round(dev, 4), strength_note=f"偏离下轨 {dev:.1%}",
            ))
        # 收盘价上穿上轨 → 均值回归卖点
        elif prev_c < prev_up and cur_c >= cur_up:
            dev = (cur_c - cur_up) / cur_up if cur_up else 0.0
            signals.append(StrategySignal(
                ts=klines[i].ts, price=cur_c, kind="sell",
                reason="收盘触布林上轨(均值回归卖点)", levels=levels,
                strength=round(dev, 4), strength_note=f"偏离上轨 {dev:.1%}",
            ))
    return signals


def scan_macd_cross(
    klines: list[Kline], fast: int = 12, slow: int = 26, signal: int = 9,
) -> list[StrategySignal]:
    """MACD 金叉/死叉(★DIF 穿 DEA · 不是均线穿越):

    DIF 上穿 DEA = buy(金叉);DIF 下穿 DEA = sell(死叉)。
    ⑤ 关键价位:DIF / DEA / 柱(=(DIF−DEA)×2)· ⑥ 成色:柱体绝对值(动能强弱)。
    """
    closes = [float(k.close) for k in klines]
    series = _macd_series(closes, fast, slow, signal)
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        prev, cur = series[i - 1], series[i]
        if prev is None or cur is None:
            continue
        pdif, pdea = prev
        cdif, cdea = cur
        hist = round((cdif - cdea) * 2, 4)
        levels = {"DIF": round(cdif, 4), "DEA": round(cdea, 4), "柱": hist}
        if _crosses_up(pdif, pdea, cdif, cdea):
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="buy",
                reason="DIF 上穿 DEA(MACD 金叉)", levels=levels,
                strength=abs(hist), strength_note=f"柱体 {hist:+.4f}",
            ))
        elif _crosses_down(pdif, pdea, cdif, cdea):
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="sell",
                reason="DIF 下穿 DEA(MACD 死叉)", levels=levels,
                strength=abs(hist), strength_note=f"柱体 {hist:+.4f}",
            ))
    return signals


def scan_kdj_cross(
    klines: list[Kline], n: int = 9, m1: int = 3, m2: int = 3,
) -> list[StrategySignal]:
    """KDJ 金叉/死叉:K 上穿 D = buy(低位 <20 更强)· K 下穿 D = sell(高位 >80 更强)。

    ⑤ 关键价位:K / D / J · ⑥ 成色:低位金叉(20−K)/ 高位死叉(K−80)· 非低/高位则 0。
    """
    series = _kdj_series(klines, n, m1, m2)
    closes = [float(k.close) for k in klines]
    signals: list[StrategySignal] = []
    for i in range(1, len(klines)):
        prev, cur = series[i - 1], series[i]
        if prev is None or cur is None:
            continue
        pk, pd, _ = prev
        ck, cd, cj = cur
        levels = {"K": round(ck, 1), "D": round(cd, 1), "J": round(cj, 1)}
        if _crosses_up(pk, pd, ck, cd):
            low = ck < 20
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="buy",
                reason="K 上穿 D(KDJ 金叉)", levels=levels,
                strength=round(max(0.0, 20 - ck), 1) if low else 0.0,
                strength_note=(f"低位金叉 · K={ck:.0f}" if low else None),
            ))
        elif _crosses_down(pk, pd, ck, cd):
            high = ck > 80
            signals.append(StrategySignal(
                ts=klines[i].ts, price=closes[i], kind="sell",
                reason="K 下穿 D(KDJ 死叉)", levels=levels,
                strength=round(max(0.0, ck - 80), 1) if high else 0.0,
                strength_note=(f"高位死叉 · K={ck:.0f}" if high else None),
            ))
    return signals


def scan_extreme(
    klines: list[Kline],
    *,
    funding_rate: float | None = None,
    oi_usd_series: list[float] | None = None,
    long_short_ratio: float | None = None,
) -> list[StrategySignal]:
    """极端信号(★仅 crypto perp · 合约情绪)· 三者任一走极端即触发,合并为一个当前态信号。

    解耦:只吃标量/序列(端点从 select_funding_rates/open_interest/long_short 提取后传入),
    不导入 crypto schema。某项为 None = 数据缺 → 该项不参与(优雅降级,不报错)。
    方向(★反向情绪 · 拥挤的一方反向):
      · 资金费率正高=多头付空头=多头拥挤→偏空(sell);负低=空头付多头=空头拥挤→偏多(buy)。
      · 大户多空比偏高=过度做多→偏空;偏低=过度做空→偏多。
      · OI 急变=情绪转折(本身不定多空):有 funding/多空比方向则随之;仅 OI 异动则逆近期价格。
    数据全不极端 → 返回空(不触发)。只在最新一根 K 标一个点(当前态信号)。
    """
    if not klines:
        return []
    closes = [float(k.close) for k in klines]
    last = klines[-1]
    reasons: list[str] = []
    levels: dict[str, float] = {}
    votes = 0  # buy=+1 / sell=-1(反向情绪净票)

    if funding_rate is not None:
        levels["资金费率%"] = round(funding_rate * 100, 4)
        if funding_rate > _FUNDING_EXTREME:
            reasons.append("资金费率正向偏高")
            votes -= 1
        elif funding_rate < -_FUNDING_EXTREME:
            reasons.append("资金费率负向偏低")
            votes += 1

    if long_short_ratio is not None:
        levels["多空比"] = round(long_short_ratio, 2)
        if long_short_ratio > _LS_HIGH:
            reasons.append("多空比偏高")
            votes -= 1
        elif long_short_ratio < _LS_LOW:
            reasons.append("多空比偏低")
            votes += 1

    if oi_usd_series and len(oi_usd_series) >= 2:
        k = min(_OI_WINDOW, len(oi_usd_series) - 1)
        base = oi_usd_series[-1 - k]
        if base > 0:
            chg = (oi_usd_series[-1] - base) / base
            levels["OI变动%"] = round(chg * 100, 1)
            if abs(chg) >= _OI_CHANGE:
                reasons.append("OI急增" if chg > 0 else "OI急减")

    if not reasons:
        return []  # 三者都不极端 → 不触发

    if votes > 0:
        kind: SignalKind = "buy"
    elif votes < 0:
        kind = "sell"
    else:
        # 仅 OI 异动(无 funding/多空比方向)→ 逆近期价格(过热反向)· 数据不足则默认 sell
        w = min(_OI_WINDOW, len(closes) - 1)
        base_c = closes[-1 - w] if w >= 1 else 0.0
        recent = (closes[-1] - base_c) / base_c if base_c else 0.0
        kind = "sell" if recent > 0 else "buy"

    reason = f"极端信号 · {' · '.join(reasons)}"[:80]
    return [
        StrategySignal(
            ts=last.ts, price=closes[-1], kind=kind, reason=reason, levels=levels,
            strength=float(len(reasons)),
            strength_note=f"{len(reasons)}/3 项走极端",
        ),
    ]


# ===== dispatcher =====
# ⚠ extreme 不入 _SCANNERS:它需合约数据(funding/oi/多空比)· 端点对 crypto perp 特判直调
#   scan_extreme(带数据);其余 5 个纯 klines 走 _SCANNERS。scan_signals 不处理 extreme。
_SCANNERS: dict[StrategyKind, Callable[[list[Kline]], list[StrategySignal]]] = {
    "ma_cross": scan_ma_cross,
    "rsi_reversal": scan_rsi_reversal,
    "boll_reversion": scan_boll_reversion,
    "macd_cross": scan_macd_cross,
    "kdj_cross": scan_kdj_cross,
}


def scan_signals(klines: list[Kline], strategy: StrategyKind) -> list[StrategySignal]:
    """按策略 key 分发扫描器 · 返回 ts 升序的信号点序列(空 K 线返回空)。

    ★ 只读纯计算 · 不下单 · 不执行 · 不打实时。strategy 非法 → ValueError(由调用方/端点兜底)。
    """
    scanner = _SCANNERS.get(strategy)
    if scanner is None:
        raise ValueError(f"未知策略:{strategy}")
    return scanner(klines)


__all__ = [
    "scan_boll_reversion",
    "scan_extreme",
    "scan_kdj_cross",
    "scan_macd_cross",
    "scan_ma_cross",
    "scan_rsi_reversal",
    "scan_signals",
]
