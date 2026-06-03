"""港股行业(板块)· yfinance GICS 源采集 + 英中映射 + 板块聚合(港股板块 A2)。

🔴 红线:只读行业分类 · 仅首页板块聚合展示 · 不参与下单/撮合/余额。采不到/空 sector → 归「其他」。

数据流:worker `hk_sector_scan` 遍历行情池 ~900 → yfinance `.info` sector → upsert hk_sector 表 →
`/hk/sectors` 端点 join 本表(code→sector)+ 新浪 spot(行情池涨跌/成交额)→ 按【中文板块】聚合。
生产实测:50 只 1.94s · 背靠背 180 调用 0 限流 · ~900 只 ≈ 35s · 主流 sector 拿到率 100%。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import yfinance as yf
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hk_sector import HkSector
from app.schemas.hk_market import HkSectorAgg
from app.services.hk_pool import normalize_hk_code

# GICS 11 大类(yfinance .info sector)→ 中文 · 空/未知归「其他」(不瞎填行业)
_OTHER = "其他"
GICS_CN: dict[str, str] = {
    "Technology": "科技",
    "Communication Services": "通讯服务",
    "Financial Services": "金融",
    "Energy": "能源",
    "Healthcare": "医疗",
    "Industrials": "工业",
    "Consumer Cyclical": "可选消费",
    "Consumer Defensive": "必需消费",
    "Real Estate": "地产",
    "Basic Materials": "原材料",
    "Utilities": "公用事业",
}


def _to_yf_code(symbol: str) -> str:
    """5 位港股代码 → yfinance ticker(去前导 0 补 4 位 + '.HK')· 与 hk_source 一致。"""
    return normalize_hk_code(symbol).lstrip("0").zfill(4) + ".HK"


def _fetch_one_sector(code: str) -> tuple[str, str | None]:
    """探一只 sector · 返 (规范化 code, sector 英文|None)· 异常/空 → None(归其他)。"""
    try:
        info = yf.Ticker(_to_yf_code(code)).info
        return normalize_hk_code(code), (info.get("sector") or None)
    except Exception:  # noqa: BLE001 · 采集要吞异常,一只挂不能拖垮整批(失败 → None → 归其他)
        return normalize_hk_code(code), None


def collect_hk_sectors(codes: list[str], max_workers: int = 8) -> list[tuple[str, str]]:
    """worker 用:线程池并发取 N 只 sector · 只返拿到非空 sector 的 (code, sector_en)(空的不入表)。

    同步阻塞(yfinance)· 调用方经 asyncio.to_thread 跑。生产 ~900 只 ≈ 35s(实测不限流)。
    """
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        results = list(ex.map(_fetch_one_sector, codes))
    return [(code, sector) for code, sector in results if sector]


async def upsert_hk_sectors(db: AsyncSession, rows: list[tuple[str, str]]) -> int:
    """worker 采后 upsert hk_sector 表(主键 code 冲突 → 更新 sector/updated_at)· 返写入行数。"""
    if not rows:
        return 0
    now = datetime.now(UTC)
    values = [{"code": code, "sector": sector, "updated_at": now} for code, sector in rows]
    stmt = pg_insert(HkSector).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={"sector": stmt.excluded.sector, "updated_at": stmt.excluded.updated_at},
    )
    await db.execute(stmt)
    await db.commit()
    return len(rows)


async def load_sector_map(db: AsyncSession) -> dict[str, str]:
    """读 hk_sector 全表 → {规范化 code: sector 英文} · 给 /hk/sectors 聚合用。"""
    result = await db.execute(select(HkSector.code, HkSector.sector))
    return {str(code): str(sector) for code, sector in result.all()}


def aggregate_hk_sectors(
    sector_map: dict[str, str],
    spot_rows: Iterable[tuple[str, str, float, float]],
) -> list[HkSectorAgg]:
    """按【中文板块】聚合行情池 spot · 纯函数(无 IO · 可单测)。

    spot_rows = (code, name, change_pct, amount)。板块涨跌% = 成交额加权(无成交额回退简单均值)·
    领涨股 = 板块内 change_pct 最大者。结果按板块涨跌% 降序(对标 A股 select_latest_sectors)。
    """
    buckets: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for code, name, change_pct, amount in spot_rows:
        sector_en = sector_map.get(normalize_hk_code(code))
        cn = GICS_CN.get(sector_en, _OTHER) if sector_en else _OTHER
        buckets[cn].append((name, change_pct, amount))

    out: list[HkSectorAgg] = []
    for cn, members in buckets.items():
        count = len(members)
        total_amount = sum(a for _, _, a in members)
        if total_amount > 0:
            change_pct = sum(cp * a for _, cp, a in members) / total_amount
        else:
            change_pct = sum(cp for _, cp, _ in members) / count if count else 0.0
        leader_name, leader_cp, _ = max(members, key=lambda m: m[1])
        out.append(HkSectorAgg(
            name=cn, change_pct=round(change_pct, 2), stock_count=count,
            total_amount=total_amount, leader_name=leader_name,
            leader_change_pct=round(leader_cp, 2),
        ))
    out.sort(key=lambda s: s.change_pct, reverse=True)
    return out
