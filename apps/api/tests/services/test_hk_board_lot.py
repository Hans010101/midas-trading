"""港股 board lot 服务单测 · resolve_hk_board_lot(lot 表优先 + 18 种子兜底 + None)。

★ 红线:表无且种子无 → None(不进下单池 · 宁缺毋滥)· 现有 18 种子兜底不回归。
mock db(不连 PG · docker 崩也能跑)· fetch_hkex_board_lots(网络)由 A1 生产实测 + 本地真跑覆盖。
"""

from __future__ import annotations

import pytest

from app.services.hk_board_lot import resolve_hk_board_lot


class _FakeDb:
    """mock AsyncSession · scalar 返预设 lot(模拟 lot 表命中=int / 未命中=None)。"""

    def __init__(self, table_lot: int | None) -> None:
        self._lot = table_lot

    async def scalar(self, _stmt: object) -> int | None:  # noqa: ANN401 · mock 签名
        return self._lot


@pytest.mark.asyncio
async def test_resolve_table_hit_uses_table() -> None:
    # lot 表命中 → 用表值(worker 采的 HKEX 官方 · 可能 ≠ 种子 · 全市场 ~2406)
    db = _FakeDb(table_lot=500)
    assert await resolve_hk_board_lot(db, "01234") == 500  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_resolve_table_miss_falls_back_to_seed() -> None:
    # 表无(冷启动/未采)→ 回退 hk_pool 18 种子(00700=100 · BYD 01211=100 已修)
    db = _FakeDb(table_lot=None)
    assert await resolve_hk_board_lot(db, "00700") == 100  # type: ignore[arg-type]
    assert await resolve_hk_board_lot(db, "01211") == 100  # type: ignore[arg-type] · BYD 种子已修 100
    assert await resolve_hk_board_lot(db, "00005") == 400  # type: ignore[arg-type] · 汇丰种子


@pytest.mark.asyncio
async def test_resolve_both_miss_returns_none() -> None:
    # 表无 + 不在 18 种子 → None(★红线:不进下单池,不可下单 · 宁缺毋滥)
    db = _FakeDb(table_lot=None)
    assert await resolve_hk_board_lot(db, "99999") is None  # type: ignore[arg-type]
