"""市场结构快照 Pydantic 契约 · 研究室「结构分析助手」第1刀(数据层)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:纯【客观结构描述】数据 —— 只读 ClickHouse 已采衍生品因子,不预测价格、
   不下单、不碰撮合/真实交易。LLM 诊断是第2刀,本层只做因子聚合。
═══════════════════════════════════════════════════════════════════════════

window 字段是【强制数据口径】(TTL 约束的产品化):核心因子表 60 天滚动 TTL、
premium 表仅 7 天 —— 下游(含 LLM prompt)绝不允许把这些窗口冒充长期历史基线。
"""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class StructureFactor(BaseModel):
    """单个因子读数 · value 键值随因子而异(见 service 各 build 函数)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: dict[str, float]                          # 因子数值组(键名见 service)
    window: str = Field(min_length=1, max_length=16)  # 数据口径:"24h" / "7d" / "latest"
    asof: AwareDatetime                              # 该因子最新数据点时间
    text: str | None = Field(default=None, max_length=40)  # 可读标签(仅 FGI classification 用)


class StructureSnapshot(BaseModel):
    """7 因子结构快照 · 单 symbol(USDT 永续 · Binance 风格无斜杠)。

    任一因子查无数据 → 该项 None(527 symbol 覆盖不均是常态,不阻塞整体)。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str = Field(min_length=1)                # 'BTCUSDT'
    generated_at: AwareDatetime

    account_long_short: StructureFactor | None = None   # 大户账户多空比(latest + avg_24h)
    position_long_short: StructureFactor | None = None  # 大户持仓多空比(latest + avg_24h)
    taker_flow: StructureFactor | None = None           # taker 主动买卖比(latest + avg_24h)
    open_interest: StructureFactor | None = None        # OI(oi_usd / oi_coin / change_pct_24h)
    funding_rate: StructureFactor | None = None         # 资金费率(latest + 7d avg/max/min)
    basis: StructureFactor | None = None                # 基差 mark-index(premium 表仅 7d)
    sentiment: StructureFactor | None = None            # FGI + BTC dominance(全市场 · 非单 symbol)


# ═══ 第2刀 · LLM 结构诊断 ═══════════════════════════════════════════════════

# 自然语言问题 → 5 类归一意图(枚举化 = 诊断层可缓存的前提)
IntentKind = Literal[
    "long_crowding", "short_crowding", "leverage_buildup", "funding_extreme", "overall",
]


class FactorFinding(BaseModel):
    """单因子状态结论(LLM 产出 · validator 改写后)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    factor: str = Field(min_length=1, max_length=32)   # 因子键名(对齐快照字段)
    state: str = Field(min_length=1, max_length=40)    # 状态短语(偏多拥挤/中性/费率偏高…)
    detail: str = Field(min_length=1, max_length=300)  # 客观描述(含数值 · 非预测)
    window: str = Field(min_length=1, max_length=16)   # 数据口径(照抄快照 window · 红线②)


class DiagnoseRequest(BaseModel):
    """POST /api/v1/structure/diagnose 请求体。"""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=3, max_length=32)
    question: str = Field(min_length=2, max_length=200)


class StructureDiagnosis(BaseModel):
    """结构诊断结果(结论先行 · 分因子状态 · 口径随行)· 🔴 非价格预测。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    conclusion: str = Field(min_length=1, max_length=400)   # 一句话总体结构判断
    factor_findings: list[FactorFinding]                    # 分因子状态(相关因子在前)
    intent: IntentKind                                      # 归一意图
    unsupported_note: str | None = Field(default=None, max_length=200)  # 缺失维度说明(红线③)
    snapshot: StructureSnapshot                             # 因子快照(前端数据下钻用)
