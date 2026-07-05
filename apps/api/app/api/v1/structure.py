"""市场结构快照路由 · /api/v1/structure · 结构分析助手第1刀(数据层)。

- GET /snapshot/{symbol} · authed · 7 因子结构快照(USDT 永续 · 只读 CH)。
  本刀裸暴露快照供验证;第2刀 LLM 诊断端点复用同一 service 层。

🔴 红线:纯客观结构数据(多空比/OI/资金费/基差/情绪)—— 非价格预测 · 不下单 ·
   不撮合 · 只读 ClickHouse。window 字段强制携带数据口径(TTL 约束产品化)。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.deps import ClickHouseDep, CurrentUserDep, RequestLangDep
from app.models.user import User
from app.schemas.structure import DiagnoseRequest, StructureDiagnosis, StructureSnapshot
from app.services.i18n import translate
from app.services.membership import make_quota_consumer, require_quota
from app.services.structure.snapshot import get_structure_snapshot
from app.services.structure.workflow import NoFactorDataError, get_structure_diagnosis

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


@router.post(
    "/diagnose",
    response_model=StructureDiagnosis,
    summary="自然语言结构诊断(7 因子 · 非价格预测 · 缓存按意图+6h 桶)",
    description=(
        "问题→意图归一(5 类枚举)→因子快照→单次 LLM 结构化诊断→祈使句合规改写。"
        "🔴 只描述当前结构状态(拥挤/杠杆/费率/基差/情绪),不输出点位/目标价/方向概率/买卖建议;"
        "每个因子结论携带数据窗口;清算/盘口深度/全市场人数比未采集,涉及则明示不支持。"
    ),
)
async def post_diagnose(
    payload: DiagnoseRequest,
    ch: ClickHouseDep,
    # 会员刀1:额度闸(429)替换裸 CurrentUserDep —— 依赖内部已含鉴权,返回 User。
    # 🔴 QuotaDep 只查不扣;扣减回调由 get_structure_diagnosis 在缓存 miss、
    #    LLM 真跑成功后调用(命中缓存不扣 · LLM 失败不扣)。
    current_user: Annotated[User, Depends(require_quota("diagnose"))],
    lang: RequestLangDep,
) -> StructureDiagnosis:
    raw_client = ch._client  # noqa: SLF001 — 房规:读层收裸 AsyncClient(同上)
    # ★i18n:lang 由 RequestLangDep 解析(2026-07-05 收窄=仅 X-Lang override,否则 zh ·
    #   language_pref/Accept 停用 · 见 i18n/lang.py + 0047)· zh 逐字节零变化。
    try:
        return await get_structure_diagnosis(
            raw_client,
            payload.symbol,
            payload.question,
            user_id=str(current_user.id),
            on_llm_run=make_quota_consumer(current_user.id, "diagnose"),
            language=lang,
        )
    except NoFactorDataError as e:
        # 友好闸:无效 symbol / 非 USDT 永续 → 422(用户输入面 · 未进 LLM 零成本)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=translate("structure.no_factor_data", lang, symbol=e.symbol),
        ) from e
    except ValueError as e:
        # LLM 输出解析失败(不产兜底假诊断 · 不污染缓存)→ 502 让用户重试
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=translate("structure.diagnosis_generation_failed", lang, e=e),
        ) from e
