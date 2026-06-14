"""支付 Pydantic 契约(Phase 2a 刀1 · 会员订阅收款)。

🔴 红线:订阅费非交易 · 金额字段全 string(避免 JS 浮点损失,与房规一致)。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

Period = Literal["month", "quarter", "year"]


class CreateOrderIn(BaseModel):
    """POST /payment/order 入参 · 选周期(pro 档)。"""

    model_config = ConfigDict(extra="forbid")

    period: Period


class CreateOrderOut(BaseModel):
    """收款信息(前端展示二维码/地址 + 应付额)· external_id 给前端轮询订单态用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    address: str            # Bcon 收款地址(USDT/BSC)
    payment_amount: str     # 用户应付精确额(Bcon 返回)
    external_id: str        # 我方订单号(不可猜)
    period: str
