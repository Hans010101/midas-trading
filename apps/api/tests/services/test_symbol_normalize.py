"""#296 改动二 · 标的模糊识别(只两档:大小写无关 + 简称/缺斜杠)单测。

normalize_symbol 是纯字符串函数 · 不打 DB/网络 · 存在性校验在 router 用 quote_price(另测)。
"""

from __future__ import annotations

import pytest

from app.services.bot.order import normalize_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("btc", "BTC/USDT"),       # 简称 + 小写
        ("BTC", "BTC/USDT"),
        ("Btc", "BTC/USDT"),       # 大小写无关
        ("btcusdt", "BTC/USDT"),   # 缺斜杠
        ("BTCUSDT", "BTC/USDT"),
        ("btc/usdt", "BTC/USDT"),  # 全写
        ("BTC/USDT", "BTC/USDT"),
        (" eth ", "ETH/USDT"),     # 去空格 + 补 USDT
        ("ethusdc", "ETH/USDC"),   # 非 USDT quote 不强改
        ("sol", "SOL/USDT"),
    ],
)
def test_crypto_normalize(raw: str, expected: str) -> None:
    assert normalize_symbol("crypto", raw) == expected


def test_us_uppercase() -> None:
    assert normalize_symbol("us", "nvda") == "NVDA"
    assert normalize_symbol("us", " aapl ") == "AAPL"


def test_cn_strip_digits() -> None:
    assert normalize_symbol("cn", " 600519 ") == "600519"


def test_empty_returns_empty() -> None:
    assert normalize_symbol("crypto", "  ") == ""
    assert normalize_symbol("us", "") == ""
