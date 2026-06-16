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
    """收款信息(前端跳转 OxaPay 托管收款页)· external_id 给前端轮询订单态用。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    payment_url: str        # OxaPay 托管收款页(前端跳转 · 用户在此自选链/币付款)
    external_id: str        # 我方订单号(不可猜)
    period: str


class OrderStatusOut(BaseModel):
    """订单状态(前端到账轮询用)· pending → paid/expired。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    external_id: str
    status: str             # pending|paid|expired
    period: str
