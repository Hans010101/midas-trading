"""兑换码 service · 兑换码模块刀1(生成 + 兑换)。

🔴 红线:本模块【不 import】virtual_trading / engine —— 兑换开的是会员权益(走
   extend_subscription),非交易;与邀请/支付共用同一开权益引擎,仅 source 不同。
复用 pro 档(extend 硬编码 plan='pro')· 额度 resolve_plan/PLAN_QUOTAS 零改。
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.redeem_code import RedeemCode
from app.services.growth import extend_subscription
from app.services.membership import PERIOD_DAYS

# Crockford base32(去易混 I/L/O/U)· 12 位 ≈ 32^12 ≈ 1.15e18 空间,不可猜;
# 撞码由 unique 约束 + 重试兜底(照 invite_code 范式 · 本码加长到 12 位)
_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_LEN = 12
_VALID_DAYS = 365  # 生成起 1 年有效
MAX_BATCH = 100  # 单次生成上限(防误操作 / 滥用)


class RedeemError(Exception):
    """兑换失败基类 · API 层映射到结构化 4xx(各态不同 code/detail)。"""

    code = "redeem_error"
    http_status = 400


class RedeemNotFound(RedeemError):  # noqa: N818 — 与 RedeemError 基类成系列,语义清晰
    code = "not_found"
    http_status = 404


class RedeemAlreadyUsed(RedeemError):  # noqa: N818
    code = "already_used"
    http_status = 409


class RedeemExpired(RedeemError):  # noqa: N818
    code = "expired"
    http_status = 410


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


def normalize_code(raw: str) -> str:
    """兑换输入归一:trim + 大写(用户可能小写/带空格输入)。"""
    return raw.strip().upper()


# ── 生成(管理员)─────────────────────────────────────────────────────────


async def generate_codes(
    db: AsyncSession,
    *,
    admin_id: UUID,
    period: str,
    count: int,
    note: str | None = None,
) -> list[RedeemCode]:
    """批量生成 count 个唯一码 · days 按 period 固化 · expires=now+1年。

    撞码(unique 冲突)概率近零(1e18 空间),仍逐码查重 + 重试 5 次兜底。
    period 非法 → ValueError(API 层 422);count 越界由 API 层 schema 卡。
    """
    if period not in PERIOD_DAYS:
        raise ValueError(f"unknown period: {period}")
    now = datetime.now(UTC)
    days = PERIOD_DAYS[period]
    expires_at = now + timedelta(days=_VALID_DAYS)
    created: list[RedeemCode] = []
    for _ in range(count):
        for _attempt in range(5):
            code = _gen_code()
            dup = await db.scalar(select(RedeemCode.id).where(RedeemCode.code == code))
            if dup is None:
                break
        else:
            raise RuntimeError("兑换码生成 5 次均撞码(1e18 空间 · 概率近零)")
        row = RedeemCode(
            code=code, period=period, days=days, note=note,
            created_by=admin_id, expires_at=expires_at,
        )
        db.add(row)
        created.append(row)
    await db.flush()
    return created


# ── 兑换(登录用户)· rowcount 幂等 ─────────────────────────────────────────


async def redeem(db: AsyncSession, *, user_id: UUID, code: str) -> tuple[int, datetime | None]:
    """兑换一码 → 开/续 pro(source='redeem' · 不传 cap_days 不封顶)。

    返回 (days_added, new_expires_at)· plan 恒为 'pro'(extend 硬编码)。
    分类报错(各态友好):不存在 404 / 已兑换 409 / 已过期 410。
    ★ 并发/重复点恰好一次:UPDATE ... WHERE redeemed_by IS NULL AND expires_at>now
    的 rowcount 判定(照邀请兑现范式);rowcount=1 才开权益,同事务提交。
    """
    norm = normalize_code(code)
    now = datetime.now(UTC)

    row = await db.scalar(select(RedeemCode).where(RedeemCode.code == norm))
    if row is None:
        raise RedeemNotFound("兑换码不存在")
    if row.redeemed_at is not None:
        raise RedeemAlreadyUsed("兑换码已被使用")
    if row.expires_at <= now:
        raise RedeemExpired("兑换码已过期")

    # ★ rowcount 闸:并发双击 / 抢兑恰好一次成功
    result = await db.execute(
        update(RedeemCode)
        .where(
            RedeemCode.code == norm,
            RedeemCode.redeemed_by.is_(None),
            RedeemCode.expires_at > now,
        )
        .values(redeemed_by=user_id, redeemed_at=now)
        .returning(RedeemCode.days),
    )
    claimed = result.first()
    if claimed is None:
        # 上面 SELECT 后、UPDATE 前被人抢走(竞态)→ 已用
        raise RedeemAlreadyUsed("兑换码已被使用")

    days = int(claimed[0])
    new_exp = await extend_subscription(db, user_id, days, "redeem")  # 不传 cap_days = 不封顶
    await db.commit()  # 码标记 + 开权益同事务
    return days, new_exp


# ── 列表(管理员)· 状态派生 ─────────────────────────────────────────────────


def derive_status(redeemed_at: datetime | None, expires_at: datetime, now: datetime) -> str:
    """status 派生(不存列):已兑现 / 已过期 / 未用。"""
    if redeemed_at is not None:
        return "redeemed"
    if expires_at <= now:
        return "expired"
    return "unused"


async def count_codes(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(RedeemCode))).scalar_one())
