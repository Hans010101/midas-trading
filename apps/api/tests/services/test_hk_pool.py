"""港股策展池 + 每手股数(board lot)单测(阶段一 P1-2 · 种子值结构)。

只验结构可读 + 代码规范化 + lot 查询;不接数据 / 不下单(种子值待核 HKEX)。
"""

from __future__ import annotations

from app.services.hk_pool import (
    HK_LOT_SIZE,
    HK_POOL,
    HK_POOL_META,
    HK_POOL_SYMBOLS,
    hk_lot_size,
    normalize_hk_code,
)

_MIN_POOL = 18


def test_pool_non_empty_and_consistent() -> None:
    assert len(HK_POOL) >= _MIN_POOL
    # 派生集合与池一致(无重复 / 无遗漏)
    assert len(HK_POOL_SYMBOLS) == len(HK_POOL)
    assert len(set(HK_POOL_SYMBOLS)) == len(HK_POOL_SYMBOLS)
    assert set(HK_LOT_SIZE) == set(HK_POOL_SYMBOLS)
    assert set(HK_POOL_META) == set(HK_POOL_SYMBOLS)


def test_codes_are_5_digit() -> None:
    for sym in HK_POOL_SYMBOLS:
        assert len(sym) == 5
        assert sym.isdigit()


def test_lot_sizes_positive_int() -> None:
    for lot in HK_LOT_SIZE.values():
        assert isinstance(lot, int)
        assert lot > 0


def test_seed_values_present() -> None:
    # 腾讯 00700 种子每手 100(★待核 HKEX)
    assert HK_LOT_SIZE["00700"] == 100
    assert HK_POOL_META["00700"][0] == "腾讯控股"


def test_normalize_hk_code() -> None:
    assert normalize_hk_code("700") == "00700"
    assert normalize_hk_code("0700") == "00700"
    assert normalize_hk_code("00700") == "00700"
    assert normalize_hk_code("00700.HK") == "00700"
    assert normalize_hk_code(" 00700 ") == "00700"
    assert normalize_hk_code("9988") == "09988"


def test_hk_lot_size_lookup() -> None:
    assert hk_lot_size("700") == 100         # 规范化后命中
    assert hk_lot_size("00700.HK") == 100
    assert hk_lot_size("99999") is None      # 不在池 → None(暂不可下单 · 决策②兜底)


def test_confirmed_board_lots_hkex_2026_06_02() -> None:
    """18 只策展池每手股数 · 已逐一核港交所官方(2026-06-02)。

    注:BYD 01211 原种子手核填 500 是错的(stale 源),HKEX 官方 ListOfSecurities +
    now.com 三角验证 = 100,已修正(其余 17 只与种子一致)。

    ★ 阶段三单元3 下单按手取整依赖这些值准确。
    ⚠️ 港交所 2025-12 在咨询「精简每手买卖单位框架」· 若 lot 调整(尤其汇丰 400 不在拟定
       标准集 {1,50,100,500,1000,2000,5000,10000})· 改这里 + fees.py + 重核官方。
    """
    expected = {
        "00700": 100, "09988": 100, "03690": 100, "01810": 200,
        "09618": 50, "01024": 100, "09999": 100, "09888": 50,
        "00388": 100, "01299": 200, "00005": 400, "00939": 1000,
        "01398": 1000, "02318": 500, "00941": 500, "01211": 100,
        "02015": 100, "09868": 100,
    }
    assert set(expected) == set(HK_POOL_SYMBOLS), "策展池应与已核清单一致(18 只)"
    for sym, lot in expected.items():
        assert HK_LOT_SIZE[sym] == lot, f"{sym} 每手应为 {lot}(已核 HKEX)"
