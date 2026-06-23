"""单币布林结构接口 /api/v1/crypto/boll-structure/{symbol} 单测(做T B-1)。

★验:① 快照命中→source=snapshot 零重算 ② 长尾→现算 source=computed ③ 数据不足→
available=false 不报错 ④ disclaimer + layer 层级标注 + bias 仅偏多/偏空/中性。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.api.deps import get_clickhouse
from app.main import app
from app.schemas.crypto import Ticker24h
from app.schemas.market import Kline
from app.services.ai.boll_state import BollSnapshot, BollState, to_snapshot_row


def _patch_redis(monkeypatch: object, value: str | None) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.api.v1.crypto.get_redis", AsyncMock(return_value=_FakeRedis(value)),
    )


class _FakeRedis:
    def __init__(self, value: str | None) -> None:
        self._value = value

    async def get(self, _key: str) -> str | None:
        return self._value


class _FakeCH:
    """假 ClickHouseClient · select_kline 返预置 K线 · _client 占位(crypto 函数被 monkeypatch)。"""

    def __init__(self, klines: list[Kline]) -> None:
        self._klines = klines
        self._client = object()

    async def select_kline(self, **_kwargs: object) -> list[Kline]:
        return self._klines


def _klines(closes: list[float]) -> list[Kline]:
    base = datetime(2026, 6, 22, tzinfo=UTC)
    return [
        Kline(ts=base + timedelta(minutes=15 * i), open=c, high=c * 1.001,
              low=c * 0.999, close=c, volume=1.0)
        for i, c in enumerate(closes)
    ]


def _snapshot_with(symbol: str) -> str:
    snap = BollSnapshot(
        state=BollState.BREAKOUT_UP, bias="偏多", pct_b=0.85, bandwidth=0.04,
        zone="upper", close=68500, mid=67200, upper=68800, lower=65600,
    )
    row = to_snapshot_row(symbol, snap, change_pct_24h=5.2, funding_rate=0.0091,
                          transition=True, prev_state="range")
    return json.dumps({"as_of": "2026-06-22T12:03:00+00:00", "items": [row]})


def _use_fake_ch(klines: list[Kline]) -> None:
    app.dependency_overrides[get_clickhouse] = lambda: _FakeCH(klines)


async def test_snapshot_hit_zero_recompute(client: AsyncClient, monkeypatch: object) -> None:
    # ★Top150 命中快照 → source=snapshot(零重算)· 直接返回那条
    _patch_redis(monkeypatch, _snapshot_with("BTCUSDT"))
    _use_fake_ch([])  # ClickHouseDep 需可解析(快照命中路径不会真用 ch)
    try:
        resp = await client.get("/api/v1/crypto/boll-structure/BTCUSDT")
    finally:
        app.dependency_overrides.pop(get_clickhouse, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["source"] == "snapshot"  # ★复用快照,非现算
    assert body["layer"] == "布林结构"
    assert "不构成投资建议" in body["disclaimer"]
    assert body["item"]["symbol"] == "BTCUSDT"
    assert body["item"]["bias"] in ("偏多", "偏空", "中性")
    # ★措辞红线:item 无买卖词
    blob = json.dumps(body["item"], ensure_ascii=False)
    for w in ("买入", "卖出", "抄底", "止损", "目标价", "建议"):
        assert w not in blob


async def test_long_tail_computed(client: AsyncClient, monkeypatch: object) -> None:
    # 不在快照 → 按需现算 → source=computed(★长尾兜底)
    _patch_redis(monkeypatch, json.dumps({"as_of": None, "items": []}))
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.api.v1.crypto.select_tickers_by_symbols",
        AsyncMock(return_value={"TNSR/USDT": Ticker24h(
            symbol="TNSR/USDT", instrument="perp", ts=datetime.now(tz=UTC),
            last_price=0.41, change_pct_24h=3.1, high_24h=0.43, low_24h=0.40,
            volume_24h=1.0, quote_volume_24h=1.0)}),
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.api.v1.crypto.select_latest_funding_rates",
        AsyncMock(return_value={"TNSRUSDT": 0.0001}),
    )
    _use_fake_ch(_klines([100 + i * 0.6 for i in range(28)]))  # 28 根 → classify 出结构
    try:
        resp = await client.get("/api/v1/crypto/boll-structure/TNSRUSDT")
    finally:
        app.dependency_overrides.pop(get_clickhouse, None)
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["source"] == "computed"  # ★长尾现算
    assert body["item"]["bias"] in ("偏多", "偏空", "中性")
    assert "不构成投资建议" in body["disclaimer"]


async def test_insufficient_data_degrades(client: AsyncClient, monkeypatch: object) -> None:
    # 不在快照 + K线不足 24 根 → available=false · source=none · ★不报错(200)
    _patch_redis(monkeypatch, json.dumps({"as_of": None, "items": []}))
    _use_fake_ch(_klines([100.0] * 5))  # 仅 5 根 → classify None
    try:
        resp = await client.get("/api/v1/crypto/boll-structure/NOBODYUSDT")
    finally:
        app.dependency_overrides.pop(get_clickhouse, None)
    assert resp.status_code == 200  # ★不报错
    body = resp.json()
    assert body["available"] is False
    assert body["source"] == "none"
    assert body["item"] is None
    assert "不构成投资建议" in body["disclaimer"]  # 不可用也带免责
