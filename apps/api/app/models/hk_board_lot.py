"""港股每手股数(board lot)表 · 下单池扩量 A2(方案A · HKEX 官方源)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 只读引用数据 · 下单【按手取整】用 · 绝不参与撮合 / 余额 / 强平任何计算。
   - 每手股数全用港交所官方 ListOfSecurities(最准)· worker 每日采(自动跟港交所改革)。
   - 查不到(表无 + 18 种子兜底也无)→ hk_lot_size 返 None → 不进下单池(宁缺毋滥,不瞎填)。
═══════════════════════════════════════════════════════════════════════════

数据源:worker `tasks.market.hk_board_lot_scan` 每日下载 HKEX 官方 ListOfSecurities.xlsx →
解析主板 HKD 普通股(~2406)→ upsert 本表(A1 已生产实测可达:200 + 2406 + 解析零失败)。
读取:`get_hk_board_lot(db, code)` 优先查本表 · 表无则回退 hk_pool 18 只硬编码种子(过渡/兜底)。
刷新:每日 upsert(港交所文件每日更新 · 如汇丰 400 改了次日自动跟)。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HkBoardLot(Base):
    """港股每手股数 · 主键规范化 5 位代码 · worker 每日 upsert 刷新。"""

    __tablename__ = "hk_board_lot"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # 规范化 5 位港股代码
    name: Mapped[str] = mapped_column(String(64), nullable=False)   # 证券名(下单池 UI 展示用)
    lot: Mapped[int] = mapped_column(Integer, nullable=False)       # 每手股数(港交所官方)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
