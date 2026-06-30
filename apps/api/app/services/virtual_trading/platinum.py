"""铂金多账户共享 helper(多账户 PR-2)· 查铂金用户(is_platinum)。

铂金 = superadmin 手动设的 is_platinum 标记(PR-1)· 每铂金用户配托管/智能影子账户(PR-2 account.py)。
worker(PR-4 遍历开平)+ 自助端点(PR-5)共用本模块查铂金用户列表。🔴只读 User.is_platinum · 不碰引擎。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.user import User
from app.models.virtual import VirtualAccount

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_platinum_user_ids(session: AsyncSession) -> list[UUID]:
    """所有铂金用户(真人)id 列表 · where is_platinum=true。

    ★比订阅查询简单(PR-1 加的 User.is_platinum 字段·superadmin 手动设)。
    PR-4 worker open scan 遍历此列表 → 各自影子账户开仓。空列表 → 无铂金用户可开(全局账户照常)。
    """
    rows = await session.scalars(select(User.id).where(User.is_platinum.is_(True)))
    return list(rows)


async def get_account_owner_uids(
    session: AsyncSession, account_ids: Sequence[int],
) -> dict[int, UUID]:
    """批量:account_id → 所属 user_id(PR-4a close 逐仓反查 owner)。

    ★全局仓 → 全局系统账户 user_id · 影子仓 → 影子系统账户 user_id。
    close 监控全表扫活仓(不收窄)后,用本映射给每仓配【自己账户的 uid】平 → 修 close uid 错配
    (旧版对所有仓用全局 uid → 影子仓 _active_position 解析不到 → 只开不平)。🔴只读 · 不碰引擎。
    """
    ids = set(account_ids)
    if not ids:
        return {}
    result = await session.execute(
        select(VirtualAccount.id, VirtualAccount.user_id).where(VirtualAccount.id.in_(ids)),
    )
    return dict(result.tuples().all())


async def get_account_owner_uid(session: AsyncSession, account_id: int) -> UUID | None:
    """单个 account_id → owner user_id(close_one 手动平用)· 账户不存在 → None。"""
    return (await get_account_owner_uids(session, [account_id])).get(account_id)
