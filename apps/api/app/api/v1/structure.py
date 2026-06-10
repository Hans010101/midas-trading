"""市场结构快照路由 · /api/v1/structure · 结构分析助手第1刀(数据层)。

- GET /snapshot/{symbol} · authed · 7 因子结构快照(USDT 永续 · 只读 CH)。
  本刀裸暴露快照供验证;第2刀 LLM 诊断端点复用同一 service 层。

🔴 红线:纯客观结构数据(多空比/OI/资金费/基差/情绪)—— 非价格预测 · 不下单 ·
   不撮合 · 只读 ClickHouse。window 字段强制携带数据口径(TTL 约束产品化)。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path

from app.api.deps import ClickHouseDep, CurrentUserDep
from app.schemas.structure import StructureSnapshot
from app.services.structure.snapshot import get_structure_snapshot

router = APIRouter(prefix="/structure", tags=["structure"])


@router.get(
    "/snapshot/{symbol}",
    response_model=StructureSnapshot,
    summary="7 因子结构快照(USDT 永续 · 缓存 1h/6h 分桶)",
    description=(
        "大户账户/持仓多空比 + taker 主动买卖(24h)· OI 水平与 24h 变化 · "
        "资金费率(近 7d)· 基差(premium 表仅存 7d)· FGI+BTC dominance(全市场)。"
        "单因子无数据返 null 不阻塞;核心因子表 60 天滚动 TTL,window 即数据口径。"
    ),
)
async def get_snapshot(
    ch: ClickHouseDep,
    current_user: CurrentUserDep,  # noqa: ARG001 — authed-only 门禁(快照本身不分用户)
    symbol: Annotated[str, Path(min_length=3, examples=["BTCUSDT"])],
) -> StructureSnapshot:
    # 房规:select_* 读层收裸 AsyncClient(同 crypto.py 各端点)
    return await get_structure_snapshot(ch._client, symbol)  # noqa: SLF001
