"""app.core.formatting 单元测试 · 价格动态精度 + <1 去尾零(金额精度收尾调整)。

锁死规格(产品定调):
- 价格按数量级动态小数位:≥1000→0 · ≥100<1000→1 · ≥1<100→2 · <1→最多 8 位且去尾零。
- 边界归属明确(1000→0 / 100→1 / 1→2)。
本测试是 price_decimals / format_price_number 的单一事实源守卫(改规则必先改这里)。
"""

from __future__ import annotations

import pytest

from app.core.formatting import format_price_number, price_decimals


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # ≥1000 → 0 位(含边界 1000)
        (1000.0, 0),
        (95234.5, 0),
        # ≥100 <1000 → 1 位(含边界 100)
        (999.9, 1),
        (523.4, 1),
        (100.0, 1),
        # ≥1 <100 → 2 位(含边界 1)
        (99.99, 2),
        (12.35, 2),
        (1.0, 2),
        # <1 → 8 位
        (0.9999, 8),
        (0.00012345, 8),
        (0.0, 8),
    ],
)
def test_price_decimals_ranges_and_boundaries(value: float, expected: int) -> None:
    assert price_decimals(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # ≥1 各档:千分位 + 定位小数,【不去零】
        (95234.0, "95,234"),
        (1000.0, "1,000"),
        (523.4, "523.4"),
        (100.0, "100.0"),
        (12.35, "12.35"),
        (1.0, "1.00"),
        # <1 档:最多 8 位、【去尾零】(0.5 入参即覆盖 0.500000 —— 同一个 float;
        # 去尾零发生在格式化层 f"{0.5:.8f}"="0.50000000" → "0.5")
        (0.5, "0.5"),
        (0.1, "0.1"),
        (0.25, "0.25"),
        (0.00012345, "0.00012345"),  # 完整精度不受影响
        (0.0001234, "0.0001234"),
    ],
)
def test_format_price_number(value: float, expected: str) -> None:
    assert format_price_number(value) == expected
