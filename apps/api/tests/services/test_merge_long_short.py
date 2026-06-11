"""_merge_long_short 单测(刀C)· global left-join 语义 + top 三件套交集零回归。

纯函数 · 构造上游 dict 列表直接测 · 不需要网络/PG/CH。
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.data_sources.binance_futures_source import _merge_long_short

TS1 = 1781184600000
TS2 = 1781185500000


def _row(ts: int, long: str = "0.6", short: str = "0.4", ratio: str = "1.5") -> dict[str, Any]:
    return {"timestamp": ts, "longAccount": long, "shortAccount": short, "longShortRatio": ratio}


def _taker(ts: int) -> dict[str, Any]:
    return {"timestamp": ts, "buyVol": "100", "sellVol": "80", "buySellRatio": "1.25"}


def test_global_present_fills_all_four() -> None:
    """① top 三件套全有 + global 有 → 4 套指标都填。"""
    out = _merge_long_short(
        account=[_row(TS1)], position=[_row(TS1)], taker=[_taker(TS1)],
        global_account=[_row(TS1, long="0.61", short="0.39", ratio="1.56")],
        symbol="BTCUSDT",
    )
    assert len(out) == 1
    r = out[0]
    assert r.ts == datetime.fromtimestamp(TS1 / 1000, tz=UTC)
    assert r.top_account_ratio == 1.5
    assert r.global_account_long == 0.61
    assert r.global_account_short == 0.39
    assert r.global_account_ratio == 1.56


def test_global_missing_keeps_row_intact() -> None:
    """② ★ 交集回归:top 全有 + global 缺该 ts → top 三套正常 · global 留 0 · 不丢整行。"""
    out = _merge_long_short(
        account=[_row(TS1), _row(TS2)],
        position=[_row(TS1), _row(TS2)],
        taker=[_taker(TS1), _taker(TS2)],
        global_account=[_row(TS2, ratio="1.6")],  # 只有 TS2 有 global
        symbol="BTCUSDT",
    )
    assert len(out) == 2  # ★ TS1 没 global 也不丢
    by_ts = {int(r.ts.timestamp() * 1000): r for r in out}
    assert by_ts[TS1].top_account_ratio == 1.5  # top 主干零回归
    assert by_ts[TS1].global_account_ratio == 0.0  # 未采哨兵
    assert by_ts[TS2].global_account_ratio == 1.6


def test_global_only_ts_not_included() -> None:
    """③ global 有但某 top 缺 → 照原交集规则跳过(global 不能让缺 top 的行混进来)。"""
    out = _merge_long_short(
        account=[_row(TS1)],
        position=[_row(TS1)],
        taker=[],  # taker 缺 TS1 → 交集为空
        global_account=[_row(TS1)],
        symbol="BTCUSDT",
    )
    assert out == []


def test_global_omitted_backward_compatible() -> None:
    """④ 不传 global(老调用形态)→ 行为与改造前一致 · global 列全 0。"""
    out = _merge_long_short(
        account=[_row(TS1)], position=[_row(TS1)], taker=[_taker(TS1)], symbol="BTCUSDT",
    )
    assert len(out) == 1
    assert out[0].global_account_ratio == 0.0


def test_global_dirty_row_only_drops_global_columns() -> None:
    """⑤ global 单点脏数据(缺字段)→ 只丢 global 三列(留 0)· 不丢整行。"""
    dirty = {"timestamp": TS1, "longAccount": "0.6"}  # 缺 shortAccount/longShortRatio
    out = _merge_long_short(
        account=[_row(TS1)], position=[_row(TS1)], taker=[_taker(TS1)],
        global_account=[dirty], symbol="BTCUSDT",
    )
    assert len(out) == 1
    assert out[0].top_account_ratio == 1.5
    assert out[0].global_account_ratio == 0.0
