"""市场 Pydantic 契约的边界测试。"""

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.schemas.market import Kline, KlineResponse, SymbolMeta

_TS = datetime(2026, 5, 19, 8, 0, 0, tzinfo=UTC)


class TestKline:
    def test_valid(self) -> None:
        k = Kline(ts=_TS, open=100.0, high=110.0, low=95.0, close=105.0, volume=1234.0, amount=12.5)
        assert k.open == 100.0
        assert k.amount == 12.5

    def test_amount_optional(self) -> None:
        k = Kline(ts=_TS, open=100.0, high=110.0, low=95.0, close=105.0, volume=1234.0)
        assert k.amount is None

    def test_naive_datetime_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone"):
            Kline(
                ts=datetime(2026, 5, 19, 8, 0, 0),  # naive  # noqa: DTZ001
                open=100.0,
                high=110.0,
                low=95.0,
                close=105.0,
                volume=1234.0,
            )

    def test_price_non_positive_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Kline(ts=_TS, open=0.0, high=110.0, low=95.0, close=105.0, volume=0.0)

    def test_negative_volume_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Kline(ts=_TS, open=100.0, high=110.0, low=95.0, close=105.0, volume=-1.0)

    def test_open_above_high_rejected(self) -> None:
        with pytest.raises(ValidationError, match="open"):
            Kline(ts=_TS, open=120.0, high=110.0, low=95.0, close=105.0, volume=10.0)

    def test_close_below_low_rejected(self) -> None:
        with pytest.raises(ValidationError, match="close"):
            Kline(ts=_TS, open=100.0, high=110.0, low=95.0, close=80.0, volume=10.0)

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError, match="extra"):
            Kline(
                ts=_TS,
                open=100.0,
                high=110.0,
                low=95.0,
                close=105.0,
                volume=10.0,
                extra_garbage="x",  # type: ignore[call-arg]
            )

    def test_frozen(self) -> None:
        k = Kline(ts=_TS, open=100.0, high=110.0, low=95.0, close=105.0, volume=10.0)
        with pytest.raises(ValidationError):
            k.open = 999.0  # type: ignore[misc]


class TestKlineResponse:
    def test_valid(self) -> None:
        items = [
            Kline(ts=_TS, open=100.0, high=110.0, low=95.0, close=105.0, volume=10.0),
        ]
        resp = KlineResponse(symbol="600519", market="cn", period="1d", items=items)
        assert resp.symbol == "600519"
        assert len(resp.items) == 1

    def test_invalid_market(self) -> None:
        # 用一个确实不在 Market Literal 里的值(hk 自 feat/hk-phase1-config 起已是合法市场)
        with pytest.raises(ValidationError):
            KlineResponse(symbol="600519", market="xx", period="1d", items=[])  # type: ignore[arg-type]

    def test_invalid_period(self) -> None:
        with pytest.raises(ValidationError):
            KlineResponse(symbol="600519", market="cn", period="2h", items=[])  # type: ignore[arg-type]


class TestSymbolMeta:
    def test_valid(self) -> None:
        m = SymbolMeta(
            symbol="600519",
            market="cn",
            name="贵州茅台",
            name_en="Kweichow Moutai",
            listed_date=date(2001, 8, 27),
            is_active=True,
            updated_at=_TS,
        )
        assert m.symbol == "600519"
        assert m.name_en == "Kweichow Moutai"

    def test_optional_fields(self) -> None:
        m = SymbolMeta(symbol="BTC/USDT", market="crypto", name="Bitcoin", updated_at=_TS)
        assert m.name_en == ""
        assert m.listed_date is None
        assert m.is_active is True
