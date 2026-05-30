"""全球指标概览 · 配置 + schema 一致性离线测试(ADR 0035 阶段 A)。

不打网络 / 不连 CH:只校验 symbol 清单、分类、单位、schema 约束的内部一致性。
catch 的真实问题:category 拼错、unit 与前端 QuoteUnit 不符、symbol 重复、
crypto 漏进顺序表、地区码空串等。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.overview import OverviewQuote
from app.services.global_overview_config import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CRYPTO_NAME,
    CRYPTO_OVERVIEW,
    GLOBAL_OVERVIEW_YF,
    OVERVIEW_SYMBOL_ORDER,
)

# 前端 components/market-home/index-card.tsx 的 QuoteUnit 联合类型 · 必须保持同步
_FRONTEND_QUOTE_UNITS = {"point", "price", "rate", "yield_pct"}


class TestConfigConsistency:
    def test_first_batch_counts(self) -> None:
        # 拍板首批:8 指数 + 5 商品 + 4 外汇 + 3 债券 = 20 个 yfinance + 2 加密
        assert len(GLOBAL_OVERVIEW_YF) == 20
        assert len(CRYPTO_OVERVIEW) == 2
        by_cat = dict.fromkeys(CATEGORY_ORDER, 0)
        for _sym, _name, _region, category, _unit in GLOBAL_OVERVIEW_YF:
            by_cat[category] += 1
        assert by_cat == {
            "index": 8,
            "commodity": 5,
            "forex": 4,
            "bond": 3,
            "crypto": 0,  # 加密走 CRYPTO_OVERVIEW · 不在 yfinance 表
        }

    def test_no_duplicate_symbols(self) -> None:
        yf_syms = [s for s, *_ in GLOBAL_OVERVIEW_YF]
        crypto_syms = [s for s, _ in CRYPTO_OVERVIEW]
        all_syms = yf_syms + crypto_syms
        assert len(all_syms) == len(set(all_syms)), "概览 symbol 不允许重复"

    def test_every_category_known_and_ordered(self) -> None:
        # 每个 yfinance 条目的 category 必须在标签表 + 顺序表里
        for sym, _name, _region, category, _unit in GLOBAL_OVERVIEW_YF:
            assert category in CATEGORY_LABELS, f"{sym} 的 category={category} 缺标签"
            assert category in CATEGORY_ORDER, f"{sym} 的 category={category} 缺顺序"
        # CATEGORY_ORDER 与 CATEGORY_LABELS 键集一致
        assert set(CATEGORY_ORDER) == set(CATEGORY_LABELS)

    def test_units_match_frontend(self) -> None:
        # 后端配的 unit 必须落在前端 QuoteUnit 联合类型内(否则前端格式化会错)
        for sym, _name, _region, _category, unit in GLOBAL_OVERVIEW_YF:
            assert unit in _FRONTEND_QUOTE_UNITS, f"{sym} 的 unit={unit} 前端不认识"

    def test_region_codes_non_empty(self) -> None:
        # 地区码非空(阶段 B 地图定位键)· 但绝不能是交易 Market 的语义混淆
        for sym, _name, region, _category, _unit in GLOBAL_OVERVIEW_YF:
            assert region, f"{sym} 地区码为空"
            assert region.strip(), f"{sym} 地区码全空白"

    def test_bond_uses_yield_pct(self) -> None:
        # 债券收益率口径 · 拍板③:显示百分比、涨跌用 bp → unit 必须 yield_pct
        bonds = [t for t in GLOBAL_OVERVIEW_YF if t[3] == "bond"]
        assert bonds, "应有债券条目"
        for sym, _name, _region, _category, unit in bonds:
            assert unit == "yield_pct", f"债券 {sym} 单位应为 yield_pct"

    def test_symbol_order_covers_all(self) -> None:
        # 顺序表覆盖全部 symbol(yfinance + 加密)· 缺了会 fallback 到 9999 乱序
        for sym, *_ in GLOBAL_OVERVIEW_YF:
            assert sym in OVERVIEW_SYMBOL_ORDER
        for sym, _name in CRYPTO_OVERVIEW:
            assert sym in OVERVIEW_SYMBOL_ORDER

    def test_crypto_name_map(self) -> None:
        assert CRYPTO_NAME == {"BTC/USDT": "比特币", "ETH/USDT": "以太坊"}


class TestOverviewQuoteSchema:
    def _valid_kwargs(self) -> dict[str, object]:
        return {
            "market": "us",
            "symbol": "^GSPC",
            "name": "标普500",
            "category": "index",
            "unit": "point",
            "ts": "2026-05-30T12:00:00+00:00",
            "last_point": 7580.06,
            "prev_close": 7563.5,
            "change_point": 16.56,
            "change_pct": 0.22,
        }

    def test_valid(self) -> None:
        q = OverviewQuote(**self._valid_kwargs())
        assert q.symbol == "^GSPC"
        assert q.category == "index"

    def test_naive_ts_rejected(self) -> None:
        # AwareDatetime · 必须带时区(项目铁律:CH 永远 tz-aware)
        kw = self._valid_kwargs()
        kw["ts"] = "2026-05-30T12:00:00"  # naive
        with pytest.raises(ValidationError):
            OverviewQuote(**kw)

    def test_last_point_must_be_positive(self) -> None:
        kw = self._valid_kwargs()
        kw["last_point"] = 0
        with pytest.raises(ValidationError):
            OverviewQuote(**kw)

    def test_extra_field_forbidden(self) -> None:
        kw = self._valid_kwargs()
        kw["wallet_id"] = "x"  # 概览不可交易 · 绝不接受交易维度字段
        with pytest.raises(ValidationError):
            OverviewQuote(**kw)

    def test_empty_market_rejected(self) -> None:
        kw = self._valid_kwargs()
        kw["market"] = ""
        with pytest.raises(ValidationError):
            OverviewQuote(**kw)
