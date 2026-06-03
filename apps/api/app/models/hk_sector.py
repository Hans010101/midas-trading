"""港股行业(板块)分类表 · 港股板块 A2(yfinance GICS 行业源)。

═══════════════════════════════════════════════════════════════════════════
🔴 红线:
   - 只读行业分类数据 · 仅用于首页板块聚合展示 · 绝不参与下单 / 撮合 / 余额任何计算。
   - 行业来自 yfinance `Ticker.info` 的 GICS sector(已是港股 K线备用源 · 生产可达 · 免费)。
   - 采不到 / sector 空(小盘股常见)→ 不入表 → 聚合时归「其他」(不瞎填行业)。
═══════════════════════════════════════════════════════════════════════════

数据源:worker `tasks.market.hk_sector_scan` 遍历行情池 ~900 只 → yfinance `.info` 拿 GICS sector
(英文 11 大类)→ upsert 本表。生产实测:50 只 1.94s · 背靠背 180 调用 0 限流 · ~900 只 ≈ 35s。
读取:`/hk/sectors` 端点 join 本表(code→sector)+ 新浪 spot(行情池涨跌/成交额)→ 按板块聚合。
刷新:每周 beat(行业分类稳定 · 不需每日)+ worker_ready 启动采一次。sector 英→中映射在 service 层。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HkSector(Base):
    """港股行业分类 · 主键规范化 5 位代码 · worker 周级 upsert 刷新。"""

    __tablename__ = "hk_sector"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)   # 规范化 5 位港股代码
    sector: Mapped[str] = mapped_column(String(48), nullable=False)  # GICS sector 英文(11 大类)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )
