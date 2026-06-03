"""港股板块聚合 aggregate_hk_sectors 单测 · A2(纯函数 · 无 IO)。

验:GICS 英→中映射 · 不在 map / 空 sector → 「其他」· 成交额加权涨跌% · 领涨股 · 降序。
"""

from __future__ import annotations

from app.services.hk_sector import GICS_CN, aggregate_hk_sectors


def test_aggregate_groups_weights_leader_and_sorts() -> None:
    sector_map = {
        "00700": "Communication Services",
        "00005": "Financial Services",
        "00939": "Financial Services",
    }
    # (code, name, change_pct, amount)· 01111 不在 map → 其他
    spot = [
        ("00700", "腾讯", 2.0, 1000.0),
        ("00005", "汇丰", 1.0, 500.0),
        ("00939", "建行", -1.0, 300.0),
        ("01111", "小盘股", 5.0, 10.0),
    ]
    out = aggregate_hk_sectors(sector_map, spot)
    by = {s.name: s for s in out}

    # 通讯服务:1 只
    assert by["通讯服务"].stock_count == 1
    assert by["通讯服务"].change_pct == 2.0
    # 金融:2 只 · 成交额加权 (1*500 + -1*300)/800 = 0.25 · 领涨汇丰
    assert by["金融"].stock_count == 2
    assert by["金融"].change_pct == 0.25
    assert by["金融"].leader_name == "汇丰"
    assert by["金融"].total_amount == 800.0
    # 不在 map → 其他
    assert by["其他"].stock_count == 1
    # 按板块涨跌% 降序:其他 5.0 > 通讯服务 2.0 > 金融 0.25
    assert [s.name for s in out] == ["其他", "通讯服务", "金融"]


def test_aggregate_zero_amount_falls_back_to_simple_avg() -> None:
    sector_map = {"00001": "Technology", "00002": "Technology"}
    spot = [("00001", "A", 2.0, 0.0), ("00002", "B", 4.0, 0.0)]  # 成交额 0 → 简单均值 3.0
    out = aggregate_hk_sectors(sector_map, spot)
    assert len(out) == 1
    assert out[0].name == "科技"
    assert out[0].change_pct == 3.0


def test_empty_sector_goes_to_other() -> None:
    # sector_map 没有的 code(yfinance 没采到 / sector 空)→ 全归「其他」
    out = aggregate_hk_sectors({}, [("00700", "腾讯", 1.0, 100.0)])
    assert len(out) == 1
    assert out[0].name == "其他"


def test_gics_cn_covers_11_sectors() -> None:
    # GICS 11 大类中文映射齐全(别漏某类显示英文)
    assert len(GICS_CN) == 11
    assert GICS_CN["Technology"] == "科技"
    assert GICS_CN["Financial Services"] == "金融"
    assert "其他" not in GICS_CN.values()  # 「其他」是兜底常量,不在映射表里
