"""布林做T信号接口 /api/v1/crypto/boll-scan 单测(做T A-1)。

★只读 Redis 快照 · 验:有快照→列表 / 无快照→空列表不报错 / 筛选(bias/transition)生效 /
顶层 disclaimer 存在 / ★措辞红线无买卖祈使词 / bias 仅 偏多/偏空/中性。
快照行用真 to_snapshot_row 构造 → 同时坐实 schema 键对齐(BollScanItem extra=forbid)。
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from httpx import AsyncClient

from app.services.ai.boll_state import BollSnapshot, BollState, to_snapshot_row


class _FakeRedis:
    def __init__(self, value: str | None) -> None:
        self._value = value

    async def get(self, _key: str) -> str | None:
        return self._value


def _snapshot_json() -> str:
    btc = BollSnapshot(
        state=BollState.BREAKOUT_UP, bias="偏多", pct_b=0.85, bandwidth=0.04,
        zone="upper", close=68500, mid=67200, upper=68800, lower=65600,
    )
    eth = BollSnapshot(
        state=BollState.TREND_DOWN, bias="偏空", pct_b=0.18, bandwidth=0.05,
        zone="lower", close=3500, mid=3600, upper=3720, lower=3480,
    )
    rows = [
        to_snapshot_row(
            "BTCUSDT", btc, change_pct_24h=5.2, funding_rate=0.0091,
            transition=True, prev_state="range",
        ),
        to_snapshot_row(
            "ETHUSDT", eth, change_pct_24h=-3.1, funding_rate=-0.0042,
            transition=False, prev_state="trend_down",
        ),
    ]
    return json.dumps({"as_of": "2026-06-22T08:00:00+00:00", "items": rows}, ensure_ascii=False)


def _patch_redis(monkeypatch: object, value: str | None) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.api.v1.crypto.get_redis", AsyncMock(return_value=_FakeRedis(value)),
    )


async def test_returns_list_with_disclaimer(client: AsyncClient, monkeypatch: object) -> None:
    _patch_redis(monkeypatch, _snapshot_json())
    resp = await client.get("/api/v1/crypto/boll-scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    # ★顶层免责存在且含锁死红线口径
    assert "不构成投资建议" in body["disclaimer"]
    # ★措辞红线:信号数据(items)无买卖祈使/预测词(disclaimer 的「非建议/不构成投资建议」
    #   含「建议」属正常免责语,故只查 items)
    blob = json.dumps(body["items"], ensure_ascii=False)
    for w in ("买入", "卖出", "抄底", "逃顶", "止损", "止盈", "目标价", "建议"):
        assert w not in blob, f"信号数据不得含买卖词:{w}"
    # bias 仅 偏多/偏空/中性
    for it in body["items"]:
        assert it["bias"] in ("偏多", "偏空", "中性")


async def test_empty_when_no_snapshot(client: AsyncClient, monkeypatch: object) -> None:
    # M1 未落首份快照 → 空列表 + as_of=null · 不报错
    _patch_redis(monkeypatch, None)
    resp = await client.get("/api/v1/crypto/boll-scan")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 0
    assert body["items"] == []
    assert body["as_of"] is None
    assert "不构成投资建议" in body["disclaimer"]  # 空也带免责


async def test_filter_bias_long(client: AsyncClient, monkeypatch: object) -> None:
    _patch_redis(monkeypatch, _snapshot_json())
    resp = await client.get("/api/v1/crypto/boll-scan?bias=long")
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "BTCUSDT"
    assert body["items"][0]["bias"] == "偏多"


async def test_filter_transition_true(client: AsyncClient, monkeypatch: object) -> None:
    _patch_redis(monkeypatch, _snapshot_json())
    resp = await client.get("/api/v1/crypto/boll-scan?transition=true")
    body = resp.json()
    assert body["count"] == 1
    it = body["items"][0]
    assert it["transition"] is True
    # transition_from = prev_state "range" 的中文口诀
    assert it["transition_from"] == "三线走平·震荡结构"


async def test_stale_snapshot_does_not_500(client: AsyncClient, monkeypatch: object) -> None:
    # ★部署过渡窗口:旧格式快照(A-1 · 无 zone_label/bandwidth)→ 跳过坏行,返回 200 空列表,绝不 500
    old_row = {
        "symbol": "BTCUSDT", "state": "range", "state_label": "三线走平·震荡结构",
        "bias": "中性", "pct_b": 0.5, "close": 68500, "mid": 67000,
        "upper": 69000, "lower": 65000, "change_pct_24h": 2.1,
        "transition": False, "transition_from": None,
    }
    stale = json.dumps({"as_of": "2026-06-22T10:00:00+00:00", "count": 1, "items": [old_row]})
    _patch_redis(monkeypatch, stale)
    resp = await client.get("/api/v1/crypto/boll-scan")
    assert resp.status_code == 200  # ★不 500
    body = resp.json()
    assert body["count"] == 0  # 旧行被跳过(待下一轮 beat 刷新)
    assert "不构成投资建议" in body["disclaimer"]
