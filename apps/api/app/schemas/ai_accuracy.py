"""AI 历史命中率 Pydantic 契约 · 自学习闭环呈现层(ADR 0036 批次乙 sub-unit C)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 纯只读统计 · 基于 reflection 已验证记录(ai_analysis_memory.was_correct)。
   - 不碰下单 / 交易 / 撮合 · 不改 analyze 主流程 · 不打实时上游(只读 PG)。
   - ★ 样本量诚实标注:每桶给 sample_count + reliable,避免「3 条全对 = 100%」误导。
═══════════════════════════════════════════════════════════════════════════

借鉴 QuantDinger calibration 思路分桶(但本期不接 QuantDinger 实盘部分 · ADR 0036):
按 市场 / 方向 / 置信度区间 三个维度各自聚合 was_correct → hit_rate + sample_count。
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class AccuracyBucket(BaseModel):
    """单个分桶的命中率 + 样本数(★样本诚实标注的最小单元)。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)          # 桶标识(如 "cn" / "bull" / "60-70")
    label: str = Field(min_length=1)        # 人类可读(如 "A股" / "看多" / "60-70%")
    # 命中率 0.0..1.0 · ★ 样本为 0 时为 None(不写 0.0,避免「0% 命中」误导)
    hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    sample_count: int = Field(ge=0)         # 已验证样本数(基于多少条算出命中率)
    correct_count: int = Field(ge=0)        # 命中数(was_correct=True)
    # ★ 样本是否足够可靠(>= min_reliable_sample)· 前端据此决定灰显 / 加「样本不足」标注
    reliable: bool


class AiAccuracyResponse(BaseModel):
    """GET /api/v1/analysis/ai-accuracy 响应 · AI 历史命中率(总体 + 三维分桶)。

    所有命中率均基于 reflection 事后验证的记录(was_correct IS NOT NULL)。
    ★ 小样本桶(sample_count < min_reliable_sample · reliable=False)命中率仅供参考。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    generated_at: AwareDatetime

    # ===== 总体 =====
    overall_hit_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_sample_count: int = Field(ge=0)
    overall_correct_count: int = Field(ge=0)

    # ===== 三维分桶 =====
    by_market: list[AccuracyBucket]         # cn / us / crypto
    by_direction: list[AccuracyBucket]      # bull / bear / flat
    by_confidence: list[AccuracyBucket]     # <50 / 50-60 / ... / 90-100

    # ===== 统计口径(★诚实标注)=====
    min_reliable_sample: int = Field(ge=0)  # 可靠阈值 · 告知前端
    # 回显本次统计的过滤条件(便于前端展示「real 模型 / 最近 90 天」之类)
    llm_mode_filter: str | None = None
    since_days: int | None = None
    # 统计口径说明(中文 · 含小样本告知)· 非投资建议 disclaimer
    note: str = ""
