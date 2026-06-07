"""研究室回测运行记录(P1-4c 块3)· vibe 回测结果落库。

生命周期:
  1. api/Celery 触发回测 → 落一行(status='pending')。
  2. midas-vibe 容器执行(路径B · run_backtest_job)→ artifacts。
  3. 解析 artifacts → 回填 metrics_json + status='done'(失败则 status='error' + error)。

🔴 红线:纯研究记录 · 绝不参与撮合 / 下单 / 余额任何计算 · loader 只读 CH。
  user_id 为软引用(不加 FK 约束 · 匿名研究跑也允许 NULL)。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, String, Text, Uuid, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BacktestRun(Base):
    """一次回测运行 · 入参 + 状态 + 16 指标结果(JSONB)。"""

    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 软引用 user(无 FK · 匿名研究跑可空)
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    # vibe 容器返回的 run_id(关联 run_dir · 落 done 时回填)
    run_id: Mapped[str | None] = mapped_column(String(64))

    # ===== 回测入参 =====
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)  # 当前仅 crypto
    period: Mapped[str] = mapped_column(String(8), nullable=False)  # 1m/.../1d/1w
    start_date: Mapped[str] = mapped_column(String(16), nullable=False)  # YYYY-MM-DD
    end_date: Mapped[str] = mapped_column(String(16), nullable=False)
    # 完整 BacktestParams(含 SMA 窗口 / 资金)· 前向兼容
    params_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)

    # ===== 状态机 =====
    # pending → (容器执行)→ done / error
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'"),
    )
    # 16 个标量指标(done 时回填 · 见 service.BacktestMetrics)
    metrics_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    # P1-4c.5 full-data:收益曲线 / 逐笔 / run_card 方法学脚注(done 时回填 · 与 metrics_json 一致)·
    #   数据来自 parse_artifacts 返回的 BacktestResult,B 档报告 UI 取数渲染(ADR 0038 D4)。
    equity_json: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    trades_json: Mapped[list[dict[str, object]] | None] = mapped_column(JSONB)
    run_card_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        # 我的回测历史按 (用户, 时间) 倒序列
        Index("ix_backtest_runs_user_created", "user_id", "created_at"),
    )
