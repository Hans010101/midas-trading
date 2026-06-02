"""港股每手股数(board lot)· HKEX 官方 List of Securities 下载 + 解析 + lot 表读写。

阶段三方案 A · 全市场主板 HKD 下单池的每手股数源(替代 hk_pool 18 只硬编码种子)。
- 源:港交所官方 `ListOfSecurities.xlsx`(每日更新 · 自动跟 2025-12「精简每手框架」改革)。
- A1(/hk/board-lot-scan 端点):生产实测可达 —— 下载 + 解析,只读不写库(已生产验:200/2406/零失败)。
- A2a(本服务 + worker + lot 表):worker 每日采 → upsert `hk_board_lot` 表 →
  `get_hk_board_lot(db)` 优先读表 · 表无回退 18 种子 · 下单池扩到 ~2406。

★ 红线:每手股数全用 HKEX 官方(最准)· 解析不出 / 非主板 HKD / 表无且种子无 → None(不进下单池)。
详见 docs/research/hk-board-lot-batch-source.md。
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hk_board_lot import HkBoardLot
from app.services.hk_pool import hk_lot_size, normalize_hk_code

logger = logging.getLogger(__name__)

HKEX_LOS_URL = (
    "https://www.hkex.com.hk/eng/services/trading/securities/"
    "securitieslists/ListOfSecurities.xlsx"
)
_HEADER_ROW = 2  # 第 0 行「List of Securities」· 第 1 行「Updated as at ...」· 第 2 行才是真表头
_TIMEOUT = 60.0
# 浏览器 UA(HKEX 可能拒默认客户端 UA · 与本机 curl 实测一致)
_UA = "Mozilla/5.0 (compatible; MidasBoardLotSync/1.0)"
# 下单池范围:主板普通股 + HKD 计价(剔除 GEM / RMB counter / 衍生品)
_MAIN_BOARD = "Equity Securities (Main Board)"
_HKD = "HKD"
# 抽验样本(已知正确值 · 验解析对:00700=100 / 00005=400 / 01211=100)
_SAMPLE_CODES = ("00700", "00005", "01211", "03690", "09988", "00939")


@dataclass(frozen=True)
class HkBoardLotRow:
    """主板 HKD 普通股一行(worker upsert lot 表用)。"""

    code: str  # 规范化 5 位港股代码
    name: str
    lot: int


@dataclass(frozen=True)
class BoardLotScanResult:
    """HKEX board lot 下载+解析结果(A1 探测端点 + A2 worker 采集共用)。"""

    ok: bool
    http_code: int
    bytes_downloaded: int
    updated_as_at: str | None  # 文件头「Updated as at DD/MM/YYYY」· 确认数据新鲜度
    total_rows: int  # 文件全部证券行(~17880 · 含衍生/债/ETF · 仅供参考)
    mainboard_hkd_count: int  # 主板 HKD 普通股(= 下单池目标量 · ~2406)
    parse_errors: int  # board lot 解析失败数(应为 0)
    rows: list[HkBoardLotRow] = field(default_factory=list)  # 主板 HKD (code,name,lot)
    samples: dict[str, int] = field(default_factory=dict)  # 抽验样本
    error: str | None = None


def _empty_fail(http_code: int, error: str) -> BoardLotScanResult:
    return BoardLotScanResult(
        ok=False, http_code=http_code, bytes_downloaded=0, updated_as_at=None,
        total_rows=0, mainboard_hkd_count=0, parse_errors=0, error=error,
    )


def fetch_hkex_board_lots() -> BoardLotScanResult:
    """阻塞:下载 + 解析 HKEX List of Securities → 主板 HKD 普通股 (code,name,lot) rows。

    ★ 同步阻塞(httpx.get + pd.read_excel)· 调用方须经 `asyncio.to_thread` 跑,
      绝不在事件循环里直接调(项目约定 · 同 chan._analyze_sync)。
    """
    try:
        resp = httpx.get(
            HKEX_LOS_URL, timeout=_TIMEOUT, follow_redirects=True,
            headers={"User-Agent": _UA},
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[hk_board_lot] download error: %s", e)
        return _empty_fail(0, f"download error: {e}")

    if resp.status_code != 200:
        return _empty_fail(resp.status_code, f"HTTP {resp.status_code}")

    raw = resp.content
    try:
        head = pd.read_excel(io.BytesIO(raw), header=None, nrows=2, engine="openpyxl")
        updated = str(head.iloc[1, 0]).strip() if len(head) > 1 else None
        df = pd.read_excel(io.BytesIO(raw), header=_HEADER_ROW, engine="openpyxl")
    except Exception as e:  # noqa: BLE001
        logger.warning("[hk_board_lot] parse error: %s", e)
        return _empty_fail(resp.status_code, f"parse error: {e}")

    df.columns = [str(c).strip() for c in df.columns]
    required = {"Stock Code", "Name of Securities", "Sub-Category", "Board Lot", "Trading Currency"}
    if not required.issubset(df.columns):
        return _empty_fail(
            resp.status_code,
            f"unexpected columns: {list(df.columns)[:10]}",
        )

    mb = df[
        (df["Sub-Category"] == _MAIN_BOARD) & (df["Trading Currency"] == _HKD)
    ]
    rows: list[HkBoardLotRow] = []
    errors = 0
    for code_raw, name_raw, lot_raw in zip(
        mb["Stock Code"], mb["Name of Securities"], mb["Board Lot"], strict=False,
    ):
        code = str(code_raw).strip().zfill(5)
        try:
            lot = int(str(lot_raw).replace(",", "").strip())
        except (ValueError, TypeError):
            errors += 1
            continue
        if lot > 0:
            rows.append(HkBoardLotRow(code=code, name=str(name_raw).strip()[:64], lot=lot))
        else:
            errors += 1

    lots = {r.code: r.lot for r in rows}
    return BoardLotScanResult(
        ok=True,
        http_code=200,
        bytes_downloaded=len(raw),
        updated_as_at=updated,
        total_rows=int(len(df)),
        mainboard_hkd_count=len(rows),
        parse_errors=errors,
        rows=rows,
        samples={c: lots[c] for c in _SAMPLE_CODES if c in lots},
    )


async def upsert_board_lots(db: AsyncSession, rows: list[HkBoardLotRow]) -> int:
    """worker 每日采后 upsert lot 表(主键 code 冲突 → 更新 name/lot/updated_at)· 返写入行数。"""
    if not rows:
        return 0
    now = datetime.now(UTC)
    values = [{"code": r.code, "name": r.name, "lot": r.lot, "updated_at": now} for r in rows]
    stmt = pg_insert(HkBoardLot).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["code"],
        set_={
            "name": stmt.excluded.name,
            "lot": stmt.excluded.lot,
            "updated_at": stmt.excluded.updated_at,
        },
    )
    await db.execute(stmt)
    await db.commit()
    return len(rows)


async def resolve_hk_board_lot(db: AsyncSession, code: str) -> int | None:
    """港股每手股数:优先 PG lot 表(worker 每日采 HKEX)· 表无回退 hk_pool 18 种子 · 仍无 None。

    ★ 下单按手取整 + /hk/board-lot 端点都用此函数 · None = 不在下单池(红线宁缺毋滥,不可下单)。
    种子兜底:lot 表冷启动(worker 还没采)/ DB 故障时,18 只仍可下单(不回归)· 其余暂不可。
    """
    norm = normalize_hk_code(code)
    lot = await db.scalar(select(HkBoardLot.lot).where(HkBoardLot.code == norm))
    if lot is not None:
        return int(lot)
    return hk_lot_size(norm)  # 种子兜底(18 只 · BYD 已修 100)· 无则 None
