"""AI 决策卡历史记录 · 自学习闭环地基(ADR 0036 批次乙)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 纯只读历史记录,绝不参与撮合 / 下单 / 余额任何计算。
   - 端点旁路记录(best-effort try/except),失败必须吞掉不阻塞响应。
   - reflection 只读 ClickHouse 历史 K 线回填,不触发实时上游 / 不写 CH。
   - 不改 analyze 主流程(workflow / agents 零改动)。
═══════════════════════════════════════════════════════════════════════════

设计要点(对齐 perp.py 量纲约定):
- 价格(price_at / price_after)= Numeric(20, 8) · 跨市场统一(crypto 八位小数也兜得住)。
- 收益率(actual_return)= Numeric(10, 6) · ±99.9999 倍以内,足够 5d horizon 的任何币。
- composite_confidence = Numeric(5, 4) · 0.0000..1.0000(对齐 schema 的 0.0..1.0 契约)。
- direction 由 composite_label 映射(强多/弱多 → bull · 中性 → flat · 弱空/强空 → bear),
  在端点旁路时计算,模型只存归一化结果(节省 reflection 时的判断成本)。
- analyzed_at 索引 + 部分索引 WHERE reflected_at IS NULL,给 reflection 扫描走 index-only。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AIAnalysisMemory(Base):
    """AI 决策卡历史 · 旁路记录每次 cache-miss 生成的卡 + reflection 回填实测涨跌。

    生命周期:
      1. 决策卡端点 cache-miss → workflow 生成 card → best-effort 写一行(reflected_at NULL)。
      2. Celery beat 每日扫 reflected_at IS NULL AND analyzed_at <= now - 5d 的行。
      3. 只读 CH 取 ts >= analyzed_at + 5d 首根 close 作为 price_after,回写四列。

    direction 语义:AI 对未来的方向判断(派生自 composite_label · 端点旁路时算)。
    was_correct 判定(reflection 时算):
      · bull → actual_return > 0
      · bear → actual_return < 0
      · flat → |actual_return| < 0.01(1%)

    🔴 纯元数据 · 不参与撮合 / 余额 / 强平任何计算。
    """

    __tablename__ = "ai_analysis_memory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # ===== 标识(对齐决策卡 cache key + 缠论参数)=====
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # cn/us/crypto/hk
    instrument: Mapped[str] = mapped_column(
        String(8), nullable=False, server_default=text("'spot'"),
    )  # spot/perp(0017 ADR)
    period: Mapped[str] = mapped_column(String(8), nullable=False)  # 1m/5m/15m/30m/1h/1d/1w

    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )

    # ===== AI 判断快照(决策卡产出)=====
    # direction: bull/bear/flat · composite_score: -100..100
    # composite_label: 强多/弱多/中性/弱空/强空 · composite_confidence: 0.0000..1.0000
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    composite_score: Mapped[int] = mapped_column(Integer, nullable=False)
    composite_label: Mapped[str] = mapped_column(String(8), nullable=False)
    composite_confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False,
    )

    # 分析时最新 close 价(klines[-1].close)
    price_at: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)

    llm_mode: Mapped[str] = mapped_column(String(8), nullable=False)  # mock/real

    # ===== Reflection 回填(初写时全部 NULL · Celery beat 5d 后回填)=====
    reflected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # horizon 后实测 close 价
    price_after: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    # (price_after - price_at) / price_at · 比例值(0.0234 = 2.34%)
    actual_return: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    was_correct: Mapped[bool | None] = mapped_column(Boolean)

    # 索引设计:
    #   ix_ai_memory_analyzed_at - reflection / 命中率统计按时间窗扫
    #   ix_ai_memory_pending_reflection - 部分索引(reflected_at IS NULL),
    #     reflection 每日只读未回填行 → index-only scan,扫表代价 O(待回填数)
    #   ix_ai_memory_market_reflected - 命中率分桶聚合按 (市场, 是否已回填) 走
    __table_args__ = (
        Index("ix_ai_memory_analyzed_at", "analyzed_at"),
        Index(
            "ix_ai_memory_pending_reflection",
            "analyzed_at",
            postgresql_where=text("reflected_at IS NULL"),
        ),
        Index(
            "ix_ai_memory_market_reflected",
            "market", "reflected_at",
        ),
    )
